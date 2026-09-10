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
#   named-for-unit           the file stem is one of its units (rule 1), or a declaring
#     [[workflows]] entry carries `rule1_exempt = "<reason>"` and an EXEMPT line names it on
#     every run. The opt-out was a `breaks rule 1` substring in the contract's preamble until
#     2026-09-09; a substring cannot be read for polarity, so a contract saying the OPPOSITE —
#     that some other file breaks rule 1 — exempted itself. A declaration can.
#   manifest-parse           a manifest that does not parse is named, not silently dropped.
#   entry-shape              a [[workflows]] entry naming a contract and no unit is named; it
#     used to reach sorted() beside a str and die as a traceback rather than a finding.
#   contract-parseable       an unterminated code fence is named as the fence. It swallows
#     every heading below it, so the section rules would otherwise report six missing
#     sections in a file that has all eight.
#   schema-sections          the eight section names are READ from design/contract-schema.md,
#     not retyped here, and there must be exactly eight of them. A schema doc the validator
#     could not read would grade every contract against an empty list and call it clean —
#     which is why every fixture root below is given a copy of the real one.
#
# WHAT THIS DOES NOT ASSERT. That a contract named by a manifest exists — T1.1's rule in
# tests/test_workflow_coverage.py, which ships red on the ten missing files. That an
# acceptance check is executable — T4.0 extends the validator for that.
#
# FIXTURES FIRST, LIVE TREE SECOND. Group 1 builds five roots under mktemp: a healthy one that
# must yield no PROBLEM, a broken one where each rule has exactly one offender and the total is
# asserted so a rule that stopped firing is red rather than quiet, and three small ones for the
# rules whose offenders cannot share a root without doubling another rule's count. Fixture
# output goes to a file and is grepped, never printed, so no PROBLEM line reaches the gate
# output on a pass. No box precondition: every checkout carries both inputs, so this never
# prints SKIP.
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
# The conforming ## Acceptance checks body every fixture gets unless it is overriding it to be
# the one offender of a rule. Two items, so "exactly one block per item" is exercised in the
# healthy direction; the second declares a vantage and an exit-77 branch, which are the two
# things T4.0 added that a single trivial block would never reach.
DEFAULT_CHECKS=$(cat <<'EOF'
1. **Artifact exists and is this run's.**

   ```check id=artifact-is-this-run
   test -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_thing.md" \
                -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   ```

2. **The timer fired.**

   ```check id=timer-fired when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) exit 77 ;; esac
   [ "$(( $(date +%s) - ${t#@} ))" -lt 691200 ]
   ```
EOF
)

# A contract with all eight sections in order. $1 path, $2 the Unit(s) row, $3 the Owner(s)
# row (empty string for none), $4 optional preamble line before ## Identity, $5 an override
# for the ## Acceptance checks body (default: DEFAULT_CHECKS).
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

EOF
    printf '%s\n' "${5:-$DEFAULT_CHECKS}"
    cat <<'EOF'

## Known failure modes

none
EOF
  } >"$1"
}

mk_entry() {                  # $1 manifest, $2 unit ('' omits it), $3 contract, $4 rule1_exempt
  {
    printf '\n[[workflows]]\n'
    [ -n "$2" ] && printf 'unit     = "%s"\n' "$2"
    printf 'contract = "%s"\nstatus   = "standing"\n' "$3"
    [ -n "${4:-}" ] && printf 'rule1_exempt = "%s"\n' "$4"
    true
  } >>"$1"
}

mk_root() {                   # $1 root — design/{contracts,agents} plus the real schema doc
  mkdir -p "$1/design/contracts" "$1/design/agents"
  cp "$REPO_ROOT/design/contract-schema.md" "$1/design/contract-schema.md"
}

echo "--- 0. canary ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT

echo "--- 1a. fixtures: a healthy root is silent and names its one exemption ---"
H="$fx/healthy"
mk_root "$H"
mk_entry "$H/design/agents/claudius.toml" knowledge-digest design/contracts/knowledge-digest.md
mk_entry "$H/design/agents/marcus.toml"   buzz-agent@marcus design/contracts/shared-thing.md \
  'five units, one runtime — five files would be five copies of one fact'
mk_entry "$H/design/agents/trajan.toml"   buzz-agent@trajan design/contracts/shared-thing.md \
  'five units, one runtime — five files would be five copies of one fact'
mk_entry "$H/design/agents/marcus.toml"   pipe-thing design/contracts/pipe-thing.md
mk_contract "$H/design/contracts/knowledge-digest.md" \
  '| Unit | `knowledge-digest.service` / `.timer` |' \
  '| Owner | **claudius** (`design/agents/claudius.toml`) |'
mk_contract "$H/design/contracts/shared-thing.md" \
  '| Units | `buzz-agent@{marcus,trajan}.service` (`--user` scope) |' \
  '| Owners | **marcus**, **trajan** — each unit'"'"'s own manifest |' \
  '**buzz-interactive.md breaks rule 1 of the schema; the exemption is declared in the manifests.**'
# The three shapes a naive row parser gets wrong, in one Unit cell: an escaped pipe BEFORE the
# unit token (truncation drops the unit entirely), a pipe inside a code span, and a systemd
# specifier. Before 2026-09-09 this row declared `no unit` and, once un-truncated, a phantom `n`.
mk_contract "$H/design/contracts/pipe-thing.md" \
  '| Unit | alerted \| `pipe-thing.service`, `OnFailure=agent-alert@%n.service`, listed by `systemctl list-units | grep pipe` |' \
  '| Owner | **marcus** |'

rc=0; validate "$H" >"$fx/healthy.out" 2>&1 || rc=$?
assert "the validator runs on the healthy root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/healthy.out' ]"
assert 'a healthy root yields no PROBLEM line' "! grep -q '^PROBLEM	' '$fx/healthy.out'"
assert 'an escaped pipe, a pipe inside a code span and a %n specifier leave one real unit and no finding' \
  "! grep -q 'pipe-thing.md' '$fx/healthy.out'"
assert 'the shared contract whose manifests declare rule1_exempt is EXEMPT by name, once' \
  "[ \"\$(grep -c '^EXEMPT	' '$fx/healthy.out')\" = 1 ] && grep -q '^EXEMPT	design/contracts/shared-thing.md	.*rule1_exempt on 2 of 2' '$fx/healthy.out'"
assert 'the summary counts all three contracts, the declared paths, the one exemption, the eight sections and the six check blocks it graded' \
  "grep -q '^SUMMARY	contracts=3 declared=3 absent=0 exempt=1 sections=8 checks=6 env=' '$fx/healthy.out'"

echo "--- 1b. fixtures: each rule names exactly its offender ---"
B="$fx/broken"
mk_root "$B"
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
mk_entry "$C" dup-unit design/contracts/dup-a.md 'stem is the surface, not the unit'
mk_entry "$B/design/agents/marcus.toml" dup-unit design/contracts/dup-b.md 'stem is the surface, not the unit'
mk_contract "$B/design/contracts/dup-a.md" '| Unit | `dup-unit.service` |' '| Owner | **claudius** |'
mk_contract "$B/design/contracts/dup-b.md" '| Unit | `dup-unit.service` |' '| Owner | **marcus** |'
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

echo "--- 1c. fixtures: emptiness that reads as content ---"
# A sub-heading is a label and an empty fence is a hole. Both left `any(line.strip())` true,
# so `## Decline conditions` followed by `### When it declines` and nothing else read as full.
E="$fx/empty"
mk_root "$E"
for u in sub-only hollow-fence; do
  mk_entry "$E/design/agents/claudius.toml" "$u" "design/contracts/$u.md"
  mk_contract "$E/design/contracts/$u.md" "| Unit | \`$u.service\` |" '| Owner | **claudius** |'
done
sed -i '/^## Decline conditions$/,/^## Side effects$/{/^## Decline conditions$/b;/^## Side effects$/b;d}' "$E/design/contracts/sub-only.md"
sed -i 's/^## Decline conditions$/## Decline conditions\n\n### When it declines\n/' "$E/design/contracts/sub-only.md"
sed -i '/^## Side effects$/,/^## Acceptance checks$/{/^## Side effects$/b;/^## Acceptance checks$/b;d}' "$E/design/contracts/hollow-fence.md"
sed -i 's/^## Side effects$/## Side effects\n\n```\n```\n/' "$E/design/contracts/hollow-fence.md"

rc=0; validate "$E" >"$fx/empty.out" 2>&1 || rc=$?
assert "the validator runs on the emptiness root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/empty.out' ]"
assert 'a section whose whole body is a sub-heading is empty' \
  "grep -q '^PROBLEM	sections-nonempty	design/contracts/sub-only.md: ## Decline conditions is empty' '$fx/empty.out'"
assert 'a section whose whole body is an unfilled fence is empty' \
  "grep -q '^PROBLEM	sections-nonempty	design/contracts/hollow-fence.md: ## Side effects is empty' '$fx/empty.out'"
assert 'and those two are the only findings — a fenced ## Inputs still counts as content' \
  "[ \"\$(grep -c '^PROBLEM	' '$fx/empty.out')\" = 2 ]"

echo "--- 1d. fixtures: shapes that used to be a traceback or a wrong verdict ---"
S="$fx/shapes"
mk_root "$S"
mk_entry "$S/design/agents/claudius.toml" '' design/contracts/no-unit.md
mk_entry "$S/design/agents/claudius.toml" open-fence design/contracts/open-fence.md
mk_contract "$S/design/contracts/no-unit.md" '| Unit | none declared |' '| Owner | **claudius** |'
mk_contract "$S/design/contracts/open-fence.md" '| Unit | `open-fence.service` |' '| Owner | **claudius** |'
printf '\n```\n' >>"$S/design/contracts/open-fence.md"

rc=0; validate "$S" >"$fx/shapes.out" 2>&1 || rc=$?
assert "the validator runs on the shapes root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/shapes.out' ]"
assert 'an entry naming a contract and no unit is a finding, not a TypeError in sorted()' \
  "grep -q '^PROBLEM	entry-shape	claudius.toml: a \[\[workflows\]\] entry names contract design/contracts/no-unit.md and no unit' '$fx/shapes.out'"
assert 'an unterminated fence is named as the fence, by line' \
  "grep -qE '^PROBLEM	contract-parseable	design/contracts/open-fence.md: the code fence opened on line [0-9]+ is never closed' '$fx/shapes.out'"
assert 'and it is reported once, not as the six sections it swallowed' \
  "[ \"\$(grep -c 'open-fence.md' '$fx/shapes.out')\" = 1 ]"
assert 'the shapes root reports exactly those three findings' \
  "[ \"\$(grep -c '^PROBLEM	' '$fx/shapes.out')\" = 3 ]"

echo "--- 1e. fixtures: the schema list is read, and a list that is not eight is named ---"
# Each of these roots has exactly one offence, so `mk_schema_vocab` writes the check
# vocabulary the T4.0 rules read; a root missing THAT is the next fixture down.
mk_schema_vocab() {            # $1 schema doc — appends the two vocabulary blocks
  cat >>"$1" <<'EOF'

#### Executor environment

- `UNIT` — the unit
- `RUN_DATE` — the run's date

#### Vantage

- `run` — from inside the run
- `sweep` — from outside, on a cadence
EOF
}
X="$fx/schema-short"; mkdir -p "$X/design"
printf '### `## Identity`\n### `## Trigger`\n### `## Inputs`\n' >"$X/design/contract-schema.md"
mk_schema_vocab "$X/design/contract-schema.md"
N="$fx/schema-absent"; mkdir -p "$N/design"
V="$fx/schema-novocab"; mkdir -p "$V/design"
sed -n '/^### `## /p' "$REPO_ROOT/design/contract-schema.md" >"$V/design/contract-schema.md"

assert 'a schema doc declaring three sections is named with the count it found' \
  "validate '$X' 2>&1 | grep -q '^PROBLEM	schema-sections	design/contract-schema.md: declares 3 '"
assert 'and it is the only finding — a short schema is not also reported as missing sections' \
  "[ \"\$(validate '$X' 2>&1 | grep -c '^PROBLEM	')\" = 1 ]"
assert 'a root with no schema doc at all is named, not graded against an empty list' \
  "validate '$N' 2>&1 | grep -q '^PROBLEM	schema-sections	design/contract-schema.md: absent'"
assert 'a schema doc declaring the eight sections and no executor environment is named' \
  "validate '$V' 2>&1 | grep -q '^PROBLEM	checks-vocabulary	design/contract-schema.md: declares no executor environment'"
assert 'and its missing vantage list is named too — both halves of the vocabulary are read' \
  "validate '$V' 2>&1 | grep -q '^PROBLEM	checks-vocabulary	design/contract-schema.md: declares no vantage'"
assert 'and those two are its only findings — the eight sections it does declare are not re-reported' \
  "[ \"\$(validate '$V' 2>&1 | grep -c '^PROBLEM	')\" = 2 ]"

echo "--- 1f. fixtures: the executable-check rules, one offender each ---"
# T4.0. A contract's ## Acceptance checks are the executor's suite (T5.1), so each item must
# carry a block it can RUN. Every offender below is a shape a hand-written contract actually
# reaches: prose next to the assertion instead of the command that decides it, a block that
# cannot fail, a block naming a variable nothing exports.
F="$fx/checks"
mk_root "$F"
FM="$F/design/agents/claudius.toml"

mk_offender() {               # $1 stem (also its unit), $2 the ## Acceptance checks body
  mk_entry "$FM" "$1" "design/contracts/$1.md"
  mk_contract "$F/design/contracts/$1.md" "| Unit | \`$1.service\` |" '| Owner | **claudius** |' \
    '' "$2"
}

# The healthy control: mk_contract's default body — one block per item, a declared vantage,
# an exit-77 branch, and every variable either exported by the executor or set in the block.
mk_entry "$FM" healthy-checks design/contracts/healthy-checks.md
mk_contract "$F/design/contracts/healthy-checks.md" \
  '| Unit | `healthy-checks.service` |' '| Owner | **claudius** |'

mk_offender no-check "$(cat <<'EOF'
1. **Artifact exists.** `bin/proposal_or_decline.sh` decides it. This is the shape the
   schema has always forbidden and nothing has ever caught: the command is named in prose,
   which is not the same as carrying one.
EOF
)"

mk_offender stray-check "$(cat <<'EOF'
1. **Artifact exists.**

   ```check id=has-a-block
   test -f /tmp
   ```

```check id=at-column-zero
test -f /tmp
```
EOF
)"

mk_offender two-checks "$(cat <<'EOF'
1. **Two assertions wearing one number.**

   ```check id=first
   test -f /tmp
   ```

   ```check id=second
   test -d /tmp
   ```
EOF
)"

mk_offender no-id "$(cat <<'EOF'
1. **Nameless.**

   ```check
   test -f /tmp
   ```
EOF
)"

mk_offender dup-id "$(cat <<'EOF'
1. **First.**

   ```check id=twice
   test -f /tmp
   ```

2. **Second, under the same name.**

   ```check id=twice
   test -d /tmp
   ```
EOF
)"

mk_offender bad-vantage "$(cat <<'EOF'
1. **From nowhere in particular.**

   ```check id=vantage when=whenever
   test -f /tmp
   ```
EOF
)"

mk_offender bad-attr "$(cat <<'EOF'
1. **Carrying an attribute the executor does not read.**

   ```check id=attr retries=3
   test -f /tmp
   ```
EOF
)"

mk_offender trivial "$(cat <<'EOF'
1. **A check that cannot fail is not a check.**

   ```check id=vacuous
   true
   ```
EOF
)"

mk_offender bad-syntax "$(cat <<'EOF'
1. **A fence exists; a command does not.**

   ```check id=unparseable
   [ -f /tmp ] &&
   ```
EOF
)"

mk_offender undeclared-var "$(cat <<'EOF'
1. **Reading something nothing exports.**

   ```check id=phantom
   [ -n "$NOT_DECLARED" ]
   ```
EOF
)"

rc=0; validate "$F" >"$fx/checks.out" 2>&1 || rc=$?
assert "the validator runs on the checks root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/checks.out' ]"
assert 'a prose-only check is named by its item number — the gate T4.0 was written for' \
  "grep -q '^PROBLEM	checks-executable	design/contracts/no-check.md: check 1 carries no check block' '$fx/checks.out'"
assert 'a check block outside any numbered item is named by line, not silently adopted by the item above' \
  "grep -qE '^PROBLEM	checks-executable	design/contracts/stray-check.md: the check block on line [0-9]+ sits outside any numbered item' '$fx/checks.out'"
assert 'two blocks under one item are named with the count' \
  "grep -q '^PROBLEM	checks-executable	design/contracts/two-checks.md: check 1 carries 2 check blocks' '$fx/checks.out'"
assert 'a block declaring no id is named — a receipt has nothing to call it' \
  "grep -q '^PROBLEM	checks-declared	design/contracts/no-id.md: check 1 declares no id=' '$fx/checks.out'"
assert 'an id used twice in one file is named, with the check that had it first' \
  "grep -q '^PROBLEM	checks-declared	design/contracts/dup-id.md: check 2 (id=twice): already used by check 1' '$fx/checks.out'"
assert 'a when= outside the declared vantages is named, with the ones that exist' \
  "grep -q '^PROBLEM	checks-declared	design/contracts/bad-vantage.md: check 1 (id=vantage): when=whenever is not a declared vantage' '$fx/checks.out'"
assert 'an attribute the executor does not read is named rather than ignored' \
  "grep -q '^PROBLEM	checks-declared	design/contracts/bad-attr.md: check 1 (id=attr): unknown attribute retries=' '$fx/checks.out'"
assert 'a block that cannot fail is named' \
  "grep -q '^PROBLEM	checks-decidable	design/contracts/trivial.md: check 1 (id=vacuous): the block cannot fail' '$fx/checks.out'"
assert 'a block bash -n rejects is named as the block, not as a missing section' \
  "grep -q '^PROBLEM	checks-syntax	design/contracts/bad-syntax.md: check 1 (id=unparseable): bash -n rejects the block' '$fx/checks.out'"
assert 'a block reading a variable the executor does not export is named, by variable' \
  "grep -q '^PROBLEM	checks-env	design/contracts/undeclared-var.md: check 1 (id=phantom): reads \$NOT_DECLARED' '$fx/checks.out'"
assert 'the healthy contract is named by none of them' \
  "! grep -q 'healthy-checks.md' '$fx/checks.out'"
assert 'and those ten are the only findings — every new rule fired exactly once' \
  "[ \"\$(grep -c '^PROBLEM	' '$fx/checks.out')\" = 10 ]"
[ "$(grep -c '^PROBLEM	' "$fx/checks.out")" = 10 ] || sed -n 's/^PROBLEM\t/      /p' "$fx/checks.out"
assert 'the summary counts the blocks it graded and the variables the schema declares' \
  "grep -qE '^SUMMARY	.* checks=[0-9]+ env=[0-9]+\$' '$fx/checks.out'"

echo "--- 1g. fixtures: a contract for an always-on unit is exempt from the check rules ---"
# By the manifest join, never by its own prose: a unit with kind = "service" has no run, so
# there is no RUN_DATE, no attempt log and no LastTriggerUSec for the executor to be given.
# `kind` is not self-assertion — tests/test_fleet_ownership.sh::kind-matches-unit-files
# already joins it against the unit files on disk.
A="$fx/always-on"
mk_root "$A"
printf '[[workflows]]\nunit = "always-on"\nkind = "service"\ncontract = "design/contracts/always-on.md"\n\n' \
  >"$A/design/agents/marcus.toml"
mk_contract "$A/design/contracts/always-on.md" '| Unit | `always-on.service` |' '| Owner | **marcus** |' \
  '' '1. **Prose, and no block.** There is no run to decide it from.'

rc=0; validate "$A" >"$fx/always-on.out" 2>&1 || rc=$?
assert "the validator runs on the always-on root (rc=$rc)" "[ '$rc' = 0 ] && [ -s '$fx/always-on.out' ]"
assert 'a contract whose declaring entries are all kind = service yields no check finding' \
  "! grep -q '^PROBLEM	checks-' '$fx/always-on.out'"
assert 'and it is EXEMPT by name, never merely skipped' \
  "grep -q '^EXEMPT	design/contracts/always-on.md	.*always-on.service.*no run' '$fx/always-on.out'"
assert 'the exemption is the whole finding — the section rules still ran on it' \
  "[ \"\$(grep -c '^PROBLEM	' '$fx/always-on.out')\" = 0 ]"

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
  'every contract is named for one of its units, or a declaring entry carries rule1_exempt'  # (::named-for-unit)
check entry-shape \
  'every [[workflows]] entry naming a contract also names the unit it is the contract for'  # (::entry-shape)
check contract-parseable \
  'every code fence in every contract is closed, so the headings below it are headings'  # (::contract-parseable)
check schema-sections \
  'design/contract-schema.md declares the eight sections this validator grades against'  # (::schema-sections)
check checks-vocabulary \
  'design/contract-schema.md declares the executor environment and the vantages, so the check rules grade against a vocabulary rather than an empty one'  # (::checks-vocabulary)
check checks-executable \
  'every acceptance check carries exactly one runnable block, and every block belongs to a check'  # (::checks-executable)
check checks-declared \
  'every check block declares a unique id and, if it declares a vantage, a declared one'  # (::checks-declared)
check checks-decidable \
  'no check block is empty or trivially true — a check that cannot fail is not a check'  # (::checks-decidable)
check checks-syntax \
  'bash -n accepts every check block, so a fence that exists is also a command that runs'  # (::checks-syntax)
check checks-env \
  'every variable a check block reads is exported by the executor or set in the block itself'  # (::checks-env)

sections_counted=$(sed -n 's/^SUMMARY\t.*sections=\([0-9]*\).*/\1/p' "$report")
assert "the eight section names came from the schema doc, not from an empty read (${sections_counted:-none})" \
  "[ \"\$sections_counted\" = 8 ]"  # (::schema-sections)

exempt_named=$(grep -c '^EXEMPT	' "$report")
exempt_counted=$(sed -n 's/.*\bexempt=\([0-9]*\).*/\1/p' "$report")
assert 'every rule-1 exemption is printed by name, never merely skipped' \
  "[ -n \"\$exempt_counted\" ] && [ \"\$exempt_named\" = \"\$exempt_counted\" ]"  # (::exempt-named)

# The vacuity guard: the count the validator reports is compared to one computed here, so a
# validator that read an empty directory — or the wrong one — is red rather than clean.
# The same guard for the T4.0 half: a validator that parsed no blocks would report every
# check rule clean. knowledge-digest.md alone carries nine.
checks_graded=$(sed -n 's/^SUMMARY\t.* checks=\([0-9]*\).*/\1/p' "$report")
env_declared=$(sed -n 's/^SUMMARY\t.* env=\([0-9]*\).*/\1/p' "$report")
assert "the check rules graded real blocks (${checks_graded:-none}), against a real environment (${env_declared:-none} vars)" \
  "[ -n \"\$checks_graded\" ] && [ \"\$checks_graded\" -ge 9 ] && [ -n \"\$env_declared\" ] && [ \"\$env_declared\" -ge 1 ]"  # (::checks-graded)

here=$(find "$REPO_ROOT/design/contracts" -maxdepth 1 -name '*.md' | wc -l)
counted=$(sed -n 's/^SUMMARY\tcontracts=\([0-9]*\) .*/\1/p' "$report")
assert "the validator judged every contract on disk ($here), not fewer" \
  "[ -n \"\$counted\" ] && [ \"\$counted\" -ge 1 ] && [ \"\$counted\" = \"\$here\" ]"  # (::validated-count)

exit $fail
