#!/usr/bin/env bash
# agent_alert.sh — the OnFailure alert handler, with a throttle. NUC-25 / NUC-30.
#
# Replaces the inline `/bin/sh -c '...'` that agent-alert@.service used to carry, so
# the alert path is version-controlled and testable instead of quoted twice inside a
# unit file. Called as: agent_alert.sh <failed-unit-name>   (%i from the template).
#
# WHY A THROTTLE: OnFailure fires one instance per failure, and nothing deduplicated
# them. A unit on a 30-minute timer that fails and STAYS failed emits ~48 alerts/day
# — qmd-refresh did exactly that on 2026-08-14, 14 identical alerts before anyone
# looked. Across the 17-31 Aug fortnight, when these alerts are the only signal, one
# stuck unit would bury every other unit's first failure. Repetition is not news; the
# transition into failure is.
#
# TWO RECORDS, ONE THROTTLED. The journal and the log file are written on EVERY
# failure and are never suppressed: they are local, free, and are the only paths that
# still work when the failure being reported is the transport itself. Only the
# outbound notification (Discord + Buzz, via notify.sh) is throttled. Nothing is lost
# — a suppressed failure is still on disk, it just does not buzz Dave's phone again.
#
# NOTIFIES WHEN:
#   1. No open episode          — the transition into failure. The alert that matters.
#   2. The unit succeeded since — it recovered and broke again. A flapping unit is
#      the most interesting state there is, and a pure cooldown would hide it.
#   3. The reminder window passed — one "still failing" per AGENT_ALERT_REMINDER_HOURS
#      (default 24), carrying the suppressed count, so a stuck unit is never silently
#      forgotten for a fortnight.
#
# FAIL-OPEN, ALWAYS. Every uncertainty — unreadable state, unusable clock, a journal
# query that errors — resolves to NOTIFY. A throttle that errs toward silence has
# defeated its own purpose; the worst case must stay a duplicate alert, never a
# missing one.
#
# FAIL-SOFT, ALWAYS. Exits 0 unconditionally, like notify.sh: an OnFailure handler
# that fails is a second alert about itself, and it would mark the reporting unit
# failed on top of the unit it was reporting on.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTIFY_BIN="${NOTIFY_BIN:-$BIN_DIR/notify.sh}"
# Both outward calls are seams, the way DELIVER_BIN is one for the transport: the
# case table drives every branch offline, against neither the real journal nor a
# real Discord/Buzz delivery.
JOURNALCTL_BIN="${JOURNALCTL_BIN:-journalctl}"
STATE_DIR="${AGENT_ALERT_STATE_DIR:-$HOME/.local/state/agent-workforce/alert}"
LOG_FILE="${AGENT_ALERT_LOG:-$HOME/logs/agent-alert.log}"
REMINDER_HOURS="${AGENT_ALERT_REMINDER_HOURS:-24}"

# systemd's stable structured id for "Finished <unit>", i.e. a run that succeeded.
# Matched on MESSAGE_ID rather than on the message text because the text is
# translated and reworded between systemd releases; the id is neither.
MSGID_UNIT_SUCCEEDED=39f53479d3a045ac8e11786248231fbf

unit="${1:-}"
[ -n "$unit" ] || { echo "usage: agent_alert.sh <unit>" >&2; exit 0; }

now=$(date +%s)
stamp=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# systemd instance names are already escaped to [A-Za-z0-9._-], but this handler is
# reachable by hand too; a stray slash would write the state file outside STATE_DIR.
state_file="$STATE_DIR/$(printf '%s' "$unit" | tr -c 'A-Za-z0-9._-' '_')"

record_locally() {  # the two paths that survive a transport failure
  printf '%s\n' "$1" | systemd-cat -t agent-alert -p err 2>/dev/null || true
  mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true
  printf '%s\n' "$1" >> "$LOG_FILE" 2>/dev/null || true
}

state_value() {  # state_value <key> — empty when absent, unreadable, or not a number
  local v
  v=$(sed -n "s/^$1=//p" "$state_file" 2>/dev/null | tail -1)
  [[ $v =~ ^[0-9]+$ ]] && printf '%s' "$v"
}

# A completed run since <epoch> means this is a NEW episode, not a continuing one.
#
# Deliberately NOT `journalctl ... | grep -q .`: under `pipefail` grep -q exits on the
# first match, journalctl dies of SIGPIPE, and the pipeline reports 141 — so a success
# that WAS found returns false and the alert is suppressed. That is the repo-wide trap
# in CLAUDE.md, and here it degrades fail-CLOSED, which is the expensive direction.
# Capturing the output has no early exit and so cannot misreport.
succeeded_since() {
  local found
  found=$("$JOURNALCTL_BIN" -u "$unit" --since "@$1" "MESSAGE_ID=$MSGID_UNIT_SUCCEEDED" \
    -o cat --no-pager 2>/dev/null)
  [ -n "$found" ]
}

# Prints the reason to notify, or nothing to stay silent. Order matters: recovery is
# checked before the reminder window so a flap is reported as a flap, not as a
# "still failing" that has been broken the whole time.
notify_reason() {
  local last="$1" since_h=$(( (now - ${1:-0}) / 3600 ))
  [ -n "$last" ] || { echo "new failure"; return; }
  [ "$last" -le "$now" ] 2>/dev/null || { echo "clock moved backwards — failing open"; return; }
  if succeeded_since "$last"; then
    echo "recovered, then failed again"
  elif [ "$since_h" -ge "$REMINDER_HOURS" ]; then
    echo "still failing after ${since_h}h"
  fi
}

mkdir -p "$STATE_DIR" 2>/dev/null || true

open_episode=$(state_value episode_start)
last_notify=$(state_value last_notify)
suppressed=$(state_value suppressed)
suppressed=${suppressed:-0}

# An episode with no recorded notify is a half-written state file. Treat the episode
# as open but the notify as never made, which fails open by construction.
reason=$(notify_reason "$last_notify")

# A new episode restarts the clock; a reminder keeps the original failure time, which
# is what makes "failing since" in the message mean the start of the outage.
case "$reason" in
  ''|"still failing"*) episode_start="${open_episode:-$now}" ;;
  *)                   episode_start="$now" ;;
esac

msg="agent-workforce ALERT: unit $unit failed at $stamp"
[ "$episode_start" -eq "$now" ] 2>/dev/null \
  || msg="$msg (failing since $(date -u -d "@$episode_start" +%Y-%m-%dT%H:%M:%SZ))"
if [ -z "$reason" ]; then
  msg="$msg [notification throttled: failure $((suppressed + 1)) since the last alert]"
else
  [ "$suppressed" -eq 0 ] || msg="$msg [$suppressed further failure(s) suppressed since the last alert]"
  msg="$msg — $reason"
fi

record_locally "$msg"

if [ -z "$reason" ]; then
  { echo "episode_start=$episode_start"
    echo "last_notify=${last_notify:-$now}"
    echo "suppressed=$((suppressed + 1))"; } > "$state_file" 2>/dev/null || true
  exit 0
fi

{ echo "episode_start=$episode_start"
  echo "last_notify=$now"
  echo "suppressed=0"; } > "$state_file" 2>/dev/null || true

"$NOTIFY_BIN" "[Praetorium] Unit failed: $unit" "$msg" || true

exit 0
