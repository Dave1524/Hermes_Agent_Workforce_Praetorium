# Workflow registry — ownership freeze (D1)

**Status: FROZEN 2026-09-01** — Dave decided §7.1–7.5 and §7.8 (ALL-CAPS answers
recorded in §7, commit `ed568f8`; applied same day). Two exceptions remain OPEN and
under discussion: §7.6 (kanban posture) and §7.7 (kill/archive list) — §4's kill
proposals stand as proposals until §7.7 closes.
Once confirmed, this file is the single source of truth for **which workflows exist
and who is accountable for each** — build-order step 1 of the approved infrastructure
review (Notion: "Proposal — Praetorium agent infrastructure review", decision section
2026-08-31). Per-workflow contracts (input schema, sources, output schema, decline
conditions, side effects, acceptance checks) are deliberately NOT here — they are D2,
one file each under `design/contracts/` once the schema exists.

Derived live 2026-09-01 from: `systemctl list-timers --all` (system + user scope),
`systemctl cat <unit>` for every workflow unit, `profiles/*.md` headers,
`hermes cron list` (empty), `hermes kanban boards list`, and `buzz-agent@*` unit state.

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

## 4. Paused, dead, or dormant — every row needs a call

| Item | State | Proposed decision |
|---|---|---|
| augustus-content.timer | RE-ENABLED 2026-09-01 08:15; Persistent=true fired an immediate catch-up run (healthy at launch) | done — owner augustus (§7.4) |
| content-change-dispatch.timer | RE-ENABLED 2026-09-01 08:15; first poll tick clean (0 Picked, exit 0) | done (§7.4) |
| content-inbox-finalize.{service,timer} | one-shot, completed 2026-08-15 | remove units |
| holiday-content-reminder (user) | fired 2026-08-31, purpose served | remove |
| marcus-morning-summary (user) | disabled; superseded by daily-plan + morning-report | remove |
| profiles/bd_stall_radar_task.md | no scheduler; kernel built, never wired | DECIDED: wire to timer, owner claudius — Phase B brief (§7.5) |
| profiles/bd_followup_drafts_cc_task.md | no scheduler | DECIDED: wire to timer, owner claudius — Phase B brief (§7.5) |
| profiles/augustus_polish_task.md | hand-dispatched only, by design | keep as manual runbook |
| profiles/{claudius,overnight_morning_report,weekly_pre_assembly,m1_signal_scan}_task.md | hermes-era variants, superseded by `_cc_task.md` | move to profiles/archive/ |
| profiles/cron-overnight-pre-snapshot.prompt.md | hermes cron is empty; job gone | move to profiles/archive/ |
| profiles/linkedin_shape.md | reference for bin/linkedin_shape.py, not a workflow | keep, mark as reference |

## 5. Other dispatch surfaces

- **hermes cron** — empty ("No scheduled jobs"); everything migrated to systemd.
  Propose: declared retired; nothing may be scheduled here again.
- **hermes kanban** — gateway auto-dispatches `ready` cards every 60s. `default` board
  is stale. `vpc-seo` mixes a live queue (5 SEO cards assigned `engineer` = trajan)
  with stale blocked nightly content / box-brief leftovers (38 blocked total).
  Propose: vpc-seo stays as trajan's one-off queue; archive the stale nightly cards;
  rule going forward — recurring = systemd, queued one-offs = kanban. → §7.6
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
3. **Persona framing is inconsistent in-prompt.** daily-plan/eod say "You are Marcus";
   the `_cc_task` variants are persona-less. After the freeze, every persona
   workflow's profile states its owner in one standard header line (a D2 manifest
   field).
4. **Report input coverage is hand-maintained in N places.** The `praetorium-*` glob
   defect existed in six files. A unit list *generated from this registry* should
   replace every hand-maintained coverage list in the reporting jobs.

## 7. Decisions required from Dave

1. Platform jobs accountable owner: trajan, or leave Dave-owned? OWNED BY TRAJAN 
2. weekly-pre-assembly owner: marcus (proposed) or claudius (historical)? MARCUS
3. content-strategy + faceless-content research owner: claudius (proposed) or augustus? AUGUSTUS
4. Re-enable augustus-content + content-change-dispatch now that the holiday is over? RE-ENABLE 
5. bd-stall-radar and bd-followup-drafts: wire to timers (owner claudius) or kill? WIRE TO TIMERS
6. Kanban posture: confirm "recurring = systemd, one-offs = kanban, vpc-seo stays"? LETS DISCUSS THIS 
7. Confirm the kill/archive list in §4. LETS DISCUSS 
8. Confirm the deploy-path convention in §6.1. AGREED

Decision log: §7.1–7.5 and §7.8 answered by Dave 2026-09-01 (ALL-CAPS above, commit
`ed568f8`); applied and content timers re-enabled the same day. §7.6 and §7.7 remain
OPEN — closing them drops the status exceptions, and D2 (contracts, manifests,
skill/tool profiles) starts from the fully frozen table.
