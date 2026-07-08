#!/usr/bin/env bash
# Smoke test for bin/agent_propose.sh (NUC-08b) — mocked runtime, no network calls,
# no real API key, no real secrets/logs touched. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/agent_propose.sh"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then
    echo "  ok: $desc"
  else
    echo "  FAIL: $desc"
    fail=1
  fi
}

# ── Sandbox: isolate $HOME so the script never touches real secrets/logs/worktree ──
sandbox() {
  local home; home=$(mktemp -d)
  mkdir -p "$home/.config/agent-workforce" "$home/agent-workforce/logs" "$home/agent-worktrees"

  local mock_hermes="$home/mock_hermes.sh"
  cat > "$mock_hermes" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$home/hermes_argv.log"
[ "\${MOCK_WRITE_FILE:-}" = "1" ] && touch "$home/agent-worktrees/inbox/out_of_bounds.txt"
exit "\${MOCK_EXIT_CODE:-0}"
EOF
  chmod +x "$mock_hermes"

  cat > "$home/.config/agent-workforce/secrets.env" <<EOF
OPENROUTER_API_KEY=test-key-not-real
AGENT_RUNTIME_CMD=$mock_hermes
AGENT_MAX_ITERATIONS=8
AGENT_TIMEOUT_MINUTES=1
LLM_MODEL_BUSINESS=test-model
EOF

  local worktree="$home/agent-worktrees/inbox"
  git init -q "$worktree"
  git -C "$worktree" config user.email test@example.com
  git -C "$worktree" config user.name test
  mkdir -p "$worktree/_inbox/agents"
  touch "$worktree/_inbox/agents/.gitkeep"
  git -C "$worktree" add -A
  git -C "$worktree" commit -q -m init
  git -C "$worktree" checkout -q -b agents/inbox

  echo "$home"
}

run_scenario() {
  local home=$1 exit_code=$2 write_violation=$3
  local rc=0
  HOME="$home" AGENT_PROPOSE_LOCK="$home/lock" AGENT_RETRY_BASE_SECONDS=0 \
    MOCK_EXIT_CODE="$exit_code" MOCK_WRITE_FILE="$write_violation" \
    bash "$SCRIPT" >"$home/stdout.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- scenario 1: success, no proposal ---"
h1=$(sandbox)
rc=$(run_scenario "$h1" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs no-proposal" "grep -q 'OK: run completed, agent produced no proposal' '$h1/agent-workforce/logs/agent_propose.log'"
assert "cost.log written with outcome=OK" "grep -q 'outcome=OK' '$h1/agent-workforce/logs/cost.log'"
assert "no phantom --max-turns flag passed to runtime (NUC-16: hermes -z has none)" "! grep -q -- '--max-turns' '$h1/hermes_argv.log'"

echo "--- scenario 2: all retries fail ---"
h2=$(sandbox)
rc=$(run_scenario "$h2" 1 0)
assert "exits 1" "[ '$rc' = 1 ]"
assert "logs FAIL after exhausting retries" "grep -q 'FAIL: runtime failed after 3 attempts' '$h2/agent-workforce/logs/agent_propose.log'"
assert "cost.log written even on failure (outcome=FAIL)" "grep -q 'outcome=FAIL' '$h2/agent-workforce/logs/cost.log'"

echo "--- scenario 3: write-boundary violation ---"
h3=$(sandbox)
rc=$(run_scenario "$h3" 0 1)
assert "exits 1" "[ '$rc' = 1 ]"
assert "logs FATAL boundary violation" "grep -q 'FATAL: agent touched files outside' '$h3/agent-workforce/logs/agent_propose.log'"
assert "cost.log written on violation (outcome=VIOLATION)" "grep -q 'outcome=VIOLATION' '$h3/agent-workforce/logs/cost.log'"
assert "violating file discarded from worktree" "[ ! -e '$h3/agent-worktrees/inbox/out_of_bounds.txt' ]"

exit $fail
