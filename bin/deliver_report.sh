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
# shellcheck source=bin/delivery_common.sh
. "$BIN_DIR/delivery_common.sh"

REPORT_DIR="${REPORT_DIR:-$HOME/logs/overnight}"
REPORT_GLOB="${REPORT_GLOB:-morning-report-*.md}"
REPORT_SUBJECT="${REPORT_SUBJECT:-[Praetorium] Morning report}"

TASK="${DELIVERY_TASK:-}"
MARKER="${DELIVERY_RUN_MARKER:-}"

# shellcheck source=bin/run_record.sh
. "$BIN_DIR/run_record.sh"

DELIVERY_RUNTIME=$(run_runtime "$DELIVERY_RUNTIME")

# The weaker of the two freshness anchors, kept for units that have no run marker yet:
# 26 hours covers one skipped day. DELIVERY_RUN_MARKER supersedes it when present.
MAX_REPORT_AGE_SECS=$(( 26 * 3600 ))

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

args=(--subject "$REPORT_SUBJECT" --file "$latest" --max-age-secs "$MAX_REPORT_AGE_SECS")
[ -n "${DELIVERY_RUN_MARKER:-}" ] && args+=(--run-marker "$DELIVERY_RUN_MARKER")

note "handing $(basename "$latest")"
delivery_handoff "${args[@]}"

exit 0
