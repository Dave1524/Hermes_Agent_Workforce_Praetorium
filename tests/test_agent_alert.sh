#!/usr/bin/env bash
# Case table for bin/agent_alert.sh — the OnFailure alert throttle.
#
# Offline by contract: NOTIFY_BIN and JOURNALCTL_BIN are stubbed, so no case can reach
# Discord, Buzz, or the real journal.
#
# The case that matters most is `repeat`: that is the 2026-08-14 qmd-refresh storm,
# where one stuck unit on a 30-minute timer emitted an alert every ~31 min with nothing
# deduplicating them. It must stay SILENT here forever.
#
# The second-most important is `corrupt_state`: a throttle that errs toward silence has
# defeated its own purpose, so every unreadable-state case must still NOTIFY.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
ALERT="$REPO_ROOT/bin/agent_alert.sh"
fail=0

assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
}

# A fixture is a state dir + a notify recorder + a journal stub. `succeeded` decides
# whether the stub reports a completed run since the last alert, which is the only
# thing the real journalctl is consulted for.
# `succeeded=big` emits far more than a pipe buffer holds. That is the regression canary
# for the CLAUDE.md pipefail trap: with `journalctl | grep -q .`, grep exits on the first
# match, journalctl dies of SIGPIPE and the pipeline reports 141, so a success that WAS
# found reads as absent and a real alert is suppressed. A one-line stub passes that bug
# happily — only a large one catches it.
make_fixture() {  # make_fixture <succeeded:yes|no|big>
  local root; root=$(mktemp -d)
  mkdir -p "$root/state"
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$*" >> "%s/notified.log"\n' "$root" > "$root/notify"
  case "$1" in
    yes) printf '#!/usr/bin/env bash\necho "Finished a.service"\n' > "$root/journalctl" ;;
    big) printf '#!/usr/bin/env bash\nseq 1 50000 | sed "s/^/Finished a.service run /"\n' > "$root/journalctl" ;;
    *)   printf '#!/usr/bin/env bash\nexit 0\n' > "$root/journalctl" ;;
  esac
  chmod +x "$root/notify" "$root/journalctl"
  echo "$root"
}

run_alert() {  # run_alert <root> <unit>
  NOTIFY_BIN="$1/notify" JOURNALCTL_BIN="$1/journalctl" \
  AGENT_ALERT_STATE_DIR="$1/state" AGENT_ALERT_LOG="$1/alert.log" \
  AGENT_ALERT_REMINDER_HOURS="${REMINDER_HOURS:-24}" \
    bash "$ALERT" "$2" >"$1/out.log" 2>&1
}

notify_count() { wc -l < "$1/notified.log" 2>/dev/null | tr -d ' '; }

age_last_notify() {  # backdate the open episode by <hours> to age the reminder window
  local root=$1 hours=$2 f; f=$(ls "$root/state"/*)
  # Read before the redirect: `> "$f"` truncates the file before the block runs, so a
  # $(sed ... "$f") inside it reads an already-empty file.
  local sup; sup=$(sed -n 's/^suppressed=//p' "$f")
  local then=$(( $(date +%s) - hours * 3600 ))
  { echo "episode_start=$then"; echo "last_notify=$then"; echo "suppressed=$sup"; } > "$f"
}

echo "--- first failure notifies (the transition into failure) ---"
r=$(make_fixture no); run_alert "$r" demo.service
assert "first failure notifies" "[ \"\$(notify_count '$r')\" = 1 ]"
assert "and names it a new failure" "grep -q 'new failure' '$r/notified.log'"
assert "and writes the local record" "grep -q 'demo.service failed' '$r/alert.log'"

echo "--- repeat failures stay silent (the 2026-08-14 storm) ---"
for _ in 1 2 3 4 5; do run_alert "$r" demo.service; done
assert "five further failures notify nobody" "[ \"\$(notify_count '$r')\" = 1 ]"
assert "but every one is still recorded locally" "[ \"\$(grep -c 'demo.service failed' '$r/alert.log')\" = 6 ]"
assert "and the suppressed count is carried" "grep -q 'suppressed=5' \$(ls '$r'/state/*)"
assert "and the local record numbers the suppressed failures" \
  "grep -q 'throttled: failure 5 since the last alert' '$r/alert.log'"

echo "--- a stuck unit still gets one reminder per window ---"
age_last_notify "$r" 25
run_alert "$r" demo.service
assert "reminder fires after the window" "[ \"\$(notify_count '$r')\" = 2 ]"
assert "and reports it as still failing" "grep -q 'still failing after 25h' '$r/notified.log'"
assert "and carries the suppressed count" "grep -q '5 further failure(s) suppressed' '$r/notified.log'"
assert "and keeps the original failure time" "grep -q 'failing since' '$r/notified.log'"
run_alert "$r" demo.service
assert "the window then closes again" "[ \"\$(notify_count '$r')\" = 2 ]"

echo "--- recovery reopens the episode (a flap must not be hidden) ---"
r=$(make_fixture yes); run_alert "$r" demo.service
run_alert "$r" demo.service
assert "failing after a success notifies again" "[ \"\$(notify_count '$r')\" = 2 ]"
assert "and is reported as a flap, not a reminder" "grep -q 'recovered, then failed again' '$r/notified.log'"

echo "--- a large journal is still read correctly (pipefail/SIGPIPE canary) ---"
r=$(make_fixture big); run_alert "$r" demo.service
run_alert "$r" demo.service
assert "recovery is detected even when the journal query is large" \
  "[ \"\$(notify_count '$r')\" = 2 ]"
assert "and is still reported as a flap" "grep -q 'recovered, then failed again' '$r/notified.log'"
assert "canary: an early-exiting reader under pipefail does report 141" \
  "! bash -c 'set -uo pipefail; seq 1 50000 | grep -q .'"

echo "--- fail-open: uncertainty must never resolve to silence ---"
r=$(make_fixture no); run_alert "$r" demo.service
printf 'episode_start=notanumber\nlast_notify=garbage\n' > "$(ls "$r"/state/*)"
run_alert "$r" demo.service
assert "corrupt state notifies rather than swallowing" "[ \"\$(notify_count '$r')\" = 2 ]"

r=$(make_fixture no); run_alert "$r" demo.service
f=$(ls "$r"/state/*); printf 'episode_start=%s\nlast_notify=%s\n' "$(date +%s)" "$(( $(date +%s) + 7200 ))" > "$f"
run_alert "$r" demo.service
assert "a last_notify in the future notifies (clock moved)" "[ \"\$(notify_count '$r')\" = 2 ]"
assert "and says so" "grep -q 'clock moved backwards' '$r/notified.log'"

echo "--- fail-soft: the handler can never fail the unit it reports on ---"
r=$(make_fixture no)
printf '#!/usr/bin/env bash\nexit 7\n' > "$r/notify"; chmod +x "$r/notify"
rc=0; run_alert "$r" demo.service || rc=$?
assert "a failing notify transport still exits 0" "[ '$rc' = 0 ]"
rc=0; NOTIFY_BIN=/nonexistent JOURNALCTL_BIN=/nonexistent \
  AGENT_ALERT_STATE_DIR=/proc/nope AGENT_ALERT_LOG=/proc/nope/x \
  bash "$ALERT" demo.service >/dev/null 2>&1 || rc=$?
assert "an unwritable state dir still exits 0" "[ '$rc' = 0 ]"
rc=0; bash "$ALERT" >/dev/null 2>&1 || rc=$?
assert "no unit argument still exits 0" "[ '$rc' = 0 ]"

echo "--- the delivery chain this handler stands in front of ---"
# test_buzz_unit_wiring.sh accepts agent_alert.sh as the unit's delivery hook, so the
# link from here to a real adapter has to be pinned somewhere. It is pinned here.
assert "defaults to bin/notify.sh, the delivery adapter" \
  "grep -q 'NOTIFY_BIN:-\$BIN_DIR/notify.sh' '$ALERT'"
assert "and that adapter exists and is executable" "[ -x '$REPO_ROOT/bin/notify.sh' ]"
assert "the unit source invokes this handler" \
  "grep -q '^ExecStart=/home/dave/agent-workforce/bin/agent_alert.sh %i\$' '$REPO_ROOT/systemd/agent-alert@.service'"

echo "--- units are isolated from each other ---"
r=$(make_fixture no)
run_alert "$r" one.service; run_alert "$r" two.service; run_alert "$r" one.service
assert "a second unit's first failure is not throttled by the first's" \
  "[ \"\$(notify_count '$r')\" = 2 ]"
assert "each unit gets its own state file" "[ \"\$(ls '$r'/state | wc -l)\" = 2 ]"

r=$(make_fixture no); run_alert "$r" 'evil/../../etc/passwd'
assert "a path-traversing unit name cannot escape the state dir" \
  "[ \"\$(ls '$r'/state | wc -l)\" = 1 ] && [ ! -e '$r/state/evil' ]"

exit $fail
