#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — the de-silencing fix. Direct red-test for the
# ten-day 402 regression: a run that dies produces neither a dated proposal nor a
# DECLINE sentinel, and AGENT_VERIFY_CMD must fail it instead of letting agent_propose.sh
# log "OK: run completed, agent produced no proposal".
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/proposal_or_decline.sh"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
}

check() {
  local inbox=$1 log=$2 run_date=$3 started=$4 slug=$5
  local rc=0
  RUN_DATE="$run_date" AGENT_RUN_STARTED_AT="$started" \
    AGENT_INBOX_DIR="$inbox" AGENT_RUN_LOG="$log" \
    bash "$SCRIPT" "$slug" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}

home=$(mktemp -d)
inbox="$home/_inbox/agents"; mkdir -p "$inbox"
run_log="$home/agent_run.log"
run_date="2026-07-30"
started=$(date -d '2026-07-30 04:30:00' +%s)
proposal="$inbox/${run_date}_standing-research.md"

echo "--- usage: missing slug argument -> exit non-zero ---"
rc=0
bash "$SCRIPT" >/dev/null 2>&1 || rc=$?
assert "exits non-zero" "[ '$rc' != 0 ]"

echo "--- (a) fresh dated proposal present -> exit 0 ---"
: > "$run_log"
printf 'proposal body\n' > "$proposal"
touch -d "@$((started + 60))" "$proposal"
rc=$(check "$inbox" "$run_log" "$run_date" "$started" standing-research)
assert "exits 0" "[ '$rc' = 0 ]"
rm -f "$proposal"

echo "--- (b) no proposal but a DECLINE: sentinel in the log tail -> exit 0 ---"
printf 'some earlier line\nDECLINE: no unprocessed sources in 05_knowledge/raw/\n' > "$run_log"
rc=$(check "$inbox" "$run_log" "$run_date" "$started" standing-research)
assert "exits 0" "[ '$rc' = 0 ]"

echo "--- (c) neither proposal nor decline -> exit 1 (the ten-day silent-failure regression) ---"
: > "$run_log"
rc=$(check "$inbox" "$run_log" "$run_date" "$started" standing-research)
assert "exits 1" "[ '$rc' = 1 ]"

echo "--- (d) a proposal file predating AGENT_RUN_STARTED_AT -> exit 1 (stale artifact must not certify this run) ---"
: > "$run_log"
printf 'stale proposal body from an earlier run\n' > "$proposal"
touch -d "@$((started - 3600))" "$proposal"
rc=$(check "$inbox" "$run_log" "$run_date" "$started" standing-research)
assert "exits 1" "[ '$rc' = 1 ]"
rm -f "$proposal"

echo "--- DECLINE: sentinel outside the tail window does not count ---"
: > "$run_log"
{ printf 'DECLINE: this is outside the tail window\n'; for i in $(seq 1 40); do printf 'line %s\n' "$i"; done; } > "$run_log"
rc=$(check "$inbox" "$run_log" "$run_date" "$started" standing-research)
assert "exits 1" "[ '$rc' = 1 ]"

echo "--- fail closed: missing AGENT_RUN_STARTED_AT -> exit non-zero, never 0 ---"
: > "$run_log"
rc=0
RUN_DATE="$run_date" AGENT_INBOX_DIR="$inbox" AGENT_RUN_LOG="$run_log" \
  bash "$SCRIPT" standing-research >/dev/null 2>&1 || rc=$?
assert "exits non-zero" "[ '$rc' != 0 ]"

echo "--- fail closed: missing RUN_DATE -> exit non-zero, never 0 ---"
rc=0
AGENT_RUN_STARTED_AT="$started" AGENT_INBOX_DIR="$inbox" AGENT_RUN_LOG="$run_log" \
  bash "$SCRIPT" standing-research >/dev/null 2>&1 || rc=$?
assert "exits non-zero" "[ '$rc' != 0 ]"

exit $fail
