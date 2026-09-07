#!/usr/bin/env bash
# bin/buzz_acp_update.sh is the only thing on this box that can notice the Buzz CLI going
# stale, so its failure modes are the subject here — not its happy path.
#
# WHY IT EXISTS AT ALL. The fleet ran a buzz-acp twelve releases behind for five weeks and
# nothing could have reported it: Desktop on the Mac and the CLI here are two independent
# installs of one release stream, there is no dpkg package, and neither binary answers
# --version. A checker for that class is worthless if it can fail open, and the ways it can
# fail open are specific: a receipt that has drifted from the bytes it describes, a network
# blip read as "current", or a compatibility probe that says ok because extraction broke.
# Each has a group below.
#
# IT ALSO OWNS THE WAKE CHECK, which was tests/test_buzz_acp_workflow_wake.sh until it was
# folded in here the same day both were written. That suite asserted the three buzz:workflow*
# literals against the installed binary; `probe` asserts the same three, against any binary,
# because an install gate and a test gate that disagree about capability are worse than
# either alone. Keeping both would have been two copies of one predicate on a box whose
# CLAUDE.md is largely a record of two copies drifting. What that suite documented and this
# one must not lose: a workflow message is signed by the RELAY, not a person, so clearing
# --respond-to owner-only depends on verified_workflow_owner() re-attributing it via those
# tags. The function was absent for five weeks and every scheduled workflow message was
# dropped with no error on either side — indistinguishable from a dead unit, a mis-bound
# mention or a stuck turn. Nothing failed and nothing was looking.
#
# What is deliberately NOT asserted, then or now: that the relay emits those tags. That needs
# an authenticated `buzz workflows list` and the only credentials here are deny-listed. An
# unauthenticated HTTP probe is a non-test — it 403s on a nonsense path too.
#
# THE PROBE IS ASSERTED AGAINST A REAL OLD BINARY WHERE ONE IS PRESENT. ~/.local/bin holds
# the July build as a rollback backup, and it is a genuine pre-#6953 artifact — a better
# fixture than anything synthetic, because it fails the wake check while passing the
# control and every flag, which is exactly the shape the real defect had. It is box-only,
# so the synthetic fixtures run everywhere and carry the coverage in CI.
set -uo pipefail

# shellcheck source=tests/box_precondition.sh
. "$(cd "$(dirname "$0")" && pwd)/box_precondition.sh"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TOOL="$REPO_ROOT/bin/buzz_acp_update.sh"
fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT

# A stand-in for the unit, so the flag half of the probe has something to read in CI.
mkdir -p "$fx/unit"
cat > "$fx/unit/buzz-agent@.service" <<'UNIT'
[Service]
ExecStart=/usr/bin/buzz-acp \
  --config /x \
  --respond-to owner-only \
  --subscribe all \
  --system-prompt-file /y \
  --mcp-command /z \
  --idle-timeout 30
UNIT
FAKE_UNIT="$fx/unit/buzz-agent@.service"

# A buzz-acp stand-in: --help echoes whichever flags it claims, and the literals it
# carries are whatever we write into it.
make_acp() {  # make_acp <path> <literals-space-sep> <help-flags-space-sep>
  local p=$1 lits=$2 flags=$3
  { echo '#!/usr/bin/env bash'
    echo "# literals: $lits"
    for l in $lits; do echo "# $l"; done
    echo "[ \"\${1:-}\" = --help ] && { for f in $flags; do echo \"  \$f\"; done; exit 0; }"
  } > "$p"
  chmod +x "$p"
}
ALL_FLAGS='--config --respond-to --subscribe --system-prompt-file --mcp-command --idle-timeout'
WAKE='buzz:config-nudge buzz:workflow buzz:workflow-owner buzz:workflow-mention'

echo "--- probe: the three shapes of a bad candidate are each distinguished ---"
make_acp "$fx/good"       "$WAKE"              "$ALL_FLAGS"
make_acp "$fx/no-wake"    'buzz:config-nudge'  "$ALL_FLAGS"
make_acp "$fx/lost-flag"  "$WAKE"              '--config --respond-to --subscribe --system-prompt-file --mcp-command'
printf '\x00\x01\x02\x03' > "$fx/opaque"; chmod +x "$fx/opaque"

assert 'a candidate with the wake path and every flag PASSES' \
  "'$TOOL' probe '$fx/good' '$FAKE_UNIT' >/dev/null 2>&1"
assert 'a pre-#6953 candidate FAILS, and on the wake path specifically' \
  "'$TOOL' probe '$fx/no-wake' '$FAKE_UNIT' 2>&1 | grep -q 'FAIL wake: buzz:workflow-mention'"
assert 'and it still PASSES the control, so the absence is real rather than unreadable' \
  "'$TOOL' probe '$fx/no-wake' '$FAKE_UNIT' 2>&1 | grep -q 'ok control'"
assert 'a candidate that DROPPED a flag the unit passes FAILS, naming the flag' \
  "'$TOOL' probe '$fx/lost-flag' '$FAKE_UNIT' 2>&1 | grep -q 'FAIL flag: --idle-timeout'"
assert 'a binary strings cannot read FAILS ON THE CONTROL, not as three missing features' \
  "'$TOOL' probe '$fx/opaque' '$FAKE_UNIT' 2>&1 | grep -q 'FAIL control'"
# The vacuity guard. A unit whose ExecStart stops parsing must not certify a release by
# checking nothing — the flag loop would be empty and every candidate would pass.
printf '[Service]\nExecStart=/usr/bin/buzz-acp\n' > "$fx/unit/bare.service"
assert 'a unit with too few parsed flags is a refusal, not a silent pass' \
  "! '$TOOL' probe '$fx/good' '$fx/unit/bare.service' >/dev/null 2>&1"

echo "--- check: every uncertainty about what is installed is a REPORT, never a pass ---"
newvar() { local d; d=$(mktemp -d -p "$fx"); printf '%s' "$d"; }
mkdir -p "$fx/bin"; cp "$fx/good" "$fx/bin/buzz-acp"; cp "$fx/good" "$fx/bin/buzz"

# An API that answers with a tag we choose, without leaving the machine.
serve_tag() { printf '{"tag_name": "%s"}' "$1" > "$fx/api.json"; printf 'file://%s' "$fx/api.json"; }

run_check() {  # run_check <var-dir> <api-url>
  BUZZ_UPDATE_VAR="$1" BUZZ_UPDATE_BIN="$fx/bin" BUZZ_UPDATE_UNIT="$FAKE_UNIT" \
    BUZZ_UPDATE_API="$2" "$TOOL" check >/dev/null 2>&1
}

v=$(newvar)
assert 'no receipt at all is exit 1 — an unknown install is never reported as current' \
  "! run_check '$v' \"\$(serve_tag desktop-v9.9.9)\""

BUZZ_UPDATE_VAR="$v" BUZZ_UPDATE_BIN="$fx/bin" "$TOOL" adopt desktop-v0.5.23 >/dev/null 2>&1
assert 'adopt writes a receipt pinned to the bytes it found' \
  "grep -q '\"sha256\"' '$v/buzz-cli-install.json'"
assert 'a receipt matching disk, with upstream at the same tag, is exit 0' \
  "run_check '$v' \"\$(serve_tag desktop-v0.5.23)\""
assert 'the same receipt with upstream AHEAD is exit 10, not 0' \
  "run_check '$v' \"\$(serve_tag desktop-v9.9.9)\"; [ \$? -eq 10 ]"

# The failure this whole design turns on: the receipt is a note about the artifact, and a
# note can describe bytes that are no longer there. It must never be believed on its own.
printf 'tamper' >> "$fx/bin/buzz-acp"
assert 'a receipt whose hashes no longer match disk is exit 1, not a version comparison' \
  "! run_check '$v' \"\$(serve_tag desktop-v0.5.23)\""
assert 'and it says UNPINNED with both hashes, so the next step is obvious' \
  "BUZZ_UPDATE_VAR='$v' BUZZ_UPDATE_BIN='$fx/bin' BUZZ_UPDATE_UNIT='$FAKE_UNIT' \
     BUZZ_UPDATE_API=\"\$(serve_tag desktop-v0.5.23)\" '$TOOL' check 2>&1 | grep -q 'UNPINNED'"

echo "--- check: an unreachable upstream is fail-soft, but only for a while ---"
v2=$(newvar); cp "$fx/good" "$fx/bin/buzz-acp"
BUZZ_UPDATE_VAR="$v2" BUZZ_UPDATE_BIN="$fx/bin" "$TOOL" adopt desktop-v0.5.23 >/dev/null 2>&1
date +%s > "$v2/buzz-cli-check-last-ok"
assert 'a blip right after a good check is exit 0 — one hiccup must not page Dave' \
  "run_check '$v2' 'file:///nonexistent-endpoint'"
echo $(( $(date +%s) - 30 * 86400 )) > "$v2/buzz-cli-check-last-ok"
assert 'but a month of not reaching upstream is exit 1 — silence is the original defect' \
  "! run_check '$v2' 'file:///nonexistent-endpoint'"
printf '0' > "$v2/buzz-cli-check-last-ok"
assert 'and a checker that has NEVER succeeded reports rather than waiting out a window' \
  "! run_check '$v2' 'file:///nonexistent-endpoint'"

echo "--- the live install, and the real July binary as a fixture ---"
box_only_with 'the installed buzz binaries and the unit that launches them' \
  "$HOME/.local/bin/buzz-acp" "$HOME/.config/systemd/user/buzz-agent@.service" || exit 77

assert 'the installed buzz-acp passes its own probe' \
  "'$TOOL' probe \"\$HOME/.local/bin/buzz-acp\" >/dev/null 2>&1"
old="$HOME/.local/bin/buzz-backup-2026-09-07/buzz-acp"
if [ -f "$old" ]; then
  assert 'the kept July build FAILS the wake check — a real pre-#6953 artifact, not a mock' \
    "! '$TOOL' probe '$old' >/dev/null 2>&1"
  assert 'and fails ONLY there: it passes the control and every flag the unit passes' \
    "[ \"\$('$TOOL' probe '$old' 2>&1 | grep -c '^  FAIL')\" -eq 3 ]"
else
  echo "  note: the July rollback backup is gone, so the real-artifact fixture did not run"
fi
assert 'the live receipt is pinned to the live bytes' \
  "'$TOOL' status 2>&1 | grep -q '  pinned:'"

echo
[ "$fail" -eq 0 ] && echo "  all buzz_acp_update assertions passed"
exit "$fail"
