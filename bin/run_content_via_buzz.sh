#!/usr/bin/env bash
# run_content_via_buzz.sh — the AGENT_RUNTIME_CMD target that runs the nightly content
# task on buzz-agent@augustus instead of hermes → OpenRouter (NUC-46).
#
# OpenRouter has answered `402 Insufficient credits` on every augustus-content call
# since ~2026-07-25. The same Editor-in-Chief already runs on this box on the codex-acp
# harness at zero marginal cost, so this dispatches to him over Buzz and waits.
#
# THE WHOLE CONTRACT IS THE EXIT CODE, and it has three states, not two:
#   4 (CRASH_EXIT)  the trigger never landed — nobody was asked. agent_propose.sh
#                   records CRASHED and does NOT retry.
#   1               augustus was asked and produced nothing within the wait. Recorded
#                   as FAIL and retried.
#   0               a pre-dispatch `Picked` row reached `Draft`, or augustus replied
#                   `DECLINE: <reason>`.
# NUC-44 is the reason those are separate: for twenty nights a crashed run logged as
# NOPROPOSAL and read exactly like a quiet night. A dispatched-but-silent run is a
# failure, never a decline — a decline has an author.
#
# TRANSPORT OWNERSHIP. bin/deliver.sh is the only script that may call
# `buzz messages send` (tests/test_buzz_unit_wiring.sh enforces it), so the trigger goes
# out through the route table and this script never touches a credential. The kind
# (45001) and the mention (augustus's pubkey) are therefore properties of
# bin/buzz_routes.env, not of anything here. Reading the channel back is not a
# transport and stays local.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DIGEST_BIN="${CONTENT_DIGEST_BIN:-$BIN_DIR/content_board_digest.sh}"
CORPUS_BIN="${CONTENT_CORPUS_BIN:-$BIN_DIR/published_corpus.py}"
DELIVER_BIN="${DELIVER_BIN:-$BIN_DIR/deliver.sh}"
HELPER="${BUZZ_HELPER_BIN:-$BIN_DIR/buzz_publish.sh}"
ROUTES_FILE="${BUZZ_ROUTES_FILE:-$BIN_DIR/buzz_routes.env}"
AGENTS_FILE="${BUZZ_AGENTS_FILE:-$BIN_DIR/buzz_agents.env}"
RECEIPTS="${DELIVERY_RECEIPTS:-$HOME/logs/delivery-receipts.jsonl}"
SNAPSHOT="${CONTENT_BOARD_SNAPSHOT:-$HOME/agent-workforce/var/content_board.snapshot}"
IDENTITY="${BUZZ_SERVICE_IDENTITY:-praetorium}"
PROFILE="${CONTENT_TASK_PROFILE:-$HOME/agent-workforce/profiles/augustus_content_task.md}"
JOB="${AGENT_TASK_SLUG:-augustus-content}"
ROUTE=content
ENTRY_POINT="${CONTENT_ENTRY_POINT:-nightly}"

CRASH_EXIT=4

wait_secs="${AGENT_BUZZ_WAIT_SECONDS:-}"
[ -n "$wait_secs" ] || wait_secs=$(( ${AGENT_BUZZ_WAIT_MINUTES:-20} * 60 ))
poll_secs="${AGENT_BUZZ_POLL_SECONDS:-30}"

log() { printf '%s run_content_via_buzz: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*"; }

crash() { log "CRASH: $*"; exit "$CRASH_EXIT"; }

channel=$(sed -n "s/^ROUTE_${ROUTE}=//p" "$ROUTES_FILE" 2>/dev/null | tail -1 | tr -d "\"' \\r")
augustus=$(sed -n 's/^AGENT_augustus=//p' "$AGENTS_FILE" 2>/dev/null | tail -1 | tr -d "\"' \\r")
[ -n "$channel" ]  || crash "route '$ROUTE' has no channel UUID in $ROUTES_FILE"
[ -n "$augustus" ] || crash "augustus has no pubkey in $AGENTS_FILE"
case "$ENTRY_POINT" in
  nightly|picked-change) ;;
  *) crash "CONTENT_ENTRY_POINT must be nightly or picked-change (got '$ENTRY_POINT')" ;;
esac

# ── 1. baseline ───────────────────────────────────────────────────────────────────
# Taken BEFORE the trigger goes out, so the comparison cannot straddle augustus's own
# writes. A board that will not read is a crash, not a slow night: dispatching against
# an unknown baseline would make every later comparison meaningless.
baseline=$("$DIGEST_BIN") \
  || crash "the board could not be read — refusing to dispatch on an unknown baseline"

mkdir -p "$(dirname "$SNAPSHOT")" 2>/dev/null || true
# The trailing newline is load-bearing: `decline_event=` is appended to this file later and
# content_moved.sh strips metadata by line anchor. Written without it, the record fuses onto
# the last digest row, the strip misses it, and the verify reports a board that never moved
# — passing on its own bookkeeping. Live on 2026-08-13's first run.
printf '%s\n' "$baseline" >"$SNAPSHOT" \
  || crash "could not write the board snapshot at $SNAPSHOT"

# ── 1b. arm the corpus gate, on the HOST ──────────────────────────────────────────
# augustus cannot do this himself and never could. He is the only agent on codex-acp, and
# his bwrap namespace mounts a tmpfs over ~/.ssh; the site remote is `git@github-website:`,
# an ssh-config alias, so with no ssh config the name does not resolve. For nine consecutive
# nights (2026-08-14 → 09-06) he reported the corpus unreachable while the host-side receipt
# seconds later read `corpus: fetched`. It is a transport split, not a namespace question:
# ~/agent-workforce/var/ is already inside his dev-bind and under no tmpfs, so the host
# writes the snapshot and he reads it with no credential and no widening — which is the
# rule, not merely the cheaper option (~/CLAUDE.md).
#
# A crash, not a warning, for the same reason the baseline above is one: a run dispatched
# without the duplicate-title gate produces a draft that looks exactly as confident as a
# correct one. Ten posts shipped that way between 09-02 and 09-05.
if ! corpus_note=$("$CORPUS_BIN" snapshot 2>&1); then
  crash "the corpus gate could not be armed, so nobody was asked — augustus cannot reach origin from his namespace and would draft with the duplicate-title check not running: ${corpus_note//$'\n'/ }"
fi
log "corpus gate armed — ${corpus_note//$'\n'/ }"

dispatch_epoch=$(date +%s)

# ── 2. dispatch ───────────────────────────────────────────────────────────────────
# A trigger, not the task. The profile is the single source of truth for what the job
# is; resending its text nightly would give it two places to drift, and augustus reads
# the deployed copy anyway.
read -r -d '' trigger <<EOF || true
Nightly content run. Read ${PROFILE} and execute it now.

Notion is reachable on your harness through the broker socket, so the tool calls in
that profile work unmodified — run them as written, including the NUC-44 limits.

If you judge there is nothing to draft, reply in this channel with a single line
beginning \`DECLINE:\` and the reason. Silence is recorded as a failed run.
EOF

receipts_before=0
[ -f "$RECEIPTS" ] && receipts_before=$(wc -l <"$RECEIPTS" 2>/dev/null || echo 0)

# deliver.sh is fail-soft by contract — it exits 0 on a rejected send and files a
# categorized receipt instead. The receipt is therefore the only evidence that the
# trigger actually reached the relay, and `--mention` of a non-member fails the WHOLE
# send, so this is also how a membership regression surfaces.
DELIVER_DISCORD=0 "$DELIVER_BIN" \
  --job "$JOB" --route "$ROUTE" --runtime buzz-augustus \
  --subject "[Praetorium] Augustus content — run now" \
  --message "$trigger" >/dev/null 2>&1

if ! run_id=$(python3 - "$RECEIPTS" "$receipts_before" "$JOB" <<'PY'
import json, sys
import re
path, before, job = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    with open(path) as f:
        lines = f.readlines()[before:]
except OSError:
    sys.exit(2)
for raw in reversed(lines):
    try:
        receipt = json.loads(raw)
    except ValueError:
        continue
    if receipt.get("job") != job:
        continue
    event_id = receipt.get("buzz_event_id", "")
    if receipt.get("buzz_result") == "ok" and re.fullmatch(r"[0-9a-f]{64}", event_id):
        print(event_id)
        sys.exit(0)
    sys.exit(1)
sys.exit(3)
PY
); then
  crash "the trigger was not published with a valid event id to route '$ROUTE' — augustus was never asked"
fi
# The relay event ID is the content run identity.  It joins the trigger receipt, attempt
# output, board snapshot, and (when this was a change-triggered run) the dispatch log
# without introducing another receipt store or a parallel database.
printf 'run_id=%s\nentry_point=%s\n' "$run_id" "$ENTRY_POINT" >>"$SNAPSHOT"
log "trigger published to $ROUTE (channel $channel, mention $augustus) run_id=$run_id entry_point=$ENTRY_POINT"

# ── 3. wait ───────────────────────────────────────────────────────────────────────
# `messages get`, never `messages thread`: thread returns only e-tagged replies, so a
# flat top-level answer reads as silence and a live reply times out as a failure.
# No --kinds filter either — praetorium publishes 45001 but augustus answers as 45003
# (forum comment), so a filter set from the route table would drop every reply he
# writes. Author + epoch are the gates; the kind is not.
# ONE reader, two sentinels. They differ only in the prefix they look for, and a second
# copy of the relay call is a second place for the author/epoch gates to drift.
sentinel_reply() {  # sentinel_reply <since-epoch> <prefix> -> "<event-id> <line>"
  local json
  json=$("$HELPER" "$IDENTITY" messages get --channel "$channel" \
           --since "$1" --limit 50 2>/dev/null) || return 1
  printf '%s' "$json" | python3 -c '
import json, sys

author, since, prefix = sys.argv[1], int(sys.argv[2]), sys.argv[3]
try:
    events = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
for event in events if isinstance(events, list) else []:
    if event.get("pubkey") != author or int(event.get("created_at", 0)) < since:
        continue
    for line in (event.get("content") or "").splitlines():
        # The empty prefix, used by the any-reply read at the deadline, matches every
        # line including blank ones, and would report an empty string as the reply that
        # ended the wait. (No apostrophes here: this block is inside a single-quoted -c.)
        if line.strip() and line.strip().startswith(prefix):
            sys.stdout.write(event.get("id", "") + " " + line.strip() + "\n")
            sys.exit(0)
sys.exit(1)
' "$augustus" "$1" "$2"
}

# A valid draft is deliberately narrower than any digest mutation.  The runner is allowed
# to certify only a page that was Picked in its own pre-dispatch baseline and is Draft now.
# An unrelated edit, Idea creation, deletion, or a status change in the other direction is
# useful diagnosis but is never an artifact from this run.
picked_to_draft_transition() {  # picked_to_draft_transition <current-digest> -> page id
  local current=$1 page status
  while IFS=: read -r page status; do
    [ "$status" = Picked ] || continue
    if grep -Fqx "$page:Draft" <<<"$current"; then
      printf '%s\n' "$page"
      return 0
    fi
  done <<<"$baseline"
  return 1
}

# THE OUTCOMES AUGUSTUS CAN NAME, as a table rather than a branch each. The three the
# header names are Picked-to-Draft (0), DECLINE: (0) and asked-but-silent (1). Every other
# sentinel is a reply that IS an answer and is NOT a decline — a skill section that no
# longer resolves, a mandatory step that exited non-zero.
#
# SKILL-READ-FAILED: was fixed here as a special case in 2026-08. RUN-FAILED: arrived on
# 2026-09-06 and fell through the identical hole, because a special case ends an instance
# and leaves the class alive. A new sentinel is now one row plus its message, and the
# verify gate pins this table against profiles/augustus_content_task.md in BOTH directions
# — so the next one fails a gate instead of costing twenty minutes in production.
#
# Failures precede DECLINE: a reply carrying both is a failed run, not a quiet night.
SENTINELS=(
  'SKILL-READ-FAILED: 1'
  'RUN-FAILED: 1'
  'DECLINE: 0'
)

sentinel_log() {  # sentinel_log <prefix> <event-id> <line>
  case "$1" in
    'SKILL-READ-FAILED:')
      log "augustus could not read the skill — $3"
      log "  (event $2) a named section did not resolve in the vault SKILL.md;"
      log "  this is a FAILURE, not a decline. Fix the section name or the heading, not the run." ;;
    'RUN-FAILED:')
      log "augustus could not complete a mandatory step — $3"
      log "  (event $2) a command the profile makes non-optional exited non-zero;"
      log "  this is a FAILURE, not a decline. Fix what it names, not the run." ;;
    'DECLINE:')
      # Recorded so content_moved.sh can pass an unmoved board without re-reading the
      # relay, and so the claim stays checkable: `buzz social event --event $2`.
      printf 'decline_event=%s\n' "$2" >>"$SNAPSHOT"
      log "owned-reply-evidences-decline run_id=$run_id entry_point=$ENTRY_POINT decline_event=$2"
      log "augustus declined (event $2) — nothing to draft" ;;
  esac
}

deadline=$(( dispatch_epoch + wait_secs ))
while :; do
  current=$("$DIGEST_BIN") || current=""
  if [ -n "$current" ] && page=$(picked_to_draft_transition "$current"); then
    printf 'page=%s from=Picked to=Draft\n' "$page" >>"$SNAPSHOT"
    log "content-board-transition-produced-draft run_id=$run_id entry_point=$ENTRY_POINT page=$page from=Picked to=Draft"
    exit 0
  fi

  for row in "${SENTINELS[@]}"; do
    hit=$(sentinel_reply "$dispatch_epoch" "${row%% *}") || continue
    [ -n "$hit" ] || continue
    sentinel_log "${row%% *}" "${hit%% *}" "${hit#* }"
    exit "${row##* }"
  done

  [ "$(date +%s)" -ge "$deadline" ] && break
  sleep "$poll_secs"
done

# ── 4. the deadline is not proof of silence ───────────────────────────────────────
# Before recording "no reply", ask whether there WAS one: the empty prefix matches any
# non-blank line augustus wrote after the dispatch. On 2026-09-07 he answered 110 seconds
# in, no branch matched, and the run spent the remaining 18 minutes to log the opposite of
# what happened — throwing away the only line that said what to fix.
# Deliberately OUTSIDE the poll loop. A catch-all inside it would fire on the first
# `STATUS:`-shaped progress line and kill a run that was still working.
if last_reply=$(sentinel_reply "$dispatch_epoch" '') && [ -n "$last_reply" ]; then
  log "content-board-transition-produced-draft failed run_id=$run_id entry_point=$ENTRY_POINT — no pre-dispatch Picked row reached Draft"
  log "owned-reply-evidences-decline failed run_id=$run_id entry_point=$ENTRY_POINT — the reply was not DECLINE:"
  log "augustus replied and no sentinel matched — ${last_reply#* }"
  log "  (event ${last_reply%% *}) the wait ended on his reply, not on the clock."
  log "  Add this prefix as one row in SENTINELS with a message in sentinel_log. The table"
  log "  and profiles/augustus_content_task.md are pinned to each other by the verify gate."
  exit 1
fi

log "content-board-transition-produced-draft failed run_id=$run_id entry_point=$ENTRY_POINT — no pre-dispatch Picked row reached Draft"
log "owned-reply-evidences-decline failed run_id=$run_id entry_point=$ENTRY_POINT — no post-dispatch Augustus DECLINE: reply"
log "no board movement and no reply within ${wait_secs}s — recording FAIL"
exit 1
