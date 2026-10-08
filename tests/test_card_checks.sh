#!/usr/bin/env bash
# Dev Plan B3 — driver for the offline test of bin/card_checks.py, the board-join checks of
# design/contracts/standing-research.md.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 tests/test_card_checks.py
