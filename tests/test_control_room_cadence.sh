#!/usr/bin/env bash
# Control Room cadence/freshness fixture suite (T5.3). Anchors live in the .py this runs.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_control_room_cadence.py
