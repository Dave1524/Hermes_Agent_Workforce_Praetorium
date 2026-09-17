#!/usr/bin/env python3
"""Route actionable workflow incidents to the Buzz incidents stream (T5.3c).

    incident_notify.py [--mode sweep] [--digest] [--dry-run] [--now ISO] [...overrides]

One sweep: derive incidents from the Control Room read model (bin/workflow_incidents.py),
reconcile them into the state file (bin/incident_state.py), then send — one `[incident]`
message per newly open immediate-class incident, one `[recovered]` per closed one that was
alerted, and one `[incident digest]` a day while anything stays unresolved. Every send goes
through bin/deliver.sh; a send that fails is recorded on the entry and never fails the sweep.
Exit is non-zero only when the sweep itself cannot run (state unwritable).

Runs only as workflow-incidents.service or by hand. No run path references it.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import incident_state as state_io  # noqa: E402
import workflow_incidents as wi  # noqa: E402
from control_room_api import ControlRoomReadModel, SourcePaths, SystemdReader  # noqa: E402
from workflow_receipt import iso_utc, parse_time, utc_now  # noqa: E402

BIN_DIR = pathlib.Path(__file__).resolve().parent
HOME = pathlib.Path.home()
POINTER = "buzz://message?channel={channel}&id={event}"
SENT_OUTCOMES = {"delivered", "partial_success"}


def env_int(name: str, default: int) -> int:
    raw = os.environ.get(name, "")
    return int(raw) if raw.isdigit() else default


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    runtime = pathlib.Path(os.environ.get("CONTROL_ROOM_RUNTIME_ROOT", HOME / "agent-workforce"))
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--mode", choices=["sweep"], default="sweep")
    p.add_argument("--digest", action="store_true", help="send the digest now, gate or not")
    p.add_argument("--dry-run", action="store_true", help="print what would be sent; touch nothing")
    p.add_argument("--now", help="ISO-8601 clock override, for fixtures")
    p.add_argument("--state-dir", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("INCIDENT_STATE_DIR", runtime / "var" / "incidents")))
    p.add_argument("--routes-file", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("BUZZ_ROUTES_FILE", BIN_DIR / "buzz_routes.env")))
    p.add_argument("--deliver-bin", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("INCIDENT_DELIVER_BIN", BIN_DIR / "deliver.sh")))
    p.add_argument("--receipts-log", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("DELIVERY_RECEIPTS", HOME / "logs" / "delivery-receipts.jsonl")))
    p.add_argument("--repo-root", type=pathlib.Path)
    p.add_argument("--runtime-root", type=pathlib.Path)
    p.add_argument("--receipt-root", type=pathlib.Path)
    p.add_argument("--route", default=os.environ.get("DELIVERY_ROUTE", "incidents"))
    p.add_argument("--job", default=os.environ.get("DELIVERY_JOB", "workflow-incidents.service"))
    p.add_argument("--link-template",
                   default=os.environ.get("INCIDENT_LINK_TEMPLATE", "http://praetorium:8787/api/v1/incidents#{key}"))
    p.add_argument("--grace-secs", type=int, default=env_int("INCIDENT_RECEIPT_GRACE_SECS", wi.DEFAULT_GRACE_SECS))
    p.add_argument("--digest-at", default=os.environ.get("INCIDENT_DIGEST_AT", "07:00"))
    p.add_argument("--max-sends", type=int, default=env_int("INCIDENT_MAX_SENDS_PER_SWEEP", 10))
    p.add_argument("--max-attempts", type=int, default=env_int("INCIDENT_MAX_SEND_ATTEMPTS", 6))
    p.add_argument("--retention-days", type=int, default=env_int("INCIDENT_RESOLVED_RETENTION_DAYS", 14))
    p.add_argument("--deliver-timeout", type=int, default=env_int("INCIDENT_DELIVER_TIMEOUT_SECS", 90))
    return p.parse_args(argv)


def source_paths(args: argparse.Namespace) -> SourcePaths:
    defaults = SourcePaths.defaults()
    repo = args.repo_root or defaults.repo
    runtime = args.runtime_root or defaults.runtime
    receipts = args.receipt_root or (runtime / "var" / "workflow-receipts" if args.runtime_root else defaults.receipts)
    return SourcePaths(repo=repo, runtime=runtime, receipts=receipts)


def route_channel(routes_file: pathlib.Path, route: str) -> str:
    try:
        lines = routes_file.read_text().splitlines()
    except OSError:
        return ""
    values = [line.partition("=")[2].strip().strip("\"'") for line in lines if line.startswith(f"ROUTE_{route}=")]
    return values[-1] if values else ""


# --- rendering ------------------------------------------------------------------------------
def link(template: str, key: str) -> str:
    return template.replace("{key}", key)


def render_immediate(entry: dict[str, Any], template: str) -> tuple[str, str]:
    lines = [f"workflow: {entry['workflow_id'] or 'n/a'} (unit {entry['unit'] or 'n/a'})",
             f"agent: {entry['agent'] or 'n/a'}",
             f"failure: {entry['class']} — {entry['issue']}"]
    if entry.get("failed_assertion"):
        lines.append(f"failed check: {entry['failed_assertion']}")
    lines += [f"time: first seen {entry['first_seen']} · run {entry['run_id'] or 'n/a'} · seen {entry['observations']}×",
              f"required action: {entry['required_action']}",
              f"incident: {link(template, entry['key'])}",
              f"evidence: {'; '.join(entry.get('evidence') or []) or 'none recorded'}"]
    return f"[incident] {entry['key']}", "\n".join(lines)


def render_recovery(entry: dict[str, Any], healthy_receipt: str | None) -> tuple[str, str]:
    evidence = healthy_receipt or f"observation ceased: {entry['issue']}"
    lines = [f"workflow: {entry['workflow_id'] or 'n/a'} (unit {entry['unit'] or 'n/a'})",
             f"agent: {entry['agent'] or 'n/a'}",
             f"class: {entry['class']}",
             f"open since {entry['first_seen']}, resolved {entry['resolved_at']}",
             f"evidence: {evidence}",
             "alert: " + POINTER.format(channel=entry.get("notify_channel") or "", event=entry.get("notify_event_id") or "")]
    return f"[recovered] {entry['key']}", "\n".join(lines)


def render_digest(entries: list[dict[str, Any]], template: str) -> tuple[str, str]:
    lines = []
    for entry in entries:
        line = (f"{entry['class']} {entry['workflow_id'] or 'n/a'} — since {entry['first_seen']} "
                f"(seen {entry['observations']}×, last {entry['last_seen']}) — {entry['required_action']} — "
                f"{link(template, entry['key'])}")
        if entry.get("notified_at") is None:
            line += f" — unsent ({entry.get('last_send_error') or 'route unset'})"
        lines.append(line)
    return f"[incident digest] {len(entries)} unresolved", "\n".join(lines)


# --- transport ------------------------------------------------------------------------------
class Sender:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args

    def _receipts_after(self, offset: int) -> list[dict[str, Any]]:
        try:
            with open(self.args.receipts_log, "rb") as handle:
                handle.seek(offset)
                raw = handle.read().decode("utf-8", "replace")
        except OSError:
            return []
        parsed = []
        for line in raw.splitlines():
            try:
                parsed.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return [r for r in parsed if isinstance(r, dict)]

    def send(self, subject: str, message: str) -> tuple[dict[str, Any] | None, str | None]:
        """(receipt, None) when Buzz took it; (None, error) otherwise. Never raises."""
        a = self.args
        offset = a.receipts_log.stat().st_size if a.receipts_log.exists() else 0
        command = [str(a.deliver_bin), "--job", a.job, "--route", a.route, "--runtime", "none",
                   "--subject", subject, "--message", message]
        env = {**os.environ, "DELIVER_DISCORD": "0", "BUZZ_ROUTES_FILE": str(a.routes_file),
               "DELIVERY_RECEIPTS": str(a.receipts_log)}
        try:
            completed = subprocess.run(command, env=env, capture_output=True, text=True, timeout=a.deliver_timeout, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            return None, f"{type(exc).__name__}: {exc}"
        if completed.returncode != 0:
            return None, f"deliver.sh exited {completed.returncode}"
        mine = [r for r in self._receipts_after(offset) if r.get("job") == a.job and r.get("subject") == subject]
        if not mine:
            return None, "no delivery receipt written"
        receipt = mine[-1]
        if receipt.get("outcome") in SENT_OUTCOMES and receipt.get("buzz_result") == "ok":
            return receipt, None
        return None, (f"receipt outcome={receipt.get('outcome')} buzz_result={receipt.get('buzz_result')} "
                      f"error={receipt.get('error') or 'n/a'}")


# --- the sweep ------------------------------------------------------------------------------
class Sweep:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.now = (parse_time(args.now) or utc_now()).replace(microsecond=0)
        self.log_path = HOME / "logs" / "workflow-incidents.log"
        self.sender = Sender(args)
        self.state_path = args.state_dir / "state.json"
        self.sent = 0

    def log(self, message: str) -> None:
        line = f"{iso_utc(self.now if self.args.now else utc_now())} incident_notify: {message}\n"
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.log_path, "a") as handle:
                handle.write(line)
        except OSError:
            pass
        if self.args.dry_run:
            sys.stdout.write(line)

    def observe(self) -> tuple[list[dict[str, Any]], bool, dict[str, list[dict[str, Any]]]]:
        model = ControlRoomReadModel(source_paths(self.args), systemd=SystemdReader(), clock=lambda: self.now)
        workflows, status = model.workflows()
        _, malformed, source_errors = model.receipts()
        declared, declared_errors = wi.load_declared(self.args.state_dir)
        for error in declared_errors:
            self.log(f"declared incident ignored: {error}")
        manifest_errors = status["errors"]["manifests"]
        observed = wi.derive(workflows, malformed, source_errors, declared, self.args.grace_secs,
                             manifest_errors=manifest_errors)
        healthy = {w["id"]: (w.get("lastEligibleRun") or {}).get("receiptPath") for w in workflows
                   if (w.get("lastEligibleRun") or {}).get("outcome") in {"artifact", "decline"}}
        return observed, wi.sources_visible(source_errors, manifest_errors), healthy

    def deliver(self, entry: dict[str, Any], subject: str, body: str, on_success) -> bool:
        if self.args.dry_run:
            sys.stdout.write(f"--- {subject}\n{body}\n")
            return False
        receipt, error = self.sender.send(subject, body)
        if receipt is None:
            entry["send_attempts"] = entry.get("send_attempts", 0) + 1
            entry["last_send_error"] = error
            self.log(f"send failed for {subject}: {error} (attempt {entry['send_attempts']})")
            return False
        on_success(receipt)
        self.sent += 1
        self.log(f"sent {subject} event={receipt.get('buzz_event_id') or 'n/a'}")
        return True

    def send_opens(self, state: dict[str, Any]) -> None:
        pending = [e for e in state_io.open_entries(state)
                   if e["class"] in wi.IMMEDIATE_CLASSES and e.get("notified_at") is None
                   and e.get("send_attempts", 0) < self.args.max_attempts]
        for entry in pending[: self.args.max_sends]:
            subject, body = render_immediate(entry, self.args.link_template)

            def mark(receipt: dict[str, Any], entry=entry) -> None:
                entry["notified_at"] = iso_utc(self.now)
                entry["notify_event_id"] = receipt.get("buzz_event_id") or None
                entry["notify_channel"] = receipt.get("channel") or None

            self.deliver(entry, subject, body, mark)
        if len(pending) > self.args.max_sends:
            self.log(f"{len(pending) - self.args.max_sends} open incidents deferred to the next sweep")

    def send_recoveries(self, state: dict[str, Any], healthy: dict[str, str | None]) -> None:
        for entry in state["incidents"].values():
            if entry.get("resolved_at") is None or entry.get("notified_at") is None or entry.get("recovery_notified_at"):
                continue
            subject, body = render_recovery(entry, healthy.get(entry.get("workflow_id") or ""))

            def mark(receipt: dict[str, Any], entry=entry) -> None:
                entry["recovery_notified_at"] = iso_utc(self.now)

            self.deliver(entry, subject, body, mark)

    def send_digest(self, state: dict[str, Any]) -> None:
        due = self.args.digest or state_io.digest_due(state, self.now.astimezone(), self.args.digest_at)
        if not due:
            return
        if not self.args.dry_run:
            state["last_digest_at"] = iso_utc(self.now)
        entries = state_io.open_entries(state)
        if not entries:
            self.log("digest due: 0 unresolved, nothing sent")
            return
        subject, body = render_digest(entries, self.args.link_template)

        def mark(receipt: dict[str, Any]) -> None:
            for entry in entries:
                entry["digested_at"] = iso_utc(self.now)

        self.deliver({}, subject, body, mark)

    def run(self) -> int:
        observed, sources_ok, healthy = self.observe()
        state, notice = state_io.load(self.state_path, self.now)
        if notice:
            self.log(notice)
        transitions = state_io.reconcile(state, observed, self.now, sources_ok)
        pruned = state_io.prune(state, self.now, self.args.retention_days)
        if not sources_ok:
            self.log("a source is degraded: closing nothing this sweep")
        for name in ("opened", "updated", "closed"):
            for key in transitions[name]:
                self.log(f"{name}: {key}")
        if pruned:
            self.log(f"pruned {len(pruned)} resolved: {', '.join(pruned)}")
        if not self.args.dry_run:
            state_io.save(state, self.state_path)
        channel = route_channel(self.args.routes_file, self.args.route)
        if channel:
            self.send_opens(state)
            self.send_recoveries(state, healthy)
            self.send_digest(state)
        else:
            self.log(f"route '{self.args.route}' has no channel UUID in {self.args.routes_file} — sending nothing, state kept")
        if not self.args.dry_run:
            state_io.save(state, self.state_path)
        self.log(f"sweep done: {len(state_io.open_entries(state))} open, {self.sent} sent")
        return 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    sweep = Sweep(args)
    try:
        return sweep.run()
    except OSError as exc:
        sweep.log(f"sweep cannot run: {type(exc).__name__}: {exc}")
        print(f"incident_notify: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
