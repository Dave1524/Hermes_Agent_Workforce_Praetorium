#!/usr/bin/env bash
# Proposal-or-decline receipt for the agent_propose.sh jobs — the `status` payload.
#
# The answer comes from the run's own cost.log record, never from the agent's prose.
# agent_run.log is a raw concatenation of attempt stdout with no run boundary in it, so
# nothing there can be attributed to a particular run; the structured record that
# agent_propose.sh appends when a run ends can.
#
# The decline REASON is the one thing the structured record does not hold. It comes from
# the run's OWN output — agent_propose.sh keeps this attempt's stdout at a path keyed by
# task — and is quoted only when that file was written during this run. Reading it from
# agent_run.log quoted whichever sibling job had declined last: on 2026-09-09 that stream
# held bd-stall-radar's decline 27 minutes before bd-followup-drafts said nothing at all.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/delivery_common.sh
. "$BIN_DIR/delivery_common.sh"

TASK="${DELIVERY_TASK:-}"
MARKER="${DELIVERY_RUN_MARKER:-}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] ${TASK:-agent run}}"
INBOX_DIR="${AGENT_INBOX_DIR:-$HOME/agent-worktrees/inbox/_inbox/agents}"
# ExecStartPost is a separate process and inherits no export from the run, so the path is
# derived from the same task slug agent_propose.sh keyed it on.
ATTEMPT_LOG="${AGENT_ATTEMPT_LOG:-$HOME/agent-workforce/logs/last-attempt/${TASK}.log}"

# shellcheck source=bin/run_record.sh
. "$BIN_DIR/run_record.sh"

DELIVERY_RUNTIME=$(run_runtime "$DELIVERY_RUNTIME")

decline_reason() {
  [ -n "$TASK" ] || return 0
  [ -r "$ATTEMPT_LOG" ] || return 0
  [ -n "$MARKER" ] && [ ! "$ATTEMPT_LOG" -nt "$MARKER" ] && return 0
  grep '^DECLINE:' "$ATTEMPT_LOG" | tail -1
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
      [ -n "$reason" ] || reason="DECLINE: no reason recorded in $ATTEMPT_LOG"
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

artifact_args() {  # artifact_args <record> — the proposal itself, when this run wrote one
  local ts proposal name path
  proposal=$(field "$1" proposal); [ -n "$proposal" ] || return 0
  ts=$(field "$1" ts); name="${ts%%T*}_${proposal}.md"; path="$INBOX_DIR/$name"
  [ -r "$path" ] || { note "proposal named but not readable at $path"; return 0; }
  printf '%s\n' --file "$path" --artifact-type proposal \
    --target "_inbox/agents/$name" --operation create
}

line=$(status_line "$record")
note "$line"

payload=()
while IFS= read -r arg; do payload+=("$arg"); done < <(artifact_args "$record")
delivery_handoff --subject "$SUBJECT" --message "$line" --note "$line" \
  ${payload[@]+"${payload[@]}"}

exit 0
