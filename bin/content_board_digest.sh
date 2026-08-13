#!/usr/bin/env bash
# content_board_digest.sh — the single owner of "what does the board look like".
#
# Prints one `<page-id>:<status>` line per row, sorted, and nothing else. The waiter in
# run_content_via_buzz.sh and the verifier in content_moved.sh both read this, so "the
# board moved" has exactly one definition and the two cannot drift into disagreeing
# about whether a run produced anything.
#
# Status only — deliberately not last_edited_time. Notion truncates that stamp to the
# minute and rewrites it for edits nobody asked for, which makes it a fine receipt line
# (bin/content_state.sh uses it for exactly that) and a terrible completion signal: a
# poll would fire on a stamp that moved while the row's Status sat where it was.
#
# FAIL-SOFT MEANS LOUD, NOT EMPTY. An unreadable board exits non-zero having printed
# nothing, because the one output this must never produce is a digest that compares
# equal to the previous one by accident — that is indistinguishable from "augustus did
# nothing" and would record a real failure as a quiet unchanged board.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NOTION_REST="${NOTION_REST_BIN:-$BIN_DIR/notion_rest.py}"

# --max-rows 0 overrides the NUC-44 per-run cap of 2. That cap exists to bound what one
# agent is asked to draft in a night; a digest that inherited it would call the board
# "unchanged" whenever the movement happened on row 3.
json=$(timeout "${CONTENT_BOARD_TIMEOUT:-90}" \
         python3 "$NOTION_REST" board --json --max-rows 0 2>/dev/null) || exit 1
[ -n "$json" ] || exit 1

printf '%s' "$json" | python3 -c '
import json, sys

try:
    rows = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
if not isinstance(rows, list):
    sys.exit(1)
lines = sorted("%s:%s" % (r.get("id", ""), r.get("status", "")) for r in rows)
sys.stdout.write("".join(l + "\n" for l in lines))
' || exit 1
