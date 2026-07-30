#!/usr/bin/env bash
# Knowledge digest — Mechanism C (research pipeline brief, 2026-07-30). Reports what the
# *knowledge base* learned in the last 7 days (git-log delta over 05_knowledge/ and
# 11_entities/), distinct from the existing *activity* digest (weekly-pre-assembly).
# Headless Claude Code, Opus 5, box subscription — same guarded shape as
# run_weekly_pre_assembly_cc.sh: agent_propose.sh owns worktree checkout, the
# _inbox/agents/ write boundary, commit/push and metrics; this script is only the "brain"
# it execs, gated by the same vault-freshness refusal.
#
# Why the guard: a digest built off a frozen mirror is a confident wrong answer — exactly
# the failure vault_sync_guard.sh exists to prevent.
set -euo pipefail

BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
GUARD="${VAULT_SYNC_GUARD:-$BIN_DIR/vault_sync_guard.sh}"
INBOX="${KNOWLEDGE_DIGEST_INBOX:-$HOME/agent-worktrees/inbox}"
TASK_FILE="${KNOWLEDGE_DIGEST_TASK:-$HOME/agent-workforce/profiles/knowledge_digest_cc_task.md}"

[ -r "$TASK_FILE" ] || { echo "knowledge-digest: task file not readable: $TASK_FILE" >&2; exit 1; }

if ! "$GUARD" check; then
  echo "knowledge-digest: REFUSING to run — the vault mirror is dirty or stale (see above)." >&2
  echo "knowledge-digest: a digest off this tree would be confidently wrong. Route the drift, then re-run." >&2
  exit 1
fi

cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep"
