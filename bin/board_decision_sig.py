#!/usr/bin/env python3
"""Reference verifier for the board broker's signed decisions (Dev Plan B9, spec §7 decision 12).

The broker (bin/control_broker.py, root) appends each decision to decisions.jsonl with a `sig`: an
OpenSSH signature, namespace `board-decision`, over the canonical JSON of the record without `sig`.
Anything that holds the broker's public key can check a line, and nothing running as dave can make
one. The Mac watcher (B10) re-implements this from the runbook; this file pins the bytes.

    board_decision_sig.py verify --allowed-signers FILE [decisions.jsonl]   exit 1 on any bad line
    board_decision_sig.py allowed-signers KEY.pub                           print the pin for the Mac
"""
from __future__ import annotations

import argparse
import json
import pathlib
import subprocess
import sys
import tempfile
from typing import Any, Mapping

NAMESPACE = "board-decision"
SIGNER = "board-broker"


def canonical(record: Mapping[str, Any]) -> bytes:
    body = {key: value for key, value in record.items() if key != "sig"}
    return json.dumps(body, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def allowed_signers_line(public_key: str) -> str:
    kind, blob = public_key.split()[:2]
    return f'{SIGNER} namespaces="{NAMESPACE}" {kind} {blob}\n'


def verify(record: Mapping[str, Any], allowed_signers: pathlib.Path | str) -> bool:
    signature = record.get("sig")
    if not isinstance(signature, str) or not signature:
        return False
    with tempfile.TemporaryDirectory() as scratch:
        sig_file = pathlib.Path(scratch) / "sig"
        sig_file.write_text(signature, encoding="utf-8")
        done = subprocess.run(
            ["ssh-keygen", "-Y", "verify", "-f", str(allowed_signers), "-I", SIGNER, "-n", NAMESPACE, "-s", str(sig_file)],
            input=canonical(record), capture_output=True, check=False)
    return done.returncode == 0


def verify_stream(path: pathlib.Path | str, allowed_signers: pathlib.Path | str) -> list[int]:
    bad: list[int] = []
    for number, line in enumerate(pathlib.Path(path).read_text(encoding="utf-8").splitlines(), 1):
        try:
            ok = verify(json.loads(line), allowed_signers)
        except ValueError:
            ok = False
        if not ok:
            bad.append(number)
    return bad


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    modes = parser.add_subparsers(dest="mode", required=True)
    check = modes.add_parser("verify")
    check.add_argument("--allowed-signers", required=True)
    check.add_argument("stream", nargs="?", default="/var/lib/control-room/receipts/board/decisions.jsonl")
    pin = modes.add_parser("allowed-signers")
    pin.add_argument("public_key")
    args = parser.parse_args(argv)
    if args.mode == "allowed-signers":
        sys.stdout.write(allowed_signers_line(pathlib.Path(args.public_key).read_text(encoding="utf-8")))
        return 0
    bad = verify_stream(args.stream, args.allowed_signers)
    for number in bad:
        print(f"line {number}: signature does not verify", file=sys.stderr)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
