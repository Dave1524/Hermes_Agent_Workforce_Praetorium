#!/bin/sh
# The seam that splits agent policy from Dave's own.
#
# The Claude Agent SDK spawns $CLAUDE_CODE_EXECUTABLE directly as an executable, so this
# stands in for `claude` and adds --settings on the way through. It is the only seam that
# works: --settings passed via BUZZ_ACP_AGENT_ARGS is accepted and silently ignored, because
# buzz-acp's index.js parses nothing from argv but --version.
#
# --settings is an ADDITIONAL settings source and deny lists union, so this file can only
# ever tighten. agent-settings.json is written as a full superset of ~/.claude/settings.json
# regardless, so the split holds whether the loader merges or replaces.
#
# Set from buzz-agent@.service, so it covers every claude-agent-acp agent session and no
# interactive session. Dave's ~/.claude/settings.json is untouched.
BREW=/home/linuxbrew/.linuxbrew/bin
PATH="$BREW:$HOME/.local/bin:$PATH"
export PATH

# Absolute path, never PATH resolution: this script is itself named `claude` to its caller,
# and a PATH lookup is the one way it could exec itself.
exec "$BREW/claude" --settings "$HOME/.config/buzz-team/agent-settings.json" "$@"
