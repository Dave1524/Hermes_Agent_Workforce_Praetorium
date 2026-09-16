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

echo "--- units this box depends on that no repo unit file describes (EXTERNAL_UNITS) ---"
python3 - <<'PY'
import sys
sys.path.insert(0, "bin")
import workflow_requires
for key, description in workflow_requires.EXTERNAL_UNITS.items():
    print(f"  {key}\t{description}")
PY

echo "--- tests/test_workflow_requires.py ---"
assert "the requires suite is green" 'python3 tests/test_workflow_requires.py'
exit $fail
