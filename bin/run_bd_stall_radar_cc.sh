#!/usr/bin/env bash
# BD pipeline stall radar — Claude Code harness around bin/bd_stall_radar_kernel.py (T2.3).
# agent_propose.sh owns worktree checkout, the _inbox/agents/ write-boundary, commit/push
# and metrics; this script is only the "brain" it execs. Stall rules live in the kernel
# (exact, $0, no model); the task file tells the session to run it rather than reimplement
# them. Revert: restore the live override's AGENT_RUNTIME_CMD to the kernel.
set -euo pipefail

CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
INBOX="$HOME/agent-worktrees/inbox"
TASK_FILE="$HOME/agent-workforce/profiles/bd_stall_radar_task.md"

# W15: this guard is what stands between a missing profile and a launched EMPTY PROMPT.
# The `$(cat "$TASK_FILE")` below sits in a command substitution used as an ARGUMENT, and
# `set -e` does not propagate a failure from there. Same shape as
# bin/run_m1_signal_scan_cc.sh. `-r`, not `-f`.
[ -r "$TASK_FILE" ] || { echo "bd-stall-radar: task file not readable: $TASK_FILE" >&2; exit 1; }
SKILLS_DIR="${PRAETORIUM_SKILLS_DIR:-$HOME/agent-workforce/skills/claudius}"
# A --plugin-dir path that does not exist is silent — exit 0, no diagnostic, no skills.
[ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || { echo "bd-stall-radar: skills plugin not readable: $SKILLS_DIR" >&2; exit 1; }

# No MCP servers by design: Notion I/O is the kernel's REST call, priorities are disk or
# the qmd CLI inside the kernel, never an MCP tool. Declare AGENT_MCP_DEPS=none in the job
# env so agent_propose.sh skips the daemon probes too. No vault_sync_guard — the radar
# flags inward and nothing leaves the box.
cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-sonnet-5 \
  --permission-mode dontAsk \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --plugin-dir "$SKILLS_DIR" \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep"
