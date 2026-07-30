#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — Mechanism C, the 7-day knowledge digest. Offline
# by contract: throwaway git fixtures and a mock claude binary, never ~/vault, never a
# real remote, never OpenRouter.
#
# The case that matters is the freshness gate: this job reports what the knowledge base
# learned via a git-log delta, so a mirror that silently froze must refuse rather than
# report a confident "nothing changed" that is actually "nothing synced".
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/rhythm_test_lib.sh
. "$TESTS_DIR/rhythm_test_lib.sh"

RUNNER="$REPO_ROOT/bin/run_knowledge_digest_cc.sh"
TASK="$REPO_ROOT/profiles/knowledge_digest_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/knowledge_digest.env.example"

run_digest() {
  local state=$1 home=$2 root
  root=$(make_vault_fixture "$state")
  local claude; claude=$(make_mock_claude "$home")
  mkdir -p "$home/inbox/_inbox/agents"
  rc=0
  HOME="$home" CLAUDE_BIN="$claude" VAULT_DIR="$root/vault" VAULT_SYNC_GUARD="$GUARD" \
    KNOWLEDGE_DIGEST_INBOX="$home/inbox" KNOWLEDGE_DIGEST_TASK="$TASK" \
    bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- knowledge-digest: the env override parses and wires the CC runner ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert "AGENT_TASK_SLUG=knowledge-digest" "[ '$slug' = knowledge-digest ]"
assert "AGENT_PROFILE is the Claude Code runtime" "[ '$profile' = claude-opus ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"
assert "and points at run_knowledge_digest_cc.sh" "[[ '$runtime' == *run_knowledge_digest_cc.sh* ]]"
assert "no hermes/OpenRouter invocation survives" "! grep -qE '^AGENT_RUNTIME_CMD=.*hermes' '$ENV_EXAMPLE'"
assert "AGENT_VERIFY_CMD wires the shared de-silencing helper" \
  "[[ '$verify' == *'proposal_or_decline.sh knowledge-digest'* ]]"

echo "--- knowledge-digest: refuses to digest off a stale mirror ---"
home=$(mktemp -d)
rc=$(run_digest stale_behind "$home")
assert "exits non-zero on a 5-day-stale mirror" "[ '$rc' != 0 ]"
assert "says REFUSING (so the journal explains the alert)" "grep -q 'REFUSING' '$home/run.log'"
assert "the agent is never launched on stale data" "[ ! -f '$home/claude_argv.log' ]"

echo "--- knowledge-digest: runs on a current mirror ---"
home=$(mktemp -d)
rc=$(run_digest clean_current "$home")
assert "exits 0" "[ '$rc' = 0 ]"
assert "launches the agent with the knowledge-digest task prompt" \
  "grep -qF 'Knowledge Digest' '$home/claude_argv.log'"
assert "pins the full Opus 5 model name" "grep -qx 'claude-opus-5' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "no web tools in the allowlist" "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"

echo "--- knowledge-digest: the task profile encodes the whole mechanism ---"
assert "task profile exists" "[ -f '$TASK' ]"
assert "computes the delta with git log --since over 05_knowledge/ and 11_entities/ (exact deltas, not mtime)" \
  "grep -q -- \"log --since='7 days ago'\" '$TASK' && grep -q '05_knowledge/ 11_entities/' '$TASK'"
assert "states the under-500-words instruction" "grep -qi '500 words' '$TASK'"
assert "states it does not replace weekly-pre-assembly" "grep -qi 'does not replace .*weekly-pre-assembly\|not a replacement for .*weekly-pre-assembly' '$TASK'"
assert "flags contradictions from the last 7 days" "grep -q 'Contradictions flagged this week' '$TASK'"
assert "surfaces open questions from open_loops.md" "grep -q 'open_loops.md' '$TASK'"
assert "emits the DECLINE: sentinel contract on an empty delta" "grep -q 'DECLINE: no 05_knowledge/ or 11_entities/' '$TASK'"

exit $fail
