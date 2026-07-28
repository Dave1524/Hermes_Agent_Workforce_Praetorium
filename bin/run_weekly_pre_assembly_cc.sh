#!/usr/bin/env bash
# Weekly Review Pre-Assembly (NUC-24) — Claude Code runtime, following the proven
# m1-signal-scan shape (run_m1_signal_scan_cc.sh): box subscription, $0 OpenRouter spend,
# no MCP servers, explicit tool allowlist. agent_propose.sh (AGENT_RUN_MODE=proposal) owns
# worktree checkout, the _inbox/agents/ write boundary, commit/push and metrics.
#
# Why this exists: the job still ran hermes/claudius on OpenRouter after the 2026-07-24
# budget pause moved m1-signal-scan to Claude Code — it was the one job left behind. Its
# first run after the pause (Fri 2026-07-24 22:04) died three times on
# `HTTP 402: requires more credits ... requested up to 65536 tokens, but can only afford
# 15227` — OpenRouter reserves the worst-case cost of max_tokens up front, so a nearly
# spent monthly cap rejects the request before any inference happens.
#
# The freshness gate is the same one the daily-rhythm jobs use: this job reads the vault
# mirror and speaks with confidence about Dave's week, so a silently frozen mirror (as on
# 2026-07-23 → 07-28) would produce a pre-read that is wrong rather than absent.
set -euo pipefail

BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
GUARD="${VAULT_SYNC_GUARD:-$BIN_DIR/vault_sync_guard.sh}"
INBOX="${WEEKLY_PRE_ASSEMBLY_INBOX:-$HOME/agent-worktrees/inbox}"
TASK_FILE="${WEEKLY_PRE_ASSEMBLY_TASK:-$HOME/agent-workforce/profiles/weekly_pre_assembly_cc_task.md}"
MODEL="${WEEKLY_PRE_ASSEMBLY_MODEL:-sonnet}"

[ -r "$TASK_FILE" ] || { echo "weekly-pre-assembly: task file not readable: $TASK_FILE" >&2; exit 1; }

if ! "$GUARD" check; then
  echo "weekly-pre-assembly: REFUSING to run — the vault mirror is dirty or stale (see above)." >&2
  echo "weekly-pre-assembly: a pre-read off this tree would be confidently wrong. Route the drift, then re-run." >&2
  exit 1
fi

cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model "$MODEL" \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Glob,Grep"
