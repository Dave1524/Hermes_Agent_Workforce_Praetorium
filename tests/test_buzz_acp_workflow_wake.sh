#!/usr/bin/env bash
# The installed buzz-acp must be able to wake an agent from a scheduled workflow, and must
# still accept every flag the unit passes it.
#
# Why this suite exists. Between 2026-07-31 and 2026-09-07 the fleet ran a buzz-acp that
# predated upstream #6953. A workflow message is signed by the RELAY, not by a person, so
# clearing --respond-to owner-only depends on verified_workflow_owner() re-attributing it
# via three buzz:workflow* tags. That function was absent, so every scheduled workflow
# message was dropped with no error on either side — indistinguishable from a dead unit, a
# mis-bound mention or a stuck turn. Nothing failed and nothing was looking. The defect was
# found by reading upstream and grepping the binary; this suite is that grep, kept.
#
# The binary has no repo source and answers no --version, so a hash pin would be a
# maintenance tax that says nothing about capability. What is asserted instead is the
# CAPABILITY: the literals the wake path is built from, and the flag surface the unit
# depends on. Both survive a version bump that keeps the contract and fail one that breaks it.
#
# What this suite deliberately does NOT assert: that the relay emits those tags. That needs
# an authenticated `buzz workflows list` and the only credentials on this box are
# deny-listed. An unauthenticated HTTP probe is a non-test — it 403s on a nonsense path too.
set -uo pipefail

# shellcheck source=tests/box_precondition.sh
. "$(cd "$(dirname "$0")" && pwd)/box_precondition.sh"

ACP="$HOME/.local/bin/buzz-acp"
UNIT="$HOME/.config/systemd/user/buzz-agent@.service"

fail=0

# pipefail has no place inside a boolean condition: `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# Deterministic canary for exactly that regression: `yes` is still writing when grep exits.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# ---------------------------------------------------------------------------
# Fixtures first. The live assertions below are green today by construction, so
# on their own they would be a check that cannot fail — which is what let the
# real defect sit for five weeks. These run everywhere, including CI, and prove
# the predicate detects both shapes of the bug it exists to catch.
# ---------------------------------------------------------------------------
has_lit() { strings "$1" | grep -c -- "$2"; }

fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT

# A binary shaped like the one that ran here until 2026-09-07: the control literal
# is present, so extraction demonstrably works, and the wake path is simply absent.
printf 'buzz:config-nudge\nrespond-to\nsome other text\n' > "$fx/old-acp"
# And one shaped like a build where strings(1) yields nothing — the case that would
# otherwise be misread as three missing features rather than one broken method.
printf '\x00\x01\x02\x03' > "$fx/opaque"

echo "--- fixtures: the predicate detects the defect it was written for ---"
assert 'a pre-#6953 binary FAILS the wake-path check' \
  "[ \"\$(has_lit \"$fx/old-acp\" 'buzz:workflow-mention')\" -eq 0 ]"
assert 'and that same binary PASSES the control, so the absence is real' \
  "[ \"\$(has_lit \"$fx/old-acp\" 'buzz:config-nudge')\" -ge 1 ]"
assert 'a binary strings cannot read FAILS the control, not just the wake path' \
  "[ \"\$(has_lit \"$fx/opaque\" 'buzz:config-nudge')\" -eq 0 ]"

box_only_with 'the installed buzz-acp and the unit that launches it' "$ACP" "$UNIT" || exit 77

lit() { has_lit "$ACP" "$1"; }

echo "--- the extraction method itself works ---"
# Checked FIRST and separately. If strings(1) returns nothing useful for this binary, the
# three assertions below would read as three missing features rather than one broken method.
# buzz:config-nudge is unrelated to workflows and has been present in every build measured.
assert 'strings finds an unrelated buzz: literal, so an absence below means absent' \
  "[ \"\$(lit 'buzz:config-nudge')\" -ge 1 ]"

echo "--- the workflow wake path is present (upstream #6953) ---"
for t in 'buzz:workflow' 'buzz:workflow-owner' 'buzz:workflow-mention'; do
  assert "$t is compiled into the installed buzz-acp" "[ \"\$(lit \"$t\")\" -ge 1 ]"
done

echo "--- every flag the unit passes is still accepted ---"
# The crash-loop risk of any upgrade. buzz-acp rejects an unknown flag at startup, and
# Restart=on-failure turns that into a loop rather than a visible stop.
help=$("$ACP" --help 2>&1)
unit_flags=$(grep -oE '^[[:space:]]+--[a-z-]+' "$UNIT" | tr -d ' ' | sort -u)
assert 'the unit passes at least one flag, so the loop below is not vacuous' \
  "[ \"\$(printf '%s\n' \"\$unit_flags\" | grep -c .)\" -ge 5 ]"
while read -r f; do
  [ -n "$f" ] || continue
  assert "$f is in --help" "printf '%s' \"\$help\" | grep -q -- '$f'"
done <<< "$unit_flags"

echo
[ "$fail" -eq 0 ] && echo "  all buzz-acp workflow-wake assertions passed"
exit "$fail"
