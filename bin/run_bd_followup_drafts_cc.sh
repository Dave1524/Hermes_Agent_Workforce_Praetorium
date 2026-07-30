#!/usr/bin/env bash
# BD follow-up draft pack (2026-07-30). Turns every Dave-owed BD next action — stall-radar
# flags, Client Pipeline rows past their Next action date, and due BD Task Inbox rows —
# into up to five copy-paste-ready drafts. bd-stall-radar stops at flagging; the missing
# artifact is the text, not the decision (three overdue sends sat `Planned` for five days).
#
# Headless Claude Code, Opus 5, box subscription — same guarded shape as
# run_knowledge_digest_cc.sh: agent_propose.sh owns worktree checkout, the _inbox/agents/
# write boundary, commit/push and metrics; this script is only the "brain" it execs.
#
# Why the guard: a draft built off a frozen mirror asserts stale facts to a real client.
# That is the failure vault_sync_guard.sh exists to prevent, and here it leaves the box.
set -euo pipefail

BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
GUARD="${VAULT_SYNC_GUARD:-$BIN_DIR/vault_sync_guard.sh}"
INBOX="${BD_FOLLOWUP_INBOX:-$HOME/agent-worktrees/inbox}"
TASK_FILE="${BD_FOLLOWUP_TASK:-$HOME/agent-workforce/profiles/bd_followup_drafts_cc_task.md}"

[ -r "$TASK_FILE" ] || { echo "bd-followup-drafts: task file not readable: $TASK_FILE" >&2; exit 1; }

if ! "$GUARD" check; then
  echo "bd-followup-drafts: REFUSING to run — the vault mirror is dirty or stale (see above)." >&2
  echo "bd-followup-drafts: a draft off this tree asserts stale facts to a real client. Route the drift, then re-run." >&2
  exit 1
fi

cd "$INBOX"
exec "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep"
