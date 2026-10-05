#!/usr/bin/env bash
# cc_run.sh <claude-bin> <args…> — the one seam between a scheduled runner and Claude Code.
#
# With AGENT_USAGE_JSON unset this is `exec "$@"`, argv byte for byte: hand runs and the smoke
# suites see no wrapper beyond the variables exported below (the close-loop opt-out, and the
# headless token when bin/claude_oauth_env.sh finds one). With it set, claude is asked
# for its JSON envelope, which bin/cc_envelope.py splits: `.result` goes to stdout exactly as
# text mode printed it — the five readers of runner stdout (^DECLINE:, PROVIDER_ERROR_RE,
# proposal_or_decline.sh, the contract checks, deliver_proposal.sh) are unchanged — and the
# envelope lands atomically at $AGENT_USAGE_JSON for the receipt's usage and cost. claude's
# own exit status is returned.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# A headless run must end on its own answer. The vault's project Stop hook
# (.claude/hooks/close-loop-check.sh) injects a close-the-loop reminder once 30-60 min have
# passed since its last check — one /tmp timer for every session on the machine. Under -p the
# model answers it and that answer replaces `.result`: nine false merge notices from the Mac's
# hourly merge watcher. Claude Code tells a hook nothing about print mode, so the caller opts
# out, and the hook stands down on exactly `off`. No runner's cwd carries the vault's .claude/
# today (the box-safe mirror is allowlist-only); a canonical vault checkout does. Unconditional:
# no scheduled run wants the reminder.
export CLAUDE_CLOSE_LOOP_CHECK=off

# shellcheck source=bin/claude_oauth_env.sh
. "$BIN_DIR/claude_oauth_env.sh"
claude_oauth_export

if [ -z "${AGENT_USAGE_JSON:-}" ]; then
  exec "$@"
fi

mkdir -p "$(dirname "$AGENT_USAGE_JSON")" 2>/dev/null
capture="$(mktemp "$AGENT_USAGE_JSON.XXXXXX" 2>/dev/null)" || {
  echo "cc_run: cannot capture at $AGENT_USAGE_JSON — running without usage" >&2
  exec "$@"
}

"$@" --output-format json >"$capture"
rc=$?
python3 "$BIN_DIR/cc_envelope.py" "$capture" "$AGENT_USAGE_JSON"
exit "$rc"
