#!/usr/bin/env bash
# Launcher for the Brave Search MCP HTTP daemon (brave-mcp.service, NUC-21). Logs each launch
# and whether BRAVE_API_KEY reached the process — the one fact praetorium-status.sh reads back —
# then execs the real server with the unit's args. Moved here from ~/.hermes/bin at T6.1
# (2026-09-16); the daemon serves the fleet and never depended on that tree.
# BRAVE_MCP_LOG and BRAVE_MCP_SERVER exist for the fixture test only; unset in production.
LOG="${BRAVE_MCP_LOG:-$HOME/agent-workforce/logs/brave_mcp.log}"
mkdir -p "$(dirname "$LOG")"
if [ -n "${BRAVE_API_KEY:-}" ]; then keystate="set(len=${#BRAVE_API_KEY})"; else keystate="MISSING"; fi
printf '%s launch pid=%s key=%s\n' "$(date -Is)" "$$" "$keystate" >> "$LOG"
export PATH="/usr/bin:$PATH"
exec "${BRAVE_MCP_SERVER:-npx}" -y @brave/brave-search-mcp-server "$@"
