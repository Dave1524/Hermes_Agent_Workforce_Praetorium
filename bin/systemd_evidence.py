"""systemd's verdict on one finished run, as contract-executor evidence.

Two producers record the same run from two sources: bin/receipt_sweep.py reads `systemctl show`
after the fact, and bin/receipt_finish.py reads the environment systemd hands ExecStopPost. One
builder keeps their receipts one string. A clean exit is a state change; anything else is
`--failed Result=… ExecMainStatus=…`.
"""
from __future__ import annotations

import datetime as dt
import os
import signal
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_receipt  # noqa: E402

UTC = dt.timezone.utc
SIGNAL_EXITS = ("killed", "dumped")


def epoch_of(stamp: str) -> int | None:
    """`@1789452600` (the --timestamp=unix form) -> 1789452600; anything else -> None."""
    if stamp.startswith("@") and stamp[1:].isdigit():
        return int(stamp[1:])
    return None


def exit_status_number(code: str, status: str) -> str:
    """ExecStopPost's EXIT_STATUS names the signal (`TERM`) where ExecMainStatus has its number."""
    if code not in SIGNAL_EXITS or status.isdigit():
        return status
    try:
        return str(signal.Signals[f"SIG{status}"].value)
    except KeyError:
        return status


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
