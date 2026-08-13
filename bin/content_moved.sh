#!/usr/bin/env bash
# content_moved.sh — the AGENT_VERIFY_CMD target for augustus-content (NUC-46).
#
# agent_propose.sh runs this only when the runtime exited 0, and turns a non-zero here
# into rc=91 / SILENT-FAIL. Its whole reason to exist is that a zero exit is not
# evidence the work happened: this asks the board, not the run's own prose.
#
# It passes on either of two things:
#   - the board differs from the snapshot the runtime took before dispatching, or
#   - the runtime recorded a `decline_event=<id>` — augustus said, in his own hand and
#     under his own key, that there was nothing to draft.
# The decline record is bounded trust and deliberately carries the relay event id, so
# "he declined" is a claim Dave can check (`buzz social event --event <id>`) rather
# than a boolean the runtime asserted about itself. Without it every legitimately
# quiet night would record as FAIL, which is the NUC-44 mistake pointed the other way.
#
# A missing or unreadable snapshot fails. So does an unreadable board — "I could not
# look" must never resolve to "nothing changed".
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIGEST_BIN="${CONTENT_DIGEST_BIN:-$BIN_DIR/content_board_digest.sh}"
SNAPSHOT="${CONTENT_BOARD_SNAPSHOT:-$HOME/agent-workforce/var/content_board.snapshot}"

log() { printf 'content_moved: %s\n' "$*"; }

if [ ! -r "$SNAPSHOT" ]; then
  log "no board snapshot at $SNAPSHOT — the runtime never took a baseline"
  exit 1
fi

# The runtime appends `key=value` metadata after the digest lines. Digest rows are
# `<page-id>:<status>` and never contain `=`, so stripping the metadata cannot eat one.
before=$(grep -v '^[a-z_][a-z0-9_]*=' "$SNAPSHOT")

if ! current=$("$DIGEST_BIN"); then
  log "the board could not be read — refusing to certify it as unchanged"
  exit 1
fi

if [ "$current" != "$before" ]; then
  log "board moved since the pre-run snapshot"
  exit 0
fi

decline=$(sed -n 's/^decline_event=//p' "$SNAPSHOT" | tail -1)
if [ -n "$decline" ]; then
  log "board unchanged, but augustus declined on the record (event $decline)"
  exit 0
fi

log "board unchanged and no decline on the record — nothing was drafted"
exit 1
