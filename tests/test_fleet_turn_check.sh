#!/usr/bin/env bash
# Suite for buzz-team/fleet-turn-check.sh — the hourly gate that proves an agent can
# COMPLETE A TURN.
#
# WHY THIS SUITE EXISTS AT ALL. Its subject was `suite_exempt` until 2026-09-03 for a reason
# that was true — the script lived at ~/.config/buzz-team/ and not in this repo — and brief 7
# adopted it, which made the reason false. Restating the exemption with a fresh wording was
# the alternative and it would have been a true-looking exemption whose premise the same
# commit removed.
#
# WHAT IT ASSERTS: the five design rules the script's own header declares as REQUIRED. Each
# is the invariant whose loss produced a real misdiagnosis, so each is worth pinning:
#
#   1. Enumerate from systemd, never a hardcoded roster. A roster cannot report an agent it
#      does not know about. (buzz-team/verify-fleet.sh's AGENTS=() array is the pattern this
#      file deliberately does not copy — and both files are now in this repo, so a future
#      edit could quietly copy it.)
#   2. Bound every per-unit window at BOTH ends. Anchor-only charges a restarted unit for its
#      predecessor's errors; lookback-only reported augustus's 19-20 Aug errors as live on
#      31 Aug.
#   3. Print the boundary of every window examined, and which bound produced it.
#   4. Name a quiet unit OUT LOUD. Absence of attempts is not evidence of health, and the
#      ANSWERED branch was dead code until CPU delta replaced the journal as the signal.
#   5. Exit non-zero on failure, or OnFailure=agent-alert@%n.service never fires.
#
# WHAT IT DELIBERATELY DOES NOT DO: run the script. Gate 2 spends a real model turn on every
# invocation, and gate 3 reads the live journal of five running agents — so a suite that ran
# it would cost tokens per gate run and would be red for box state rather than for the code
# under test. A PATH-stubbed run is not available either: the script pins PATH at line 23 so
# a systemd unit with a minimal environment can resolve its binaries, which defeats a stub by
# construction. That pin is a testability limit, recorded here rather than worked around.
#
# So this is a STRUCTURAL suite and says so. It cannot prove the gate works; it can prove the
# five properties that make the gate's output mean something have not been edited away.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/buzz-team/fleet-turn-check.sh"
UNIT="$REPO_ROOT/systemd/fleet-turn-check.service"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one. Scoped off here
# rather than per-condition so a later `| grep -q` cannot reintroduce it.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo '--- the subject is in this repo, which is what ended its exemption ---'
assert 'buzz-team/fleet-turn-check.sh exists' "[ -f '$SCRIPT' ]"
assert 'it is executable' "[ -x '$SCRIPT' ]"
assert 'it parses' "bash -n '$SCRIPT'"
# The end of the exemption is a MECHANISM question, not a prose one. trajan.toml still
# quotes the old `suite_exempt` string verbatim inside its notes — that is history being
# recorded, not a live claim, and a grep for the sentence flags it as if it were one. Ask the
# manifest what it declares instead of asking the prose what it mentions.
exempt_check() {
  python3 - "$REPO_ROOT" <<'PYEOF'
import sys, tomllib, pathlib
root = pathlib.Path(sys.argv[1])
d = tomllib.loads((root / "design/agents/trajan.toml").read_text())
w = [x for x in d.get("workflows", []) if x.get("unit") == "fleet-turn-check"]
if len(w) != 1:
    print("expected exactly one fleet-turn-check entry, found", len(w)); sys.exit(1)
w = w[0]
if "suite_exempt" in w:
    print("still exempt:", w["suite_exempt"]); sys.exit(1)
suites = w.get("suite", [])
if not suites:
    print("no suite declared and no exemption — the entry claims nothing"); sys.exit(1)
missing = [s for s in suites if not (root / s).is_file()]
if missing:
    print("declared suite does not exist:", missing); sys.exit(1)
PYEOF
}
assert 'its manifest entry declares a real suite and claims no exemption' "exempt_check"

echo '--- rule 1: the roster comes from systemd, never from a literal ---'
assert 'it asks systemd which buzz-agent units exist' \
  "grep -q \"list-units .*'buzz-agent@\\*.service'\" '$SCRIPT'"
# The negative half, and it is the one that decays. verify-fleet.sh sits beside this file in
# the same adopted tree and DOES carry AGENTS=(...); copying that array in here is a one-line
# edit that would pass every other assertion in this suite.
assert 'it declares no hardcoded agent array of its own' \
  "! grep -qE '^[[:space:]]*(declare -a )?AGENTS=\\(' '$SCRIPT'"
assert 'an empty unit list is a FAILURE, not a clean run over nothing' \
  "grep -A2 'if \\[ -z \"\\\$units\" \\]' '$SCRIPT' | grep -q 'fail_'"

echo '--- rule 2: every per-unit window is bounded at BOTH ends ---'
# Both inputs must be present AND both must feed the choice. Asserting only that the two
# strings appear would pass a version that read one and used the other.
assert 'the per-unit anchor is the unit ActiveEnterTimestamp' \
  "grep -q 'ActiveEnterTimestamp' '$SCRIPT'"
assert 'the floor is a lookback window' "grep -q 'LOOKBACK_MIN' '$SCRIPT'"
assert 'the window start is the LATER of the two, not either alone' \
  "grep -q 'if \\[ \"\\\$anchor_s\" -gt \"\\\$look_s\" \\]' '$SCRIPT'"
assert 'a unit that is active with no anchor fails rather than being judged on a guess' \
  "grep -q 'cannot bound a window' '$SCRIPT'"

echo '--- rule 3: the boundary and its cause are printed ---'
assert 'the chosen bound is named in the output' \
  "grep -q 'bound=\"since restart\"' '$SCRIPT' && grep -q 'bound=\"last ' '$SCRIPT'"
assert 'and the window itself is printed alongside every verdict' \
  "[ \"\$(grep -c '(\$bound)' '$SCRIPT')\" -ge 3 ]"

echo '--- rule 4: a quiet unit is named out loud ---'
# The whole point of the gate: absence of attempts is not evidence of health. A version that
# counted quiet units without naming them would read as a pass.
assert 'quiet units are accumulated' "grep -q 'quiet_list=' '$SCRIPT'"
assert 'and printed by name' "grep -q 'quiet (unproven, not failed)' '$SCRIPT'"
assert 'QUIET is distinguished from SEED — a first reading proves nothing either way' \
  "grep -q 'QUIET ' '$SCRIPT' && grep -q 'SEED ' '$SCRIPT'"
assert 'a seeded unit is never judged on its whole lifetime' \
  "grep -B2 -A2 'seeded.*-eq 1' '$SCRIPT' | grep -q 'turns=0'"

echo '--- rule 5: failure reaches the alert path ---'
assert 'fail_ sets the exit flag' "grep -q 'fail_() {.*fail=1' '$SCRIPT'"
assert 'and the script exits with it' "grep -qE '^exit \\\$fail' '$SCRIPT'"
assert 'the unit wires OnFailure, or a red gate notifies nobody' \
  "[ -f '$UNIT' ] && grep -q '^OnFailure=' '$UNIT'"

echo '--- gate 4: its own discovery pattern refuses an empty set ---'
# A check that cannot fail is not a check. Gate 4 walks /etc for agent_propose.sh units and
# asserts each carries OnFailure=; if the walk matches nothing it must go red rather than
# report "all 0 units are wired", which is the whitelist defect in its purest form.
assert 'finding zero agent_propose.sh units is itself a failure' \
  "grep -A2 'if \\[ \"\\\$checked\" -eq 0 \\]' '$SCRIPT' | grep -q 'discovery pattern itself is broken'"

echo '--- the unit and the registry agree about what execs what ---'
assert 'the unit ExecStarts the adopted script by its box path' \
  "grep -qE '^ExecStart=.*/\\.config/buzz-team/fleet-turn-check\\.sh' '$UNIT'"
# The box path, not the repo path, and that is correct: buzz-team/ is read from
# ~/.config/buzz-team/ at run time and never from the repo, exactly as bin/ is read from
# ~/agent-workforce/bin/. The repo is the source; bin/deploy_buzz_team.sh is the converge.
assert 'and this repo is its declared source, so drift between the two is checkable' \
  "grep -q 'buzz-team/' '$REPO_ROOT/bin/check_deploy_drift.sh'"

exit $fail
