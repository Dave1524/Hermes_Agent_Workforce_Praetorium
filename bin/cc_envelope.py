#!/usr/bin/env python3
"""Split a `claude -p --output-format json` envelope: `.result` to stdout, the file to its home.

    cc_envelope.py <captured-file> <target-path>

A parsable envelope with a string `result` prints that text (one trailing newline) and is
renamed atomically onto <target-path>, where bin/propose_receipt.py reads its usage. Anything
else — garbage, an empty capture, JSON with no `result` — is printed raw so every reader of
runner stdout still sees exactly what claude said, the capture is deleted, and any stale
<target-path> is removed: usage becomes `unavailable`, never a previous run's numbers.
Exit 0 always; the caller carries claude's own status.
"""
from __future__ import annotations

import json
import os
import pathlib
import sys


def result_text(raw: bytes) -> str | None:
    try:
        envelope = json.loads(raw)
    except ValueError:
        return None
    if not isinstance(envelope, dict) or not isinstance(envelope.get("result"), str):
        return None
    return envelope["result"]


def main(argv: list[str]) -> int:
    captured, target = pathlib.Path(argv[1]), pathlib.Path(argv[2])
    raw = captured.read_bytes()
    text = result_text(raw)
    if text is None:
        sys.stdout.buffer.write(raw)
        captured.unlink(missing_ok=True)
        target.unlink(missing_ok=True)
        return 0
    sys.stdout.write(text if text.endswith("\n") else text + "\n")
    os.replace(captured, target)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
