#!/usr/bin/env bash
# M1 — Market Signal Scan, Claude Code runtime (NUC-32 variant).
# Runs the standing M1 mission as headless Claude Code (Sonnet) on the box's own
# Claude subscription instead of hermes/claudius on OpenRouter — wired in as
# AGENT_RUNTIME_CMD via ~/.config/agent-workforce/m1_signal_scan.env while the
# OpenRouter budget is paused (2026-07-24). agent_propose.sh owns worktree
# checkout, the _inbox/agents/ write-boundary, commit/push and metrics; this
# script is only the "brain" it execs. Revert: restore m1_signal_scan.env.bak.
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
INBOX="$HOME/agent-worktrees/inbox"
TASK_FILE="$HOME/agent-workforce/profiles/m1_signal_scan_cc_task.md"

cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model sonnet \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"
