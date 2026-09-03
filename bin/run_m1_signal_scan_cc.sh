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

# W15: this guard is what stands between a missing profile and a launched EMPTY PROMPT.
# The `$(cat "$TASK_FILE")` below sits in a command substitution used as an ARGUMENT, and
# `set -e` does not propagate a failure from there: cat(1) writes to stderr, yields the
# empty string, and the agent runs with no mission and exits 0 — which agent_propose.sh
# then records as NOPROPOSAL, indistinguishable from a genuine "no signals at quality".
# Must stay BEFORE the substitution. Same shape and message as
# bin/run_overnight_morning_report_cc.sh:30. `-r`, not `-f`: a present-but-unreadable
# profile produces the identical empty prompt.
[ -r "$TASK_FILE" ] || { echo "m1-signal-scan: task file not readable: $TASK_FILE" >&2; exit 1; }

# No MCP servers by design (toolset trim, 2026-07-20): this job reads the vault off disk via
# its `cd "$INBOX"` checkout with Read/Glob/Grep and needs no qmd retrieval. Declare
# AGENT_MCP_DEPS=none in the job env so agent_propose.sh skips the daemon probes too.
cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model sonnet \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"
