#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — shared AGENT_VERIFY_CMD for the standing-research,
# raw-ingest and knowledge-digest CC jobs. Closes the ten-day silent-failure regression:
# an OpenRouter 402 died on the hermes/claudius path without ever surfacing in
# agent_propose.sh's PROVIDER_ERROR_RE scan (the error went to the hermes profile's own
# errors.log, not the attempt's stdout), so a dead run logged "OK: run completed, agent
# produced no proposal" for eight consecutive days. A run is only legitimate if it EITHER
# produced this run's dated proposal OR deliberately declined — anything else must FAIL.
#
# RUN_DATE, AGENT_RUN_STARTED_AT and AGENT_ATTEMPT_LOG are already exported by
# agent_propose.sh (the date stamp, the run's start epoch and this attempt's own output) —
# read them, never recompute, so this can't drift from a midnight rollover between the two
# scripts.
#
# T7.1 (2026-09-10): the sentinel is read from THIS run's own output, never from the shared
# agent_run.log. That log is one stream for every job with no run boundary in it, so any
# job's decline satisfied every other job's check — on 2026-09-09 bd-followup-drafts passed
# here on a decline bd-stall-radar had written, having produced nothing itself. A per-run,
# per-job file removes both ambiguities at once, which is why there is no tail window left
# to tune: the file holds one attempt of one job, so there is nothing to window.
#
# usage: proposal_or_decline.sh <slug>
set -euo pipefail

slug="${1:?usage: proposal_or_decline.sh <slug>}"
: "${RUN_DATE:?RUN_DATE not set (exported by agent_propose.sh) — fail closed}"
: "${AGENT_RUN_STARTED_AT:?AGENT_RUN_STARTED_AT not set (exported by agent_propose.sh) — fail closed}"

inbox_dir="${AGENT_INBOX_DIR:-$HOME/agent-worktrees/inbox/_inbox/agents}"
# Derived from the slug when unset so a hand invocation stays job-scoped rather than
# falling back to something shared.
attempt_log="${AGENT_ATTEMPT_LOG:-$HOME/agent-workforce/logs/last-attempt/${slug}.log}"

proposal_file="$inbox_dir/${RUN_DATE}_${slug}.md"

# Never `find … | grep -q`: grep exits on its first match, the find dies of SIGPIPE and
# pipefail reports 141 for a file that WAS found.
newer_than_run() {  # newer_than_run <path>
  [ -f "$1" ] || return 1
  [ -n "$(find "$(dirname "$1")" -maxdepth 1 -name "$(basename "$1")" \
            -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
}

proposal_fresh() {
  newer_than_run "$proposal_file"
}

decline_sentinel() {
  newer_than_run "$attempt_log" || return 1
  grep -qE '^DECLINE:' "$attempt_log"
}

proposal_fresh && exit 0
decline_sentinel && exit 0
exit 1
