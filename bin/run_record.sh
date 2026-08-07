#!/usr/bin/env bash
# The cost.log record for the invocation now ending — shared by every adapter that
# hangs off an agent_propose.sh job.
#
# agent_propose.sh appends one structured record per run and does it before
# ExecStartPost fires, so the record is the only account of a run that can be
# attributed to that run. Anchoring it to the marker stamped at ExecStartPre is what
# separates "this run said nothing" from "this run never got far enough to say
# anything" — the distinction the ten-day OpenRouter 402 outage erased, when eight
# dead nights read as clean declines.
#
# Expects TASK and MARKER in scope. Not executable on its own.

COST_LOG="${AGENT_COST_LOG:-$HOME/agent-workforce/logs/cost.log}"

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

marker_epoch() {
  stat -c %Y "${MARKER:-/nonexistent}" 2>/dev/null || echo 0
}
