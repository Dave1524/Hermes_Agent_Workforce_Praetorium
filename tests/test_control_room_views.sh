#!/usr/bin/env bash
# Control Room screen fixture suite (T5.3): views, static, headers, control stubs, serve wrapper.
# Anchors live in the .py this runs. Fixture-only: no timer, no bus, no runtime tree.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_control_room_views.py
