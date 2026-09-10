export const meta = {
  name: 'ship-dev-plan',
  description: 'Serially /ship ready dev-plan tasks: worktree ship, independent verify + review, fast-forward to main; stop on first red',
  whenToUse: 'Launching one or more ready tasks from docs/dev-plan-2026-09.md unattended, per .claude/briefs/archive/2026-09-08-workflow-ship-feasibility.md',
  phases: [
    { title: 'Ship', detail: 'plan -> implement -> finish in an isolated worktree, one task at a time' },
    { title: 'Land', detail: 'fresh agent: verify.sh set-diff, plan gate, /code-review, ff-merge, push, archive brief' },
  ],
}

// args, measured inline by the launching session because a script cannot read the box:
//   { today: 'YYYY-MM-DD', tasks: ['T6.4', ...], baselineRed: [...],
//     fleetStart: { marcus: '<ExecMainStartTimestamp>', ... }, enabled: { system: N, user: N },
//     preShipped: { 'T6.4': <a SHIP object from an earlier run> } }
//
// preShipped exists because the expensive half is not the half that fails. A ship can finish,
// push its branch and be verified, and the run still die in the land step — T6.2 lost a land
// agent to the session limit mid-review with the branch already pushed. Re-running the task
// then re-ships work that is already on a branch. An id listed here skips the ship agent and
// hands the recorded object to the land step unchanged; every gate after it is unchanged, so a
// pre-shipped task is landed by the same independent verifier as any other. The object is the
// launching session's evidence, not the script's: it is checked for the branch the land prompt
// is built from and for the phase the task requires, and a run stops rather than sending an
// agent to rebase `undefined`.
const REPO = '/home/dave/dev/agent-workforce'
const PLAN = 'docs/dev-plan-2026-09.md'

const MISSING_CONTRACTS = ['augustus-content', 'bd-followup-drafts', 'bd-stall-radar', 'm1-signal-scan', 'raw-ingest', 'standing-research']
const ALIAS_WORKFLOWS = ['praetorium-daily-plan', 'praetorium-eod-summary', 'overnight-morning-report', 'weekly-pre-assembly', 'm1-signal-scan']
const WORKFLOW_ENTRIES = 33

const TASKS = {
  'T6.4': { size: 'S', review: 'medium', deploy: false, shipsRed: false, expectedRed: [],
    gateCmd: "head -30 design/workflow-registry.md | grep -qiE 'frozen|d1 record' && head -30 design/workflow-registry.md | grep -q 'design/agents/'",
    gateWords: 'header present pointing at the manifests; no live claim left in the file' },
  'T1.3': { size: 'S', review: 'medium', deploy: false, shipsRed: false, expectedRed: [],
    gateCmd: "grep -q 'strict-mcp-config' design/agent-model.md",
    gateWords: 'no line credits --allowedTools as enforcement; S2 containment is --strict-mcp-config plus the agent_propose.sh write boundary; judge every grep hit for --allowedTools' },
  'T1.4': { size: 'S', review: 'medium', deploy: false, shipsRed: false, expectedRed: [],
    gateCmd: "bash tests/test_contract_schema.sh > /tmp/t14.out 2>&1; rc=$?; grep -q 'ok:' /tmp/t14.out && [ $rc = 0 ]",
    gateWords: 'green on the two existing contracts; a fixture missing one of the eight sections is reported red by name; owner equals the declaring manifest; one contract per unit' },
  'T6.2': { size: 'M', review: 'medium', deploy: false, shipsRed: false, expectedRed: [],
    gateCmd: "grep -A3 'surfaces.scheduled' design/agents/augustus.toml | grep -qE 'present *= *false|reason' && [ $(grep -c '^\\[\\[runtime_only\\]\\]' design/deploy-exclusions.toml) = 11 ]",
    gateWords: "grep -rn 'content-strategy\\|faceless-content' design/ profiles/ bin/ config/ returns only historical notes; registry rows 77-78 and eval-spec 166-167 read as history; W19 row updated" },
  'T1.1': { size: 'S', review: 'high', deploy: false, shipsRed: true, expectedRed: MISSING_CONTRACTS,
    gateCmd: `python3 tests/test_workflow_coverage.py > /tmp/t11.out 2>&1; [ $(grep -c '^PROBLEM.*design/contracts/' /tmp/t11.out) = ${MISSING_CONTRACTS.length} ] && grep -qE '${WORKFLOW_ENTRIES}' /tmp/t11.out`,
    gateWords: `the red list equals the ${MISSING_CONTRACTS.length} in the baseline; the rule reports ${WORKFLOW_ENTRIES} entries checked and fails below the manifest count` },
  'T1.2': { size: 'M', review: 'high', deploy: false, shipsRed: true, expectedRed: ALIAS_WORKFLOWS,
    gateCmd: `python3 tests/test_workflow_coverage.py > /tmp/t12.out 2>&1; [ $(grep -ciE '^PROBLEM.*(model|alias|sonnet)' /tmp/t12.out) = ${ALIAS_WORKFLOWS.length} ]`,
    gateWords: `the red list equals the ${ALIAS_WORKFLOWS.length} alias workflows; tools, tools_web, mcp and model are joined against --allowedTools, --strict-mcp-config, --model read out of the runner; claudius's per-workflow web split is honoured` },
  'T6.1': { size: 'M', review: 'high', deploy: true, shipsRed: false, expectedRed: [],
    gateCmd: "diff -q systemd/memory-consolidation.service /etc/systemd/system/memory-consolidation.service && ! grep -rniE 'hermes' bin/ systemd/ profiles/ | grep -viE 'retired|historical|was |until 20|removed 20|migrat' | grep -q .",
    gateWords: 'grep for hermes across bin/ systemd/ profiles/ returns only historical notes; the changed unit ran once live and its journal output was read; base0 and leantest kept' },
}

const SHIP = { type: 'object', required: ['branch', 'headCommit', 'briefPath', 'phaseReached', 'verifyExit', 'newRed', 'stopReason'],
  properties: { branch: { type: 'string' }, headCommit: { type: 'string' }, briefPath: { type: 'string' },
    phaseReached: { type: 'string', enum: ['plan', 'implement', 'finish'] }, verifyExit: { type: 'integer' },
    newRed: { type: 'array', items: { type: 'string' } }, stopReason: { type: 'string' } } }

const LAND = { type: 'object',
  required: ['verifyExit', 'allRed', 'newRed', 'gateExit', 'gateVerdict', 'gateEvidence', 'reviewConfirmed', 'reviewPlausible',
             'landed', 'mainHead', 'originMainHead', 'archiveCommit', 'fleetStart', 'enabled', 'failingAssertion'],
  properties: { verifyExit: { type: 'integer' }, allRed: { type: 'array', items: { type: 'string' } },
    newRed: { type: 'array', items: { type: 'string' } }, gateExit: { type: 'integer' },
    gateVerdict: { type: 'string', enum: ['met', 'not met'] }, gateEvidence: { type: 'string' },
    reviewConfirmed: { type: 'array', items: { type: 'string' } }, reviewPlausible: { type: 'array', items: { type: 'string' } },
    landed: { type: 'boolean' }, mainHead: { type: 'string' }, originMainHead: { type: 'string' }, archiveCommit: { type: 'string' },
    fleetStart: { type: 'object' }, enabled: { type: 'object' }, failingAssertion: { type: 'string' } } }

const RAILS = `Rails, non-negotiable: never restart, stop, enable or disable any systemd unit (buzz-agent@* above all);
never run buzz agents / buzz-admin generate-key; never read ~/.ssh, ~/.config/agent-workforce, ~/.config/buzz-agents,
~/.confidential.img, ~/ENCRYPTION_RECOVERY.md; never pass --no-verify; never run bin/deploy --prune; never git add -A;
never edit bin/verify.sh, bin/check_deploy_drift.sh or any existing test to make something green.
Always run bash bin/verify.sh with output redirected to a file, then read it with grep/tail; it is 200 KB.`

function shipPrompt(id, t, baseline) {
  const gateLine = t.shipsRed
    ? `This task SHIPS RED by design. Green for this task means: bin/verify.sh's red lines (matching ^\\s*FAIL:|^PROBLEM\\t|^\\s*DRIFT ) equal the baseline below plus exactly one new line per item in ${JSON.stringify(t.expectedRed)}, and nothing else. Run /plan-feature then /implement with that as the acceptance. Do NOT run /finish. When the gate matches, commit on your branch by explicit path with a Conventional Commit whose body lists every new red line verbatim (precedent: commit 9f7e977), then git push origin HEAD.`
    : `Run /ship. Green means bin/verify.sh exits 0 and its red lines equal the baseline below exactly. /finish commits by explicit path and pushes your branch.`
  return `You are in an isolated worktree of ${REPO} on your own branch. Task ${id} of ${PLAN} (read that task's bullet and § Definition of done). Write the brief to .claude/briefs/${id.toLowerCase().replace('.', '-')}-<slug>.md and commit that named brief with the code.
.claude/briefs/current.md is tracked and belongs to a live brief (T0.3): do not archive, move, overwrite or stage it, and never use git mv anywhere. Where /plan-feature says to archive or write current.md, skip that step. Do not touch .claude/briefs/archive/.
${gateLine}
retries: 2 for the refine loop; escalate = stop and report. Do not run bin/deploy (the land step deploys from main).
${t.deploy ? 'Your brief MUST carry a section "## Runtime actions" listing the exact commands the land step runs after merge: bin/deploy, targeted rm of runtime files this task deletes, sudo cp of the unit, daemon-reload, the one live run, the journal read. Do not run any of them yourself. Do not delete anything under ~/.hermes; D4 decides that and it is out of this task.' : ''}
Baseline red lines on main: ${JSON.stringify(baseline)}
${RAILS}
Return: branch (git rev-parse --abbrev-ref HEAD), headCommit, briefPath, phaseReached (plan|implement|finish), verifyExit of your last gate run, newRed (red lines not in the baseline), stopReason ('' if you completed).`
}

function landPrompt(id, t, ship, baseline, today) {
  return `You are the independent verifier and landing agent for task ${id} (${PLAN}). You did not write this code. Work in ${REPO} (the main checkout), which must be on main and clean; stop if not.
1. git fetch origin. Rebase branch ${ship.branch} onto main in a temporary worktree under .claude/worktrees/land-${id} (a conflict = stop, failingAssertion='rebase conflict'). If git diff --name-only main..${ship.branch} names .claude/briefs/current.md or any archive/ file containing buzz-task-scheduling, stop (failingAssertion='touched the live current.md'). Then in the main checkout: git merge --ff-only ${ship.branch}.
${t.deploy ? `2. Read the merged brief's "## Runtime actions" section and run exactly those commands, nothing more: bin/deploy (from main), the targeted rm lines, sudo cp systemd/memory-consolidation.service /etc/systemd/system/ && sudo systemctl daemon-reload, sudo systemctl start memory-consolidation.service, journalctl -u memory-consolidation -n 40 --no-pager. Put the journal text in gateEvidence.` : '2. No deploy for this task. If bin/verify.sh reports DRIFT on a file this task changed, that is a red, not something to deploy away.'}
3. bash bin/verify.sh > /tmp/land-${id}.out 2>&1; verifyExit=$?. allRed = lines matching ^\\s*FAIL:|^PROBLEM\\t|^\\s*DRIFT . newRed = allRed minus this baseline: ${JSON.stringify(baseline)}. Expected new red for this task: ${JSON.stringify(t.expectedRed)} (one line per item, matched by substring, nothing else).
4. Plan gate. Run: ${t.gateCmd}  -> gateExit. Then judge these words against the tree and put the commands and lines you used in gateEvidence: "${t.gateWords}". gateVerdict = met | not met.
5. The code review is a gate, not a note. Independent read, calibration-pinned. Read ~/.config/buzz-team/aurelian-calibration.md § "Code / config" and § "Binding"; compute diff_digest = git diff --binary origin/main..main | sha256sum and calibration_digest = sha256sum of that file; apply the rubric's five bullets to the diff. Then invoke the code-review skill at effort ${t.review} on git diff origin/main..main. reviewConfirmed = CONFIRMED findings (file:line: summary); reviewPlausible = the rest.
Do not return until the review has produced findings. If the code-review skill cannot be invoked, or returns no result, reset as in step 6, set landed=false and failingAssertion='code review did not complete', and return: an empty reviewConfirmed means the review ran and confirmed nothing, and it must never also mean the review never ran. Both read identically to the caller, and the second one lands the diff.
6. If verifyExit/newRed/gateExit/gateVerdict/reviewConfirmed do not all pass: git reset --keep origin/main${t.deploy ? ' && bin/deploy (restore runtime bin/ from origin/main; the /etc unit stays as installed, say so)' : ''}; landed=false; fill failingAssertion; return.
7. Otherwise: git push origin main. git mv the brief to .claude/briefs/archive/${today}-<slug>.md and commit "docs(briefs): archive ${id} — <slug>" with a body carrying verifyExit, every newRed line verbatim, the gate command and result, the diff_digest and calibration_digest, and the plausible findings. git push origin main. git push origin --delete ${ship.branch}. Remove the temporary worktree.
8. Return fleetStart = ExecMainStartTimestamp of buzz-agent@{marcus,claudius,augustus,trajan,aurelian} (systemctl --user show -p ExecMainStartTimestamp --value) and enabled = {system: systemctl list-unit-files --state=enabled --no-legend | wc -l, user: same with --user}.
${RAILS}
Never take the ship agent's word for anything; every returned value comes from a command you ran. mainHead = git rev-parse main, originMainHead = git rev-parse origin/main after a final git fetch.`
}

function stop(at, failingAssertion, landed, extra) {
  log(`STOP at ${at}: ${failingAssertion}`)
  return { stoppedAt: at, failingAssertion, landed, ...extra }
}

const landed = []
if (!Array.isArray(args?.tasks) || !args.tasks.length) return stop('args', 'args.tasks must be a non-empty array of task ids', landed)
if (typeof args.today !== 'string' || !args.today) return stop('args', 'args.today must be the launch date as YYYY-MM-DD', landed)

let baseline = args.baselineRed || []
for (const id of args.tasks) {
  const t = TASKS[id]
  if (!t) return stop(id, 'unknown task id', landed)
  const pre = args.preShipped && args.preShipped[id]
  let ship
  if (pre) {
    if (typeof pre.branch !== 'string' || !pre.branch)
      return stop(id, `args.preShipped entry for ${id} carries no branch to land`, landed, { ship: pre })
    ship = pre
    log(`${id}: landing the recorded ship of ${pre.branch}; no ship agent`)
  } else {
    phase('Ship')
    ship = await agent(shipPrompt(id, t, baseline), { label: `ship:${id}`, phase: 'Ship', schema: SHIP, isolation: 'worktree' })
    if (!ship) return stop(id, 'ship agent returned null (skipped or terminal API error)', landed)
  }
  const wantPhase = t.shipsRed ? 'implement' : 'finish'
  if (ship.phaseReached !== wantPhase) return stop(id, `ship reached ${ship.phaseReached}, wanted ${wantPhase}: ${ship.stopReason}`, landed, { ship })

  phase('Land')
  const land = await agent(landPrompt(id, t, ship, baseline, args.today), { label: `land:${id}`, phase: 'Land', schema: LAND })
  if (!land) return stop(id, 'land agent returned null', landed, { ship })
  const extra = land.newRed.filter(l => !t.expectedRed.some(s => l.includes(s)))
  const missing = t.expectedRed.filter(s => !land.newRed.some(l => l.includes(s)))
  if (extra.length || missing.length || land.newRed.length !== t.expectedRed.length)
    return stop(id, `red set mismatch: extra=${JSON.stringify(extra)} missing=${JSON.stringify(missing)}`, landed, { ship, land })
  if (t.shipsRed ? land.verifyExit === 0 : land.verifyExit !== 0)
    return stop(id, `verify.sh exit ${land.verifyExit}`, landed, { ship, land })
  if (land.gateExit !== 0 || land.gateVerdict !== 'met')
    return stop(id, `plan gate: exit ${land.gateExit}, verdict ${land.gateVerdict}`, landed, { ship, land })
  if (land.reviewConfirmed.length)
    return stop(id, `code review confirmed: ${land.reviewConfirmed.join(' | ')}`, landed, { ship, land })
  if (!land.landed || land.mainHead !== land.originMainHead)
    return stop(id, `not landed: main ${land.mainHead} origin/main ${land.originMainHead} (${land.failingAssertion})`, landed, { ship, land })
  const restarted = Object.keys(args.fleetStart || {}).filter(a => land.fleetStart[a] !== args.fleetStart[a])
  if (restarted.length) return stop(id, `fleet restart detected: ${restarted.join(',')}`, landed, { land })
  if (args.enabled && (land.enabled.system !== args.enabled.system || land.enabled.user !== args.enabled.user))
    return stop(id, `enabled-unit count changed: ${JSON.stringify(land.enabled)}`, landed, { land })

  baseline = land.allRed
  landed.push({ id, commit: land.mainHead, archive: land.archiveCommit, plausible: land.reviewPlausible })
  log(`${id} landed at ${land.mainHead}; red set now ${baseline.length} line(s)`)
}
return { landed, finalRed: baseline }
