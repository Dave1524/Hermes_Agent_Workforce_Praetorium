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
#   0               the board moved, or augustus replied `DECLINE: <reason>`.
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

# ── 1. baseline ───────────────────────────────────────────────────────────────────
# Taken BEFORE the trigger goes out, so the comparison cannot straddle augustus's own
# writes. A board that will not read is a crash, not a slow night: dispatching against
# an unknown baseline would make every later comparison meaningless.
baseline=$("$DIGEST_BIN") \
  || crash "the board could not be read — refusing to dispatch on an unknown baseline"

mkdir -p "$(dirname "$SNAPSHOT")" 2>/dev/null || true
printf '%s' "$baseline" >"$SNAPSHOT" \
  || crash "could not write the board snapshot at $SNAPSHOT"

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

if ! python3 - "$RECEIPTS" "$receipts_before" "$JOB" <<'PY'
import json, sys
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
    sys.exit(0 if receipt.get("buzz_result") == "ok" else 1)
sys.exit(3)
PY
then
  crash "the trigger was not published to route '$ROUTE' — augustus was never asked"
fi
log "trigger published to $ROUTE (channel $channel, mention $augustus)"

# ── 3. wait ───────────────────────────────────────────────────────────────────────
# `messages get`, never `messages thread`: thread returns only e-tagged replies, so a
# flat top-level answer reads as silence and a live reply times out as a failure.
# No --kinds filter either — praetorium publishes 45001 but augustus answers as 45003
# (forum comment), so a filter set from the route table would drop every reply he
# writes. Author + epoch are the gates; the kind is not.
decline_event() {  # decline_event <since-epoch>
  local json
  json=$("$HELPER" "$IDENTITY" messages get --channel "$channel" \
           --since "$1" --limit 50 2>/dev/null) || return 1
  printf '%s' "$json" | python3 -c '
import json, sys

author, since = sys.argv[1], int(sys.argv[2])
try:
    events = json.load(sys.stdin)
except ValueError:
    sys.exit(1)
for event in events if isinstance(events, list) else []:
    if event.get("pubkey") != author or int(event.get("created_at", 0)) < since:
        continue
    for line in (event.get("content") or "").splitlines():
        if line.strip().startswith("DECLINE:"):
            sys.stdout.write(event.get("id", "") + "\n")
            sys.exit(0)
sys.exit(1)
' "$augustus" "$1"
}

deadline=$(( dispatch_epoch + wait_secs ))
while :; do
  current=$("$DIGEST_BIN") || current=""
  if [ -n "$current" ] && [ "$current" != "$baseline" ]; then
    log "board moved — augustus drafted"
    exit 0
  fi

  if event_id=$(decline_event "$dispatch_epoch") && [ -n "$event_id" ]; then
    # Recorded so content_moved.sh can pass an unmoved board without re-reading the
    # relay, and so the claim stays checkable: `buzz social event --event <id>`.
    printf 'decline_event=%s\n' "$event_id" >>"$SNAPSHOT"
    log "augustus declined (event $event_id) — nothing to draft"
    exit 0
  fi

  [ "$(date +%s)" -ge "$deadline" ] && break
  sleep "$poll_secs"
done

log "no board movement and no reply within ${wait_secs}s — recording FAIL"
exit 1
