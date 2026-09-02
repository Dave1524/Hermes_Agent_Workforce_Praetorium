# Workflow registry — ownership freeze (D1)

**Status: FROZEN 2026-09-01** — all eight decisions in §7 are closed (Dave's ALL-CAPS
answers to §7.1–7.5/§7.8 in commit `ed568f8`; §7.6 and §7.7 discussed and closed the
same day). Every action below is executed, not proposed. Timer coverage was verified
by enumerating live timers from systemd (system + user scope) and diffing against this
file: **every box-owned timer is accounted for here**; the only unlisted timers are OS
ones (apport, launchpadlib, xfs_scrub, sysstat…). D2 starts from this table.
Once confirmed, this file is the single source of truth for **which workflows exist
and who is accountable for each** — build-order step 1 of the approved infrastructure
review (Notion: "Proposal — Praetorium agent infrastructure review", decision section
2026-08-31). Per-workflow contracts (input schema, sources, output schema, decline
conditions, side effects, acceptance checks) are deliberately NOT here — they are D2,
one file each under `design/contracts/` once the schema exists.

Derived live 2026-09-01 from: `systemctl list-timers --all` (system + user scope),
`systemctl cat <unit>` for every workflow unit, `profiles/*.md` headers,
`hermes cron list` (empty), `hermes kanban boards list`, and `buzz-agent@*` unit state.
**Two of those inputs no longer exist**: S3 was retired 2026-09-02 (§5), so a
re-derivation drops the two `hermes` commands and gains nothing — they contributed only
the surface §5 now records as retired.

## Ownership model (proposed)

- **Persona workflow** — output is LLM judgment. Names exactly one accountable persona,
  even when the executor is headless Claude Code on a different model tier
  (decision doc amendment 7). The persona answers for output quality in eval reviews.
- **Platform job** — deterministic script; no persona. Accountable to the platform
  owner: **trajan** (decided 2026-09-01, §7.1).

## 1. Interactive layer (always-on, Buzz)

| Agent | Harness | Standing role |
|---|---|---|
| marcus | claude-agent-acp | Chief of staff; DAG root (~20 channels); dispatch + reporting |
| claudius | claude-agent-acp | Research + BD analysis |
| trajan | claude-agent-acp | Engineering; vpc-seo queue executor |
| augustus | codex-acp (bwrap) | Content editor-in-chief; namespace strips `~/.ssh`, so never owns a workflow needing `git fetch` |
| aurelian | read-only calibration pin | Cold verification only; never a co-author; no scheduled work |

## 2. Scheduled persona workflows (live)

All run headless Claude Code via `bin/agent_propose.sh` + `AGENT_JOB_OVERRIDES`.
"Owner" is accountability, not executor.

| Unit (timer) | Trigger | Model | Profile | Route | Owner (prop.) | Decision (prop.) |
|---|---|---|---|---|---|---|
| praetorium-daily-plan | Mon–Fri 06:01 | (env) | daily_plan_task.md ("You are Marcus") | ops | marcus | keep |
| overnight-morning-report | daily 06:17 | Sonnet | overnight_morning_report_cc_task.md | ops | marcus | keep ¹ |
| praetorium-eod-summary | daily 22:19 | (env) | eod_summary_task.md ("You are Marcus") | ops | marcus | keep |
| weekly-pre-assembly | Fri 22:02 | Sonnet | weekly_pre_assembly_cc_task.md | research | marcus ² | keep |
| knowledge-digest | Sun 09:01 | Opus 5 | knowledge_digest_cc_task.md | research | claudius | keep |
| agent-proposal (standing research) | daily 04:31 | Opus 5 | standing_research_cc_task.md | research | claudius | keep |
| raw-ingest | daily 03:00 | Opus 5 | raw_ingest_cc_task.md | research | claudius | keep |
| m1-signal-scan | daily 05:30 | Sonnet | m1_signal_scan_cc_task.md | signals | claudius | keep |
| praetorium-content-strategy-research | daily 23:00 | Opus 5 | standing_research_content_strategy_task.md | (env) | augustus ³ | keep |
| praetorium-faceless-content-research | daily 01:30 | Opus 5 | standing_research_faceless_content_task.md | (env) | augustus ³ | keep |

¹ The recurring defect class lives here (coverage globs, whitelist health checks —
  memory `readiness-report-phantom-blockers`); merge-candidate with daily-plan later,
  not part of this freeze.
² Historically a claudius task (hermes era); chief-of-staff prep for Dave's weekly
  review. Confirmed marcus 2026-09-01 (§7.2).
³ Proposed claudius (output is research, not drafts); Dave assigned **augustus**
  2026-09-01 (§7.3) — accountability follows the content pipeline; executor stays
  headless CC.

"(env)" = pinned inside the deny-listed `*.env` override; D2 records it from
`agent_propose.sh` run logs, not by reading the env.

**CORRECTION 2026-09-01 (D2, `design/agent-model.md` §6.8).** The Trigger column above was
read from `list-timers` next-elapse values, which fold in `RandomizedDelaySec` and show only
the next occurrence. Three rows are wrong on the **day**, not just the minute:
`agent-proposal` is **Mon–Fri** 04:30 (not daily), `raw-ingest` is **Tue–Sat** 03:00 (not
daily), and `m1-signal-scan` is **Mon,Wed** 05:30 — twice weekly, not daily. The declared
values are in `design/agents/*.toml`. Read a schedule from `systemctl cat`, never from
`list-timers`. Ownership decisions are unaffected.

**CORRECTION 2026-09-01 (D2 §6.5).** `praetorium-content-strategy-research` and
`praetorium-faceless-content-research` are **not** daily timers, and they are **not standing
workflows at all**. Each carries four absolute `OnCalendar` dates — last 2026-09-03 23:00 and
2026-09-04 01:30 — because each is a **bounded research campaign** on one named topic,
authorised by Dave for six nights on 2026-08-14 and rescheduled for four make-up nights after
the 2026-08-27 OAuth outage. Expiry is the design, not a defect: leave them alone.
An earlier draft of §6.5 called this a silent failure and proposed converting both to
recurring calendars — that would have created two permanent nightly Opus jobs nobody asked
for. Both also exist only in `/etc` with no source in `systemd/` (§6.7), which stands.
Registry treatment: these are campaigns, not rows in the standing-workflow table.

## 3. Scheduled platform jobs (live, deterministic)

| Unit | Trigger | What | Route |
|---|---|---|---|
| fleet-turn-check | hourly | fleet can complete a real turn | — |
| fleet-eval | daily 07:07 | delivery conformance + vault grounding regression | — |
| local-tier-eval | recurring (~6h) | Ollama capability regression | — |
| memory-consolidation | daily 03:30 | working-memory prune, all profiles | — |
| agent-inbox-sync | 30 min | Notion↔agent-inbox reconcile | — |
| inbox-backlog-alert | daily 06:22 | approvals aging >2d | approvals |
| scorecard | Mon 07:01 | weekly agent-run rollup | ops |
| qmd-refresh | 30 min | vault pull + re-index + embed | — |
| agent-workforce-auto-sync | 15 min | git auto-commit/push of source repo | — |
| ttm-pool-drain | 2 min | GPU page-pool drain | — |
| buzz-pr-watch (user) | daily | watch block/buzz#3816, announce on close | — |

**ADDITION 2026-09-01 (D2).** `overnight-pre-snapshot` (daily 04:25 +2min) is live and
belongs in this table; it was named above only in a §4 row about an archived prompt file.
Platform job, owner trajan per §7.1, recorded in `design/agents/trajan.toml`. Also note
`fleet-turn-check` and `ttm-pool-drain` have no source unit in `systemd/` (§6.7).

## 4. Paused, dead, or dormant — every row needs a call

| Item | State | Proposed decision |
|---|---|---|
| augustus-content.timer | RE-ENABLED 2026-09-01 08:15; Persistent=true fired an immediate catch-up run (healthy at launch) | done — owner augustus (§7.4) |
| content-change-dispatch.timer | RE-ENABLED 2026-09-01 08:15; first poll tick clean (0 Picked, exit 0) | done (§7.4) |
| content-inbox-finalize.{service,timer} | spent one-shot: absolute `OnCalendar=2026-08-15 22:00`, fired 08-15 22:00:29, **no next elapse** | REMOVED 2026-09-01 (disabled, /etc files deleted, units → `systemd/archive/`) |
| holiday-content-reminder (user) | spent one-shot: `OnCalendar=2026-08-31 09:00`, fired 08-31 09:00:12, no next elapse | REMOVED 2026-09-01 (user unit; text preserved in `systemd/archive/`) |
| marcus-morning-summary (user) | spent one-shot Dave requested for 2026-08-26 08:00, fired, no next elapse — **not** a competing recurring summary (an earlier note here said otherwise) | REMOVED 2026-09-01 (user unit; text preserved in `systemd/archive/`) |
| profiles/bd_stall_radar_task.md | no scheduler; kernel built, never wired | DECIDED: wire to timer, owner claudius — Phase B brief (§7.5) |
| profiles/bd_followup_drafts_cc_task.md | no scheduler | DECIDED: wire to timer, owner claudius — Phase B brief (§7.5) |
| profiles/augustus_polish_task.md | hand-dispatched only, by design | KEPT as manual runbook (§7.7) |
| profiles/{claudius,overnight_morning_report,weekly_pre_assembly,m1_signal_scan}_task.md | hermes-era variants, superseded by `_cc_task.md`. Proven unused before moving: each live unit's journal logs its effective runtime (`run attempt N/M: …`) and all four exec `bin/run_*_cc.sh`, which hardcode the `_cc_task.md` paths | ARCHIVED 2026-09-01 → `profiles/archive/` |
| profiles/cron-overnight-pre-snapshot.prompt.md | hermes cron is empty. `overnight-pre-snapshot.service` is live (daily 04:26) but references this file only in a **comment** ("Replaces the Hermes cron LLM checklist"), not an ExecStart | ARCHIVED 2026-09-01 → `profiles/archive/` |
| profiles/linkedin_shape.md | reference for bin/linkedin_shape.py, not a workflow | KEPT as reference (§7.7) |

## 5. Other dispatch surfaces

**Read this section's first two bullets in order. They record two decisions one day
apart, and the second reverses the first.** On 2026-09-01 §7.6 adopted "recurring work =
systemd timers, queued one-offs = kanban, vpc-seo stays". On 2026-09-02 D7 concluded
**retire the whole surface**, and brief 5 executed it. Both are recorded, dated, in that
order — a reader who stops at the first bullet gets the opposite instruction, which is
why neither was deleted (`open-decisions.md:16-18`).

- **hermes cron** — empty ("No scheduled jobs"); everything migrated to systemd.
  **RETIRED (§7.6)** — nothing may be scheduled here again. Its host, `hermes-gateway`,
  was disabled and stopped 2026-09-02, so this is now enforced by the absence of a
  scheduler rather than by convention. trajan's `must_not` rule against it was removed the
  same day: a prohibition whose only mechanism is the non-existence of a surface is moot,
  not standing (`eval-spec.md` §8 decision 2).
- **hermes kanban — RETIRED 2026-09-02 (D7).** The gateway no longer dispatches anything;
  it is `inactive` + `disabled`, with the unit file kept on disk for one review cycle. The
  board is archived content-free to `design/archive/hermes-kanban-board.md`; the full
  export is at `~/OUTBOX/hermes-kanban-full-export-2026-09-02.md`, outside every repo
  because this one is public. `bin/kanban_run_and_wait.sh` and both its suites are deleted.

  What the 2026-09-01 rule said, and what happened to each part:
  - ~~`vpc-seo` stays as **trajan's** one-off queue.~~ **Superseded 2026-09-02.** The queue
    moved to Notion; Dave moved the 5 cards before the retirement. The finding that
    prompted the rule stands and is the reason it did not survive: those cards were
    assigned to `engineer`, a profile **not on disk** (`kanban assignees` → `engineer / no`),
    so they could never have dispatched — measured 2026-09-02, **none of the 5 has a
    `started_at`, ever.** Reassigning them to trajan on 09-01 fixed the routing but not the
    surface, and a queue that has never once dispatched a card in 54 days is not a queue.
  - 33 stale blocked nightly `content pitch+draft` / `box-brief run` cards archived
    2026-09-01 (reversible; `archive`, not `--rm`). Root cause worth recording: those cards
    were generated by the old `kanban_run_and_wait.sh` wiring in
    `config/job-overrides/augustus-content.env.example`; the live job moved to
    `run_content_via_buzz.sh`, so nothing consumed them and they piled up. They are the
    residue of inconsistency 5 below, not an independent mess. Nothing was purged then and
    nothing is purged now — retirement stops the surface, it does not destroy its contents.
  - `default` board: 3 stale blocked cards archived. Moot with the rest.
- **Agent Inbox (Notion)** — the approval pipeline (propose → sync → Dave approves on
  Mac → promote). Stays; it is the human gate, not a workflow.
- **Buzz** — interactive dispatch; stays the human-facing control plane per the
  decision doc.

## 6. Known inconsistencies this freeze must resolve

1. **Deploy-path split.** `agent-inbox-sync` ExecStarts from the SOURCE repo
   (`~/dev/agent-workforce/bin`); every other unit from the deployed copy
   (`~/agent-workforce/bin`). Proposed: deployed copy everywhere except `auto-sync`
   (which must run from source by definition). AGREED 2026-09-01 (§7.8).
2. **AGENT_PROFILE memory keying defect.** Model-named profiles log `memory=no-store`
   (66 runs) while memory-consolidation prunes four frozen persona stores nightly.
   The owner column here is the fix's spec: episodic memory keys on the OWNER
   persona, not the runtime profile name.
   **RESOLVED IN CODE 2026-09-02 (W1, `cc9f802`); NOT YET ON THE BOX.** `AGENT_OWNER`
   keys `MEM_DIR`, `AGENT_PROFILE` keeps keying `cost.log`'s `profile=`. The "66 runs"
   here is a snapshot that has since grown to **77** across six task slugs — a count in
   prose ages, so re-derive it (`grep -c 'memory=no-store' ~/agent-workforce/logs/cost.log`)
   rather than citing this number. The live jobs keep the old keying until the
   `AGENT_OWNER` lines in `docs/runbook.md` § W1 handoff are applied to the deny-listed
   `~/.config/agent-workforce/*.env`.
3. **Persona framing is inconsistent in-prompt.** daily-plan/eod say "You are Marcus";
   the `_cc_task` variants are persona-less. After the freeze, every persona
   workflow's profile states its owner in one standard header line (a D2 manifest
   field).
   **RESOLVED 2026-09-02 (W2, `a2d132e`).** All 12 profile-carrying entries open with
   `Owner: <persona>`, derived from the declaring manifest and asserted by
   `tests/test_fleet_ownership.sh`. The direction is load-bearing: prompt prose gets
   `weekly_pre_assembly_cc_task.md` wrong.
4. **Report input coverage is hand-maintained in N places.** The `praetorium-*` glob
   defect existed in six files. A unit list *generated from this registry* should
   replace every hand-maintained coverage list in the reporting jobs.
   **RESOLVED 2026-09-02 (W3, `d86278a`).** `config/fleet-units.tsv` — a committed
   literal in a tree `bin/deploy` ships, asserted against `design/agents/*.toml` in both
   directions. Not *generated at run time*, deliberately: `design/` is not among
   `bin/deploy`'s eight paths, so a runtime read works in the repo and empties silently
   in `~/agent-workforce/`. Measured coverage of the six it replaced: 8–11 of 23 standing
   units each. One side effect worth expecting — `bin/local_tier_eval.sh`'s t1 fixture
   moves from 7 timers to 21, so eval scores either side of the deploy that ships this
   are **not comparable**; the denominator is visible in t1's own detail string.
5. **Job-override examples live in two homes, and the authoritative-looking one is the
   stale one.** Found 2026-09-01 while closing §7.7. `config/job-overrides/*.env.example`
   — the directory whose README correctly describes the mechanism — held only
   **retired-runtime** examples (`~/.local/bin/hermes -z …`, and
   `kanban_run_and_wait.sh` for augustus-content), while `profiles/*.env.example` carry
   the live headless-Claude-Code wiring. Provisioning a live `.env` from the config
   directory installed a runtime that no longer exists. All four stale files moved to
   `config/job-overrides/archive/` and the README now points at `profiles/`
   (2026-09-01). **Consolidating the two homes into one is D2/Phase-B work and is NOT
   done.** Method note: the live wiring was established without reading any deny-listed
   `~/.config/agent-workforce/*.env` — each unit's journal logs
   `run attempt N/M: <command>`, which is the effective `AGENT_RUNTIME_CMD`.
   **RESOLVED 2026-09-02 (W4, `36f7242`).** One home: `profiles/*.env.example`.
   `config/job-overrides/` keeps `archive/` plus a pointer README. The surviving defect
   was an *instruction* rather than a file — `docs/runbook.md` still ran
   `install -m 600 config/job-overrides/augustus-content.env.example` against a path that
   had existed only under `archive/` since the 2026-09-01 move, so the half-fix recorded
   above left a broken provisioning step reading as authoritative for a day. The new
   assertion targets `install` commands, not prose. **Open:** `augustus-content` and
   `bd-stall-radar` still have no example in either home.
6. **Inconsistency 2 is wider than "66 m1 runs".** Measured 2026-09-01 from journals:
   `m1-signal-scan`, `weekly-pre-assembly`, `overnight-morning-report` and
   `praetorium-daily-plan` all run `profile=claude-sonnet`; `knowledge-digest` and
   `raw-ingest` run `profile=claude-opus`; the `bd_followup_drafts` example ships
   `AGENT_PROFILE=claude-opus`. m1 and knowledge-digest log
   `MEMORY: no per-profile store at /home/dave/.her…` outright. So **no scheduled
   persona workflow currently accumulates episodic memory** — the fix is a fleet-wide
   rename to owner personas, not a one-job patch.
   **PARTLY SUPERSEDED 2026-09-02 (W1).** The conclusion held for the wrong span. Six of
   the ten jobs listed here are fixed by `AGENT_OWNER`; the other four
   (`praetorium-daily-plan`, `praetorium-eod-summary`, `overnight-morning-report`, and
   both campaigns) run `AGENT_RUN_MODE=ops`, which skips the memory path **by design**
   (NUC-36) and logs `na`, not `no-store`. So "no scheduled persona workflow accumulates
   episodic memory" stays true after the fix, for a reason that is deliberate rather than
   defective — and a reader who treats the whole sentence as the bug will go looking for a
   fault in the four jobs that do not have one.

## 7. Decisions required from Dave

1. Platform jobs accountable owner: trajan, or leave Dave-owned? OWNED BY TRAJAN 
2. weekly-pre-assembly owner: marcus (proposed) or claudius (historical)? MARCUS
3. content-strategy + faceless-content research owner: claudius (proposed) or augustus? AUGUSTUS
4. Re-enable augustus-content + content-change-dispatch now that the holiday is over? RE-ENABLE 
5. bd-stall-radar and bd-followup-drafts: wire to timers (owner claudius) or kill? WIRE TO TIMERS
6. Kanban posture: confirm "recurring = systemd, one-offs = kanban, vpc-seo stays"? LETS DISCUSS THIS
   → **CLOSED 2026-09-01.** Rule adopted; hermes cron retired; vpc-seo kept as trajan's
   queue (5 cards reassigned off the non-existent `engineer` profile, left blocked);
   33 + 3 stale cards archived. Detail in §5.
   → **REOPENED AND ANSWERED DIFFERENTLY 2026-09-02 (D7): retire the surface entirely.**
   The 09-01 answer kept a one-off queue on the strength of the routing fix. D7 asked the
   next question — has this queue ever dispatched anything? — and the answer was no: 5 of
   11 cards never started, the last completion was 2026-07-20, and 0 of 11 ever used the
   skills mechanism the surface existed to offer. Executed by brief 5 on 2026-09-02: board
   archived, gateway disabled and stopped, dispatch code and both suites deleted, all five
   `[surfaces.kanban]` manifest blocks marked `retired`.

   **The 24-hour reversal is the point, not an embarrassment.** The 09-01 answer was
   correct about what it measured (the cards could not route) and did not measure whether
   the surface was worth keeping. Both answers stay here, dated and in order, because a
   registry carrying one dated correction is worth more than one carrying a single
   confident number.
7. Confirm the kill/archive list in §4. LETS DISCUSS
   → **CLOSED 2026-09-01**, with two corrections found while verifying rather than
   assuming: (a) all three "kill" units were **spent one-shots with absolute dates and
   no next elapse** — inert clutter, not live risks, and the stated reason for
   marcus-morning-summary ("competing recurring summary") was wrong; (b) two candidates
   needed a live check before removal — `cron-overnight-pre-snapshot.prompt.md` is named
   by a **live** unit (comment only, safe) and the four hermes-era task files are named
   by five `.env.example` files (proven unused via journal runtime lines, safe). Nothing
   was deleted outright: units and prompts are in `systemd/archive/` and
   `profiles/archive/`, kanban cards are `archive`d rather than purged.
8. Confirm the deploy-path convention in §6.1. AGREED

Decision log: §7.1–7.5 and §7.8 answered by Dave 2026-09-01 (ALL-CAPS above, commit
`ed568f8`) and applied the same day, with the content timers re-enabled and verified.
§7.6 and §7.7 discussed and closed 2026-09-01; all their actions are executed. **D1 is
complete** — D2 (contract schema, five agent manifests, per-agent skill/tool profiles)
starts from this table. Two items carried into D2 rather than closed here: consolidating
the job-override example homes (§6.5) and the fleet-wide `AGENT_PROFILE` → owner-persona
rename (§6.6).
