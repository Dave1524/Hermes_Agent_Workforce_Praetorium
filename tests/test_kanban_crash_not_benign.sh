#!/usr/bin/env bash
# NUC-44 regression: a `blocked` kanban card is only a benign decline when the AGENT
# authored the block (a run with outcome=blocked, i.e. it called kanban_block). A card
# that reached `blocked` because every run crashed is a hard failure wearing a decline's
# clothes — 20 consecutive augustus-content nights logged outcome=NOPROPOSAL + exit 0
# that way, and content_change_dispatch.sh advanced its state over every one of them.
#
# The wrapper must therefore exit non-zero (CRASH_EXIT=4) on a crash-blocked card while
# keeping NUC-25's exit 0 for a genuine decline. Isolated $HOME, stubbed hermes, no
# network, no gateway. Run via bin/verify.sh.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/kanban_run_and_wait.sh"
CRASH_EXIT=4

fail=0
# pipefail describes data-producing pipelines, not conditions: an early-exiting reader
# (grep -q) SIGPIPEs its producer and reports 141, which inverts a true assertion into a
# failure. Scope it off for the duration of the condition only.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# ── Sandbox: isolate $HOME and stub ~/.local/bin/hermes, mirroring
#    tests/test_kanban_run_and_wait.sh so both suites share one fixture shape. ──
sandbox() {
  local home; home=$(mktemp -d)
  mkdir -p "$home/.local/bin"
  # `show` is called twice on a blocked card — once by the poll loop for the status, then
  # again by block_is_agent_authored for the runs. MOCK_SHOW_JSON_2, when set, answers the
  # second call onwards, so a scenario can hand the status read a good payload and the
  # runs read a bad one (scenario 5).
  cat > "$home/.local/bin/hermes" <<'HERMES'
#!/usr/bin/env bash
echo "$@" >> "$ARGV_LOG"
case "${2:-}" in
  create) printf '%s' "$MOCK_CREATE_JSON" ;;
  show)
    n=$(( $(cat "$SHOW_COUNT" 2>/dev/null || echo 0) + 1 ))
    echo "$n" > "$SHOW_COUNT"
    if [ "$n" -ge 2 ] && [ -n "${MOCK_SHOW_JSON_2:-}" ]; then
      printf '%s' "$MOCK_SHOW_JSON_2"
    else
      printf '%s' "$MOCK_SHOW_JSON"
    fi
    ;;
  *) printf '%s' '{}' ;;
esac
HERMES
  chmod +x "$home/.local/bin/hermes"
  printf 'Draft any Picked rows, then pitch.\n' > "$home/task_body.md"
  echo "$home"
}

# Card starts non-terminal so the wrapper enters its poll loop (a terminal status on the
# create response is NUC-38 DEDUP, a different path); the poll then sees $1.
run_wrapper() {
  local home=$1 show_json=$2 show_json_2=${3:-}
  local rc=0
  HOME="$home" ARGV_LOG="$home/hermes_argv.log" SHOW_COUNT="$home/show_count" \
    POLL_INTERVAL_SECONDS=1 POLL_TIMEOUT_SECONDS=2 \
    MOCK_CREATE_JSON='{"id":"t1","task":{"status":"todo"}}' MOCK_SHOW_JSON="$show_json" \
    MOCK_SHOW_JSON_2="$show_json_2" \
    bash "$SCRIPT" "Nightly content pitch+draft" "$home/task_body.md" augustus "$home/ws" \
      "augustus-content-2026-08-12" 5m \
    >"$home/stdout.log" 2>"$home/stderr.log" || rc=$?
  echo "$rc"
}

# Real payload shape, confirmed against `hermes kanban show t_6692a6e6 --json`:
# runs[] sits at the TOP level (not under .task), and a protocol violation surfaces as
# outcome=crashed with the explanation in .error — there is no protocol_violation field.
crashed_runs='{"task":{"status":"blocked"},"runs":[
  {"status":"crashed","outcome":"crashed","error":"worker exited cleanly (rc=0) without calling kanban_complete or kanban_block — protocol violation"},
  {"status":"crashed","outcome":"crashed","error":"worker exited cleanly (rc=0) without calling kanban_complete or kanban_block — protocol violation"},
  {"status":"crashed","outcome":"crashed","error":"worker exited cleanly (rc=0) without calling kanban_complete or kanban_block — protocol violation"}]}'
agent_blocked_runs='{"task":{"status":"blocked"},"runs":[
  {"status":"blocked","outcome":"blocked","summary":"Nothing cleared the insight bar — pitching nothing beats filler.","error":null}]}'
gave_up_runs='{"task":{"status":"blocked"},"runs":[
  {"status":"timed_out","outcome":"timed_out","error":"run exceeded max-runtime"},
  {"status":"gave_up","outcome":"gave_up","error":"retries exhausted"}]}'
no_runs='{"task":{"status":"blocked"},"runs":[]}'

echo '--- scenario 1: all runs crashed -> NOT benign, exits CRASH_EXIT ---'
h1=$(sandbox)
rc=$(run_wrapper "$h1" "$crashed_runs")
assert "exits $CRASH_EXIT (crash, not benign decline)" "[ '$rc' = '$CRASH_EXIT' ]"
assert 'stderr names it a crash, not a decline' "grep -q 'crashed' '$h1/stderr.log'"
assert 'stderr does NOT call it a benign decline' "! grep -q 'benign decline' '$h1/stderr.log'"
assert 'stderr surfaces the underlying run error' "grep -q 'protocol violation' '$h1/stderr.log'"

echo '--- scenario 2: agent-authored kanban_block -> benign decline preserved (NUC-25) ---'
h2=$(sandbox)
rc=$(run_wrapper "$h2" "$agent_blocked_runs")
assert 'exits 0 (genuine decline is still not a failure)' "[ '$rc' = 0 ]"
assert 'stderr records the benign decline' "grep -q 'benign decline' '$h2/stderr.log'"

echo '--- scenario 3: timed_out / gave_up runs are failures too, not declines ---'
h3=$(sandbox)
rc=$(run_wrapper "$h3" "$gave_up_runs")
assert "exits $CRASH_EXIT (no agent-authored block present)" "[ '$rc' = '$CRASH_EXIT' ]"
assert 'stderr does NOT call it a benign decline' "! grep -q 'benign decline' '$h3/stderr.log'"

echo '--- scenario 4: blocked with no runs at all -> fails CLOSED ---'
h4=$(sandbox)
rc=$(run_wrapper "$h4" "$no_runs")
assert "exits $CRASH_EXIT (cannot prove a genuine decline)" "[ '$rc' = '$CRASH_EXIT' ]"

echo '--- scenario 5: unparseable runs payload -> fails CLOSED, never a false benign ---'
# Status reads fine, the runs read does not. A wholly-malformed payload would already die
# in the poll loop's own status parse (non-zero, also fail-closed); this pins the branch
# that is reachable AFTER the card is known blocked, which is where a false benign lives.
h5=$(sandbox)
rc=$(run_wrapper "$h5" "$agent_blocked_runs" '{"task":{"status":"blocked"},"runs":')
assert "exits $CRASH_EXIT when the runs payload cannot be parsed" "[ '$rc' = '$CRASH_EXIT' ]"
assert 'stderr does NOT call it a benign decline' "! grep -q 'benign decline' '$h5/stderr.log'"

echo '--- scenario 6: done card is untouched by the new check ---'
h6=$(sandbox)
rc=$(run_wrapper "$h6" '{"task":{"status":"done"},"runs":[{"outcome":"completed"}]}')
assert 'exits 0 (done)' "[ '$rc' = 0 ]"

exit $fail
