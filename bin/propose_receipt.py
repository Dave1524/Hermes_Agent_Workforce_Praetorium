#!/usr/bin/env python3
"""An agent_propose.sh outcome -> the executor's argv -> one receipt (T5.2).

    propose_receipt.py <OUTCOME> [--rc N] [--reason TEXT] [--proposal RELPATH]

OUTCOME is the word agent_propose.sh logs to cost.log: SKIP, DEDUP, BLOCKED, FAIL, CRASHED,
VIOLATION, OPS, PROPOSAL or NOPROPOSAL. Each maps to exactly one executor evidence flag —
the outcome map in .claude/briefs/t5-2-executor-wiring.md — and the executor derives the
terminal outcome from there; nothing here defaults to success.

The unit is AGENT_RECEIPT_UNIT, else DELIVERY_JOB without `.service`. Neither set means a
hand run outside systemd: log `no unit known — no receipt` and exit 0, which is the right
answer rather than a failure. The run id is AGENT_RUN_ID, else INVOCATION_ID; the usage
envelope is AGENT_USAGE_JSON when the file exists. CONTRACT_EXEC overrides the executor
path for fixtures. The executor's stdout is echoed and its exit status returned; the caller
(write_receipt in agent_propose.sh) decides that neither changes the run's own exit code.
"""
from __future__ import annotations

import argparse
import glob
import os
import pathlib
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import content_run_evidence  # noqa: E402

BIN_DIR = pathlib.Path(__file__).resolve().parent
CONTENT_TASK = "augustus-content"
REASON_TAIL = 160


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("outcome", choices=["SKIP", "DEDUP", "BLOCKED", "FAIL", "CRASHED", "VIOLATION",
                                       "OPS", "PROPOSAL", "NOPROPOSAL"])
    p.add_argument("--rc", type=int, help="the runtime's exit status (FAIL, CRASHED)")
    p.add_argument("--reason", help="the gate that refused (BLOCKED)")
    p.add_argument("--proposal", metavar="RELPATH", help="the proposal, relative to the inbox worktree (PROPOSAL)")
    return p.parse_args(argv)


def unit_name(env: dict[str, str]) -> str | None:
    explicit = env.get("AGENT_RECEIPT_UNIT", "").strip()
    if explicit:
        return explicit
    job = env.get("DELIVERY_JOB", "").strip()
    return job.removesuffix(".service") or None


def last_attempt_line(env: dict[str, str]) -> str:
    """The attempt log's last non-empty line that is not a decline — the runtime's own
    last word on why it failed, for the receipt's reason."""
    path = env.get("AGENT_ATTEMPT_LOG")
    if not path:
        return ""
    try:
        lines = pathlib.Path(path).read_text(errors="replace").splitlines()
    except OSError:
        return ""
    for line in reversed(lines):
        text = line.strip()
        if text and not text.startswith("DECLINE:"):
            return text[:REASON_TAIL]
    return ""


def newest_report(env: dict[str, str]) -> str | None:
    """REPORT_DIR/REPORT_GLOB's newest match written since the run started, as a file URI."""
    report_dir, pattern = env.get("REPORT_DIR"), env.get("REPORT_GLOB")
    if not report_dir or not pattern:
        return None
    started = int(env.get("AGENT_RUN_STARTED_AT") or 0)
    fresh = [p for p in glob.glob(os.path.join(report_dir, pattern))
             if os.path.isfile(p) and os.path.getmtime(p) > started]
    if not fresh:
        return None
    return "file://" + max(fresh, key=os.path.getmtime)


def content_evidence(env: dict[str, str]) -> list[str]:
    found = content_run_evidence.read(pathlib.Path(env.get("AGENT_ATTEMPT_LOG", "")))
    flags: list[str] = []
    if found["state_change"]:
        flags += ["--state-change", found["state_change"]]
    elif found["decline_reason"]:
        flags += ["--decline", found["decline_reason"]]
    if found["handoff_event"]:
        flags += ["--handoff-actor", "praetorium", "--handoff-recipient", "augustus",
                  "--handoff-event", found["handoff_event"]]
    return flags


def proposal_artifact(args: argparse.Namespace, env: dict[str, str]) -> str:
    worktree = env.get("INBOX_WORKTREE") or os.path.join(env.get("HOME", ""), "agent-worktrees", "inbox")
    relative = args.proposal or f"_inbox/agents/{env.get('RUN_DATE', '')}_{env.get('AGENT_TASK_SLUG', '')}.md"
    return "file://" + os.path.join(worktree, relative)


def evidence_flags(args: argparse.Namespace, env: dict[str, str]) -> list[str]:
    outcome = args.outcome
    if outcome == "SKIP":
        return ["--skipped", "previous run still active (flock)"]
    if outcome == "DEDUP":
        return ["--skipped", "dedup: today's proposal already exists"]
    if outcome == "BLOCKED":
        return ["--failed", f"BLOCKED: {args.reason or 'a preflight gate refused'}"]
    if outcome in ("FAIL", "CRASHED"):
        return ["--failed", f"{outcome}: rc={args.rc if args.rc is not None else '?'} {last_attempt_line(env)}".rstrip()]
    if outcome == "VIOLATION":
        return ["--failed", "VIOLATION: wrote outside _inbox/agents"]
    if outcome == "OPS":
        if env.get("AGENT_TASK_SLUG") == CONTENT_TASK:
            return content_evidence(env)
        report = newest_report(env)
        return ["--artifact", report] if report else []
    if outcome == "PROPOSAL":
        return ["--artifact", proposal_artifact(args, env)]
    return []


def identity_flags(env: dict[str, str]) -> list[str]:
    flags: list[str] = []
    run_id = env.get("AGENT_RUN_ID") or env.get("INVOCATION_ID")
    if run_id:
        flags += ["--run-id", run_id]
    if env.get("AGENT_PARENT_RUN_ID"):
        flags += ["--parent-run-id", env["AGENT_PARENT_RUN_ID"]]
    usage = env.get("AGENT_USAGE_JSON")
    if usage and os.path.isfile(usage):
        flags += ["--usage-json", usage]
    return flags


def executor_argv(args: argparse.Namespace, env: dict[str, str], unit: str) -> list[str]:
    executor = env.get("CONTRACT_EXEC") or str(BIN_DIR / "contract_exec.py")
    return [executor, unit, "--vantage", "run", *evidence_flags(args, env), *identity_flags(env)]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    env = dict(os.environ)
    unit = unit_name(env)
    if unit is None:
        print("propose_receipt: no unit known — no receipt (AGENT_RECEIPT_UNIT and DELIVERY_JOB unset)")
        return 0
    try:
        return subprocess.run(executor_argv(args, env, unit), env=env).returncode
    except OSError as exc:
        print(f"propose_receipt: executor did not start: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
