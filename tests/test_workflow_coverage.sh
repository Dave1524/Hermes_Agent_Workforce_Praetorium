#!/usr/bin/env bash
# Workflow-coverage checker (D6; design/eval-spec.md §7.1). The mechanism that COMPUTES
# coverage, so §5 stops being a hand-written number that rots the day it is written.
#
# IT SHIPS RED, AND THAT IS THE DELIVERABLE. Five named failures on arrival: four standing
# workflows whose code is in this repo and has no owning suite (m1-signal-scan,
# overnight-morning-report, agent-workforce-auto-sync, overnight-pre-snapshot), plus one
# orphaned suite. A coverage checker that goes green the moment it lands has not been shown
# to detect anything. The four get suites — later, one brief each; `suite_exempt` means the
# code is not in this repo, and using it to silence an in-repo hole would forge the exact
# signal this suite exists to produce.
#
# It reads the source tree ONLY — no systemctl, no /etc, no ~/.config/systemd. Unit
# membership across the four trees is D8's subject and its ownership filter lives there;
# duplicating it here would put one concept in two places.
#
# tests/test_workflow_coverage.py carries the parse and the join. This file is the entry
# point because bin/verify.sh globs tests/*.sh, and it holds the assertions so a failure
# names the rule it broke rather than dumping one undifferentiated report.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

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

fail=0

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

report=$(mktemp)
trap 'rm -f "$report"' EXIT
python3 tests/test_workflow_coverage.py >"$report" 2>&1 || { cat "$report"; exit 1; }
grep -v '^\(PROBLEM\|EXEMPT\|SUMMARY\)	' "$report"

# Every exempt workflow is printed BY NAME on every run. A silent exemption is how a thing
# stops being looked at, and fleet-turn-check — exempt here — is the gate that proves an
# agent can complete a turn. The count comes from the entry scan and the lines from the
# print, so dropping the print goes red instead of going quiet.
sed -n 's/^EXEMPT\t\([^\t]*\)\t/      exempt: \1 — /p' "$report"
exempt_named=$(grep -c '^EXEMPT	' "$report")
exempt_counted=$(sed -n 's/.*\bexempt=\([0-9]*\).*/\1/p' "$report")

named_matches_counted() {
  [ -n "$exempt_counted" ] && [ "$exempt_named" = "$exempt_counted" ]
}

# One assertion per rule, each named as design/fleet-suites.toml declares it.
#
# THE TRAILING TOKEN IS THE JOIN ANCHOR, not decoration (W9). `check <id>` names the id to
# bash but to nothing else, and `exempt-named` below is a plain assert whose id appeared
# nowhere in this file at all — so the manifest and this file agreed by convention only and
# a rename on either side went unnoticed. The anchors are read back by asserts-anchored in
# tests/test_workflow_coverage.py, in both directions: a declared id with no anchor here is
# red, and an anchor this file's entry does not declare is red too. Move an id and update
# both, or the gate says so.
check() {
  local id=$1 desc=$2
  assert "$desc" "! grep -q '^PROBLEM	$id	' '$report'"
  sed -n "s/^PROBLEM\t$id\t/      /p" "$report"
}

check parse-integrity \
  'the coverage figure was computed from entries that actually parsed'  # (::parse-integrity)
check standing-has-suite \
  'every standing workflow without suite_exempt names at least one suite'  # (::standing-has-suite)
check suite-paths-exist \
  'every path named in a suite exists on disk'  # (::suite-paths-exist)
assert 'every exempt workflow is printed by name, never merely skipped' \
  named_matches_counted  # (::exempt-named)
check no-orphan-suite \
  'every suite is claimed by a workflow or by design/fleet-suites.toml'  # (::no-orphan-suite)
check timer-family-declared \
  'every *.timer family in systemd/ has a manifest entry'  # (::timer-family-declared)
check asserts-anchored \
  'every asserts id is anchored in the suite it names, and every anchor is declared'  # (::asserts-anchored)

exit $fail
