#!/usr/bin/env bash
# `requires` — one resolver for the screen's rows and the executor pre-flights (T5.3f).
# Static rules over the live manifests and mutated copies; `check` against a fake systemctl.
# Anchors live in tests/test_workflow_requires.py: (::workflow-requires-resolves)
# (::workflow-requires-fold-agrees) (::workflow-requires-unit-file)
# (::workflow-requires-buzz-handoff) (::workflow-requires-check)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

echo "--- canary ---"
assert "the pipefail canary passes" 'yes | grep -q y'

echo "--- tests/test_workflow_requires.py ---"
assert "the requires suite is green" 'python3 tests/test_workflow_requires.py'

echo "--- executor pre-flight (::workflow-requires-preflight) ---"
# agent_propose.sh calls the CLI before the run and honours exit 1; it is driven end-to-end
# by tests/test_agent_propose_smoke.sh scenario 40. Unknown is not a refusal, and that is the
# CLI's exit 0.
assert "agent_propose.sh calls workflow_requires.py check on the unit systemd is running" \
  'grep -q "WORKFLOW_REQUIRES:-\$BIN_DIR/workflow_requires.py}\" check \"\$requires_unit\"" bin/agent_propose.sh'
assert "and a refusal is a BLOCKED exit" \
  'grep -A6 "workflow_requires.py}\" check" bin/agent_propose.sh | grep -q "block_exit"'
exit $fail
