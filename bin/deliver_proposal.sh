#!/usr/bin/env bash
# Proposal-or-decline receipt for the agent_propose.sh jobs — the `status` payload.
#
# The answer comes from the run's own cost.log record, never from the agent's prose.
# agent_run.log is a raw concatenation of attempt stdout with no run boundary in it, so
# nothing there can be attributed to a particular run; the structured record that
# agent_propose.sh appends when a run ends can. A run that produced no record at all
# died before it could write one, which is itself the thing most worth reporting —
# the ten-day OpenRouter 402 outage read as a clean NOPROPOSAL precisely because
# nobody was watching for the absence.
#
# The decline REASON is the one thing only agent_run.log holds, and it is quoted only
# when that log was written during this run.
set -uo pipefail

# shellcheck source=bin/delivery_common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/delivery_common.sh"

TASK="${DELIVERY_TASK:-}"
COST_LOG="${AGENT_COST_LOG:-$HOME/agent-workforce/logs/cost.log}"
RUN_LOG="${AGENT_RUN_LOG:-$HOME/agent-workforce/logs/agent_run.log}"
MARKER="${DELIVERY_RUN_MARKER:-}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] ${TASK:-agent run}}"

run_record() {  # last cost.log record for this task; fields are space-separated
  [ -n "$TASK" ] || return 1
  [ -r "$COST_LOG" ] || return 1
  grep " task=$TASK " "$COST_LOG" | tail -1
}

field() {  # field <record> <key>
  printf '%s' "$1" | tr ' ' '\n' | sed -n "s/^$2=//p" | tail -1
}

is_this_run() {  # the record must post-date the marker stamped before ExecStart
  [ -n "$MARKER" ] || return 0
  [ -f "$MARKER" ] || return 1
  local ts; ts=$(field "$1" ts)
  [ -n "$ts" ] || return 1
  [ "$(date -d "$ts" +%s 2>/dev/null || echo 0)" -ge "$(stat -c %Y "$MARKER" 2>/dev/null || echo 0)" ]
}

decline_reason() {
  [ -r "$RUN_LOG" ] || return 0
  [ -n "$MARKER" ] && [ ! "$RUN_LOG" -nt "$MARKER" ] && return 0
  grep '^DECLINE:' "$RUN_LOG" | tail -1
}

status_line() {  # status_line <record>
  local outcome proposal secs ts reason
  outcome=$(field "$1" outcome); proposal=$(field "$1" proposal)
  secs=$(field "$1" run_seconds); ts=$(field "$1" ts)
  case "$outcome" in
    PROPOSAL)
      printf '%s — proposed _inbox/agents/%s_%s.md (%ss)' \
        "$outcome" "${ts%%T*}" "$proposal" "$secs" ;;
    NOPROPOSAL)
      reason=$(decline_reason)
      [ -n "$reason" ] || reason='DECLINE: no reason recorded in agent_run.log'
      printf '%s — %s (%ss)' "$outcome" "${reason#DECLINE: }" "$secs" ;;
    *)
      printf '%s (%ss)' "${outcome:-unknown outcome}" "$secs" ;;
  esac
}

record=$(run_record)
if [ -z "$record" ]; then
  note "no cost.log record for task=${TASK:-<unset>}"
  delivery_handoff --subject "$SUBJECT" \
    --message "no run record for task ${TASK:-<unset>} — the run ended before agent_propose.sh wrote one"
  exit 0
fi

if ! is_this_run "$record"; then
  note "newest record for task=$TASK predates this run"
  delivery_handoff --subject "$SUBJECT" \
    --message "this run wrote no record; the newest for $TASK is from $(field "$record" ts)"
  exit 0
fi

line=$(status_line "$record")
note "$line"
delivery_handoff --subject "$SUBJECT" --message "$line"

exit 0
