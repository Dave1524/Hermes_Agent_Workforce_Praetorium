#!/usr/bin/env bash
# The fleet MCP bridge (buzz-team/buzz-team-mcp.py) over a stub qmd and a stub Brave daemon.
# The assertions and their `::` anchors live in the companion .py — asserts-anchored in
# tests/test_workflow_coverage.py follows the python line below — so this wrapper is only the
# gate's entry point. No box precondition: nothing here reaches the live index, the broker
# socket or Brave.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_buzz_team_mcp.py
