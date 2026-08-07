#!/usr/bin/env bash
# Completion summary for the change-triggered content dispatch — the `summary` payload.
#
# The unit ticks four times an hour and almost every tick is a no-op by design, so the
# quiet poll stays silent: a channel that announces "nothing happened" 96 times a day
# stops being read, and the two ticks that mattered go with it.
#
# ExecStartPost cannot see ExecStart's stdout, so the decision is read back from the
# log content_change_dispatch.sh already tees, bounded to the lines this invocation
# wrote. Every non-quiet decision delivers — including the fail-soft Notion read,
# which is the one outcome that leaves state deliberately unchanged and would
# otherwise be indistinguishable from a genuinely quiet tick.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/delivery_common.sh
. "$BIN_DIR/delivery_common.sh"

MARKER="${DELIVERY_RUN_MARKER:-}"
TASK="${DELIVERY_TASK:-augustus-content}"
DISPATCH_LOG="${DISPATCH_LOG:-$HOME/agent-workforce/logs/content_change_dispatch.log}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] Content dispatch}"

# shellcheck source=bin/run_record.sh
. "$BIN_DIR/run_record.sh"
# shellcheck source=bin/content_state.sh
. "$BIN_DIR/content_state.sh"

# A quiet tick spends nothing, so the unit's `none` stands; the ticks that dispatch a
# draft run are attributed to whatever profile that run recorded.
DELIVERY_RUNTIME=$(run_runtime "$DELIVERY_RUNTIME")

run_lines() {  # the log lines this invocation wrote, stripped of timestamp and prefix
  local since line stamp
  since=$(marker_epoch)
  [ -r "$DISPATCH_LOG" ] || return 0
  tail -40 "$DISPATCH_LOG" | while IFS= read -r line; do
    stamp=${line%% *}
    [ "$(date -d "$stamp" +%s 2>/dev/null || echo 0)" -ge "$since" ] || continue
    printf '%s\n' "${line#* content_change_dispatch: }"
  done
}

lines=$(run_lines)

if [ -z "$lines" ]; then
  note "no dispatch log lines for this run"
  delivery_handoff --subject "$SUBJECT" \
    --message "the poll wrote no log line — content_change_dispatch.sh never reached a decision"
  exit 0
fi

case "$lines" in
  *"no new Picked rows"*)
    note "quiet tick — staying silent"
    exit 0 ;;
esac

summary=$(printf '%s\n%s\n%s' "$lines" "$(board_delta "$(marker_epoch)")" "$(corpus_line)")
note "${summary//$'\n'/ | }"
delivery_handoff --subject "$SUBJECT" --message "$summary"

exit 0
