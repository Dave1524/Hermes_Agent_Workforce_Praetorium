#!/usr/bin/env python3
"""Contract executor (T5.1): run every check of a unit's contract for one run, write one receipt.

    contract_exec.py <unit> --vantage run|sweep [--artifact URI] [--state-change EVIDENCE]
                     [--usage-json FILE] [--skipped REASON] [--parent-run-id ID]
                     [--handoff-actor A --handoff-recipient R --handoff-event E]

Every ```check block under the contract's ## Acceptance checks runs as bash under `set -u`
(never -e, never pipefail), in exactly the environment design/contract-schema.md declares
and nothing else from this process. Exit 0 is `passed`, 77 `not_applicable`, anything else
`failed`; a block whose `when=` is not this vantage is recorded `not_applicable` by vantage,
never omitted. The receipt lists every check the contract declares.

Exactly one terminal outcome is derived, never defaulted: any failed check -> `failed`; else
a fresh `^DECLINE:` line in the attempt log -> `decline`; else an artifact URI or state-change
evidence -> `artifact`; else `failed` ("neither artifact nor decline"). `skipped` only when
the caller says so. The receipt cannot be written without one (bin/workflow_receipt.py).

Exit 0 when the outcome is artifact, decline or skipped; 1 when it is failed; 2 when the unit
cannot be decided at all — no manifest row, kind = "service", contract_exempt, an unreadable
contract, a schema variable this executor cannot derive — in which case no receipt exists.

Overrides (--manifest-dir, --schema-doc, --receipt-root, --attempt-log, --inbox-worktree,
--vault, --home, --now, --run-started-at, --run-date) exist so fixtures never touch live paths.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract_checks  # noqa: E402
import workflow_receipt  # noqa: E402

CHECK_TIMEOUT_SECONDS = 300
NOT_APPLICABLE = 77
DECLINE = re.compile(r"^DECLINE:", re.MULTILINE)
UTC = dt.timezone.utc


class Refusal(Exception):
    """The unit cannot be decided; printed to stderr, exit 2, no receipt."""


# --- arguments ----------------------------------------------------------------------------
def default_repo_root() -> pathlib.Path:
    """The source checkout. bin/deploy copies this script to ~/agent-workforce, where design/
    deliberately does not exist, so the deployed copy reads the adjacent source checkout —
    the same rule bin/control_room_api.py applies."""
    script_root = pathlib.Path(__file__).resolve().parents[1]
    if (script_root / "design" / "agents").is_dir():
        return script_root
    return pathlib.Path.home() / "dev" / "agent-workforce"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("unit", help="unit name with no suffix, as the manifest names it")
    p.add_argument("--vantage", required=True, help="run | sweep (design/contract-schema.md)")
    p.add_argument("--artifact", metavar="URI", help="the artifact this run produced")
    p.add_argument("--state-change", metavar="EVIDENCE", help="state-change evidence instead of an artifact")
    p.add_argument("--usage-json", metavar="FILE", help="a `claude -p --output-format json` envelope")
    p.add_argument("--skipped", metavar="REASON", help="the run never happened; record why, run nothing")
    p.add_argument("--parent-run-id")
    p.add_argument("--handoff-actor")
    p.add_argument("--handoff-recipient")
    p.add_argument("--handoff-event")
    p.add_argument("--repo-root", type=pathlib.Path, default=default_repo_root())
    p.add_argument("--manifest-dir", type=pathlib.Path)
    p.add_argument("--schema-doc", type=pathlib.Path)
    p.add_argument("--receipt-root", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("CONTROL_ROOM_RECEIPT_ROOT",
                                                       pathlib.Path.home() / "agent-workforce" / "var" / "workflow-receipts")))
    p.add_argument("--attempt-log", type=pathlib.Path)
    p.add_argument("--inbox-worktree", type=pathlib.Path)
    p.add_argument("--vault", type=pathlib.Path)
    p.add_argument("--home", type=pathlib.Path)
    p.add_argument("--now", help="ISO-8601; the executor's clock, for fixtures")
    p.add_argument("--run-started-at", type=int, metavar="EPOCH")
    p.add_argument("--run-date", metavar="YYYY-MM-DD")
    args = p.parse_args(argv)
    args.manifest_dir = args.manifest_dir or args.repo_root / "design" / "agents"
    args.schema_doc = args.schema_doc or args.repo_root / contract_checks.SCHEMA_DOC
    return args


# --- the manifest row -----------------------------------------------------------------------
def manifest_row(manifest_dir: pathlib.Path, unit: str) -> tuple[dict[str, Any], str]:
    """The [[workflows]] entry naming `unit`, and the agent (the manifest's file stem)."""
    for path in sorted(manifest_dir.glob("*.toml")):
        try:
            data = tomllib.loads(path.read_text())
        except (OSError, tomllib.TOMLDecodeError) as exc:
            raise Refusal(f"{path.name}: does not parse: {exc}") from exc
        for row in data.get("workflows", []):
            if isinstance(row, dict) and row.get("unit") == unit:
                return row, path.stem
    raise Refusal(f"{unit}: no [[workflows]] entry names this unit under {manifest_dir}")


def contract_of(row: dict[str, Any], unit: str, repo_root: pathlib.Path) -> pathlib.Path:
    """The contract path, or the refusal the schema itself declares for this row."""
    if row.get("kind") == "service":
        raise Refusal(f"{unit}: kind = \"service\" — an always-on unit has no run to decide a check "
                      "from (design/contract-schema.md, #### Vantage)")
    if row.get("contract_exempt"):
        raise Refusal(f"{unit}: contract_exempt = {row['contract_exempt']!r} — nothing is promised, "
                      "so there is nothing to execute")
    relative = row.get("contract")
    if not isinstance(relative, str) or not relative.strip():
        raise Refusal(f"{unit}: the manifest row names no contract")
    path = pathlib.Path(relative)
    if not path.is_absolute():
        path = repo_root / path
    if not path.is_file():
        raise Refusal(f"{unit}: contract missing: {path}")
    return path


# --- the run's facts ------------------------------------------------------------------------
class Run:
    """Everything the checks and the receipt need to know about this run, resolved once."""

    def __init__(self, args: argparse.Namespace, row: dict[str, Any], agent: str) -> None:
        env = os.environ
        self.unit = args.unit
        self.vantage = args.vantage
        self.agent = agent
        self.row = row
        self.scope = str(row.get("scope") or "system")
        self.now = _clock(args.now)
        self.started = int(args.run_started_at if args.run_started_at is not None
                           else env.get("AGENT_RUN_STARTED_AT") or int(self.now.timestamp()))
        self.run_date = args.run_date or env.get("RUN_DATE") or self.now.astimezone().strftime("%Y-%m-%d")
        self.home = pathlib.Path(args.home or env.get("HOME") or pathlib.Path.home())
        self.inbox_worktree = pathlib.Path(args.inbox_worktree or env.get("INBOX_WORKTREE")
                                           or self.home / "agent-worktrees" / "inbox")
        self.attempt_log = pathlib.Path(args.attempt_log or env.get("AGENT_ATTEMPT_LOG")
                                        or self.home / "agent-workforce" / "logs" / "last-attempt" / f"{self.unit}.log")
        self.vault = pathlib.Path(os.path.realpath(args.vault or env.get("VAULT") or self.home / "vault"))
        self.invocation_id = env.get("INVOCATION_ID")

    def systemctl(self) -> str:
        return "systemctl --user" if self.scope == "user" else "systemctl"

    def journalctl(self) -> str:
        return "journalctl --user" if self.scope == "user" else "journalctl"

    def derivations(self) -> dict[str, str]:
        """Every variable this executor knows how to derive. The schema's list selects."""
        return {
            "UNIT": self.unit,
            "SYSTEMCTL": self.systemctl(),
            "JOURNALCTL": self.journalctl(),
            "RUN_DATE": self.run_date,
            "AGENT_RUN_STARTED_AT": str(self.started),
            "AGENT_ATTEMPT_LOG": str(self.attempt_log),
            "AGENT_INBOX_DIR": str(self.inbox_worktree / "_inbox" / "agents"),
            "INBOX_WORKTREE": str(self.inbox_worktree),
            "VAULT": str(self.vault),
            "HOME": str(self.home),
        }


def _clock(value: str | None) -> dt.datetime:
    if not value:
        return workflow_receipt.utc_now()
    parsed = workflow_receipt.parse_time(value)
    if parsed is None:
        raise Refusal(f"--now is not ISO-8601: {value!r}")
    return parsed


def child_environment(run: Run, names: list[str]) -> dict[str, str]:
    """Exactly the schema's variables plus PATH — nothing else from this process leaks.

    PATH is not in the schema's list but must reach the child or `grep` and `find` in a
    block cannot run; the "nothing else" rule is about the parent's variables.
    """
    known = run.derivations()
    missing = [n for n in names if n not in known]
    if missing:
        raise Refusal(f"the schema declares {', '.join(missing)} and this executor cannot derive "
                      "it — teach bin/contract_exec.py the variable before running checks against it")
    env = {name: known[name] for name in names}
    env["PATH"] = os.environ.get("PATH", os.defpath)
    return env


# --- running the checks ---------------------------------------------------------------------
def declared_checks(text: str) -> list[dict[str, Any]]:
    """One entry per check block, in contract order, with a unique id even when none was declared."""
    _, blocks = contract_checks.acceptance_checks(text)
    seen: dict[str, int] = {}
    out = []
    for block in blocks:
        attrs, _ = contract_checks.attrs_of(block["info"])
        ident = attrs.get("id") or f"check-{block['item'] or block['line']}"
        if ident in seen:
            seen[ident] += 1
            ident = f"{ident}-{seen[ident]}"
        else:
            seen[ident] = 1
        out.append({"id": ident, "when": attrs.get("when") or contract_checks.DEFAULT_VANTAGE,
                    "body": block["body"]})
    return out


def run_check(check: dict[str, Any], env: dict[str, str], vantage: str, cwd: pathlib.Path) -> dict[str, Any]:
    result = {"id": check["id"], "when": check["when"]}
    if check["when"] != vantage:
        return {**result, "status": "not_applicable", "reason": "vantage", "output": ""}
    script = contract_checks.block_script(check["body"])
    try:
        done = subprocess.run(["bash", "-c", script], env=env, cwd=str(cwd), capture_output=True,
                              text=True, timeout=CHECK_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired as exc:
        output = (exc.stdout or b"").decode(errors="replace") + (exc.stderr or b"").decode(errors="replace")
        return {**result, "status": "failed", "reason": f"timed out after {CHECK_TIMEOUT_SECONDS}s",
                "output": output.strip()}
    output = (done.stdout + done.stderr).strip()
    if done.returncode == 0:
        return {**result, "status": "passed", "output": output}
    if done.returncode == NOT_APPLICABLE:
        return {**result, "status": "not_applicable", "reason": output.splitlines()[0] if output else "exit 77",
                "output": output}
    return {**result, "status": "failed", "reason": f"exit {done.returncode}", "output": output}


# --- the terminal outcome ---------------------------------------------------------------------
def fresh_decline(run: Run) -> str | None:
    """The `^DECLINE:` line in this run's own attempt log, if the log is newer than the run
    started — bin/proposal_or_decline.sh's definition, re-implemented rather than shelled to."""
    try:
        if run.attempt_log.stat().st_mtime <= run.started:
            return None
        match = DECLINE.search(run.attempt_log.read_text(errors="replace"))
    except OSError:
        return None
    if not match:
        return None
    return run.attempt_log.read_text(errors="replace")[match.start():].splitlines()[0].strip()


def terminal_outcome(assertions: list[dict[str, Any]], decline: str | None, has_evidence: bool,
                     skipped: str | None) -> dict[str, Any]:
    if skipped is not None:
        return {"outcome": "skipped", "reason": skipped}
    reasons = []
    if not decline and not has_evidence:
        reasons.append("neither artifact nor decline")
    failed = [a["id"] for a in assertions if a["status"] == "failed"]
    if failed:
        reasons.append("failed checks: " + ", ".join(failed))
    if reasons:
        return {"outcome": "failed", "reason": "; ".join(reasons)}
    if decline:
        return {"outcome": "decline", "reason": decline}
    return {"outcome": "artifact", "reason": None}


# --- identity, usage, next action ---------------------------------------------------------------
def run_identity(run: Run, env: dict[str, str]) -> str:
    """systemd's invocation id where there is one; the unit plus the run's start otherwise.

    At vantage `sweep` the executor is not inside the run, so it asks systemd for the
    service's current InvocationID; an inactive service answers empty, and the fallback then
    names the sweep rather than borrowing a run id that is not this one's.
    """
    if run.vantage == "sweep":
        cmd = run.systemctl().split() + ["show", f"{run.unit}.service", "-p", "InvocationID", "--value"]
        try:
            done = subprocess.run(cmd, env=env, capture_output=True, text=True, timeout=30)
            value = done.stdout.strip() if done.returncode == 0 else ""
        except (OSError, subprocess.TimeoutExpired):
            value = ""
        return value or f"{run.unit}-sweep-{run.started}"
    return run.invocation_id or f"{run.unit}-{run.started}"


def usage_and_cost(path: pathlib.Path | None) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """Measured only from a parsable envelope; a missing, empty or unparsable file is
    `unavailable`, never zero."""
    if path is None:
        return workflow_receipt.unavailable_usage(), workflow_receipt.unavailable_cost(), None
    try:
        envelope = json.loads(path.read_text())
    except (OSError, ValueError):
        return workflow_receipt.unavailable_usage(), workflow_receipt.unavailable_cost(), None
    return workflow_receipt.usage_from_claude_code(envelope)


def next_action(contract_text: str) -> dict[str, str | None]:
    bullets = contract_checks.outputs_bullets(contract_text)
    actor, action = bullets.get("next actor"), bullets.get("next action")
    return {"actor": None if contract_checks.says_none(actor) else actor,
            "action": None if contract_checks.says_none(action) else action}


def handoff_of(args: argparse.Namespace) -> dict[str, str] | None:
    fields = {"actor": args.handoff_actor, "recipient": args.handoff_recipient, "event": args.handoff_event}
    return fields if any(fields.values()) else None


# --- the receipt ----------------------------------------------------------------------------------
def build_receipt(run: Run, run_id: str, assertions: list[dict[str, Any]], terminal: dict[str, Any],
                  args: argparse.Namespace, contract_text: str) -> dict[str, Any]:
    usage, cost, measured_model = usage_and_cost(pathlib.Path(args.usage_json) if args.usage_json else None)
    ended = max(run.now, dt.datetime.fromtimestamp(run.started, UTC))
    receipt: dict[str, Any] = {
        "schema_version": workflow_receipt.SCHEMA_VERSION,
        "workflow_id": str(run.row.get("logical_workflow") or run.unit),
        "run_id": run_id,
        "unit": run.unit,
        "agent": run.agent,
        "model": measured_model or run.row.get("model"),
        "vantage": run.vantage,
        "started_at": workflow_receipt.iso_utc(dt.datetime.fromtimestamp(run.started, UTC)),
        "ended_at": workflow_receipt.iso_utc(ended),
        "terminal": terminal,
        "assertions": assertions,
        "usage": usage,
        "cost": cost,
        "next_action": next_action(contract_text),
        "parent_run_id": args.parent_run_id,
        "handoff": handoff_of(args),
    }
    if args.artifact:
        receipt["artifact"] = {"uri": args.artifact}
    if args.state_change:
        receipt["state_change"] = {"evidence": args.state_change}
    return receipt


def print_table(receipt: dict[str, Any], path: pathlib.Path) -> None:
    print(f"contract_exec: {receipt['unit']} vantage={receipt['vantage']} run_id={receipt['run_id']} "
          f"agent={receipt['agent']}")
    for a in receipt["assertions"]:
        note = a.get("reason") or (a["output"].splitlines() or [""])[0]
        print(f"  {a['status']:<15} {a['id']:<32} {note[:100]}")
    reason = receipt["terminal"].get("reason")
    print(f"terminal: {receipt['terminal']['outcome']}" + (f" — {reason}" if reason else ""))
    print(f"receipt: {path}")


def execute(args: argparse.Namespace) -> int:
    row, agent = manifest_row(args.manifest_dir, args.unit)
    contract = contract_of(row, args.unit, args.repo_root)
    run = Run(args, row, agent)
    if run.vantage not in contract_checks.vantages(args.schema_doc):
        raise Refusal(f"--vantage {run.vantage}: not one the schema declares")
    contract_text = contract.read_text()
    env = child_environment(run, contract_checks.executor_environment(args.schema_doc))
    if args.skipped is not None:
        assertions: list[dict[str, Any]] = []
    else:
        assertions = [run_check(check, env, run.vantage, run.home if run.home.is_dir() else pathlib.Path.cwd())
                      for check in declared_checks(contract_text)]
    terminal = terminal_outcome(assertions, fresh_decline(run), bool(args.artifact or args.state_change),
                                args.skipped)
    receipt = build_receipt(run, run_identity(run, env), assertions, terminal, args, contract_text)
    path = workflow_receipt.write(receipt, args.receipt_root)
    print_table(receipt, path)
    return 1 if terminal["outcome"] == "failed" else 0


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        return execute(args)
    except Refusal as exc:
        print(f"contract_exec: refused: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
