#!/usr/bin/env bash
# Read-only Control Room backend/API fixture suite. (::control-room-api)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_control_room_api.py
