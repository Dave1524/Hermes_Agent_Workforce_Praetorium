#!/usr/bin/env python3
"""One receipt per finished timer invocation, from systemd's own record (T5.2, criterion 6).

    receipt_sweep.py [--tsv FILE] [--receipt-root DIR] [--now ISO] [--executor PATH]
                     [--repo-root DIR] [--manifest-dir DIR]

Walks config/fleet-units.tsv rows `status=standing kind=timer` — itself excluded — and for
each asks systemd about the unit, in this order:

  timer inactive                        -> `paused: <unit>`, nothing written
  service has no InvocationID           -> `never ran: <unit>` (nothing since boot), nothing
  service still active                  -> `running: <unit>`, nothing — no finished run to decide
  <workflow_id>/<InvocationID>.json exists -> `already receipted: <unit>`, never overwritten
  else                                  -> the executor at --vantage sweep, run id = InvocationID,
                                           evidence = systemd's record: `Result=success` is a
                                           state change, anything else is `--failed Result=…`;
                                           the contract's sweep checks decide the rest

An executor refusal (exit 2 — no manifest row, a service-kind row, no contract) is logged and
skipped; an executor that returns without a receipt on disk is `errored`, and the sweep
exits 1 for it after finishing the walk, so OnFailure= alerts on broken receipt machinery
but never on a paused fleet. The sweep ends by receipting itself at vantage run with
`--state-change "swept N: M written, K paused, J refused, S skipped"`, the same line it
logged, which the contract's run check reads back.

Fixtures: SYSTEMCTL names the systemctl to run (default `systemctl`; `--user` is appended
for `scope=user` rows), CONTRACT_EXEC or --executor the executor, --now the clock. Logs to
~/agent-workforce/logs/receipt_sweep.log. Reads no secret and prints no environment.
"""
from __future__ import annotations

import argparse
import datetime as dt
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract_exec  # noqa: E402
import workflow_receipt  # noqa: E402

BIN_DIR = pathlib.Path(__file__).resolve().parent
SELF_UNIT = workflow_receipt.SWEEP_WORKFLOW_ID
SERVICE_PROPS = ("InvocationID", "ExecMainStartTimestamp", "ExecMainExitTimestamp", "Result",
                 "ExecMainStatus", "ActiveState")
UTC = dt.timezone.utc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--tsv", type=pathlib.Path, default=BIN_DIR.parent / "config" / "fleet-units.tsv")
    p.add_argument("--receipt-root", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("CONTROL_ROOM_RECEIPT_ROOT",
                                                       pathlib.Path.home() / "agent-workforce" / "var" / "workflow-receipts")))
    p.add_argument("--now", help="ISO-8601; the sweep's and the executor's clock, for fixtures")
    p.add_argument("--executor", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("CONTRACT_EXEC", BIN_DIR / "contract_exec.py")))
    p.add_argument("--repo-root", type=pathlib.Path, default=contract_exec.default_repo_root())
    p.add_argument("--manifest-dir", type=pathlib.Path)
    args = p.parse_args(argv)
    args.manifest_dir = args.manifest_dir or args.repo_root / "design" / "agents"
    return args


# --- the fleet list -----------------------------------------------------------------------
def standing_timers(tsv: pathlib.Path) -> list[tuple[str, str]]:
    """(unit, scope) for every `standing` `timer` row that is not this sweep."""
    rows = []
    for line in tsv.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        cells = line.split("\t")
        if len(cells) < 5:
            continue
        unit, scope, status, _owner, kind = (c.strip() for c in cells[:5])
        if status == "standing" and kind == "timer" and unit != SELF_UNIT:
            rows.append((unit, scope))
    return rows


# --- systemd's record -----------------------------------------------------------------------
def systemctl_argv(scope: str) -> list[str]:
    argv = os.environ.get("SYSTEMCTL", "systemctl").split()
    return argv + ["--user"] if scope == "user" else argv


def show(scope: str, name: str, props: tuple[str, ...]) -> dict[str, str]:
    cmd = systemctl_argv(scope) + ["show", name, "-p", ",".join(props), "--timestamp=unix"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return {}
    if done.returncode != 0:
        return {}
    pairs = (line.split("=", 1) for line in done.stdout.splitlines() if "=" in line)
    return {key.strip(): value.strip() for key, value in pairs}


def timer_is_active(scope: str, unit: str) -> bool:
    cmd = systemctl_argv(scope) + ["show", f"{unit}.timer", "-p", "ActiveState", "--value"]
    try:
        done = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return done.returncode == 0 and done.stdout.strip() == "active"


def epoch_of(stamp: str) -> int | None:
    """`@1789452600` (the --timestamp=unix form) -> 1789452600; anything else -> None."""
    if stamp.startswith("@") and stamp[1:].isdigit():
        return int(stamp[1:])
    return None


def evidence_flags(unit: str, record: dict[str, str]) -> list[str]:
    """systemd's verdict as executor evidence: a clean exit is a state change, the rest failed."""
    result = record.get("Result") or "unknown"
    status = record.get("ExecMainStatus") or "?"
    exited = epoch_of(record.get("ExecMainExitTimestamp", ""))
    when = workflow_receipt.iso_utc(dt.datetime.fromtimestamp(exited, UTC)) if exited else "unknown time"
    summary = f"systemd: {unit}.service {record['InvocationID']} Result={result} ExecMainStatus={status} exited {when}"
    if result == "success":
        return ["--state-change", summary]
    return ["--failed", f"Result={result} ExecMainStatus={status}", "--state-change", summary]


# --- the sweep ------------------------------------------------------------------------------
class Sweep:
    def __init__(self, args: argparse.Namespace) -> None:
        self.args = args
        self.now = contract_exec._clock(args.now)
        self.started = int(self.now.timestamp())
        self.log_path = pathlib.Path.home() / "agent-workforce" / "logs" / "receipt_sweep.log"
        self.counts = {"written": 0, "paused": 0, "refused": 0, "skipped": 0}
        self.errored: list[str] = []

    def stamp(self) -> str:
        """Seconds, the precision the contract's run check compares against AGENT_RUN_STARTED_AT."""
        now = self.now if self.args.now else dt.datetime.now(UTC)
        return now.strftime("%Y-%m-%dT%H:%M:%SZ")

    def log(self, message: str) -> None:
        line = f"{self.stamp()} {message}"
        print(line)
        try:
            self.log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.log_path.open("a") as fh:
                fh.write(line + "\n")
        except OSError as exc:
            print(f"receipt_sweep: cannot log to {self.log_path}: {exc}", file=sys.stderr)

    def executor(self, unit: str, *flags: str) -> subprocess.CompletedProcess | None:
        cmd = [str(self.args.executor), unit, "--repo-root", str(self.args.repo_root),
               "--manifest-dir", str(self.args.manifest_dir), "--receipt-root", str(self.args.receipt_root),
               *flags]
        if self.args.now:
            cmd += ["--now", self.args.now]
        try:
            return subprocess.run(cmd, capture_output=True, text=True, timeout=600)
        except (OSError, subprocess.TimeoutExpired) as exc:
            self.log(f"errored: {unit} — executor did not run: {exc}")
            return None

    def workflow_id(self, unit: str) -> str | None:
        try:
            row, _agent = contract_exec.manifest_row(self.args.manifest_dir, unit)
        except contract_exec.Refusal as exc:
            self.log(f"refused: {unit} — {exc}")
            return None
        return str(row.get("logical_workflow") or unit)

    def receipt_exists(self, workflow_id: str, run_id: str) -> bool:
        try:
            return workflow_receipt.receipt_path(self.args.receipt_root, {"workflow_id": workflow_id,
                                                                          "run_id": run_id}).exists()
        except ValueError:
            return False

    def sweep_unit(self, unit: str, scope: str) -> str:
        """One bucket name per unit: written | paused | refused | skipped."""
        if not timer_is_active(scope, unit):
            self.log(f"paused: {unit} — timer inactive")
            return "paused"
        record = show(scope, f"{unit}.service", SERVICE_PROPS)
        run_id = record.get("InvocationID", "")
        if not run_id:
            self.log(f"never ran: {unit} — no InvocationID since boot")
            return "skipped"
        if record.get("ActiveState") in ("active", "activating", "deactivating", "reloading"):
            self.log(f"running: {unit} — {run_id} has not finished")
            return "skipped"
        workflow_id = self.workflow_id(unit)
        if workflow_id is None:
            return "refused"
        if self.receipt_exists(workflow_id, run_id):
            self.log(f"already receipted: {unit} — {workflow_id}/{run_id}.json")
            return "skipped"
        return self.write(unit, workflow_id, run_id, record)

    def write(self, unit: str, workflow_id: str, run_id: str, record: dict[str, str]) -> str:
        flags = ["--vantage", "sweep", "--run-id", run_id, *evidence_flags(unit, record)]
        started = epoch_of(record.get("ExecMainStartTimestamp", ""))
        if started is not None:
            flags += ["--run-started-at", str(started)]
        done = self.executor(unit, *flags)
        if done is None:
            self.errored.append(unit)
            return "skipped"
        if done.returncode == 2:
            self.log(f"refused: {unit} — {done.stderr.strip().splitlines()[-1] if done.stderr.strip() else 'exit 2'}")
            return "refused"
        if not self.receipt_exists(workflow_id, run_id):
            self.log(f"errored: {unit} — executor exit {done.returncode} left no receipt at "
                     f"{workflow_id}/{run_id}.json: {(done.stderr or done.stdout).strip()[-200:]}")
            self.errored.append(unit)
            return "skipped"
        outcome = "failed" if done.returncode == 1 else "decided"
        self.log(f"written: {unit} — {workflow_id}/{run_id}.json ({outcome})")
        return "written"

    def summary(self, total: int) -> str:
        c = self.counts
        return f"swept {total}: {c['written']} written, {c['paused']} paused, {c['refused']} refused, {c['skipped']} skipped"

    def receipt_self(self, summary: str) -> bool:
        flags = ["--vantage", "run", "--state-change", summary, "--run-started-at", str(self.started)]
        if self.errored:
            flags += ["--failed", "executor errored for: " + ", ".join(self.errored)]
        done = self.executor(SELF_UNIT, *flags)
        if done is None:
            return False
        if done.returncode not in (0, 1):
            self.log(f"errored: {SELF_UNIT} — own receipt not written (exit {done.returncode}): "
                     f"{(done.stderr or done.stdout).strip()[-200:]}")
            return False
        return True

    def run(self) -> int:
        try:
            units = standing_timers(self.args.tsv)
        except OSError as exc:
            self.log(f"errored: cannot read {self.args.tsv}: {exc}")
            return 1
        for unit, scope in units:
            self.counts[self.sweep_unit(unit, scope)] += 1
        summary = self.summary(len(units))
        self.log(summary)
        own = self.receipt_self(summary)
        return 0 if own and not self.errored else 1


def main(argv: list[str] | None = None) -> int:
    return Sweep(parse_args(argv)).run()


if __name__ == "__main__":
    sys.exit(main())
