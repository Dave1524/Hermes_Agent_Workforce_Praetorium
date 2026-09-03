#!/usr/bin/env bash
# NUC-24 — weekly-pre-assembly on the Claude Code runtime. Offline by contract: throwaway
# git fixtures and a mock claude binary, never ~/vault, never a real remote, never OpenRouter.
#
# The case that matters is the freshness gate. This job assembles a weekly pre-read from the
# vault mirror, so a mirror that silently froze must produce a refusal, never a confident
# pre-read built from last week's tree.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in assert(): `yes` is guaranteed
# to still be writing when `grep -q` exits, so this fails if and only if a condition is
# evaluated under pipefail. It lives in every caller because the assert it guards is shared —
# a single copy in the lib could not tell which suite had reintroduced the setting.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_weekly_pre_assembly_cc.sh"
TASK="$REPO_ROOT/profiles/weekly_pre_assembly_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/weekly_pre_assembly.env.example"

run_weekly() {
  local state=$1 home=$2 root
  root=$(make_vault_fixture "$state")
  local claude; claude=$(make_mock_claude "$home")
  mkdir -p "$home/inbox/_inbox/agents"
  rc=0
  HOME="$home" CLAUDE_BIN="$claude" VAULT_DIR="$root/vault" VAULT_SYNC_GUARD="$GUARD" \
    WEEKLY_PRE_ASSEMBLY_INBOX="$home/inbox" WEEKLY_PRE_ASSEMBLY_TASK="$TASK" \
    bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- weekly-pre-assembly: the env override parses and wires the CC runner ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
assert "AGENT_TASK_SLUG=weekly-pre-assembly" "[ '$slug' = weekly-pre-assembly ]"
assert "AGENT_PROFILE is the Claude Code runtime, not claudius/OpenRouter" \
  "[ '$profile' = claude-sonnet ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"
assert "and points at the CC runner (the 402 fix)" "[[ '$runtime' == *run_weekly_pre_assembly_cc.sh* ]]"
assert "no hermes/OpenRouter invocation survives in the active wiring" \
  "! grep -qE '^AGENT_RUNTIME_CMD=.*hermes' '$ENV_EXAMPLE'"

echo "--- weekly-pre-assembly: refuses to assemble off a stale mirror ---"
home=$(mktemp -d)
rc=$(run_weekly stale_behind "$home")
assert "exits non-zero on a 5-day-stale mirror" "[ '$rc' != 0 ]"
assert "says REFUSING (so the journal explains the alert)" "grep -q 'REFUSING' '$home/run.log'"
assert "the agent is never launched on stale data" "[ ! -f '$home/claude_argv.log' ]"

echo "--- weekly-pre-assembly: runs on a current mirror ---"
home=$(mktemp -d)
rc=$(run_weekly clean_current "$home")
assert "exits 0" "[ '$rc' = 0 ]"
assert "launches the agent with the pre-assembly task prompt" \
  "grep -qF 'Weekly Review Pre-Assembly (NUC-24), Claude Code runtime variant' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "no outward tools in the allowlist (box holds no outward credential)" \
  "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"

echo "--- weekly-pre-assembly: the task profile does not re-introduce the size-capped read ---"
assert "task profile exists" "[ -f '$TASK' ]"
assert "does not tell the agent to multi-get the daily logs (all now exceed the 10KB cap)" \
  "! grep -qE '^ *[0-9]\. .*multi-get.*daily log' '$TASK'"
assert "reads the logs off the vault mirror instead" "grep -q '~/vault/07_daily/logs' '$TASK'"
assert "keeps Notion on REST, never the removed MCP" \
  "grep -q 'api.notion.com/v1/data_sources' '$TASK' && ! grep -q 'mcp__notion__[a-z]' '$TASK'"

exit $fail
