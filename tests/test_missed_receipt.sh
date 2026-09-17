#!/usr/bin/env bash
# Missed-receipt judgement suite. The assertions and their `::` anchors live in the companion
# .py; this wrapper is only the gate's entry point. No box precondition.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_missed_receipt.py
