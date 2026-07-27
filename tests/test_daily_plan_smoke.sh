#!/usr/bin/env bash
# NUC-45 — smoke test for the morning job: env wiring, artifact assertion, freshness gate.
# Offline: mock claude binary, throwaway vault fixture, no Notion call.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

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

exit $fail
