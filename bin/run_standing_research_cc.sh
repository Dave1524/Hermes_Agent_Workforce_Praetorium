#!/usr/bin/env bash
# Standing research — Opus 5 migration (research pipeline brief, 2026-07-30). Replaces
# hermes/claudius on OpenRouter, which was hard-down for ten days on 402 "Insufficient
# credits" while agent_propose.sh logged a clean NOPROPOSAL (the 402 never reached the
# attempt's stdout, so PROVIDER_ERROR_RE could not see it). Clones the proven
# run_m1_signal_scan_cc.sh shape: box subscription, $0 OpenRouter spend, no MCP servers,
# explicit tool allowlist. agent_propose.sh owns worktree checkout, the _inbox/agents/
# write boundary, commit/push and metrics; this script is only the "brain" it execs.
# Revert: restore standing_research.env.bak (see its commented prior wiring).
#
# --model claude-opus-5 is the FULL model name, not the `opus` alias — an alias silently
# rolls forward on the next model release, and Dave asked for Opus 5 specifically.
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
INBOX="${STANDING_RESEARCH_INBOX:-$HOME/agent-worktrees/inbox}"
TASK_FILE="${STANDING_RESEARCH_TASK:-$HOME/agent-workforce/profiles/standing_research_cc_task.md}"

# No MCP servers by design (toolset trim, 2026-07-20): this job reads the vault off disk via
# its `cd "$INBOX"` checkout with Read/Glob/Grep and needs no qmd retrieval. Declare
# AGENT_MCP_DEPS=none in the job env so agent_propose.sh skips the daemon probes too.
cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"
