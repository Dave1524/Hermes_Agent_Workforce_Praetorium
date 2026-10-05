#!/usr/bin/env bash
# Can headless claude authenticate right now? The one owner of "what an auth refusal looks like".
#
#   claude_auth_probe.sh            one real haiku turn through bin/cc_run.sh; prints one line
#                                   exit 0 ok | 3 refused (auth) | 1 unknown (anything else)
#   claude_auth_probe.sh classify   stdin is claude/buzz-acp output; exit 3 if it carries an
#                                   auth refusal, else 0
#
# `claude auth status` cannot answer this: it reads the credentials file and says
# loggedIn: true through a refresh that has already failed (measured 2026-10-05). Only a turn
# can. Unknown is never a refusal — a network blip must not read as an expired login, so a
# caller refuses only on 3.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
PROBE_MODEL="${CLAUDE_AUTH_PROBE_MODEL:-claude-haiku-4-5-20251001}"
PROBE_TIMEOUT="${CLAUDE_AUTH_PROBE_TIMEOUT:-120}"
SENTINEL=CLAUDE_AUTH_OK
AUTH_REFUSAL_RE='OAuth session expired|could not be refreshed|OAuth token has expired|Failed to authenticate|authentication_error|Invalid API key|Please run /login'
REFUSED=3

# Reads its whole input, never exits early: this script runs under pipefail, and a reader that
# stops at the first match SIGPIPEs its producer into a 141 that reads as "no match".
refusal_line() { awk -v re="$AUTH_REFUSAL_RE" '!found && $0 ~ re { print; found = 1 }'; }

classify() {
  local line
  line=$(refusal_line)
  [ -n "$line" ] || return 0
  printf '%s\n' "${line:0:200}"
  return "$REFUSED"
}

probe() {
  local out rc=0 t0 line
  t0=$(date +%s)
  out=$(cd / && env -u AGENT_USAGE_JSON timeout "$PROBE_TIMEOUT" "$BIN_DIR/cc_run.sh" "$CLAUDE_BIN" \
    -p "Reply with exactly this token and nothing else: $SENTINEL" \
    --model "$PROBE_MODEL" --strict-mcp-config --mcp-config '{"mcpServers":{}}' </dev/null 2>&1) || rc=$?
  line=$(printf '%s\n' "$out" | refusal_line)
  if [ -n "$line" ]; then
    echo "claude-auth: refused — ${line:0:200}"
    return "$REFUSED"
  fi
  if [ "$rc" -eq 0 ] && printf '%s\n' "$out" | tr -d '[:blank:]\r' | grep -x "$SENTINEL" >/dev/null; then
    echo "claude-auth: ok ($(( $(date +%s) - t0 ))s, $PROBE_MODEL)"
    return 0
  fi
  echo "claude-auth: unknown — exit $rc after $(( $(date +%s) - t0 ))s: $(printf '%s' "$out" | head -1 | cut -c1-200)"
  return 1
}

case "${1:-}" in
  classify) classify ;;
  "") probe ;;
  *) echo "usage: $(basename "$0") [classify]" >&2; exit 2 ;;
esac
