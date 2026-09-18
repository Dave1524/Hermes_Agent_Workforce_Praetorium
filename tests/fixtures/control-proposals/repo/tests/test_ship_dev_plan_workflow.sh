#!/usr/bin/env bash
# Fixture stand-in for the dev-plan workflow gate: the literal equals the live [[workflows]] count.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
script_entries=$(sed -n 's/^const WORKFLOW_ENTRIES = \([0-9]*\)$/\1/p' .claude/workflows/ship-dev-plan.js)
live_entries=$(cat design/agents/*.toml | grep -c '^\[\[workflows\]\]')
[ -n "$script_entries" ] && [ "$script_entries" = "$live_entries" ]
