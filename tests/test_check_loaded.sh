#!/usr/bin/env bash
# check-loaded.sh must not report OK for a check it could not run.
#
# WHY THIS SUITE EXISTS. On 2026-09-06 the fleet gate had been red for two days on
# `BADAUTH claudius — key and auth tag are from different identities`. Every clause was
# false. check_relay never contacted the relay: it grepped the journal for the string
# `Auth failed` and printed a hardcoded cause. The single match in seven days was a
# reconnect storm that had already healed — attempts 1-4 failed, attempt 5 succeeded 21s
# later — and because the window was bounded only at the start (`--since` with no `--until`)
# that one historical line would have pinned the gate red forever.
#
# The same run surfaced the inverse defect, and it is the one this suite is built around:
#
#     stat: cannot stat '.../praetorium.prompt': No such file or directory
#     line 41: ((: 1785495882 >  : arithmetic syntax error: operand expected
#       OK       praetorium prompt is current with GUARDRAILS.md
#
# `(( a > b ))` returns non-zero when the comparison is FALSE and when the expression is
# MALFORMED, and the old check_sync could not tell those apart, so a missing file took the
# else branch and was certified current. A hosted agent whose .prompt vanished would have
# been reported healthy indefinitely.
#
# THE TWO DEFECTS DEGRADE IN OPPOSITE DIRECTIONS, which is why only one of them was ever
# noticed. The grep failed CLOSED — loud, wrong, and it cost two days of attention. The
# arithmetic failed OPEN — silent, wrong, and it cost nothing until you look for it. Per
# CLAUDE.md's corollary, the second is the expensive half: a check that fails open has been
# certifying nothing the whole time.
#
# FIXTURES FIRST. Group 1 proves each failure mode is detected on synthetic input; the old
# implementation passes case D and the current one must not. Group 2's verdict on live box
# state means something only because group 1 can fail. Group 2 deliberately probes NO
# credentials — it names only the non-hosted identities, which short-circuit before the
# relay call — so this gate never depends on relay reachability.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# The SOURCE copy, which every checkout carries — not the box's, so groups 0-1b run in CI too.
# bin/check_deploy_drift.sh is what guarantees the box is running this same file.
CHECKER="${CHECKER:-$REPO_ROOT/buzz-team/check-loaded.sh}"
# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

echo "--- 0. canary: the pipefail-in-a-condition regression ---"
assert "a true piped condition reads as true" 'yes | grep -q y'

# --- the checker under fixtures -----------------------------------------------------------
# A fixture identity never matches a real buzz-agent@ unit, so it takes the not-hosted path.
# That holds on a runner with no systemd --user as well, where the unit list is simply empty.
run_fixture() {
  local dir=$1 name=$2
  BUZZ_AGENTS_DIR="$dir" bash "$CHECKER" "$name" 2>/dev/null
}

new_base() {
  local d
  d=$(mktemp -d)
  : > "$d/ghost.env"
  printf '%s' "$d"
}

echo "--- 1. fixtures: each failure mode is detected ---"

A=$(new_base)
out=$(run_fixture "$A" ghost); rc=$?
assert "A: an identity with no prompt is INFO, not DEAD" '[[ $out == *INFO* && $out != *DEAD* ]]'
assert "A: and does not fail the gate" '[[ $rc -eq 0 ]]'

B=$(new_base)
touch -d '2026-01-01' "$B/GUARDRAILS.md"
touch -d '2026-06-01' "$B/ghost.prompt"
out=$(run_fixture "$B" ghost); rc=$?
assert "B: a prompt newer than GUARDRAILS.md is OK" '[[ $out == *"prompt is current"* ]]'
assert "B: and does not fail the gate" '[[ $rc -eq 0 ]]'

C=$(new_base)
touch -d '2026-06-01' "$C/GUARDRAILS.md"
touch -d '2026-01-01' "$C/ghost.prompt"
out=$(run_fixture "$C" ghost); rc=$?
assert "C: a prompt older than GUARDRAILS.md is STALE" '[[ $out == *STALE* ]]'
assert "C: and fails the gate" '[[ $rc -ne 0 ]]'

# THE REGRESSION. The old check_sync reported `OK ... prompt is current` here, because the
# stat failure left an empty operand and the malformed (( )) took the else branch.
D=$(new_base)
touch -d '2026-01-01' "$D/ghost.prompt"          # no GUARDRAILS.md at all
out=$(run_fixture "$D" ghost); rc=$?
assert "D: an unrunnable freshness check is UNKNOWN, never OK" '[[ $out == *UNKNOWN* ]]'
assert "D: it does not claim the prompt is current" '[[ $out != *"prompt is current"* ]]'
assert "D: and it fails the gate rather than passing silently" '[[ $rc -ne 0 ]]'

E=$(new_base)
out=$(run_fixture "$E" nosuchagent); rc=$?
assert "E: an unprovisioned name is SKIP" '[[ $out == *SKIP* ]]'
assert "E: and fails the gate" '[[ $rc -ne 0 ]]'

rm -rf "$A" "$B" "$C" "$D" "$E"

echo "--- 1b. fixtures: the relay-event patterns, against real journal text ---"
# Verbatim from buzz-agent@claudius, 2026-09-04/06. Fixtures come from the producer: a
# hand-written imitation of a log line proves nothing about the log (memory
# `handoff-fixtures-must-come-from-the-producer`). The first draft of last_relay_event knew
# only 'connected to relay' and so read case S — a storm that RECOVERED — as an auth failure,
# contradicting a live credential probe that said the identity was fine.
# shellcheck source=/dev/null
. "$CHECKER"

STORM='INFO buzz_acp::relay: autonomous reconnect attempt 3/5 to wss://vpc.communities.buzz.xyz…
WARN buzz_acp::relay: autonomous reconnect attempt 3 failed: Auth failed: error: internal error checking restriction state
INFO buzz_acp::relay: autonomous reconnect attempt 5/5 to wss://vpc.communities.buzz.xyz…
INFO buzz_acp::relay: autonomous reconnect succeeded (attempt 5)
INFO buzz_acp::relay: resubscribing to 6 channel(s) after reconnect'

DOWN='WARN buzz_acp::relay: relay connection lost — reconnecting…
INFO buzz_acp::relay: autonomous reconnect attempt 1/5 to wss://vpc.communities.buzz.xyz…
WARN buzz_acp::relay: autonomous reconnect attempt 1 failed: Auth failed: restricted: not a relay member'

LOST='INFO buzz_acp::relay: connected to relay wss://vpc.communities.buzz.xyz
WARN buzz_acp::relay: relay connection lost — reconnecting…'

assert "S: a storm that recovered reads as recovered" \
  '[[ $(last_relay_event <<<"$STORM") == "autonomous reconnect succeeded" ]]'
assert "S: and specifically NOT as the auth failure it contains" \
  '[[ $(last_relay_event <<<"$STORM") != "Auth failed" ]]'
assert "F: an unrecovered auth failure reads as Auth failed" \
  '[[ $(last_relay_event <<<"$DOWN") == "Auth failed" ]]'
assert "L: a drop with no recovery reads as lost, not connected" \
  '[[ $(last_relay_event <<<"$LOST") == "relay connection lost" ]]'
assert "N: an empty log yields no event at all" \
  '[[ -z $(last_relay_event </dev/null) ]]'

echo "--- 2. the live agent tree ---"
if box_only_with "the live agent identities this classification is checked against" \
     "$HOME/.config/buzz-agents"; then
  # praetorium is the scheduled-delivery identity and spike0 was a test subject: both have a
  # .env, neither has a buzz-agent@ unit. The old enumeration globbed *.env and called them
  # DEAD, which is what made the gate's failing lines look routine.
  for id in praetorium spike0; do
    if [ -f "$HOME/.config/buzz-agents/$id.env" ]; then
      out=$(bash "$CHECKER" "$id" 2>/dev/null); rc=$?
      assert "$id is classified INFO, not DEAD" '[[ $out == *INFO* && $out != *DEAD* ]]'
      assert "$id does not fail the gate" '[[ $rc -eq 0 ]]'
    else
      echo "  info: $id has no .env on this box — nothing to classify"
    fi
  done
fi

exit "$fail"
