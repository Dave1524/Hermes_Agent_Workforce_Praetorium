#!/usr/bin/env python3
"""The finish step: a platform timer's run receipt the moment the run ends, when its outcome moved.

    receipt_finish.py [--user] [--receipt-root DIR] [--repo-root DIR] [--manifest-dir DIR]
                      [--executor PATH] [--timeout SECS] <unit>

Each platform timer unit runs it as its LAST `ExecStopPost=-…/receipt_finish.py %N`. systemd
hands stop-post commands the run's INVOCATION_ID, SERVICE_RESULT, EXIT_CODE and EXIT_STATUS; the
start and exit times come from `systemctl show`, already final for the main process. The receipt
is written at vantage `run`, with the evidence bin/receipt_sweep.py would have written
(bin/systemd_evidence.py), only when systemd's verdict on this run differs from its verdict on
the run behind the workflow's newest judged receipt — the run that would move its incident. The
comparison is systemd's verdict and never the receipt's outcome: a run that exited 0 but failed a
`sweep` check (no alert followed) is the sweep's to clear, or every clean run would resolve the
incident and every 05:50 reopen it. An unchanged verdict is left to workflow-receipt-sweep, which
still writes each unit's daily receipt and amends this one's `sweep` checks while it is the unit's
latest invocation. Every run would be ~400 receipts a day
for the Control Room to re-read on each request; the flips are what it needs to see at once.

Prints exactly one line, which lands in the unit's journal — `receipt: written|unchanged|errored
…` — and exits 0 whatever happened: a receipt must never change the job's result. The `-` prefix
on the unit line is the second guard. Stop-post time counts against the unit's TimeoutStopSec
(90 s): `systemctl show` is bounded at 30 s and the executor at --timeout, 20 s by default.
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
from typing import Any, Iterator, Mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import contract_exec  # noqa: E402
import workflow_receipt  # noqa: E402
from receipt_sweep import show  # noqa: E402
from systemd_evidence import epoch_of, evidence_flags, exit_status_number  # noqa: E402

BIN_DIR = pathlib.Path(__file__).resolve().parent
TIMES = ("ExecMainStartTimestamp", "ExecMainExitTimestamp")
SHOWN = (*TIMES, "ExecMainStatus")
RESULT = re.compile(r"\bResult=(\S+)")
EARLIEST = dt.datetime.min.replace(tzinfo=dt.timezone.utc)


class Errored(Exception):
    """Why no receipt was written: the rest of the one line the step prints."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("unit", help="unit name with no suffix, as systemd's %%N gives it")
    p.add_argument("--user", action="store_true", help="the unit runs under the user manager")
    p.add_argument("--receipt-root", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("CONTROL_ROOM_RECEIPT_ROOT",
                                                       pathlib.Path.home() / "agent-workforce" / "var" / "workflow-receipts")))
    p.add_argument("--repo-root", type=pathlib.Path, default=contract_exec.default_repo_root())
    p.add_argument("--manifest-dir", type=pathlib.Path)
    p.add_argument("--executor", type=pathlib.Path,
                   default=pathlib.Path(os.environ.get("CONTRACT_EXEC", BIN_DIR / "contract_exec.py")))
    p.add_argument("--timeout", type=int, default=20, help="seconds the executor may take")
    args = p.parse_args(argv)
    args.manifest_dir = args.manifest_dir or args.repo_root / "design" / "agents"
    return args


def run_record(args: argparse.Namespace, env: Mapping[str, str]) -> dict[str, str]:
    """systemd's record of the run that just ended, in the shape `systemctl show` answers."""
    if not env.get("INVOCATION_ID"):
        raise Errored("no INVOCATION_ID: not run by systemd as ExecStopPost")
    shown = show("user" if args.user else "system", f"{args.unit}.service", SHOWN)
    status = env.get("EXIT_STATUS")
    if status:
        status = exit_status_number(env.get("EXIT_CODE", ""), status)
    return {"InvocationID": env["INVOCATION_ID"], "Result": env.get("SERVICE_RESULT") or "unknown",
            "ExecMainStatus": status or shown.get("ExecMainStatus", ""), **{key: shown.get(key, "") for key in TIMES}}


def workflow_id(args: argparse.Namespace) -> str:
    try:
        row, _agent = contract_exec.manifest_row(args.manifest_dir, args.unit)
    except contract_exec.Refusal as exc:
        raise Errored(f"no manifest row: {exc}") from exc
    return str(row.get("logical_workflow") or args.unit)


def judged_receipts(root: pathlib.Path, workflow: str) -> Iterator[dict[str, Any]]:
    for path in (root / workflow).glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and not workflow_receipt.validate(data) and workflow_receipt.judged(data):
            yield data


def verdict(result: str) -> str:
    return "artifact" if result == "success" else "failed"


def systemd_verdict(receipt: dict[str, Any]) -> str | None:
    """systemd's verdict on the receipted run, from its evidence; the outcome where none is recorded."""
    found = RESULT.search((receipt.get("state_change") or {}).get("evidence") or "")
    return verdict(found.group(1)) if found else (receipt.get("terminal") or {}).get("outcome")


def newest_judged_verdict(root: pathlib.Path, workflow: str) -> str | None:
    """systemd's verdict on the run the incident derivation reads: the newest receipt no reader skips."""
    newest = max(judged_receipts(root, workflow), default=None,
                 key=lambda r: workflow_receipt.parse_time(r.get("ended_at")) or EARLIEST)
    return None if newest is None else systemd_verdict(newest)


def executor_argv(args: argparse.Namespace, record: dict[str, str]) -> list[str]:
    flags = ["--vantage", "run", "--run-id", record["InvocationID"], *evidence_flags(args.unit, record)]
    started = epoch_of(record["ExecMainStartTimestamp"])
    if started is not None:
        flags += ["--run-started-at", str(started)]
    return [str(args.executor), args.unit, "--repo-root", str(args.repo_root), "--manifest-dir",
            str(args.manifest_dir), "--receipt-root", str(args.receipt_root), *flags]


def write(args: argparse.Namespace, record: dict[str, str], workflow: str) -> None:
    try:
        done = subprocess.run(executor_argv(args, record), capture_output=True, text=True, timeout=args.timeout)
    except subprocess.TimeoutExpired as exc:
        raise Errored(f"executor timed out after {args.timeout}s") from exc
    except OSError as exc:
        raise Errored(f"executor did not run: {exc}") from exc
    if done.returncode not in (0, 1):
        raise Errored(f"executor exit {done.returncode}: {(done.stderr or done.stdout).strip()[-200:]}")
    if not workflow_receipt.receipt_path(args.receipt_root, {"workflow_id": workflow,
                                                             "run_id": record["InvocationID"]}).exists():
        raise Errored(f"executor exit {done.returncode} left no receipt")


def finish(args: argparse.Namespace, env: Mapping[str, str]) -> str:
    record = run_record(args, env)
    workflow = workflow_id(args)
    now = verdict(record["Result"])
    before = newest_judged_verdict(args.receipt_root, workflow)
    if before == now:
        return f"receipt: unchanged ({now}), left to the sweep"
    write(args, record, workflow)
    return f"receipt: written {workflow}/{record['InvocationID']}.json ({before or 'none'} -> {now})"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        print(finish(args, os.environ))
    except Errored as exc:
        print(f"receipt: errored {exc}")
    except Exception as exc:  # noqa: BLE001 — the job's result is not this step's to change
        print(f"receipt: errored {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
