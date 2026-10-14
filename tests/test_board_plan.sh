#!/usr/bin/env bash
# board_plan suite. The assertions and their `::` anchors live in the companion .py; this wrapper is
# only the gate's entry point. No box precondition: temp roots, fakes for systemd.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_board_plan.py
