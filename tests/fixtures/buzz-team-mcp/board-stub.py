#!/usr/bin/env python3
"""Stands in for bin/board.py: logs argv and the text of any file argument, answers one line."""
import json
import os
import sys

argv = sys.argv[1:]
files = {}
for flag in ("--from-file", "--brief"):
    if flag in argv:
        with open(argv[argv.index(flag) + 1], encoding="utf-8") as handle:
            files[flag] = handle.read()
with open(os.environ["BOARD_STUB_LOG"], "a", encoding="utf-8") as log:
    log.write(json.dumps({"argv": argv, "files": files}) + "\n")
if os.environ.get("BOARD_STUB_FAIL"):
    print("board: refused by the stub", file=sys.stderr)
    sys.exit(1)
print("stub-ok " + argv[0])
