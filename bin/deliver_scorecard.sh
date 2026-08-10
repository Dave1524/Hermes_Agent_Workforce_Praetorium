#!/usr/bin/env bash
# Weekly scorecard summary adapter — ExecStartPost on scorecard.service.
#
# scorecard.sh is idempotent: an unchanged week leaves the digest byte-identical and
# it is not rewritten. So there is deliberately NO run-marker freshness check here —
# anchoring on the digest's mtime would silence the rollup on exactly the quiet weeks
# it exists to report, and this producer's silence policy is `never`. The summary is
# composed from current digest state, which is what a weekly rollup means.
#
# Aggregate counts only. scorecard.sh guarantees the digest is box-safe (no proposal
# slugs, no client-identifiable strings), and this adapter forwards named rows from
# it rather than the file, so nothing else in the inbox can ride along.
set -uo pipefail

# shellcheck source=bin/delivery_common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/delivery_common.sh"

DIGEST="${SCORECARD_DIGEST:-$HOME/agent-worktrees/inbox/_inbox/agents/_metrics/scorecard.md}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] Weekly scorecard}"

HEADLINE_ROWS=(
  'Agent runs (all-time)'
  'Proposal rate'
  'Error runs (last 7d)'
  'Acceptance rate (promoted+edited / decisions)'
  'Record window'
)

digest_value() {  # value cell of the digest's '| <label> | <value> |' row
  awk -F'|' -v want="$1" '
    { label = $2; value = $3
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", label)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", value) }
    label == want { print value; exit }
  ' "$DIGEST"
}

headline_summary() {
  local label value
  for label in "${HEADLINE_ROWS[@]}"; do
    value=$(digest_value "$label")
    [ -n "$value" ] && printf '%s: %s\n' "$label" "$value"
  done
}

if [ ! -s "$DIGEST" ]; then
  note "no digest at $DIGEST"
  delivery_handoff --subject "$SUBJECT" \
    --message "the weekly rollup produced no digest at $DIGEST"
  exit 0
fi

summary=$(headline_summary)
if [ -z "$summary" ]; then
  note "digest present but no headline rows matched"
  delivery_handoff --subject "$SUBJECT" \
    --message "digest present but none of the headline rows parsed — check $DIGEST"
  exit 0
fi

# The canvas is written on the good path only. `buzz canvas set` is a blind replace, so
# mirroring a degraded run would overwrite last week's readable rollup with "no digest at
# <path>" — the living document is the one place a failure must not be allowed to land.
note "summarising $(printf '%s\n' "$summary" | grep -c .) headline row(s)"
delivery_handoff --subject "$SUBJECT" --message "$summary" --canvas mirror

exit 0
