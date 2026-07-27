#!/usr/bin/env bash
# NUC-45 — case table for bin/vault_sync_guard.sh. Offline by contract: every case runs
# against a throwaway git fixture, never ~/vault and never a real remote.
#
# The case that matters most is `sync|dirty_behind`: that is the 2026-07-23→27 freeze,
# where a rejected fast-forward was swallowed by `|| echo "(offline?)"` and the unit still
# reported success. It must stay RED (exit 1) here forever. The table is exhaustive over
# the guard's branches so a new branch cannot be added without a case.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# mode | state | expected rc | expected message fragment
CASES=(
  "sync|clean_behind|0|fast-forwarded"
  "sync|dirty_behind|1|REJECTED"
  "sync|clean_current|0|already current"
  "sync|offline|0|SOFT: cannot reach origin"
  "check|clean_current|0|in sync with"
  "check|clean_behind|0|within 24h"
  "check|stale_behind|1|REFUSE"
  "check|dirty_behind|1|REFUSE"
  "check|untracked|0|not blocking"
  "check|offline|0|WARN: cannot reach origin"
  "check|offline_stale|1|REFUSE"
)

declare -A ROOT
for c in "${CASES[@]}"; do
  IFS='|' read -r mode state want_rc want_msg <<<"$c"
  root=$(make_vault_fixture "$state")
  ROOT["$mode/$state"]="$root"
  rc=0
  VAULT_DIR="$root/vault" bash "$GUARD" "$mode" --max-lag-hours 24 >"$root/out.log" 2>&1 || rc=$?
  echo "--- $mode / $state (rc=$rc) ---"
  assert "$mode/$state exits $want_rc" "[ '$rc' = '$want_rc' ]"
  assert "$mode/$state reports '$want_msg'" "grep -q '$want_msg' '$root/out.log'"
done

echo "--- state assertions ---"
r=${ROOT["sync/clean_behind"]}
assert "clean+behind actually fast-forwarded (worktree now has upstream content)" \
  "grep -q 'published from the Mac' '$r/vault/shared.md'"

r=${ROOT["sync/dirty_behind"]}
assert "rejected pull names the blocking file" "grep -q 'shared.md' '$r/out.log'"
assert "rejected pull discards nothing (local edit survives)" \
  "grep -q 'box-side edit' '$r/vault/shared.md'"
assert "rejected pull leaves the tree unmoved (still behind)" \
  "[ \"\$(git -C '$r/vault' rev-list --count HEAD..origin/main)\" = 1 ]"

r=${ROOT["check/dirty_behind"]}
assert "check names the dirty file rather than swallowing it" "grep -q 'shared.md' '$r/out.log'"

r=${ROOT["check/untracked"]}
assert "untracked stray is surfaced, not silently ignored" \
  "grep -q 'local_inference_charter.md' '$r/out.log'"

r=${ROOT["check/offline"]}
assert "offline check is distinguishable from an in-sync check" "! grep -q 'in sync with' '$r/out.log'"

echo "--- usage ---"
rc=0; bash "$GUARD" >/dev/null 2>&1 || rc=$?
assert "no mode exits 2 (usage)" "[ '$rc' = 2 ]"
rc=0; VAULT_DIR=$(mktemp -d) bash "$GUARD" check >/dev/null 2>&1 || rc=$?
assert "non-checkout path exits 1" "[ '$rc' = 1 ]"

exit $fail
