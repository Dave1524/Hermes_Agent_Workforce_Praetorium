#!/usr/bin/env bash
# Artifact-lookup adapter: find the report this unit just produced and hand it to
# bin/deliver.sh. Wired as ExecStartPost on the report-producing units.
#
# NUC-30 introduced this as a Discord sender; the 2026-08-04 Buzz migration took the
# transport out. What remains here is the only part that is genuinely per-unit — which
# directory, which glob, which subject (REPORT_DIR / REPORT_GLOB / REPORT_SUBJECT, set
# in each unit's Environment= lines). Delivery, freshness enforcement and the receipt
# belong to deliver.sh, the single owner of both surfaces.
#
# FAIL-SOFT BY DESIGN: exits 0 on every path, so a delivery problem never marks the
# report unit failed (which would fire OnFailure=agent-alert@ for a non-event).
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVER_BIN="${DELIVER_BIN:-$BIN_DIR/deliver.sh}"

REPORT_DIR="${REPORT_DIR:-$HOME/logs/overnight}"
REPORT_GLOB="${REPORT_GLOB:-morning-report-*.md}"
REPORT_SUBJECT="${REPORT_SUBJECT:-[Praetorium] Morning report}"

# A caller with no route configured keeps exactly its pre-migration behaviour —
# Discord only — and deliver.sh records a config_error receipt, so an unported
# producer surfaces in the dual-run audit instead of defaulting into someone
# else's channel.
ROUTE="${DELIVERY_ROUTE:-unrouted}"
JOB="${DELIVERY_JOB:-deliver_report.sh}"
RUNTIME="${DELIVERY_RUNTIME:-${AGENT_PROFILE:-unknown}}"

# The weaker of the two freshness anchors, kept for units that have no run marker yet:
# 26 hours covers one skipped day. DELIVERY_RUN_MARKER supersedes it when present.
MAX_REPORT_AGE_SECS=$(( 26 * 3600 ))

log="$HOME/logs/deliver_report.log"
mkdir -p "$HOME/logs" 2>/dev/null || true
note() {
  printf '%s deliver_report: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    >> "$log" 2>/dev/null || true
}

# Newest report by filename (the timestamped names sort lexically = chronologically).
latest=""
if [ -d "$REPORT_DIR" ]; then
  # REPORT_GLOB must stay unquoted here — quoting it would defeat the glob.
  # shellcheck disable=SC2086
  latest=$(ls -1 $REPORT_DIR/$REPORT_GLOB 2>/dev/null | sort | tail -1)
fi

if [ -z "$latest" ] || [ ! -s "$latest" ]; then
  note "no $REPORT_GLOB found in $REPORT_DIR — nothing to deliver"
  exit 0
fi

args=(--job "$JOB" --route "$ROUTE" --subject "$REPORT_SUBJECT" --file "$latest"
      --runtime "$RUNTIME" --max-age-secs "$MAX_REPORT_AGE_SECS")
[ -n "${DELIVERY_RUN_MARKER:-}" ] && args+=(--run-marker "$DELIVERY_RUN_MARKER")

if "$DELIVER_BIN" "${args[@]}"; then
  note "handed $(basename "$latest") to deliver.sh (route=$ROUTE)"
else
  note "deliver.sh returned non-zero for $(basename "$latest") (non-fatal)"
fi

exit 0
