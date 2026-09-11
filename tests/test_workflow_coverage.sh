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
fixture_root=$(mktemp -d)
trap 'rm -f "$report"; rm -rf "$fixture_root"' EXIT
python3 tests/test_workflow_coverage.py >"$report" 2>&1 || { cat "$report"; exit 1; }
grep -v '^\(PROBLEM\|EXEMPT\|SUMMARY\)	' "$report"
# T1.1 ships red as PROBLEM lines, not a collapsed FAIL: — the land set-diff matches
# one line per missing path. Other PROBLEM ids stay filtered above.
# (::contract-exists)
grep '^PROBLEM	contract-exists	' "$report" || true
if grep -q '^PROBLEM	contract-exists	' "$report"; then
  fail=1
fi
# T1.2 ships red as PROBLEM lines, same reason as T1.1. tools/mcp mismatches stay
# behind check() below — they are green on the live tree.
# (::model-alias)
grep '^PROBLEM	model-alias	' "$report" || true
if grep -q '^PROBLEM	model-alias	' "$report"; then
  fail=1
fi

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

# The join's own size, asserted rather than merely printed. `check asserts-anchored` below is
# a NEGATIVE assertion — `! grep -q PROBLEM` — so it passes identically whether the join found
# nothing wrong or the rule was deleted from tests/test_workflow_coverage.py entirely. Proven
# 2026-09-04: removing the join block left this suite green, printing one line fewer. The
# reported count is therefore compared against a figure derived HERE, from this file's own
# anchors, the same way exempt-named compares two independent emissions above.
anchors_here=$(grep -cE '\(::[A-Za-z0-9][A-Za-z0-9_-]*\)' tests/test_workflow_coverage.sh)
join_ids=$(sed -n 's/^  asserts join: \([0-9]\{1,\}\) anchored.*/\1/p' "$report")
join_suites=$(sed -n 's/^  asserts join: [0-9]\{1,\} anchored id(s) matched across \([0-9]\{1,\}\) .*/\1/p' "$report")

join_reported_what_it_compared() {
  [ -n "$join_ids" ] && [ -n "$join_suites" ] \
    && [ "$join_suites" -gt 0 ] && [ "$anchors_here" -gt 0 ] \
    && [ "$join_ids" -ge "$anchors_here" ]
}

# Same vacuity shape as the asserts join: a printed count compared against a figure
# derived here. Walking only the entries that name a contract would print 17 of 33
# (or 17 of 17) and this would fail; deleting the join prints nothing and this fails.
contract_checked=$(sed -n 's/^  contract join: checked \([0-9]\{1,\}\) of .*/\1/p' "$report")
contract_of=$(sed -n 's/^  contract join: checked [0-9]\{1,\} of \([0-9]\{1,\}\) entries.*/\1/p' "$report")
entries_summary=$(sed -n 's/.*\bentries=\([0-9]*\).*/\1/p' "$report")
live_entries=$(cat design/agents/*.toml | grep -c '^\[\[workflows\]\]' || true)

contract_join_checked_every_entry() {
  [ -n "$contract_checked" ] && [ "$contract_checked" = "$contract_of" ] \
    && [ "$contract_checked" = "$entries_summary" ] \
    && [ "$contract_checked" = "$live_entries" ] \
    && [ "$contract_checked" -gt 0 ]
}

runner_checked=$(sed -n 's/^  runner join: checked \([0-9]\{1,\}\) of .*/\1/p' "$report")
runner_of=$(sed -n 's/^  runner join: checked [0-9]\{1,\} of \([0-9]\{1,\}\) entries.*/\1/p' "$report")

runner_join_checked_every_entry() {
  [ -n "$runner_checked" ] && [ "$runner_checked" = "$runner_of" ] \
    && [ "$runner_checked" = "$entries_summary" ] \
    && [ "$runner_checked" = "$live_entries" ] \
    && [ "$runner_checked" -gt 0 ]
}

# Same shape again for T3.2, plus one more figure: the heading-extraction count is compared
# against the manifests' own `skills_mechanism` lines and must be > 0, so the branch that
# reads a profile instead of a runner is proven to have run, not merely to exist.
skills_checked=$(sed -n 's/^  skills join: checked \([0-9]\{1,\}\) of .*/\1/p' "$report")
skills_of=$(sed -n 's/^  skills join: checked [0-9]\{1,\} of \([0-9]\{1,\}\) entries.*/\1/p' "$report")
skills_he=$(sed -n 's/^  skills join: checked [0-9]\{1,\} of [0-9]\{1,\} entries, \([0-9]\{1,\}\) heading-extraction.*/\1/p' "$report")
live_he=$(cat design/agents/*.toml | grep -c '^skills_mechanism *= *"heading-extraction"' || true)

skills_join_checked_every_entry() {
  [ -n "$skills_checked" ] && [ "$skills_checked" = "$skills_of" ] \
    && [ "$skills_checked" = "$entries_summary" ] \
    && [ "$skills_checked" = "$live_entries" ] \
    && [ "$skills_checked" -gt 0 ] \
    && [ -n "$skills_he" ] && [ "$skills_he" = "$live_he" ] \
    && [ "$skills_he" -gt 0 ]
}

# --- T3.2 negative controls ---------------------------------------------------------------
# `check skills-*` below are negative assertions and pass identically whether the join found
# nothing wrong or never looked. So the join is also shown to BITE: the trees the .py reads
# are copied, one entry of one manifest is mutated, and the skills-* ids the copy reports
# must be exactly the one the mutation earns. The .py derives its root from its own
# location, so the fixture is a checkout-shaped directory rather than an env override, and
# an unmutated copy is run first so the four mutations are the only difference measured.
#
# Each result is `<entries checked>:<skills-* ids, comma-joined>`. The count is the positive
# half: a fixture whose python never ran, or ran against an empty copy, yields no ids and
# would otherwise read as clean — the first version of this function did exactly that.
skills_fixture() {  # skills_fixture <name> <manifest> <unit> <sed-expr>
  local name=$1 manifest=$2 unit=$3 expr=$4
  local dir="$fixture_root/$name"
  mkdir -p "$dir"
  cp -r design tests bin systemd skills profiles "$dir"/
  if [ -n "$expr" ]; then
    sed -i "/^unit *= *\"$unit\"/,/^\[\[workflows\]\]/{$expr}" "$dir/design/agents/$manifest.toml"
  fi
  python3 "$dir/tests/test_workflow_coverage.py" >"$dir/report" 2>/dev/null
  printf '%s:%s\n' \
    "$(sed -n 's/^  skills join: checked \([0-9]\{1,\}\) of .*/\1/p' "$dir/report")" \
    "$(sed -n 's/^PROBLEM\t\(skills-[a-z-]*\)\t.*/\1/p' "$dir/report" | sort -u | paste -sd,)"
}
fx_clean=$(skills_fixture clean claudius knowledge-digest '')
fx_declared=$(skills_fixture declared claudius knowledge-digest '/^skills *= \[/d')
fx_join=$(skills_fixture join claudius knowledge-digest 's/^skills *= \[.*\]/skills = ["meeting-prep"]/')
fx_mechanism=$(skills_fixture mechanism trajan fleet-turn-check 's/^skills *= \[\]/skills = []\nskills_mechanism = "heading-extraction"/')
fx_unreachable=$(skills_fixture unreachable trajan fleet-turn-check 's/^skills *= \[\]/skills = ["systematic-debugging"]/')

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
assert 'and the join says how much it compared, so a deleted rule cannot pass as a clean one' \
  join_reported_what_it_compared  # (::asserts-join-counted)
assert 'the contract-path join checked every parsed entry, so skipping the ones without a field cannot pass as a clean run' \
  contract_join_checked_every_entry  # (::contract-join-counted)
check runner-tools \
  'every joined runner --allowedTools equals surfaces.scheduled.tools, plus tools_web when web is true'  # (::runner-tools)
check runner-mcp \
  'every joined empty mcp is --strict-mcp-config and empty mcpServers'  # (::runner-mcp)
assert 'the runner join checked every parsed entry, so skipping the ones without a runner cannot pass as a clean run' \
  runner_join_checked_every_entry  # (::runner-join-counted)
check skills-declared \
  'every entry carries skills = [...] as a list of distinct strings; an empty offer is written []'  # (::skills-declared)
check skills-mechanism \
  'skills_mechanism, when present, is heading-extraction over an in-repo profile that extracts pointers in the owner tree'  # (::skills-mechanism)
check skills-join \
  'every declared skills list equals the offer its mechanism delivers to the run'  # (::skills-join)
assert 'the skills join checked every parsed entry and exercised the heading-extraction branch, so a skipped entry or a dead branch cannot pass as a clean run' \
  skills_join_checked_every_entry  # (::skills-join-counted)
assert 'fixture control: an unmutated copy of the checkout checks every entry and reports no skills-* problem' \
  "[ \"\$fx_clean\" = \"\$live_entries:\" ]"
assert 'fixture (a): an entry with skills removed is skills-declared, and only that' \
  "[ \"\$fx_declared\" = \"\$live_entries:skills-declared\" ]"
assert 'fixture (b): a claudius entry declaring only meeting-prep is skills-join, and only that' \
  "[ \"\$fx_join\" = \"\$live_entries:skills-join\" ]"
assert 'fixture (c): heading-extraction on an entry with no profile is skills-mechanism, and only that' \
  "[ \"\$fx_mechanism\" = \"\$live_entries:skills-mechanism\" ]"
assert 'fixture (d): a trajan entry declaring systematic-debugging is skills-join — an unreachable tree cannot be declared as delivered' \
  "[ \"\$fx_unreachable\" = \"\$live_entries:skills-join\" ]"

exit $fail
