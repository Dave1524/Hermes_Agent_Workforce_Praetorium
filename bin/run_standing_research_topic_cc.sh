#!/usr/bin/env bash
# Overnight standing-research pair (Marcus relay, 2026-08-25): "2026 content strategy" and
# "faceless content as a digital product" — Dave's two GO topics from 2026-08-14. Follows
# run_standing_research_cc.sh's proven shape (box subscription, $0 OpenRouter spend, no MCP
# servers, explicit tool allowlist) but runs under AGENT_RUN_MODE=ops: no inbox worktree, no
# proposal commit — the artifact is a dated log file plus a Notion section, appended via
# notion_research_page.py. Zero external actions for the entire run (Marcus relay, rule 5):
# no ExecStartPost delivery step is wired for either job, by design.
set -euo pipefail

job="${1:-}"
case "$job" in
  content-strategy|faceless-content) ;;
  *) echo "usage: $(basename "$0") content-strategy|faceless-content" >&2; exit 2 ;;
esac

CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
WORKDIR="${STANDING_RESEARCH_TOPIC_WORKDIR:-$HOME/agent-workforce}"

case "$job" in
  content-strategy) TASK_FILE="$WORKDIR/profiles/standing_research_content_strategy_task.md" ;;
  faceless-content) TASK_FILE="$WORKDIR/profiles/standing_research_faceless_content_task.md" ;;
esac
[ -r "$TASK_FILE" ] || { echo "$job: task file not readable: $TASK_FILE" >&2; exit 1; }

# No MCP servers by design, same as run_standing_research_cc.sh: Notion I/O goes through
# notion_research_page.py (plain HTTP via notion_rest.py), not an MCP tool. Declare
# AGENT_MCP_DEPS=none in the job env so agent_propose.sh skips the daemon probes too.
cd "$WORKDIR"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"
