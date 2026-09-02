# D3 — Eval spec: how we know a workflow works

**Status:** design, 2026-09-01. Third and last design session before Phase B.
D1 (`design/workflow-registry.md`) froze *which workflows exist and who owns them*.
D2 (`design/agent-model.md` + `design/agents/*.toml`) froze *what each agent may do, per
surface*. D3 freezes *what proves a workflow works* — and therefore what a Phase-B brief
must be green against before it lands.

---

## 1. The finding this document exists for

**The box has five independent eval layers and 42 executed suites, and none of them knows
the workflow list.** Every layer is organised by *mechanism* — scripts, delivery receipts,
retrieval probes, model tiers, turn liveness. None is organised by *workflow*. So coverage
is not a property anyone chose; it is an accident of which mechanism a given workflow
happens to touch.

Measured, and **corrected 2026-09-01 under D6**: **16 of the 26 workflows in the D2 manifests
have an owning suite; 10 do not.** The figure first recorded here — "9 of 26, four absent from
`tests/` entirely" — was wrong, and wrong in a way worth keeping visible: it came from
eyeballing suite filenames against unit names, which is one of four plausible join rules that
each yield a different number (D6 measures all four). Six workflows §5 called uncovered are
covered, three by a suite named for the *implementation script* rather than the unit
(`qmd-refresh` -> `test_vault_sync_guard.sh`, `memory-consolidation` ->
`test_consolidate_memory.sh`, `inbox-backlog-alert` -> `test_buzz_adapters.sh`), and
`agent-inbox-sync` by a suite three hops down its call chain.

Nothing on the box reports that number, because computing it needs a list of all workflows
and until D2 no such list existed. `fleet_eval.sh --no-coverage` sounds like the missing
check and is not: its "coverage" is *delivery* coverage — did every expected timer fire
land a receipt — delegated to `audit_buzz_dual_run.sh` (`fleet_eval_behaviour.py:204`).
That answers "did the sends arrive", never "is this workflow tested at all".

This is the same shape as the reporting defect already recorded in the fleet notes: **a
check that cannot fail is not a check.** A suite that runs `tests/*.sh` grades whatever
tests happen to exist and is structurally incapable of noticing an absent one. The D2
manifests are the fix — they are the first artifact on this box that enumerates all 26
workflows, so for the first time coverage is *computable*.

---

## 2. The five layers that already exist

| # | Layer | Entry point | Cadence | Gates on | Evidence |
|---|---|---|---|---|---|
| L1 | Static + unit | `bin/verify.sh` | on demand (pre-commit) | exit code | `bash -n`, `shellcheck -S error`, **42 executed `tests/*.sh`** |
| L2 | Behavioural conformance | `bin/fleet_eval_behaviour.py` | daily 07:07 | regression vs baseline | delivery receipts vs the **deployed** route table |
| L3 | Grounding | `bin/fleet_eval_grounding.py` | daily 07:07 | regression vs baseline | qmd retrieval against `fleet_eval_probes.json` |
| L4 | Local model tier | `bin/local_tier_eval.sh` (+ `_score`/`_report`/`_trend`) | 6×/day | scored trend | on-box model output |
| L5 | Turn liveness | `fleet-turn-check` | hourly | can an agent complete a turn | live Buzz round trip |

Machine-level siblings outside this repo: `~/.config/buzz-team/verify-fleet.sh` (fleet
state) and `~/.config/buzz-agents/check-loaded.sh` (config actually loaded). They gate the
`buzz-agent@*` units, not the workflows, and are governed by `~/CLAUDE.md`.

`bin/verify.sh` is the **only** layer that is a gate in the blocking sense. L2/L3 exit 1 on
regression but `fleet-eval.service` carries **no** `OnFailure=agent-alert@%n.service`,
deliberately: "a failing eval is a report to read, not an incident" — it posts to `#ops`
via `--deliver` instead.

---

## 3. The doctrine is already written — extract it, don't reinvent it

The strongest eval thinking on this box is in the headers of `fleet_eval.sh` and
`fleet_eval_behaviour.py`. D3 adopts it verbatim as the standard for every new suite.

**R1 — Gate on regression, not on state.** Probes carry the verdict measured when they
were added; only a fall below that verdict fails. Two grounding probes are red today and
are *known* to be red for a cause the box cannot fix (it holds no canonical vault
credential). *Why:* "a suite that goes red on day one for a condition already accepted gets
muted within a week, and a muted suite detects nothing."

**R2 — Improving a baseline is a deliberate fixture edit, never something a scheduled job
does to its own pass mark.** An improvement is reported; the baseline is left alone.

**R3 — Measure against evidence, not config.** Two existing gates prove `TEAM.md` and the
route table agree, and that every expected fire produced a receipt. Neither reads what a
delivery *actually carried*, so "a producer can hand-roll a send that contradicts a route
table both gates certify as correct." Start from the artifact.

**R4 — Grade traffic against the config it was produced under.** L2 reads the *deployed*
route table on purpose, because receipts were written by the deployed `deliver.sh`.
Checking them against an edited source copy "would grade yesterday's traffic against
today's intent." Source-vs-deployed drift is a *separate* assertion.

**R5 — One problem, one red light.** Delivery coverage is reported but not gated in L2,
because `audit_buzz_dual_run.sh` already owns it: "failing this suite on the same condition
gives one problem two red lights and no new information."

**R6 — A missing field is not a mismatch.** Receipts predating a schema change are counted
`legacy`, not `failed`, and the window ages them out.

**R7 — Never end a pipeline in an early-exiting reader while `pipefail` is on.** Documented
in the repo `CLAUDE.md`: it inverts twice, so a true assertion fails and a negated one
passes without reading anything. Every suite carries `yes | grep -q y` as a canary.

---

## 4. Rules D3 adds, each from a defect that actually shipped

R1–R7 come from code. R8–R14 come from field failures recorded in the fleet notes and in
D1/D2. Each is stated as a requirement on a suite.

**R8 — Assert the artifact, never the exit code.** A run's exit status describes the
harness, not the work. `proposal_or_decline.sh` exists because a dead run once logged as a
clean NOPROPOSAL. *Test:* would this assertion still pass if the job produced nothing?

**R9 — Assert *which* branch passed, not merely that something passed.** A fixture that
imitates a producer proves nothing about the producer. Fixtures come from the producer.

**R10 — A bounded window must state its boundary, and the boundary must be able to contain
the failure.** "Zero commits since 00:00 today" dressed an eight-day outage as a five-hour
lag. A window whose span is shorter than the fault it is meant to catch is decorative.

**R11 — Presence is not freshness; a level is not a delta.** `tail -N` renders an
eight-day-dead log identically to a live one. Assert the age of the newest record against
the schedule that should have produced it, and report the change, not the value.

**R12 — Ask the system what is wrong; never ask a whitelist whether it is fine.** A
four-item health whitelist that never runs `systemctl --failed` left a failed unit unnamed
for eight days, twice daily. Enumerate from the system (`systemctl list-units --failed`,
`list-timers`), never from a hand-maintained roster — a coverage list kept in N places
disagrees in N ways.

**R13 — Verify a fix on a day its failing case can occur.** A defect that is correct by
coincidence five days in seven survives every verification scheduled on the other two.

**R14 — Prove absence only after proving the path exists.** `grep -c` on a missing file
returns a clean `0`. Assert the input exists before asserting what it does not contain.

---

## 5. Coverage — computed, not recorded (D6, 2026-09-02)

**The headline count lives in `tests/test_workflow_coverage.sh`'s output, not in this
paragraph.** Run `bash tests/test_workflow_coverage.sh` for the current figure; the gate
runs it on every commit. A number written here was wrong three ways in one document
(`open-decisions.md:548-551`) before anything computed it, and the checker exists precisely
so this section stops rotting the day it is written.

The table below stays, because it carries the *why* — which no checker computes. Each row
says whether a gap is a hole worth a brief or a bounded thing that needs no suite, and that
judgement is the part a coverage figure cannot express.

| Workflow | Owner | Status | Why uncovered |
|---|---|---|---|
| `overnight-morning-report` | marcus | standing | **real hole — highest value.** Carries the whole recurring reporting-defect class. |
| `m1-signal-scan` | claudius | standing | **real hole.** `bin/run_m1_signal_scan_cc.sh` is in-repo and writable. |
| `agent-workforce-auto-sync` | trajan | standing | **real hole.** `bin/auto-sync` is in-repo. Appears in `test_local_tier_eval_score.sh` only as a `list-timers` *fixture string*. |
| `overnight-pre-snapshot` | trajan | standing | **real hole.** `bin/overnight_pre_snapshot.sh` is in-repo. |
| `fleet-turn-check` | trajan | standing | exempt — `~/.config/buzz-team/fleet-turn-check.sh`, outside this repo |
| `ttm-pool-drain` | trajan | standing | exempt — `/usr/local/bin/ttm-pool-drain`, root-owned, outside this repo |
| `buzz-pr-watch` | trajan | standing | exempt — `--user` unit running `~/.local/bin/buzz-pr-watch`, outside this repo |
| `praetorium-content-strategy-research` | augustus | campaign | bounded, `expires` 2026-09-03 — needs no standing suite |
| `praetorium-faceless-content-research` | augustus | campaign | bounded, `expires` 2026-09-04 — needs no standing suite |
| `bd-stall-radar` | claudius | dormant | installed but disabled; its sibling `bd-followup-drafts` has a suite |

So the honest backlog is **four suites** — not fifteen, and not the two this section previously
concluded. Every other gap is bounded, disabled, or code this repo does not own. Those four
are what `tests/test_workflow_coverage.sh` ships red naming; it is not passing until each
has a suite, and `suite_exempt` is not the way to close one — it means the code is not in
this repo, and all four are in-repo and writable.

Two qualifications, both load-bearing:

- **"No owning suite" is not "untested."** Several uncovered workflows are touched obliquely by
  five or more suites. What they lack is a suite that fails when *they* break.
- **The reverse direction has one live case.** `tests/test_content_inbox_finalize.sh` tests
  `bin/content_inbox_finalize.py`, whose unit was removed 2026-09-01 (`systemd/archive/`,
  nothing in `/etc`). The script is exec'd by nothing, and its only other mention in `bin/` is a
  comment at `notion_rest.py:241` calling it *"the retired"* path. It still runs green in the
  gate. Detecting this needs **reachability**, not suite-name matching — see D6.

**R15 — every workflow entry must carry an explicit `status`.** DONE 2026-09-01 (`3a52d42`):
all 26 entries carry one, validated under `tomllib`. Extended by **R15b — every entry must also
carry `suite = [...]`**, hand-declared, plus `suite_exempt = "<reason>"` where the code is not
in this repo (`6e4fb34`). Both are manifest changes, not code changes; the checker that consumes
them is the first Phase-B brief.

---

## 6. The Phase-B gate

A Phase-B brief is done when **all** of the following hold. "Impacted suites" is now
definable because the manifests exist.

1. `bash bin/verify.sh` exits 0 — lint plus all 43 suites.
2. Every workflow the change touches has a suite that **owns** it and asserts its
   contract's `## Acceptance checks` (per `design/contract-schema.md`).
3. The suite obeys R1–R14. The two that catch the most defects here: **R8** (assert the
   artifact) and **R12** (enumerate from the system).
4. For a change to a *unit file*: repo and `/etc` are diffed **in both directions** before
   and after (D2 §6.3 — the repo is behind `/etc` in three places today), and the service
   is run **once, live, with its output read**. `active` + `enabled` + a correct next
   elapse prove nothing about whether `ExecStart` exists.
5. For a change to code the runtime execs: `bin/deploy` has run. Nothing deploys
   automatically; a runner that exists only in source makes its unit structurally incapable
   of producing anything.
6. If the change alters delivery, L2's baseline is re-read but **not** re-baselined in the
   same commit (R2).

Gate ownership by surface, from D2:

| Surface | Blocking gate | Reporting layers |
|---|---|---|
| S1 Buzz interactive | `verify-fleet.sh`, `check-loaded.sh` | L5 |
| S2 Scheduled headless CC | `bin/verify.sh` | L2, L3 |
| S3 Hermes kanban | `bin/verify.sh` | — (none; see §7) |
| S4 Buzz-dispatched scheduled | `bin/verify.sh` | L2, L5 |

### Suite ownership has two valid owners, not one

D6's join runs workflow → suite: every registry entry hand-declares the suites that own it
(`suite = [...]`, R15b), and the coverage checker of §7.1 reads that join in both
directions — an unowned workflow is red, and so is a suite no workflow claims.

**A suite can also be owned by the fleet rather than by a workflow.** Those are declared in
`design/fleet-suites.toml`, one `[[suite]]` table per file, carrying `owner = "fleet"`
alongside `path` and the `asserts` list. `owner = "fleet"` is the second value the §7.1
checker must accept as ownership.

This is not a formality. `tests/test_fleet_guards.sh` asserts the guards on the agents
themselves — a settings deny, a git hook, an absent slug, a namespace without a credential.
Nothing schedules it, so no registry entry can ever claim it, and a checker that knows only
the workflow→suite direction would classify the security suite as an orphan and recommend
deleting it. The declaration exists so that recommendation cannot be made.

---

## 7. Gaps

**7.1 Nothing computes workflow coverage — CLOSED 2026-09-02.** §1. Fixed by
`tests/test_workflow_coverage.sh`, which reads `design/agents/*.toml`, resolves each
`status = "standing"` workflow to a suite, and fails on an unowned one. It is the only new
mechanism D3 asks for, and it makes §5 self-maintaining instead of a number that rots the
day it is written.

**The filter is `standing`, not `live`.** This sentence read `status = "live"` until
2026-09-02, and no workflow entry has ever had that value: `live | read-only | retired` is
the *agent-level* vocabulary (`agent-model.md:106`), deliberately different words so a grep
for one never matches the other (`agent-model.md:187-188`). Workflow status is
`standing | campaign | spent | dormant | planned`. An implementer following the old sentence
literally selects **zero** entries and reports full coverage, which is why the checker
refuses a figure computed from an empty selection.

It must read `design/fleet-suites.toml` as a second source of ownership and treat
`owner = "fleet"` as owned (§6). A checker that knows only the workflow→suite direction
reports `tests/test_fleet_guards.sh` as an orphan, and an orphan's recommended fix is
deletion — so the first act of the coverage checker would be to propose deleting the suite
that asserts the fleet's security guards.

**7.2 The Hermes kanban surface has no eval at all.** L2–L5 cover Buzz and the scheduled
jobs. Nothing grades a kanban card's execution. This may be correct to leave — D2 §8.4
already asks whether the S3 investment should be retired — but it should be a decision,
not an omission.

**7.3 L1 grades the source tree; every other layer grades the deployed one.** `verify.sh`
runs from the repo, L2 reads deployed config by design (R4). So a green `verify.sh` says
nothing about what is running, and this has already produced two live outages (D2 §6.2
alert throttle, §6.3 unit drift). Source-vs-deployed drift deserves its own assertion in
L1 rather than living as a rule people are asked to remember.

**7.4 No eval asserts a `must_not` rule — CLOSED 2026-09-01 (D1 + D9).** The manifests
carry 22 of them, `enforced = true` on only a subset. An unenforced `must_not` is prose,
and prose is what D2 §6.1 found sitting between the fleet and a live `send_message` tool.

`tests/test_fleet_guards.sh` now asserts every `enforced = true` rule, and each rule names
the assertion that covers it in a `test = "<file>::<assertion-id>"` field. The suite's last
group closes the loop in the other direction: it reads the manifests, and fails if a rule
is flagged enforced while naming no assertion, or naming one that is not in the file it
names. `enforced = true` is therefore no longer a string anyone can type.

**D9 redefines the flag to make that checkable: `enforced = true` iff a machine-checkable
artifact exists whose removal or absence a test can detect.** Not "a mechanism blocks it"
in the abstract — a mechanism nobody can point a test at is indistinguishable from prose,
which is the defect this gap was opened for. Two consequences worth stating:

- **A rule can be enforced by different mechanisms on different agents, and the `why` must
  name the right one.** marcus and claudius are covered by the strict settings file;
  augustus is covered by running a harness that never had the connectors, and the settings
  file never reaches him. Crediting the settings file for augustus would be the exact
  §2/§6.1 defect D3 found — a real boundary attributed to the wrong thing, which then
  survives the removal of the thing that actually holds it.
- **A rule whose mechanism is the non-existence of a surface gets `test_exempt`, not a
  test.** Same shape as R15b's `suite_exempt`: an exemption is a declared hole that greps,
  and silence is not. trajan's hermes-cron rule is the one instance — the cron list is
  empty because the surface is retired, so there is nothing whose removal a test could
  detect, and a test pinning it empty would go red the day D7 finishes the retirement.

Negative tests here **assert the absence of capability and never attempt the forbidden
action.** You cannot test "must not send email" by sending email — the test would be the
violation, and a "safe" recipient is still an outward action from a box whose whole charter
is that it performs none. Every assertion reads the state of a mechanism instead.

---

## 8. Decisions required from Dave

1. **Build the coverage checker (7.1) as the first Phase-B item?** Recommended yes — it is
   small, and every later brief gets graded by it. It needs R15 first.
2. **Leave S3/kanban unevaluated (7.2)?** Recommended yes for now, folded into the D2 §8.4
   skills-posture decision rather than answered separately.
3. **Add a source-vs-deployed drift assertion to `verify.sh` (7.3)?** Recommended yes.
   Two of D2's eight gaps were this defect; it is the highest-yield single check available.
4. **Negative tests for `enforced = true` must-nots (7.4)?** ANSWERED yes — done
   2026-09-01 as D1, and wider than the original recommendation. Scoping to the outward
   rules was the wrong shape: the flag itself was the unchecked thing, so the suite covers
   all six enforced rules and adds the reverse-direction check that a flag with no
   assertion is red. D9 supplies the definition that makes the reverse check possible
   (§7.4).
