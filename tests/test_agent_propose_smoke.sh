#!/usr/bin/env bash
# Smoke test for bin/agent_propose.sh (NUC-08b/16/21/23) — mocked runtime, no network,
# no real API key, no real secrets/logs touched. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/agent_propose.sh"

fail=0
# See CLAUDE.md § Verification: a condition must not run under pipefail, or an early-exiting
# reader (grep -q) SIGPIPEs its producer and turns a satisfied assertion red.
assert() {
  local desc=$1 cond=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$cond"; then
    echo "  ok: $desc"
  else
    echo "  FAIL: $desc"
    fail=1
  fi
  eval "$pf"
}

assert "a found pattern is never reported as a failure" "yes | grep -q y"

# ── Sandbox: isolate $HOME so the script never touches real secrets/logs/worktree ──
sandbox() {
  local home; home=$(mktemp -d)
  mkdir -p "$home/.config/agent-workforce" "$home/agent-workforce/logs" "$home/agent-worktrees"
  # No ~/.hermes in the sandbox on purpose (T6.1): the runner must neither read a profile
  # config for the model nor create an episodic store; scenario 1 asserts the path stays absent.

  local mock_hermes="$home/mock_hermes.sh"
  cat > "$mock_hermes" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$home/hermes_argv.log"
# T3.3: the runner exports one AGENT_SESSION_ID per attempt; a Claude runner passes it as
# --session-id and the transcript lands at ~/.claude/projects/<slug>/<id>.jsonl. Record what
# this attempt saw, and on request write a transcript there in the real record shapes.
echo "\${AGENT_SESSION_ID:-unset}" >> "$home/session_ids.log"
echo "GRAFT_DIR=\${GRAFT_DIR:-unset} GRAFT_NO_SEED=\${GRAFT_NO_SEED:-unset} GRAFT_NO_REFRESH=\${GRAFT_NO_REFRESH:-unset} GRAFT_NO_GITIGNORE=\${GRAFT_NO_GITIGNORE:-unset} GRAFT_NO_IGNORE=\${GRAFT_NO_IGNORE:-unset}" >> "$home/graft_env.log"
if [ "\${MOCK_WRITE_TRANSCRIPT:-}" = "1" ]; then
  mkdir -p "$home/.claude/projects/fixture"
  cat > "$home/.claude/projects/fixture/\${AGENT_SESSION_ID}.jsonl" <<'JSONL'
{"type":"attachment","attachment":{"type":"skill_listing","isInitial":true,"skillCount":6,"names":["finish","shared:codex","praetorium-claudius:investment-research","praetorium-claudius:meeting-prep","praetorium-claudius:prospect-research"]},"sessionId":"x","cwd":"/x","timestamp":"2026-09-11T11:40:00.000Z"}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_01","name":"Skill","input":{"skill":"praetorium-claudius:meeting-prep"}}]}}
{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_01","content":"Launching skill: praetorium-claudius:meeting-prep"}]}}
{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_02","name":"Read","input":{"file_path":"/home/dave/vault/08_skills/meeting-prep/SKILL.md"}}]}}
JSONL
fi
[ "\${MOCK_WRITE_FILE:-}" = "1" ] && touch "$home/agent-worktrees/inbox/out_of_bounds.txt"
[ "\${MOCK_WRITE_PROPOSAL:-}" = "1" ] && { mkdir -p "$home/agent-worktrees/inbox/_inbox/agents"; touch "$home/agent-worktrees/inbox/_inbox/agents/2026-08-08_test-slug.md"; }
[ "\${MOCK_WRITE_METRICS:-}" = "1" ] && { mkdir -p "$home/agent-worktrees/inbox/_inbox/agents/_metrics"; echo digest > "$home/agent-worktrees/inbox/_inbox/agents/_metrics/scorecard.md"; }
exit "\${MOCK_EXIT_CODE:-0}"
EOF
  chmod +x "$mock_hermes"

  mkdir -p "$home/mockbin"
  # Offline stub for the one probe the runner still makes, the NUC-31 qmd /health GET
  # (prepended to PATH in run_scenario): a /health request exits MOCK_QMD_HEALTH_RC (0=up,
  # nonzero=down) so scenarios can drive the health gate. Any other URL is a regression —
  # the OpenRouter /key spend probe was retired at T6.1 — so it is named on stderr and
  # scenario 1 asserts it never happened.
  cat > "$home/mockbin/curl" <<'CURL'
#!/usr/bin/env bash
for a in "$@"; do
  case "$a" in
    *"/health"*) exit "${MOCK_QMD_HEALTH_RC:-0}" ;;
  esac
done
echo "curl stub: unexpected URL: $*" >&2
exit 0
CURL
  chmod +x "$home/mockbin/curl"

  # Offline stub for brave_healthy()'s `ss -ltn | grep ':8766'`. Default = brave DOWN, so a
  # scenario that leaves BRAVE_HEALTH_POLICY unset exercises the real default (warn) instead
  # of the host's actual socket table. MOCK_BRAVE_UP=1 emits a matching LISTEN line.
  cat > "$home/mockbin/ss" <<'SS'
#!/usr/bin/env bash
[ "${MOCK_BRAVE_UP:-0}" = 1 ] && echo 'LISTEN 0 128 127.0.0.1:8766 0.0.0.0:*'
exit 0
SS
  chmod +x "$home/mockbin/ss"

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

echo "--- scenario 1: success, no proposal (::propose-no-hermes-model) (::propose-cost-delta-unknown) ---"
h1=$(sandbox)
rc=$(run_scenario "$h1" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs no-proposal" "grep -q 'OK: run completed, agent produced no proposal' '$h1/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=NOPROPOSAL (NUC-23 vocab)" "grep -q 'outcome=NOPROPOSAL' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log model=unknown (T6.1: no hermes profile resolves it; the receipt carries the measured model)" "grep -q ' model=unknown ' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log NOT model=test-model (not LLM_MODEL_BUSINESS)" "! grep -q 'model=test-model' '$h1/agent-workforce/logs/cost.log'"
assert "nothing under ~/.hermes was read or created" "[ ! -e '$h1/.hermes' ]"
assert "cost.log profile=claudius" "grep -q 'profile=claudius' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log schema=3 (record shape unchanged)" "grep -q 'schema=3' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log cost_src=openrouter-key-api (key kept, value unknown)" "grep -q 'cost_src=openrouter-key-api' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log usage_before=unknown (T6.1: the shared-key probe is retired)" "grep -q 'usage_before=unknown' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log usage_after=unknown" "grep -q 'usage_after=unknown' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log cost_usd_delta=unknown, never a frozen zero" "grep -q 'cost_usd_delta=unknown' '$h1/agent-workforce/logs/cost.log'"
assert "no 'cost: usage_before=' probe line in the run log" "! grep -q 'cost: usage_before=' '$h1/agent-workforce/logs/agent_propose.log'"
assert "the curl stub saw no /key request" "! grep -q 'unexpected URL' '$h1/stdout.log' '$h1/agent-workforce/logs/agent_propose.log'"
assert "cost.log proposal=none" "grep -q 'proposal=none' '$h1/agent-workforce/logs/cost.log'"
# The graft Claude Code hooks (user scope) write their index and session telemetry into the
# session's cwd — the inbox worktree — unless GRAFT_DIR points elsewhere; the first resumed run
# on 2026-09-15 was discarded by the write boundary for exactly that.
assert "runtime sees GRAFT_DIR outside the inbox worktree" "grep -qE '^GRAFT_DIR=/' '$h1/graft_env.log' && ! grep -q 'GRAFT_DIR=$h1/agent-worktrees' '$h1/graft_env.log'"
assert "runtime sees every graft kill switch on" "grep -q 'GRAFT_NO_SEED=1 GRAFT_NO_REFRESH=1 GRAFT_NO_GITIGNORE=1 GRAFT_NO_IGNORE=1' '$h1/graft_env.log'"
assert "cost.log memory=na (T6.1: the episodic store is retired)" "grep -q 'memory=na' '$h1/agent-workforce/logs/cost.log'"
assert "no MEMORY: line in the run log" "! grep -q 'MEMORY:' '$h1/agent-workforce/logs/agent_propose.log'"
assert "no phantom --max-turns flag passed to runtime (NUC-16: hermes -z has none)" "! grep -q -- '--max-turns' '$h1/hermes_argv.log'"
assert "cost.log skills=unknown (T3.3: sandbox has no transcript)" "grep -q 'skills=unknown' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log skills_offered=unknown" "grep -q 'skills_offered=unknown' '$h1/agent-workforce/logs/cost.log'"
assert "cost.log skills_src=none" "grep -q 'skills_src=none' '$h1/agent-workforce/logs/cost.log'"
assert "the runtime received a session id (uuid)" "grep -qE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' '$h1/session_ids.log'"

echo "--- scenario 2: all retries fail ---"
h2=$(sandbox)
rc=$(run_scenario "$h2" 1 0)
assert "exits 1" "[ '$rc' = 1 ]"
assert "logs FAIL after exhausting retries" "grep -q 'FAIL: runtime failed after 3 attempts' '$h2/agent-workforce/logs/agent_propose.log'"
assert "cost.log written even on failure (outcome=FAIL)" "grep -q 'outcome=FAIL' '$h2/agent-workforce/logs/cost.log'"
assert "three attempts saw three session ids" "[ \"\$(wc -l < '$h2/session_ids.log')\" = 3 ]"
assert "and every id is distinct (a retry gets a fresh session)" "[ \"\$(sort -u '$h2/session_ids.log' | wc -l)\" = 3 ]"
assert "attempt log names the session next to the attempt" "grep -qE 'run attempt 1/3 session=[0-9a-f-]{36}' '$h2/agent-workforce/logs/agent_propose.log'"

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

echo "--- scenario 6: no episodic store, even when one is offered (::propose-no-episodic-store) ---"
h6=$(sandbox)
mkdir -p "$h6/.hermes/profiles/claudius/memories" "$h6/ra"   # a store dir exists; the runner must not write it
rc=$(RA_MEMORY_DIR="$h6/ra" run_scenario "$h6" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "cost.log memory=na (T6.1)" "grep -q 'memory=na' '$h6/agent-workforce/logs/cost.log'"
assert "no MEMORY.md under the offered profile store" "[ ! -e '$h6/.hermes/profiles/claudius/memories/MEMORY.md' ]"
assert "RA_MEMORY_DIR is not honoured" "[ -z \"\$(ls -A '$h6/ra')\" ]"
assert "no runner fallback entry logged" "! grep -q 'fallback entry' '$h6/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 7: preflight BLOCKED — secrets.env missing (NUC-37) ---"
h7=$(sandbox); rm -f "$h7/.config/agent-workforce/secrets.env"
rc=$(run_scenario "$h7" 0 0)
assert "exits 0 (blocked is not a crash)" "[ '$rc' = 0 ]"
assert "logs BLOCKED secrets.env missing" "grep -q 'BLOCKED: secrets.env missing' '$h7/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=BLOCKED (NUC-37)" "grep -q 'outcome=BLOCKED' '$h7/agent-workforce/logs/cost.log'"
assert "cost.log profile=unknown (secrets never sourced)" "grep -q 'profile=unknown' '$h7/agent-workforce/logs/cost.log'"
assert "cost.log usage_before=unknown (no network probe on early block)" "grep -q 'usage_before=unknown' '$h7/agent-workforce/logs/cost.log'"
assert "agent never launched (no hermes argv)" "[ ! -s '$h7/hermes_argv.log' ]"
assert "cost.log skills=unknown on BLOCKED (no attempt, no session)" "grep -q 'skills=unknown skills_offered=unknown skills_src=none' '$h7/agent-workforce/logs/cost.log'"

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

# ── Silent-failure scenarios ────────────────────────────────────────────────
# hermes exits 0 when a provider error becomes the agent's final RESPONSE, so the
# runner used to record OK for a run that produced nothing (observed 2026-07-21:
# HTTP 400 model-ID, and an ollama empty stream). A stale artifact then re-delivers
# downstream for up to 26h. These pin both detectors and the no-false-positive case.
silent_fail_sandbox() {
  local home; home=$(sandbox)
  cat > "$home/mock_hermes.sh" <<EOF
#!/usr/bin/env bash
[ -n "\${MOCK_STDOUT:-}" ] && printf '%s\n' "\${MOCK_STDOUT}"
exit 0
EOF
  chmod +x "$home/mock_hermes.sh"
  echo "$home"
}

run_silent() {
  local home=$1 stdout=$2 verify=${3:-} rc=0
  HOME="$home" PATH="$home/mockbin:$PATH" AGENT_PROPOSE_LOCK="$home/lock" \
    AGENT_RETRY_BASE_SECONDS=0 AGENT_MAX_ATTEMPTS=1 AGENT_RUN_MODE=ops \
    QMD_HEALTH_POLICY=off BRAVE_HEALTH_POLICY=off \
    MOCK_STDOUT="$stdout" AGENT_VERIFY_CMD="$verify" \
    bash "$SCRIPT" >"$home/stdout.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- scenario 14: exit 0 ending on a provider error is FAIL, not OK ---"
h14=$(silent_fail_sandbox)
rc=$(run_silent "$h14" 'API call failed after 3 retries: Provider returned an empty stream with no finish_reason')
assert "exits 1 despite runtime exit 0" "[ '$rc' = 1 ]"
assert "logs SILENT-FAIL" "grep -q 'SILENT-FAIL: exit 0 but the run ended on a provider error' '$h14/agent-workforce/logs/agent_propose.log'"
assert "does NOT log ops OK" "! grep -q 'OK: ops run completed' '$h14/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=FAIL" "grep -q 'outcome=FAIL' '$h14/agent-workforce/logs/cost.log'"

echo "--- scenario 15: HTTP 4xx as final response is FAIL ---"
h15=$(silent_fail_sandbox)
rc=$(run_silent "$h15" 'HTTP 400: local-big is not a valid model ID')
assert "exits 1" "[ '$rc' = 1 ]"
assert "logs SILENT-FAIL" "grep -q 'SILENT-FAIL' '$h15/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 16: a report QUOTING a provider error is not a false positive ---"
h16=$(silent_fail_sandbox)
# The error string appears in the body (as an overnight report summarising a journal
# would), but the run ends on real content — tail-only scanning must let this pass.
rc=$(run_silent "$h16" 'HTTP 400: local-big is not a valid model ID
line2
line3
line4
line5
line6
## Overnight Report — all nominal')
assert "exits 0 (no false positive)" "[ '$rc' = 0 ]"
assert "logs ops OK" "grep -q 'OK: ops run completed' '$h16/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 17: AGENT_VERIFY_CMD gates the artifact ---"
h17=$(silent_fail_sandbox)
rc=$(run_silent "$h17" 'looks fine to me' 'test -f /nonexistent/morning-report.md')
assert "exits 1 when artifact missing" "[ '$rc' = 1 ]"
assert "logs artifact SILENT-FAIL" "grep -q 'SILENT-FAIL: exit 0 but AGENT_VERIFY_CMD found no artifact' '$h17/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 18: AGENT_VERIFY_CMD passing leaves the run OK ---"
h18=$(silent_fail_sandbox)
rc=$(run_silent "$h18" 'looks fine to me' 'true')
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs ops OK" "grep -q 'OK: ops run completed' '$h18/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 19: AGENT_RUN_STARTED_AT lets verify assert artifact freshness ---"
# The live morning-report job uses -newermt "@$AGENT_RUN_STARTED_AT"; pin that the
# var is exported and usable, so a PRE-EXISTING (stale) artifact does not pass.
h19=$(silent_fail_sandbox)
mkdir -p "$h19/logs/overnight"
touch -d '2 hours ago' "$h19/logs/overnight/morning-report-stale.md"
rc=$(run_silent "$h19" 'done' 'test -n "$AGENT_RUN_STARTED_AT" && find "$HOME/logs/overnight" -name "morning-report-*.md" -newermt "@$AGENT_RUN_STARTED_AT" | grep -q .')
assert "stale artifact does NOT satisfy verify" "[ '$rc' = 1 ]"
assert "logs artifact SILENT-FAIL" "grep -q 'AGENT_VERIFY_CMD found no artifact' '$h19/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 20: a freshly written artifact DOES satisfy verify ---"
h20=$(silent_fail_sandbox)
cat > "$h20/mock_hermes.sh" <<EOF
#!/usr/bin/env bash
mkdir -p "$h20/logs/overnight"
touch "$h20/logs/overnight/morning-report-fresh.md"
echo ok
exit 0
EOF
chmod +x "$h20/mock_hermes.sh"
rc=$(run_silent "$h20" '' 'find "$HOME/logs/overnight" -name "morning-report-*.md" -newermt "@$AGENT_RUN_STARTED_AT" | grep -q .')
assert "fresh artifact passes verify" "[ '$rc' = 0 ]"
assert "logs ops OK" "grep -q 'OK: ops run completed' '$h20/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 21: CRASHED — runtime exits 4 (crash-parked kanban card) (NUC-44) ---"
# The 2026-08-12 outage: 20 nights of crashed hermes runs recorded as outcome=NOPROPOSAL,
# which reads identically to "the agent had nothing to say". A crash gets its own vocab.
h21=$(sandbox)
rc=$(run_scenario "$h21" 4 0)   # mock runtime exits 4 == CRASH_EXIT
assert "exits 1 (a crash is a failure, not a decline)" "[ '$rc' = 1 ]"
assert "cost.log outcome=CRASHED" "grep -q 'outcome=CRASHED' '$h21/agent-workforce/logs/cost.log'"
assert "cost.log is NOT outcome=NOPROPOSAL (the masked-failure bug)" "! grep -q 'outcome=NOPROPOSAL' '$h21/agent-workforce/logs/cost.log'"
assert "cost.log is NOT a generic outcome=FAIL" "! grep -q 'outcome=FAIL' '$h21/agent-workforce/logs/cost.log'"
assert "logs CRASHED with the underlying cause named" "grep -q 'CRASHED: runtime reported a crashed run' '$h21/agent-workforce/logs/agent_propose.log'"
assert "cost.log attempts=1 (hermes already retried; no outer re-run)" "grep -q 'attempts=1' '$h21/agent-workforce/logs/cost.log'"

echo "--- scenario 22: an ops-mode crash is CRASHED too, and never OPS (NUC-44) ---"
h22=$(sandbox)
printf '\nAGENT_RUN_MODE=ops\nAGENT_TASK_SLUG=augustus-content\n' \
  >> "$h22/.config/agent-workforce/secrets.env"
rc=$(run_scenario "$h22" 4 0)
assert "exits 1" "[ '$rc' = 1 ]"
assert "cost.log outcome=CRASHED" "grep -q 'outcome=CRASHED' '$h22/agent-workforce/logs/cost.log'"
assert "cost.log is NOT outcome=OPS" "! grep -q 'outcome=OPS' '$h22/agent-workforce/logs/cost.log'"
assert "cost.log task=augustus-content (the crash is attributable)" "grep -q 'task=augustus-content' '$h22/agent-workforce/logs/cost.log'"

# ── F5: per-job MCP opt-out (AGENT_MCP_DEPS) ────────────────────────────────
# Eight of the eleven runners exec with `--strict-mcp-config --mcp-config '{"mcpServers":{}}'`
# and reach no MCP daemon at all, so probing qmd/brave for them logged a WARN naming a
# dependency the job does not have. Scenario 24 pins the opt-out; scenario 23 is the one that
# matters more — it pins that a job which does NOT opt out still gets the `warn` default, so
# this change can neither switch the probe off fleet-wide nor make it fail closed.
run_mcp_deps() {
  local home=$1 overrides=${2:-} rc=0 ov=""
  if [ -n "$overrides" ]; then
    ov="$home/job.env"
    printf '%s\n' "$overrides" > "$ov"
  fi
  # Deliberately does NOT preset QMD_HEALTH_POLICY/BRAVE_HEALTH_POLICY, unlike run_scenario:
  # these scenarios are about which DEFAULT the script picks. Both daemons are mocked down,
  # and AGENT_JOB_OVERRIDES is the real supply path a job would use (NUC-24).
  HOME="$home" PATH="$home/mockbin:$PATH" AGENT_PROPOSE_LOCK="$home/lock" \
    AGENT_RETRY_BASE_SECONDS=0 AGENT_JOB_OVERRIDES="$ov" MOCK_QMD_HEALTH_RC=7 \
    bash "$SCRIPT" >"$home/stdout.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- scenario 23: no AGENT_MCP_DEPS -> both probes still run at the warn default ---"
h23=$(sandbox)
rc=$(run_mcp_deps "$h23")
assert "exits 0 (warn never blocks)" "[ '$rc' = 0 ]"
assert "qmd WARN still fires for a job that did not opt out" "grep -q 'WARN: qmd MCP daemon down (policy=warn)' '$h23/agent-workforce/logs/agent_propose.log'"
assert "brave WARN still fires (default is warn, not off)" "grep -q 'WARN: brave MCP endpoint down (policy=warn)' '$h23/agent-workforce/logs/agent_propose.log'"
assert "default is NOT block (no BLOCKED record)" "! grep -q 'outcome=BLOCKED' '$h23/agent-workforce/logs/cost.log'"
assert "run proceeded to the agent" "[ -s '$h23/hermes_argv.log' ]"

echo "--- scenario 24: AGENT_MCP_DEPS=none -> both probes skipped, run still proceeds ---"
h24=$(sandbox)
rc=$(run_mcp_deps "$h24" 'AGENT_MCP_DEPS=none')
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs the skip, naming why" "grep -q 'MCP probes: skipped' '$h24/agent-workforce/logs/agent_propose.log'"
assert "no qmd WARN (the misleading line is gone)" "! grep -q 'WARN: qmd MCP daemon down' '$h24/agent-workforce/logs/agent_propose.log'"
assert "no brave WARN" "! grep -q 'WARN: brave MCP endpoint down' '$h24/agent-workforce/logs/agent_propose.log'"
assert "opting out never blocks (no BLOCKED record)" "! grep -q 'outcome=BLOCKED' '$h24/agent-workforce/logs/cost.log'"
assert "run reached the agent unchanged" "[ -s '$h24/hermes_argv.log' ]"
assert "cost.log outcome=NOPROPOSAL (same outcome as scenario 23)" "grep -q 'outcome=NOPROPOSAL' '$h24/agent-workforce/logs/cost.log'"

echo "--- scenario 25: an explicit policy still wins over AGENT_MCP_DEPS=none ---"
# The opt-out supplies a DEFAULT only. If it could override, adding AGENT_MCP_DEPS=none to a
# job env would silently disarm a block someone set deliberately — a fail-open regression.
h25=$(sandbox)
rc=$(run_mcp_deps "$h25" 'AGENT_MCP_DEPS=none
QMD_HEALTH_POLICY=block')
assert "exits 0 (blocked is not a crash)" "[ '$rc' = 0 ]"
assert "explicit block still BLOCKS" "grep -q 'BLOCKED: qmd MCP daemon down' '$h25/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=BLOCKED" "grep -q 'outcome=BLOCKED' '$h25/agent-workforce/logs/cost.log'"
assert "agent never launched" "[ ! -s '$h25/hermes_argv.log' ]"

echo "--- scenario 26: an unrecognised AGENT_MCP_DEPS probes as normal, and says so ---"
# Fail OPEN on a typo: 'none' is the only value that skips. A misspelling must not silently
# opt a job out of a gate it still depends on.
h26=$(sandbox)
rc=$(run_mcp_deps "$h26" 'AGENT_MCP_DEPS=nonw')
assert "exits 0" "[ '$rc' = 0 ]"
assert "logs the unrecognised value" "grep -q 'AGENT_MCP_DEPS=.nonw. unrecognised' '$h26/agent-workforce/logs/agent_propose.log'"
assert "probes ran anyway (qmd WARN present)" "grep -q 'WARN: qmd MCP daemon down' '$h26/agent-workforce/logs/agent_propose.log'"
assert "did NOT silently skip" "! grep -q 'MCP probes: skipped' '$h26/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 27: brave_healthy reports UP without SIGPIPEing ss under pipefail ---"
# CLAUDE.md § Verification: `ss -ltn | grep -q ':8766'` returns 141 when grep exits first,
# reporting the daemon DOWN while it is up. Pin the fixed form against a chatty socket table.
h27=$(sandbox)
cat > "$h27/mockbin/ss" <<'SS'
#!/usr/bin/env bash
echo 'LISTEN 0 128 127.0.0.1:8766 0.0.0.0:*'
for i in $(seq 1 20000); do echo "LISTEN 0 128 127.0.0.1:$((9000 + i % 900)) 0.0.0.0:*"; done
exit 0
SS
chmod +x "$h27/mockbin/ss"
rc=$(run_mcp_deps "$h27")
assert "exits 0" "[ '$rc' = 0 ]"
assert "brave reported UP (no false 'down' from SIGPIPE)" "! grep -q 'brave MCP endpoint down' '$h27/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 28: transcript found by session id -> pointer-skill telemetry in cost.log (T3.3) ---"
# The mock writes a transcript at ~/.claude/projects/<slug>/<AGENT_SESSION_ID>.jsonl in the real
# record shapes; log_cost must find it by id (never mtime), run the sibling extractor, and record
# skills = invoked ∪ read, skills_offered from the listing, skills_src=transcript.
h28=$(sandbox)
rc=$(MOCK_WRITE_TRANSCRIPT=1 run_scenario "$h28" 0 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "one session id, a valid uuid" "[ \"\$(grep -cE '^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$' '$h28/session_ids.log')\" = 1 ]"
assert "the transcript was written under that id" "[ -f \"$h28/.claude/projects/fixture/\$(cat '$h28/session_ids.log').jsonl\" ]"
assert "cost.log skills=meeting-prep (invoked ∪ read)" "grep -q ' skills=meeting-prep ' '$h28/agent-workforce/logs/cost.log'"
assert "cost.log skills_offered=the three pointers, sorted" "grep -q 'skills_offered=investment-research,meeting-prep,prospect-research' '$h28/agent-workforce/logs/cost.log'"
assert "cost.log skills_src=transcript" "grep -q 'skills_src=transcript' '$h28/agent-workforce/logs/cost.log'"
assert "the runner logged what it found" "grep -q 'skills: offered=investment-research,meeting-prep,prospect-research invoked=meeting-prep read=meeting-prep src=transcript' '$h28/agent-workforce/logs/agent_propose.log'"
assert "schema stays 3 (parser is key-based)" "grep -q 'schema=3' '$h28/agent-workforce/logs/cost.log'"
assert "the three keys are on the same record as the outcome" "grep 'outcome=NOPROPOSAL' '$h28/agent-workforce/logs/cost.log' | grep -q 'skills_src=transcript'"

echo "--- scenario 29: an extractor failure is fail-soft — unknown recorded, run outcome untouched (T3.3) ---"
h29=$(sandbox)
# A transcript that exists but is not UTF-8 makes the extractor exit 1 (it skips unparseable
# JSON lines, not undecodable bytes); the run must still record its real outcome with the
# telemetry keys reading unknown/unknown/none.
cat > "$h29/mock_hermes.sh" <<EOF
#!/usr/bin/env bash
echo "\${AGENT_SESSION_ID:-unset}" >> "$h29/session_ids.log"
mkdir -p "$h29/.claude/projects/fixture"
printf '\xff\xfe not utf-8\n' > "$h29/.claude/projects/fixture/\${AGENT_SESSION_ID}.jsonl"
exit 0
EOF
chmod +x "$h29/mock_hermes.sh"
rc=$(run_scenario "$h29" 0 0)
assert "exits 0 (telemetry never fails a run)" "[ '$rc' = 0 ]"
assert "cost.log outcome=NOPROPOSAL still recorded" "grep -q 'outcome=NOPROPOSAL' '$h29/agent-workforce/logs/cost.log'"
assert "cost.log telemetry keys read unknown/unknown/none" "grep -q 'skills=unknown skills_offered=unknown skills_src=none' '$h29/agent-workforce/logs/cost.log'"
assert "the failure is logged with a reason" "grep -q 'skills: telemetry failed' '$h29/agent-workforce/logs/agent_propose.log'"

# ── T5.2: one receipt on every exit path, and the receipt can never change the exit code ──
# CONTRACT_EXEC points propose_receipt.py at a recording stub, so each scenario asserts the
# executor argv the adapter built (the outcome map) without a manifest or a contract. One
# scenario runs the real executor over T5.1's fixture manifest so the receipt on disk is
# proven to validate — the producer's own suite owns that assertion (criterion 11).
make_receipt_stub() {
  local home=$1
  cat > "$home/stub_exec.py" <<'PY'
#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_OUT"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
print("contract_exec: stub")
sys.exit(int(os.environ.get("STUB_RC", "0")))
PY
  chmod +x "$home/stub_exec.py"
  echo "$home/stub_exec.py"
}
run_receipt_scenario() {
  local home=$1 exit_code=$2 write_proposal=${3:-0} write_violation=${4:-0} exec_bin=${5:-} rc=0
  [ -n "$exec_bin" ] || exec_bin=$(make_receipt_stub "$home")
  HOME="$home" PATH="$home/mockbin:$PATH" AGENT_PROPOSE_LOCK="$home/lock" AGENT_RETRY_BASE_SECONDS=0 \
    QMD_HEALTH_POLICY=off BRAVE_HEALTH_POLICY=off \
    DELIVERY_JOB=knowledge-digest.service INVOCATION_ID=inv-smoke \
    CONTRACT_EXEC="$exec_bin" STUB_OUT="$home/stub.jsonl" CONTROL_ROOM_RECEIPT_ROOT="$home/receipts" \
    MOCK_EXIT_CODE="$exit_code" MOCK_WRITE_FILE="$write_violation" MOCK_WRITE_PROPOSAL="$write_proposal" \
    bash "$SCRIPT" >"$home/stdout.log" 2>&1 || rc=$?
  echo "$rc"
}
stub_calls() { if [ -f "$1/stub.jsonl" ]; then wc -l < "$1/stub.jsonl"; else echo 0; fi; }
# stub_has <home> <flag> <value>: the last recorded executor argv carries flag followed by value.
stub_has() {
  python3 - "$1/stub.jsonl" "$2" "$3" <<'PY'
import json, sys
call = json.loads(open(sys.argv[1]).read().splitlines()[-1])
flag, value = sys.argv[2], sys.argv[3]
sys.exit(0 if flag in call and call[call.index(flag) + 1] == value else 1)
PY
}
receipt_validates() {
  python3 - "$1" "$2" <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location("wr", sys.argv[2])
module = importlib.util.module_from_spec(spec); spec.loader.exec_module(module)
receipt = json.load(open(sys.argv[1]))
ok = not module.validate(receipt) and receipt["terminal"]["outcome"] in ("artifact", "decline", "failed", "skipped")
sys.exit(0 if ok and receipt["run_id"] == "inv-smoke" else 1)
PY
}

echo "--- scenario 30: NOPROPOSAL writes one receipt with no evidence flag (::propose-writes-receipt-on-exit) ---"
h30=$(sandbox)
rc=$(run_receipt_scenario "$h30" 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "exactly one executor call" "[ \"\$(stub_calls '$h30')\" = 1 ]"
assert "unit from DELIVERY_JOB, vantage run" "grep -q '\"knowledge-digest\", \"--vantage\", \"run\"' '$h30/stub.jsonl'"
assert "run id is INVOCATION_ID" "stub_has '$h30' --run-id inv-smoke"
assert "no artifact, no skipped, no failed — the executor reads ^DECLINE: itself" "! grep -qE -- '--artifact|--skipped|--failed|--state-change' '$h30/stub.jsonl'"
assert "the executor's line reaches agent_propose.log" "grep -q 'contract_exec: stub' '$h30/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 31: PROPOSAL passes the proposal as the artifact (::propose-writes-receipt-on-exit) ---"
h31=$(sandbox)
rc=$(run_receipt_scenario "$h31" 0 1)
assert "exits 0" "[ '$rc' = 0 ]"
assert "one call, --artifact is the pushed proposal" "stub_has '$h31' --artifact 'file://$h31/agent-worktrees/inbox/_inbox/agents/2026-08-08_test-slug.md'"

echo "--- scenario 32: FAIL passes --failed with the rc and the last attempt line (::propose-writes-receipt-on-exit) ---"
h32=$(sandbox)
rc=$(run_receipt_scenario "$h32" 1)
assert "exits 1 (unchanged)" "[ '$rc' = 1 ]"
assert "one call" "[ \"\$(stub_calls '$h32')\" = 1 ]"
assert "--failed names FAIL and rc=1" "grep -q '\"--failed\", \"FAIL: rc=1' '$h32/stub.jsonl'"

echo "--- scenario 33: CRASHED, DEDUP, VIOLATION and BLOCKED each write their mapped receipt (::propose-writes-receipt-on-exit) ---"
h33=$(sandbox); rc=$(run_receipt_scenario "$h33" 4)
assert "CRASHED: exits 1, --failed CRASHED: rc=4" "[ '$rc' = 1 ] && grep -q '\"--failed\", \"CRASHED: rc=4' '$h33/stub.jsonl'"
h33b=$(sandbox); rc=$(run_receipt_scenario "$h33b" 3)
assert "DEDUP: exits 0, --skipped dedup" "[ '$rc' = 0 ] && stub_has '$h33b' --skipped \"dedup: today's proposal already exists\""
h33c=$(sandbox); rc=$(run_receipt_scenario "$h33c" 0 0 1)
assert "VIOLATION: exits 1, --failed VIOLATION" "[ '$rc' = 1 ] && stub_has '$h33c' --failed 'VIOLATION: wrote outside _inbox/agents'"
h33d=$(sandbox); rm -f "$h33d/.config/agent-workforce/secrets.env"; rc=$(run_receipt_scenario "$h33d" 0)
assert "BLOCKED: exits 0, --failed BLOCKED: secrets.env missing" "[ '$rc' = 0 ] && stub_has '$h33d' --failed 'BLOCKED: secrets.env missing'"
assert "BLOCKED: exactly one receipt call" "[ \"\$(stub_calls '$h33d')\" = 1 ]"

echo "--- scenario 34: flock SKIP writes a skipped receipt and still exits 0 (::propose-writes-receipt-on-exit) ---"
h34=$(sandbox)
( exec 9>"$h34/lock"; flock 9; sleep 20 ) &
holder=$!
sleep 0.3
rc=$(run_receipt_scenario "$h34" 0)
kill "$holder" 2>/dev/null; wait "$holder" 2>/dev/null || true
assert "exits 0" "[ '$rc' = 0 ]"
assert "--skipped names the flock" "stub_has '$h34' --skipped 'previous run still active (flock)'"
assert "the runtime was never launched" "[ ! -s '$h34/hermes_argv.log' ]"

echo "--- scenario 35: OPS with a report passes it as the artifact; the mock's envelope becomes --usage-json (::propose-writes-receipt-on-exit) ---"
h35=$(sandbox)
printf '\nAGENT_RUN_MODE=ops\nAGENT_TASK_SLUG=overnight-morning-report\n' \
  >> "$h35/.config/agent-workforce/secrets.env"
cat > "$h35/mock_hermes.sh" <<EOF
#!/usr/bin/env bash
echo "\$@" >> "$h35/hermes_argv.log"
mkdir -p "$h35/logs/overnight" "\$(dirname "\$AGENT_USAGE_JSON")"
echo report > "$h35/logs/overnight/morning-report-test.md"
cp "$REPO_ROOT/tests/fixtures/receipt-wiring/claude-envelope.json" "\$AGENT_USAGE_JSON"
exit 0
EOF
chmod +x "$h35/mock_hermes.sh"
# REPORT_DIR/REPORT_GLOB come from the unit file's Environment= in production, so they are
# env here too, not lines in the sourced-but-unexported secrets.env.
rc=$(REPORT_DIR="$h35/logs/overnight" REPORT_GLOB='morning-report-*.md' run_receipt_scenario "$h35" 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "--artifact is the fresh report" "stub_has '$h35' --artifact 'file://$h35/logs/overnight/morning-report-test.md'"
assert "--usage-json is the attempt's envelope" "stub_has '$h35' --usage-json '$h35/agent-workforce/logs/last-attempt/overnight-morning-report.usage.json'"

echo "--- scenario 36: a stale envelope from the previous attempt is removed before the runtime runs ---"
h36=$(sandbox)
mkdir -p "$h36/agent-workforce/logs/last-attempt"
echo '{"stale":1}' > "$h36/agent-workforce/logs/last-attempt/standing.usage.json"
rc=$(run_receipt_scenario "$h36" 0)
assert "the stale envelope is gone (the mock wrote none)" "[ ! -e '$h36/agent-workforce/logs/last-attempt/standing.usage.json' ]"
assert "so no --usage-json is passed" "! grep -q -- '--usage-json' '$h36/stub.jsonl'"

echo "--- scenario 37: a broken receipt adapter never changes the exit code (::propose-receipt-failure-keeps-exit-code) ---"
h37=$(sandbox); rc=$(run_receipt_scenario "$h37" 0 1 0 /bin/false)
assert "PROPOSAL with CONTRACT_EXEC=/bin/false still exits 0" "[ '$rc' = 0 ]"
assert "and says so in the log" "grep -q 'receipt: not written' '$h37/agent-workforce/logs/agent_propose.log'"
h37b=$(sandbox); rc=$(run_receipt_scenario "$h37b" 1 0 0 /bin/false)
assert "FAIL with a broken adapter still exits 1" "[ '$rc' = 1 ]"
h37c=$(sandbox); rc=$(run_receipt_scenario "$h37c" 0 0 0 "$h37c/does-not-exist.py")
assert "a missing adapter target still exits 0" "[ '$rc' = 0 ]"
h37d=$(sandbox); rc=$(STUB_RC=1 run_receipt_scenario "$h37d" 0)
assert "an executor that says failed (exit 1) does not fail a NOPROPOSAL run" "[ '$rc' = 0 ]"

echo "--- scenario 38: no DELIVERY_JOB (a hand run) writes no receipt and says why ---"
h38=$(sandbox); stub=$(make_receipt_stub "$h38")
rc=0
HOME="$h38" PATH="$h38/mockbin:$PATH" AGENT_PROPOSE_LOCK="$h38/lock" AGENT_RETRY_BASE_SECONDS=0 \
  QMD_HEALTH_POLICY=off BRAVE_HEALTH_POLICY=off CONTRACT_EXEC="$stub" STUB_OUT="$h38/stub.jsonl" \
  bash "$SCRIPT" >"$h38/stdout.log" 2>&1 || rc=$?
assert "exits 0" "[ '$rc' = 0 ]"
assert "no executor call" "[ \"\$(stub_calls '$h38')\" = 0 ]"
assert "the log says no unit known" "grep -q 'no unit known — no receipt' '$h38/agent-workforce/logs/agent_propose.log'"

echo "--- scenario 39: the real executor writes a receipt that validates and reads back (::receipt-reads-back-valid) ---"
h39=$(sandbox)
cat > "$h39/real_exec.sh" <<EOF
#!/usr/bin/env bash
exec python3 "$REPO_ROOT/bin/contract_exec.py" "\$@" --repo-root "$REPO_ROOT" \\
  --manifest-dir "$REPO_ROOT/tests/fixtures/contract-exec/agents" --home "\$HOME"
EOF
chmod +x "$h39/real_exec.sh"
rc=$(run_receipt_scenario "$h39" 0 1 0 "$h39/real_exec.sh")
assert "exits 0" "[ '$rc' = 0 ]"
assert "receipt at <root>/knowledge-digest/inv-smoke.json" "[ -s '$h39/receipts/knowledge-digest/inv-smoke.json' ]"
assert "the receipt validates and carries one terminal outcome" "receipt_validates '$h39/receipts/knowledge-digest/inv-smoke.json' '$REPO_ROOT/bin/workflow_receipt.py'"
assert "the log names the receipt path" "grep -q 'receipt: $h39/receipts/knowledge-digest/inv-smoke.json' '$h39/agent-workforce/logs/agent_propose.log'"

# ── T5.3f: the requires pre-flight ─────────────────────────────────────────────────────────
# WORKFLOW_REQUIRES points the pre-flight at a stub, as CONTRACT_EXEC does for the receipt:
# the CLI's own verdicts are tests/test_workflow_requires.sh's; this proves what the runner
# does with exit 1 (BLOCKED, receipted, exit 0, nothing launched) and with exit 0 (nothing).
make_requires_stub() {  # make_requires_stub <home> <rc> <line>
  cat > "$1/stub_requires.sh" <<EOF
#!/usr/bin/env bash
echo "\$*" >> "$1/requires_argv.log"
echo "$3"
exit $2
EOF
  chmod +x "$1/stub_requires.sh"
  echo "$1/stub_requires.sh"
}
echo "--- scenario 40: a requirement known down is BLOCKED before the runtime launches (::propose-requires-preflight) ---"
h40=$(sandbox); stub40=$(make_requires_stub "$h40" 1 'requires buzz-agent@augustus: inactive')
rc=$(WORKFLOW_REQUIRES="$stub40" run_receipt_scenario "$h40" 0)
assert "exits 0" "[ '$rc' = 0 ]"
assert "the pre-flight was asked about the unit systemd is running" "grep -qx 'check knowledge-digest' '$h40/requires_argv.log'"
assert "logs BLOCKED with the CLI's last line" "grep -q 'BLOCKED: requires buzz-agent@augustus: inactive' '$h40/agent-workforce/logs/agent_propose.log'"
assert "cost.log outcome=BLOCKED" "grep -q 'outcome=BLOCKED' '$h40/agent-workforce/logs/cost.log'"
assert "the receipt is --failed BLOCKED: requires …" "stub_has '$h40' --failed 'BLOCKED: requires buzz-agent@augustus: inactive'"
assert "exactly one receipt call" "[ \"\$(stub_calls '$h40')\" = 1 ]"
assert "the runtime was never launched" "[ ! -s '$h40/hermes_argv.log' ]"
h40b=$(sandbox); stub40b=$(make_requires_stub "$h40b" 0 'requires buzz-agent@augustus: unknown')
rc=$(WORKFLOW_REQUIRES="$stub40b" run_receipt_scenario "$h40b" 0)
assert "exit 0 from the pre-flight is not a refusal: the run proceeds" "[ '$rc' = 0 ] && grep -q 'outcome=NOPROPOSAL' '$h40b/agent-workforce/logs/cost.log'"
assert "and its lines are in the log" "grep -q 'requires buzz-agent@augustus: unknown' '$h40b/agent-workforce/logs/agent_propose.log'"
assert "no BLOCKED record" "! grep -q 'outcome=BLOCKED' '$h40b/agent-workforce/logs/cost.log'"
h40c=$(sandbox); stub40c=$(make_requires_stub "$h40c" 1 'requires x: inactive')
rc=$(DELIVERY_JOB= AGENT_RECEIPT_UNIT= WORKFLOW_REQUIRES="$stub40c" run_scenario "$h40c" 0 0)
assert "no unit known: the pre-flight is skipped out loud, never asked" "[ '$rc' = 0 ] && [ ! -e '$h40c/requires_argv.log' ] && grep -q 'requires pre-flight skipped: no unit' '$h40c/agent-workforce/logs/agent_propose.log'"
exit $fail
