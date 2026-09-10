#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — the de-silencing fix. Direct red-test for the
# ten-day 402 regression: a run that dies produces neither a dated proposal nor a
# DECLINE sentinel, and AGENT_VERIFY_CMD must fail it instead of letting agent_propose.sh
# log "OK: run completed, agent produced no proposal".
#
# T7.1 (2026-09-10) — the sentinel must belong to THIS run of THIS job. It used to be
# read from the shared agent_run.log, which carries no job identity and no run boundary,
# so any job's decline certified every other job's run. Live on 2026-09-09: bd-stall-radar
# declined at 23:04 and bd-followup-drafts passed its verify at 23:31 having produced
# nothing. Every case below that names an attempt log is pinning that scoping.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/proposal_or_decline.sh"

fail=0
# pipefail has no place inside a boolean condition: `grep -q` exits on its first match,
# so whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that
# WAS found — failing a true assertion and silently passing a negated one.
assert() {
  local desc=$1 cond=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
  eval "$pf"
}

assert 'a found pattern is never reported as a failure' "yes | grep -q y"

home=$(mktemp -d)
inbox="$home/_inbox/agents"; mkdir -p "$inbox"
attempt_dir="$home/agent-workforce/logs/last-attempt"; mkdir -p "$attempt_dir"
shared_log="$home/agent-workforce/logs/agent_run.log"
run_date="2026-07-30"
started=$(date -d '2026-07-30 04:30:00' +%s)
proposal="$inbox/${run_date}_standing-research.md"

# The path agent_propose.sh exports per run. Written fresh unless a case is about staleness.
attempt_log() {  # attempt_log <slug> <body> [mtime-epoch]
  local f="$attempt_dir/$1.log"
  printf '%s\n' "$2" > "$f"
  touch -d "@${3:-$((started + 30))}" "$f"
  echo "$f"
}

# HOME is redirected in every invocation so an unset override resolves inside the
# sandbox — otherwise a default-path case reads the live box's own logs.
check() {  # check <slug> [extra env assignments via CHECK_ENV]
  local rc=0
  HOME="$home" RUN_DATE="$run_date" AGENT_RUN_STARTED_AT="$started" \
    AGENT_INBOX_DIR="$inbox" ${CHECK_ENV:+"${CHECK_ENV}"} \
    bash "$SCRIPT" "$1" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}

echo "--- usage: missing slug argument -> exit non-zero ---"
rc=0
bash "$SCRIPT" >/dev/null 2>&1 || rc=$?
assert "exits non-zero" "[ '$rc' != 0 ]"

echo "--- (a) fresh dated proposal present -> exit 0 ---"
rm -f "$attempt_dir"/*.log
printf 'proposal body\n' > "$proposal"
touch -d "@$((started + 60))" "$proposal"
rc=$(check standing-research)
assert "exits 0" "[ '$rc' = 0 ]"
rm -f "$proposal"

echo "--- (b) no proposal but a DECLINE: in THIS run's own output -> exit 0 ---"
attempt_log standing-research 'DECLINE: no unprocessed sources in 05_knowledge/raw/' >/dev/null
rc=$(check standing-research)
assert "exits 0" "[ '$rc' = 0 ]"

echo "--- (c) neither proposal nor decline -> exit 1 (the ten-day silent-failure regression) ---"
rm -f "$attempt_dir"/*.log
rc=$(check standing-research)
assert "exits 1" "[ '$rc' = 1 ]"

echo "--- (d) a proposal file predating AGENT_RUN_STARTED_AT -> exit 1 (stale artifact must not certify this run) ---"
rm -f "$attempt_dir"/*.log
printf 'stale proposal body from an earlier run\n' > "$proposal"
touch -d "@$((started - 3600))" "$proposal"
rc=$(check standing-research)
assert "exits 1" "[ '$rc' = 1 ]"
rm -f "$proposal"

echo "--- T7.1: another job's decline never certifies this one (the 2026-09-09 live failure) ---"
rm -f "$attempt_dir"/*.log
attempt_log bd-stall-radar 'DECLINE: no genuine new stalls, no proposal written' >/dev/null
rc=$(check bd-followup-drafts)
assert "exits 1" "[ '$rc' = 1 ]"
assert "and the job that did decline still passes" "[ \"\$(check bd-stall-radar)\" = 0 ]"

echo "--- T7.1: the shared agent_run.log certifies nothing, wherever the sentinel sits in it ---"
rm -f "$attempt_dir"/*.log
{ printf 'DECLINE: near the top of the shared log\n'
  for i in $(seq 1 40); do printf 'line %s\n' "$i"; done
  printf 'DECLINE: and again in the last 40 lines\n'; } > "$shared_log"
rc=$(check standing-research)
assert "exits 1" "[ '$rc' = 1 ]"
rm -f "$shared_log"

echo "--- T7.1: this job's own output from an EARLIER run -> exit 1 ---"
rm -f "$attempt_dir"/*.log
attempt_log standing-research 'DECLINE: declared by the run before this one' "$((started - 3600))" >/dev/null
rc=$(check standing-research)
assert "exits 1" "[ '$rc' = 1 ]"

echo "--- T7.1: the idempotency skip is not a decline, for every profile that prints one ---"
# design/contracts/knowledge-digest.md records this deliberately: a second run in one day
# is anomalous and must stay visible. Pinned across all six so a later change is a choice.
pinned=0
for f in "$REPO_ROOT"/profiles/*_cc_task.md; do
  skip=$(tr '\n' ' ' < "$f" | { grep -o '"skip: [^"]*"' || true; } | awk 'NR==1' | tr -d '"')
  [ -n "$skip" ] || continue
  pinned=$((pinned + 1))
  rm -f "$attempt_dir"/*.log
  attempt_log standing-research "$skip" >/dev/null
  rc=$(check standing-research)
  assert "$(basename "$f" .md): '$skip' does not certify the run" "[ '$rc' = 1 ]"
done
assert "every profile that prints a skip was pinned, so a broken extraction cannot pass as a clean run ($pinned)" \
  "[ '$pinned' -eq 6 ]"

echo "--- fail closed: missing AGENT_RUN_STARTED_AT -> exit non-zero, never 0 ---"
rm -f "$attempt_dir"/*.log
rc=0
HOME="$home" RUN_DATE="$run_date" AGENT_INBOX_DIR="$inbox" \
  bash "$SCRIPT" standing-research >/dev/null 2>&1 || rc=$?
assert "exits non-zero" "[ '$rc' != 0 ]"

echo "--- fail closed: missing RUN_DATE -> exit non-zero, never 0 ---"
rc=0
HOME="$home" AGENT_RUN_STARTED_AT="$started" AGENT_INBOX_DIR="$inbox" \
  bash "$SCRIPT" standing-research >/dev/null 2>&1 || rc=$?
assert "exits non-zero" "[ '$rc' != 0 ]"

exit $fail
