# Development plan — agents, workflows, skills, tools (2026-09)

**Source:** Notion page *Agent Workforce — Agents, Workflows, Skills, Tools* (MEASURED 2026-09-07).
**Tracker:** Notion database *Agent Workforce — Dev Plan*, a child of that page:
https://app.notion.com/p/071af559943649fb86494b88a67106a6 (43 rows, MEASURED 2026-09-10). Status lives
there only. This file owns scope, order and the reason for each task.
**Questionnaire:** 2026-09-07, Dave and Claude. Decisions below are his.
**Review:** *Workflow Portfolio & Automation Governance Proposal — 2026-09-10*, by the vault's
Process & Automation Architect persona (`06_resources/prompts/ops_process_automation_architect.md`).
It arrived in two waves on the same day: a **governance wave** (13:00 UTC) that rewrote thirteen
cards and widened the gates on Phases 4, 5 and 7, and a **confirmed-operator-requirements wave**
(15:21-15:23 UTC) that rewrote all four Phase 5 cards and split T5.3 into a Control Room plus four
sub-cards. Both are folded into the task text below; § *What the 2026-09-10 review changed* records
the delta and two corrections to the review itself.

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
- The 13-pointer skills allocation drafted on the page is the starting bet. The page says 14
  and its own table sums to 13; the table is what T3.1 built. `skills/README.md` carries the
  correction, and `design/archive/open-decisions-closed-2026-09-07.md` keeps its 14 as the
  record of what was written.
- **The Dev Plan stays the only delivery backlog** (review, 2026-09-10). The workflow-portfolio
  read model and its benefit evidence arrive through the existing Phase 4 and Phase 5 cards. No
  second roadmap, and no parallel contract schema — the actionability fields land inside the
  eight sections that already exist.
- **The Control Room reads; the repo writes** (review, wave two). The operator surface is a private
  browser interface on this box for Dave only. It renders manifests, contracts and receipts and
  never becomes a second source of truth: live controls go through a root-owned allowlisted broker
  that accepts a known workflow id and a named action only, and schedule changes and retirements are
  produced as reviewed source-repo PRs rather than as edits to the deployed tree. Notion is where an
  artifact opens, not where the portfolio lives.
- **Unavailable is a value; zero is a measurement.** Receipts carry per-run tokens and cost with an
  explicit unavailable state. `tokens=unknown` and a frozen OpenRouter-derived `0.000000` are being
  rendered today as if they were measured — every benefit number built on them inherits the lie.
  Same rule as `Unknown` for benefit, one layer down.
- **Actionability is part of a contract, not a later reporting layer.** A workflow ending in
  "recommendation generated" has not closed its loop. Every standing workflow names an artifact or
  state change, a beneficiary, a next actor and next action, a valid no-output state, and a benefit
  hypothesis whose value may be `Unknown` — but never absent. `Unknown` is the preferred value
  until a baseline and a consumption signal exist; an estimate is metric theatre.

## Definition of done for a Claude task

1. A brief in `.claude/briefs/` before code.
2. `bash bin/verify.sh` green. Red is allowed only on drift that this task's own deploy clears.
   Both fleet gates too when `buzz-team/` or a `buzz-agent@*` unit changes.
3. `bin/deploy` has run; units are installed and enabled; any changed unit ran once live with
   its output read.
4. Committed and pushed by hand. The auto-sync timer does not push a commit made on a clean
   tree.

Sizes: **S** one session. **M** two or three. **L** several, or one that waits on a real run.

## Baseline

Two columns. 2026-09-07 is what the plan was written against and what T1.1's gate was sized from;
2026-09-10 is current. Both MEASURED on the box, not remembered.

| Fact | 2026-09-07 | 2026-09-10 |
|---|---|---|
| Workflow entries in `design/agents/*.toml` | 33 (29 standing, 2 dormant, 2 spent) | 33 (**31 standing**, 2 spent) — the two BD entries went dormant → standing with T2.4 |
| **Logical** standing workflows | not distinguished | **30** — `augustus-content` and `content-change-dispatch` are two triggers for one workflow, not two products |
| Contracts named / existing / missing | 12 / 2 / 10 (marcus 4, claudius 5, augustus 1) | 12 / **12** / **0** |
| Contracts carrying the review's actionability fields | n/a | **12 of 12** (`063e6ce`) — measured **0 of 12** earlier the same day; backfilled with T4.1-T4.3 and now enforced as `outputs-actionability` |
| Workflows declaring `claude-sonnet` but running an alias | 5 | **0** (T2.1) |
| Fields the coverage checker joins | status, suite, unit, owner | + contract path, runner, model, tools, mcp (T1.1, T1.2) |
| Scheduled runners passing `bypassPermissions` | 9 of 9 | **0 of 9** (T2.2) |
| Tracker rows | 37 | 43 |
| `bash bin/verify.sh` | red on 10 `contract-exists` | **green, rc=0**, one declared skip |
| `augustus-content.timer` | active; fired 09-07 01:31 | active, and **failing most nights** — see T7.2 |

## What the 2026-09-10 review changed

The review is *Workflow Portfolio & Automation Governance Proposal — 2026-09-10*, produced by the
vault's Process & Automation Architect persona against the Notion page, this tracker and this repo.
It changed **Notion only** — no repo mutation — because T3.1 was being implemented concurrently.

**Its diagnosis.** The execution plane is ahead of the evidence plane. The repo is a good source of
truth for what a workflow *is* and systemd for whether it *ran*; nothing joins either to what it
*produced* or who *acted* on it. So "the timer fired" is easier to see than "the workflow produced
something useful", and the primary failure mode is open-loop output.

**What it did to the board, wave one (13:00 UTC).** Thirteen cards rewritten (T3.1, T4.0–T4.5,
T5.1–T5.4, T7.1, T7.2), two added (T7.1 and T7.2 — both were in this file and in neither the
board), one status corrected (T3.1 Todo → In Progress).

**What it did to the board, wave two (15:21–15:23 UTC), sourced as *confirmed operator
requirements*.** All four Phase 5 cards rewritten again and four sub-cards added, taking the tracker
from 39 rows to 43. This is the wave that turns Phase 5 from "emit receipts and surface them" into
an operator product:

- **T5.3 renamed a second time** — "Publish workflow portfolio and surface contract results" →
  **"Build the read-only Praetorium Control Room"**: a private browser interface hosted on this box,
  for Dave only, opening on workflow health, incomplete or failed runs, and token usage by agent.
  Notion stops being the portfolio surface and becomes the place an artifact opens.
- **T5.3a** live workflow controls (pause / resume / run now / retry / stop) through a root-owned,
  allowlisted broker.
- **T5.3b** schedule changes and retirements land as **reviewed source-repo PRs**, never as a direct
  mutation of the deployed tree.
- **T5.3c** a dedicated Buzz stream for workflow *incidents* — exceptions only, deduplicated, with a
  daily digest of what is still unresolved.
- **T5.3d** agent-to-agent handoff traces (Marcus → Trajan) as structured run events.
- **T5.1 and T5.2 gain a telemetry requirement** that is really a defect report: the receipt must
  carry per-run tokens and cost with an explicit *unavailable* state, because today's
  `tokens=unknown` and a frozen OpenRouter-derived `0.000000` are being rendered as if they were
  measured zero.
- **T5.4 splits the consumption signal** into four distinct observations — opened, approved,
  sent/published, manually marked useful — and forbids collapsing them into one score.

**What it adds here**, in its own priority order:

1. **Actionability inside the contract** (Phase 4). Every `## Outputs` names seven things: artifact
   or state change; beneficiary and next actor; next action; location and freshness; valid
   no-output conditions; benefit hypothesis and measurement signal; and an acceptance assertion
   proving the artifact belongs to this run. Explicitly *not* a new schema — these live inside the
   eight sections already in `design/contract-schema.md`.
   **LANDED 2026-09-10, `063e6ce`**, as *five* `## Outputs` bullets rather than six: beneficiary,
   next actor, next action, benefit hypothesis, benefit signal. The valid no-output state stayed in
   `## Decline conditions`, which already enumerates and validates those states — a second copy in
   `## Outputs` would be a second owner of one fact, the shape this schema keeps deleting. The
   deviation is recorded in the schema doc and in the suite header, not only here.
2. **A uniform run receipt** (T5.1, T5.2). One structured receipt per run: workflow id, run id,
   start/end, **exactly one** terminal outcome, artifact URI or state-change evidence, assertion
   results, next actor and action due, cost/runtime. A silent skip is never a success.
3. **A published control surface** (T5.3). Portfolio, exception and benefit views generated from
   manifests, contracts and receipts. The default operator experience is the exception queue, not a
   wall of 30 healthy rows. Wave two made this a **box-local browser interface** — see below.
4. **Forced keep / improve / retire** (T5.4), one decision per logical workflow, on evidence.

**Two corrections to the review**, both measured here:

- It cites `2e359f5` as where T3.1 landed. That commit is an **auto-sync tick** — the 15-minute
  timer swept the worktree mid-session. T3.1 is `a83792a`, which carries the message that tick lost,
  including the recorded headless-run output the card's own gate asks for. The review's risk
  register predicted exactly this ("commit evidence remains buried in git"); it is why T3.1 is Done
  below and not In Progress.
- It puts the database at 40 cards (38 + 2). It was never 40 at any moment. Measured over the REST
  API on 2026-09-10 at 17:19 CEST: **39** — the pre-review figure was 37 (this file, MEASURED
  2026-09-07), not 38, and wave one added two. Two minutes later wave two added the four T5.3
  sub-cards, taking it to **43**, which is what the header now records.

**Where it leaves the contracts already written — closed the same day.** T4.1, T4.2 and T4.3 first
landed against this file's *original* gates: the `contract-exists` red list is empty and
`bin/verify.sh` is green. Against the *reviewed* gates they were half done — all 12 contracts
carried the mechanism half (artifact, location, freshness, valid decline, a run-anchored assertion)
and **none** declared a beneficiary, next actor, next action or benefit hypothesis, verified by grep
across `design/contracts/` with zero matches. `063e6ce` closed that half: five bullets defined once
in `design/contract-schema.md`, backfilled into all twelve, and enforced as `outputs-actionability`
rather than left to T4.5. T4.1 and T4.2 are Done. T4.3 is not — its reviewed gate also asks that a
deliberately missing board movement fail by name, and that assertion does not exist yet.

## Tasks

Format: `ID [assignee, size, blocked by]`. Gate is what green means for that task.

### Phase 0 — Scheduling remedy (§8, W20)

- **T0.1** [Dave, S] Ask one agent in Buzz to run `buzz workflows list --channel <uuid>` and
  report the one-line result. Paste it, dated, into W20. Gate: output recorded.
- **T0.2** [Dave, S, T0.1] If the relay supports workflows, have Marcus create the minimal test
  workflow: `schedule` trigger, interval at least 60 s, one `send_message` naming one agent
  literally in the stored template. Gate: workflow id recorded.
- **T0.3** [Claude, S, T0.2] Prove the wake from the journal and `CPUUsageNSec` against an idle
  sibling, never by asking the agent. Record in `.claude/briefs/archive/2026-09-10-buzz-task-scheduling.md` and
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
  list the runtime sees equals the repo's. The 13 drafted pointers are the initial content.
  Gate: drift covers `skills/`; every scheduled runner offers its owner's deployed tree behind a
  readability guard; a headless run lists the skills.
  **DONE 2026-09-10, `a83792a`.** 13 pointers, four owner plugin manifests, `--plugin-dir` wiring
  and readability guards in all nine runners, deploy/drift coverage, suites, docs. The gate's
  headless half is recorded in that commit message (claudius → investment-research, meeting-prep,
  prospect-research; marcus → agent-inbox-sync, post-call-capture, weekly-review; per-owner
  isolation holds). The review saw only the auto-sync tick `2e359f5` and left the card In Progress.
- **T3.2** [Claude, M, T3.1, T1.2] `skills = [...]` on all 33 entries, an empty list stated
  explicitly, joined to the runner's offer by T1.2's mechanism. Augustus's entries carry
  `skills_mechanism = "heading-extraction"` (`bin/skill_sections.sh`). `agent-model.md`
  records the allocation as a bet: 1 of 13 grounded in a live workflow. Gate: join green,
  33 of 33 carry the field.
  **DONE 2026-09-11, `701b766`.** 33 of 33 entries carry `skills = [...]` (16 trajan platform
  entries and the five `buzz-agent@*` entries as `[]`), joined by four asserts-anchored ids
  (`skills-declared`, `skills-mechanism`, `skills-join`, `skills-join-counted`) with four
  negative fixtures on copied checkouts. Live tree: 2 heading-extraction, 12 with a non-empty
  offer. The bet, recorded in `agent-model.md` §2 and §8.4: 13 pointers; 7 offered on at least
  one live entry (6 by `--plugin-dir` across 10 claudius/marcus entries, 1 by heading-extraction
  across augustus's 2 content triggers); 1 of 13 named by a live profile
  (`linkedin-content-engine`); 6 reach nobody (trajan's 4, `linkedin-review`, `blog-engine`).
  Offered is not used — invocation is unmeasured until T3.3. Gate ran against a scratch copy of
  the runtime tree (`AGENT_WORKFORCE_RUNTIME`), because the live tree carried T5.1's
  un-merged deploy; the live deploy follows the merge.
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
  overnight-morning-report, weekly-pre-assembly, each with its Notion receipt check.
  Reviewed requirement: each `## Outputs` also names the beneficiary, the next actor and the next
  action — daily plan → Dave chooses and executes the day's priorities; EOD summary → close or
  carry work with evidence; morning report → the **remediation owner** resolves the exception, not
  merely reads it; weekly pre-assembly → the weekly review decision. A report with no named next
  action is incomplete.
  Gate: T1.1's red list shrinks by four **and** all four carry the actionability fields.
  **DONE 2026-09-10, `37d9563` + `063e6ce`** — four contracts, 24 executable checks, red list
  10 → 6, and the actionability fields backfilled and enforced. All four answer `Unknown` for the
  benefit signal and say why: nothing on this box measures whether Dave read the report.
- **T4.2** [Claude, L, T4.0, T2.3] Claudius's five: standing-research, raw-ingest,
  m1-signal-scan, bd-stall-radar, bd-followup-drafts.
  Reviewed requirement: each names the next commercial or editorial move its artifact enables —
  standing research → a reviewable vault-change proposal; raw ingest → one distillation with target
  file and exact content; m1 signal scan → the decision the signal should inform; **bd-stall-radar
  must not stop at "stalled"** but rank and name the next commercial decision; bd-followup-drafts →
  a copy-ready pack closing the radar-to-send-material handoff. BD benefit evidence is a draft used,
  edited, parked or rejected — never invented revenue.
  Gate: red list shrinks by five **and** all five join to a real run and a downstream action.
  **DONE 2026-09-10, `28cc156` + `063e6ce`** — five contracts, 47 checks, red list 5 → 0, gate
  green, and the actionability fields backfilled and enforced. Two of the five name a benefit signal
  that is already computable and computed by nothing — `raw-ingest`'s ingest backlog, which is this
  job's own input, and `standing-research`'s Mac-side promotion rate. The other three answer
  `Unknown`, which is the finding rather than a gap in the writing.
- **T4.3** [Claude, M, T4.0] augustus-content, shared by two triggers. Must carry the
  corpus-freshness check that would have caught the nine-night failure, and the three-state exit.
  Reviewed requirement: the two triggers are **one logical workflow**, not two products. The
  artifact receipt names the content row, the resulting state, the draft location, run/event
  identity and who acts next; a trigger receipt with no board movement, draft or owned decline is a
  failure. Benefit signals: Picked-to-Drafted latency, valid-artifact rate, human edits required,
  whether the draft was scheduled or published — ROI stays `Unknown` until consumption is measured.
  Gate: T1.1's red list is empty, the two manifest entries reconcile to one logical workflow, **and**
  a deliberately missing board movement fails by name.
  **HALF LANDED 2026-09-10, `9c36094` + `063e6ce`** — one contract for both triggers, red list
  6 → 5, and the actionability fields backfilled: the beneficiary splits by trigger — Dave for a
  board row, **augustus** for a `content-change-dispatch` tick, the only artifact on this box whose
  reader is an agent — and the benefit signal is the board delta, already computed by
  `deliver_content.sh` and read by nothing. Outstanding: **the named board-movement assertion.**
  `run-ended-in-a-named-outcome` accepts `no board movement and no reply within` as one of the seven
  terminal branches, so a night that moved nothing still passes by name. The reviewed gate asks for
  the opposite, and closing it is a decision about the three-state exit, not a line to bolt on.
- **T4.4** [Claude, L, T4.0] Light contracts for Trajan's 14 standing platform jobs: trigger,
  artifact, cadence and at least one check (fired within window, artifact is this run's).
  Inputs and side effects may read `none`. The two spent entries get `contract_exempt` with a
  reason and stay out of the active portfolio.
  Reviewed requirement: **a log line alone is not an artifact** unless a named consumer or alert
  path acts on it. Each contract names trigger, cadence, artifact or state change, evidence
  location, failure-remediation owner and at least one executable check. Minimum mappings:
  health/eval/drift/update → a verdict or alert carrying the failed assertion and its remediation
  owner; sync/refresh/auto-sync/consolidation/drain → a state change with before/after or receipt
  evidence; snapshot/scorecard → a dated artifact and a named downstream consumer; temporary
  watchers → a status-change alert and an explicit **retirement condition**. Risk avoided and
  operator time saved are hypotheses until failures are caught or manual effort is baselined —
  record `Unknown` rather than estimate.
  Gate: 14 files pass the validator, and every standing platform workflow exposes an actionable
  artifact or state change plus a retirement condition where one applies.
  **DONE 2026-09-11, `96c9019` (PR #31, merged `d11be38`)** — fourteen light contracts, two
  `sweep` checks each (timer fired within its window; this run's own evidence exists), all 28
  dry-run to 0/77/1, validator and gate green. The two spent entries carry `contract_exempt` with a
  reason; the manifest counts 33 entries, 31 `contract`, 2 exempt, 26 distinct contract paths, 26
  on disk. All fourteen answer `Unknown` for the benefit signal, which is the finding, not a gap.
  Two things surfaced and left as written: `buzz-pr-watch` self-retires — its second check fails by
  name once block/buzz#3816 is closed **and** announced (still open on 2026-09-11) — and
  `/usr/local/bin/ttm-pool-drain` sits outside the repo, so no drift check covers it. Written while
  the fleet was paused, so every timer check currently says "not loaded or never fired", which is
  the correct answer; `qmd-refresh` stayed enabled and is green.
- **T4.5** [Claude, S, T4.1, T4.2, T4.3, T4.4] Field mandatory: T1.1 flips from "resolves if
  present" to "present and resolves". Exemption only for `status = "spent"`.
  Reviewed requirement, **half of it already landed**: the actionability rule became enforced with
  T4.1-T4.3 (`063e6ce`, `outputs-actionability`), because all twelve contracts complied the moment
  they were backfilled and enforcing over a compliant tree costs nothing. So T4.5 keeps only the
  manifest-side flip — `contract` from "resolves if present" to "present and resolves", exempt only
  for the two spent entries — and that half genuinely must wait for T4.4's fourteen files. The valid
  no-output state is enforced in `## Decline conditions`, where it already lived; T4.5 does not add a
  second copy of it to `## Outputs`.
  Gate: green with no exemption beyond the two spent, **and** the 31 standing manifest entries
  reconcile to 30 logical standing workflows with no unexplained duplicate.

### Phase 5 — Execute the contracts

- **T5.1** [Claude, L, T4.0] The executor: runs every check of a unit's contract for a given
  run, one result per check, non-zero on any failure. Fixture tests per check class: lock
  skip, timer fired within window, input freshness, artifact is this run's, write boundary,
  sentinel branch.
  Reviewed requirement — **the receipt is part of this card, not a later one.** Every execution
  emits a structured receipt carrying workflow id, run id, start/end, terminal outcome, artifact URI
  or state-change evidence, assertion results, next actor and action due, and runtime/cost where
  meaningful. **Exactly one** terminal outcome is legal: artifact, valid decline/no-op, failed, or
  skipped. Silent success is invalid. The schema must be consumable by T5.3 without scraping prose,
  and must preserve T7.1's run identity rather than re-flattening it.
  Confirmed telemetry requirement (wave two) — **this half is a defect report, not a feature.** The
  receipt carries agent/model plus input, output, cache and total token counts when the runtime
  provides them, and cost amount, currency, source and confidence. Where the runtime provides
  neither, the receipt says **unavailable**. Today's `tokens=unknown` and the frozen
  OpenRouter-derived `0.000000` are rendered as though they were measured zero, and every benefit
  number downstream inherits that. Optional `parent run id` and handoff actor/recipient/event fields
  land here too, so T5.3d never has to reconstruct causality from logs.
  Gate: green on knowledge-digest fixtures including checks 7-9; a run producing neither a current
  artifact nor a valid decline fails; the receipt validates against the declared workflow, carries
  truthful tokens and cost, and **never renders unavailable usage as zero**.
- **T5.2** [Claude, L, T5.1, T4.5] Wiring: S2 and S4 runs call it from `agent_propose.sh`
  after `AGENT_VERIFY_CMD`; platform jobs through a post-run hook or a sweep timer, the brief
  decides which. Results land in one receipt directory keyed by workflow and run.
  Reviewed requirement: the wiring joins each receipt to its actionable artifact or state-change
  evidence, and preserves two-trigger/one-workflow semantics for augustus-content. Interactive
  services need a request/response receipt strategy — **do not pretend an always-on service has a
  timer cadence**, which is the shape `buzz-interactive` already refuses to fake.
  Confirmed wiring requirement (wave two): per-run token and cost fields come from the runtime's own
  output, **not** from the obsolete shared-key delta. Parent/child ids survive agent-to-agent
  dispatch. Missing data stays `Unknown` and is never synthesized.
  Gate: every standing workflow produces a valid receipt within one cadence or triggering
  interaction; the 31 standing entries reconcile to 30 logical workflows; no success exists without
  artifact or state-change evidence, or an accepted no-output state.
- **T5.3** [Claude, M, T5.2] **Build the read-only Praetorium Control Room** — renamed twice by the
  review, first from "Surfacing" to "Publish the workflow portfolio", then to this. A private
  browser interface **hosted on this box, for Dave only**, generated from manifests, contracts and
  receipts. Notion stops being the portfolio surface and becomes where an artifact opens; workflow
  truth is still edited in the repo, so the Control Room never becomes a second source of truth.
  overnight-morning-report and fleet-eval still read the receipts and name failed checks, and the
  scorecard still counts them — the browser is an additional surface over the same receipts, not a
  replacement for the morning delivery.
  **Opening screen:** workflow health, incomplete and failed runs, token usage by agent. Each
  logical workflow appears **once**, even with multiple triggers.
  **Workflow page:** purpose, all triggers and schedules, last and next run, latest valid artifact,
  incomplete runs, reliability, tokens and cost, benefit and consumption signals, contract and Dev
  Plan links. The latest output opens directly in Notion. For research, render the full lineage:
  source → selection rule and reason → trigger → agent → Notion output → human action.
  **Three required views:** *Portfolio* — 30 logical standing workflows with owner, purpose, trigger,
  artifact/state change, beneficiary, next action, benefit status, last run, last valid artifact,
  contract and Dev Plan links. *Exceptions* — only failed, stale-input, missed-cadence,
  missing-artifact, unconsumed-output and overdue-next-action rows. *Benefit* — baseline, eligible
  runs, valid-artifact rate, consumption signal, latency, manual minutes avoided, and the
  Keep/Improve/Retire state, where `Unknown` is valid and preferred when unmeasured.
  Output-use signals are counted **separately** — opened, approved, sent/published, manually marked
  useful — never collapsed into one opaque score. Healthy workflows recede; exceptions and owed
  decisions lead. The default operator experience is the exception queue, not a wall of 30 healthy
  rows.
  **Backend foundation landed 2026-09-11:** `bin/control_room_api.py` now exposes the versioned,
  read-only JSON surface for overview, workflows, runs, incidents, usage and activity. It reconciles
  the 31 standing manifest entries to 30 logical workflows, validates future T5.1 receipts, and
  reports missing contracts, receipts or systemd visibility as degraded/Unknown rather than fake
  health, usage or cost. This is an enabling slice, not completion of T5.3: T5.1/T5.2 still own the
  real receipt stream, and the production frontend plus durable private hosting remain on this card.
  Gate: a deliberately failing check appears by name the next morning; the local browser reconciles
  30 logical workflows with no unexplained duplicate or missing artifact field, and shows health,
  incomplete runs, truthful agent usage, research lineage and one-click Notion output links.
- **T5.3a** [Claude, M, T5.3] **Live workflow controls**, through a **root-owned, allowlisted
  broker**. The browser submits a known workflow id and a named action and **never** arbitrary
  shell, unit or path input — that constraint is the card, not a detail of it. Pause (future fires
  stop; the current run finishes by default), resume (showing any `Persistent=true` catch-up
  implication *before* applying), run now (returns a run id), retry (only where the contract
  declares the operation idempotent), stop current run (destructive confirmation plus a reason).
  Every action records actor, reason where required, before/after state, timestamp, result, next
  scheduled run and links.
  Gate: unknown ids, units, actions or arguments are refused; pausing during an active run does not
  kill it; UI state is **reconciled from systemd after each action**, never assumed from the click;
  every action — successful or refused — emits an audit receipt; tests prove system-scope and
  user-scope units are addressed correctly. Creating a workflow, changing its schedule and retiring
  it are all out of scope here — they are T5.3b or a conversation.
- **T5.3b** [Claude, M, T5.3] **Schedule changes and retirements as reviewed PRs.** Dave requests
  one from the Control Room; the implementation is a source-repo branch and pull request. Never a
  direct edit of the deployed tree, never an auto-merge. A schedule change carries current and
  proposed schedule, timezone and catch-up behaviour, the unit and manifest diff, and the schedule,
  manifest, deploy and drift checks. A retirement carries the removal across manifests, units,
  runners, profiles and contracts, route and producer joins and deploy exclusions, **a residue
  report derived from the W19 failure class**, and an explicit artifact-retention decision.
  Gate: the exact diff is previewed before the PR exists; no action mutates live workflow truth
  directly; the PR carries test evidence and names any Dave-only cleanup; retirement **fails closed**
  while any executable or deployed residue remains.
- **T5.3c** [Claude, S, T5.3] **Route actionable incidents to Buzz.** One dedicated stream, and it
  is an exception channel — not a heartbeat, not an activity feed. `bin/deliver.sh` and
  `bin/buzz_routes.env` stay the transport and routing owners; systemd stays the scheduler and Buzz
  scheduled workflows are not used. Send immediately only when Dave must act: incomplete run, failed
  assertion, stale or missing artifact, blocked next action, control failure. One daily digest of
  what is still unresolved. Deduplicate repeated observations of one incident and emit a recovery
  update when it closes. Each message names workflow, agent, failure, time, required action, and
  links to the incident and its evidence.
  Gate: healthy runs and valid no-output outcomes stay **silent**; a persistent incident does not
  produce repeated immediate alerts; the digest holds only unresolved ones; recovery is visible; and
  **a delivery failure cannot make the originating workflow fail**.
- **T5.3d** [Claude, M, T5.3, T5.1] **Agent handoff traces.** Capture agent-to-agent handoffs as
  structured run events and render them as a timeline in the run detail page: parent run/request id,
  requesting and receiving agent, Buzz event or pointer where safe, sent/accepted/replied timestamps,
  outcome, resulting artifact, terminal failure or timeout. Store metadata and bounded summaries,
  **not** full private prompts.
  Gate: a multi-agent run preserves parent/child causality across at least one Marcus → Trajan
  handoff; the timeline distinguishes requested, accepted, working, replied, failed and timed-out;
  each terminal handoff links to its artifact or explicit failure evidence; the view works without
  opening Buzz Desktop; missing telemetry shows as `Unknown` and is never reconstructed from
  guesswork.
- **T5.4** [Claude, M, T5.2] Proof on real runs: one full week with every declared check of
  every contract executed against real runs; the pass matrix recorded in the brief.
  Reviewed requirement — **passing assertions prove delivery, not value.** Add a consumption and
  benefit review that forces one decision per logical workflow: **Keep** (reliable current artifact
  and visible consumption or risk reduction), **Improve** (benefit plausible, reliability or
  actionability or evidence incomplete), **Retire** (obsolete, duplicate, chronically unconsumed, or
  recurring cost with no named action). Review `memory-consolidation`, `buzz-pr-watch`, the two
  spent NeKoVri entries and the two-trigger augustus-content design explicitly. Do not invent
  financial ROI; benefit stays `Unknown` until baselined. Phase 6 cleanup executes from these
  decisions, not from age or intuition.
  Confirmed consumption interpretation (wave two): opened, approved, sent/published and manually
  marked useful are **four distinct observations**. Opening is not approval and approval is not
  downstream use. Reliability, output use and cost are the three benefit dimensions.
  Gate: matrix complete with no check skipped, and 30 logical standing workflows each carry
  Keep/Improve/Retire on reliability, cost and the four distinct use signals, with evidence and an
  owner for the resulting action.

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
  runner scripts and clears eleven deferred exclusions in one act. Dave picks the moment and
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

### Phase 7 — Live breakage, found 2026-09-10 by the /verify sweep

Neither item is on the Notion page. Both are in the class Phase 5 exists to catch, and both are
losing artifacts today.

- **T7.1** [Claude, S] `bin/proposal_or_decline.sh` fails open across jobs. It greps the last 40
  lines of the **shared** `agent_run.log` for `^DECLINE:` with no job identity, so any job's
  decline satisfies any other job's verify. Proved with a fixture: `proposal_or_decline.sh
  bd-followup-drafts` exits 0 on a sentinel written by `bd-stall-radar`. It happened live — the
  2026-09-09 23:31 bd-followup-drafts run wrote no proposal, printed only `skip: today's pack
  already exists`, and logged `OK` five log lines after the radar's 23:04 decline.
  `bin/deliver_proposal.sh:31` has the same defect one step narrower, quoting whichever sibling
  declined last as this job's reason. Fix: give the run boundary a name — `agent_propose.sh` keeps
  the attempt's own output at a per-task path and exports it, and both consumers read that instead
  of the shared tail, which removes the wrong-job and wrong-run axes together and deletes the tail
  window rather than tuning it. Gate: a fixture where job A declines and job B is silent fails B.
  **Deliberately excluded** — giving the idempotent skip its own accepted sentinel. Six task
  profiles print `skip: …`, which the checker rejects; `design/contracts/knowledge-digest.md`
  already records that as intended ("a second run in one day is anomalous and should be visible").
  Today the skip passes anyway by borrowing a sibling's decline, so the scoping fix *restores* that
  decision rather than overturning it. The consequence goes live with the fix: a same-day re-run
  goes red, and a canary-then-schedule night costs one red run. Whether that alerting is wanted is
  a policy call for Dave, tracked separately — not something a defect fix should settle.
- **T7.2** [Claude, M] `augustus-content.service` failed 3 of the last 5 nights — 2026-09-06,
  09-07 and 09-09 (UTC; the last is the 09-10 01:33 CEST run) — every time on
  `run_content_via_buzz: no board movement and no reply within 1200s — recording FAIL`, 20 minutes
  burnt per failure. The corpus gate armed and the trigger published on each; augustus simply never
  moved the board. On the two nights it worked he replied in under three minutes, so this is not a
  slow turn. Diagnose along the CLAUDE.md path — the event's `p` tags first, then channel
  membership, then the unit's cgroup — never by asking the agent. Then correlate board transition,
  agent reply, event receipt and timeout under **one run id**, and test the nightly and
  change-trigger paths as two triggers of one workflow.
  Reviewed acceptance: the root cause is **evidenced, not inferred from journal silence** (CLAUDE.md
  § Debugging: absence of logs is not absence of work); the workflow produces a content-board
  transition plus a draft, or an owned DECLINE; missing board movement and missing reply each fail
  by a **named assertion**; three consecutive eligible runs reach a valid terminal outcome.
  Gate: the cause named, and either fixed or recorded as a `DECIDED` with the timeout re-based on
  measured successful turn length.

## Execution order for Claude

Order as of **2026-09-10**, after the 09-10 batch (T3.1, T4.0, T4.1, T4.2, T4.3, T7.1) landed and
the two 2026-09-10 review waves rewrote the board. Status for every row lives in the Notion
tracker; this section is the sequence for what is left.

**The gate is green and, since `063e6ce`, the green means more than it did this morning.**
`bash bin/verify.sh` exits 0: zero FAIL lines, zero `contract-exists` PROBLEM lines, drift clean,
one declared skip. Every standing unit has a contract, every contract's checks are executable, and
every `## Outputs` now names a beneficiary, a next actor, a next action, a benefit hypothesis and a
benefit signal. Until that commit the gate asserted that a contract named an artifact, a path, a
freshness requirement and a legitimate decline, and asserted nothing whatever about whether the
artifact was for anyone — twelve contracts were green and not one of them named a beneficiary. So
the ordering principle held: Phase 4 no longer exists to turn the gate green, it exists to make the
green mean something, and eight of the twelve answering `Unknown` for the benefit signal is that
phase reporting rather than failing.

**The actionability fields landed 2026-09-10 (`063e6ce`)** — defined once in
`design/contract-schema.md`, enforced as `outputs-actionability`, and present in all twelve
contracts. **T4.4 landed 2026-09-11 (`96c9019`)**: twenty-six contracts on disk, every standing
manifest entry names one or carries `contract_exempt`. **Next: T4.5.**

**T4.5 stays last, and its field definition goes first.** The temptation is to put T4.5 at the head
of the phase because it is the enforcement point — but T4.5 flips the `contract` field from
"resolves if present" to "present and resolves", and Trajan's fourteen platform entries do not name
a contract yet. Enforcing before T4.4 lands would hold the gate red across several sessions, which
is the one thing this repo's loop does not allow. Split it instead: the *shape* is defined up front
in `design/contract-schema.md`, everything is written to that shape, and the validator turns
mandatory only once nothing violates it.

**Steps 1 and 2 are done** (`063e6ce`): the fields were defined once in the schema doc and
backfilled into all twelve contracts, and the validator rule turned mandatory in the same commit
because nothing violated it. T4.1 and T4.2 closed; T4.3 keeps one assertion, named in its row.

1. ~~**T4.4**~~ — done `96c9019`: Trajan's fourteen platform jobs, written once, to the finished
   shape.
2. **T4.5** — now the flip is safe: both rules turn mandatory over a tree that already complies, so
   the gate stays green through the change instead of going red and waiting to be caught up with.
3. **T5.1**, then **T5.2**. The receipt is the artifact every downstream view reads; nothing in
   Phase 5 can be built ahead of it. T5.2's own trap is stated in its row: an always-on service has
   no timer cadence to hang a receipt off.
4. **T5.3** — the Control Room, read-only. It is the only place the 30-vs-31 reconciliation becomes
   visible to Dave rather than to a test, and every card below it renders into it.
5. **T5.3c** next among the sub-cards, not last: it is the S, it rides the delivery mechanism that
   already exists, and an exception stream is worth having before the browser is finished. Then
   **T5.3a** (controls), then **T5.3b** (schedule/retirement PRs). **T5.3d** trails — it needs the
   handoff fields T5.1 is asked to carry and there is no second agent in a scheduled path today.
6. **T5.4**. Its Keep/Improve/Retire decisions need a full week of receipts behind them, so it
   genuinely trails T5.2 rather than merely being sequenced after it.
7. **T7.2**, in parallel with any of the above — `augustus-content.service` is still failing most
   nights and every failed night is 20 minutes burnt. It is not blocked on anything; it is here
   rather than at the top only because T4.3's contract now gives it named checks to diagnose
   against.
8. **T3.3**, unblocked since T3.2 landed 2026-09-11.
9. **T6.1**, alongside any of the above; nothing depends on it.
10. **T0.3** — S, and it closes W20 either way.
11. **T6.3** when Dave says.

Startable today with no blocker: T4.4, T7.2, T3.3, T6.1, T0.3. Everything else
waits on one of those or on a Dave item.

Dave's queue, unchanged by this sweep: D2, D3, D4, D5, D6, L1, T6.3. D1 closed with T2.4; D7 and
L2 are closed.
