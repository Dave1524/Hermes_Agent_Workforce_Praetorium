#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — Mechanism B, box-side raw ingestion. Offline by
# contract: throwaway git fixtures and a mock claude binary, never ~/vault, never a real
# remote, never OpenRouter.
#
# The case that matters is the freshness gate: this job diffs 05_knowledge/raw/ against
# 00_system/ingest_log.md, so a mirror that silently froze must refuse rather than distill
# a source that may already be superseded.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/rhythm_test_lib.sh
. "$TESTS_DIR/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in assert(): `yes` is guaranteed
# to still be writing when `grep -q` exits, so this fails if and only if a condition is
# evaluated under pipefail. It lives in every caller because the assert it guards is shared —
# a single copy in the lib could not tell which suite had reintroduced the setting.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_raw_ingest_cc.sh"
TASK="$REPO_ROOT/profiles/raw_ingest_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/raw_ingest.env.example"

run_raw_ingest() {
  local state=$1 home=$2 root
  root=$(make_vault_fixture "$state")
  local claude; claude=$(make_mock_claude "$home")
  mkdir -p "$home/inbox/_inbox/agents"
  rc=0
  HOME="$home" CLAUDE_BIN="$claude" VAULT_DIR="$root/vault" VAULT_SYNC_GUARD="$GUARD" \
    RAW_INGEST_INBOX="$home/inbox" RAW_INGEST_TASK="$TASK" \
    bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- raw-ingest: the env override parses and wires the CC runner ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert "AGENT_TASK_SLUG=raw-ingest" "[ '$slug' = raw-ingest ]"
assert "AGENT_PROFILE is the Claude Code runtime" "[ '$profile' = claude-opus ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"
assert "and points at run_raw_ingest_cc.sh" "[[ '$runtime' == *run_raw_ingest_cc.sh* ]]"
assert "no hermes/OpenRouter invocation survives" "! grep -qE '^AGENT_RUNTIME_CMD=.*hermes' '$ENV_EXAMPLE'"
assert "AGENT_VERIFY_CMD wires the shared de-silencing helper" \
  "[[ '$verify' == *'proposal_or_decline.sh raw-ingest'* ]]"

echo "--- raw-ingest: refuses to ingest off a stale mirror ---"
home=$(mktemp -d)
rc=$(run_raw_ingest stale_behind "$home")
assert "exits non-zero on a 5-day-stale mirror" "[ '$rc' != 0 ]"
assert "says REFUSING (so the journal explains the alert)" "grep -q 'REFUSING' '$home/run.log'"
assert "the agent is never launched on stale data" "[ ! -f '$home/claude_argv.log' ]"

echo "--- raw-ingest: refuses on a dirty mirror ---"
home=$(mktemp -d)
rc=$(run_raw_ingest dirty_behind "$home")
assert "exits non-zero on tracked local edits" "[ '$rc' != 0 ]"
assert "says REFUSING" "grep -q 'REFUSING' '$home/run.log'"
assert "the agent is never launched on a dirty mirror" "[ ! -f '$home/claude_argv.log' ]"

echo "--- raw-ingest: runs on a current mirror ---"
home=$(mktemp -d)
rc=$(run_raw_ingest clean_current "$home")
assert "exits 0" "[ '$rc' = 0 ]"
assert "launches the agent with the raw-ingest task prompt" \
  "grep -qF 'Raw Source Ingestion' '$home/claude_argv.log'"
assert "pins the full Opus 5 model name" "grep -qx 'claude-opus-5' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "no web tools in the allowlist (this job reads local sources only)" \
  "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"

echo "--- raw-ingest: the task profile encodes the whole mechanism ---"
assert "task profile exists" "[ -f '$TASK' ]"
assert "references 05_knowledge/raw" "grep -q '05_knowledge/raw' '$TASK'"
assert "references 00_system/ingest_log.md" "grep -q '00_system/ingest_log.md' '$TASK'"
assert "carries source:/updates: frontmatter per the Source Ingestion protocol" \
  "grep -q 'source:' '$TASK' && grep -q 'updates:' '$TASK' && grep -q 'update_protocol.md' '$TASK'"
assert "adds the Mechanism A Contradictions section" "grep -q '## Contradictions' '$TASK'"
assert "emits the DECLINE: sentinel contract" "grep -q 'DECLINE: no unprocessed sources' '$TASK'"
assert "names the existing-notes-checked auditability requirement" "grep -q 'knowledge_index.md' '$TASK'"

exit $fail
