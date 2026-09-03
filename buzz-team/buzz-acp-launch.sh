#!/bin/sh
# buzz-acp takes --team-instructions as literal text and ships no
# --team-instructions-file counterpart, so the file is read here and handed over
# through the documented BUZZ_ACP_TEAM_INSTRUCTIONS env var.
set -eu

TEAM="$HOME/.config/buzz-team/TEAM.md"
if [ -r "$TEAM" ]; then
  BUZZ_ACP_TEAM_INSTRUCTIONS="$(cat "$TEAM")"
  export BUZZ_ACP_TEAM_INSTRUCTIONS
fi

exec "$HOME/.local/bin/buzz-acp" "$@"
