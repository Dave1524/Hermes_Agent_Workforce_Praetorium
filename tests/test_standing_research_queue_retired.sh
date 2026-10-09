#!/usr/bin/env bash
set -uo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TASK="$ROOT/profiles/standing_research_cc_task.md"
CONTRACT="$ROOT/design/contracts/standing-research.md"
fail=0
assert() {
  local label="$1" cmd="$2"
  if (set +o pipefail; eval "$cmd") >/dev/null 2>&1; then echo "PASS: $label"; else echo "FAIL: $label"; fail=1; fi
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"
assert "profile never names queue.md" "! grep -q 'queue.md' '$TASK'"
assert "profile never names a Q- queue item" "! grep -q 'Q-2026' '$TASK'"
assert "contract has no queue.md input row" "! grep -q '^| .04_operations/box_brief/queue.md' '$CONTRACT'"
assert "profile still reads standing_missions.md" "grep -q 'standing_missions.md' '$TASK'"
assert "decline step and duplicate-title gate are distinct" "grep -q 'Decline as in step 2b' '$TASK' && grep -q 'gate 2c' '$TASK' && grep -q '^2c\\.' '$TASK'"
exit "$fail"
