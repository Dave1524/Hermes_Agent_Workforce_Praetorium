#!/usr/bin/env bash
# One notice line for a board brief run (Dev Plan B2): the card's id and where it now waits,
# never the brief. Silent on a quiet tick — a run that picked no card writes no cost.log record,
# so there is nothing to attribute and nothing to say. A failed run is the unit's OnFailure.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/delivery_common.sh
. "$BIN_DIR/delivery_common.sh"

TASK="${DELIVERY_TASK:-}"
MARKER="${DELIVERY_RUN_MARKER:-}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] ${TASK:-board brief}}"
ATTEMPT_LOG="${AGENT_ATTEMPT_LOG:-$HOME/agent-workforce/logs/last-attempt/${TASK}.log}"

# shellcheck source=bin/run_record.sh
. "$BIN_DIR/run_record.sh"

DELIVERY_RUNTIME=$(run_runtime "$DELIVERY_RUNTIME")

record=$(run_record)
{ [ -n "$record" ] && is_this_run "$record"; } || { note "quiet tick: no run record for task=${TASK:-<unset>}"; exit 0; }

card=$(field "$record" proposal)
case "$(field "$record" outcome)" in
  BOARD) line="card \`$card\`: brief in Refine" ;;
  NOPROPOSAL)
    reason=$(grep '^DECLINE:' "$ATTEMPT_LOG" 2>/dev/null | tail -1)
    line="brief run declined — ${reason#DECLINE: }" ;;
  *) exit 0 ;;
esac
note "$line"
delivery_handoff --subject "$SUBJECT" --message "$line" --note "$line"
exit 0
