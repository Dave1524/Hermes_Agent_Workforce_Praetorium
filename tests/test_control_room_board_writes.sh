#!/usr/bin/env bash
# Board write seam suite (B5). The assertions live in the companion .py; this wrapper is only
# the gate's entry point. No box precondition: synthetic cards, temp roots, loopback server.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_control_room_board_writes.py
