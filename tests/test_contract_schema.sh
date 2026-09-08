#!/usr/bin/env bash
# design/contract-schema.md declares eight sections in a fixed order and says of the owner
# in ## Identity that "D3's validator exists to keep the two ends equal". Until 2026-09-08
# (T1.4, docs/dev-plan-2026-09.md) no validator existed: two contracts were written by hand
# against the schema, ten more land in Phase 4 by as many sessions, and nothing would have
# named a missing section, an owner that disagreed with the declaring manifest, or two
# contracts claiming one unit. This suite is that validator's entry point; the rules live in
# tests/test_contract_schema.py, which prints one PROBLEM line per finding so a failure here
# names the file and the rule rather than a count.
#
# THE RULES, one id each — the same ids design/fleet-suites.toml declares for this suite:
#   sections-present / sections-ordered / sections-nonempty  the eight `## ` headings, once
#     each, in schema order, none empty ("none" counts). Extra `##` sections are allowed.
#   owner-matches-manifest   the bold tokens in Identity's Owner(s) row equal the manifests
#     whose [[workflows]].contract names the file, both directions.
#   units-match-manifest     Identity's Unit(s) row (brace-expanded, .service/.timer stripped)
#     equals the declaring entries' `unit` values, both directions.
#   one-contract-per-unit    no unit is named by entries pointing at two contract paths.
#   contract-declared        every design/contracts/*.md is named by some manifest.
#   named-for-unit           the file stem is one of its units (rule 1), or the preamble says
#     it `breaks rule 1` and an EXEMPT line names it on every run.
#   manifest-parse           a manifest that does not parse is named, not silently dropped.
#
# WHAT THIS DOES NOT ASSERT. That a contract named by a manifest exists — T1.1's rule in
# tests/test_workflow_coverage.py, which ships red on the ten missing files. That an
# acceptance check is executable — T4.0 extends the validator for that.
#
# FIXTURES FIRST, LIVE TREE SECOND. Group 1 builds two roots under mktemp: a healthy one that
# must yield no PROBLEM, and a broken one where each rule has exactly one offender and the
# total is asserted, so a rule that stopped firing is red rather than quiet. Fixture output
# goes to a file and is grepped, never printed, so no PROBLEM line reaches the gate output on
# a pass. No box precondition: every checkout carries both inputs, so this never prints SKIP.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

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

validate() {                  # $1 root — the report on stdout, exit status is the python's
  python3 "$REPO_ROOT/tests/test_contract_schema.py" "$1"
}

# --- fixture builders ----------------------------------------------------------------------
# A contract with all eight sections in order. $1 path, $2 the Unit(s) row, $3 the Owner(s)
# row (empty string for none), $4 optional preamble line before ## Identity.
mk_contract() {
  {
    echo "# Contract: $(basename "$1" .md)"
    echo
    if [ -n "${4:-}" ]; then echo "$4"; echo; fi
    echo '## Identity'
    echo
    echo '| | |'
    echo '|---|---|'
    echo "$2"
    [ -n "$3" ] && echo "$3"
    echo '| Surface | S2 |'
    cat <<'EOF'

## Trigger

`OnCalendar=Sun 09:00`, `RandomizedDelaySec=5min`.

## Inputs

none

## Outputs

One file. The fence below carries a required heading that must not count:

```
## Inputs
```

## Decline conditions

none

## Side effects

none

## Acceptance checks

1. **Artifact exists.** `test -f`.

## Known failure modes

none
EOF
  } >"$1"
}

mk_entry() {                  # $1 manifest file, $2 unit, $3 contract path — appends one entry
  printf '\n[[workflows]]\nunit     = "%s"\ncontract = "%s"\nstatus   = "standing"\n' "$2" "$3" >>"$1"
}

echo "--- 0. canary ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT

echo "--- 1a. fixtures: a healthy root is silent and names its one exemption ---"
H="$fx/healthy"
mkdir -p "$H/design/contracts" "$H/design/agents"
mk_entry "$H/design/agents/claudius.toml" knowledge-digest design/contracts/knowledge-digest.md
mk_entry "$H/design/agents/marcus.toml"   buzz-agent@marcus design/contracts/shared-thing.md
mk_entry "$H/design/agents/trajan.toml"   buzz-agent@trajan design/contracts/shared-thing.md
mk_contract "$H/design/contracts/knowledge-digest.md" \
  '| Unit | `knowledge-digest.service` / `.timer` |' \
  '| Owner | **claudius** (`design/agents/claudius.toml`) |'
mk_contract "$H/design/contracts/shared-thing.md" \
  '| Units | `buzz-agent@{marcus,trajan}.service` (`--user` scope) |' \
  '| Owners | **marcus**, **trajan** — each unit'"'"'s own manifest |' \
  '**This one breaks rule 1 of the schema deliberately, and says so.**'

rc=0; validate "$H" >"$fx/healthy.out" 2>&1 || rc=$?
assert "the validator runs on the healthy root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/healthy.out' ]"
assert 'a healthy root yields no PROBLEM line' "! grep -q '^PROBLEM	' '$fx/healthy.out'"
assert 'the shared contract that says it breaks rule 1 is EXEMPT by name, once' \
  "[ \"\$(grep -c '^EXEMPT	' '$fx/healthy.out')\" = 1 ] && grep -q '^EXEMPT	design/contracts/shared-thing.md	' '$fx/healthy.out'"
assert 'the summary counts both contracts, both declared paths and the one exemption' \
  "grep -q '^SUMMARY	contracts=2 declared=2 absent=0 exempt=1\$' '$fx/healthy.out'"

echo "--- 1b. fixtures: each rule names exactly its offender ---"
B="$fx/broken"
mkdir -p "$B/design/contracts" "$B/design/agents"
C="$B/design/agents/claudius.toml"
for u in missing-section dup-section out-of-order empty-section wrong-owner no-owner-row wrong-unit; do
  mk_entry "$C" "$u" "design/contracts/$u.md"
  mk_contract "$B/design/contracts/$u.md" "| Unit | \`$u.service\` |" '| Owner | **claudius** |'
done
# sections-present: one section gone; one doubled
sed -i '/^## Side effects$/,/^## Acceptance checks$/{/^## Acceptance checks$/!d}' "$B/design/contracts/missing-section.md"
sed -i 's/^## Known failure modes$/## Inputs\n\nagain\n\n## Known failure modes/' "$B/design/contracts/dup-section.md"
# sections-ordered: the whole Trigger block moved ahead of Identity, bodies intact
awk '/^## Identity$/{s=1} /^## Trigger$/{s=2} /^## Inputs$/{s=3}
     s==0{print; next} s==1{id=id $0 "\n"; next} s==2{tr=tr $0 "\n"; next}
     s==3 && !done{printf "%s%s", tr, id; done=1} {print}' \
  "$B/design/contracts/out-of-order.md" >"$B/design/contracts/out-of-order.tmp"
mv "$B/design/contracts/out-of-order.tmp" "$B/design/contracts/out-of-order.md"
# sections-nonempty: Decline conditions with no body
sed -i '/^## Decline conditions$/,/^## Side effects$/{/^## Decline conditions$/b;/^## Side effects$/b;d}' "$B/design/contracts/empty-section.md"
# owner-matches-manifest: names a real manifest that does not declare it; row absent
sed -i 's/^| Owner | \*\*claudius\*\* |$/| Owner | **marcus** |/' "$B/design/contracts/wrong-owner.md"
sed -i '/^| Owner |/d' "$B/design/contracts/no-owner-row.md"
# units-match-manifest: the row names another unit
sed -i 's/^| Unit | `wrong-unit.service` |$/| Unit | `other-unit.service` |/' "$B/design/contracts/wrong-unit.md"
# contract-declared: a file no manifest names
mk_contract "$B/design/contracts/undeclared.md" '| Unit | `undeclared.service` |' '| Owner | **claudius** |'
# named-for-unit: declared for some-unit, stem says otherwise, no exemption
mk_entry "$C" some-unit design/contracts/misnamed.md
mk_contract "$B/design/contracts/misnamed.md" '| Unit | `some-unit.service` |' '| Owner | **claudius** |'
# one-contract-per-unit: two manifests, two contracts, one unit (both exempt from the stem rule)
mk_entry "$C" dup-unit design/contracts/dup-a.md
mk_entry "$B/design/agents/marcus.toml" dup-unit design/contracts/dup-b.md
mk_contract "$B/design/contracts/dup-a.md" '| Unit | `dup-unit.service` |' '| Owner | **claudius** |' 'It breaks rule 1 on purpose.'
mk_contract "$B/design/contracts/dup-b.md" '| Unit | `dup-unit.service` |' '| Owner | **marcus** |' 'It breaks rule 1 on purpose.'
# manifest-parse
printf '[[workflows\nunit = "x"\n' >"$B/design/agents/broken.toml"

rc=0; validate "$B" >"$fx/broken.out" 2>&1 || rc=$?
assert "the validator runs on the broken root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/broken.out' ]"
assert 'a missing section is named with the file' \
  "grep -q '^PROBLEM	sections-present	design/contracts/missing-section.md: missing ## Side effects' '$fx/broken.out'"
assert 'a doubled section is named with its count' \
  "grep -q '^PROBLEM	sections-present	design/contracts/dup-section.md: ## Inputs appears 2 times' '$fx/broken.out'"
assert 'a section out of schema order is named' \
  "grep -q '^PROBLEM	sections-ordered	design/contracts/out-of-order.md: ## Trigger is out of place' '$fx/broken.out'"
assert 'an empty section is named' \
  "grep -q '^PROBLEM	sections-nonempty	design/contracts/empty-section.md: ## Decline conditions is empty' '$fx/broken.out'"
assert 'a required heading inside a code fence is not a section (every fixture fences one)' \
  "! grep -q 'knowledge-digest.md: ## Inputs appears' '$fx/healthy.out' && ! grep -q 'missing-section.md: ## Inputs appears' '$fx/broken.out'"
assert 'an Owner row naming a manifest that does not declare the file is named, both sides shown' \
  "grep -q '^PROBLEM	owner-matches-manifest	design/contracts/wrong-owner.md: Owner row names marcus; declared by claudius' '$fx/broken.out'"
assert 'an Identity with no Owner row is named' \
  "grep -q '^PROBLEM	owner-matches-manifest	design/contracts/no-owner-row.md: no Owner/Owners row' '$fx/broken.out'"
assert 'a Unit row disagreeing with the declaring entries is named, both sides shown' \
  "grep -q '^PROBLEM	units-match-manifest	design/contracts/wrong-unit.md: Unit row names other-unit; manifests declare wrong-unit' '$fx/broken.out'"
assert 'a contract no manifest names is named' \
  "grep -q '^PROBLEM	contract-declared	design/contracts/undeclared.md: named by no' '$fx/broken.out'"
assert 'a file whose stem is none of its units, with no exemption, is named' \
  "grep -q '^PROBLEM	named-for-unit	design/contracts/misnamed.md: stem is none of its units (some-unit)' '$fx/broken.out'"
assert 'a unit named by two contract paths is named once, with both paths' \
  "[ \"\$(grep -c '^PROBLEM	one-contract-per-unit	' '$fx/broken.out')\" = 1 ] && grep '^PROBLEM	one-contract-per-unit	dup-unit: ' '$fx/broken.out' | grep -q 'dup-a.md.*dup-b.md'"
assert 'a manifest that does not parse is named' \
  "grep -q '^PROBLEM	manifest-parse	broken.toml: does not parse' '$fx/broken.out'"
assert 'and those eleven are the only findings — every rule fired exactly once' \
  "[ \"\$(grep -c '^PROBLEM	' '$fx/broken.out')\" = 11 ]"
[ "$(grep -c '^PROBLEM	' "$fx/broken.out")" = 11 ] || sed -n 's/^PROBLEM\t/      /p' "$fx/broken.out"
assert 'the two rule-1 exemptions in the broken root are printed by name' \
  "[ \"\$(grep -c '^EXEMPT	' '$fx/broken.out')\" = 2 ]"

echo "--- 2. the live tree: $REPO_ROOT/design/contracts against design/agents ---"
report="$fx/live.out"
validate "$REPO_ROOT" >"$report" 2>&1 || { cat "$report"; fail=1; }
grep -v '^\(PROBLEM\|EXEMPT\|SUMMARY\)	' "$report"
sed -n 's/^EXEMPT\t\([^\t]*\)\t/      exempt: \1 — /p' "$report"

# One assertion per rule, each anchored to the id design/fleet-suites.toml declares for it, so
# tests/test_workflow_coverage.py::asserts-anchored can read the two sides against each other.
check() {
  local id=$1 desc=$2
  assert "$desc" "! grep -q '^PROBLEM	$id	' '$report'"
  sed -n "s/^PROBLEM\t$id\t/      /p" "$report"
}

check manifest-parse \
  'every design/agents/*.toml parses, so the owner join reads all of them'  # (::manifest-parse)
check sections-present \
  'every contract carries each of the eight sections exactly once'  # (::sections-present)
check sections-ordered \
  'and in schema order'  # (::sections-ordered)
check sections-nonempty \
  'and none of them empty'  # (::sections-nonempty)
check contract-declared \
  'every contract file is named by a [[workflows]] entry'  # (::contract-declared)
check owner-matches-manifest \
  "every contract's Owner row equals the manifests that declare it"  # (::owner-matches-manifest)
check units-match-manifest \
  "every contract's Unit row equals the units of the entries that declare it"  # (::units-match-manifest)
check one-contract-per-unit \
  'no unit is claimed by two contract paths'  # (::one-contract-per-unit)
check named-for-unit \
  'every contract is named for one of its units, or says it breaks rule 1'  # (::named-for-unit)

exempt_named=$(grep -c '^EXEMPT	' "$report")
exempt_counted=$(sed -n 's/.*\bexempt=\([0-9]*\).*/\1/p' "$report")
assert 'every rule-1 exemption is printed by name, never merely skipped' \
  "[ -n \"\$exempt_counted\" ] && [ \"\$exempt_named\" = \"\$exempt_counted\" ]"  # (::exempt-named)

# The vacuity guard: the count the validator reports is compared to one computed here, so a
# validator that read an empty directory — or the wrong one — is red rather than clean.
here=$(find "$REPO_ROOT/design/contracts" -maxdepth 1 -name '*.md' | wc -l)
counted=$(sed -n 's/^SUMMARY\tcontracts=\([0-9]*\) .*/\1/p' "$report")
assert "the validator judged every contract on disk ($here), not fewer" \
  "[ -n \"\$counted\" ] && [ \"\$counted\" -ge 1 ] && [ \"\$counted\" = \"\$here\" ]"  # (::validated-count)

exit $fail
