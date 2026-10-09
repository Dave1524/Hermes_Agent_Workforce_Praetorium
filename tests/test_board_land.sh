#!/usr/bin/env bash
# Land, sweep and Done-join suite for the agent board. Assertions and `::` anchors live in the
# companion .py; no box precondition: synthetic cards, temp roots, a temp bare "canonical" repo.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_board_land.py
