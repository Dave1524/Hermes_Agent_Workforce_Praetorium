# Brief: can a Workflow script run /ship over the ready dev-plan tasks unattended?

**Date:** 2026-09-08   **Scope:** T1.1-T1.4, T6.1, T6.2, T6.4 of `docs/dev-plan-2026-09.md`. Phase 0 excluded.
**Verify:** `bash bin/verify.sh` (repo root). Nothing here touches `buzz-team/` or a `buzz-agent@*` unit.
**Status:** investigation. No workflow launched, no code changed, no unit touched. Everything marked
MEASURED was run on this box today; everything else cites a file and line.

> ## STATE — 2026-09-08: DONE. Archived.
>
> Implemented the same day by `/implement` + `/finish` (commit f58fe5d). The §11 script is
> now the saved workflow `.claude/workflows/ship-dev-plan.js`, which the Workflow tool
> resolves by name; §11 below is the design record and that file is the source. Deltas from
> §11: the two red lists and the entry count are named single-line constants;
> `args.tasks` and `args.today` are guarded before any agent runs; `meta.whenToUse` set.
> Its control flow is proven by `tests/test_ship_dev_plan_workflow.sh` through
> `tests/ship_dev_plan_harness.mjs` (scripted agents, nothing spawned): the task ids are
> plan bullets, T1.1's red list equals the live missing contracts, the 33 equals the live
> entry count, and all sixteen stop rules fire without shipping a later task. Mutation-checked
> three ways. `bash bin/verify.sh` exit 0, no red lines.
>
> **Not launched.** The §12 sentence now reads: `use a workflow: run ship-dev-plan for
> T6.4, T1.3, T1.4, T6.2, T1.1, T1.2, today <date>`; the launching session measures
> `baselineRed`, `fleetStart` and `enabled` inline. H0's `bin/deploy` had already run by
> the time this was implemented (drift clean on `main`); D4 and the §7 hook rail are still
> Dave's.

## Verdict

GO for six of the seven, serially, in two launches. Launch 1 ships T6.4, T1.3, T1.4, T6.2, T1.1, T1.2 and
never runs `bin/deploy`, never uses `sudo`, never touches the runtime tree. Launch 2 ships T6.1 alone, after
Dave answers D4 and reads launch 1. The gate is red on `main` right now for one reason (the plan document
is committed and not deployed); one `bin/deploy` clears it and must precede launch 1.

The one design question the plan leaves open is how T1.1 and T1.2 land red. Answer in §2: the land agent,
not `/finish`, is the commit authority for those two, and it lands only when the new red set equals the
plan's named list exactly. `bin/verify.sh` is not edited.

## Go / no-go

| Task | Size | Files (deployed tree?) | Deploy / sudo | Ships red | Verdict | Why |
|---|---|---|---|---|---|---|
| T6.4 | S | `design/workflow-registry.md` (no) | none | no | GO, first: pipeline canary | pure docs; proves ship -> land before anything expensive |
| T1.3 | S | `design/agent-model.md` (no) | none | no | GO | docs; gate is a per-line judgment the land agent makes |
| T1.4 | S | new `tests/test_contract_schema.*`, fixture (no) | none | no | GO | green on 2 contracts + one negative fixture; self-contained |
| T6.2 | M | `design/*`, `augustus.toml`, 2 `profiles/` deletions, `deploy-exclusions.toml` (profiles: yes, but deletion = additive deploy is a no-op) | none | no | GO, after T6.4 (shares `workflow-registry.md`) | deletions become `info: runtime-only` once declared; no `--prune` (reserved for T6.3) |
| T1.1 | S | `tests/test_workflow_coverage.py` (no) | none | yes, 10 | GO, second-to-last | after it lands, every later `/finish` is blocked; see §2 |
| T1.2 | M | `tests/test_workflow_coverage.py`, reads `bin/run_*_cc.sh` (no) | none | yes, 5 | GO, last | shares the file with T1.1; serial |
| T6.1 | M | `bin/agent_propose.sh`, `consolidate_memory.sh`, `praetorium-status.sh`, `systemd/memory-consolidation.service`, 4 env examples, 5 manifests, deletes 1 script + 1 doc, `~/.hermes/profiles/*` | `bin/deploy`, targeted `rm` in runtime, `sudo cp` + `daemon-reload`, one live run | no | GO, launch 2 only, behind D4 | out-of-repo deletion coupled to D4 (plan § Phase D); `agent_propose.sh` is exec'd by 9 nightly units and its live proof is the next night |

Rejected: two parallel lanes (Phase 1 / Phase 6). T1.1/T1.2 share a file, T6.2/T6.4 share a file, T1.3/T6.1
share a file, and two land steps racing on one `main` checkout is the failure I cannot make mechanical.
Serial costs wall-clock, not correctness.

## 1. Mechanics

- **A subagent can invoke `/ship`.** MEASURED: an `Agent` probe reports a `Skill` tool listing `ship`,
  `plan-feature`, `implement`, `finish`, `code-review`; `pwd` = `/home/dave/dev/agent-workforce`;
  `sudo -n true` exit 0 (`sudo -l`: `(ALL) NOPASSWD: ALL`); `Agent` and `ToolSearch` present, `Workflow`
  absent. Workflow agents resolve from the same registry (`workflow-authoring` § agentType), so the same
  surface is expected there. Not measured inside a Workflow run.
- **Permission mode.** `~/.claude/settings.json` `defaultMode: bypassPermissions`, `hooks: []`. Nothing
  prompts and nothing intercepts; every rail in §7 is prompt plus post-hoc assertion unless Dave adds a hook.
- **`bin/deploy` from a worktree deploys the worktree.** `bin/deploy:16` sets `SRC` from `$0`, so a worktree
  copy rsyncs the branch's tree into `~/agent-workforce` and its post-condition
  (`bin/deploy:102`, `check_deploy_drift.sh --scope bin`) compares that worktree against the runtime. Deploying
  an unmerged branch is the thing `CLAUDE.md` § Verification says not to do casually. Resolution: the ship
  agent never deploys; the land agent deploys from `main` after the fast-forward. Only T6.1 deploys at all.
- **Worktrees.** `isolation: 'worktree'` gives each ship agent its own checkout. The harness places them under
  `.claude/worktrees/`, which `.gitignore:13-17` lists for exactly that reason and `bin/auto-sync:50-73`
  refuses to stage as gitlinks. So the `main` checkout stays clean and the 15-minute sweep sees nothing.
- **Serial.** One task at a time. Concurrency cap here is `min(16, nproc-2)` = 6 (MEASURED `nproc` = 8), so
  parallel would be possible; the shared files above are why it is not done.
- **The `## Verification` block has no `retries` or `escalate` field** (`CLAUDE.md` § Verification is prose;
  the contract format at `~/.claude/verification-contract.md:12-23` expects fields). `/implement` step 4 says
  "up to `retries` times (the contract's value)" and there is none; the machine-level `~/CLAUDE.md` block
  carries `retries: 1` for a different gate. The prompt states `retries: 2` explicitly so the agent does not
  pick the fleet's value.
- **`verify.sh` output is 211 KB / 5,096 lines per run** (MEASURED, 114 s, exit 1 today). An agent that lets
  that into context five times spends its window on `ok:` lines. Prompts require `> file` then `grep`/`tail`.
- **`/finish` archives the brief after committing** (`finish.md:33-48`: commit and push, then `mv`). In a
  worktree the archived copy is an uncommitted rename that dies with the worktree. The land agent owns the
  archive commit, which is also where the review verdict is recorded (precedent: `8bb6b39`, `a2f4841`).
- **`.claude/briefs/current.md` is tracked and is a byte-copy of `buzz-task-scheduling.md`** (MEASURED:
  `git ls-files`, `cmp`). Every worktree starts with it. `/plan-feature` step 5 (`plan-feature.md:43-44`)
  archives "any existing current.md whose slug differs", which would land
  `archive/<date>-buzz-task-scheduling.md` on `main` and make T0.3's live brief read as finished. The ship
  prompt forbids touching `current.md` and `git mv`; the land agent stops if the diff names `current.md` or
  an archive entry for `buzz-task-scheduling`.

## 2. Ships-red: one mechanism

T1.1 and T1.2 are designed to fail the gate (plan: "Ships red on the 10 missing files", "the red list equals
those 5"). `/implement` Gate 2 and `/finish` step 1 both STOP on any red (`implement.md:44-47`,
`finish.md:20-22`). The plan's own DoD 2 says red is allowed only on drift, which these two contradict; the
Gate lines win for these two tasks.

Precedent for landing red by hand: brief 2 (`8bb6b39`: "Criterion 14 (verify.sh exits 0) is not met and
cannot be met from this branch"), brief 3 (`a987cdb`: "It ships red with exactly five named failures, and
that is the deliverable"), brief 7 (`9f7e977`: "Ships RED by design (criterion 20): the gate's two FAILs are
byte-identical to a3bed90"). Each time a human read the red set, compared it to the baseline, and committed
with the red named in the body. W6 (`e58b3f3`) records the cost: "the gate cannot go green and every PR on
this branch is red."

**Mechanism: baseline-diff equality in the land agent.** For every task, green is defined as
`red(after) == red(baseline) ∪ expectedRed(task)` as a set of lines matching `^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `,
where `expectedRed` is empty for five tasks, the 10 contract paths for T1.1, and the 5 unit names for T1.2.
The script asserts equality in code, not in prose (§11). Consequences:

- `bin/verify.sh`, the checker and every suite are untouched. The gate stays red after T1.1 lands; the red is
  named line-for-line in the landing commit body, as the three precedents did by hand.
- For T1.1 and T1.2 the ship agent runs `/plan-feature` and `/implement` with the expected red stated as the
  acceptance, commits on its branch by explicit path, pushes the branch, and does not run `/finish`. The land
  agent is the commit authority to `main`. For the other five, `/ship` runs whole and the land agent only
  verifies and fast-forwards.
- Ordering follows from it: the two red tasks go last, because once T1.1 is on `main` every later `/finish`
  in this repo stops until T2.1 closes the 5 aliases and T4.1-T4.3 close the 10 contracts. That is weeks.
  Interactive `/ship` sessions in that window need the same baseline handed to them, or they stop at Gate 2.

Alternative, not chosen because it changes the plan: make T1.1's rule two-sided against a declared
`expected-missing` list that must shrink in the same commit a contract lands (the `ci-expected-skips.txt`
and `deploy-exclusions.toml` pattern). The gate would be green with the debt named and diffed both ways.
It is the better engineering answer and it is Dave's call, not the workflow's.

## 3. Autonomy horizon

What stops a run, in the order it would bite:

| Stopper | Evidence | Effect on this design |
|---|---|---|
| Gate red on `main` today | MEASURED: `verify.sh` rc=1, 0 `FAIL:`, 1 `DRIFT [content] source-only: docs/dev-plan-2026-09.md` | every `/ship` stops at Gate 2 until `bin/deploy` runs. Pre-launch item H0 |
| Auto-sync sweep | `bin/auto-sync:39-48`: `git add -A` on any dirty `main` checkout, every 15 min (MEASURED next 09:30:02) | worktrees are gitignored, so nothing to sweep. Residual: the land agent's `git mv` + commit window of a few seconds; a tick inside it commits the archive under `Auto-sync:`. Not lost, mislabeled |
| Auto-sync refusal | `bin/auto-sync:12-15` exits 1 off `main`, firing `OnFailure=agent-alert@` | the `main` checkout never leaves `main`; the land agent asserts `git rev-parse --abbrev-ref HEAD` = `main` before and after |
| Push not by auto-sync | `bin/auto-sync:41-42` exits before push on a clean tree | the land agent pushes `main` itself and asserts `origin/main` == `main` after `git fetch` |
| Context | 211 KB per `verify.sh` run | redirect to file; the ship agent runs it at most `retries+2` times |
| Agent returns null | `workflow-authoring`: skipped or terminal API error | treated as red; stop |
| `Date.now()` unavailable in scripts | `workflow-authoring` § script body | `today` and every baseline passed via `args` |
| Sudo | passwordless for `dave` | not a stopper; the rail is that launch 1 has no step that needs it |
| Real timer windows | MEASURED `list-timers`: S2 jobs 01:33-07:37 and 22:15 CEST; `local-tier-eval` 11:17 then ~3-hourly; `fleet-turn-check` hourly; `content-change-dispatch`, `agent-inbox-sync`, `qmd-refresh` ~15-30 min | launch 1 changes nothing any unit execs. Launch 2 changes `agent_propose.sh` and must land between 08:00 and 21:00 CEST so the 22:15 `praetorium-eod-summary` is the first live consumer and a human has read the deploy first |
| Tool limits | 1000 agents/run, 6 concurrent | irrelevant at 12 agents |

Longest safe unattended stretch: launch 1 end to end, estimated 3-6 h (§8). No unit reads anything it
changes, so there is nothing to watch overnight. Launch 2 is one task, 1-1.5 h, and the human read comes
before the 22:15 timer, then again next morning for the 03:00-06:30 S2 runs.

Where a human must read first: before launch 1 (H0), between launches (H1), after launch 2 before 22:15 (H2).

## 4. Verification matrix

Run by the land agent, a fresh context that did not write the code. Each row is a command and an exit code
or a set comparison; the script asserts the returned values (§11). "Judged" rows return per-line verdicts
the land agent makes from the plan's words; they are the only non-mechanical cells and they are marked.

| Task | `verify.sh` | Plan Gate as assertion | Landed |
|---|---|---|---|
| all | `bash bin/verify.sh > $f; rc`; red set = lines matching `FAIL:`/`PROBLEM\t`/`DRIFT `; assert `red == baseline ∪ expectedRed` | below | `git fetch && [ "$(git rev-parse main)" = "$(git rev-parse origin/main)" ]`; HEAD on `main`; tree clean; brief archived in a second commit |
| T6.4 | rc 0, red = baseline | `head -30 design/workflow-registry.md` contains a frozen/D1-record header naming `design/agents/`; judged: every `keep`/live cell reads as history | as above |
| T1.3 | rc 0 | `grep -n -- '--allowedTools' design/agent-model.md`: judged per hit, none credits enforcement; `grep -n 'strict-mcp-config' design/agent-model.md` names it as the S2 containment | |
| T1.4 | rc 0 | `bash tests/test_contract_schema.sh` exit 0; output shows the negative fixture (missing section) reported red; `grep -c 'ok:'` >= 2 for the two contracts | |
| T6.2 | rc 0 (the two profile deletions read `info: runtime-only`, declared) | `grep -rn 'content-strategy\|faceless-content' design/ profiles/ bin/ config/`: judged, only historical; `grep -A3 'surfaces.scheduled' design/agents/augustus.toml` shows `present = false` or a stated reason; `deploy-exclusions.toml` entry count 9 -> 11 | |
| T1.1 | rc 1, red = baseline + exactly the 10 paths (`augustus-content`, `bd-followup-drafts`, `bd-stall-radar`, `m1-signal-scan`, `overnight-morning-report`, `praetorium-daily-plan`, `praetorium-eod-summary`, `raw-ingest`, `standing-research`, `weekly-pre-assembly`; MEASURED from `design/agents/*.toml`: 12 distinct `contract` values, 2 exist) | `python3 tests/test_workflow_coverage.py` prints a checked-count line reading 33 (MEASURED `[[workflows]]` = 1+7+3+17+5) and `grep -c '^PROBLEM.*design/contracts/'` = 10 | |
| T1.2 | rc 1, red = baseline(now incl. T1.1) + exactly 5 (`praetorium-daily-plan`, `praetorium-eod-summary`, `overnight-morning-report`, `weekly-pre-assembly`, `m1-signal-scan`) | the runner join names all four `--allowedTools`, `--strict-mcp-config`, `--model` reads; claudius's web split produces no red | |
| T6.1 | rc 0 after `bin/deploy` from `main`, targeted `rm` of `~/agent-workforce/bin/apply_skills_allowlist.sh` and `docs/skills_allowlist.md` (the `c96c54a` precedent, since `--prune` is T6.3's) | `grep -rni hermes bin/ systemd/ profiles/`: judged, only historical; `diff systemd/memory-consolidation.service /etc/systemd/system/memory-consolidation.service` empty; `sudo systemctl start memory-consolidation.service` then `journalctl -u memory-consolidation -n 40` read and returned; `ls ~/.hermes/profiles/` = `base0 leantest default` only if D4 said delete | plus: `buzz-agent@*` `ExecMainStartTimestamp` unchanged vs `args.fleetStart`; enabled-unit counts unchanged vs `args.enabled` |

## 5. Aurelian as QA

Facts that decide it:

- **`deliver.sh` cannot address him.** A mention is resolved from `ROUTE_<key>_notify` slug to
  `AGENT_<slug>` in `bin/buzz_agents.env` (`deliver.sh:323-333`); the table holds marcus, claudius,
  augustus, trajan; `tests/test_fleet_guards.sh:174` asserts aurelian is absent, and
  `design/agents/aurelian.toml:111-115` calls that absence load-bearing. Option (a) as written is not
  possible without breaking a guard. A direct `bin/buzz_publish.sh praetorium messages send --mention <hex>`
  would reach him (his rules admit praetorium, `buzz-team/aurelian.toml:44-48`), from an ad-hoc shell that
  the transport-ownership rule exists to forbid (`deliver.sh:12-15`).
- **He cannot run the gate.** Calibration pack `~/.config/buzz-team/aurelian-calibration.md` § Runtime
  policy, pinned `host-noexec-v1`: "every criterion requiring execution resolves to INCONCLUSIVE. Static
  inspection is the whole of the review." His own code rubric says "Run it. Record each command and its exit
  status" and the policy above forbids exactly that. A Buzz dispatch returns a static read, never a verify
  exit code.
- **Isolation knobs, MEASURED from `/proc`:** `NO_MEMORY=true`, `MAX_TURNS_PER_SESSION=1`,
  `CONTEXT_MESSAGE_LIMIT=0`, `HEARTBEAT_INTERVAL=0`. One turn, then the session ends. Readback would be
  channel polling for a reply from his pubkey (`run_content_via_buzz.sh:148-172` is the pattern); no verdict
  prefix is defined anywhere readable here, and his `.prompt` is deny-listed.

| | (a) Buzz dispatch | (b) in-workflow cold verifier with his calibration pack |
|---|---|---|
| Cost | one full S1 session per dispatch: static layers resent per request (`~/CLAUDE.md` § Debugging, 27-32 KB × 20-47 requests) | one `agent()` call, fresh context, ~200-400k tokens |
| Latency | minutes to tens of minutes, polled every 30 s | minutes, returned inline |
| Independence | strongest: separate unit, separate identity, Dave-visible verdict in the channel | strong: fresh context, the prompt is his pack verbatim, the same session model; the orchestrator writes the prompt |
| Mechanical readback | prose in a channel; no defined sentinel | typed schema, asserted in code |
| Can produce the verify exit code | no (host-noexec-v1) | yes |

**Recommendation: (b) for the blocking gate.** The land agent's prompt carries the calibration pack's
"Code / config" rubric and binding block (`artifact_digest`, `diff_digest`, `criteria_digest`,
`calibration_digest`, computed by the verifier from bytes it fetched). (a) stays what it is today: Dave
`@aurelian`s a landed commit from Desktop when he wants the calibration-pinned static read, which keeps the
pin intact and the fleet guard untouched.

## 6. Code review

- **Where:** in the land agent, after the fast-forward onto local `main` and before `git push`, on
  `git diff origin/main..main`. Findings reach `main` on the box but not `origin` until they clear.
- **Which skill:** the built-in `/code-review` (effort levels, `ReportFindings` with CONFIRMED/PLAUSIBLE
  verdicts). The marketplace plugin at
  `~/.claude/plugins/marketplaces/claude-plugins-official/plugins/code-review/commands/code-review.md` is a
  PR-only `gh` flow and is not what gets invoked.
- **Effort:** `medium` for T6.4, T1.3, T1.4, T6.2; `high` for T1.1, T1.2, T6.1 (gate logic, runtime wiring).
  Every task, not only M: the two S doc tasks cost minutes at medium and the review is what catches a "live"
  cell left in a frozen file.
- **Blocking rule:** stop only on a CONFIRMED finding. PLAUSIBLE findings are listed in the archive commit
  body and do not block. The land agent returns both lists; the script asserts `confirmed.length === 0`.
- **Ultra is user-only.** `/code-review ultra` is launched and billed by Dave; no agent can start it. If he
  wants it, it runs after launch 1 on `main`.

## 7. Rails as code

| Rail | Mechanism | Strength |
|---|---|---|
| No fleet restart | prompt; post-hoc: land agent returns `ExecMainStartTimestamp` for all five `buzz-agent@*`, script compares to `args.fleetStart` (MEASURED 2026-09-07 12:12:16 / 12:14:36) | detects, does not prevent |
| No unit enable | prompt; post-hoc: `systemctl list-unit-files --state=enabled | wc -l` system 122, user 14 (MEASURED) compared to `args.enabled` | detects |
| No identity minting | prompt; nothing here needs `buzz agents`; the box holds no owner key (`~/CLAUDE.md` § Buzz) | structural for minting, prompt for `buzz-admin generate-key` |
| No deny-listed reads | `settings.json` `permissions.deny` blocks `Read`/`Edit` on the five paths for subagents too; a `Bash` `cat` is not blocked in bypass mode | harness for the tools, prompt for the shell; no task here needs those paths |
| Never `--no-verify` | prompt; no git hooks exist in this repo (`.git/hooks` has samples only), so the flag has nothing to bypass here | moot |
| Commit + push per task | land agent asserts `main == origin/main` after push; script stops otherwise | mechanical |
| Stop on first red | the script's loop returns on the first failed assertion with `{stoppedAt, failingAssertion}`; nothing after it runs | mechanical |
| No `bin/deploy --prune` | prompt; `--prune` clears the nine deferred exclusions T6.3 owns (`w19-campaign-retirement-residue.md` § Out of scope) | prompt |

The one rail that would prevent rather than detect: a `PreToolUse` hook on `Bash` denying
`systemctl .*(restart|enable|disable|stop).*buzz-agent`, `--no-verify`, `buzz agents`, `deploy --prune`.
`hooks` is empty today. Adding it is a `settings.json` change (the `update-config` skill) and Dave's call.

## 8. Budget

| | Launch 1 (6 tasks) | Launch 2 (T6.1) |
|---|---|---|
| Workflow agents | 12 (2 per task) | 2 |
| Tokens, estimate | 6-12M (ship 0.3-2M per task by size; land 0.2-0.6M incl. review) | 2-3M |
| Wall-clock, estimate | 3-6 h serial (`verify.sh` 114 s × 4-6 runs per task, plus model time) | 1-1.5 h |

Datum behind the estimate: the read-only probe cost 55k tokens for 5 tool calls in 19 s. No `/ship` has been
measured on this box. `/code-review`'s internal subagents are not counted as workflow agents (they are
`Agent` calls inside one workflow agent); if the harness counts them, the 15-agent guideline is exceeded
and the script needs a third launch split at T6.2.

## 9. Human checkpoints

- **H0, before launch 1.** Run `bin/deploy` (clears the one drift line; the gate is otherwise 0 FAIL).
  Decide D4 (it decides whether T6.1 deletes the four Hermes profiles). Optionally install the hook rail.
  Confirm the baseline red set is empty after the deploy; it is passed in as `args.baselineRed`.
- **H1, between launches.** Read six landed commits and six archive commits on `origin/main`; the two
  red-shipping bodies name their red lines. Read the review notes in the archive bodies. Nothing runtime
  changed, so nothing to watch overnight.
- **H2, after launch 2, before 22:15 CEST.** Read `memory-consolidation`'s live output from the journal, the
  `bin/deploy` itemised output, and the `agent_propose.sh` diff. Next morning: the 03:00-06:30 S2 runs are
  the first live proof of the reroute.

## 10. What could not be established

- That `Skill("ship")` inside a Workflow `agent()` behaves as in the `Agent` probe. Same registry per the
  authoring reference; not measured without launching.
- That `/code-review` fans out correctly inside a workflow agent. `Agent` is present in subagents; not measured.
- The worktree path the Workflow tool uses. `.gitignore:13-17` and `bin/auto-sync:56` say
  `.claude/worktrees/`; the directory exists and is empty today.
- Whether a changed worktree persists after its agent returns. The pushed branch makes it not matter.
- Tokens per `/ship`. No measurement exists.
- Aurelian's verdict line format. The calibration pack defines binding fields, not a sentinel; his charter is
  deny-listed.
- Whether the harness counts skill-spawned subagents toward the workflow's agent total.

## 11. Script

Serial, stop on first red, two agents per task. `pipeline()` is deliberately not used: a stage that throws
drops one item and continues with the next, which is the opposite of stop-on-first-red. `args` carries
everything a script cannot compute: `today`, `tasks`, `baselineRed`, `fleetStart`, `enabled`.

```js
export const meta = {
  name: 'ship-dev-plan',
  description: 'Serially /ship ready dev-plan tasks: worktree ship, independent verify + review, fast-forward to main; stop on first red',
  phases: [
    { title: 'Ship', detail: 'plan -> implement -> finish in an isolated worktree, one task at a time' },
    { title: 'Land', detail: 'fresh agent: verify.sh set-diff, plan gate, /code-review, ff-merge, push, archive brief' },
  ],
}

// args = { today, tasks: ['T6.4', ...], baselineRed: [...], fleetStart: {marcus: '...', ...}, enabled: {system: 122, user: 14} }
const REPO = '/home/dave/dev/agent-workforce'
const PLAN = 'docs/dev-plan-2026-09.md'

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
  'T1.1': { size: 'S', review: 'high', deploy: false, shipsRed: true,
    expectedRed: ['augustus-content', 'bd-followup-drafts', 'bd-stall-radar', 'm1-signal-scan', 'overnight-morning-report',
                  'praetorium-daily-plan', 'praetorium-eod-summary', 'raw-ingest', 'standing-research', 'weekly-pre-assembly'],
    gateCmd: "python3 tests/test_workflow_coverage.py > /tmp/t11.out 2>&1; [ $(grep -c '^PROBLEM.*design/contracts/' /tmp/t11.out) = 10 ] && grep -qE '33' /tmp/t11.out",
    gateWords: 'the red list equals the 10 in the baseline; the rule reports 33 entries checked and fails below the manifest count' },
  'T1.2': { size: 'M', review: 'high', deploy: false, shipsRed: true,
    expectedRed: ['praetorium-daily-plan', 'praetorium-eod-summary', 'overnight-morning-report', 'weekly-pre-assembly', 'm1-signal-scan'],
    gateCmd: "python3 tests/test_workflow_coverage.py > /tmp/t12.out 2>&1; [ $(grep -ciE '^PROBLEM.*(model|alias|sonnet)' /tmp/t12.out) = 5 ]",
    gateWords: "the red list equals the 5 alias workflows; tools, tools_web, mcp and model are joined against --allowedTools, --strict-mcp-config, --model read out of the runner; claudius's per-workflow web split is honoured" },
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
5. Independent read, calibration-pinned. Read ~/.config/buzz-team/aurelian-calibration.md § "Code / config" and § "Binding"; compute diff_digest = git diff --binary origin/main..main | sha256sum and calibration_digest = sha256sum of that file; apply the rubric's five bullets to the diff. Then invoke the code-review skill at effort ${t.review} on git diff origin/main..main. reviewConfirmed = CONFIRMED findings (file:line: summary); reviewPlausible = the rest.
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
let baseline = args.baselineRed || []
for (const id of args.tasks) {
  const t = TASKS[id]
  if (!t) return stop(id, 'unknown task id', landed)
  phase('Ship')
  const ship = await agent(shipPrompt(id, t, baseline), { label: `ship:${id}`, phase: 'Ship', schema: SHIP, isolation: 'worktree' })
  if (!ship) return stop(id, 'ship agent returned null (skipped or terminal API error)', landed)
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
```

Notes on the script:

- `TASKS[...].gateCmd` for T1.1, T1.2 and T6.1 guesses the checker's output wording. The land agent reports
  `gateExit` from the command as written; if the implementer's line format differs, the run stops at that
  task with the evidence in hand, which is the right direction.
- `isolation: 'worktree'` is per the authoring reference; `phase` is set per call so the progress groups do
  not race.
- `args.fleetStart` and `args.enabled` are captured inline before launch by the orchestrating session; the
  script cannot read the box itself.

## 12. Launch

The sentence, after H0:

> Run bin/deploy to clear the dev-plan drift, then use a workflow: run the script in
> .claude/briefs/workflow-ship-feasibility.md §11 for tasks T6.4, T1.3, T1.4, T6.2, T1.1, T1.2, today 2026-09-08.

The orchestrating session then measures `baselineRed`, `fleetStart` and `enabled` inline and passes them as
`args`. Launch 2, after D4 and H1: the same sentence with `T6.1` alone.

What to watch while it runs:

- `/workflows` for the Ship/Land groups; a STOP line names the task and the failing assertion.
- `git -C ~/dev/agent-workforce log origin/main --oneline -14` growing by two commits per task.
- `journalctl -u agent-workforce-auto-sync -n 5` staying at "working tree clean. Nothing to do."
- `for a in marcus claudius augustus trajan aurelian; do systemctl --user show buzz-agent@$a -p ExecMainStartTimestamp --value; done`
  unchanged from 2026-09-07 12:12:16 / 12:14:36.
- The transcript directory's `journal.jsonl` for each agent's returned object if a result looks wrong.
