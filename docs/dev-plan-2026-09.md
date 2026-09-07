# Development plan — agents, workflows, skills, tools (2026-09)

**Source:** Notion page *Agent Workforce — Agents, Workflows, Skills, Tools* (MEASURED 2026-09-07).
**Tracker:** Notion database *Agent Workforce — Dev Plan*, a child of that page:
https://app.notion.com/p/071af559943649fb86494b88a67106a6 (37 rows, MEASURED 2026-09-07). Status lives
there only. This file owns scope, order and the reason for each task.
**Questionnaire:** 2026-09-07, Dave and Claude. Decisions below are his.

## Decisions taken

- Scope is the page's §9 phases 1-6, the §8 scheduling remedy, the §10 Dave-only items and
  the open loose ends in `design/open-decisions.md`.
- A task is brief-sized. Claude executes it as plan → implement → finish, with the full loop:
  `bin/deploy`, sudo unit installs and enables. An enable that changes the fleet's schedule
  gets a canary first.
- Order as the page wrote it: the self-checking gate first, then the reds, skills, contracts,
  execution. Residue cleanup runs in parallel because nothing depends on it.
- Containment on the scheduled surface: make `--allowedTools` real by taking the runners off
  `bypassPermissions`, not by documenting MCP-emptiness as the boundary.
- BD pair: build the radar runner and enable both timers.
- Platform jobs get a light contract each; the `contract` field becomes mandatory for every
  entry.
- Phase 5 executes every declared acceptance check of every contract, not a subset.
- The 14-pointer skills allocation drafted on the page is the starting bet.

## Definition of done for a Claude task

1. A brief in `.claude/briefs/` before code.
2. `bash bin/verify.sh` green. Red is allowed only on drift that this task's own deploy clears.
   Both fleet gates too when `buzz-team/` or a `buzz-agent@*` unit changes.
3. `bin/deploy` has run; units are installed and enabled; any changed unit ran once live with
   its output read.
4. Committed and pushed by hand. The auto-sync timer does not push a commit made on a clean
   tree.

Sizes: **S** one session. **M** two or three. **L** several, or one that waits on a real run.

## Baseline, measured 2026-09-07

| Fact | Value |
|---|---|
| Workflow entries in `design/agents/*.toml` | 33 (29 standing, 2 dormant, 2 spent). The page said 32; `agent-buzz-acp-update` landed the same day. |
| Contracts named / existing / missing | 12 distinct / 2 / 10 (marcus 4, claudius 5, augustus 1). 16 platform entries name none. |
| Workflows declaring `claude-sonnet` but running an alias | 5: daily-plan, eod-summary, morning-report, weekly-pre-assembly (`${VAR:-sonnet}`), m1-signal-scan (`sonnet`). |
| Fields the coverage checker reads | status, suite, unit, owner. Not tools, mcp, model, contract. |
| Scheduled runners passing `bypassPermissions` | 9 of 9. |
| `augustus-content.timer` | active; fired 2026-09-07 01:31; next 09-08 01:33. The 09-04 "found stopped" loose end is closed by this. |

## Tasks

Format: `ID [assignee, size, blocked by]`. Gate is what green means for that task.

### Phase 0 — Scheduling remedy (§8, W20)

- **T0.1** [Dave, S] Ask one agent in Buzz to run `buzz workflows list --channel <uuid>` and
  report the one-line result. Paste it, dated, into W20. Gate: output recorded.
- **T0.2** [Dave, S, T0.1] If the relay supports workflows, have Marcus create the minimal test
  workflow: `schedule` trigger, interval at least 60 s, one `send_message` naming one agent
  literally in the stored template. Gate: workflow id recorded.
- **T0.3** [Claude, S, T0.2] Prove the wake from the journal and `CPUUsageNSec` against an idle
  sibling, never by asking the agent. Record in `.claude/briefs/buzz-task-scheduling.md` and
  W20. Close W20 as available, or as `DECIDED — not available` with the timer-dispatch path
  written up as the supported mechanism. Delete the test workflow. Gate: W20 closed either way.

### Phase 1 — Make the design self-checking

- **T1.1** [Claude, S] Contract-path join in `tests/test_workflow_coverage.py`: every
  `contract` value resolves to a file. The rule reports how many entries it checked and fails
  if that is below the manifest's entry count. Ships red on the 10 missing files. Gate: the red
  list equals the 10 in the baseline.
- **T1.2** [Claude, M] Runner join: `surfaces.scheduled` tools, `tools_web`, `mcp` and each
  workflow's `model` against what the named runner passes (`--allowedTools`,
  `--strict-mcp-config`, `--model`), read out of the script. Honour claudius's per-workflow
  web split. Ships red on the 5 alias workflows. Gate: the red list equals those 5.
- **T1.3** [Claude, S] Correct `design/agent-model.md:60` and §6.1. Today S2 containment is
  `--strict-mcp-config` plus the `agent_propose.sh` write boundary; the allowlist is inert
  under `bypassPermissions`. Gate: no line credits `--allowedTools` as enforcement. T2.2
  revises this again when enforcement lands.
- **T1.4** [Claude, M] Contract schema validator in the gate: every `design/contracts/*.md`
  carries the eight sections in order, Identity's owner equals the declaring manifest, one
  contract per unit. Gate: green on the two existing contracts; a fixture missing a section
  fails.

### Phase 2 — Close what Phase 1 turns red

- **T2.1** [Claude, S, T1.2] Pin `claude-sonnet-5` in the four runners (`run_daily_rhythm_cc`,
  `run_overnight_morning_report_cc`, `run_weekly_pre_assembly_cc`, `run_m1_signal_scan_cc`)
  and the five manifest rows. Drop `${VAR:-sonnet}` or default it to the full id. Smoke suites
  assert the full id. Gate: T1.2 green on model.
- **T2.2** [Claude, L, T1.2, T1.3] Make the allowlist real. Move the scheduled runners off
  `bypassPermissions`; canary on knowledge-digest with the run output read; then the other
  eight; re-run every smoke suite; add a gate rule that no `run_*_cc.sh` passes
  `bypassPermissions`; revise `agent-model.md` §6.1. The brief states what a bare `Bash`
  allowlist entry still permits, so the claim stays honest. Gate: nine runners converted, nine
  suites green, one live run per runner read.
- **T2.3** [Claude, M] bd-stall-radar runner: `bin/run_bd_stall_radar_cc.sh` on the m1 pattern
  around `bin/bd_stall_radar_kernel.py`; a smoke suite; `profiles/bd_stall_radar.env.example`
  with `AGENT_VERIFY_CMD`; the manifest's `runner` field. Existing brief:
  `.claude/briefs/bd-radar-followup-timers.md`. Gate: verify green; the unit stays disabled.
- **T2.4** [Claude, M, T2.3, D1] Enable both BD timers. Fix the drafts example's
  `AGENT_PROFILE` line; diff repo and `/etc` units both ways (OnFailure parity); enable; one
  live run each with output read; manifests dormant → standing; §10 item 1 closed. Gate: two
  live runs each produced a proposal or a `DECLINE:`.

### Phase 3 — Skills as a per-workflow field

- **T3.1** [Claude, L] Pointer-skill tree `skills/` in this repo: each a few lines naming the
  canonical vault path, never a copy. Deployed by `bin/deploy`; compared by
  `bin/check_deploy_drift.sh` as an additional tree; loaded by the scheduled runner from an
  explicit path in the deployed tree, not from `~/.claude/skills/`. A test asserts the skill
  list the runtime sees equals the repo's. The 14 drafted pointers are the initial content.
  Gate: drift covers `skills/`; a headless run lists the skills.
- **T3.2** [Claude, M, T3.1, T1.2] `skills = [...]` on all 33 entries, an empty list stated
  explicitly, joined to the runner's offer by T1.2's mechanism. Augustus's entries carry
  `skills_mechanism = "heading-extraction"` (`bin/skill_sections.sh`). `agent-model.md`
  records the allocation as a bet: 1 of 14 grounded in a live workflow. Gate: join green,
  33 of 33 carry the field.
- **T3.3** [Claude, S, T3.2] Invocation telemetry: per run, which pointer skills were read,
  from run-log or transcript evidence, summarised by the scorecard. Gate: one week of runs
  yields a per-skill count.

### Phase 4 — Write the contracts

- **T4.0** [Claude, M, T1.4] Executable check syntax. Extend `design/contract-schema.md` so
  every acceptance check carries a decidable command the executor runs, given unit,
  `RUN_DATE`, run-log path and systemd properties. Convert `knowledge-digest.md`. The
  validator enforces the syntax. Gate: validator green on the converted file; a prose-only
  check fails it.
- **T4.1** [Claude, M, T4.0] Marcus's four: praetorium-daily-plan, praetorium-eod-summary,
  overnight-morning-report, weekly-pre-assembly, each with its Notion receipt check. Gate:
  T1.1's red list shrinks by four.
- **T4.2** [Claude, L, T4.0, T2.3] Claudius's five: standing-research, raw-ingest,
  m1-signal-scan, bd-stall-radar, bd-followup-drafts. Gate: red list shrinks by five.
- **T4.3** [Claude, M, T4.0] augustus-content, shared by two triggers. Must carry the
  corpus-freshness check that would have caught the nine-night failure, and the three-state
  exit. Gate: T1.1's red list is empty.
- **T4.4** [Claude, L, T4.0] Light contracts for Trajan's 14 standing platform jobs: trigger,
  artifact, cadence and at least one check (fired within window, artifact is this run's).
  Inputs and side effects may read `none`. The two spent entries get `contract_exempt` with a
  reason. Gate: 14 files pass the validator.
- **T4.5** [Claude, S, T4.1, T4.2, T4.3, T4.4] Field mandatory: T1.1 flips from "resolves if
  present" to "present and resolves". Exemption only for `status = "spent"`. Gate: green with
  no exemption beyond the two spent.

### Phase 5 — Execute the contracts

- **T5.1** [Claude, L, T4.0] The executor: runs every check of a unit's contract for a given
  run, one result per check, non-zero on any failure. Fixture tests per check class: lock
  skip, timer fired within window, input freshness, artifact is this run's, write boundary,
  sentinel branch. Gate: green on knowledge-digest fixtures, checks 7-9 included.
- **T5.2** [Claude, L, T5.1, T4.5] Wiring: S2 and S4 runs call it from `agent_propose.sh`
  after `AGENT_VERIFY_CMD`; platform jobs through a post-run hook or a sweep timer, the brief
  decides which. Results land in a receipt directory the gate can read. Gate: every standing
  unit produces a receipt within one cadence.
- **T5.3** [Claude, M, T5.2] Surfacing: overnight-morning-report and fleet-eval read the
  receipts and name failed checks; the scorecard counts them. Gate: a deliberately failing
  check appears by name the next morning.
- **T5.4** [Claude, M, T5.2] Proof on real runs: one full week with every declared check of
  every contract executed against real runs; the pass matrix recorded in the brief. Gate:
  matrix complete, no check skipped.

### Phase 6 — Retire the residue

- **T6.1** [Claude, M] Hermes residue: `bin/apply_skills_allowlist.sh`,
  `docs/skills_allowlist.md`, the five `[surfaces.kanban]` blocks with `agent-model.md` §3
  updated to match, and `~/.hermes/profiles/{marcus,claudius,augustus,trajan}`. Precondition:
  inventory the remaining hermes references in `bin/consolidate_memory.sh`,
  `bin/praetorium-status.sh`, `bin/agent_propose.sh`, `systemd/memory-consolidation.service`
  and the four `profiles/*.env.example` that name it, then retire or reroute each. Keep
  `base0` and `leantest` while local-tier-eval needs them. Gate: a grep for hermes across
  `bin/ systemd/ profiles/` returns only historical notes; verify green.
- **T6.2** [Claude, M] W19, the design and profiles half: `design/workflow-registry.md:77-78`,
  `design/eval-spec.md:166-167`, `augustus.toml`'s scheduled surface (`present = false` or a
  stated reason), the two `profiles/` task files declared runtime-only, the W19 row updated.
  Gate: verify green; the brief's check 2 grep returns only historical notes.
- **T6.3** [Dave then Claude, S, T6.2] W19, the bin half: `bin/deploy --prune` removes the three
  runner scripts and clears nine deferred exclusions in one act. Dave picks the moment and
  deletes the two override envs in the deny-listed tree; Claude runs the prune and re-verifies.
  Gate: drift clean with no runtime-only `bin/` files.
- **T6.4** [Claude, S] `design/workflow-registry.md` is joined by no test or script. Freeze it as
  the D1 record with a header pointing at the manifests. Gate: header present, no live claim
  left in it.

### Phase D — Dave-only

- **D1** [Dave, S] Place the two BD override envs in `~/.config/agent-workforce/`: the radar
  from T2.3's new example, the drafts one with `AGENT_PROFILE` fixed. Mode 600. Unblocks T2.4.
- **D2** [Dave, S] Install `AGENT_VERIFY_CMD` into `~/.config/agent-workforce/m1_signal_scan.env`
  from `profiles/m1_signal_scan.env.example`. Mode 600.
- **D3** [Dave, M] Codex filesystem permission profile: select `default_permissions` in
  `~/.codex/config.toml` denying `.ssh/**`, `.config/buzz-agents/**`,
  `.config/agent-workforce/**` and `ENCRYPTION_RECOVERY.md`; grant `/home/linuxbrew` read;
  `workspace_roots` entries relative. A posture change, proven working here 2026-08-04.
- **D4** [Dave, S] Augustus's ZDR pin. Closes with T6.1 if his Hermes profile is deleted;
  otherwise set `only: ["azure"]`. Decide which.
- **D5** [Dave, M] Vault edit, Mac-side: make
  `03_projects/active/ai_agent_workforce/buzz_architecture.md` win retrieval for "how does the
  workforce publish and get proposals approved", then re-baseline `fleet_eval`'s
  `p2_publish_approve` to PASS.
- **D6** [Dave, Refine] The website corpus is 644 hours old. Publish, or accept the freshness
  refusal as correct. A content decision.
- **D7** Done 2026-09-07: workflow authoring granted in `TEAM.md`.
- **D8** is T0.1.

### Phase L — Loose ends

- **L1** [Dave, S] Marcus's engram is near 79% of the 65,535 B wall. Ask Marcus to prune it
  with `buzz mem patch core --base-hash`, never `set`. Gate: `buzz mem hash core` changed,
  size under 60%.
- **L2** Closed by measurement 2026-09-07: `augustus-content.timer` is active and fired today.

## Execution order for Claude

1. T1.1, T1.4, T1.3, then T1.2 last, because Phase 2 hangs on it.
2. T6.1, T6.2, T6.4 alongside Phase 1; nothing depends on them.
3. T2.1 and T2.3, then T2.2 (largest, needs a canary window), then T2.4 once D1 lands.
4. T3.1, T3.2, T3.3.
5. T4.0 first. Then T4.1, T4.3, T4.4, T4.2 (BD last, after T2.3), T4.5.
6. T5.1 starts right after T4.0, in parallel with contract writing. Then T5.2, T5.3, T5.4.
7. T0.3 when T0.2 lands. T6.3 when Dave says.
