#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — shared AGENT_VERIFY_CMD for the standing-research,
# raw-ingest and knowledge-digest CC jobs. Closes the ten-day silent-failure regression:
# an OpenRouter 402 died on the hermes/claudius path without ever surfacing in
# agent_propose.sh's PROVIDER_ERROR_RE scan (the error went to the hermes profile's own
# errors.log, not the attempt's stdout), so a dead run logged "OK: run completed, agent
# produced no proposal" for eight consecutive days. A run is only legitimate if it EITHER
# produced this run's dated proposal OR deliberately declined — anything else must FAIL.
#
# RUN_DATE and AGENT_RUN_STARTED_AT are already exported by agent_propose.sh (the date
# stamp and the run's start epoch) — read them, never recompute, so this can't drift from
# a midnight rollover between the two scripts.
#
# usage: proposal_or_decline.sh <slug>
set -euo pipefail

slug="${1:?usage: proposal_or_decline.sh <slug>}"
: "${RUN_DATE:?RUN_DATE not set (exported by agent_propose.sh) — fail closed}"
: "${AGENT_RUN_STARTED_AT:?AGENT_RUN_STARTED_AT not set (exported by agent_propose.sh) — fail closed}"

inbox_dir="${AGENT_INBOX_DIR:-$HOME/agent-worktrees/inbox/_inbox/agents}"
run_log="${AGENT_RUN_LOG:-$HOME/agent-workforce/logs/agent_run.log}"
tail_lines="${AGENT_DECLINE_TAIL_LINES:-40}"

proposal_file="$inbox_dir/${RUN_DATE}_${slug}.md"

proposal_fresh() {
  [ -f "$proposal_file" ] || return 1
  find "$inbox_dir" -maxdepth 1 -name "$(basename "$proposal_file")" \
    -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | grep -q .
}

decline_sentinel() {
  [ -f "$run_log" ] || return 1
  tail -n "$tail_lines" "$run_log" | grep -qE '^DECLINE:'
}

proposal_fresh && exit 0
decline_sentinel && exit 0
exit 1
