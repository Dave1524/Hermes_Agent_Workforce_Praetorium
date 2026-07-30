#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — standing research on headless Claude Code,
# pinned to Opus 5, replacing hermes/claudius on OpenRouter. The case that matters: the
# standing run was hard-down for ten days on OpenRouter 402s while agent_propose.sh logged
# a clean NOPROPOSAL, because the 402 landed in the hermes profile's own errors.log, never
# in the attempt's stdout where PROVIDER_ERROR_RE could see it. Offline by contract: mock
# claude, never a real inbox worktree, never OpenRouter.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/rhythm_test_lib.sh
. "$TESTS_DIR/rhythm_test_lib.sh"

RUNNER="$REPO_ROOT/bin/run_standing_research_cc.sh"
TASK="$REPO_ROOT/profiles/standing_research_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/standing_research.env.example"

echo "--- standing-research: the env override parses and wires the CC runner ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert "AGENT_TASK_SLUG=standing-research" "[ '$slug' = standing-research ]"
assert "AGENT_PROFILE is the Claude Code runtime, not claudius/OpenRouter" "[ '$profile' = claude-opus ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"
assert "and points at the CC runner (the 402 fix)" "[[ '$runtime' == *run_standing_research_cc.sh* ]]"
assert "no hermes/OpenRouter invocation survives in the active wiring" \
  "! grep -qE '^AGENT_RUNTIME_CMD=.*hermes' '$ENV_EXAMPLE'"
assert "AGENT_VERIFY_CMD wires the shared de-silencing helper" \
  "[[ '$verify' == *'proposal_or_decline.sh standing-research'* ]]"

echo "--- standing-research: the runner launches Opus 5 with no MCP servers ---"
home=$(mktemp -d)
inbox="$home/inbox"; mkdir -p "$inbox"
claude=$(make_mock_claude "$home")
rc=0
HOME="$home" CLAUDE_BIN="$claude" STANDING_RESEARCH_INBOX="$inbox" STANDING_RESEARCH_TASK="$TASK" \
  bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
assert "exits 0" "[ '$rc' = 0 ]"
assert "pins the full Opus 5 model name, not the opus alias" \
  "grep -qx 'claude-opus-5' '$home/claude_argv.log' && ! grep -qx 'opus' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "keeps WebSearch/WebFetch (this job does public web research)" \
  "grep -qE 'WebSearch' '$home/claude_argv.log' && grep -qE 'WebFetch' '$home/claude_argv.log'"
assert "launches with the standing-research task prompt" \
  "grep -qF 'headless Claude Code (Opus 5)' '$home/claude_argv.log'"

echo "--- standing-research: task profile carries over the load-bearing claudius instructions ---"
assert "task profile exists" "[ -f '$TASK' ]"
assert "keeps the published_corpus.py duplicate-title gate" "grep -q 'published_corpus.py' '$TASK'"
assert "keeps FACT vs INFERENCE labelling" "grep -qi 'FACT' '$TASK' && grep -qi 'INFERENCE' '$TASK'"
assert "keeps the queue.md soonest-Deadline priority order" "grep -q 'queue.md' '$TASK'"
assert "adds the Mechanism A Contradictions section" "grep -q '## Contradictions' '$TASK'"
assert "emits the DECLINE: sentinel contract" "grep -q 'DECLINE:' '$TASK'"
assert "never acts outward" "grep -qi 'never act outward' '$TASK'"
assert "no hermes memory tool call survives (STEP 5 dropped)" "! grep -q 'action=add' '$TASK'"
assert "substitutes ls _inbox/agents for the removed hermes MEMORY store" \
  "grep -q 'ls -1 _inbox/agents' '$TASK'"
assert "reads approvals.tsv for what was already proposed" "grep -q 'approvals.tsv' '$TASK'"

exit $fail
