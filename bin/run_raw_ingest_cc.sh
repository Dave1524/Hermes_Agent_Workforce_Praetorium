#!/usr/bin/env bash
# Raw ingestion — Mechanism B (research pipeline brief, 2026-07-30). Diffs
# 05_knowledge/raw/ against 00_system/ingest_log.md and proposes ONE distillation for the
# oldest unprocessed source. Headless Claude Code, Opus 5, box subscription — same guarded
# shape as run_weekly_pre_assembly_cc.sh: agent_propose.sh owns worktree checkout, the
# _inbox/agents/ write boundary, commit/push and metrics; this script is only the "brain"
# it execs, gated by the same vault-freshness refusal.
#
# Why the guard: an ingest built off a frozen mirror is worse than no ingest — it could
# distill a source that's already superseded, or miss a contradiction a fresher mirror
# would have surfaced. Nothing watched 05_knowledge/raw/ before this; ingestion was
# entirely Mac-side interactive.
set -euo pipefail

BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
GUARD="${VAULT_SYNC_GUARD:-$BIN_DIR/vault_sync_guard.sh}"
INBOX="${RAW_INGEST_INBOX:-$HOME/agent-worktrees/inbox}"
TASK_FILE="${RAW_INGEST_TASK:-$HOME/agent-workforce/profiles/raw_ingest_cc_task.md}"

[ -r "$TASK_FILE" ] || { echo "raw-ingest: task file not readable: $TASK_FILE" >&2; exit 1; }

if ! "$GUARD" check; then
  echo "raw-ingest: REFUSING to run — the vault mirror is dirty or stale (see above)." >&2
  echo "raw-ingest: an ingest off this tree is worse than no ingest. Route the drift, then re-run." >&2
  exit 1
fi

# No MCP servers by design (toolset trim, 2026-07-20): this job reads the vault off disk via
# its `cd "$INBOX"` checkout with Read/Glob/Grep and needs no qmd retrieval. Declare
# AGENT_MCP_DEPS=none in the job env so agent_propose.sh skips the daemon probes too.
cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep"
