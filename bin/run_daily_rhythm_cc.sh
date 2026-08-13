#!/usr/bin/env bash
# NUC-45 — the headless Claude Code "brain" both daily-rhythm jobs exec, following the
# proven m1-signal-scan shape (run_m1_signal_scan_cc.sh): box subscription, $0 OpenRouter
# spend, no MCP servers, explicit tool allowlist. agent_propose.sh (AGENT_RUN_MODE=ops)
# still owns lock, retry, cost.log and the AGENT_VERIFY_CMD artifact assertion.
#
# The one thing added here is the freshness gate. These two jobs read the vault mirror
# and speak with confidence about Dave's day; a mirror that silently froze (as it did
# 2026-07-23 → 07-27) would produce a plan that is wrong rather than absent. So the gate
# runs BEFORE the agent launches and a refusal is a hard failure — the unit fails, the
# OnFailure alert fires, and Dave learns the mirror is stale instead of trusting a
# confident briefing built from four-day-old priorities.
set -euo pipefail

job="${1:-}"
case "$job" in
  daily-plan|eod-summary) ;;
  *) echo "usage: $(basename "$0") daily-plan|eod-summary" >&2; exit 2 ;;
esac

BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
GUARD="${VAULT_SYNC_GUARD:-$BIN_DIR/vault_sync_guard.sh}"
WORKDIR="${DAILY_RHYTHM_WORKDIR:-$HOME/agent-workforce}"
MODEL="${DAILY_RHYTHM_MODEL:-sonnet}"

case "$job" in
  daily-plan)  TASK_FILE="$WORKDIR/profiles/daily_plan_task.md" ;;
  eod-summary) TASK_FILE="$WORKDIR/profiles/eod_summary_task.md" ;;
esac
[ -r "$TASK_FILE" ] || { echo "$job: task file not readable: $TASK_FILE" >&2; exit 1; }

if ! "$GUARD" check; then
  echo "$job: REFUSING to run — the vault mirror is dirty or stale (see above)." >&2
  echo "$job: a briefing off this tree would be confidently wrong. Route the drift, then re-run." >&2
  exit 1
fi

# No MCP servers by design (toolset trim, 2026-07-20): cwd here is $HOME/agent-workforce, NOT
# a vault checkout — the job reads ~/vault by absolute path with Read/Glob/Grep and needs no
# qmd retrieval. Declare AGENT_MCP_DEPS=none in the job env to skip the daemon probes too.
cd "$WORKDIR"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model "$MODEL" \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Glob,Grep"
