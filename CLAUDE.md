# CLAUDE.md — agent-workforce (Praetorium, box-side)

## What this is
The box-side operational home for the AI agent workforce running on this machine:
orchestration config, scheduling, inbox/approval tooling, agent profiles. The vault clones
(`../Obsidian_AI_Operating_System/` canonical, `../obsidian-ai-os-boxsafe/` legacy mirror) hold
*what the agents know*; this repo holds *how they run*.

A trap this file used to narrate is now an assertion in `bin/verify.sh`; each rule below names
its test. `tests/test_instruction_size.sh` holds this file to a size ceiling that only goes down.

## Roster

**This section owns the personas and their job wiring, not the live Buzz fleet** — that is
the `buzz-agent@*` units, owned by `~/CLAUDE.md`. Two runtimes, sharing only the persona
charters. Membership is machine state; enumerate it, never count it in prose
(`test_instruction_size.sh` refuses a count literal here):

```
systemctl --user list-units 'buzz-agent@*' --all    # the chat fleet
ls design/agents/                                   # the personas — one manifest each
```

- Box name: **Praetorium**. Keep the Roman-emperor convention for any additional agent profiles.
- **A persona is `design/agents/<name>.toml`** — the single normative statement of what each owns
  and may do (`design/agent-model.md`). The model a scheduled job runs on is the `--model` in its
  `bin/run_*_cc.sh`; a Buzz agent's is its unit's env. "What runs tonight" is the runbook's Job
  wiring table, not a persona list.
- **Hermes, Ollama and Discord are off the box (2026-09-18).** No local inference tier, no
  Discord delivery; Buzz is the only surface. `tests/test_hermes_residue.sh` asserts the tree and
  the live paths stay clean, including that `discord-bot.service` is installed nowhere.

## Hard constraints (short form)
- **Vault data is in-bubble.** The box sits inside Dave's private trust zone (the same zone as
  Notion): the whole working vault is on the mirror — client names, deals, priorities, daily
  logs — and agents may reason over all of it. `_confidential/` is the one data quarantine
  (never published, tripwired in the publish script). De-identification applies only to what
  *leaves* the bubble — outward-destined drafts, Brave queries, fetched URLs. See
  `docs/data_boundary.md`.
- **The one hard gate is outward action.** No email, no social, no messaging humans from this
  box — it holds no outward credentials, ever. Anything for the outside world is a draft Dave
  sends. Notion is inside the bubble, not outward.
- **Canonical vault access: the box pushes as a GitHub App, and `main` refuses it.** The canonical
  clone's credential helper is `~/.local/bin/github_app_credential.py` (config
  `~/.config/agent-workforce/vault_app.env`); push `git push origin HEAD:agents/…` from
  `~/dev/Obsidian_AI_Operating_System` or a worktree of it. The SSH alias `github-canonical` is
  dead. `tests/test_vault_credential.sh` asserts the helper, the local `pre-push` guard and the
  refused alias.
- **Vault writes go through `agents`, never `main`.** Any proposal to the vault is committed to
  the box-safe repo's `agents` branch/inbox. `main` is machine-published from the Mac — never
  hand-write or merge into it from here.
- **Publishing is Mac-side only.** Never run `publish_boxsafe.sh` from this box.
- **Inference is remote only.** Generative agent work runs on remote APIs (the Claude
  subscription for the scheduled runners and the Buzz fleet; OpenRouter where a job still
  names it); the LLM egress boundary in `docs/data_boundary.md` governs every call.
- **Secrets are a separate tree.** `~/.config/agent-workforce/` holds credentials (deploy key,
  mode 600) and is NOT this repo. Never `git add` anything from that path into this repo.

## Where things live
- `../Obsidian_AI_Operating_System/` — canonical vault clone; propose on `agents/<date>-<slug>`
  branches, never `main`. (Legacy mirror `../obsidian-ai-os-boxsafe/` retires at cutover.)
- `~/.config/agent-workforce/` — secrets + per-job override envs (mode 600). Outside git entirely.
- This repo (`~/dev/agent-workforce/`) — **source of truth** for orchestration config, systemd
  unit sources, agent task profiles, inbox/approval tooling. Commit **and push** your own work
  yourself: `agent-workforce-auto-sync.timer`, when enabled, sweeps a dirty tree to `main` under
  a generic message and never pushes a clean one (`tests/test_auto_sync.sh`).
- `skills/` — the **pointer-skill tree** (T3.1). One plugin per owner
  (`skills/<owner>/.claude-plugin/plugin.json`, `skills/<owner>/skills/<name>/SKILL.md`); every
  `SKILL.md` names its canonical vault path, **never a copy**. Shipped by `bin/deploy`, loaded by
  the scheduled runners with `--plugin-dir` at an explicit path in the **deployed** tree. A skill
  dir at a plugin root and a missing `--plugin-dir` are both silent, so each runner proves its
  manifest readable before it execs (`tests/test_pointer_skills.sh`; allocation in
  `skills/README.md`).
- `~/agent-workforce/` — **deployed runtime copy** (no git) that systemd actually execs. Deploy
  with **`bin/deploy`** (additive; `--dry-run` to preview, `--prune` to drop deleted files; never
  touches `logs/`, `var/`, `backups/`). **Nothing deploys automatically** — the drift check in
  the gate is what says so. Job wiring map: `docs/runbook.md` § Job wiring.
- `~/agent-workforce/var/workflow-receipts/<workflow_id>/<run_id>.json` — **run receipts**
  (T5.1), shape owned by `bin/workflow_receipt.py`. One receipt per run with **exactly one**
  terminal outcome — `artifact`, `decline`, `failed` or `skipped` — never defaulted to success.
  `usage` and `cost` are `measured` or `unavailable` (null fields, never 0). Four producers:
  `bin/agent_propose.sh`, `bin/content_change_dispatch.sh`, `bin/receipt_sweep.py`
  (`workflow-receipt-sweep.timer`, every other standing timer) and `bin/interaction_receipt.py`
  (each `buzz-agent@*` turn); `tests/test_receipt_coverage.sh` proves every standing row has
  one. `when=sweep` checks a run cannot decide are recorded `not_applicable: vantage` and the
  next sweep amends them once (`contract_exec.py --amend`, `tests/test_receipt_sweep.sh`). A
  failed receipt whose defect is fixed is **closed, not rewritten**: `bin/receipt_close.py`.
  Not to be confused with `bin/delivery_receipt.py` (Buzz delivery) or `bin/run_record.sh`
  (`cost.log`).
- `control-room.service` — the **Control Room**, `http://praetorium:8787/` from
  `bin/control_room_api.py` + `bin/control_room_ui/`. Reads only; binds the Tailscale address
  only; reads `design/` from the **source checkout** (`bin/deploy` never ships it). Not a
  manifest workflow. `/` is the SPA: source `ui/control-room/`, served from its **committed
  build** `bin/control_room_ui/app/`, rebuilt only by `bin/control_room_build_ui.sh`
  (`tests/test_control_room_spa.sh` is red on an unbuilt source edit). Rows carry a **role**
  (`agent-workflow`, `system-workflow`, `agent-runtime`); the `buzz-agent@*` units are the
  **Agents** view. A manifest entry's `requires` names units it cannot run without
  (`bin/workflow_requires.py`): a known-down dependency is a `dependency-down` exception and a
  pre-flight refusal in `agent_propose.sh`; unknown is never a refusal. `guards` is a declared
  notice, never a refusal. The agent page's Start / Stop / Restart are session verbs only; the
  broker never reads `ExecStart`/`Environment` (the agent key is in the argv). Runbook § Control
  Room.
- `control-room-broker.socket` + `control-room-broker@.service` — the **control broker** behind
  every screen action: a root-owned socket (`/run/control-room-broker.sock`,
  `root:control-room 0660`) only `control-room.service` reaches, executing the **root-owned copy**
  `/usr/local/lib/control-room/control_broker.py` against `/etc/control-room/allowlist.json`
  (rendered by `bin/control_broker_allowlist.py`), receipting under
  `/var/lib/control-room/receipts/`. Both root files are drift-checked and installed by hand.
  Never widen the socket group, add dave to it, exec the source copy or add a sudoers line —
  each is this design's `--no-verify`.
- **Schedule changes and retirements are `control-room/*` pull requests, never edits.** The
  screen or `bin/workflow_pr.py` builds the branch in a bare clone under
  `/var/lib/control-room-proposals/repo.git` and opens the PR only from a byte-identical preview
  token. Retirement is fail-closed: `tests/test_workflow_retirements.sh` stays red after a merge
  until Dave has cleared the residue and `workflow_pr.py clear <id>` stamps it.

## Daily rhythm jobs (NUC-45)
Two jobs own Dave's day, both under `agent_propose.sh` with `AGENT_RUN_MODE=ops`:
- **`praetorium-daily-plan.timer`** — Mon-Fri 06:00 → `<date> — Daily Plan` row in Notion.
- **`praetorium-eod-summary.timer`** — daily 22:15 → `<date> — EOD Summary` (Daily Plans)
  + `<date>` (Daily Log).

- **Notion is the artifact; the vault write stays Mac-side.** These jobs never write
  `07_daily/`, on any branch (the daily/eod smokes assert it). The Mac's `morning-startup` /
  `eod-wrap` skills remain canonical for interactive runs.
- **All Notion I/O goes through `bin/notion_daily.py`** (date-keyed idempotency); never
  hand-roll Notion HTTP in a task profile.
- **`bin/vault_sync_guard.sh` owns "is the mirror current?"** — `sync` for
  `qmd-refresh.service`, `check` as pre-flight. A stale or dirty mirror is a loud refusal.
  Runbook § Daily rhythm jobs.

## Research pipeline jobs
Headless Claude Code pinned to a **full model name**, never an alias (the smokes assert it):
- **`agent-proposal.timer`** — Mon-Fri 04:30 → standing research (`AGENT_JOB_OVERRIDES` →
  `standing_research.env` → `bin/run_standing_research_cc.sh`).
- **`raw-ingest.timer`** — Tue-Sat 03:00 → one distillation proposal per unprocessed
  `05_knowledge/raw/` source not in `00_system/ingest_log.md`.
- **`knowledge-digest.timer`** — Sun 09:00 → what `05_knowledge/` / `11_entities/` learned in the
  last 7 days.

- **These jobs write only `_inbox/agents/**`**; every vault change they describe is a proposal
  for Mac-side promotion. A rule the jobs keep, not one the credentials enforce.
- **A run produces a dated proposal or an explicit `DECLINE:` sentinel** —
  `bin/proposal_or_decline.sh <slug>` (`AGENT_VERIFY_CMD`) fails any run with neither.
- **Contradictions are named, never silently superseded** — both sides cited under
  `## Contradictions`, in all three profiles.

## BD follow-up drafts
**`bd-followup-drafts.timer`** — monthly, second Monday 09:37, half an hour after the weekly
`bd-stall-radar` (Mon 09:07). Up to 10 copy-paste-ready drafts for every **Dave-owed** BD next
action (radar stalls, pipeline rows past `Next action date`, due BD Task Inbox rows) into
`_inbox/agents/YYYY-MM-DD_bd-followup-drafts.md`, delivered to the Buzz `bd` channel by
`bin/deliver_report.sh`. The radar flags; this job writes the text.

- **No draft asserts elapsed time or silence** — pipeline `Last contact` is unreliable; ground
  in the last evidenced exchange, and surface anything unconfirmed as `⚠ Unverified:`.
- **Both BD jobs are Stage `Prospect` only** (`bd_stall_radar_kernel.py` `IN_SCOPE_STAGES`).
- **Drafts are send material** — `target: none`, never promoted into the vault; the job never
  writes Notion pipeline state.

## Verification
Run: `bash bin/verify.sh` from the repo root.
Gate = bash syntax check + shellcheck (error-severity, must be clean) over every script in
`bin/`, **plus `bin/check_deploy_drift.sh`**, plus any test scripts under `tests/*.sh` if
present. Full shellcheck output (style/info) is printed but does not fail the gate.

**The drift check inverts the usual loop.** It compares source against what is deployed —
`bin/` against `~/agent-workforce/bin/`, `systemd/` against `/etc/systemd/system/`,
`systemd/user/` against `~/.config/systemd/user/` — so editing a `bin/` script makes the gate
red until `bin/deploy` runs: edit → deploy → verify → commit. On a feature branch that adds a
`bin/` script or a unit the gate cannot be green; report the drift, do not soften the check.
Off the box it skips out loud, diffed against `tests/ci-expected-skips.txt`. Runbook § Deploy
ordering.

**Never end a pipeline in an early-exiting reader while `pipefail` is on** — `grep -q` SIGPIPEs
its producer and a found pattern reports 141. Every suite's `assert()` scopes `pipefail` off and
carries the `yes | grep -q y` canary (`tests/test_suite_conventions.sh`). Upstream proposal:
https://github.com/jessebuitenhuis/claude-plugin/issues/12.

Before fixing a flaky gate, establish **which direction it degrades**: one that fails open has
been certifying nothing.
