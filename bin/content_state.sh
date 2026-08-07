#!/usr/bin/env bash
# What the content route's two producers actually changed, asked of the systems that
# know — never of the run's own prose. Not executable on its own.
#
# The corpus line is the one that earns its keep. published_corpus.py's fetch is
# deliberately soft: origin unreachable falls back to the last known ref, so the
# duplicate-title gate keeps answering "no collision" against a site it can no longer
# see, and the draft that follows looks exactly as confident as a correct one. A
# successful delivery is not evidence the gate ran, so every content message states
# what the gate was reading.
#
# The board line comes from Notion's own last_edited_time rather than from what the
# agent says it wrote, because those two disagree precisely when it matters.

# Both probes reach outside the box — a git fetch and a Notion call — so the directory
# they are resolved from is a seam, the same way DELIVER_BIN is one for the transport.
CONTENT_PROBE_DIR="${CONTENT_PROBE_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"

# Notion truncates last_edited_time to the minute, so a row written seconds after the
# marker can carry a stamp up to a minute before it. Widening the window trades a
# possible neighbouring edit for never dropping a row this run genuinely touched.
BOARD_EDGE_SECONDS=60

corpus_line() {
  local json
  if ! json=$(timeout "${CONTENT_CORPUS_TIMEOUT:-150}" \
                python3 "$CONTENT_PROBE_DIR/published_corpus.py" list --json 2>&1); then
    printf 'corpus: UNAVAILABLE — %s' "$(printf '%s' "$json" | tail -1 | cut -c1-200)"
    return
  fi
  printf '%s' "$json" | python3 -c '
import json, sys
f = json.load(sys.stdin)["freshness"]
sys.stdout.write("corpus: %s, tip age %sh" % (
    "fetched" if f["fetched"] else "stale", f["ref_age_hours"]))
' 2>/dev/null || printf 'corpus: UNAVAILABLE — freshness unreadable'
}

board_delta() {  # board_delta <since-epoch>
  local json
  if ! json=$(timeout "${CONTENT_BOARD_TIMEOUT:-90}" \
                python3 "$CONTENT_PROBE_DIR/notion_rest.py" board --json 2>&1); then
    printf 'board: UNAVAILABLE — %s' "$(printf '%s' "$json" | tail -1 | cut -c1-200)"
    return
  fi
  printf '%s' "$json" | python3 -c '
import datetime, json, sys

since = int(sys.argv[1]) - int(sys.argv[2])
touched = []
for row in json.load(sys.stdin):
    stamp = row.get("last_edited")
    if not stamp:
        continue
    when = datetime.datetime.fromisoformat(stamp.replace("Z", "+00:00")).timestamp()
    if when >= since:
        touched.append(row)
if not touched:
    sys.stdout.write("board: no rows changed")
else:
    sys.stdout.write("board: %d row(s) changed — %s" % (len(touched), "; ".join(
        "%s [%s]" % (r["angle"][:70], r["status"]) for r in touched)))
' "$1" "$BOARD_EDGE_SECONDS" 2>/dev/null || printf 'board: UNAVAILABLE — rows unreadable'
}
