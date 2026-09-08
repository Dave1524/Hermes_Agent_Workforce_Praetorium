#!/usr/bin/env bash
# .claude/workflows/ship-dev-plan.js is the saved Workflow script that brief
# .claude/briefs/workflow-ship-feasibility.md §11 designed: it /ships dev-plan tasks one at a
# time, lands each through an independent verifier, and stops on the first failed assertion.
# The brief calls those rails "mechanical". They are, exactly as far as the code is right —
# and the Workflow tool runs the script with no gate of its own, against a live main and a
# live origin, for millions of tokens. This suite is where the control flow is proven first.
#
# GROUP 1 pins the script's hard-coded expectations to the tree it will run against: every
# task id is a bullet in docs/dev-plan-2026-09.md, T1.1's expected red list equals the
# contracts the manifests name and design/contracts/ lacks, and the entry count T1.1's gate
# greps for equals the live [[workflows]] count. Those figures were measured 2026-09-07 and
# copied into the script; the day a contract lands, this goes red and names the stale line.
#
# GROUP 2 runs the script through tests/ship_dev_plan_harness.mjs with scripted agent
# replies and asserts each stop rule fires, that a stop ships nothing further, and that a
# landed task's red set becomes the next task's baseline. No agent is spawned.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

SCRIPT=${SHIP_DEV_PLAN_SCRIPT:-.claude/workflows/ship-dev-plan.js}
HARNESS=tests/ship_dev_plan_harness.mjs
PLAN=docs/dev-plan-2026-09.md

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

fail=0
assert 'a found pattern is never reported as a failure' "yes | grep -q y"
assert 'node is on PATH (the harness needs it)' "command -v node >/dev/null"
assert "$SCRIPT exists" "[ -f $SCRIPT ]"
[ -f "$SCRIPT" ] || exit $fail

# --- group 1: the script against the tree ------------------------------------------------
echo "group 1: hard-coded expectations against the live tree"
assert 'the script begins with `export const meta = {` (the Workflow tool refuses anything else)' \
  "head -1 $SCRIPT | grep -q '^export const meta = {'"
assert 'no Date.now(), Math.random() or new Date() (they throw in a script and break resume)' \
  "! grep -qE 'Date\\.now\\(|Math\\.random\\(|new Date\\(' $SCRIPT"

task_ids=$(grep -oE "^  '(T[0-9]+\.[0-9]+)':" "$SCRIPT" | tr -d " ':")
assert 'the script declares at least one task' '[ -n "$task_ids" ]'
for id in $task_ids; do
  assert "task $id is a bullet in $PLAN" "grep -q -- '^- \*\*${id//./\\.}\*\*' $PLAN"
done

script_missing=$(sed -n "s/^const MISSING_CONTRACTS = \[\(.*\)\]$/\1/p" "$SCRIPT" | tr -d "' " | tr ',' '\n' | sort -u)
live_missing=$(comm -23 \
  <(grep -h '^contract *=' design/agents/*.toml | sed -E 's/^contract *= *"design\/contracts\/([^"]*)\.md".*/\1/' | sort -u) \
  <(ls design/contracts/ | sed 's/\.md$//' | sort -u))
assert "T1.1's expected red equals the contracts the manifests name and design/contracts/ lacks ($(echo "$live_missing" | wc -l))" \
  '[ -n "$script_missing" ] && [ "$script_missing" = "$live_missing" ]'

script_entries=$(sed -n 's/^const WORKFLOW_ENTRIES = \([0-9]*\)$/\1/p' "$SCRIPT")
live_entries=$(cat design/agents/*.toml | grep -c '^\[\[workflows\]\]')
assert "the entry count T1.1's gate greps for (${script_entries:-unset}) equals the live [[workflows]] count ($live_entries)" \
  '[ -n "$script_entries" ] && [ "$script_entries" = "$live_entries" ]'

script_aliases=$(sed -n "s/^const ALIAS_WORKFLOWS = \[\(.*\)\]$/\1/p" "$SCRIPT" | tr -d "' " | tr ',' '\n' | sort -u)
assert "T1.2's expected red is the plan's five alias workflows" \
  '[ "$(echo "$script_aliases" | wc -l)" = 5 ] && echo "$script_aliases" | grep -q m1-signal-scan'

# --- group 2: the control flow, agents scripted ------------------------------------------
echo "group 2: control flow through the harness"
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

FLEET='{"marcus":"m0","claudius":"c0","augustus":"a0","trajan":"t0","aurelian":"u0"}'
ENABLED='{"system":122,"user":14}'

args() {  # $1 tasks json; $2 optional jq filter applied afterwards
  jq -nc --argjson tasks "$1" --argjson fleet "$FLEET" --argjson enabled "$ENABLED" \
    '{today:"2026-09-08", tasks:$tasks, baselineRed:[], fleetStart:$fleet, enabled:$enabled}' \
    | jq -c "${2:-.}"
}
ship() {  # $1 id, $2 phaseReached, $3 verifyExit, $4 newRed json
  jq -nc --arg id "$1" --arg phase "$2" --argjson exit "$3" --argjson newRed "$4" \
    '{branch:("agents/ship-"+$id), headCommit:("head-"+$id), briefPath:(".claude/briefs/"+$id+".md"),
      phaseReached:$phase, verifyExit:$exit, newRed:$newRed, stopReason:""}'
}
land() {  # $1 id, $2 verifyExit, $3 allRed json, $4 newRed json; $5 optional jq filter
  jq -nc --arg id "$1" --argjson exit "$2" --argjson allRed "$3" --argjson newRed "$4" \
    --argjson fleet "$FLEET" --argjson enabled "$ENABLED" \
    '{verifyExit:$exit, allRed:$allRed, newRed:$newRed, gateExit:0, gateVerdict:"met", gateEvidence:"",
      reviewConfirmed:[], reviewPlausible:[], landed:true, mainHead:("main-"+$id), originMainHead:("main-"+$id),
      archiveCommit:("arch-"+$id), fleetStart:$fleet, enabled:$enabled, failingAssertion:""}' \
    | jq -c "${5:-.}"
}
two_tasks() {  # $1 id, $2 ship, $3 land, $4 id, $5 ship, $6 land — a reply may be the literal null
  jq -nc --arg i1 "$1" --argjson s1 "$2" --argjson l1 "$3" --arg i2 "$4" --argjson s2 "$5" --argjson l2 "$6" \
    '{("ship:"+$i1):$s1, ("land:"+$i1):$l1, ("ship:"+$i2):$s2, ("land:"+$i2):$l2}'
}
run() {  # $1 name, $2 args json, $3 replies json -> $tmp/$1.out
  jq -nc --argjson args "$2" --argjson replies "$3" '{args:$args, replies:$replies}' > "$tmp/$1.json"
  node "$HARNESS" "$SCRIPT" "$tmp/$1.json" > "$tmp/$1.out" 2>&1 \
    || { echo "  harness failed for $1:"; sed 's/^/    /' "$tmp/$1.out"; }
}
field() { sed -n "s/^$1=//p" "$tmp/$2.out"; }          # $1 key, $2 scenario
result_key() { field result "$2" | jq -r "$1"; }        # $1 jq path, $2 scenario
stopped_with() { case "$1" in *"$2"*) return 0 ;; esac; return 1; }

red10=$(printf '%s\n' "$script_missing" | jq -R 'select(length > 0) | "PROBLEM\tcontract-exists\tdesign/contracts/" + . + ".md"' | jq -sc .)
red5=$(printf '%s\n' "$script_aliases" | jq -R 'select(length > 0) | "PROBLEM\tmodel-alias\t" + .' | jq -sc .)
red15=$(jq -nc --argjson a "$red10" --argjson b "$red5" '$a + $b')

G64s=$(ship T6.4 finish 0 '[]');  G64l=$(land T6.4 0 '[]' '[]')
G13s=$(ship T1.3 finish 0 '[]');  G13l=$(land T1.3 0 '[]' '[]')
R11s=$(ship T1.1 implement 1 "$red10");  R11l=$(land T1.1 1 "$red10" "$red10")
R12s=$(ship T1.2 implement 1 "$red5");   R12l=$(land T1.2 1 "$red15" "$red5")

# Happy path: two green tasks.
run happy "$(args '["T6.4","T1.3"]')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")"
happy_landed=$(result_key '.landed | length' happy)
happy_stopped=$(result_key '.stoppedAt // "none"' happy)
assert 'happy path: both tasks land and nothing stops' '[ "$happy_landed" = 2 ] && [ "$happy_stopped" = none ]'
assert 'happy path: ship, land, ship, land — one task at a time' \
  '[ "$(field calls happy)" = "ship:T6.4,land:T6.4,ship:T1.3,land:T1.3" ]'
assert 'ship agents run in a worktree with a schema; land agents in the main checkout' \
  '[ "$(field call:ship:T6.4 happy)" = "{\"phase\":\"Ship\",\"isolation\":\"worktree\",\"schema\":true}" ] &&
   [ "$(field call:land:T6.4 happy)" = "{\"phase\":\"Land\",\"isolation\":null,\"schema\":true}" ]'
assert 'a landed task records the main head the land agent measured, not the ship agent'"'"'s head' \
  '[ "$(result_key ".landed[1].commit" happy)" = main-T1.3 ]'
meta_name=$(field meta happy | jq -r .name)
assert 'meta.name is ship-dev-plan, the name Workflow resolves under .claude/workflows/' '[ "$meta_name" = ship-dev-plan ]'
meta_phases=$(field meta happy | jq -r '.phases[].title' | sort -u | tr '\n' ' ')
used_phases=$(field phases happy | tr ',' '\n' | sort -u | tr '\n' ' ')
assert "meta.phases titles (${meta_phases}) equal the phase() titles the body uses (${used_phases})" \
  '[ -n "$meta_phases" ] && [ "$meta_phases" = "$used_phases" ]'
assert 'a green task'"'"'s ship prompt runs /ship whole' "grep '^prompt:ship:T6.4=' $tmp/happy.out | grep -q 'Run /ship'"
assert 'a no-deploy task'"'"'s land prompt says so' "grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'No deploy for this task'"
assert 'both prompts carry the rails' \
  "grep '^prompt:ship:T6.4=' $tmp/happy.out | grep -q 'never run bin/deploy --prune' && grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'never run bin/deploy --prune'"

# Ships-red path: T1.1 then T1.2, each landing on verify exit 1 with exactly its named red.
run red "$(args '["T1.1","T1.2"]')" "$(two_tasks T1.1 "$R11s" "$R11l" T1.2 "$R12s" "$R12l")"
assert 'ships-red: T1.1 and T1.2 land on verify exit 1 with exactly their named red lines' \
  '[ "$(result_key ".landed | length" red)" = 2 ]'
assert 'ships-red: a landed red set becomes the baseline — finalRed carries all 15 lines' \
  '[ "$(result_key ".finalRed | length" red)" = 15 ]'
assert 'ships-red: T1.2'"'"'s ship prompt is handed T1.1'"'"'s red lines as its baseline' \
  "grep '^prompt:ship:T1.2=' $tmp/red.out | grep -q 'design/contracts/augustus-content.md'"
assert 'ships-red: the ship prompt forbids /finish' "grep '^prompt:ship:T1.1=' $tmp/red.out | grep -q 'Do NOT run /finish'"

# Deploying task: the prompts carry the runtime-action contract.
run deploy "$(args '["T6.1"]')" "$(jq -nc --argjson s "$(ship T6.1 finish 0 '[]')" --argjson l "$(land T6.1 0 '[]' '[]')" '{"ship:T6.1":$s, "land:T6.1":$l}')"
assert 'T6.1: the ship prompt demands a "## Runtime actions" section and forbids running it' \
  "grep '^prompt:ship:T6.1=' $tmp/deploy.out | grep -q '## Runtime actions'"
assert 'T6.1: the land prompt runs bin/deploy from main and reads the journal' \
  "grep '^prompt:land:T6.1=' $tmp/deploy.out | grep -q 'bin/deploy (from main)'"

# Every stop rule, each with a second task queued that must never ship.
expect_stop() {  # $1 name, $2 tasks json, $3 replies json, $4 failingAssertion fragment, $5 expected calls
  local want=$4 wantcalls=$5 fa calls
  run "$1" "$2" "$3"
  fa=$(result_key '.failingAssertion // ""' "$1")
  calls=$(field calls "$1")
  assert "stop [$1]: names '$want' and runs no later agent (calls: ${calls:-none})" \
    'stopped_with "$fa" "$want" && [ "$calls" = "$wantcalls" ]'
}
T2='["T6.4","T1.3"]'
expect_stop phase-short "$(args "$T2")" "$(two_tasks T6.4 "$(ship T6.4 implement 0 '[]')" "$G64l" T1.3 "$G13s" "$G13l")" \
  'ship reached implement, wanted finish' 'ship:T6.4'
expect_stop null-ship "$(args "$T2")" "$(two_tasks T6.4 null "$G64l" T1.3 "$G13s" "$G13l")" \
  'ship agent returned null' 'ship:T6.4'
expect_stop null-land "$(args "$T2")" "$(two_tasks T6.4 "$G64s" null T1.3 "$G13s" "$G13l")" \
  'land agent returned null' 'ship:T6.4,land:T6.4'
expect_stop red-extra "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '["FAIL: x"]' '["FAIL: x"]')" T1.3 "$G13s" "$G13l")" \
  'red set mismatch: extra=' 'ship:T6.4,land:T6.4'
nine=$(jq -c '.[1:]' <<< "$red10")
expect_stop red-missing "$(args '["T1.1","T1.2"]')" "$(two_tasks T1.1 "$R11s" "$(land T1.1 1 "$nine" "$nine")" T1.2 "$R12s" "$R12l")" \
  'missing=' 'ship:T1.1,land:T1.1'
expect_stop green-exit-1 "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 1 '[]' '[]')" T1.3 "$G13s" "$G13l")" \
  'verify.sh exit 1' 'ship:T6.4,land:T6.4'
expect_stop red-exit-0 "$(args '["T1.1","T1.2"]')" "$(two_tasks T1.1 "$R11s" "$(land T1.1 0 "$red10" "$red10")" T1.2 "$R12s" "$R12l")" \
  'verify.sh exit 0' 'ship:T1.1,land:T1.1'
expect_stop gate-not-met "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.gateVerdict = "not met"')" T1.3 "$G13s" "$G13l")" \
  'plan gate: exit 0, verdict not met' 'ship:T6.4,land:T6.4'
expect_stop gate-exit "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.gateExit = 1')" T1.3 "$G13s" "$G13l")" \
  'plan gate: exit 1' 'ship:T6.4,land:T6.4'
expect_stop review "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.reviewConfirmed = ["design/x.md:3: live cell"]')" T1.3 "$G13s" "$G13l")" \
  'code review confirmed: design/x.md:3' 'ship:T6.4,land:T6.4'
expect_stop not-landed "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.originMainHead = "stale"')" T1.3 "$G13s" "$G13l")" \
  'not landed:' 'ship:T6.4,land:T6.4'
expect_stop fleet-restart "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.fleetStart.augustus = "a1"')" T1.3 "$G13s" "$G13l")" \
  'fleet restart detected: augustus' 'ship:T6.4,land:T6.4'
expect_stop enabled "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.enabled.user = 15')" T1.3 "$G13s" "$G13l")" \
  'enabled-unit count changed' 'ship:T6.4,land:T6.4'
expect_stop unknown-task "$(args '["T9.9","T6.4"]')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'unknown task id' ''
expect_stop no-tasks "$(args "$T2" 'del(.tasks)')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'args.tasks' ''
expect_stop no-today "$(args "$T2" 'del(.today)')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'args.today' ''

exit $fail
