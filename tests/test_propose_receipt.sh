#!/usr/bin/env bash
# propose_receipt.py + content_run_evidence.py suites (T5.2). Assertions and `::` anchors
# live in the two .py files; this wrapper is only the gate's entry point.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_content_run_evidence.py && python3 tests/test_propose_receipt.py
