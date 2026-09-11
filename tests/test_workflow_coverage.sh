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

# FIXTURES FIRST, LIVE TREE SECOND (T4.5). The contract-field rules turned mandatory over a
# tree that already complied, so the live run below cannot show they detect anything. Two
# mktemp roots do: a healthy one that must yield none of the four ids, and an offending one
# where each rule has a known number of offenders, asserted by exact count so a rule that
# stops firing is red rather than quiet. Fixture output goes to a file and is grepped, never
# printed, so no PROBLEM line reaches the gate output on a pass.
fx=$(mktemp -d)
report=$(mktemp)
trap 'rm -rf "$fx" "$report"' EXIT

fixture_root() {              # $1 name — a root whose one manifest is read from stdin
  local root=$fx/$1
  mkdir -p "$root/design/agents" "$root/design/contracts"
  : >"$root/design/contracts/alpha.md"
  : >"$root/design/contracts/beta.md"
  cat >"$root/design/agents/fx.toml"
  echo "$root"
}

ok=$(fixture_root ok <<'EOF'
[[workflows]]
unit = "alpha"
logical_workflow = "alpha"
status = "standing"
contract = "design/contracts/alpha.md"

[[workflows]]
unit = "alpha-change"
logical_workflow = "alpha"
status = "standing"
contract = "design/contracts/alpha.md"

[[workflows]]
unit = "old"
status = "spent"
contract_exempt = "spent: fired once and is disabled"
EOF
)

bad=$(fixture_root bad <<'EOF'
[[workflows]]
unit = "none"
status = "standing"

[[workflows]]
unit = "both"
status = "spent"
contract = "design/contracts/alpha.md"
contract_exempt = "spent: yet names a contract too"

[[workflows]]
unit = "live-exempt"
status = "standing"
contract_exempt = "still running, exempted anyway"

[[workflows]]
unit = "old-blank"
status = "spent"
contract_exempt = ""

[[workflows]]
unit = "dup"
status = "standing"
contract = "design/contracts/alpha.md"

[[workflows]]
unit = "dup"
status = "standing"
contract = "design/contracts/alpha.md"

[[workflows]]
unit = "orphan-trigger"
logical_workflow = "nothing-declares-this"
status = "standing"
contract = "design/contracts/alpha.md"

[[workflows]]
unit = "beta"
status = "standing"
contract = "design/contracts/alpha.md"

[[workflows]]
unit = "beta-change"
logical_workflow = "beta"
status = "standing"
contract = "design/contracts/beta.md"
EOF
)

count_id() {                  # $1 root  $2 id — how many PROBLEM lines carry that id
  python3 tests/test_workflow_coverage.py "$1" 2>&1 | grep -c "^PROBLEM	$2	"
}

echo "--- fixtures: the contract-field rules name their offenders ---"
for id in contract-declared contract-exempt-spent logical-workflow-reconciled; do
  assert "a healthy root yields no $id" "[ \"\$(count_id '$ok' $id)\" = 0 ]"
done
assert 'the healthy root prints its one exemption by name' \
  "python3 tests/test_workflow_coverage.py '$ok' | grep -q '^CONTRACT_EXEMPT	old	'"
assert 'the healthy root reconciles three standing entries to two logical workflows' \
  "python3 tests/test_workflow_coverage.py '$ok' | grep -q '^SECOND_TRIGGER	alpha-change	alpha$'"
assert 'contract-declared names the entry with neither field and the entry with both' \
  "[ \"\$(count_id '$bad' contract-declared)\" = 2 ]"
assert 'contract-exempt-spent names the standing exemption and the blank reason' \
  "[ \"\$(count_id '$bad' contract-exempt-spent)\" = 2 ]"
assert 'logical-workflow-reconciled names the duplicate unit, the dangling key and the split contract' \
  "[ \"\$(count_id '$bad' logical-workflow-reconciled)\" = 3 ]"

echo "--- live tree ---"
python3 tests/test_workflow_coverage.py >"$report" 2>&1 || { cat "$report"; exit 1; }
grep -v '^\(PROBLEM\|EXEMPT\|CONTRACT_EXEMPT\|SECOND_TRIGGER\|SUMMARY\)	' "$report"
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

# Same shape for the contract exemptions (T4.5): the accepted ones are printed by name from
# the rule that accepted them, and the count comes from the summary.
sed -n 's/^CONTRACT_EXEMPT\t\([^\t]*\)\t/      contract exempt: \1 — /p' "$report"
contract_exempt_named=$(grep -c '^CONTRACT_EXEMPT	' "$report")
contract_exempt_counted=$(sed -n 's/.*\bcontract_exempt=\([0-9]*\).*/\1/p' "$report")

contract_exempt_named_matches_counted() {
  [ -n "$contract_exempt_counted" ] \
    && [ "$contract_exempt_named" = "$contract_exempt_counted" ]
}

# The standing reconciliation's own size, derived here (T4.5). Every second trigger is printed
# by name, so the number of standing entries that fold into another entry's logical workflow
# is counted from those lines and compared with what the summary says was folded. A deleted
# reconciliation prints neither and is red, not quiet.
sed -n 's/^SECOND_TRIGGER\t\([^\t]*\)\t\(.*\)/      second trigger: \1 -> \2/p' "$report"
second_named=$(grep -c '^SECOND_TRIGGER	' "$report")
standing_counted=$(sed -n 's/.*\bstanding=\([0-9]*\).*/\1/p' "$report")
logical_counted=$(sed -n 's/.*\bstanding_logical=\([0-9]*\).*/\1/p' "$report")

reconciliation_folds_only_named_triggers() {
  [ -n "$standing_counted" ] && [ -n "$logical_counted" ] \
    && [ "$logical_counted" -gt 0 ] \
    && [ $((standing_counted - logical_counted)) = "$second_named" ]
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
check contract-declared \
  'every entry names a contract or carries contract_exempt — never neither, never both'  # (::contract-declared)
check contract-exempt-spent \
  'every contract_exempt sits on a status = "spent" entry and names its reason'  # (::contract-exempt-spent)
assert 'every accepted contract exemption is printed by name, and named equals counted' \
  contract_exempt_named_matches_counted  # (::contract-exempt-named)
check logical-workflow-reconciled \
  'standing entries reconcile by logical_workflow: no duplicate unit, no dangling key, one contract per workflow'  # (::logical-workflow-reconciled)
assert 'and the reconciliation folds exactly the second triggers it names, so a deleted rule cannot pass as a clean one' \
  reconciliation_folds_only_named_triggers

exit $fail
