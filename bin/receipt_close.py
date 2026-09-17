#!/usr/bin/env python3
"""Close a reviewed failure: record who, when and why on the run's receipt (T7.5).

    receipt_close.py <workflow_id> <run_id> --by WHO --reason TEXT [--root DIR]

A failed receipt keeps ringing — exception row, incident, Buzz alert — until a later run
replaces it, even when the failure was a check defect fixed the same morning. A closure is
the operator's verdict on that one run: the recorded outcome stays as written, and every
reader stops judging the run (workflow_receipt.judged), so the next real run is the next
thing anyone sees. Refused when nothing in the receipt failed, when it is already closed,
or when the review names no author or reason. The default root is the deployed runtime's
receipts, the same tree the Control Room reads; CONTROL_ROOM_RECEIPT_ROOT overrides it.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_receipt  # noqa: E402

DEFAULT_ROOT = pathlib.Path(os.environ.get(
    "CONTROL_ROOM_RECEIPT_ROOT", pathlib.Path.home() / "agent-workforce" / "var" / "workflow-receipts"))


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("workflow_id")
    p.add_argument("run_id")
    p.add_argument("--by", required=True, help="who reviewed the failure")
    p.add_argument("--reason", required=True, help="why it is closed: the defect and its fix")
    p.add_argument("--root", type=pathlib.Path, default=DEFAULT_ROOT, help="receipts root")
    return p.parse_args(argv)


def close_receipt(root: pathlib.Path, workflow_id: str, run_id: str, by: str, reason: str) -> pathlib.Path:
    path = workflow_receipt.receipt_path(root, {"workflow_id": workflow_id, "run_id": run_id})
    if not path.is_file():
        raise FileNotFoundError(f"no receipt at {path}")
    receipt = json.loads(path.read_text())
    errors = workflow_receipt.validate(receipt)
    if errors:
        raise ValueError(f"{path} does not validate: " + "; ".join(errors))
    return workflow_receipt.write(workflow_receipt.close(receipt, by, reason), root)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        path = close_receipt(args.root, args.workflow_id, args.run_id, args.by, args.reason)
    except (FileNotFoundError, ValueError, OSError, json.JSONDecodeError) as exc:
        print(f"receipt_close: {exc}", file=sys.stderr)
        return 2
    print(f"closed {args.workflow_id}/{args.run_id}: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
