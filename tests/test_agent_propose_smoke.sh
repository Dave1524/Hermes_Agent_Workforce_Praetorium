#!/usr/bin/env bash
# Smoke test for bin/agent_propose.sh (NUC-08b/16/21/23) — mocked runtime, no network,
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
  # Fake profile config so the runner reads the PROFILE model (NUC-23), not LLM_MODEL_BUSINESS.
  mkdir -p "$home/.hermes/profiles/claudius"
  printf 'model:\n  name: test/model-x\n' > "$home/.hermes/profiles/claudius/config.yaml"

  local mock_hermes="$home/mock_hermes.sh"
  cat > "$mock_hermes" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$home/hermes_argv.log"
[ "\${MOCK_WRITE_FILE:-}" = "1" ] && touch "$home/agent-worktrees/inbox/out_of_bounds.txt"
[ "\${MOCK_WRITE_PROPOSAL:-}" = "1" ] && { mkdir -p "$home/agent-worktrees/inbox/_inbox/agents"; touch "$home/agent-worktrees/inbox/_inbox/agents/2026-08-08_test-slug.md"; }
[ "\${MOCK_WRITE_METRICS:-}" = "1" ] && { mkdir -p "$home/agent-worktrees/inbox/_inbox/agents/_metrics"; echo digest > "$home/agent-worktrees/inbox/_inbox/agents/_metrics/scorecard.md"; }
exit "\${MOCK_EXIT_CODE:-0}"
EOF
  chmod +x "$mock_hermes"

  cat > "$home/.config/agent-workforce/secrets.env" <<EOF
OPENROUTER_API_KEY=test-key-not-real
AGENT_RUNTIME_CMD=$mock_hermes
AGENT_PROFILE=claudius
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
  # Bare origin so the proposal push path (scenario 4) works.
  git init -q --bare "$home/origin.git"
  git -C "$worktree" remote add origin "$home/origin.git"

  echo "$home"
}

run_scenario() {
  local home=$1 exit_code=$2 write_violation=$3 write_proposal=${4:-0} write_metrics=${5:-0}
  local rc=0
  HOME="$home" AGENT_PROPOSE_LOCK="$home/lock" AGENT_RETRY_BASE_SECONDS=0 \
    MOCK_EXIT_CODE="$exit_code" MOCK_WRITE_FILE="$write_violation" MOCK_WRITE_PROPOSAL="$write_proposal" \
    MOCK_WRITE_METRICS="$write_metrics" \
    bash "$SCRIPT" >"$home/stdout.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- scenario 1: success, no proposal ---"
h1=$(sandbox)
rc=$(run_scenario "$h1" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs no-proposal" "grep -q 'OK: run completed, agent produced no proposal' '$h1/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=NOPROPOSAL (NUC-23 vocab)" "grep -q 'outcome=NOPROPOSAL' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log model=test/model-x (profile model, NUC-23 fix)" "grep -q 'model=test/model-x' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log NOT model=test-model (not LLM_MODEL_BUSINESS)" "! grep -q 'model=test-model' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log profile=claudius" "grep -q 'profile=claudius' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log schema=2" "grep -q 'schema=2' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log cost_src=openrouter-dashboard" "grep -q 'cost_src=openrouter-dashboard' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log proposal=none" "grep -q 'proposal=none' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log memory=no-store (NUC-21 glue ran)" "grep -q 'memory=no-store' '$h1/agent-workforce/logs/cost.log'"
assert "logs no-store when profile memory dir absent" "grep -q 'MEMORY: no per-profile store' '$h1/agent-workforce/logs/agent_propose.log'"
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

echo "--- scenario 4: success WITH proposal (push path) ---"
h4=$(sandbox)
rc=$(run_scenario "$h4" 0 0 1)
assert "exits 0" "[ '$rc' = 0 ]"
assert "cost.log outcome=PROPOSAL" "grep -q 'outcome=PROPOSAL' '$h4/agent-workforce/logs/cost.log'"
assert "cost.log proposal=test-slug (slug extracted)" "grep -q 'proposal=test-slug' '$h4/agent-workforce/logs/cost.log'"
assert "logs proposal pushed" "grep -q 'OK: proposal pushed' '$h4/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 5: metrics-only change is NOT a proposal (NUC-23 _metrics exclusion) ---"
h5=$(sandbox)
rc=$(run_scenario "$h5" 0 0 0 1)   # write_metrics=1, no proposal, no violation
assert "exits 0" "[ '$rc' = 0 ]"
assert "metrics change classified NOPROPOSAL, not PROPOSAL" "grep -q 'outcome=NOPROPOSAL' '$h5/agent-workforce/logs/cost.log'"
assert "NOT outcome=PROPOSAL" "! grep -q 'outcome=PROPOSAL' '$h5/agent-workforce/logs/cost.log'"
assert "logs no-proposal (metrics not swept as proposal)" "grep -q 'OK: run completed, agent produced no proposal' '$h5/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 6: runner memory fallback when the agent didn't self-record (NUC-21) ---"
h6=$(sandbox)
mkdir -p "$h6/.hermes/profiles/claudius/memories"   # store dir exists, mock writes no memory
rc=$(run_scenario "$h6" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "cost.log memory=fallback (runner backstop wrote it)" "grep -q 'memory=fallback' '$h6/agent-workforce/logs/cost.log'"
assert "runner logged fallback write" "grep -q 'wrote runner fallback entry' '$h6/agent-workforce/logs/agent_propose.log'"
assert "MEMORY.md created with an entry" "[ -s '$h6/.hermes/profiles/claudius/memories/MEMORY.md' ]"
assert "fallback entry carries a run tag" "grep -q '\[run:' '$h6/.hermes/profiles/claudius/memories/MEMORY.md'"

exit $fail
