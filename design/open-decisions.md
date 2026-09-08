# Open decisions — what is actually open

**Closed material lives in `design/archive/open-decisions-closed-2026-09-07.md`** — the nine
D-questions (all answered 2026-09-01), the eighteen finished W rows, the cleared pending
actions, and the Phase-B brief order (all six briefs landed). This file holds only what is
open, so that a thing sitting here means something.

## Carried work — open

### W19 — The D5 campaign retirement left an executable chain behind

*Opened: W17's class, 2026-09-04*

**Design and profiles half landed 2026-09-08 (T6.2).** Registry rows footnoted `⁴` with a
dated RETIRED note (rows kept — the file is frozen, T6.4); eval-spec rows removed with a
dated note and the backlog re-measured at zero; `augustus.toml` `[surfaces.scheduled]`
`present = false`, `retired = "2026-09-04"`, the 01:30 collision note past tense; the two
task profiles deleted from source and declared in `design/deploy-exclusions.toml` (eleven
entries); `tests/test_manifest_surfaces.sh` now fails a `present = true` surface that hosts
no workflow, which is the join item 10 lacked. **Still open:** the `bin/` half — three
runner scripts plus the help-string example at `bin/notion_research_page.py:144` — goes
with `bin/deploy --prune` at Dave's chosen moment (T6.3), which clears every exclusion
entry in the same act; and items 1-2, the two override envs, Dave-only (pending action 3).
Remaining check 2 hits outside `bin/` are all dated history: `agent-model.md` §6.5-6.7,
`workflow-registry.md` rows + notes + §7.3, `phaseb-brief-queue.toml` (2026-09-01
measurements, queue spent), `augustus.toml` retirement comment, and `design/archive/`.

**OPEN — widened 2026-09-04; full write-up in `.claude/briefs/w19-campaign-retirement-residue.md`.** Opened as "two override envs outlive their units" (`~/.config/agent-workforce/content_strategy.env`, 16 lines, and `faceless_content.env`, 11). That was the visible tip. The retirement commit `1bc6a4c` touched exactly two files — `config/fleet-units.tsv` and `design/agents/augustus.toml` — **because those are the two the repo had a check for**: `tests/test_fleet_ownership.sh` failed in the manifest->list direction until the `.tsv` was re-materialised, and nothing else failed, so nothing else was touched. Eleven pieces of residue survive, and the five in `bin/` and `profiles/` form a closed, deployed, reachable chain (env -> `run_{content_strategy,faceless_content}_cc.sh` -> `run_standing_research_topic_cc.sh` -> the two task profiles), with `augustus.toml`'s `[surfaces.scheduled]` still `present = true` over zero workflows (`:33`) and its `augustus-content` note still describing a 01:30 lock collision with a unit the same commit deleted (`:78`). **`design/workflow-registry.md` is referenced by no test and no script** — verified by grep over `tests/` and `bin/` — so its rows `:77-78` still read `keep` with live triggers. That is the generalisable part and it is one level up from W17: a retirement is as complete as the repo's joins force it to be, and no more; a registry nobody joins against is prose, and prose does not get retired. The cleanup is **not piecemeal** — `bin/check_deploy_drift.sh:334` reports a runtime-only `bin/` file unconditionally while only the content loop consults `design/deploy-exclusions.toml` (`:392`), so deleting the three `bin/` scripts is hard red with no declarable exemption and needs `bin/deploy --prune`, which cannot be aimed and clears every entry in `design/deploy-exclusions.toml` (eleven since T6.2). The `design/` and `profiles/` half can land alone and green. Items 1-2 stay Dave-only: the config path is deny-listed, so no check here can enumerate it and the only instrument is a human running `ls`.

### W20 — Scheduled Buzz workflows cannot wake an agent on the installed harness

*Opened: 2026-09-07, Dave-reported*

**Open: the relay half.** Nobody has established whether the deployed relay runs the workflow
scheduler and emits the three `buzz:workflow*` tags. It takes one authenticated
`buzz workflows list`, which no Claude Code session here can run — the credentials are
deny-listed. The HTTP probe tried on 09-07 is a non-test: it 403s on a nonsense path too.

**Done 2026-09-07:** the harness (upgraded to `desktop-v0.5.23`, all three wake literals
present, staleness now watched by `agent-buzz-acp-update.timer`) and the authority grant
(`TEAM.md` now permits `buzz workflows create`). Since the grant makes `buzz workflows list`
an agent's required first move, the open half above is likely to answer itself.

Full write-up, including why a workflow message is dropped without an error on either side:
`.claude/briefs/buzz-task-scheduling.md`.

## Pending actions reserved for Dave

All three are blocked on a deny-listed path, which is the only reason they are here — no check on
this box can even read whether they are done.

1. **Install `AGENT_VERIFY_CMD` into `~/.config/agent-workforce/m1_signal_scan.env`** (W15):
   copy the line from `profiles/m1_signal_scan.env.example`, then `chmod 600`. The branch fixed
   the template only, and `bin/deploy` never writes that tree, so no deploy makes it take
   effect. Until then m1 keeps its empty-prompt guard, but a run that dies for any other reason
   still logs as a clean `NOPROPOSAL`. Safe to install now — the task profile already prints
   `DECLINE:` on a legitimate no-signal run; if that is ever reverted, revert this with it.
   State is **unknown from here**, not pending: absence of a report is not absence of the
   install, and the reverse is equally true.

2. **One `buzz workflows list --channel <uuid>` from an agent's own shell** (W20), to settle
   whether the relay runs the workflow scheduler. Also unreadable from here — the credentials
   are in the deny-listed `~/.config/buzz-agents/`. Likely to answer itself now that TEAM.md
   requires an agent to run exactly this before promising a schedule.

3. **Delete the two campaign override envs** (W19 items 1-2):
   `rm ~/.config/agent-workforce/content_strategy.env ~/.config/agent-workforce/faceless_content.env`.
   Both are `AGENT_JOB_OVERRIDES` for units deleted 2026-09-04; no surviving unit names
   either path. Safe now; do it before T6.3's prune, or the shims' headers stop describing
   what is on disk.

---

### Standing procedure, not tasks — both learned by getting them wrong

- **Verify a job by RUNNING it, not by `list-timers`.** `active` + `enabled` + a correct
  `next_elapse` say nothing about whether `ExecStart` exists. Two jobs once sat green in
  `list-timers` while structurally incapable of producing anything.

- **`buzz-team/` converges with `bin/deploy_buzz_team.sh`, NOT `bin/deploy`.** Separate script,
  separate destination guards. `--dry-run` first. It restarts nothing, and a rule-file change is
  inert until the agents are restarted — check `ExecMainStartTimestamp` against the file mtime
  rather than assuming. Exercised 2026-09-07 and the guard held: the live tree was edited first
  by mistake and the converge reverted it.

## Owned by nobody yet

**Two from 2026-09-04:** marcus's engram is at ~79% of the 65,535 B wall and
needs a prune; `augustus-content.timer` was found *stopped* and ran once in eight days — confirm it
holds its own schedule before anything is concluded from the content backlog.

**One from 2026-09-06 — the vault cannot answer its own publishing question, and
only Dave can fix it.** Asked plainly *"how does the agent workforce publish its work and get
proposals approved today?"*, retrieval over the full 529-document index does not return
`03_projects/active/ai_agent_workforce/buzz_architecture.md` **at all** — it is absent from the top
13. The field is `vision.md` 0.90, `nuc_agent_host_spec.md` 0.53 (a hardware spec) and
`08_skills/agent-inbox-sync/SKILL.md` 0.47 (the superseded Notion gate). This surfaced as
`fleet_eval`'s `p2_publish_approve` going red on 2026-09-01 and staying red for six days; the probe
baseline was re-recorded to FAIL on 09-06 because it had been measured on the pre-2026-08-31
101-document mirror, **not** because the gap is acceptable. What stands between an agent and a
wrong answer today is TEAM.md's instruction layer, which names the anchor explicitly — retrieval
alone does not get there. The remedy is a vault edit (the anchor is 84 lines against `vision.md`'s
330 and loses on wording), and the box holds no path to make it: canonical vault work is Mac-side.
Owner: Dave. Trigger: the next vault session on `03_projects/active/ai_agent_workforce/`.

