#!/usr/bin/env bash
# bin/turn_rate.py fixture suite — the reader behind fleet-turn-check.sh gate 5. Assertions
# and their `::` anchors live in the companion .py; this wrapper is only the gate's entry
# point. No box precondition: synthetic receipts under a temp root, the clock pinned.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_turn_rate.py
