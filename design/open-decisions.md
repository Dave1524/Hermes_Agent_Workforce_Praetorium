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

### W20 — Scheduled Buzz workflows cannot wake an agent — CLOSED 2026-09-10

*Opened: 2026-09-07, Dave-reported. Closed by T0.3.*

**DECIDED — not available.** The relay accepts a `schedule` trigger, stores it, and never fires
it. **Systemd timers remain the supported scheduling mechanism on this box**, and nothing below
Phase 0 of `docs/dev-plan-2026-09.md` depends on workflows.

Measured 2026-09-09 by Marcus from a credentialed shell, on one probe workflow
(`09a4b564-6651-456e-bbca-235902533716`, channel `ops-praetorium`):

- **No scheduler.** Both forms tested on that one workflow — interval 5m armed 06:16:35Z, cron
  `*/2 * * * *` armed 06:35:39Z. Zero fires on either. 65 minutes after creation the channel held
  exactly one relay-authored message, and that one carried a manual-trigger receipt.
- **Manual `trigger` works**, immediately (event `2918b0e6`, 06:30:54Z). A workflow here is a
  macro, not a schedule.
- **The emitted message cannot wake an agent.** Its tags are `p`, `h`, `buzz:workflow`,
  `p <mentioned agent>` — **missing `buzz:workflow-owner` and `buzz:workflow-mention`**, both
  required by `verified_workflow_owner` (`crates/buzz-acp/src/lib.rs:247`). Attribution is
  rejected, the effective author falls back to the raw signer, and the raw signer is the relay.

Corroborated box-side 2026-09-10, without credentials — the harness is ready and the relay is
behind it:

- `bin/buzz_acp_update.sh probe ~/.local/bin/buzz-acp` — all three `buzz:workflow*` literals
  present, with the extraction control passing. The installed harness consumes what the relay
  never sends.
- Relay NIP-11: `version 0.2.1`, `self` `12f6870117eff1a6318bd38c82a65d51dd19879b7489f57247114d0ee8a96de3`
  — byte-identical to the signer on the emitted event, which is what makes it relay-signed rather
  than agent-signed.
- That key appears in **zero** author rules across all five `buzz-team/*.toml` (grep, 0
  occurrences). So the drop is by rule, not by accident: trajan admits exactly three authors and
  the relay is not one of them.
- Fleet journals hold **0** occurrences of `workflow` since 2026-09-08; trajan's journal for the
  probe hour carries one heartbeat line and nothing else.
- All five units: `NRestarts=0`, up since 2026-09-07 12:12-12:14 CEST — so the `CPUUsageNSec`
  counters sampled at the probe were never reset, which is what makes that comparison sound.

**What this record does not contain, deliberately.** The decisive negative — *no schedule ever
fired* — is Marcus's measurement, not one this file can re-derive. `buzz workflows` needs the
deny-listed `~/.config/buzz-agents/` credentials and the brief forbids routing around them. The
box-side lines above corroborate the *consequence* (nothing woke); they cannot re-observe the
*cause*. Absence of `workflow` in a journal is weak evidence on its own — these units log
lifecycle only.

**Instrument traps found on the way, each of which reads like a result** (Marcus, 2026-09-09):
`buzz workflows runs` returns `[]` for a run that provably executed and posted — audit from the
channel, never the runs feed. `buzz workflows list` still returns a workflow after a delete: it
queries `kinds:[30620]` raw and never applies the `kind:5` deletion. `--yaml` on the installed CLI
takes YAML *content*, not a path, and a path fails with a schema-shaped error that hides the
version gap. A workflow message is always kind 9, so one posted into a non-stream channel is
receipted `ok` and rendered to nobody.

**The mechanism that does work, and why.** `augustus-content.timer` → `bin/run_content_via_buzz.sh`
→ dispatch to Augustus over Buzz → wait for reply → three-state exit contract. It works *precisely
because* the dispatch message is signed by an **agent** credential rather than the relay's, so it
never meets the gate above. Scheduled agent-to-agent dispatch exists on this box; it is reachable
by editing this repo, never from chat. Closing that last gap is a relay-side question and is not
worked around here.

**Carried out of this row, not closed with it:** `~/.config/buzz-team/TEAM.md` § "Scheduling work"
(the 2026-09-07 grant) now states two things the measurement falsified — see the pending action
below.

Full write-up: `.claude/briefs/archive/2026-09-10-buzz-task-scheduling.md`.

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

2. **Two owed on W20, both needing a credentialed shell** (answered 2026-09-09; the original
   `buzz workflows list` item is done — the relay runs no scheduler):
   - **Delete the probe workflow** `09a4b564-6651-456e-bbca-235902533716` in `ops-praetorium`.
     Marcus created it and TEAM.md tells him to delete a workflow whose task has ended, so this
     is one line to him. It is inert — nothing fires — so this is hygiene, not risk. Note that
     `buzz workflows list` shows deleted workflows anyway (it never applies the `kind:5`), so a
     later listing proves nothing either way.
   - **Correct `~/.config/buzz-team/TEAM.md` § "Scheduling work"**, which the measurement
     falsified in two places. It says *"A workflow runs with Dave's standing authority, not
     yours, and only he can trigger one by hand"* — the stored record carries the **creator's**
     pubkey, and Marcus triggered his own probe by hand on 2026-09-09. It also still instructs
     every agent to run `buzz workflows list` and report before creating one; that question is
     answered, and the section should say the relay runs no scheduler so `create` yields an
     inert record. This is the authority layer of five running agents, it needs a fleet restart
     plus `buzz-team/check-loaded.sh` to take effect, and TEAM.md is declared excluded from
     `buzz-team/` adoption — so it is a decision, not an edit, and T0.3 stopped at naming it.

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

