#!/usr/bin/env bash
# .claude/hooks/ship_rails.py fixture suite — the PreToolUse hook that holds the ship RAILS.
# Assertions and their `::` anchors live in the companion .py; this wrapper is only the
# gate's entry point. No box precondition: two git fixtures under a temp root.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_ship_rails.py
