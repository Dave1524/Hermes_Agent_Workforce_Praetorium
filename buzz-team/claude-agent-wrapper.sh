#!/bin/sh
# The seam that splits agent policy from Dave's own.
#
# The Claude Agent SDK spawns $CLAUDE_CODE_EXECUTABLE directly as an executable, so this
# stands in for `claude` and adds flags on the way through. It is the only seam that
# works: flags passed via BUZZ_ACP_AGENT_ARGS are accepted and silently ignored, because
# buzz-acp's index.js parses nothing from argv but --version.
#
# Every flag goes AFTER "$@": the adapter passes --setting-sources=user,project,local and
# no --strict-mcp-config, and for a single-value option the last occurrence wins.
#
# --setting-sources= (none) is deliberate. The agents run with cwd /home/dave, so the
# "project" settings file is /home/dave/.claude/settings.json — Dave's user file (measured
# 2026-09-18: `project,local` still loaded his marketplace plugin, effort level and hooks).
# With no sources, only the per-agent --settings file applies. ~/CLAUDE.md and the
# auto-memory pool are not settings and still load.
#
# The per-agent settings file and the owner's skill tree are selected by BUZZ_AGENT_NAME,
# which buzz-agent@.service sets from %i. Both are rendered/deployed artefacts:
# agent-settings-<name>.json by bin/fleet_capabilities.py, skills/<name> by bin/deploy.
# A --plugin-dir path that does not exist is silent — exit 0, no skills — so the plugin
# manifest is proved readable first, exactly as the scheduled runners do.
#
# The adapter passes --mcp-config <json> with the bridge's env inlined — BUZZ_PRIVATE_KEY
# included — and /proc/<pid>/cmdline is world-readable where /proc/<pid>/environ is not.
# The JSON goes into a 0600 file under $XDG_RUNTIME_DIR (tmpfs, this user only) and the
# path takes its place; every other argument passes through untouched. Only the two-token
# form is rewritten because that is the form measured (2026-09-19); verify-fleet gate 14
# reads every cgroup argv for the key, so a changed adapter shows up there, not here.
# CLAUDE_WRAPPER_BREW exists for the suite's stub claude and nothing else.
BREW="${CLAUDE_WRAPPER_BREW:-/home/linuxbrew/.linuxbrew/bin}"
PATH="$BREW:$HOME/.local/bin:$PATH"
export PATH
MCP_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/buzz-team"

[ -n "${BUZZ_AGENT_NAME:-}" ] || { echo "claude-agent-wrapper: BUZZ_AGENT_NAME is unset — buzz-agent@.service sets it from %i" >&2; exit 1; }
SETTINGS="$HOME/.config/buzz-team/agent-settings-$BUZZ_AGENT_NAME.json"
SKILLS_DIR="$HOME/agent-workforce/skills/$BUZZ_AGENT_NAME"
[ -r "$SETTINGS" ] || { echo "claude-agent-wrapper: settings not readable: $SETTINGS" >&2; exit 1; }
[ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || { echo "claude-agent-wrapper: skills plugin not readable: $SKILLS_DIR" >&2; exit 1; }

session_id=$$
for arg in "$@"; do
  case "$arg" in --session-id=*) session_id="${arg#--session-id=}" ;; esac
done

write_mcp_config() {
  file="$MCP_DIR/mcp-$BUZZ_AGENT_NAME-$session_id.json"
  ( umask 077 && mkdir -p "$MCP_DIR" && printf '%s\n' "$1" > "$file" ) || return 1
  printf '%s' "$file"
}

n=$#; i=0; prev=""
while [ "$i" -lt "$n" ]; do
  arg="$1"; shift; i=$((i + 1))
  if [ "$prev" = "--mcp-config" ] && [ "${arg#\{}" != "$arg" ]; then
    arg=$(write_mcp_config "$arg") || { echo "claude-agent-wrapper: cannot write the MCP config under $MCP_DIR — refusing to pass it in argv" >&2; exit 1; }
  fi
  prev="$arg"
  set -- "$@" "$arg"
done

# Absolute path, never PATH resolution: this script is itself named `claude` to its caller,
# and a PATH lookup is the one way it could exec itself.
exec "$BREW/claude" "$@" \
  --strict-mcp-config \
  --setting-sources= \
  --settings "$SETTINGS" \
  --plugin-dir "$SKILLS_DIR"
