#!/usr/bin/env bash
# NUC-45 — smoke test for the morning job: env wiring, artifact assertion, freshness gate.
# Offline: mock claude binary, throwaway vault fixture, no Notion call.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in assert(): `yes` is guaranteed
# to still be writing when `grep -q` exits, so this fails if and only if a condition is
# evaluated under pipefail. It lives in every caller because the assert it guards is shared —
# a single copy in the lib could not tell which suite had reintroduced the setting.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

smoke_suite daily-plan \
  bin/run_daily_plan_cc.sh \
  profiles/daily_plan.env.example \
  daily-plan \
  "# Daily plan — Praetorium morning job (NUC-45)"

echo "--- daily-plan: the port kept the box-specific requirements ---"
TASK="$REPO_ROOT/profiles/daily_plan_task.md"
assert "AITB scan fetches first (a stale fetch reports the wrong in-flight branch)" \
  "grep -q 'git -C ~/dev/AI_Trading_Bot fetch' '$TASK'"
assert "Notion goes through notion_daily.py, not hand-rolled curl" \
  "grep -q 'notion_daily.py plan' '$TASK' && ! grep -qE '^[[:space:]]*curl' '$TASK'"
assert "vault paths are absolute against ~/vault" "grep -q '~/vault/04_operations' '$TASK'"
assert "reads Praetorium's own state instead of SSH-ing to itself" \
  "grep -q 'never SSH' '$TASK' && ! grep -qE '^ssh |ssh praetorium' '$TASK'"
assert "forbids writing the vault (canonical write stays Mac-side)" \
  "grep -q 'Never write, commit, or push' '$TASK'"
assert "counts feed Events Count / Tasks Count" "grep -q 'Events Count' '$TASK'"

assert "the Notion write is unconditional (a catch-up run always finds a row already there)" \
  "grep -q 'Run this every time, including when' '$TASK' && grep -q 'already live, no action' '$TASK'"

exit $fail
