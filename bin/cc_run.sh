#!/usr/bin/env bash
# cc_run.sh <claude-bin> <args…> — the one seam between a scheduled runner and Claude Code.
#
# With AGENT_USAGE_JSON unset this is `exec "$@"`, byte for byte: hand runs and the smoke
# suites see no wrapper at all. With it set, claude is asked for its JSON envelope, which
# bin/cc_envelope.py splits: `.result` goes to stdout exactly as text mode printed it — the
# five readers of runner stdout (^DECLINE:, PROVIDER_ERROR_RE, proposal_or_decline.sh, the
# contract checks, deliver_proposal.sh) are unchanged — and the envelope lands atomically at
# $AGENT_USAGE_JSON for the receipt's usage and cost. claude's own exit status is returned.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
