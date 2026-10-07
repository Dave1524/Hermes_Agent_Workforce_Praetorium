#!/usr/bin/env bash
# Board brief run (Dev Plan B2) — the runner, its verify command, its profile and its env
# wiring. Offline by contract: a mock claude, a throwaway card directory, a stub vault guard.
# The wrapper's board mode (pick, ledger-growth detector, BOARD outcome) is exercised in
# tests/test_agent_propose_smoke.sh; this file owns everything the wrapper execs.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/rhythm_test_lib.sh
. "$TESTS_DIR/rhythm_test_lib.sh"

assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_research_brief_cc.sh"
VERIFY="$REPO_ROOT/bin/brief_or_decline.sh"
TASK="$REPO_ROOT/profiles/research_brief_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/research_brief.env.example"
BOARD="$REPO_ROOT/bin/board.py"

echo "--- research-brief: the env override wires board mode and the Backlog pick ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
assert "AGENT_TASK_SLUG=research-brief" "[ \"\$(env_value '$ENV_EXAMPLE' AGENT_TASK_SLUG)\" = research-brief ]"
assert "AGENT_RUN_MODE=board (no inbox worktree, no proposal commit)" "[ \"\$(env_value '$ENV_EXAMPLE' AGENT_RUN_MODE)\" = board ]"
assert "the pick names claudius, research and the backlog column" \
  "[ \"\$(env_value '$ENV_EXAMPLE' AGENT_BOARD_PICK)\" = '--owner claudius --kind research --column backlog' ]"
assert "a quiet tick is a skip, not a model run (AGENT_BOARD_REQUIRED=1)" "[ \"\$(env_value '$ENV_EXAMPLE' AGENT_BOARD_REQUIRED)\" = 1 ]"
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to the executable runner" "[ -x '$resolved' ] && [[ '$runtime' == *run_research_brief_cc.sh ]]"
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
resolved="${verify/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_VERIFY_CMD resolves to the executable brief verifier" "[ -x '$resolved' ] && [[ '$verify' == *brief_or_decline.sh ]]"

# A card directory the way `board.py pick` leaves it: runs/<run_id>/ with card.md in it.
make_card_fixture() {
  local home card_dir
  home=$(mktemp -d)
  card_dir="$home/board/runs/run-1"
  mkdir -p "$card_dir" "$home/inbox"
  printf '# Local search\nid: local-search\n' > "$card_dir/card.md"
  make_skills_fixture "$home" claudius >/dev/null
  cp "$TASK" "$home/task.md"
  printf '#!/usr/bin/env bash\nexit "${STUB_GUARD_RC:-0}"\n' > "$home/guard"
  chmod +x "$home/guard"
  echo "$home"
}

run_brief() { # fixture-root [VAR=value ...] -> rc
  local home=$1 claude rc=0
  shift
  claude=$(make_mock_claude "$home")
  local -a unset_args=() set_args=()
  [ "${NO_CARD_DIR:-}" = 1 ] && unset_args=(-u AGENT_CARD_DIR) || set_args=(AGENT_CARD_DIR="$home/board/runs/run-1")
  env "${unset_args[@]}" HOME="$home" CLAUDE_BIN="$claude" RESEARCH_BRIEF_TASK="$home/task.md" VAULT_SYNC_GUARD="$home/guard" \
    "${set_args[@]}" "$@" bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

assert_never_launched() {
  local home=$1 desc=$2
  assert "$desc" "[ -x '$home/claude' ] && [ ! -f '$home/claude_argv.log' ]"
}

echo "--- research-brief: the runner refuses without its preconditions ---"
home=$(make_card_fixture); rm "$home/task.md"
rc=$(run_brief "$home")
assert "a missing task file exits non-zero" "[ '$rc' != 0 ]"
assert "and names the path" "grep -qF 'research-brief: task file not readable: $home/task.md' '$home/run.log'"
assert_never_launched "$home" "and the agent is never launched with an empty prompt"

home=$(make_card_fixture); chmod 000 "$home/task.md"
rc=$(run_brief "$home")
assert "a present but unreadable task file also refuses (-r, not -f)" "[ '$rc' != 0 ]"
assert_never_launched "$home" "and the agent is never launched"

home=$(make_card_fixture); rm -r "$home/agent-workforce/skills"
rc=$(run_brief "$home")
assert "a missing skills plugin refuses (a --plugin-dir that does not exist is silent)" \
  "[ '$rc' != 0 ] && grep -qF 'skills plugin not readable' '$home/run.log'"
assert_never_launched "$home" "and the agent is never launched"

home=$(make_card_fixture)
rc=$(NO_CARD_DIR=1 run_brief "$home")
assert "no AGENT_CARD_DIR (no pick) refuses" "[ '$rc' != 0 ] && grep -qF 'AGENT_CARD_DIR not set' '$home/run.log'"
assert_never_launched "$home" "and the agent is never launched"

home=$(make_card_fixture)
rc=$(run_brief "$home" AGENT_CARD_DIR="$home/board/runs/nope")
assert "a card directory that does not exist refuses" "[ '$rc' != 0 ] && grep -qF 'card directory missing' '$home/run.log'"
assert_never_launched "$home" "and the agent is never launched"

home=$(make_card_fixture)
rc=$(run_brief "$home" STUB_GUARD_RC=1)
assert "a dirty or stale mirror refuses" "[ '$rc' != 0 ] && grep -qF 'REFUSING' '$home/run.log'"
assert_never_launched "$home" "and the agent is never launched on stale data"

echo "--- research-brief: the runner launches Opus 5 in the card directory with no MCP servers ---"
home=$(make_card_fixture)
rc=$(run_brief "$home")
assert "exits 0" "[ '$rc' = 0 ]"
assert "the prompt is the task file, not an empty string" \
  "[ \"\$(sed -n 1p '$home/claude_argv.log')\" = '-p' ] && [ -n \"\$(sed -n 2p '$home/claude_argv.log')\" ]"
assert "pins the full Opus 5 model name, not the opus alias" \
  "grep -qx 'claude-opus-5' '$home/claude_argv.log' && ! grep -qx 'opus' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "offers WebSearch and WebFetch for the landscape check (decision 9)" \
  "grep -q 'WebSearch' '$home/claude_argv.log' && grep -q 'WebFetch' '$home/claude_argv.log'"
assert "offers no Edit tool" "! grep -E '^Bash,' '$home/claude_argv.log' | grep -q 'Edit'"
assert "offers claudius's pointer-skill tree by explicit path" \
  "grep -qx -- '--plugin-dir' '$home/claude_argv.log' && grep -qx '$home/agent-workforce/skills/claudius' '$home/claude_argv.log'"

echo "--- research-brief: the profile ---"
assert "profile exists and names its owner on the first line" "[ -f '$TASK' ] && head -n 1 '$TASK' | grep -q '^Owner: claudius'"
assert "reads the template from board.py" "grep -q 'board.py template --kind research' '$TASK'"
assert "emits the DECLINE: sentinel" "grep -q 'DECLINE:' '$TASK'"
assert "never acts outward" "grep -qi 'never act outward' '$TASK'"
assert "writes exactly one file in the card directory" "grep -q 'brief.out.md' '$TASK'"
assert "names no ledger write verb" "! grep -E 'board.py (brief|note|pick|edit|create|land|sweep)' '$TASK'"
assert "de-identifies web queries per the data boundary" "grep -q 'data_boundary.md' '$TASK'"

echo "--- research-brief: brief_or_decline.sh accepts only THIS run's brief, decline or skip ---"
GOOD_BRIEF='# Brief: local-search

## Question

Can search run locally?

## Why

It feeds the tooling decision.

## Scope in / out

In: indexing. Out: hosting.

## Sources

05_knowledge/search.md

## Acceptance

- Names the refresh cost.
- Names one local engine.
- States the memory footprint.

## Size

One run.

## Questions for Dave

None.
'
make_verify_state() { # -> home with run dir, attempt log and a start stamp
  local home started
  home=$(mktemp -d); mkdir -p "$home/runs/r1" "$home/logs"
  started=$(( $(date +%s) - 60 ))
  printf '%s' "$started" > "$home/started"
  echo "$home"
}
run_verify() { # home -> rc
  local home=$1 rc=0
  env AGENT_CARD=local-search AGENT_CARD_DIR="$home/runs/r1" AGENT_RUN_STARTED_AT="$(cat "$home/started")" \
    AGENT_ATTEMPT_LOG="$home/logs/attempt.log" BOARD_PY="$BOARD" bash "$VERIFY" >"$home/verify.out" 2>&1 || rc=$?
  echo "$rc"
}

home=$(make_verify_state)
printf '%s' "$GOOD_BRIEF" > "$home/runs/r1/brief.out.md"
assert "a fresh, valid brief passes" "[ \"\$(run_verify '$home')\" = 0 ]"

home=$(make_verify_state)
printf '%s' "$GOOD_BRIEF" > "$home/runs/r1/brief.out.md"
touch -d '2 hours ago' "$home/runs/r1/brief.out.md"
assert "yesterday's brief left in place does NOT pass" "[ \"\$(run_verify '$home')\" = 1 ]"

home=$(make_verify_state)
printf '# Brief: local-search\n\n## Question\n\nx\n' > "$home/runs/r1/brief.out.md"
assert "a brief missing headings fails and says which" \
  "[ \"\$(run_verify '$home')\" = 1 ] && grep -q 'missing heading: ## Acceptance' '$home/verify.out'"

home=$(make_verify_state)
printf '%s' "$GOOD_BRIEF" | sed '1s/local-search/another-card/' > "$home/runs/r1/brief.out.md"
assert "a brief naming another card fails" "[ \"\$(run_verify '$home')\" = 1 ]"

home=$(make_verify_state)
printf 'DECLINE: duplicate of local-search-2\n' > "$home/logs/attempt.log"
assert "this run's own DECLINE: passes" "[ \"\$(run_verify '$home')\" = 0 ]"

home=$(make_verify_state)
printf 'DECLINE: stale\n' > "$home/logs/attempt.log"; touch -d '2 hours ago' "$home/logs/attempt.log"
assert "a DECLINE: from an earlier run does NOT pass" "[ \"\$(run_verify '$home')\" = 1 ]"

home=$(make_verify_state)
printf 'skip: this run already wrote its brief\n' > "$home/logs/attempt.log"
assert "this run's own idempotent skip exits 3 (receipted skipped, not failed)" "[ \"\$(run_verify '$home')\" = 3 ]"

home=$(make_verify_state)
assert "neither a brief, a decline nor a skip fails" "[ \"\$(run_verify '$home')\" = 1 ]"

rc=0; env -u AGENT_CARD bash "$VERIFY" >/dev/null 2>&1 || rc=$?
assert "an unset AGENT_CARD fails closed" "[ '$rc' != 0 ]"

exit $fail
