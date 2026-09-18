#!/usr/bin/env python3
"""Augustus's own receipt for one content dispatch, joined on the trigger's relay event id.

    content_turn_receipt.py <receipts-dir> <run-id>
        -> "<outcome>\\t<receipt run id>\\t<ended_at>\\t<error or empty>"   exit 0
        -> nothing                                                          exit 3 (no receipt yet)

`bin/interaction_receipt.py` writes one receipt per `buzz-agent@augustus` turn whose
`handoff.event` is the relay event that woke him — the same id `run_content_via_buzz.sh`
records as `run_id=`. Its presence means his turn for this dispatch has ended; its terminal
outcome says how. `failed` with a reason is a turn the harness ended in an error, which is
the one outcome the channel and the board cannot show: nothing was posted and nothing moved,
and until 2026-09-18 the dispatcher spent its full wait on it and recorded "no reply".
The tab-separated line is for the shell caller; the error is flattened to one line.
"""
from __future__ import annotations

import json
import pathlib
import sys

NO_RECEIPT = 3


def turn_receipt(receipts_dir: pathlib.Path, run_id: str) -> dict | None:
    for path in sorted(receipts_dir.glob("*.json")):
        try:
            receipt = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        handoff = receipt.get("handoff") if isinstance(receipt, dict) else None
        if isinstance(handoff, dict) and handoff.get("event") == run_id:
            return receipt
    return None


def summary_line(receipt: dict) -> str:
    terminal = receipt.get("terminal") if isinstance(receipt.get("terminal"), dict) else {}
    outcome = str(terminal.get("outcome") or "")
    reason = terminal.get("reason") if outcome == "failed" else None
    error = " ".join(str(reason).split()) if reason else ""
    return "\t".join([outcome, str(receipt.get("run_id") or ""), str(receipt.get("ended_at") or ""), error])


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[0], file=sys.stderr)
        return 2
    receipt = turn_receipt(pathlib.Path(argv[0]), argv[1])
    if receipt is None:
        return NO_RECEIPT
    print(summary_line(receipt))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
