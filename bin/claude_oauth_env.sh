# shellcheck shell=sh
# Sourced, never executed — the one reader of the headless Claude token file.
#
#   . bin/claude_oauth_env.sh && claude_oauth_export     export CLAUDE_CODE_OAUTH_TOKEN, or nothing
#   claude_oauth_expiry                                   print CLAUDE_OAUTH_EXPIRES (YYYY-MM-DD), or nothing
#
# Every claude the box launches goes through bin/cc_run.sh or buzz-team/claude-agent-wrapper.sh
# (tests/test_claude_auth.sh), and both source this. With the file present, headless
# claude authenticates with a long-lived `claude setup-token` token, so an interactive /login
# expiring no longer decides whether the fleet works (2026-10-02..05: ~75 h outage). With the
# file absent nothing changes: claude falls back to ~/.claude/.credentials.json.
#
# The file is Dave's to write, mode 600, never in a repo:
#   CLAUDE_CODE_OAUTH_TOKEN=<token>
#   CLAUDE_OAUTH_MINTED=YYYY-MM-DD
#   CLAUDE_OAUTH_EXPIRES=YYYY-MM-DD
# It is parsed, never sourced. A file group- or world-readable is refused out loud rather
# than used. The token is never printed.

claude_oauth_file() {
  printf '%s' "${CLAUDE_OAUTH_FILE:-$HOME/.config/agent-workforce/claude_oauth.env}"
}

claude_oauth_field() {
  sed -n "s/^$1=//p" "$(claude_oauth_file)" 2>/dev/null | tail -1 | tr -d "\"' \r"
}

claude_oauth_export() {
  [ -z "${CLAUDE_CODE_OAUTH_TOKEN:-}" ] || return 0
  [ -e "$(claude_oauth_file)" ] || return 0
  case "$(stat -c %a "$(claude_oauth_file)" 2>/dev/null)" in
    600 | 400) ;;
    *) echo "claude_oauth: $(claude_oauth_file) is not mode 600 — ignored, using the interactive login" >&2; return 0 ;;
  esac
  CLAUDE_CODE_OAUTH_TOKEN=$(claude_oauth_field CLAUDE_CODE_OAUTH_TOKEN)
  if [ -z "$CLAUDE_CODE_OAUTH_TOKEN" ]; then
    unset CLAUDE_CODE_OAUTH_TOKEN
    echo "claude_oauth: $(claude_oauth_file) carries no CLAUDE_CODE_OAUTH_TOKEN — using the interactive login" >&2
    return 0
  fi
  export CLAUDE_CODE_OAUTH_TOKEN
}

claude_oauth_expiry() {
  [ -e "$(claude_oauth_file)" ] || return 0
  claude_oauth_field CLAUDE_OAUTH_EXPIRES
}
