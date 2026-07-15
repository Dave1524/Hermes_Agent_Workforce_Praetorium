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

  # NUC-27: network-free stub for key_usage()'s read-only GET /api/v1/key. Emulates
  # the OpenRouter response shape so the run exercises the real parse + delta math
  # with NO network call (this smoke test is offline by contract). Prepended to PATH
  # in run_scenario so the runner's `curl` resolves here.
  mkdir -p "$home/mockbin"
  # Offline stub for BOTH probes the runner may make: the NUC-27 /key spend GET and the
  # NUC-31 qmd /health GET. Branch on the URL: a /health request exits MOCK_QMD_HEALTH_RC
  # (0=up, nonzero=down) so scenarios can drive the health gate; everything else returns
  # the OpenRouter /key JSON. No network either way.
  cat > "$home/mockbin/curl" <<'CURL'
#!/usr/bin/env bash
for a in "$@"; do
  case "$a" in
    *"/health"*) exit "${MOCK_QMD_HEALTH_RC:-0}" ;;
  esac
done
printf '%s' '{"data":{"usage":1.5,"limit":25,"limit_remaining":23.5}}'
CURL
  chmod +x "$home/mockbin/curl"

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
  # NUC-31: default both health policies to OFF so the existing scenarios stay purely
  # about runtime/proposal logic (and never shell out to the host's real ss/curl). The
  # daemon-gate scenarios pass explicit policies + a qmd health rc.
  local qmd_policy=${6:-off} brave_policy=${7:-off} qmd_rc=${8:-0}
  local rc=0
  HOME="$home" PATH="$home/mockbin:$PATH" AGENT_PROPOSE_LOCK="$home/lock" AGENT_RETRY_BASE_SECONDS=0 \
    QMD_HEALTH_POLICY="$qmd_policy" BRAVE_HEALTH_POLICY="$brave_policy" MOCK_QMD_HEALTH_RC="$qmd_rc" \
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
assert "cost.log schema=3 (NUC-27 real-spend record)" "grep -q 'schema=3' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log cost_src=openrouter-key-api (NUC-27)" "grep -q 'cost_src=openrouter-key-api' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log usage_before parsed from /key probe (NUC-27)" "grep -q 'usage_before=1.5' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log cost_usd_delta = after-before (NUC-27)" "grep -q 'cost_usd_delta=0.000000' '$h1/agent-workforce/logs/cost.log'"
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

echo "--- scenario 7: preflight BLOCKED — secrets.env missing (NUC-37) ---"
h7=$(sandbox); rm -f "$h7/.config/agent-workforce/secrets.env"
rc=$(run_scenario "$h7" 0 0)
assert "exits 0 (blocked is not a crash)" "[ '$rc' = 0 ]"
assert "logs BLOCKED secrets.env missing" "grep -q 'BLOCKED: secrets.env missing' '$h7/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=BLOCKED (NUC-37)" "grep -q 'outcome=BLOCKED' '$h7/agent-workforce/logs/cost.log'"
assert "cost.log profile=unknown (secrets never sourced)" "grep -q 'profile=unknown' '$h7/agent-workforce/logs/cost.log'"
assert "cost.log usage_before=unknown (no network probe on early block)" "grep -q 'usage_before=unknown' '$h7/agent-workforce/logs/cost.log'"
assert "agent never launched (no hermes argv)" "[ ! -s '$h7/hermes_argv.log' ]"

echo "--- scenario 8: qmd down + policy=block -> BLOCKED, agent not launched (NUC-31/37) ---"
h8=$(sandbox)
rc=$(run_scenario "$h8" 0 0 0 0 block off 7)   # qmd_rc=7 => /health probe reports 'down'
assert "exits 0 (blocked is not a crash)" "[ '$rc' = 0 ]"
assert "logs BLOCKED qmd daemon down" "grep -q 'BLOCKED: qmd MCP daemon down' '$h8/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=BLOCKED" "grep -q 'outcome=BLOCKED' '$h8/agent-workforce/logs/cost.log'"
assert "cost.log profile=claudius (gate runs after profile resolution, NUC-31)" "grep -q 'profile=claudius' '$h8/agent-workforce/logs/cost.log'"
assert "agent never launched (no hermes argv)" "[ ! -s '$h8/hermes_argv.log' ]"

echo "--- scenario 9: qmd down + policy=warn -> WARN, run proceeds (NUC-31) ---"
h9=$(sandbox)
rc=$(run_scenario "$h9" 0 0 0 0 warn off 7)
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs WARN qmd (policy=warn)" "grep -q 'WARN: qmd MCP daemon down (policy=warn)' '$h9/agent-workforce/logs/agent_propose.log'"
assert "run proceeded to the agent (hermes argv present)" "[ -s '$h9/hermes_argv.log' ]"
assert "cost.log outcome=NOPROPOSAL (not BLOCKED)" "grep -q 'outcome=NOPROPOSAL' '$h9/agent-workforce/logs/cost.log'"
assert "cost.log has no BLOCKED record" "! grep -q 'outcome=BLOCKED' '$h9/agent-workforce/logs/cost.log'"

echo "--- scenario 10: DEDUP — runtime exits 3 (idempotent kanban hit) (NUC-38) ---"
h10=$(sandbox)
rc=$(run_scenario "$h10" 3 0)   # mock runtime exits 3 == DEDUP_EXIT
assert "exits 0 (dedup is clean, not a failure)" "[ '$rc' = 0 ]"
assert "logs DEDUP idempotent hit" "grep -q 'DEDUP: kanban idempotent hit' '$h10/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=DEDUP" "grep -q 'outcome=DEDUP' '$h10/agent-workforce/logs/cost.log'"
assert "cost.log attempts=1 (not retried)" "grep -q 'attempts=1' '$h10/agent-workforce/logs/cost.log'"
assert "cost.log memory=na (dedup skips the memory block)" "grep -q 'memory=na' '$h10/agent-workforce/logs/cost.log'"
assert "no runner memory fallback written" "! grep -q 'wrote runner fallback entry' '$h10/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 11: kanban path de-stacks outer retry to 1 attempt (NUC-38) ---"
h11=$(sandbox)
# A kanban-NAMED runtime that always fails: run_cmd contains 'kanban_run_and_wait.sh',
# so max_attempts must collapse to 1 (hermes already retries internally — no 3x outer).
kmock="$h11/kanban_run_and_wait.sh"
printf '#!/usr/bin/env bash\nexit 1\n' > "$kmock"; chmod +x "$kmock"
sed -i "s#^AGENT_RUNTIME_CMD=.*#AGENT_RUNTIME_CMD=$kmock#" "$h11/.config/agent-workforce/secrets.env"
rc=$(run_scenario "$h11" 0 0)
assert "exits 1 (FAIL)" "[ '$rc' = 1 ]"
assert "FAIL after exactly 1 attempt (kanban de-stack)" "grep -q 'FAIL: runtime failed after 1 attempts' '$h11/agent-workforce/logs/agent_propose.log'"
assert "cost.log attempts=1" "grep -q 'attempts=1' '$h11/agent-workforce/logs/cost.log'"
assert "NOT the old 3-attempt behavior" "! grep -q 'after 3 attempts' '$h11/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 12: AGENT_RUN_MODE=ops success (NUC-36) ---"
h12=$(sandbox)
# Ops mode: no inbox required; mock writes outside inbox must NOT trip write-boundary.
rm -rf "$h12/agent-worktrees/inbox"
printf '\nAGENT_RUN_MODE=ops\nAGENT_TASK_SLUG=overnight-morning-report\n' \
  >> "$h12/.config/agent-workforce/secrets.env"
# Re-point mock to also touch a non-inbox path (would be VIOLATION in proposal mode).
cat > "$h12/mock_hermes.sh" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$h12/hermes_argv.log"
mkdir -p "$h12/logs/overnight"
echo report > "$h12/logs/overnight/morning-report-test.md"
exit 0
EOF
chmod +x "$h12/mock_hermes.sh"
rc=$(run_scenario "$h12" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs ops run completed" "grep -q 'OK: ops run completed' '$h12/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=OPS (ops vocab)" "grep -q 'outcome=OPS' '$h12/agent-workforce/logs/cost.log'"
assert "cost.log task=overnight-morning-report" "grep -q 'task=overnight-morning-report' '$h12/agent-workforce/logs/cost.log'"
assert "cost.log memory=na (ops skips memory)" "grep -q 'memory=na' '$h12/agent-workforce/logs/cost.log'"
assert "ops report file written by runtime" "[ -f '$h12/logs/overnight/morning-report-test.md' ]"
assert "no proposal commit path (no agents/inbox worktree)" "[ ! -d '$h12/agent-worktrees/inbox' ]"

echo "--- scenario 13: AGENT_RUN_MODE=ops still enforces write-boundary only in proposal mode ---"
h13=$(sandbox)
# Default proposal mode + out-of-bounds write still VIOLATION (regression guard).
rc=$(run_scenario "$h13" 0 1)
assert "proposal mode still exits 1 on boundary violation" "[ '$rc' = 1 ]"
assert "proposal mode still logs FATAL boundary" "grep -q 'FATAL: agent touched files outside' '$h13/agent-workforce/logs/agent_propose.log'"

exit $fail
