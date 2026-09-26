#!/usr/bin/env bash
# .claude/workflows/ship-dev-plan.js is the saved Workflow script that brief
# .claude/briefs/archive/2026-09-08-workflow-ship-feasibility.md §11 designed: it /ships dev-plan tasks one at a
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
#
# A land is two runs since main was protected (T8.2): run 1 ends `awaitingApproval` with a PR
# the App opened, run 2 names it in `approvedPR` and a merge agent lands it. Both halves and
# every refusal of the second are scenarios here.
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
# Two assertions, not one: `$script_missing` is empty both when the constant is absent and
# when it reads `MISSING_CONTRACTS = []`, and the second is the healthy end state (T4.2,
# 2026-09-10 — every contract the manifests name now exists). Folding the declaration check
# into the equality check turned an empty red list into a FAIL. `wc -l` had the mirror-image
# defect in the description, reporting 1 for no reds at all.
assert 'the script declares MISSING_CONTRACTS' \
  "grep -q '^const MISSING_CONTRACTS = \[' $SCRIPT"
assert "T1.1's expected red equals the contracts the manifests name and design/contracts/ lacks ($(printf '%s\n' "$live_missing" | grep -c . || true))" \
  '[ "$script_missing" = "$live_missing" ]'

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
      reviewConfirmed:[], reviewPlausible:[], landed:false, mainHead:"main-0", originMainHead:"main-0",
      archiveCommit:("arch-"+$id), fleetStart:$fleet, enabled:$enabled, failingAssertion:"",
      awaiting:true, pr:71, headSha:("sha-"+$id)}' \
    | jq -c "${5:-.}"
}
merge() {  # $1 id, $2 verifyExit, $3 allRed json, $4 newRed json; $5 optional jq filter
  jq -nc --arg id "$1" --argjson exit "$2" --argjson allRed "$3" --argjson newRed "$4" \
    --argjson fleet "$FLEET" --argjson enabled "$ENABLED" \
    '{reviewDecision:"APPROVED", gateConclusion:"SUCCESS", prHeadSha:("sha-"+$id), merged:true,
      mergedBy:"praetorium-vault-writer[bot]", verifyExit:$exit, allRed:$allRed, newRed:$newRed,
      mainHead:("main-"+$id), originMainHead:("main-"+$id), fleetStart:$fleet, enabled:$enabled, failingAssertion:""}' \
    | jq -c "${5:-.}"
}
approved() {  # $1.. task ids -> the approvedPR object run 2 is launched with
  local id out='{}'
  for id in "$@"; do out=$(jq -c --arg id "$id" '.[$id] = {pr:71, headSha:("sha-"+$id)}' <<< "$out"); done
  echo "$out"
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

# Both red sets are derived from the script's own constants and never counted here. T1.1's
# shrinks by one on every contract that lands and reaches zero at T4.3, so a count baked into a
# variable name or an assertion goes stale silently — which is what `red15` did when T4.1 landed.
red_contracts=$(printf '%s\n' "$script_missing" | jq -R 'select(length > 0) | "PROBLEM\tcontract-exists\tdesign/contracts/" + . + ".md"' | jq -sc .)
red_aliases=$(printf '%s\n' "$script_aliases" | jq -R 'select(length > 0) | "PROBLEM\tmodel-alias\t" + .' | jq -sc .)
red_both=$(jq -nc --argjson a "$red_aliases" --argjson b "$red_contracts" '$a + $b')
red_both_n=$(jq -r 'length' <<< "$red_both")
red_aliases_short=$(jq -c '.[1:]' <<< "$red_aliases")

G64s=$(ship T6.4 finish 0 '[]');  G64l=$(land T6.4 0 '[]' '[]')
G13s=$(ship T1.3 finish 0 '[]');  G13l=$(land T1.3 0 '[]' '[]')
# T1.2 ships first so the baseline that propagates into the second task is ALIAS_WORKFLOWS, the
# one red set no task in the plan shrinks.
R12s=$(ship T1.2 implement 1 "$red_aliases");   R12l=$(land T1.2 1 "$red_aliases" "$red_aliases")
R11s=$(ship T1.1 implement 1 "$red_contracts"); R11l=$(land T1.1 1 "$red_both" "$red_contracts")

# Happy path, run 1: the first green task opens its PR and the run returns cleanly to wait for
# Dave. The second task is not shipped: it would be built on a main the first has not reached.
run happy "$(args '["T6.4","T1.3"]')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")"
assert 'run 1: nothing stops and nothing lands; the task awaits approval of the PR it opened' \
  '[ "$(result_key ".stoppedAt // \"none\"" happy)" = none ] && [ "$(result_key ".landed | length" happy)" = 0 ] &&
   [ "$(result_key ".awaitingApproval[0].pr" happy)" = 71 ] && [ "$(result_key ".awaitingApproval[0].headSha" happy)" = sha-T6.4 ]'
assert 'run 1: ship, land — and no second task until the first is merged' \
  '[ "$(field calls happy)" = "ship:T6.4,land:T6.4" ]'
assert 'ship agents run in a worktree with a schema; land agents with a schema, isolation their own' \
  '[ "$(field call:ship:T6.4 happy)" = "{\"phase\":\"Ship\",\"isolation\":\"worktree\",\"schema\":true}" ] &&
   [ "$(field call:land:T6.4 happy)" = "{\"phase\":\"Land\",\"isolation\":null,\"schema\":true}" ]'
assert 'the land prompt opens the PR as the App and never pushes or merges main' \
  "grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'bin/gh_app.sh pr create' &&
   ! grep '^prompt:land:T6.4=' $tmp/happy.out | grep -qE -- '--ff-only|git push origin main'"
assert 'the land prompt forbids approving or merging its own PR' \
  "grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'Never approve the PR, and never merge it'"

# Happy path, run 2: both approved; each is merged by its own agent, no ship and no land agent.
run merged "$(args '["T6.4","T1.3"]' ".approvedPR = $(approved T6.4 T1.3)")" \
  "$(jq -nc --argjson a "$(merge T6.4 0 '[]' '[]')" --argjson b "$(merge T1.3 0 '[]' '[]')" '{"land-merge:T6.4":$a, "land-merge:T1.3":$b}')"
assert 'run 2: both approved tasks merge, one agent each, and nothing is re-shipped' \
  '[ "$(field calls merged)" = "land-merge:T6.4,land-merge:T1.3" ] && [ "$(result_key ".landed | length" merged)" = 2 ]'
assert 'a landed task records the main head the merge agent measured, and who merged it' \
  '[ "$(result_key ".landed[1].commit" merged)" = main-T1.3 ] && [ "$(result_key ".landed[1].mergedBy" merged)" = "praetorium-vault-writer[bot]" ]'
assert 'the merge prompt checks the approval, the gate check and the approved head before merging' \
  "grep '^prompt:land-merge:T6.4=' $tmp/merged.out | grep -q 'reviewDecision is not APPROVED' &&
   grep '^prompt:land-merge:T6.4=' $tmp/merged.out | grep -q 'prHeadSha is not sha-T6.4' &&
   grep '^prompt:land-merge:T6.4=' $tmp/merged.out | grep -q 'bin/gh_app.sh pr merge 71'"
meta_name=$(field meta happy | jq -r .name)
assert 'meta.name is ship-dev-plan, the name Workflow resolves under .claude/workflows/' '[ "$meta_name" = ship-dev-plan ]'
meta_phases=$(field meta happy | jq -r '.phases[].title' | sort -u | tr '\n' ' ')
used_phases=$(field phases happy | tr ',' '\n' | sort -u | tr '\n' ' ')
assert "meta.phases titles (${meta_phases}) equal the phase() titles the body uses (${used_phases})" \
  '[ -n "$meta_phases" ] && [ "$meta_phases" = "$used_phases" ]'
assert 'a green task'"'"'s ship prompt runs /ship whole' "grep '^prompt:ship:T6.4=' $tmp/happy.out | grep -q 'Run /ship'"
assert 'a no-deploy task'"'"'s land prompt says so' "grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'No deploy for this task'"
assert 'the land prompt refuses to return on a review that did not run' \
  "grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'code review did not complete'"
assert 'both prompts carry the rails' \
  "grep '^prompt:ship:T6.4=' $tmp/happy.out | grep -q 'never run bin/deploy --prune' && grep '^prompt:land:T6.4=' $tmp/happy.out | grep -q 'never run bin/deploy --prune'"

# Ships-red path: T1.2 opens its PR on verify exit 1 with exactly its named red; once approved,
# T1.2 merges and its red set is the baseline T1.1 ships against in the same run.
run red "$(args '["T1.2","T1.1"]')" "$(two_tasks T1.2 "$R12s" "$R12l" T1.1 "$R11s" "$R11l")"
assert 'ships-red: T1.2 opens its PR on verify exit 1 with exactly its named red lines' \
  '[ "$(result_key ".awaitingApproval[0].id" red)" = T1.2 ]'
assert 'ships-red: the ship prompt forbids /finish' "grep '^prompt:ship:T1.2=' $tmp/red.out | grep -q 'Do NOT run /finish'"
M12=$(merge T1.2 1 "$red_aliases" "$red_aliases")
run redmerged "$(args '["T1.2","T1.1"]' ".approvedPR = $(approved T1.2)")" \
  "$(jq -nc --argjson m "$M12" --argjson s "$R11s" --argjson l "$R11l" '{"land-merge:T1.2":$m, "ship:T1.1":$s, "land:T1.1":$l}')"
assert 'ships-red: T1.2 merges, then T1.1 ships and opens its PR in the same run' \
  '[ "$(field calls redmerged)" = "land-merge:T1.2,ship:T1.1,land:T1.1" ] && [ "$(result_key ".awaitingApproval[0].id" redmerged)" = T1.1 ]'
assert "ships-red: a merged red set becomes the baseline — finalRed carries T1.2's lines" \
  '[ "$(result_key ".finalRed | length" redmerged)" = "$(jq -r length <<< "$red_aliases")" ]'
assert 'ships-red: T1.1'"'"'s ship prompt is handed T1.2'"'"'s red lines as its baseline' \
  "grep '^prompt:ship:T1.1=' $tmp/redmerged.out | grep -q 'model-alias'"

# Deploying task: nothing deploys before the merge; the merge agent runs the runtime actions.
run deploy "$(args '["T6.1"]')" "$(jq -nc --argjson s "$(ship T6.1 finish 0 '[]')" --argjson l "$(land T6.1 0 '[]' '[]')" '{"ship:T6.1":$s, "land:T6.1":$l}')"
assert 'T6.1: the ship prompt demands a "## Runtime actions" section and forbids running it' \
  "grep '^prompt:ship:T6.1=' $tmp/deploy.out | grep -q '## Runtime actions'"
assert 'T6.1: run 1 deploys nothing and expects DRIFT only on the paths the task changed' \
  "grep '^prompt:land:T6.1=' $tmp/deploy.out | grep -q 'No deploy yet' &&
   grep '^prompt:land:T6.1=' $tmp/deploy.out | grep -q 'DRIFT line naming a path in git diff --name-only origin/main..HEAD is expected'"
run deploymerged "$(args '["T6.1"]' ".approvedPR = $(approved T6.1)")" "$(jq -nc --argjson m "$(merge T6.1 0 '[]' '[]')" '{"land-merge:T6.1":$m}')"
assert 'T6.1: run 2 runs the merged brief'"'"'s Runtime actions after the merge' \
  "grep '^prompt:land-merge:T6.1=' $tmp/deploymerged.out | grep -q '## Runtime actions'"

# preShipped: a task whose ship already happened (a land agent that died mid-review is the
# case this exists for) is landed from the recorded result, with no ship agent spawned.
PRE=$(jq -nc --argjson s "$G64s" '{"T6.4": $s}')
run preshipped "$(args '["T6.4"]' ".preShipped = $PRE")" "$(jq -nc --argjson l "$G64l" '{"land:T6.4":$l}')"
assert 'preShipped: the land agent runs and no ship agent is spawned' \
  '[ "$(field calls preshipped)" = "land:T6.4" ]'
assert 'preShipped: the task still reaches its PR, from the recorded ship' \
  '[ "$(result_key ".awaitingApproval[0].headSha" preshipped)" = sha-T6.4 ]'
assert 'preShipped: the recorded branch is what the land prompt is told to rebase' \
  "grep '^prompt:land:T6.4=' $tmp/preshipped.out | grep -q 'agents/ship-T6.4'"
assert 'preShipped: the reuse is logged, not silent' '[ "$(field logs preshipped)" -ge 2 ]'

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
expect_stop red-missing "$(args '["T1.2","T1.1"]')" "$(two_tasks T1.2 "$R12s" "$(land T1.2 1 "$red_aliases_short" "$red_aliases_short")" T1.1 "$R11s" "$R11l")" \
  'missing=' 'ship:T1.2,land:T1.2'
expect_stop green-exit-1 "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 1 '[]' '[]')" T1.3 "$G13s" "$G13l")" \
  'verify.sh exit 1' 'ship:T6.4,land:T6.4'
expect_stop red-exit-0 "$(args '["T1.2","T1.1"]')" "$(two_tasks T1.2 "$R12s" "$(land T1.2 0 "$red_aliases" "$red_aliases")" T1.1 "$R11s" "$R11l")" \
  'verify.sh exit 0' 'ship:T1.2,land:T1.2'
expect_stop gate-not-met "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.gateVerdict = "not met"')" T1.3 "$G13s" "$G13l")" \
  'plan gate: exit 0, verdict not met' 'ship:T6.4,land:T6.4'
expect_stop gate-exit "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.gateExit = 1')" T1.3 "$G13s" "$G13l")" \
  'plan gate: exit 1' 'ship:T6.4,land:T6.4'
expect_stop review "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.reviewConfirmed = ["design/x.md:3: live cell"]')" T1.3 "$G13s" "$G13l")" \
  'code review confirmed: design/x.md:3' 'ship:T6.4,land:T6.4'
expect_stop no-pr "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.awaiting = false | .failingAssertion = "push refused"')" T1.3 "$G13s" "$G13l")" \
  'no PR opened: push refused' 'ship:T6.4,land:T6.4'
expect_stop fleet-restart "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.fleetStart.augustus = "a1"')" T1.3 "$G13s" "$G13l")" \
  'fleet restart detected: augustus' 'ship:T6.4,land:T6.4'
expect_stop enabled "$(args "$T2")" "$(two_tasks T6.4 "$G64s" "$(land T6.4 0 '[]' '[]' '.enabled.user = 15')" T1.3 "$G13s" "$G13l")" \
  'enabled-unit count changed' 'ship:T6.4,land:T6.4'
expect_stop pre-no-branch "$(args '["T6.4"]' '.preShipped = {"T6.4": {"phaseReached":"finish"}}')" \
  "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'args.preShipped entry for T6.4 carries no branch' ''
expect_stop pre-wrong-phase "$(args '["T6.4"]' '.preShipped = {"T6.4": {"branch":"agents/x","phaseReached":"implement"}}')" \
  "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'ship reached implement, wanted finish' ''
expect_stop unknown-task "$(args '["T9.9","T6.4"]')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'unknown task id' ''
expect_stop no-tasks "$(args "$T2" 'del(.tasks)')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'args.tasks' ''
expect_stop no-today "$(args "$T2" 'del(.today)')" "$(two_tasks T6.4 "$G64s" "$G64l" T1.3 "$G13s" "$G13l")" \
  'args.today' ''

# Every refusal of run 2, each with a second approved task that must never merge.
merge_stop() {  # $1 name, $2 jq filter on T6.4's merge reply, $3 failingAssertion fragment
  expect_stop "$1" "$(args "$T2" ".approvedPR = $(approved T6.4 T1.3)")" \
    "$(jq -nc --argjson a "$(merge T6.4 0 '[]' '[]' "$2")" --argjson b "$(merge T1.3 0 '[]' '[]')" '{"land-merge:T6.4":$a, "land-merge:T1.3":$b}')" \
    "$3" 'land-merge:T6.4'
}
merge_stop merge-unapproved '.reviewDecision = "REVIEW_REQUIRED"' 'PR #71 not approved: REVIEW_REQUIRED'
merge_stop merge-gate-failed '.gateConclusion = "FAILURE"' 'PR #71 gate check: FAILURE'
merge_stop merge-gate-absent '.gateConclusion = ""' 'PR #71 gate check: absent'
merge_stop merge-new-head '.prHeadSha = "sha-pushed-after-approval"' 'is not the approved sha-T6.4'
merge_stop merge-not-merged '.merged = false | .failingAssertion = "merge refused"' 'not merged:'
merge_stop merge-red '.newRed = ["FAIL: x"] | .allRed = ["FAIL: x"]' 'after merge: red set mismatch'
merge_stop merge-restart '.fleetStart.augustus = "a1"' 'after merge: fleet restart detected: augustus'
expect_stop merge-null "$(args "$T2" ".approvedPR = $(approved T6.4 T1.3)")" '{"land-merge:T6.4":null}' \
  'merge agent returned null' 'land-merge:T6.4'
expect_stop merge-bad-entry "$(args '["T6.4"]' '.approvedPR = {"T6.4": {"pr": "71"}}')" '{}' \
  'args.approvedPR entry for T6.4 needs an integer pr' ''

exit $fail
