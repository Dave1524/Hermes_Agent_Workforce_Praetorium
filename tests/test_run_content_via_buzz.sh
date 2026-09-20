#!/usr/bin/env bash
# NUC-46: the Buzz dispatch path for augustus-content.
#
# The real bin/deliver.sh is in the loop on purpose. The kind and the mention are
# properties of the ROUTE table, not of the dispatcher's argv, so stubbing deliver.sh
# would assert only that this script asked politely — the thing that actually has to
# hold is that a trigger leaves the box as kind 45001 carrying augustus's `p` tag.
# Only the credential helper is stubbed, which is also the seam that keeps this suite
# off the relay.
#
# The exit-code split is the whole point of criterion 5: 4 (CRASH_EXIT) means the
# trigger never landed and nobody was asked; 1 means augustus was asked and produced
# nothing. agent_propose.sh retries the second and not the first, and scorecard.sh
# counts them apart, so collapsing them is a silent regression.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUNNER="$REPO_ROOT/bin/run_content_via_buzz.sh"
DIGEST="$REPO_ROOT/bin/content_board_digest.sh"
MOVED="$REPO_ROOT/bin/content_moved.sh"
AUGUSTUS=$(sed -n 's/^AGENT_augustus=//p' "$REPO_ROOT/bin/buzz_agents.env" | tail -1 | tr -d "\"' \\r")
CHANNEL=$(sed -n 's/^ROUTE_content=//p' "$REPO_ROOT/bin/buzz_routes.env" | tail -1 | tr -d "\"' \\r")

fail=0

# pipefail has no place inside a boolean condition: `grep -q` exits on its first match,
# SIGPIPEs whatever feeds it, and the pipeline reports 141 for a pattern that WAS found.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# `yes` is still writing when grep -q exits, so this fails if and only if a condition
# is ever evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/nuc46.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# ── fixtures ──────────────────────────────────────────────────────────────────────
# One stub stands in for the credential helper on BOTH sides: deliver.sh execs it to
# send, the waiter execs it to read. It records argv so the assertions can read what
# the route table actually produced.
# deliver.sh passes the body on stdin (`--content -`) to escape MAX_ARG_STRLEN, so the
# trigger text is NOT in argv — asserting it there would read deliver.sh's Pulse note
# instead of the message augustus receives. Captured separately for that reason.
cat >"$WORK/helper.sh" <<'STUB'
#!/usr/bin/env bash
printf '%s\n' "$*" >>"$STUB_ARGV"
case "$*" in
  *"messages send"*)
    cat >"$STUB_STDIN" 2>/dev/null || true
    [ -s "$STUB_SEND_RC" ] && exit "$(cat "$STUB_SEND_RC")"
    printf '{"accepted":true,"event_id":"%s"}\n' "$(printf 'a%.0s' {1..64})"
    exit 0 ;;
  *"messages get"*)
    cat "$STUB_EVENTS" 2>/dev/null || printf '[]\n'
    exit 0 ;;
esac
exit 0
STUB
chmod +x "$WORK/helper.sh"

# The digest the runner sees. The board "moves" only when a case asks it to, and only
# from the second read on — the runner's first read is its pre-dispatch baseline, so a
# board that differed from call one would be a board that moved before anyone was asked.
# A case that needs the move later writes the read number into the move file.
cat >"$WORK/digest.sh" <<'STUB'
#!/usr/bin/env bash
n=$(cat "$STUB_DIGEST_N" 2>/dev/null || echo 0); n=$((n + 1))
printf '%s' "$n" >"$STUB_DIGEST_N"
[ -s "$STUB_DIGEST_RC" ] && exit "$(cat "$STUB_DIGEST_RC")"
move_at=$(cat "$STUB_DIGEST_MOVE" 2>/dev/null); move_at=${move_at:-2}
if [ -f "$STUB_DIGEST_MOVE" ] && [ "$n" -ge "$move_at" ]; then
  cat "$STUB_DIGEST_AFTER"
else
  cat "$STUB_DIGEST_BEFORE"
fi
STUB
chmod +x "$WORK/digest.sh"

# The corpus gate, stubbed at the CONTENT_CORPUS_BIN seam. The runner arms it on the HOST
# because augustus cannot: his bwrap namespace has a tmpfs over ~/.ssh, so the site remote's
# ssh-config alias does not resolve there. What is pinned here is the ORDER — armed before
# the trigger goes out — and that a gate which cannot be armed stops the run.
cat >"$WORK/corpus.sh" <<'STUB'
#!/usr/bin/env bash
printf 'corpus %s\n' "$*" >>"$STUB_ARGV"
[ -s "$STUB_CORPUS_RC" ] && exit "$(cat "$STUB_CORPUS_RC")"
echo "# corpus snapshot written to var/published_corpus.json — 2 articles, source=origin"
exit 0
STUB
chmod +x "$WORK/corpus.sh"

export STUB_ARGV="$WORK/argv.log"
export STUB_STDIN="$WORK/sent_body"
export STUB_SEND_RC="$WORK/send_rc"
export STUB_EVENTS="$WORK/events.json"
export STUB_DIGEST_RC="$WORK/digest_rc"
export STUB_DIGEST_BEFORE="$WORK/digest_before"
export STUB_DIGEST_AFTER="$WORK/digest_after"
export STUB_DIGEST_MOVE="$WORK/digest_move"
export STUB_DIGEST_N="$WORK/digest_n"
export STUB_CORPUS_RC="$WORK/corpus_rc"
export STUB_TURN_RECEIPTS="$WORK/turn-receipts"

printf 'page-1:Picked\npage-2:Draft\n' >"$STUB_DIGEST_BEFORE"
printf 'page-1:Draft\npage-2:Draft\n' >"$STUB_DIGEST_AFTER"

reset_case() {
  : >"$STUB_ARGV"; : >"$STUB_SEND_RC"; : >"$STUB_DIGEST_RC"; : >"$STUB_STDIN"
  : >"$STUB_CORPUS_RC"
  rm -f "$STUB_DIGEST_MOVE" "$STUB_DIGEST_N" "$WORK/board.snapshot"
  rm -rf "$STUB_TURN_RECEIPTS"
  printf '[]\n' >"$STUB_EVENTS"
}

# augustus's interaction receipt for one turn, as bin/interaction_receipt.py writes it —
# the runner joins on handoff.event, which is the trigger's relay event id (the run_id).
turn_receipt() {  # turn_receipt <outcome> <handoff-event> [reason]
  mkdir -p "$STUB_TURN_RECEIPTS"
  python3 - "$STUB_TURN_RECEIPTS" "$1" "$2" "${3:-}" <<'PY'
import json, pathlib, sys
d, outcome, event, reason = sys.argv[1:]
pathlib.Path(d, "0a0a-thread-0b03.json").write_text(json.dumps({
    "run_id": "0a0a-thread-0b03", "unit": "buzz-agent@augustus", "agent": "augustus",
    "vantage": "interaction", "started_at": "2026-09-14T10:00:00Z", "ended_at": "2026-09-14T10:00:11Z",
    "terminal": {"outcome": outcome, "reason": reason or None},
    "handoff": {"actor": "PRAETORIUM", "event": event, "recipient": "augustus"}}))
PY
}

# An augustus-authored event on the content channel, `secs` from now.
event() {  # event <pubkey> <content> [offset-secs]
  python3 - "$1" "$2" "${3:-5}" >"$STUB_EVENTS" <<'PY'
import json, sys, time
pub, content, off = sys.argv[1], sys.argv[2], int(sys.argv[3])
print(json.dumps([{"content": content, "created_at": int(time.time()) + off,
                   "id": "e" * 64, "kind": 45003, "pubkey": pub, "tags": []}]))
PY
}

run_dispatch() {  # run_dispatch [extra env assignments...]
  env DELIVERY_RECEIPTS="$WORK/receipts.jsonl" \
      BUZZ_DELIVER_HELPER="$WORK/helper.sh" \
      BUZZ_HELPER_BIN="$WORK/helper.sh" \
      CONTENT_DIGEST_BIN="$WORK/digest.sh" \
      CONTENT_CORPUS_BIN="$WORK/corpus.sh" \
      CONTENT_BOARD_SNAPSHOT="$WORK/board.snapshot" \
      CONTENT_TURN_RECEIPTS="$STUB_TURN_RECEIPTS" \
      AGENT_BUZZ_WAIT_SECONDS="${WAIT_SECS:-2}" \
      AGENT_BUZZ_POLL_SECONDS=1 \
      "$@" bash "$RUNNER" >"$WORK/out" 2>&1
}

echo '--- content_board_digest.sh: one definition of "what the board looks like" ---'
cat >"$WORK/fake_notion.py" <<'PY'
import json, os, sys
if os.environ.get("FAKE_NOTION_FAIL"):
    sys.exit("boom: the board could not be read")
print(json.dumps([
    {"id": "bbb", "status": "Picked", "angle": "b"},
    {"id": "aaa", "status": "Draft", "angle": "a"},
]))
PY
out=$(NOTION_REST_BIN="$WORK/fake_notion.py" bash "$DIGEST" 2>/dev/null); rc=$?
assert 'the digest exits clean when the board reads' "[ $rc -eq 0 ]"
assert 'one <page-id>:<status> line per row, sorted' \
  "[ \"\$(printf '%s' '$out')\" = 'aaa:Draft
bbb:Picked' ]"

out=$(FAKE_NOTION_FAIL=1 NOTION_REST_BIN="$WORK/fake_notion.py" bash "$DIGEST" 2>/dev/null); rc=$?
assert 'an unreadable board exits non-zero' "[ $rc -ne 0 ]"
assert 'and prints NOTHING — an unreadable board is never "unchanged"' "[ -z '$out' ]"

assert 'the digest asks for every row, not the NUC-44 agent cap' \
  "grep -q -- '--max-rows 0' '$DIGEST'"

echo '--- the trigger leaves as kind 45001 carrying augustus in a p tag ---'
reset_case
event "$AUGUSTUS" "DECLINE: nothing Picked tonight"
run_dispatch; rc=$?
assert 'a confirmed DECLINE: reply exits 0' "[ $rc -eq 0 ]"
assert 'the send carried --kind 45001 (the content channel is a forum)' \
  "grep 'messages send' '$STUB_ARGV' | grep -q -- '--kind 45001'"
assert 'the send carried --mention with augustus pubkey' \
  "grep 'messages send' '$STUB_ARGV' | grep -q -- \"--mention $AUGUSTUS\""
assert 'the send addressed the content channel' \
  "grep 'messages send' '$STUB_ARGV' | grep -q -- \"--channel $CHANNEL\""

echo '--- a leading @mention does not hide the sentinel (2026-09-19) ---'
# The harness tells every agent to @mention the delegator when it reports a result, and
# the trigger tells augustus the line must BEGIN with `DECLINE:`. He cannot obey both in
# one fixed order: on 2026-09-18 he wrote `DECLINE: @PRAETORIUM ...` (matched), on
# 2026-09-19 `@PRAETORIUM DECLINE: ...`, and a valid decline was recorded as a failed run.
# The mention is presentation the harness demands; the sentinel is the contract.
reset_case
event "$AUGUSTUS" "@PRAETORIUM DECLINE: no Picked rows; 13 Idea rows already queued"
run_dispatch; rc=$?
assert 'DECLINE: behind a leading mention exits 0' "[ $rc -eq 0 ]"
assert 'and is reported as an owned decline' "grep -q 'augustus declined' '$WORK/out'"
assert 'and never as an unknown sentinel' "! grep -qi 'no sentinel matched' '$WORK/out'"

reset_case
event "$AUGUSTUS" "nostr:npub1praetorium @PRAETORIUM RUN-FAILED: published_corpus exited 2"
run_dispatch; rc=$?
assert 'a failure sentinel behind mentions is still a failure (exit 1)' "[ $rc -eq 1 ]"
assert 'and takes its own table row' "grep -qi 'could not complete a mandatory step' '$WORK/out'"

reset_case
event "$AUGUSTUS" "@PRAETORIUM nothing tonight, DECLINE: is not where the contract puts it"
run_dispatch; rc=$?
assert 'a sentinel that is not first after the mention does not match' "[ $rc -eq 1 ]"
assert 'and is reported as no sentinel matched' "grep -qi 'no sentinel matched' '$WORK/out'"

echo '--- the FOURTH outcome: augustus replied that he could not read the skill ---'
# Three outcomes were specified: board moved (0), DECLINE: (0), asked and silent (1). A
# section name that no longer resolves in the vault SKILL.md is none of them. Before this
# branch existed the reply matched no pattern, the poll ran the full wait to its deadline,
# and the run logged "no board movement and no reply" — which asserts the opposite of what
# happened and throws away the one line naming the heading to fix.
reset_case
event "$AUGUSTUS" "SKILL-READ-FAILED: Step 3 — Draft the post"
# run_dispatch redirects into $WORK/out; it returns nothing on its own stdout, so reading a
# command substitution here gives an empty haystack — which passes every negated assertion
# and fails every positive one, exactly as observed on this suite's first run.
run_dispatch; rc=$?
# `[ $rc -eq 1 ]` alone passed while the branch was DEAD — the runner reached its deadline
# and exited 1 for the silent-reply reason instead. An exit code shared by two paths is
# not evidence of which one ran; the log line is.
assert 'a SKILL-READ-FAILED reply exits 1 — it is a failure, not a decline' \
  "[ $rc -eq 1 ] && ! grep -q 'no board movement and no reply' '$WORK/out'"
assert 'and is NOT reported as a decline' "! grep -qi 'declined' '$WORK/out'"
assert 'and names the section that did not resolve' \
  "grep -qF -- 'Step 3 — Draft the post' '$WORK/out'"
assert 'and says plainly that it is a failure' "grep -qi 'FAILURE, not a decline' '$WORK/out'"
# The profile is what tells augustus to send it. A sentinel the dispatcher understands and
# the profile never emits is dead code; the reverse is the 20-minute stall.
assert 'the profile instructs him to reply with the sentinel this branch reads' \
  "grep -qF 'SKILL-READ-FAILED:' '$REPO_ROOT/profiles/augustus_content_task.md'"

echo '--- the waiter reads the channel, never the thread ---'
assert 'the waiter called `messages get`' "grep -q 'messages get' '$STUB_ARGV'"
assert 'nothing called `messages thread` at runtime' "! grep -q 'messages thread' '$STUB_ARGV'"
# `thread` returns only e-tagged replies, so a flat top-level answer reads as silence
# and the run times out on a reply that is sitting in the channel.
assert 'and the script names no thread subcommand at all' \
  "! grep -v '^[[:space:]]*#' '$RUNNER' | grep -q 'messages thread'"
assert 'the waiter scoped its read to the dispatch epoch' \
  "grep 'messages get' '$STUB_ARGV' | grep -q -- '--since'"
# augustus answers as kind 45003 (forum comment) while praetorium publishes 45001;
# a --kinds filter set from the route would drop every reply he writes.
assert 'the waiter filtered no kinds — augustus replies 45003, not 45001' \
  "! grep 'messages get' '$STUB_ARGV' | grep -q -- '--kinds'"

echo '--- the trigger points at the profile; it does not resend it ---'
assert 'the body reached the send at all' "[ -s '$STUB_STDIN' ]"
assert 'the trigger names the profile path' \
  "grep -q 'augustus_content_task.md' '$STUB_STDIN'"
assert 'the trigger tells him how to decline' "grep -q 'DECLINE:' '$STUB_STDIN'"
# One source of truth for the task. Inlining the profile would resend it every night
# and give it a second place to drift from the file augustus actually executes.
assert 'the trigger is short — the profile is not inlined nightly' \
  "[ \"\$(wc -c <'$STUB_STDIN')\" -lt 1200 ]"
assert 'and it is genuinely smaller than the profile it points at' \
  "[ \"\$(wc -c <'$STUB_STDIN')\" -lt \"\$(wc -c <'$REPO_ROOT/profiles/augustus_content_task.md')\" ]"

echo '--- the FIFTH outcome: a mandatory step augustus could not run ---'
# SKILL-READ-FAILED: was fixed as a special case. RUN-FAILED: then arrived on 2026-09-06 and
# fell through the identical hole — matched by nothing, polled to the deadline, and logged
# "no board movement and no reply" 110 seconds after augustus had answered. A special case
# ends an instance and leaves the class; the table below is what ends the class.
reset_case
event "$AUGUSTUS" "RUN-FAILED: published_corpus REFUSING — origin unreachable"
run_dispatch; rc=$?
# The exit code alone is not evidence: the silent path exits 1 too, which is exactly how the
# dead SKILL-READ-FAILED branch passed its first suite. The log line is what separates them.
assert 'a RUN-FAILED reply exits 1 — asked, and it could not run' \
  "[ $rc -eq 1 ] && ! grep -q 'no board movement and no reply' '$WORK/out'"
assert 'and is NOT reported as a decline' "! grep -qi 'declined' '$WORK/out'"
assert 'and quotes the reason verbatim' \
  "grep -qF -- 'published_corpus REFUSING — origin unreachable' '$WORK/out'"
assert 'and names the event, so the claim stays checkable' "grep -q 'eeeeee' '$WORK/out'"
# Neither is exit 1 alone, and neither is the absence of the silence line: the deadline
# any-reply read below also exits 1 and also suppresses that line, so with the RUN-FAILED
# row deleted every assertion above still passes. These two are what separate the table
# row from the catch-all — proven by deleting the row and watching only these go red.
assert 'and the run took the TABLE ROW, not the unknown-sentinel catch-all' \
  "! grep -qi 'no sentinel matched' '$WORK/out'"
assert 'and says which class of failure it was' \
  "grep -qi 'could not complete a mandatory step' '$WORK/out'"
assert 'the profile instructs him to reply with the sentinel this row reads' \
  "grep -qF 'RUN-FAILED:' '$REPO_ROOT/profiles/augustus_content_task.md'"

echo '--- a sentinel the table does not know ends the wait; it does not burn it ---'
# The generalisation. Whatever the next unknown prefix turns out to be, the run must stop on
# the reply and say which prefix it did not recognise — never spend the full wait and then
# assert silence over a reply that is sitting in the channel.
reset_case
event "$AUGUSTUS" "WAT-FAILED: something nobody taught the dispatcher"
run_dispatch; rc=$?
assert 'an unrecognised sentinel still exits 1' "[ $rc -eq 1 ]"
assert 'and never claims there was no reply' \
  "! grep -q 'no board movement and no reply' '$WORK/out'"
assert 'and says plainly that no sentinel matched' "grep -qi 'no sentinel matched' '$WORK/out'"
assert 'and quotes the line, so the missing row is obvious' \
  "grep -qF -- 'WAT-FAILED: something nobody taught the dispatcher' '$WORK/out'"
assert 'and names the event id' "grep -q 'eeeeee' '$WORK/out'"

echo '--- the sentinel table and the profile pin each other, both directions ---'
# The assertion that makes this class die once instead of once per sentinel. A prefix the
# profile teaches augustus to send and the dispatcher does not know costs a 20-minute stall
# in production; a row the dispatcher knows and the profile never emits is dead code. Both
# are caught here, at gate time, for the price of one table row.
# ALL-CAPS-colon is reserved in that profile FOR sentinels — if a non-sentinel one is ever
# needed, this failing is the conversation, not the obstacle.
PROFILE_MD="$REPO_ROOT/profiles/augustus_content_task.md"
sed -n '/^SENTINELS=(/,/^)/p' "$RUNNER" | grep -oE '\b[A-Z][A-Z0-9-]*:' | sort -u >"$WORK/table_sentinels"
grep -oE '\b[A-Z][A-Z0-9-]*:' "$PROFILE_MD" | sort -u >"$WORK/profile_sentinels"
comm -23 "$WORK/profile_sentinels" "$WORK/table_sentinels" >"$WORK/only_profile"
comm -13 "$WORK/profile_sentinels" "$WORK/table_sentinels" >"$WORK/only_table"
# An empty extraction would satisfy one direction vacuously and read as a pass.
assert 'the dispatcher table extraction found rows at all' "[ -s '$WORK/table_sentinels' ]"
assert 'the profile extraction found sentinels at all' "[ -s '$WORK/profile_sentinels' ]"
assert 'every sentinel the profile instructs has a row in the dispatcher table' \
  "[ ! -s '$WORK/only_profile' ]"
assert 'and every row in the dispatcher table is a sentinel the profile instructs' \
  "[ ! -s '$WORK/only_table' ]"
[ -s "$WORK/only_profile" ] && echo "    profile-only: $(tr '\n' ' ' <"$WORK/only_profile")"
[ -s "$WORK/only_table" ] && echo "    table-only:   $(tr '\n' ' ' <"$WORK/only_table")"

echo '--- the corpus gate is armed on the HOST, before anyone is asked ---'
# augustus cannot fetch the site repo: he is the only agent on codex-acp and his namespace
# mounts a tmpfs over ~/.ssh, so `git@github-website:` — an ssh-config alias — does not
# resolve. Nine consecutive nights he reported the corpus unreachable while the host-side
# receipt seconds later read `corpus: fetched`. The fix is a transport split, not a wider
# namespace: the host acquires, and ~/agent-workforce/var/ is already readable inside.
reset_case
event "$AUGUSTUS" "DECLINE: nothing Picked tonight"
run_dispatch; rc=$?
assert 'the runner armed the corpus gate' "grep -q '^corpus snapshot' '$STUB_ARGV'"
assert 'and armed it BEFORE the trigger went out' \
  "[ \"\$(grep -n '^corpus snapshot' '$STUB_ARGV' | cut -d: -f1 | sed -n 1p)\" \
   -lt \"\$(grep -n 'messages send' '$STUB_ARGV' | cut -d: -f1 | sed -n 1p)\" ]"

reset_case
echo 5 >"$STUB_CORPUS_RC"
run_dispatch; rc=$?
# Exit 4, not 1: nobody was asked, so agent_propose.sh must record CRASHED and not retry.
# Same precedent as the unreadable board — dispatching against a gate that cannot run
# produces a draft that looks exactly as confident as a correct one.
assert 'a corpus gate that cannot be armed exits 4 (CRASH_EXIT)' "[ $rc -eq 4 ]"
assert 'and nothing was dispatched — an ungated draft is worse than no draft' \
  "! grep -q 'messages send' '$STUB_ARGV'"
assert 'and the failure names the gate, not the wait' "grep -qi 'gate' '$WORK/out'"

echo '--- completion: the board moved ---'
reset_case
touch "$STUB_DIGEST_MOVE"
run_dispatch; rc=$?
assert 'a pre-dispatch Picked row that becomes Draft exits 0' "[ $rc -eq 0 ]"
assert 'and names the exact Picked-to-Draft transition' \
  "grep -q 'content-board-transition-produced-draft.*page=page-1 from=Picked to=Draft' '$WORK/out'"
assert 'the delivery receipt event id is the run id in the snapshot' \
  "grep -q '^run_id=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa$' '$WORK/board.snapshot'"
assert 'the nightly entry point is recorded beside the run id' \
  "grep -q '^entry_point=nightly$' '$WORK/board.snapshot'"

echo '--- completion rejects an unrelated board mutation ---'
reset_case
printf 'page-1:Picked\npage-2:Idea\n' >"$STUB_DIGEST_AFTER"
touch "$STUB_DIGEST_MOVE"
run_dispatch; rc=$?
assert 'an unrelated status change exits 1' "[ $rc -eq 1 ]"
assert 'and fails the named draft-transition assertion' \
  "grep -q 'content-board-transition-produced-draft failed' '$WORK/out'"
assert 'it never treats the unrelated mutation as a draft' \
  "! grep -q 'page=page-1 from=Picked to=Draft' '$WORK/out'"
printf 'page-1:Draft\npage-2:Draft\n' >"$STUB_DIGEST_AFTER"

echo '--- completion: dispatched but silent is a FAILURE, not a decline ---'
reset_case
run_dispatch; rc=$?
assert 'a timeout with neither movement nor a reply exits 1 (outcome=FAIL)' "[ $rc -eq 1 ]"
assert 'and it is NOT reported as an owned decline' "! grep -qi 'augustus declined' '$WORK/out'"
# The silence line survives the sentinel table: it is now the LAST word, reached only after
# a re-read finds no reply at all. It must still be reachable, or genuine silence would be
# mislabelled as an unknown sentinel.
assert 'and genuine silence still says exactly that' \
  "grep -q 'no board movement and no reply' '$WORK/out'"

RUN_ID="$(printf 'a%.0s' {1..64})"
ERROR_404='the harness turn ended in an error: other: unexpected status 404 Not Found: The model `gpt-5.5` does not exist or you do not have access to it., url: https://chatgpt.com/backend-api/codex/responses, request id: 80c03fe9'

echo '--- completion: his turn ended in a harness error — a named FAILURE, at once ---'
# 2026-09-07 and 09-09: the Codex turn ended on a model 404 at 115s and 11s, nothing was
# posted, the board did not move, and the runner spent the full 1200s to record "no reply".
reset_case
turn_receipt failed "$RUN_ID" "$ERROR_404"
started=$(date +%s)
WAIT_SECS=30 run_dispatch; rc=$?
elapsed=$(( $(date +%s) - started ))
assert 'an errored turn exits 1 (asked, and the harness failed him)' "[ $rc -eq 1 ]"
assert 'and the wait ended on the receipt, not the 30s deadline' "[ $elapsed -lt 10 ]"
assert 'and the failure is named after the harness, not after silence' \
  "grep -q 'agent-turn-ended-in-a-harness-error run_id=$RUN_ID' '$WORK/out'"
assert 'and it carries the error text the receipt recorded' "grep -q '404 Not Found' '$WORK/out'"
assert 'and that line is the LAST one — it becomes the run receipt'"'"'s reason' \
  "tail -1 '$WORK/out' | grep -q 'agent-turn-ended-in-a-harness-error'"
assert 'and it never says "no reply" — silence was not what happened' \
  "! grep -q 'no board movement and no reply' '$WORK/out'"
assert 'and it is NOT reported as a decline' "! grep -qi 'declined' '$WORK/out'"
assert 'and both board assertions still fail by name' \
  "grep -q 'content-board-transition-produced-draft failed' '$WORK/out' && grep -q 'owned-reply-evidences-decline failed' '$WORK/out'"
assert 'and the log names the interaction receipt it read' "grep -q '0a0a-thread-0b03' '$WORK/out'"

echo '--- completion: his turn ended clean with nothing to show — silence, recorded early ---'
reset_case
turn_receipt decline "$RUN_ID"
started=$(date +%s)
WAIT_SECS=30 run_dispatch; rc=$?
elapsed=$(( $(date +%s) - started ))
assert 'a turn that ended without a post or a move exits 1' "[ $rc -eq 1 ]"
assert 'and does not wait out the deadline for a turn that is over' "[ $elapsed -lt 10 ]"
assert 'and still calls it what it is' "grep -q 'no board movement and no reply' '$WORK/out'"
assert 'and says the turn ended, naming the receipt' \
  "grep -q 'turn ended (receipt 0a0a-thread-0b03)' '$WORK/out'"
assert 'and does not claim the deadline was reached' "! grep -q 'within 30s' '$WORK/out'"

echo '--- completion: the board moved as the turn closed ---'
# The receipt lands about a second after the turn; the last board write can land with it.
# One more read after the receipt, or a draft written in that second would be recorded as
# a failed run.
reset_case
turn_receipt artifact "$RUN_ID"
printf 3 >"$STUB_DIGEST_MOVE"
WAIT_SECS=30 run_dispatch; rc=$?
assert 'a Draft that appears on the post-turn read exits 0' "[ $rc -eq 0 ]"
assert 'and names the transition' \
  "grep -q 'content-board-transition-produced-draft.*page=page-1 from=Picked to=Draft' '$WORK/out'"

echo '--- a receipt for a different event never ends this wait ---'
reset_case
turn_receipt failed "$(printf 'b%.0s' {1..64})" "$ERROR_404"
WAIT_SECS=3 run_dispatch; rc=$?
assert 'someone else'"'"'s turn leaves the run waiting to its own deadline' \
  "grep -q 'no board movement and no reply within 3s' '$WORK/out'"
assert 'and its error is never attributed to this dispatch' \
  "! grep -q 'agent-turn-ended-in-a-harness-error' '$WORK/out'"

echo '--- completion: a publish failure is exit 4, never "no reply yet" ---'
reset_case
echo 2 >"$STUB_SEND_RC"
run_dispatch; rc=$?
assert 'a rejected send exits 4 (CRASH_EXIT)' "[ $rc -eq 4 ]"
assert 'the waiter never ran — nobody was asked' "! grep -q 'messages get' '$STUB_ARGV'"
# --mention of a non-member is fatal to the whole send, so this is the shape a
# membership regression arrives in. Waiting 20 minutes for it would be a lie.
assert 'the failure names the publish, not the wait' "grep -qi 'publish\|trigger' '$WORK/out'"

echo '--- a reply from anyone but augustus is not completion ---'
reset_case
event "f00dbabe$(printf 'f%.0s' {1..56})" "DECLINE: I am not augustus"
run_dispatch; rc=$?
assert 'a DECLINE: from another pubkey does not complete the run' "[ $rc -eq 1 ]"

echo '--- a stale reply from before the dispatch is not completion ---'
reset_case
event "$AUGUSTUS" "DECLINE: this was last night" -7200
run_dispatch; rc=$?
assert 'a DECLINE: predating the dispatch epoch is ignored' "[ $rc -eq 1 ]"

echo '--- an unreadable board never passes as "unchanged" ---'
reset_case
echo 3 >"$STUB_DIGEST_RC"
run_dispatch; rc=$?
assert 'a digest that cannot be taken fails the run before dispatching' "[ $rc -ne 0 ]"
assert 'and nothing was published on an unknown baseline' \
  "! grep -q 'messages send' '$STUB_ARGV'"

echo '--- content_moved.sh: the independent artifact check (NUC-44) ---'
reset_case
printf 'page-1:Picked\nrun_id=%s\nentry_point=nightly\n' "$(printf 'a%.0s' {1..64})" >"$WORK/board.snapshot"
touch "$STUB_DIGEST_MOVE"
# content_moved reads the board once (unlike the runner, which first captures a baseline),
# so seed the digest counter at one to present its post-run value on that call.
printf '1' >"$STUB_DIGEST_N"
rc=0
env CONTENT_DIGEST_BIN="$WORK/digest.sh" CONTENT_BOARD_SNAPSHOT="$WORK/board.snapshot" \
    bash "$MOVED" >"$WORK/out" 2>&1 || rc=$?
assert 'a pre-dispatch Picked row that becomes Draft verifies clean' "[ $rc -eq 0 ]"

reset_case
printf '%s\nrun_id=%s\nentry_point=nightly\n' "$(cat "$STUB_DIGEST_BEFORE")" "$(printf 'a%.0s' {1..64})" >"$WORK/board.snapshot"
rc=0
env CONTENT_DIGEST_BIN="$WORK/digest.sh" CONTENT_BOARD_SNAPSHOT="$WORK/board.snapshot" \
    bash "$MOVED" >"$WORK/out" 2>&1 || rc=$?
assert 'an identical board fails the verify (a lying exit 0 is still caught)' "[ $rc -ne 0 ]"

reset_case
rc=0
env CONTENT_DIGEST_BIN="$WORK/digest.sh" CONTENT_BOARD_SNAPSHOT="$WORK/absent.snapshot" \
    bash "$MOVED" >"$WORK/out" 2>&1 || rc=$?
assert 'a missing snapshot fails — the runtime never ran, so nothing is proven' "[ $rc -ne 0 ]"

reset_case
printf '%s\nrun_id=%s\nentry_point=nightly\n' "$(cat "$STUB_DIGEST_BEFORE")" "$(printf 'a%.0s' {1..64})" >"$WORK/board.snapshot"
printf 'decline_event=%s\n' "$(printf 'e%.0s' {1..64})" >>"$WORK/board.snapshot"
rc=0
env CONTENT_DIGEST_BIN="$WORK/digest.sh" CONTENT_BOARD_SNAPSHOT="$WORK/board.snapshot" \
    bash "$MOVED" >"$WORK/out" 2>&1 || rc=$?
assert 'an unmoved board with a recorded decline event verifies clean' "[ $rc -eq 0 ]"
assert 'and the receipt names the event id, so the claim is checkable' \
  "grep -q 'eeeeee' '$WORK/out'"

reset_case
echo 3 >"$STUB_DIGEST_RC"
printf '%s\nrun_id=%s\nentry_point=nightly\n' "$(cat "$STUB_DIGEST_BEFORE")" "$(printf 'a%.0s' {1..64})" >"$WORK/board.snapshot"
rc=0
env CONTENT_DIGEST_BIN="$WORK/digest.sh" CONTENT_BOARD_SNAPSHOT="$WORK/board.snapshot" \
    bash "$MOVED" >"$WORK/out" 2>&1 || rc=$?
assert 'an unreadable board fails the verify rather than reading as unchanged' "[ $rc -ne 0 ]"

echo '--- the handoff: the verifier reads the artifact the RUNTIME actually wrote ---'
# Every case above hand-builds the snapshot, so none of them exercises the one file that
# crosses between the two scripts. Live 2026-08-13 the runtime wrote it without a trailing
# newline, `decline_event=` fused onto the last digest row, and the verify passed by
# reporting a board that had not moved — the decline branch was never reached. It fails
# OPEN: after any decline the snapshot can never equal the board again.
reset_case
event "$AUGUSTUS" "DECLINE: nothing Picked tonight"
run_dispatch; rc=$?
assert 'the runtime exits 0 on the decline' "[ $rc -eq 0 ]"
assert 'the record is a line of its own, not fused onto the last digest row' \
  "grep -q '^decline_event=' '$WORK/board.snapshot'"
assert 'no digest row was corrupted by the appended record' \
  "! grep -q '[^=]decline_event=' '$WORK/board.snapshot'"
assert 'the snapshot is the digest plus run identity, entry point and decline evidence' \
  "[ \$(wc -l <'$WORK/board.snapshot') -eq \$(( \$(wc -l <'$STUB_DIGEST_BEFORE') + 3 )) ]"

rc=0
env CONTENT_DIGEST_BIN="$WORK/digest.sh" CONTENT_BOARD_SNAPSHOT="$WORK/board.snapshot" \
    bash "$MOVED" >"$WORK/out" 2>&1 || rc=$?
assert 'the verify passes on the unmoved board' "[ $rc -eq 0 ]"
assert 'and it passes BECAUSE of the owned decline, not because the board looks moved' \
  "grep -qi 'owned-reply-evidences-decline' '$WORK/out'"
assert 'it never claims movement that did not happen' \
  "! grep -qi 'board moved' '$WORK/out'"

echo '--- the contract check reads the same receipt: agent-turn-did-not-error ---'
# The block is lifted from design/contracts/augustus-content.md and run as contract_exec.py
# runs it, under a HOME whose deployed tree is this checkout's reader and a receipts dir the
# case controls. The runner ends the run on the receipt; this is the receipt-time reader
# that turns the same evidence into the receipt's check result.
CONTRACT="$REPO_ROOT/design/contracts/augustus-content.md"
sed -n '/^   ```check id=agent-turn-did-not-error/,/^   ```$/p' "$CONTRACT" | sed '1d;$d' >"$WORK/check.sh"
assert 'the contract carries the check' "[ -s '$WORK/check.sh' ]"
FAKE_HOME="$WORK/home"
mkdir -p "$FAKE_HOME/agent-workforce/bin" "$FAKE_HOME/agent-workforce/var/workflow-receipts"
ln -sfn "$REPO_ROOT/bin/content_turn_receipt.py" "$FAKE_HOME/agent-workforce/bin/content_turn_receipt.py"
STUB_TURN_RECEIPTS="$FAKE_HOME/agent-workforce/var/workflow-receipts/buzz-agent@augustus"
run_check() {  # run_check <attempt-log>
  env -i PATH="$PATH" HOME="$FAKE_HOME" UNIT=augustus-content AGENT_ATTEMPT_LOG="$1" \
    bash "$WORK/check.sh" >"$WORK/check.out" 2>&1
}
printf 'corpus gate armed\n' >"$WORK/no_trigger.log"
printf 'corpus gate armed\ntrigger published to content (channel c, mention a) run_id=%s entry_point=nightly\n' "$RUN_ID" >"$WORK/trigger.log"

rm -rf "$STUB_TURN_RECEIPTS"
run_check "$WORK/no_trigger.log"; rc=$?
assert 'no trigger published — n/a, nobody was asked' "[ $rc -eq 77 ] && grep -q 'nobody was asked' '$WORK/check.out'"
run_check "$WORK/trigger.log"; rc=$?
assert 'trigger but no receipt yet — n/a, not a pass' "[ $rc -eq 77 ] && grep -q 'no interaction receipt' '$WORK/check.out'"
turn_receipt failed "$RUN_ID" "$ERROR_404"
run_check "$WORK/trigger.log"; rc=$?
assert 'a failed receipt for this trigger fails the check' "[ $rc -eq 1 ]"
assert 'and the check output quotes the harness error' "grep -q '404 Not Found' '$WORK/check.out'"
rm -rf "$STUB_TURN_RECEIPTS"
turn_receipt artifact "$RUN_ID"
run_check "$WORK/trigger.log"; rc=$?
assert 'a clean turn passes' "[ $rc -eq 0 ] && grep -q 'outcome=artifact' '$WORK/check.out'"
env -i PATH="$PATH" HOME="$FAKE_HOME" UNIT=content-change-dispatch AGENT_ATTEMPT_LOG="$WORK/trigger.log" \
  bash "$WORK/check.sh" >"$WORK/check.out" 2>&1; rc=$?
assert 'the dispatch tick is n/a — decided for the run it dispatched' "[ $rc -eq 77 ]"
rm -f "$FAKE_HOME/agent-workforce/bin/content_turn_receipt.py"
run_check "$WORK/trigger.log"; rc=$?
assert 'a reader that cannot run is a failure, never "no receipt yet"' \
  "[ $rc -eq 1 ] && grep -q 'could not be read' '$WORK/check.out'"
STUB_TURN_RECEIPTS="$WORK/turn-receipts"

echo '--- transport ownership: the dispatcher owns no transport ---'
# bin/deliver.sh is the single owner of `buzz messages send`
# (tests/test_buzz_unit_wiring.sh). The waiter only READS.
assert 'run_content_via_buzz.sh never sends through the Buzz CLI itself' \
  "! grep -v '^[[:space:]]*#' '$RUNNER' | grep -q 'messages send'"

if [ "$fail" -ne 0 ]; then
  echo "FAILED"
  exit 1
fi
echo "all dispatch assertions passed"
