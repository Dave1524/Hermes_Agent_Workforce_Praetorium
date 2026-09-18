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
BREW=/home/linuxbrew/.linuxbrew/bin
PATH="$BREW:$HOME/.local/bin:$PATH"
export PATH

[ -n "${BUZZ_AGENT_NAME:-}" ] || { echo "claude-agent-wrapper: BUZZ_AGENT_NAME is unset — buzz-agent@.service sets it from %i" >&2; exit 1; }
SETTINGS="$HOME/.config/buzz-team/agent-settings-$BUZZ_AGENT_NAME.json"
SKILLS_DIR="$HOME/agent-workforce/skills/$BUZZ_AGENT_NAME"
[ -r "$SETTINGS" ] || { echo "claude-agent-wrapper: settings not readable: $SETTINGS" >&2; exit 1; }
[ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || { echo "claude-agent-wrapper: skills plugin not readable: $SKILLS_DIR" >&2; exit 1; }

# Absolute path, never PATH resolution: this script is itself named `claude` to its caller,
# and a PATH lookup is the one way it could exec itself.
exec "$BREW/claude" "$@" \
  --strict-mcp-config \
  --setting-sources= \
  --settings "$SETTINGS" \
  --plugin-dir "$SKILLS_DIR"
