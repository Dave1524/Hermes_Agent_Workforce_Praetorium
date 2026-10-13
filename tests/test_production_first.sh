#!/usr/bin/env bash
# The production-first rule: fixtures first (the companion .py, `::` anchors), then the live
# user-scope files on this box. Off the box the live half skips out loud.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=tests/box_precondition.sh
. tests/box_precondition.sh

python3 tests/test_production_first.py || exit 1

if box_only_with 'the box user-scope instruction files and plan commands' \
  ~/.claude/CLAUDE.md ~/.codex/AGENTS.md ~/.claude/commands/plan-feature.md ~/.claude/commands/ship.md; then
  if python3 bin/production_first_sync.py check; then
    echo "  ok: the live copies match docs/production-first.md and the plan commands carry the sections"
  else
    echo "  FAIL: a live copy drifted; run python3 bin/production_first_sync.py apply"
    exit 1
  fi
fi
