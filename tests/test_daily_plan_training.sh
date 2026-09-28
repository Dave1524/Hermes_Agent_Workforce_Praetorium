#!/usr/bin/env bash
# The daily plan's Training line (2026-09-28): bin/workout_today.py reads the day's row from
# the workout schedule, and the contract check `training-line-present` fails a plan without
# one. Before this, training appeared "only if today has a slot" and rest days dropped out.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$REPO_ROOT/bin/workout_today.py"
CONTRACT="$REPO_ROOT/design/contracts/praetorium-daily-plan.md"
PROFILE="$REPO_ROOT/profiles/daily_plan_task.md"

fail=0
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/training.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# The schedule's real shape: a week heading, a four-column table, bold day cells on some
# rows, links in the session cell, and a pipe inside a detail cell.
cat >"$WORK/schedule.md" <<'EOF'
# Workout Schedule

| Wk | Dates | Phase |
|---|---|---|
| W4 | Sep 28–Oct 4 | continuous |

### W4 — VACATION · CONTINUOUS RUNNING OPENS (Sep 28 – Oct 4)

| Day | Session | Detail | Status |
|---|---|---|---|
| Mon 9/28 | [Session R+](strength_library.md#session-r) | Hop ladder → raises → mobility, at home | — |
| **Tue 9/29** | **Run 1** → Strength B | **20 min continuous**, band pace, HR < 145 \| gate: Sat's 48 h | — |
| Wed 9/30 | Travel / rest | Walk | — |
| Fri 10/2 | Rest / walk | Hikes count as walking | ✓ done — see [[workout_log#2026-10-02]] |
EOF

run() { python3 "$BIN" --schedule "$WORK/schedule.md" --date "$1" >"$WORK/out" 2>"$WORK/err"; }
field() { sed -n "s/^$1: //p" "$WORK/out"; }

echo '--- workout_today.py: one row, the right one ---'
run 2026-09-28; rc=$?
assert 'a scheduled day is found' "[ $rc -eq 0 ]"
assert 'with its week' "[ \"\$(field week)\" = 'W4 — VACATION · CONTINUOUS RUNNING OPENS (Sep 28 – Oct 4)' ]"
assert 'as a training day' "[ \"\$(field kind)\" = training ]"
assert 'the session with the link markup stripped' "[ \"\$(field session)\" = 'Session R+' ]"
run 2026-09-29
assert 'a bold day cell still matches' "[ \"\$(field session)\" = 'Run 1 → Strength B' ]"
assert 'and a pipe inside the detail stays in the detail' "field detail | grep -qF 'HR < 145 \\| gate'"
run 2026-09-30
assert 'Travel / rest is a rest day' "[ \"\$(field kind)\" = rest ]"
run 2026-10-02
assert 'Rest / walk is a rest day' "[ \"\$(field kind)\" = rest ]"
assert 'and the status column is its own field' "field status | grep -q '^✓ done'"
run 2026-10-01; rc=$?
assert 'a date with no row exits 1' "[ $rc -eq 1 ] && grep -q 'no row for Thu 10/1' '$WORK/err'"
python3 "$BIN" --schedule "$WORK/absent.md" --date 2026-09-28 >/dev/null 2>&1; rc=$?
assert 'an unreadable schedule exits 2' "[ $rc -eq 2 ]"

echo '--- the profile makes the line mandatory and names the helper ---'
assert 'the profile runs workout_today.py for the run date' \
  "grep -qF 'workout_today.py --date \"\$DATE\"' '$PROFILE'"
assert 'the plan structure has a Training section' "grep -q '^## Training' '$PROFILE'"
assert 'and the old conditional read-list entry is gone' \
  "! grep -qF 'workout_schedule.md\` — only if today has a slot' '$PROFILE'"

echo '--- contract: training-line-present ---'
sed -n '/^   ```check id=training-line-present/,/^   ```$/p' "$CONTRACT" | sed '1d;$d' >"$WORK/check.sh"
assert 'the contract carries the check' "[ -s '$WORK/check.sh' ]"
mkdir -p "$WORK/home/logs/daily-plan"
PLAN="$WORK/home/logs/daily-plan/daily-plan-2026-09-28T0403Z.md"
run_check() {
  env -i PATH="$PATH" HOME="$WORK/home" AGENT_RUN_STARTED_AT="$(( $(date +%s) - 60 ))" \
    bash "$WORK/check.sh" >"$WORK/check.out" 2>&1
}
printf '> Monday.\n\n## Calendar\n- 09:00 call\n\n## Training\n- Session R+ — hop ladder, raises, mobility, at home\n\n## Priorities\n1. x\n' >"$PLAN"
run_check; rc=$?
assert 'a plan with a training line passes and quotes it' "[ $rc -eq 0 ] && grep -q 'Session R+' '$WORK/check.out'"
printf '> Wednesday.\n\n## Training\n- Rest day — Travel / rest, walk\n' >"$PLAN"
run_check; rc=$?
assert 'a rest day is a line, and passes' "[ $rc -eq 0 ]"
printf '> Monday.\n\n## Calendar\n- 09:00 call\n\n## Priorities\n1. x\n' >"$PLAN"
run_check; rc=$?
assert 'a plan with no Training section fails' "[ $rc -eq 1 ] && grep -q 'missing from the plan' '$WORK/check.out'"
printf '> Monday.\n\n## Training\n\n## Priorities\n- a priority is not a training line\n' >"$PLAN"
run_check; rc=$?
assert 'an empty Training section fails — the next section'"'"'s line does not count' "[ $rc -eq 1 ]"
touch -d '2 hours ago' "$PLAN"
run_check; rc=$?
assert 'no plan from this run is n/a' "[ $rc -eq 77 ]"

if [ "$fail" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "all daily-plan training assertions passed"
