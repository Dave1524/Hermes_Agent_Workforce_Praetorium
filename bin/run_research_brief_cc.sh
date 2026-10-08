#!/usr/bin/env bash
# Research brief — the board's brief run (Dev Plan B2, design agent-board-refinement §3.6.3).
# Reads one Backlog card the wrapper picked and writes ONE file, $AGENT_CARD_DIR/brief.out.md;
# agent_propose.sh (AGENT_RUN_MODE=board) turns that file into the card's `brief` event after
# the model exits. The model never touches the ledger, the inbox worktree or the vault.
# Clones run_standing_research_cc.sh's shape: box subscription, no MCP servers, explicit tool
# allowlist — and no Edit, which this run has no use for.
#
# --model claude-opus-5 is the FULL model name, not the `opus` alias: an alias silently rolls
# forward on the next release (revisit against the approved-without-edit rate).
set -euo pipefail

BIN_DIR="$(cd "$(dirname "$0")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
GUARD="${VAULT_SYNC_GUARD:-$BIN_DIR/vault_sync_guard.sh}"
TASK_FILE="${RESEARCH_BRIEF_TASK:-$HOME/agent-workforce/profiles/research_brief_cc_task.md}"

# `-r`, not `-f`, and before the substitution below: a failing cat in an ARGUMENT does not trip
# `set -e`, so an unreadable profile would launch the agent with an empty prompt.
[ -r "$TASK_FILE" ] || { echo "research-brief: task file not readable: $TASK_FILE" >&2; exit 1; }
SKILLS_DIR="${PRAETORIUM_SKILLS_DIR:-$HOME/agent-workforce/skills/claudius}"
# A --plugin-dir path that does not exist is silent — exit 0, no diagnostic, no skills.
[ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || { echo "research-brief: skills plugin not readable: $SKILLS_DIR" >&2; exit 1; }
: "${AGENT_CARD_DIR:?research-brief: AGENT_CARD_DIR not set — agent_propose.sh exports it after the pick}"
[ -d "$AGENT_CARD_DIR" ] || { echo "research-brief: card directory missing: $AGENT_CARD_DIR" >&2; exit 1; }

if ! "$GUARD" check; then
  echo "research-brief: REFUSING to run — the vault mirror is dirty or stale (see above)." >&2
  exit 1
fi

# No MCP servers by design; declare AGENT_MCP_DEPS=none in the job env so agent_propose.sh
# skips the daemon probes too. qmd is reached through the Bash CLI, as on every S2 run.
cd "$AGENT_CARD_DIR"
exec "$BIN_DIR/cc_run.sh" "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode dontAsk \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --plugin-dir "$SKILLS_DIR" \
  --session-id "${AGENT_SESSION_ID:-$(uuidgen)}" \
  --allowedTools "Bash,Read,Write,Glob,Grep,WebSearch,WebFetch"
