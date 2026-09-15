#!/usr/bin/env bash
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
python3 tests/test_control_room_views.py
