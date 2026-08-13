#!/usr/bin/env bash
# NUC-36 — overnight morning report, Claude Code runtime variant.
# Runs the morning report as headless Claude Code (Sonnet) on the box's own Claude
# subscription instead of hermes/marcus on OpenRouter — wired in as AGENT_RUNTIME_CMD
# via ~/.config/agent-workforce/overnight_morning_report.env. This was the last job
# still on the OpenRouter path; it failed 2026-07-29/30/31 on HTTP 402 once the
# account balance hit zero. Follows the proven run_m1_signal_scan_cc.sh shape.
#
# agent_propose.sh (AGENT_RUN_MODE=ops) still owns lock, preflight, retry, cost.log
# and the AGENT_VERIFY_CMD artifact assertion; this script is only the "brain" it execs.
# deliver_report.sh (ExecStartPost) still posts the resulting file to Discord.
#
# No vault freshness gate here, unlike run_daily_rhythm_cc.sh: this report reads systemd,
# journals, logs and the inbox worktree — never the vault mirror — so a stale mirror is
# not a reason to withhold it, and gating on one would invent a new way to lose the report.
#
# Revert: restore ~/.config/agent-workforce/overnight_morning_report.env.bak-* (the hermes
# invocation is preserved there verbatim).
set -euo pipefail

# Every report written under the hermes path was mode 600; Claude Code writes with the
# inherited umask (0002 under systemd here), which would silently widen them to 664.
umask 077

CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
WORKDIR="${MORNING_REPORT_WORKDIR:-$HOME/agent-workforce}"
MODEL="${MORNING_REPORT_MODEL:-sonnet}"
TASK_FILE="$WORKDIR/profiles/overnight_morning_report_cc_task.md"

[ -r "$TASK_FILE" ] || { echo "overnight-morning-report: task file not readable: $TASK_FILE" >&2; exit 1; }

mkdir -p "$HOME/logs/overnight"

# No MCP servers by design (toolset trim, 2026-07-20): cwd here is $HOME/agent-workforce, NOT
# a vault checkout — the job reads ~/agent-worktrees/inbox by absolute path with Read/Glob/
# Grep. Declare AGENT_MCP_DEPS=none in the job env to skip the daemon probes too.
cd "$WORKDIR"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model "$MODEL" \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Glob,Grep"
