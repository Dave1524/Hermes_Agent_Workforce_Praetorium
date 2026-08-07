#!/usr/bin/env bash
# Completion summary for the nightly Augustus content run — the `summary` payload.
#
# This job has no file artifact. Its output is Notion board rows, and attaching an
# invented file would make the receipt certify something that does not exist, so the
# summary carries board state instead: which rows moved, what the duplicate-title gate
# was reading, and whether agent_propose.sh got far enough to record a run at all.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/delivery_common.sh
. "$BIN_DIR/delivery_common.sh"

TASK="${DELIVERY_TASK:-augustus-content}"
MARKER="${DELIVERY_RUN_MARKER:-}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] Augustus content}"

# shellcheck source=bin/run_record.sh
. "$BIN_DIR/run_record.sh"
# shellcheck source=bin/content_state.sh
. "$BIN_DIR/content_state.sh"

DELIVERY_RUNTIME=$(run_runtime "$DELIVERY_RUNTIME")

content_summary() {  # content_summary <run-line>
  printf '%s\n%s\n%s' "$(board_delta "$(marker_epoch)")" "$(corpus_line)" "$1"
}

record=$(run_record)
if [ -z "$record" ]; then
  note "no cost.log record for task=$TASK"
  delivery_handoff --subject "$SUBJECT" \
    --message "$(content_summary "run: NO RECORD — the run ended before agent_propose.sh wrote one")"
  exit 0
fi

if ! is_this_run "$record"; then
  note "newest record for task=$TASK predates this run"
  delivery_handoff --subject "$SUBJECT" \
    --message "$(content_summary "run: NO RECORD — the newest for $TASK is from $(field "$record" ts)")"
  exit 0
fi

summary=$(content_summary "run: $(field "$record" outcome) in $(field "$record" run_seconds)s")
note "${summary//$'\n'/ | }"
delivery_handoff --subject "$SUBJECT" --message "$summary"

exit 0
