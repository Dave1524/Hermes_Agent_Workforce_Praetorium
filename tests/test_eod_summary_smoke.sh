#!/usr/bin/env bash
# NUC-45 — smoke test for the evening job: env wiring, artifact assertion, freshness gate,
# and the evidence-only contract. Offline: mock claude, throwaway fixture, no Notion call.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

smoke_suite eod-summary \
  bin/run_eod_summary_cc.sh \
  profiles/eod_summary.env.example \
  eod-summary \
  "# EOD summary — Praetorium evening job (NUC-45)"

echo "--- eod-summary: evidence-only contract ---"
TASK="$REPO_ROOT/profiles/eod_summary_task.md"
assert "an evidence gap must surface as UNCONFIRMED, not a filled-in claim" \
  "grep -q 'UNCONFIRMED' '$TASK'"
assert "the rule is stated as exhaustive (no third option)" \
  "grep -q 'There is no third option' '$TASK'"
assert "inventing a brain dump is explicitly forbidden" \
  "grep -q 'Never invent a brain dump' '$TASK'"
assert "names what the box cannot see, so the gap is not silently filled" \
  "grep -q 'CANNOT show' '$TASK'"
assert "writes both Daily Plans and Daily Log via notion_daily.py" \
  "grep -q 'notion_daily.py eod' '$TASK' && ! grep -qE '^[[:space:]]*curl' '$TASK'"
assert "reads the day's task deltas, not just the open backlog" "grep -q -- '--since' '$TASK'"
assert "declares itself a draft the Mac's eod-wrap overwrites in place" \
  "grep -q 'overwrites this row in place' '$TASK'"

echo "--- eod-summary: the evening slot precedes bd-stall-radar ---"
EOD_TIMER="$REPO_ROOT/systemd/praetorium-eod-summary.timer"
RADAR_TIMER="$REPO_ROOT/systemd/bd-stall-radar.timer"
eod_at=$(grep -oE 'OnCalendar=.*[0-9]{2}:[0-9]{2}' "$EOD_TIMER" | grep -oE '[0-9]{2}:[0-9]{2}')
radar_at=$(grep -oE 'OnCalendar=.*[0-9]{2}:[0-9]{2}' "$RADAR_TIMER" | grep -oE '[0-9]{2}:[0-9]{2}')
assert "EOD ($eod_at) runs before bd-stall-radar ($radar_at) so the radar sees a closed day" \
  "[[ '$eod_at' < '$radar_at' ]]"
assert "both new timers are Persistent (a reboot spanning the slot still catches up)" \
  "grep -q '^Persistent=true' '$EOD_TIMER' && grep -q '^Persistent=true' '$REPO_ROOT/systemd/praetorium-daily-plan.timer'"

echo "--- both units: multi-word Environment= values must be quoted ---"
# systemd splits an unquoted Environment= line on whitespace, so
# `Environment=REPORT_SUBJECT=[Praetorium] Daily plan` silently becomes `[Praetorium]`
# and drops the rest (caught by systemd-analyze verify at install time, 2026-07-27).
for unit in praetorium-daily-plan praetorium-eod-summary; do
  unquoted=$(grep -E '^Environment=[^"]*=[^"]* ' "$REPO_ROOT/systemd/$unit.service" || true)
  assert "$unit.service has no unquoted multi-word Environment=" "[ -z '$unquoted' ]"
done

exit $fail
