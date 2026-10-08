#!/usr/bin/env bash
# AGENT_VERIFY_CMD for the research-brief run (Dev Plan B2), on proposal_or_decline.sh's exit
# contract: a run is legitimate only if it produced THIS run's valid brief, or declined in its
# own output, or printed its own idempotent skip.
#
# exit 0: this run's brief.out.md passes `board.py validate-brief`, or its own `^DECLINE:`.
# exit 3: its own `^skip:` line (the card already carries a brief by this run id).
# exit 1: anything else, including a brief the template refuses.
#
# AGENT_CARD, AGENT_CARD_DIR, AGENT_RUN_STARTED_AT and AGENT_ATTEMPT_LOG are exported by
# agent_propose.sh; read, never recomputed. The sentinel is read from this attempt's own log,
# never from the shared agent_run.log (T7.1).
set -euo pipefail

SKIP_EXIT=3

: "${AGENT_CARD:?AGENT_CARD not set (exported by agent_propose.sh after the pick) — fail closed}"
: "${AGENT_CARD_DIR:?AGENT_CARD_DIR not set — fail closed}"
: "${AGENT_RUN_STARTED_AT:?AGENT_RUN_STARTED_AT not set — fail closed}"
: "${AGENT_ATTEMPT_LOG:?AGENT_ATTEMPT_LOG not set — fail closed}"

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD_PY="${BOARD_PY:-$BIN_DIR/board.py}"
brief_file="$AGENT_CARD_DIR/brief.out.md"

# Never `find … | grep -q`: grep exits on its first match and pipefail reports 141.
newer_than_run() {  # newer_than_run <path>
  [ -f "$1" ] || return 1
  [ -n "$(find "$(dirname "$1")" -maxdepth 1 -name "$(basename "$1")" \
            -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
}

brief_is_valid() {
  newer_than_run "$brief_file" || return 1
  python3 "$BOARD_PY" validate-brief "$brief_file" --card "$AGENT_CARD" >&2
}

attempt_says() {  # attempt_says <ERE>
  newer_than_run "$AGENT_ATTEMPT_LOG" || return 1
  grep -qE "$1" "$AGENT_ATTEMPT_LOG"
}

brief_is_valid && exit 0
attempt_says '^DECLINE:' && exit 0
attempt_says '^skip: ' && exit "$SKIP_EXIT"
exit 1
