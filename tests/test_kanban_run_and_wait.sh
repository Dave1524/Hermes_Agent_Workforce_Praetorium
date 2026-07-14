#!/usr/bin/env bash
# Test for bin/kanban_run_and_wait.sh — NUC-29 (real-date banner) + NUC-38 (idempotent-
# hit DEDUP detection). Isolated $HOME, a stubbed hermes that logs its argv and emits
# controllable JSON, no network, no real kanban gateway. Run via bin/verify.sh or directly.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/kanban_run_and_wait.sh"

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

# ── Sandbox: isolate $HOME and stub ~/.local/bin/hermes (what the wrapper invokes). The
#    stub logs every argv to $ARGV_LOG and prints MOCK_CREATE_JSON for `kanban create` /
#    MOCK_SHOW_JSON for `kanban show`, so a scenario fully controls create + poll results. ──
sandbox() {
  local home; home=$(mktemp -d)
  mkdir -p "$home/.local/bin"
  cat > "$home/.local/bin/hermes" <<'HERMES'
#!/usr/bin/env bash
echo "$@" >> "$ARGV_LOG"
case "${2:-}" in
  create) printf '%s' "$MOCK_CREATE_JSON" ;;
  show)   printf '%s' "$MOCK_SHOW_JSON" ;;
  *)      printf '%s' '{}' ;;
esac
HERMES
  chmod +x "$home/.local/bin/hermes"
  printf 'Investigate the standing brief and propose if warranted.\nSTEP 0: read your task file first.\n' > "$home/task_body.md"
  echo "$home"
}

run_wrapper() {
  local home=$1 create_json=$2 show_json=$3 run_date=${4:-}
  local rc=0
  # POLL_INTERVAL=1/TIMEOUT=2 bounds the loop if a scenario never reaches terminal
  # (all scenarios below hit terminal on the first poll, so no real waiting occurs).
  HOME="$home" ARGV_LOG="$home/hermes_argv.log" \
    POLL_INTERVAL_SECONDS=1 POLL_TIMEOUT_SECONDS=2 \
    MOCK_CREATE_JSON="$create_json" MOCK_SHOW_JSON="$show_json" RUN_DATE="$run_date" \
    bash "$SCRIPT" "Nightly brief" "$home/task_body.md" claudius "$home/ws" \
      "nightly-research-analyst-2026-07-13" 5m \
    >"$home/stdout.log" 2>"$home/stderr.log" || rc=$?
  echo "$rc"
}

echo "--- scenario 1: date banner injected + task body preserved, normal done (NUC-29) ---"
h1=$(sandbox); today=$(date +%Y-%m-%d)
rc=$(run_wrapper "$h1" '{"id":"t1","task":{"status":"todo"}}' '{"task":{"status":"done"}}')
assert "exits 0 (done)" "[ '$rc' = 0 ]"
assert "create argv carries the TODAY IS <today> banner" "grep -q 'TODAY IS $today' '$h1/hermes_argv.log'"
assert "create argv preserves the original task body (STEP 0 line)" "grep -q 'STEP 0: read your task file first' '$h1/hermes_argv.log'"

echo "--- scenario 2: exported RUN_DATE override is honored (NUC-29) ---"
h2=$(sandbox)
rc=$(run_wrapper "$h2" '{"id":"t1","task":{"status":"todo"}}' '{"task":{"status":"done"}}' '2020-01-01')
assert "exits 0" "[ '$rc' = 0 ]"
assert "banner uses the exported RUN_DATE, not today" "grep -q 'TODAY IS 2020-01-01' '$h2/hermes_argv.log'"
assert "proposal-name hint uses RUN_DATE" "grep -q '_inbox/agents/2020-01-01_' '$h2/hermes_argv.log'"

echo "--- scenario 3: idempotent hit via terminal create JSON -> exit 3 DEDUP (NUC-38) ---"
h3=$(sandbox)
rc=$(run_wrapper "$h3" '{"id":"t1","task":{"status":"done"}}' '{"task":{"status":"done"}}')
assert "exits 3 (DEDUP_EXIT)" "[ '$rc' = 3 ]"
assert "stderr reports idempotent hit / DEDUP" "grep -q 'idempotent hit, DEDUP' '$h3/stderr.log'"

echo "--- scenario 4: create JSON lacks status, immediate show terminal -> exit 3 (NUC-38) ---"
h4=$(sandbox)
rc=$(run_wrapper "$h4" '{"id":"t1"}' '{"task":{"status":"done"}}')
assert "exits 3 (DEDUP via show fallback)" "[ '$rc' = 3 ]"

echo "--- scenario 5: fresh card that later blocks is a benign decline (exit 0), not DEDUP ---"
h5=$(sandbox)
rc=$(run_wrapper "$h5" '{"id":"t1","task":{"status":"todo"}}' '{"task":{"status":"blocked"}}')
assert "exits 0 (benign decline, not dedup exit 3)" "[ '$rc' = 0 ]"
assert "not flagged as an idempotent hit" "! grep -q 'idempotent hit' '$h5/stderr.log'"

exit $fail
