# Praetorium runbook — backup, restore, rebuild (NUC-19)

## Source of truth (NUC-28)

| Tree | Role |
|---|---|
| `~/dev/agent-workforce/` (git, `main`) | **Source of truth.** Edit here; open PRs for non-trivial work. |
| `~/agent-workforce/` | **Deployed runtime** (no `.git`). What systemd `ExecStart=` runs. Update by copying from the git tree after merge — not by editing in place. |
| `/etc/systemd/system/*.service|.timer` | Installed units. Canonical unit *sources* live in this repo under `systemd/`; install with `sudo cp` + `daemon-reload`. |
| `~/.config/agent-workforce/` | Secrets + per-job override env files (mode 600). **Never git.** Templates: `profiles/*.env.example` — **not** `config/job-overrides/`, which holds history only (W4, 2026-09-02). |

If a reviewer only looks at git and concludes a path is "dead code", check `AGENT_RUNTIME_CMD` / `AGENT_JOB_OVERRIDES` under `~/.config/agent-workforce/` — production wiring often lives there.

## Job wiring (names only — no secret values)

Scheduled **proposal** agent jobs share `bin/agent_propose.sh` (lock, preflight, cost.log, write-boundary, scorecard). Per-job differences are injected via `AGENT_JOB_OVERRIDES` after `secrets.env`.

**NUC-36:** the Hermes cron fleet is folded under systemd + this runner. Model-free jobs get a direct `ExecStart` script; non-proposal LLM jobs use `AGENT_RUN_MODE=ops` (same lock/preflight/cost, no inbox write-boundary/commit). Do not re-add fleet schedules to `~/.hermes/cron/jobs.json`.

**NUC-35 — change-triggered content dispatch.** `content-change-dispatch.timer` polls every 15 min and runs `bin/content_change_dispatch.sh`: a deterministic, **model-free** tick that reads the Notion "Picked" content-board IDs (`notion_rest.py board --status Picked --json`), diffs them against `~/agent-workforce/var/content_picked.state`, and dispatches the **existing** Augustus draft run (`bin/agent_propose.sh`, reusing `augustus-content.env` via `AGENT_JOB_OVERRIDES`) **only when a Picked ID appears that is not already in the state file**. A quiet tick spends nothing — no `agent_propose.sh` call, so no `cost.log` line and no `agent_run.log` entry — it just refreshes the state file and exits 0. This cuts Picked→Drafted latency from the ~24h nightly cadence to ~15 min at zero steady-state cost. Fail-soft by contract: on any Notion API/parse error the script logs to `logs/content_change_dispatch.log` and exits 0 **without touching the state file**, so a transient outage never drops a pending row or corrupts state; the state is only advanced after a clean board read (empty diff) or after a dispatched run returns 0. The nightly `augustus-content.timer` stays as the backstop — a 01:30 poll tick that overlaps the 01:30 nightly run SKIPs safely on `agent_propose.sh`'s flock (`/tmp/agent_propose.lock`, "previous run still active"), so there is no double-draft and no new flag is needed.

| Job | Timer (Europe/Amsterdam) | Unit pair | Override env (runtime path) | Task profile | Runtime |
|---|---|---|---|---|---|
| Standing research (Opus 5, NUC research pipeline brief 2026-07-30) | `agent-proposal.timer` Mon–Fri 04:30 | `agent-proposal.{service,timer}` | `~/.config/agent-workforce/standing_research.env` | `profiles/standing_research_cc_task.md` | *(headless Claude Code)* |
| Raw source ingestion (Mechanism B) | **Tue–Sat 03:00** | `raw-ingest.{service,timer}` | `~/.config/agent-workforce/raw_ingest.env` | `profiles/raw_ingest_cc_task.md` | *(headless Claude Code)* |
| Knowledge digest (Mechanism C) | **Sun 09:00** | `knowledge-digest.{service,timer}` | `~/.config/agent-workforce/knowledge_digest.env` | `profiles/knowledge_digest_cc_task.md` | *(headless Claude Code)* |
| M1 signal scan (NUC-32/34) | **Mon,Wed 05:30** | `m1-signal-scan.{service,timer}` | `~/.config/agent-workforce/m1_signal_scan.env` | `profiles/m1_signal_scan_cc_task.md` | *(headless Claude Code)* |
| Augustus content pitch+draft | daily **01:30** (backstop) | `augustus-content.{service,timer}` | `~/.config/agent-workforce/augustus-content.env` | `profiles/augustus_content_task.md` | **`buzz-agent@augustus`** via `bin/run_content_via_buzz.sh` (NUC-46) |
| Content change-dispatch (poll) | every **15 min** | `content-change-dispatch.{service,timer}` | `~/.config/agent-workforce/augustus-content.env` (reused) | *(triggers the augustus run)* | inherits the row above |
| BD stall radar | weekly **Mon 09:07** | `bd-stall-radar.{service,timer}` | `~/.config/agent-workforce/bd_stall_radar.env` | `profiles/bd_stall_radar_task.md` | `claudius` |
| BD follow-up drafts | monthly, **2nd Mon 09:37** | `bd-followup-drafts.{service,timer}` | `~/.config/agent-workforce/bd_followup_drafts.env` | `profiles/bd_followup_drafts_cc_task.md` | *(headless Claude Code)* |
| Weekly pre-assembly | **Fri 22:00** | `weekly-pre-assembly.{service,timer}` | `~/.config/agent-workforce/weekly_pre_assembly.env` | `profiles/weekly_pre_assembly_cc_task.md` | *(headless Claude Code; owner **marcus**)* |
| Overnight pre-snapshot (no LLM) | daily **04:25** | `overnight-pre-snapshot.{service,timer}` | n/a | `bin/overnight_pre_snapshot.sh` | n/a |
| Overnight morning report (ops) | daily **06:15** | `overnight-morning-report.{service,timer}` | `~/.config/agent-workforce/overnight_morning_report.env` | `profiles/overnight_morning_report_cc_task.md` | *(headless Claude Code; owner **marcus**)* |
| Daily plan (ops) | **Mon–Fri 06:00** | `praetorium-daily-plan.{service,timer}` | `~/.config/agent-workforce/daily_plan.env` | `profiles/daily_plan_task.md` | *(headless Claude Code)* |
| EOD summary (ops) | daily **22:15** | `praetorium-eod-summary.{service,timer}` | `~/.config/agent-workforce/eod_summary.env` | `profiles/eod_summary_task.md` | *(headless Claude Code)* |
| Agent inbox → Notion sync | `agent-inbox-sync.timer` | `agent-inbox-sync.{service,timer}` | *(service embeds the pipeline cmd)* | n/a | n/a |
| Workflow receipt sweep (no LLM; T5.2) | daily **05:50** — shipped disabled; `systemctl is-enabled workflow-receipt-sweep.timer` read `enabled` on 2026-09-17 (fires at 05:50, last 09-17 05:50:03) | `workflow-receipt-sweep.{service,timer}` | n/a | `bin/receipt_sweep.py` — one receipt per finished platform invocation, from systemd's own record; since T7.3 it also decides the `when=sweep` checks of every self-receipted run in place (`contract_exec.py --amend`) | n/a |

**Two rows above were corrected 2026-09-02 (W1).** They named `profiles/weekly_pre_assembly_task.md`
and `profiles/overnight_morning_report_task.md` — both archived to `profiles/archive/` on 2026-09-01 —
and attributed both to `claudius`, when `design/agents/marcus.toml` declares both. Following the old
rows installed a job pointing at an archived profile under an owner that does not own it.

### `AGENT_OWNER` — the persona that owns a job

`AGENT_OWNER` in each live override env names the owning persona (`design/agents/<owner>.toml`)
and is the `owner=` field of the run log; `AGENT_PROFILE` still names the runtime and keys
`cost.log`'s `profile=` column (W1, 2026-09-02). Until T6.1 (2026-09-16) `AGENT_OWNER` also
selected a Hermes episodic store under `~/.hermes/profiles/<owner>/memories`; that store is
retired and every run logs `memory=na` — the per-run record is the receipt
(`~/agent-workforce/var/workflow-receipts/`). `~/.config/agent-workforce/` is mode-600 and
outside this repo; an agent cannot read or write it, so a missing `AGENT_OWNER` line is
Dave's to add.

**Research pipeline brief (2026-07-30).** The standing research run was hard-down for ten
days on hermes/claudius via OpenRouter (HTTP 402 "Insufficient credits" landing in the
hermes profile's own `errors.log`, never in the attempt's stdout `agent_propose.sh`
scans) while reading as a clean `NOPROPOSAL`. All three rows above run headless Claude
Code pinned to `claude-opus-5` (the full model name, not the `opus` alias) and set
`AGENT_VERIFY_CMD='bin/proposal_or_decline.sh <slug>'`, which fails any run that produces
neither a dated proposal nor an explicit `DECLINE:` sentinel — the class of failure this
migration closes, not just the one instance. All three write only `_inbox/agents/**`;
every vault change they describe is a proposal for Mac-side promotion, never a direct
write to `main`. **Follow-up (Mac-side, not attempted here):** promote the Mechanism A
contradiction-flagging rule (baked into all three task profiles) into
`00_system/update_protocol.md` § Source Ingestion itself — the box has no canonical vault
write access to do this from here.

**NUC-46 — the content job runs on the Buzz Augustus.** `augustus-content` went through
hermes → OpenRouter → `openai/gpt-5.5`, which has answered `402 Insufficient credits` on every
call since ~2026-07-25; ten `Picked` rows sat undrafted. The same Editor-in-Chief already runs
on this box as `buzz-agent@augustus` (codex-acp, `gpt-5.6-sol`) at zero marginal cost, so the
runtime now publishes a trigger to `ROUTE_content` and waits for him. Three seams, one job each:
`bin/content_board_digest.sh` is the only definition of "what the board looks like",
`bin/run_content_via_buzz.sh` is `AGENT_RUNTIME_CMD`, `bin/content_moved.sh` is
`AGENT_VERIFY_CMD`. Notion works unchanged inside augustus's bwrap namespace because
`bin/notion_rest.py` now carries a second transport (`--transport auto`) that routes the same
five REST calls over the broker socket when there is no HTTPS credential — the namespace is
**not** widened, and `~/.config/buzz-team/verify-fleet.sh` gate 5 still holds.

The cutover is one line in `~/.config/agent-workforce/augustus-content.env` (deny-listed —
Dave pastes it; no session can edit that file):

```sh
AGENT_RUNTIME_CMD='~/agent-workforce/bin/run_content_via_buzz.sh'
AGENT_VERIFY_CMD='~/agent-workforce/bin/content_moved.sh'
AGENT_MAX_ATTEMPTS=1
```

`AGENT_MAX_ATTEMPTS=1` is not optional, and since 2026-09-02 it is the **only** thing
setting it. The default is 3, and a timeout exits 1 — retried — so a slow-but-working
augustus would be re-triggered up to three times and could draft the same row twice. Until
the S3 retirement (D7) there was a second source: `agent_propose.sh` matched
`*kanban_run_and_wait.sh*` in the runtime command and collapsed to 1 attempt implicitly.
That path match is deleted, so **every** job now gets 3 unless its own override says
otherwise. Any job that was relying on the implicit 1 must set it explicitly.

**Revert is no longer available, and must not be improvised.** It used to mean: restore the
`AGENT_RUNTIME_CMD` from `config/job-overrides/archive/augustus-content.env.example`. That
line invokes `kanban_run_and_wait.sh`, which was deleted 2026-09-02 — installing it now
gives the unit a runner that does not exist, i.e. a green timer that is structurally
incapable of producing anything. The archived example stays as history and is correct as
history. If augustus-content needs backing out, the target is the Buzz-dispatch wiring in
`bin/run_content_via_buzz.sh`, not the kanban era. Nothing else changes — the
15-min `content-change-dispatch` poller reuses this same env, so both jobs move and revert
together, which is deliberate: two Augustuses drafting one board is the double-hosting hazard.
Overlap between the 20-minute wait and the 15-minute tick is a clean SKIP on
`agent_propose.sh`'s flock.

Exit codes carry the NUC-44 split and must stay apart: **4** = the trigger never landed, nobody
was asked (`CRASHED`, not retried); **1** = augustus was asked and was silent (`FAIL`); **0** =
the board moved, or he replied `DECLINE: <reason>` — the runtime records that reply's relay
event id in the snapshot so `content_moved.sh` can pass an unmoved board on evidence Dave can
re-read (`buzz social event --event <id>`) rather than on the run's own say-so.

**BD follow-up drafts is chained after the radar, deliberately.** `bd-stall-radar` (every
Monday 09:07) decides *which* deals are owed a touch and stops at flagging;
`bd-followup-drafts` (second Monday of the month, 09:37) reads that morning's pack as one of
its three inputs and writes the actual text, so the 30-min offset is a data dependency, not
cosmetic — and both slots sit off the `*:0/15` ticks of `content-change-dispatch`, which
shares `agent_propose.sh`'s global `flock` on `/tmp/agent_propose.lock`, where a collision is
a **silent** `SKIP: previous run still active` (exit 0 — at weekly/monthly cadence that costs
a week or a month, not a night). Both were Sun–Thu 23:00/23:30 until 2026-09-11. The pack is send
material, not a vault proposal: it carries `target: none`, is never promoted, and the job
never writes Notion pipeline state.

Override files set only non-secret keys:

- `AGENT_PROFILE` (optional; else parsed from `AGENT_RUNTIME_CMD -p …`)
- `AGENT_TASK_SLUG` (metrics / cost.log label — also keys `logs/last-attempt/<slug>.log`, the run's own output that `proposal_or_decline.sh` and `deliver_proposal.sh` read their decline sentinel from, so changing it renames that file)
- `AGENT_RUNTIME_CMD` (the actual runner invocation — `bin/run_*_cc.sh` or `bin/run_content_via_buzz.sh` today; paths point at the **deployed** tree `~/agent-workforce/`. It read "hermes / kanban invocation" until 2026-09-02; no live job has invoked either since 2026-08-13, proven from the `run attempt N/M:` journal line of all 14 units that set this key)
- `AGENT_RUN_MODE` (`proposal` default, or `ops` for non-inbox LLM jobs — NUC-36)

Templates (checked in): `profiles/*.env.example`. Install:

```bash
install -m 600 profiles/<job>.env.example ~/.config/agent-workforce/<job>.env
```

**One home since 2026-09-02 (W4).** These five lines used to point at
`config/job-overrides/`, and the `install` example named
`config/job-overrides/augustus-content.env.example` — a path that has existed only under
`archive/` since 2026-09-01. Following it provisioned a retired runtime. That directory now
holds history and a pointer; see `config/job-overrides/README.md`, including the one job
(`augustus-content`, standing and enabled) with no example in the live home.
`bd-stall-radar` gained `profiles/bd_stall_radar.env.example` in T2.3 and was enabled in
T2.4. `archive/` holds one each and neither is a template — augustus's
still names `kanban_run_and_wait.sh`, retired with the Hermes kanban — so derive the wiring
from the unit's own journal rather than from `archive/`.

Supporting daemons (not override-driven):

| Unit | Role |
|---|---|
| `qmd-mcp.service` (+ `qmd-mcp.service.d/gpu.conf`) | Vault MCP on `:8765`; GPU drop-in sets `QMD_LLAMA_GPU=vulkan` |
| `qmd-refresh.timer` | Index refresh every 30m; the pull leg is `bin/vault_sync_guard.sh sync` (NUC-45) |
| `brave-mcp.service` | Brave search MCP on `:8766` |
| `scorecard.timer` | Weekly scorecard publish |
| `agent-workforce-auto-sync.timer` | Shell auto-sync of this git repo (no LLM) |
| `overnight-pre-snapshot.timer` | Model-free pre-run state capture → `~/logs/overnight/` (NUC-36) |
| `inbox-backlog-alert.timer` | Daily 06:20 approvals-aging alert to the Buzz `approvals` channel (>2d oldest pending) — NUC-30 |
| `workflow-incidents.timer` | Every 5 min (+30 s jitter) actionable workflow incidents → Buzz `incidents` stream via `bin/deliver_incidents.sh` (T5.3c): one `[incident]` per failed check, missing artifact, incomplete run, malformed receipt or control failure; one `[recovered]` when it clears; one `[incident digest]` a day (07:00 gate) while anything stays open. **Ships disabled** and the `incidents` route is empty until Dave creates the channel. State: `~/agent-workforce/var/incidents/state.json`; log `~/logs/workflow-incidents.log` |
| `fleet-eval.timer` | Daily 07:07 drift check via `bin/fleet_eval.sh`: tier 1 grades receipts against `bin/buzz_routes.env`, tier 2 re-asks the vault questions the fleet got wrong — three assert which document wins, and `p4_kind_span` asserts the answer is still inside the anchor's own retrieved chunk, because prose added to a vault file re-cuts every chunk below it. Gates on **regression against the baselines in `bin/fleet_eval_probes.json`**, not on absolute state — two probes fail today by design, and re-recording a baseline is a deliberate fixture edit. Exits 1 and posts to `ops` only when something moved backwards; history spine at `~/logs/fleet-eval/history.psv` |
| `agent-drift-check.timer` | Daily 05:40 source-vs-deployed drift via `bin/check_deploy_drift.sh` (D8). Compares every destination `bin/deploy` writes plus the three unit trees — `bin/` ↔ runtime, the eight content trees ↔ their runtime copies (`profiles`, `docs`, `config`, `CLAUDE.md`, `AGENTS.md`, `README.md`, `systemd` — the staging copy — and `skills`, the pointer tree the scheduled runners load by explicit path), `systemd/` ↔ `/etc`, `systemd/user/` ↔ `~/.config/systemd/user/`, `buzz-team/` ↔ `~/.config/buzz-team/` — in **both membership directions**, not just the bytes of units present in both. Ownership fails closed: an installed unit with no source is red unless declared in `design/unit-ownership.toml` (permanent) or by its manifest's `status = "campaign"` + `expires` (dated, and an expired entry still doing work is itself red). Reports only — no `/etc` writes, no `systemctl`, no deploy. The staging copy `~/agent-workforce/systemd/` is compared against **source**, never used as a stand-in for `/etc` (W17): `bin/deploy` writes it, so it is a destination this repo answers for, but systemd never reads it — source-vs-staging alone would go green the moment a unit is deployed while `/etc` stayed stale. Both comparisons run |
| `agent-buzz-acp-update.timer` | Daily 07:35 upstream-currency check for the Buzz CLI/ACP via `bin/buzz_acp_update.sh check` (W20). The class it covers: the fleet ran a `buzz-acp` twelve releases behind for five weeks and nothing on this box could have reported it. **Buzz Desktop on the Mac and the CLI here are two independent installs of one release stream** — every upstream tag is `desktop-vX.Y.Z` and the CLI ships inside `Buzz_X.Y.Z_amd64.deb` at `usr/bin/`, as a byproduct of packaging the app — so Desktop keeping itself current through its Tauri updater says nothing about this box, and there is no dpkg package to `apt upgrade`. Neither binary answers `--version` and neither carries the release (`strings` finds the same `0.5.3` dependency crate in the July and September builds), so staleness is not merely unreported, it is **unaskable** without a receipt: `~/agent-workforce/var/buzz-cli-install.json` records tag *and* sha256, and every run re-hashes the live files before believing the tag. Non-zero is the whole notification path — **10** behind, **1** unpinned or a week without reaching upstream — because `agent-alert@` already owns the throttle (one alert on the transition, one reminder per 24h) and a second notifier would be a second copy of that policy. **It never installs.** It may stage and probe a new release, once per tag, so the report says whether that release would still *run* here: the three `buzz:workflow*` wake literals plus every flag the unit's `ExecStart` passes, since `buzz-acp` rejects an unknown flag at startup and `Restart=on-failure` turns that into a crash loop rather than a visible stop. Installing is `bin/buzz_acp_update.sh apply <tag>` by hand — canary restart, fleet gate, automatic rollback. Making it unattended is a one-line `ExecStart` change and the probe is what would make that defensible; do it after a few releases have passed cleanly, not before. |

## Deploy ordering — this inverts the usual loop

`bin/verify.sh` hard-fails on deploy drift, so **verify is red until `bin/deploy` has run**.
The order is:

```
edit source  ->  bin/deploy  ->  bash bin/verify.sh  ->  commit
```

not the usual edit → verify → commit → deploy. Adding or editing anything under `bin/` makes
the gate red immediately, and the message names the file, so a red here is explainable rather
than mysterious — but only if you know to expect it. `bin/deploy` warns when the source tree is
dirty (it does not block), and refuses to deploy onto a git tree, so the source can never be its
own destination.

Two consequences that are correct and will still surprise:

- **`bin/deploy` itself exits non-zero while any `/etc` unit is missing**, because its
  post-condition runs the same full four-tree check and installing a unit needs `sudo` —
  which no script here does. A successful rsync plus a non-zero exit means "the runtime
  converged, the box has not". Install the unit and re-run.
- **A campaign exclusion expiring turns the gate red on a calendar, with no commit.** The two
  content-research campaigns expire 2026-09-03 23:00 and 2026-09-04 01:30; after that their
  `/etc` units are red until they are deleted from `/etc` (brief 6 owns that).

**`workflow-receipt-sweep.timer` is installed like any other unit and then NOT enabled** —
`sudo cp` + `daemon-reload` only, no `enable --now`; `tests/test_receipt_sweep.sh`'s
`sweep-unit-ships-disabled` asserts no step in the repo enables it, and the first
`systemctl enable` is Dave's from the Control Room, not a deploy step.

Deploy a unit after changing `systemd/`:

```bash
sudo cp systemd/<unit> /etc/systemd/system/
sudo systemctl daemon-reload
# timers: sudo systemctl enable --now <name>.timer
```

**`systemd/user/` is NOT installed this way.** Those nine units are `--user` scope; copying one
into `/etc/systemd/system` installs it system-wide under the wrong manager and it will not find
`%h`. They go to `~/.config/systemd/user/` with no `sudo` at all:

```bash
cp systemd/user/<unit> ~/.config/systemd/user/
systemctl --user daemon-reload
# timers: systemctl --user enable --now <name>.timer
```

Deploy scripts/profiles after merge:

```bash
# Prefer rsync of tracked trees only — never copy secrets or .bak files
rsync -a --delete \
  --exclude '.git' --exclude 'logs' --exclude 'backups' --exclude 'node_modules' \
  ~/dev/agent-workforce/bin/ ~/agent-workforce/bin/
rsync -a ~/dev/agent-workforce/profiles/ ~/agent-workforce/profiles/
rsync -a ~/dev/agent-workforce/docs/ ~/agent-workforce/docs/
```

## Ship rails hook (T8.1)

`.claude/settings.json` runs `.claude/hooks/ship_rails.py` as a `PreToolUse` hook on every
`Bash`, `Write`, `Edit` and `MultiEdit` call, so the ship-dev-plan `RAILS` that were prose are
refusals: editing an **existing** test (`tests/**` on `origin/main`, falling back to `main`,
then `HEAD`), `bin/verify.sh`, `bin/check_deploy_drift.sh` or the hook itself — by tool or by a
Bash write shape (redirect, `sed -i`, `tee`, `mv`, `rm`, `cp` onto it, `git checkout --`,
`bash -c "…"`); `--no-verify` and `git commit -n`; `git add -A` / `--all`; `bin/deploy --prune`;
and `systemctl start|stop|restart|enable|disable|…`. A refusal is one stderr line naming the
rail; the helper's docstring and `tests/test_ship_rails.py` are the full table.

Not refused, on purpose: a test file new on the branch (TDD on the suite you are writing),
`bin/deploy` and `bin/deploy --dry-run --prune` (the rsync preview), `git fetch --prune`,
`systemctl show|status|is-active|list-unit-files|daemon-reload`, and every command the ship and
land prompts issue on a clean task (`rails-ship-dev-plan-pass-through` pins that list).

**Override, edit rails only:** `SHIP_RAILS_OVERRIDE="<reason>" claude` in the launching shell
lifts the test and gate-script rails and appends one line per lifted edit to
`.git/ship_rails_overrides.log` (the main `.git/` even from a worktree); an override whose
record cannot be written is refused. The command rails ignore it — a command Dave wants run is
run from a terminal. Consequence: a `t.deploy` land step's `sudo systemctl restart` now stops at
the systemctl rail and is Dave's hand. Measured 2026-09-22: the hook fired in the very session
that wired it, on the next `Bash` call — there is no launch boundary to hide behind, and the
auto-sync sweep that lands a new suite on `origin/main` makes it an *existing* test mid-task.

## Control Room (T5.3)

**URL:** `http://praetorium:8787/` (MagicDNS) or `http://100.86.82.16:8787/` — from the tailnet
only. `/` redirects to `/app/`, the single-page app (T5.3e, 2026-09-16): Overview, Workflows,
a workflow page, a run page, Incidents, Usage and Activity, every one of them read from
`/api/v1/*` and re-fetched every 60 s (the toggle in the header, remembered per browser) or on
Refresh. The server-rendered pages stay as the no-JS fallback — `/exceptions`, `/portfolio`,
`/benefit`, `/workflows/<id>`, `/runs/<run_id>` — and share the API with the app, so both
show the same numbers or the same `unavailable`.

**Unit:** `systemd/control-room.service` (system scope, `User=dave`, `Restart=on-failure`), the
one hand-started unit on this box that is not a workflow timer. It is **not** a manifest
workflow: no row in `design/agents/*.toml`, no contract, no timer, no `config/fleet-units.tsv`
entry. Land, restart and stop are Dave's, with sudo:

```bash
sudo cp systemd/control-room.service /etc/systemd/system/ && sudo systemctl daemon-reload
sudo systemctl enable --now control-room.service      # touches no workflow timer
sudo systemctl restart control-room.service           # after bin/deploy ships a change
journalctl -u control-room.service -n 50
```

**Bind rule:** `ExecStart` is `bin/control_room_serve.sh`, which resolves `tailscale ip -4` and
binds that address only. It refuses to start (exit 1, naming the command) when Tailscale is down
— never `0.0.0.0`, never the LAN, never loopback in production. Dave-only is the tailnet having
one user; there is no `tailscale serve`, no TLS, no auth header, on purpose (a `tailscale serve`
config lives in tailscaled, outside this repo and invisible to the drift check).

**What it reads:** `design/agents/*.toml` and `design/contracts/*.md` from the **source checkout**
(`CONTROL_ROOM_REPO_ROOT=/home/dave/dev/agent-workforce` — `design/` is source-only, `bin/deploy`
does not ship it), timer files under `systemd/`, `systemctl show` in both scopes,
`~/agent-workforce/var/workflow-receipts/` and `design/benefit-ledger.toml`. Missing data renders
`Unknown` or `unavailable`, never 0. **Receipts are `unavailable` until T5.2's first run** writes
one; until then every workflow's health comes from systemd alone and the Exceptions queue says
so in its empty state. Every envelope carries a `dataStatus` per source (`available` /
`degraded` / `unavailable`) with the errors behind it; the list's covers every row, while a
workflow page's is narrowed to that workflow (its contract, its units, its receipts) — source-wide
failures such as a manifest that does not parse stay on every page. A spent entry's
`contract_exempt` is `contractStatus: exempt` with the reason, never a degraded contracts source:
until 2026-09-16 the two spent NeKoVri entries read `contract not declared` and put "contracts
degraded" on all 31 workflow pages.

**What it never writes:** anything of its own. Every HTTP write method is 405 except the two
control endpoints (`POST /api/v1/control/{actions,proposals}`), which validate the request and
hand it to the broker socket (§ Control Room controls) or the proposal builder (§ Control Room
proposals) — and answer 501 only on a box where neither is wired. The service itself runs no
`systemctl` verb but `show`, touches no timer, no receipt, no vault, no Notion; every change
the screen can cause is a broker receipt or a pull request, never an edit.

**Closing a reviewed failure (T7.5):** a `failed` receipt keeps its exception row, its
incident and its Buzz alert until a later run replaces it as `lastEligibleRun` — for a
Mon-Fri job whose check defect was fixed the same morning, that is a day of a red that means
nothing. The operator's verdict is written on the receipt:

```
bin/receipt_close.py <workflow_id> <run_id> --by "Dave" --reason "<the defect and its fix>"
```

It adds a `closed` block (`at`, `by`, `reason`; `bin/workflow_receipt.py`) and changes nothing
else — the recorded outcome and checks stay as written, visible on the run page with a
`closed` chip. Every reader asks `workflow_receipt.judged` and looks past it: health,
`lastEligibleRun`, the eligible count and valid-artifact rate, the exceptions queue, incidents
and the 7-day reliability strip. The notifier's next tick resolves the incident and posts
`[recovered]` citing the closure. Only a receipt with something failed can be closed, once;
a closed run tells the next run nothing, so a new failure re-opens as a new run. Run ids are
on the run page, in `/api/v1/runs?workflow=<id>`, or the file names under
`~/agent-workforce/var/workflow-receipts/<workflow_id>/`.

**Drift:** the screen's code ships with `bin/` (including the nested `bin/control_room_ui/`,
which is why the bin half of `check_deploy_drift.sh` compares recursively since 2026-09-14);
the unit is compared against `/etc/systemd/system/` like every other. `design/` changes need
no deploy — the service reads the checkout — but a `bin/` change is inert until `bin/deploy`
**and** a restart.

### Roles, the Agents view, `requires` and `guards` (T5.3f)

Every workflow row carries a **role** derived from its manifest `surface`
(`bin/control_room_state.py` `role_of`): `agent-workflow` (scheduled, buzz_dispatch),
`system-workflow` (platform) or `agent-runtime` (the five `buzz-agent@*` units). The
Workflows page is two sections, Agent workflows and System workflows, and never lists a
runtime; `/api/v1/workflows` omits runtimes unless asked with `?role=all`, and the Overview
tiles count workflows without them. The runtimes are the **Agents** view — `/app/agents` and
`/app/agents/<name>`, from `/api/v1/agents` and `/api/v1/agents/<name>` — one card per
manifest: runtime state and `since` from `systemctl --user show`, last turn, turns and usage
over seven days from the interaction receipts, owned workflows by role, and the workflows that
require it. T5.3f shipped this view read-only; since T5.3g (2026-09-16) the agent page carries
**Start / Stop / Restart agent now** — see Control Room controls § Runtime controls. The SSR
`/portfolio` still lists all 31 rows with a `data-role` each.

`requires` on a manifest entry names the units a workflow cannot run without
(`agent-model.md` §4 has the grammar and the audit rules). The row shows each requirement's
live `ActiveState` and a tri-state `satisfied` — `true`, `false`, or `null` when the bus
answered nothing — and a chip: green when all are satisfied, red naming the first that is
down, grey `unknown`. The workflow page adds a Requires / Required by panel with links. An
**enabled** workflow with a requirement known to be down is a `dependency-down` exception
(one row naming every down unit); paused workflows raise none, and unknown is never a
refusal. The executors check the same thing before running:
`bin/workflow_requires.py check <unit>` in `bin/agent_propose.sh` (a BLOCKED receipt, exit 0).
`bin/workflow_requires.py audit` is the static half, run by `tests/test_workflow_requires.sh`
with no live `systemctl`.

`guards` is a declared one-sentence field on platform entries only — what stops working when
the job is off — rendered as a chip and as an amber notice in the Pause and Stop dialogs. A
notice, not a refusal: the broker was unchanged by T5.3f, and so were
`/etc/control-room/allowlist.json`, `/usr/local/lib/control-room/control_broker.py` and the
socket (T5.3g changed both root files; its land sequence is under Runtime controls). Landing
T5.3f was `bin/deploy` and `sudo systemctl restart control-room.service`; no root install, no
allowlist re-render, no timer or runtime touched.

### Frontend build (T5.3e)

The app's source is `ui/control-room/` (React + Vite + TypeScript, its own `README.md`); what
the service serves is the **committed build** at `bin/control_room_ui/app/` — `index.html`,
`assets/app.js`, `assets/app.css`, the woff2 font subsets and `BUILD.json`. It is committed so
`bin/deploy` ships it and the drift check compares it like any other `bin/` file, and so the
box needs no Node to serve it.

```bash
bin/control_room_build_ui.sh          # typecheck, vitest, build, stamp; prints the changed files
git add bin/control_room_ui/app ui/control-room && git commit
bin/deploy && sudo systemctl restart control-room.service
```

`BUILD.json` is `{"schema":1,"source_sha256":"…"}`: the hash `bin/control_room_ui_stamp.sh`
prints over every tracked or unignored file under `ui/control-room` (path and bytes, sorted;
no timestamp, no Node version). `tests/test_control_room_spa.sh` recomputes it, so a source
edit that was not rebuilt is red on the box and in CI without a toolchain; where Node ≥ 22
and `node_modules` exist (the box has both; CI installs them) it also runs typecheck, the
vitest suites and a rebuild that must be byte-identical to the committed output. The build
script refuses Node < 22 and runs `npm ci` when `node_modules` is absent (`--ci` to force it).

Output names are fixed (`vite.config.ts`), so a rebuild changes bytes, never membership:
`bin/deploy` without `--prune` is enough. `--prune` is needed only when a file is *removed*
from the build — a font subset dropped, say — because the runtime copy would otherwise keep
serving it. Every static response is `Cache-Control: no-store`, so fixed names cost nothing
in staleness.

## Control Room controls (T5.3a)

**The fleet stays off.** T5.3a lands the *mechanism* for pause / resume / run now / retry / stop;
the first live resume is Dave's moment (DoD item 7) and starts that workflow's evidence clock.
Nothing in the land sequence below enables, starts, stops or disables a workflow timer — the one
unit it enables is the broker socket, a control surface.

**Trust boundary — three layers, each with one job:**

```
Mac browser ──tailnet──▶ control-room.service (dave + group control-room)
                           │  bin/control_room_control.py: shape check, actor, HTTP mapping
                           ▼  unix socket /run/control-room-broker.sock  root:control-room 0660
                         control-room-broker.socket (Accept=yes) ─▶ control-room-broker@N.service (root)
                           │  /usr/local/lib/control-room/control_broker.py  (root-owned copy of bin/control_broker.py)
                           │  reads /etc/control-room/allowlist.json         (root-owned, rendered from the repo)
                           │  writes /var/lib/control-room/receipts/…        (StateDirectory, root-owned, world-readable)
                           ▼
                         systemctl [--user --machine=dave@.host] {show,disable --now,enable --now,start --no-block,stop --no-block,restart --no-block}
```

Policy lives in the broker, not the screen — the same rule `~/CLAUDE.md` records for the Notion
broker. The screen validates shape, adds the actor (`remote`/`local` of the HTTP connection),
maps refusal codes to HTTP status and **re-reads** state; the chip after a click shows what
systemd says, never what was clicked. Who may connect is the kernel's decision: the socket is
`root:control-room 0660`, `control-room.service` carries the group through a drop-in, and no
dave shell, runner or `buzz-agent@*` is in it. Belt and braces: the broker checks `SO_PEERCRED`
uid and refuses a screen request whose `remote` is the screen's own host or loopback (a
loopback-*bound* screen is a development instance and is allowed).

**Actions** (system scope shown; user-scope units prefix `--user --machine=dave@.host`):

| action | precondition (refusal) | systemctl | extras |
|---|---|---|---|
| `pause` | some timer still enabled/active, else `state_conflict` | `disable --now <unit>.timer` | the running service is **not** stopped |
| `resume` preview | paused, else `state_conflict` | read-only `show`, stamp mtime, `systemd-analyze calendar` | `preview.implication` states the `Persistent=` catch-up; `preview_token` = the preview receipt id |
| `resume` apply | a `previewed` receipt ≤ 10 min old whose fingerprint still matches, else `preview_required` / `preview_stale` | `enable --now <unit>.timer` | `next_scheduled_run`, `catch_up_fired` |
| `run_now` | no run in progress; two triggers need `trigger` (`trigger_required` lists `choices`) | `start --no-block <unit>.service` | `run_id` = InvocationID, `links.run` |
| `retry` | allowlist `retry: true` (the contract's `Retry` row), else `not_idempotent`; then as run_now | as run_now | `links.retry_of` |
| `stop` | `confirm: true`, non-empty reason, a run in progress | `stop --no-block <unit>.service` + poll ≤ 15 s | receipt notes a still-deactivating service |

**A run in progress is `activating/start-pre`, `start` or `start-post`** — every workflow unit
here is `Type=oneshot`, so a run never reads `active/running`; `RUNNING_SUBSTATES` in
`bin/control_broker.py` owns that set and the screen imports it. The first live resume
(2026-09-15) caught its catch-up run in `start-pre` and receipted `catch_up_fired: false` because
the set was `{running, start}`. While that run is in flight the timer's substate is `running` and
systemd reports no `NextElapse`, so `next_scheduled_run` is `null` on the resume receipt — read it
off the workflow page once the run ends.

**Receipts:** every outcome — applied, previewed, refused, failed — is one file at
`/var/lib/control-room/receipts/<workflow_id>/<receipt_id>.json` (`_refused/` for anything
refused before the workflow resolves — a malformed request, `peer_denied`, an id the allowlist
does not know; `requested_workflow_id` keeps the id), written atomically, 0644, carrying the actor, every `systemctl` argv
with exit and stderr, and the state before and after. The page's *last action* is the newest
non-preview receipt for that workflow. The CLI form, through the root copy:

```bash
sudo /usr/bin/python3 /usr/local/lib/control-room/control_broker.py act resume knowledge-digest --stage preview
sudo /usr/bin/python3 /usr/local/lib/control-room/control_broker.py act pause no-such-workflow   # -> unknown_workflow
```

**Land sequence** (sudo; the branch cannot be green before this, and the drift check says so):

```bash
sudo groupadd --system control-room
sudo install -D -o root -g root -m 0755 bin/control_broker.py /usr/local/lib/control-room/control_broker.py
python3 bin/control_broker_allowlist.py render > /tmp/allowlist.json \
  && sudo install -D -o root -g root -m 0644 /tmp/allowlist.json /etc/control-room/allowlist.json \
  && python3 bin/control_broker_allowlist.py check
sudo cp systemd/control-room-broker.socket systemd/control-room-broker@.service /etc/systemd/system/
sudo mkdir -p /etc/systemd/system/control-room.service.d \
  && sudo cp systemd/control-room.service.d/broker.conf /etc/systemd/system/control-room.service.d/
sudo systemctl daemon-reload
sudo systemctl enable --now control-room-broker.socket   # the socket, not a workflow timer
sudo systemctl restart control-room.service              # the screen picks up its drop-in
ls -l /run/control-room-broker.sock                       # srw-rw---- root control-room
bash tests/acceptance/control_room_controls.sh            # previews and refusals only; all PASS
```

If `systemctl --user --machine=dave@.host` does not answer from root on this systemd, the
fallback is `runuser -u dave -- env XDG_RUNTIME_DIR=/run/user/1000
DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user …` — documented, not
implemented; the broker's `--user-manager` option is where it would go.

**Re-render rule:** a manifest, timer or contract change changes the allowlist. `python3
bin/control_broker_allowlist.py check` (and the drift check's `[broker]` section) goes red until
the render is re-installed with the `install` line above. The root copy of the broker is
compared the same way: a `bin/control_broker.py` change is inert — and red — until re-installed.

**Never:** widen the socket group, add dave to it, point `ExecStart` at `/home`, or add a sudoers
line — each is the `--no-verify` of this design, the same escalation with the record removed.

### Runtime controls (T5.3g)

The same broker, socket, receipts tree and screen seam carry a second kind of entry: the
**runtimes**, the `kind = "service"` manifest rows — the five `buzz-agent@<name>` user units.
Their id on the wire is the read-model id (`workflow_id: "buzz-agent@marcus"`), so the receipts
land under `/var/lib/control-room/receipts/buzz-agent@marcus/` and the page's *last action*
reads them with the same reader. The allowlist gains a `runtimes` table (schema still 1; a file
without the table is valid and knows no runtime, so a stale render refuses runtime requests as
`unknown_workflow` rather than refusing everything; a malformed entry is `allowlist_invalid`):

```json
"runtimes": {"buzz-agent@marcus": {"owner": "marcus", "unit": "buzz-agent@marcus",
                                   "scope": "user", "template": "buzz-agent@.service"}}
```

rendered from every standing `kind = "service"` entry whose template unit exists under
`systemd/user/` (`status = spent` rows and units with no service file stay in `excluded`).

**The verbs are the session verbs** — what `systemctl --user start|stop|restart` does — and the
screen labels them *Start agent now* / *Stop agent now* / *Restart agent now*. The unit file's
enable state is a fact the card shows as `boot: enabled|disabled` and nothing on the screen
changes it: a Start on a disabled unit is session-only and does not survive a reboot, a Stop on
an enabled one comes back at the next boot, and both dialogs say so. A workflow verb on a runtime
(or a runtime verb on a workflow) is `unknown_action` naming the right vocabulary.

| action | precondition (refusal) | systemctl (`--user --machine=dave@.host`) | extras |
|---|---|---|---|
| `start` | `confirm: true`; not active/activating, else `state_conflict` | `start --no-block <unit>.service`, then poll `show` ≤ 6 s | `note` when the unit is `failed` or `activating/auto-restart` inside the window, naming `NRestarts`, `journalctl --user -u <unit>` and `check-loaded.sh` |
| `stop` | `confirm: true`; non-empty reason; active/activating, else `state_conflict` | `stop --no-block <unit>.service` + poll ≤ 15 s | as workflow stop |
| `restart` | as stop | `restart --no-block <unit>.service`, wait out `deactivating` (≤ 15 s), then the start poll | as start; a stop half still running at 15 s is noted, never receipted as `paused` |

The settle window is `START_SETTLE_SECONDS` (`RestartSec=5` in the template + 1;
`--start-settle` / `CONTROL_BROKER_START_SETTLE_SECONDS`, 0 in the suite). A runtime whose
credential the relay refuses starts cleanly and dies into `Restart=on-failure`, so the receipt is
`applied` with `after.state = active` (activating counts) and the note is the tell — read the
journal before clicking again. `before`/`after` carry `{state, fingerprint, units: [{unit,
scope, timer: null, service}]}` with the screen's four-value `state`, and `links.agent =
/agents/<owner>`. The page's *last action* is the API's summary of the newest non-preview
receipt (`ControlReceipts._seam`: result, action, refusal code, note, before/after as states,
actor, receipt id) — not the receipt file; the SPA parses that shape (`lastActionSchema`), which
from T5.3e until T5.3g it did not, so every workflow page read "No control action recorded."

**The broker reads `RUNTIME_PROPERTIES` and nothing else** — `ActiveState, SubState,
UnitFileState, LoadState, Result, InvocationID, ExecMainStartTimestamp, ExecMainExitTimestamp,
NRestarts`. It never runs `systemctl status` and never reads `ExecStart` or `Environment`: the
launched process carries the agent's private key in its argv (`~/CLAUDE.md` § fleet MCP bridge),
and a receipt is world-readable. `tests/test_control_broker.py` pins both on every runtime
receipt and `tests/acceptance/control_room_controls.sh` step 4b on the live root copy.

**Required-by is a notice, not a refusal.** Stopping `buzz-agent@augustus` while
`augustus-content` is enabled is allowed; the dialog names the dependents in amber, and the
dependent's next run is a one-second BLOCKED receipt plus a `dependency-down` exception (T5.3f).
The broker stays ignorant of `requires`.

**Double hosting** is the one risk the screen cannot see: if Buzz Desktop on the Mac is also
hosting the identity, both reply to every mention and `check-loaded.sh` reports all-OK. The
Start dialog says so; the verification after any Start or Restart is
`~/.config/buzz-team/check-loaded.sh` from a shell.

CLI form, refusal-only (no `--confirm` → `confirmation_required`, no state read):

```bash
sudo /usr/bin/python3 /usr/local/lib/control-room/control_broker.py act start buzz-agent@marcus
```

**Land sequence** — the T5.3a root install lines again, because both root files change:

```bash
bin/deploy
sudo install -D -o root -g root -m 0755 bin/control_broker.py /usr/local/lib/control-room/control_broker.py
python3 bin/control_broker_allowlist.py render > /tmp/allowlist.json \
  && sudo install -D -o root -g root -m 0644 /tmp/allowlist.json /etc/control-room/allowlist.json \
  && python3 bin/control_broker_allowlist.py check
sudo systemctl restart control-room.service              # the broker is per-connection; nothing else restarts
bash tests/acceptance/control_room_controls.sh            # refusals only; no agent starts
```

## Control Room proposals (T5.3b)

**A schedule change or a retirement is a pull request, never an edit.** `Change schedule…` and
`Retire…` on a workflow page produce a branch `control-room/<kind>-<workflow_id>-<UTC stamp>` in a
dedicated bare clone of origin and a PR through `gh pr create`. Nothing here writes
`~/dev/agent-workforce`, `~/agent-workforce`, `/etc` or `main`; nothing merges, force-pushes,
deploys or runs a mutating `systemctl`. **The fleet stays off** — a schedule change applies at
resume (T5.3a's moment), and a retirement's units are already disabled when the PR is merged.

**Two stages, one identity.** `preview` builds the branch in a worktree, records the diff's
sha256, runs the check bundle and answers with the diff, the checks, the residue tables and
`submit_allowed`. `submit` rebuilds the plan under the preview's proposal id, refuses
`preview_stale` unless the bytes match (30-minute token), pushes the one branch and opens the
PR. A red hard check refuses `checks_failed`; a red *pinned* suite (one that names the unit) is
accepted only with `acknowledge_pinned_tests` and opens a draft with a "Red on purpose until"
section. Every request — previewed, submitted, refused, failed — writes one record under the
state root with every git/gh argv; `stage: "list"` and `bin/workflow_pr.py list <id>` read them.
The reason and the retention note are **one line each** (`bad_request` otherwise): both land in
a manifest comment and a TOML string. Submit re-plans with the preview's clock, so a preview at
23:58Z submitted at 00:02Z still matches. A submit that fails *after* its push (a `gh pr create`
error) leaves the branch on origin with no PR; the next submit for that workflow is refused
`open_proposal_exists` naming it — open its PR by hand or delete it
(`gh api -X DELETE repos/<repo>/git/refs/heads/<branch>`), then submit again. Nothing in the
worker deletes a remote branch.

**Where it runs.**

```
Mac browser ──tailnet──▶ control-room.service (dave, ProtectHome=read-only)
                           │  bin/control_room_proposals.py: shape, peer gate, actor, HTTP map
                           ▼  bin/workflow_pr.py: the worker (lock, worktree, plan, checks, record)
                         /var/lib/control-room-proposals/   (StateDirectory; the drop-in)
                           ├─ repo.git      bare clone of origin, fetch main + push control-room/* only
                           ├─ work/<pid>    the proposal worktree, removed after each stage
                           └─ proposals/    one JSON record per request
```

The state root is `CONTROL_ROOM_PROPOSALS_ROOT` (`systemd/control-room.service.d/proposals.conf`
sets it, plus the remote, the gh repo and the git author). Health: `bin/workflow_pr.py doctor`
(state root writable, `repo.git` present and its origin, `ls-remote main`, `git`/`gh`/
`systemd-analyze` on PATH, `gh auth status`, the timezone). First run: `bin/workflow_pr.py init`
from the dave shell the drop-in describes. The CLI mirrors the dialog — `schedule <id>
--on-calendar S [--delay D] [--persistent yes|no] [--trigger U] --reason R --preview|--submit
TOKEN`, `retire <id> --reason R --receipts V --notion V --inbox V --note N --preview|--submit
TOKEN` — and is the acceptance path (`tests/acceptance/control_room_proposals.sh`).

**Landing a schedule PR (Dave, by hand — the PR body carries the same list):** merge → `git -C
~/dev/agent-workforce pull --ff-only` → `bin/deploy` → `sudo cp systemd/<unit>.timer
/etc/systemd/system/ && sudo systemctl daemon-reload` → only if that timer is active, `sudo
systemctl restart <unit>.timer`; it is paused today, so the new schedule applies at resume →
`bash bin/verify.sh`.

**Landing a retirement (Dave, by hand):** merge → pull → `bin/deploy` (ships `systemd/archive/`)
→ `sudo systemctl disable --now <unit>.timer` (a no-op while the fleet is off; it is the
retirement, not a fleet change) → `sudo rm /etc/systemd/system/<unit>.{timer,service} && sudo
systemctl daemon-reload && sudo systemctl reset-failed` → `ls -l` then `rm` the deny-listed
`~/.config/agent-workforce/<job>.env` (no agent stats it; the PR says `unverifiable from an
agent`) → `bin/deploy --prune` → `bin/workflow_pr.py clear <id> [--env-removed] --pr <url>`
→ commit the registry line it writes → `bash bin/verify.sh`.

**Prune cannot be aimed.** `bin/deploy --prune` deletes *everything* source no longer carries,
so the PR's `deploy-preview` check lists what else the prune would take (the deferred entries in
`design/deploy-exclusions.toml`), and the retirement adds its own files there so the deployed
copies wait for the prune instead of failing the drift check on the branch.

**Count literals move with the entry, in every file that pins one.** Three suites pin a
count a retirement changes, and the plan decrements each by that file's own rule, then pins the
suite so the preview proves the new number: `tests/test_control_room_views.py`
(`STANDING_ENTRIES`, `LOGICAL_WORKFLOWS`, by value against `count_literals`),
`tests/test_receipt_coverage.py` (`EXPECTED_TALLY["<class>"]` under the producer class the
retired unit's `ExecStart` basename decides against that suite's own `SELF_RECEIPTING` —
`scheduled` for an `agent_propose.sh` job, `sweep` for a plain timer — and
`LOGICAL_WORKFLOWS` by one) and `.claude/workflows/ship-dev-plan.js` (`WORKFLOW_ENTRIES`, one
per manifest entry, whatever its status). A dormant or spent entry was never a standing row, so
only the last moves. Until 2026-09-18 the plan bumped the views suite alone and CI went red on
the other two after every retirement (`cfd42e1`, `7a535b4`).

**The registry is the fail-closed half.** The PR appends a `[[retired]]` entry to
`design/retired-workflows.toml` with the whole subject set (units, runners, profiles, contract,
suites, env override, run markers, retention) and `residue_cleared_on = ""`.
`tests/test_workflow_retirements.sh` is **red by design between merge and cleanup**: on the box it
scans the deployed trees and the installed units (`bin/workflow_retire_residue.py --live`) and
fails naming each pending item and the `clear` command; off the box that group skips out loud.
`clear` re-runs the live scan, refuses while residue remains, and stamps the entry when the box
is clean. The W19 table the scanner renders (`| # | residue | tree | has a check? | who clears it
| how |`) is the same shape the 2026-09-11 retirement audit used, so the next audit reads the
registry instead of the box.

## S1 — the Buzz interactive surface (brief 7, 2026-09-03)

The five `buzz-agent@*` `--user` units. Their **mechanism** files have a source here
(`buzz-team/`) as of 2026-09-03; their **charters** do not and will not — those live in the
deny-listed `~/.config/buzz-agents/` tree, and `profile_in_repo = false` in each manifest is
how that is declared rather than assumed.

Every turn is receipted (T5.2): `buzz-team/agent-settings.json` declares a Claude Code `Stop`
hook running `bin/interaction_receipt.py`, which reads the turn from the transcript and writes
one receipt under `var/workflow-receipts/buzz-agent@<name>/`; augustus, on codex-acp, gets the
same writer from codex `notify` (`--codex-notify`, in `~/.config/codex-agents/augustus/config.toml`,
outside this repo — a **top-level** key, so it sits above the first `[table]` header; appended
at the end of the file it lands inside `[features]` and never fires. Landed 2026-09-15 with a
`.bak-prenotify-2026-09-15` beside it). The hook never blocks a stop: exit 0 on every path,
nothing on stdout, one line in `logs/interaction_receipt.log`.

### The loop

```
edit buzz-team/<file>
  ->  bash bin/deploy_buzz_team.sh --dry-run      # what would change
  ->  bash bin/deploy_buzz_team.sh                # converge; RESTARTS NOTHING
  ->  systemctl --user restart buzz-agent@<name>  # by hand, per agent — see below
  ->  bash bin/verify.sh                          # drift + the S1 suites
  ->  ~/.config/buzz-team/verify-fleet.sh         # machine-level gate, ~/CLAUDE.md owns it
```

**`bin/deploy_buzz_team.sh` is not `bin/deploy`, and adding `buzz-team` to `bin/deploy`'s
`PATHS` is the wrong fix.** That script's three destination guards are specific to the
runtime tree; this one has its own (the five rule files must already exist in the
destination, the destination must not be a git tree, and source must not equal destination).
The adopted list comes from `buzz-team/MANIFEST.toml`, never from a glob, so a file added to
the directory without being declared is not silently shipped.

**Nothing restarts on its own, and the converge says so on every run.** A rule file is read
**at process start only** — an edited `.toml` sits unread while you re-debug the symptom you
already fixed. Prove the running process loaded it before concluding a fix did not work:

```bash
stat -c %y ~/.config/buzz-team/marcus.toml
systemctl --user show buzz-agent@marcus -p ExecMainStartTimestamp
```

If the file is newer, you have not tested the fix yet.

**A malformed filter expression crash-loops the unit.** Filter compilation is *eager*, so a
bad rule is not one that silently never matches — it is an agent that will not stay up. That
is the safe direction, and it is why an edit here is a restart rather than a reload. Restart
one agent, confirm it is up, then move to the next; do not restart all five at once.

### Which gate owns what

| Question | Gate | Where it runs |
|---|---|---|
| Does the dispatch DAG still have the shape it claims? Does every rule require a mention? Is there key material in `buzz-team/`? | `tests/test_buzz_interactive_harness.sh` | `bin/verify.sh`, anywhere |
| Do the source route table and the live `TEAM.md` agree about event kinds? | `buzz-team/check-team-kinds.py` | `bin/verify.sh`, box-gated |
| Does the box match the source? | `bin/check_deploy_drift.sh` (fifth tree) | `bin/verify.sh`, box-gated |
| Are the five processes' *runtime* knobs what the design says — isolation flags from `/proc`, connector denies, secret-path containment? | `~/.config/buzz-team/verify-fleet.sh` | by hand; `~/CLAUDE.md` § Verification |
| Does each agent's rendered capability set (settings file, shim, wrapper flags, aurelian's denies) still equal its manifest? | `tests/test_fleet_capabilities.sh` | `bin/verify.sh`, anywhere |
| Is the deployed wrapper the strict one, and does every deployed per-agent settings file carry the base deny? | `tests/test_fleet_guards.sh` | `bin/verify.sh`, box-gated |
| Is each live session wired to its own settings, skills and bridge shim, and does each shim offer exactly its manifest's families — from the host and, for augustus, inside his namespace? | `verify-fleet.sh` gates 14 and 15 | by hand |
| Does any process in a unit's cgroup carry the agent's private key in its argv, and is the `claude` child's `--mcp-config` a 0600 runtime file naming only the bridge? | `verify-fleet.sh` gate 14 (`14/argv`, `14/mcp-config`) | by hand |
| Does the wrapper file the adapter's `--mcp-config` JSON instead of passing it, do the coders' settings enable the shared plugin, and is the managed file the base's path denies and nothing else? | `tests/test_fleet_capabilities.sh` sections 3, 10, 11 | `bin/verify.sh`, anywhere |
| Is `/etc/claude-code/managed-settings.json` the committed render? | `bin/check_deploy_drift.sh` (eighth comparison) | `bin/verify.sh`, box-gated |
| Are the three harness packages current on npm? | `check-loaded.sh` `INFO` rows from `bin/adapter_versions.py` | by hand; never red |
| Did the running process read the config, and do the credential halves match? | `~/.config/buzz-team/check-loaded.sh` | by hand; reports `STALE` / `BADAUTH` |
| Is a deployed settings file, shim or wrapper newer than the oldest live `claude` session that should have read it? | `verify-fleet.sh` gate 7 (`7/fresh-config`, since 2026-09-19) | by hand; a deploy without a restart is red here |
| Can an agent actually **complete a turn**? | `fleet-turn-check.service` | hourly, on the box |
| Is a session **re-prompting itself** — more than 3 turns an hour with `origin = scheduled` (CronCreate, `/loop`) and no relay event behind them? | `fleet-turn-check.service` gate 5 over the receipts, through `bin/turn_rate.py` | hourly, on the box; alerts like any FAIL |

The split is not arbitrary. Rows 1–3 are decidable from a checkout, so they belong in the PR
gate. Rows 4–5 need live `/proc`, a live relay and the deny-listed tree — running them from a
gate would make a PR red for box state rather than for the diff. Row 6 costs a real model
turn. Adoption made the code reviewable; it did not make the runtime assertable.

### Capability isolation — per-agent skills and tools (2026-09-18)

Until 2026-09-18 every Claude agent's `claude` child ran with the adapter's own
`--setting-sources user,project,local` and no `--strict-mcp-config`, so a session loaded
**Dave's** user scope: his MCP servers (`brave-search` with his key in the child's env,
`graft`, `google-docs`, `qmd`, the project-scoped `HA` — the agents' cwd is `~`), the
`shared@jbuitenhuis` plugin's `context7` / `linear`, his `~/.claude/skills/`, and every
claude.ai connector the five-name deny did not name — Eden's `publish_post_now` included.
None of the five was offered a pointer skill. Measured on the live cgroups: 15 MCP servers,
78 tools and 63,912 prompt tokens per request before; the bridge only, 45 tools (aurelian
33) and 34,593 after.

**One source, one renderer.** `design/agents/<name>.toml` declares it —
`[surfaces.interactive]` `tools` (the builtin family), `tools_deny`, `bridge_tools`
(`qmd` / `notion` / `brave`), `mcp = ["buzz-team-mcp"]`, and the `buzz-agent@<name>`
workflow entry's `skills` + `skills_mechanism` (`acp-wrapper` or `codex-home`). From that
`bin/fleet_capabilities.py render` writes, and `check` proves committed == rendered:

- `buzz-team/agent-settings-<name>.json` (four, Claude harness only) = the base
  `agent-settings.json` (connector deny, the cloud-scheduling deny, the Stop receipt hook)
  ∪ `tools_deny` ∪ the tool
  names of every bridge family the agent is *not* given, under his own namespace.
- `buzz-team/buzz-team-mcp-<name>` (five), a two-line shim that execs
  `buzz-team-mcp.py --agent <name> --tools <families>`. The unit passes `--mcp-command
  %h/.config/buzz-team/buzz-team-mcp-%i`, because buzz-acp hands the server `args: []` and a
  fixed env and codex sanitises the env to `BUZZ_* HOME LANG LOGNAME PATH SHELL USER` — the
  command *path* is the only seam both harnesses carry through. The server name is the
  file stem, so tools are `mcp__buzz-team-mcp-<name>__*`; `--tools` filters `tools/list`
  and refuses a `tools/call` outside the set. Policy is still the broker's — the filter is
  what the *harness* offers, not what a shell talking to the socket could do.

**The Claude side is enforced by `buzz-team/claude-agent-wrapper.sh`**, which appends,
*after* `"$@"` so it wins the adapter's single-value flags: `--strict-mcp-config`
(only the adapter's `--mcp-config`, i.e. the bridge), `--setting-sources=` (nothing of
Dave's — `project,local` would not do: with cwd `~` the project settings file *is*
`~/.claude/settings.json`), `--settings ~/.config/buzz-team/agent-settings-$BUZZ_AGENT_NAME.json`
and `--plugin-dir ~/agent-workforce/skills/$BUZZ_AGENT_NAME`, behind the runners'
readability guard (a missing plugin dir is silent otherwise). The unit sets
`BUZZ_AGENT_NAME=%i`; the wrapper refuses to exec without it or without its two files.
`~/CLAUDE.md` and the shared auto-memory pool still load — they are not settings.

**The private key is not in the `claude` argv (2026-09-19).** The adapter passes
`--mcp-config <json>` with the bridge's env inlined, `BUZZ_PRIVATE_KEY` included, and
`/proc/<pid>/cmdline` is world-readable where `environ` is not — measured on all ten live
children. The wrapper now writes that JSON 0600 to
`$XDG_RUNTIME_DIR/buzz-team/mcp-<agent>-<session-id>.json` and passes the path; an
unwritable dir refuses rather than falling back; `buzz-acp-launch.sh` clears the agent's
files at unit start. Gate 14 counts the key in every cgroup argv (host and augustus's
namespace) and reads the filed config's server names, never its content. Claudius's research
put this one process too high — his "non-systemd buzz-acp with `--private-key`" was his own
`pgrep -f` matching the shell that ran it; every `buzz-acp` takes the key from env.

**Managed settings carry the credential-path deny, and only that (2026-09-19).**
`/etc/claude-code/managed-settings.json` is rendered by `bin/fleet_capabilities.py` from the
base's twelve `Read(//…)` / `Edit(//…)` rules and root-installed by hand (the drift check's
eighth comparison names the `sudo install` line). Claude Code applies it to every session on
the box whatever `--setting-sources` or `--settings` say — so the deny that S1 gets by flag
can no longer be dropped by flag, by the fleet or by a future `claude -p`. Fleet policy
(connector denies, `Skill(schedule)`) stays out of it on purpose: the same file binds Dave's
interactive sessions and the nine scheduled runners, which is where the research proposal
was wrong in scope. `tests/test_fleet_capabilities.sh::managed-settings-paths-only` holds
the line.

**The shared plugin rides with whoever builds or reviews software (Dave, 2026-09-19).**
trajan, marcus and aurelian declare `plugins = ["shared@jbuitenhuis"]`; the renderer writes
`enabledPlugins` into their settings files, and Claude Code resolves the plugin from
`~/.claude/plugins/installed_plugins.json` at session start — Dave's installed version, so
his `claude plugin update` reaches them at their next session. Measured before wiring:
under `--setting-sources=` the plugin's seven `shared:*` skills load and its SessionStart
hook prints `# Coding Standards`; under `--strict-mcp-config` its `context7` / `linear`
servers do **not** load, so the one-MCP-server invariant holds. claudius has no plugin
(research); augustus cannot (codex). `shared:*` never appears in a receipt's `offered` —
that field is the governed pointer offer.

**Augustus (codex-acp)** gets his skills through
`~/.config/codex-agents/augustus/skills/praetorium -> ~/agent-workforce/skills/augustus/skills`,
a symlink codex follows (rendered `praetorium-augustus:<name>`), hand-installed like a unit
and asserted live by gate 15. There is no `--settings` on that harness; his tool set is the
shim's filter plus codex's own sandbox.

**Aurelian is enforced as declared:** `Edit`, `Write`, `NotebookEdit` and the seven
`notion_*` are denied in his settings file, `Bash` stays; the two `enforced = true`
must-nots in his manifest name `tests/test_fleet_capabilities.sh::aurelian-deny-as-declared`
and `::bridge-filter-matches-manifest`.

**Offer is measured per turn.** Every interaction receipt carries a `skills` block
(`offered` / `invoked` / `read`, `measured` or `unavailable`): from the transcript's skill
listing and `Skill` / `Read` calls on Claude, from the rollout's `<skills_instructions>`
message and shell commands naming a `SKILL.md` on codex. `bin/scorecard.sh` folds it into
the T3.3 table beside the S2 `cost.log` figures, so "offered but never read" is answerable
per surface.

**Claude Code's bundled skills are in every listing and outside the manifest** — `init`,
`simplify`, `loop`, `schedule`, `security-review` and the rest ship inside the binary, so
`--setting-sources=` cannot drop them and the receipt's `offered` and `invoked` (both
namespace-filtered) never list them — a blocked attempt leaves no receipt trace. One is
denied in the base settings (`Skill(schedule)`, 2026-09-19): it creates claude.ai cloud
scheduled runs from inside an agent session, which is scheduling the box does not own. The
skill is only the instructions; the capability is the deferred `RemoteTrigger` tool it
loads through `ToolSearch`, and with the skill alone denied that tool was still loadable
and callable under `bypassPermissions` (measured the same day, `#58`'s review) — so the base
denies both names, and `tests/test_fleet_guards.sh::schedule-deny` pins both in the base
and in every deployed per-agent file. A scoped deny blocks at call time and does not
delist: `schedule` stays in the session's listing, and an agent that tries it reads
"blocked by permission rules". The class-level lever exists — `disableBundledSkills: true`
in the settings file drops all thirteen and leaves the pointer skills — and **Dave decided
against it (2026-09-19): the bundled skills stay**, `loop` included; only the cloud-scheduling
pair is denied, so a future release that adds a bundled skill adds it to the agents too, and
that is the accepted cost. What stays open is the *in-session* scheduler — `CronCreate`, what
`/loop` runs on — which claudius proved the same afternoon with a one-shot that fired at
14:21Z. Its fire lands in the transcript as an `isMeta` user record with
`turnOrigin: scheduled`; since 2026-09-19 `bin/transcript_reader.py` starts a turn there, so
the receipt begins at the fire, carries no handoff and says `origin: scheduled` (before that
it folded into Dave's last prompt and was receipted under his event). The alarm on the effect
is `fleet-turn-check.sh` gate 5: more than `FLEET_UNOWNED_MAX` (3) such turns in
`FLEET_RATE_WINDOW_MIN` (60) minutes is a FAIL — a deny on the tool would leave Bash, which
does the same and survives the session. Claudius's 10:19Z DM reply of that day named the
full list.
The `shared:*` plugin skills on the three coders are likewise outside `offered`.

The loop for a change here is the S1 loop above with one step in front: edit the manifest,
`bin/fleet_capabilities.py render`, then `bin/deploy_buzz_team.sh`, restart the agent, and
`verify-fleet.sh`. A change to the vault's skill `description` is
`bin/pointer_skills_sync.py render` then `bin/deploy` — see `skills/README.md`.

### Harness versions — the watch and the canary (2026-09-19)

`check-loaded.sh` prints one `INFO` row per package from `bin/adapter_versions.py`
(`@agentclientprotocol/claude-agent-acp`, `@agentclientprotocol/codex-acp`,
`@anthropic-ai/claude-code`: installed vs npm latest), never a verdict — a stale adapter is
a decision. On 2026-09-19 it read 0.64.0 vs 0.79.0 and 1.1.9 vs 1.12.0, found by claudius's
research with nothing on the box saying so. Upgrading is the fleet-upgrade shape
(memory `praetorium-fleet-upgrade-shape`) on npm:

1. Install the new version under a side prefix (`npm i -g --prefix ~/.local/lib/acp-<v>
   <pkg>@<v>`); never over the global copy first.
2. Point **aurelian** at it with a unit drop-in (`BUZZ_ACP_AGENT_COMMAND=` a shim exec'ing
   the side copy), restart him, DM him by pubkey.
3. On his live child read gate 14: the four flags still after `"$@"`, `--mcp-config` filed,
   no MCP child but the bridge, no key in any argv — the seam is `CLAUDE_CODE_EXECUTABLE`,
   read by claude-agent-acp itself (`dist/acp-agent.js:230` at 0.64.0), and if a release
   drops it the wrapper is bypassed and gate 14 says so. Read his journal in full.
4. Global install by rename-into-place, drop the drop-in, restart the other three when idle
   (the child is the session; read the last `stop_reason` first). codex-acp the same way
   with augustus as his own canary. Rollback is the side prefix.

### Three failures that are silent by construction

Full detail, each with its evidence, is `design/contracts/buzz-interactive.md`. In short:

1. **buzz-acp never auto-publishes.** A turn that computes an answer and ends publishes
   nothing and still reports `ok`. Only `buzz messages send` publishes. `fleet-turn-check` is
   the only thing that catches it.
2. **The kind belongs to the destination.** A kind-9 post into a forum channel is accepted by
   the relay, receipted `ok`, and rendered to nobody. `bin/buzz_routes.env` is the owner;
   `TEAM.md` follows it.
3. **An unresolved mention is sent with no `p` tag.** It reaches the channel addressed to
   nobody and looks exactly like a dead unit. Check the event's `tags` — and note the
   read-back trap: `buzz messages get` has no `p_tags` field and no `reply_to` field, so a
   checker reading those invented names prints empty and imitates the real failure.

And one that is not silent but reads as unrelated: `journalctl --user -u buzz-agent@<name>`
logs **lifecycle only** — start, shutdown, subscribe, reconnect — never a line per message.
A silent journal during a live turn is the normal case. Prove work by `CPUUsageNSec` against
an idle sibling, not by the absence of log lines.

## Daily rhythm jobs — daily plan + EOD summary (NUC-45)

Both jobs moved off Mac launchd, where they silently no-opped whenever the laptop was
asleep (3 of the 7 weekdays before 2026-07-27 had no morning plan at all, and nothing was
written to either Notion DB after 07-24). **Notion is the durable artifact; the canonical
vault write stays Mac-side** — the box never writes `07_daily/logs/`, on any branch.

| | Daily plan | EOD summary |
|---|---|---|
| Timer | `praetorium-daily-plan.timer`, Mon–Fri 06:00 | `praetorium-eod-summary.timer`, daily 22:15 |
| Runtime | `bin/run_daily_plan_cc.sh` | `bin/run_eod_summary_cc.sh` |
| Notion row | `<date> — Daily Plan` in Daily Plans | `<date> — EOD Summary` in Daily Plans **and** `<date>` in Daily Log |
| Local artifact | `~/logs/daily-plan/daily-plan-<ts>.md` + `receipt-<date>.json` | `~/logs/eod-summary/eod-summary-<ts>.md` + `receipt-<date>.json` |
| Buzz `ops` | `ExecStartPost=deliver_report.sh` (`REPORT_DIR`/`REPORT_GLOB`/`REPORT_SUBJECT` per unit) | same |

Both entrypoints are thin wrappers over `bin/run_daily_rhythm_cc.sh`, which owns the
vault freshness gate and the headless Claude Code invocation (box subscription, `$0`
OpenRouter spend, `--strict-mcp-config` with an empty MCP config, no web tools).

**The idempotency key is the row title**, owned by `bin/notion_daily.py`. Re-running a job
for the same date updates that row and *replaces* its block body — it never stacks a
second row. That is also what lets Dave's interactive `eod-wrap` overwrite the box's row
later the same day instead of duplicating it.

**Verify command.** Exit code is not evidence: the runtime exits 0 when a provider error
becomes the agent's final response (observed 2026-07-21). `notion_daily.py` writes its
receipt only after Notion accepts the upsert, and `AGENT_VERIFY_CMD` asserts a receipt
newer than `$AGENT_RUN_STARTED_AT`, so yesterday's receipt cannot satisfy today's run.

**What a failure looks like.**

| Symptom | Cause | Fix |
|---|---|---|
| Unit failed, journal says `REFUSING to run` | `vault_sync_guard.sh check` refused: `~/vault` is dirty or lagging `origin/main` by >24h | Route the named drift (see below), then re-run by hand |
| Unit failed, log says `AGENT_VERIFY_CMD found no artifact` | the agent produced no Notion write | Read `logs/last-attempt/<task>.log` — this run's own output, the only file attributable to it — then `logs/agent_run.log` for history; do **not** trust the exit code |
| No Buzz message, unit green | `deliver_report.sh` is fail-soft | `~/logs/deliver_report.log`, then the receipt in `~/logs/delivery-receipts.jsonl` |
| Two rows for one date | something wrote Notion outside `notion_daily.py` | Archive the duplicate; keep the title-keyed path |

Re-run either job by hand (same guarded path as the timer):

```bash
systemctl start praetorium-daily-plan.service
journalctl -u praetorium-daily-plan.service -n 50 --no-pager
```

### Vault freshness gate — `bin/vault_sync_guard.sh`

The mirror froze silently for four days (2026-07-23 → 07-27) because `qmd-refresh`'s
inline `git pull --ff-only || echo "... (offline?)"` treated a **rejected** pull like an
offline blip: the unit exited 0, systemd logged `Finished`, no `OnFailure` fired, and qmd
happily re-indexed a stale tree while every health check read green. A local edit to
`00_system/tools/agent_inbox.py` had been blocking the fast-forward on every single run.

The guard splits those two events apart:

- `sync` (used by `qmd-refresh.service`) — fetch + fast-forward. Genuine offline stays
  **soft** (exit 0, reindex what we have). A **rejected** fast-forward is a hard failure
  that names the blocking files and fires `OnFailure=agent-alert@`. It discards nothing.
- `check` (used by both daily jobs, before the agent launches) — refuses on a dirty tree,
  or when the mirror lags `origin/main` by more than `--max-lag-hours` (default 24), or
  when origin is unreachable *and* the last confirmed sync is older than that. A stale
  mirror must produce a loud absence, never a confident wrong plan.

Untracked files are reported but never block: they cannot make a briefing wrong and cannot
stop a fast-forward. Tracked modifications do both.

Because git rewrites `FETCH_HEAD` even when a fetch fails, the guard keeps its own
`.git/vault_sync_guard_last_fetch` stamp as the witness for "origin was last reachable".

## What must be backed up (inventory)

| Asset | Where | Backup path |
|---|---|---|
| Service units (`--user`) | Every `.service`/`.timer` in this repo's `systemd/user/` that is installed under `~/.config/systemd/user/` — the nine Buzz-fleet and gateway units. Their drop-in `*.conf` files are **not** captured: three carry `BUZZ_AUTH_TAG` and this tarball is the no-secrets one | `backup_config.sh` tarball |
| Service units (system) | Every deployed `.service`/`.timer` whose name matches a unit in this repo's `systemd/` (incl. `agent-workforce-auto-sync`, `overnight-*`, `agent-alert@`, `agent-inbox-sync` alongside the qmd/agent-proposal/augustus/bd-stall/brave/memory/scorecard/discord families) — enumerated automatically by `backup_config.sh` | `backup_config.sh` tarball |
| Scripts & docs | `~/agent-workforce/{bin,docs,profiles}` | `backup_config.sh` tarball |
| Job-override templates | this repo `profiles/*.env.example` | git |
| Job-override runtime envs | `~/.config/agent-workforce/{augustus-content,bd_stall_radar,weekly_pre_assembly}.env` | **not secrets**, but recreate from templates if lost |
| qmd config | `~/.config/qmd/index.yml` | `backup_config.sh` tarball |
| Secrets template | `~/.config/agent-workforce/.env.example` + README | `backup_config.sh` tarball |
| Brave MCP key | `~/.config/agent-workforce/brave-mcp.env` (mode 600) | **NEVER backed up** — re-derive from `secrets.env` `BRAVE_API_KEY` |
| Secrets values | `secrets.env`, deploy key | **NEVER backed up** — re-issued at providers (see `~/.config/agent-workforce/README.md`) |
| Vault content | GitHub `Dave1524/obsidian-ai-os-boxsafe` | already remote; clone is disposable |
| qmd index/embeddings | `~/.cache/qmd` | disposable — rebuilt by `qmd update && qmd embed` |

Run `~/agent-workforce/bin/backup_config.sh`, then pull the tarball to the Mac:
`scp praetorium:~/agent-workforce/backups/<latest>.tar.gz ~/backups/praetorium/`

## Rebuild checklist (fresh Ubuntu → working box)

1. Install Ubuntu Server LTS headless; create user `dave`; enable SSH (NUC-02/03 pattern).
2. Join Tailscale (`tailscale up`), confirm Mac SSH; UFW default-deny + 22/tcp (Tailscale-only net).
3. `sudo apt install git curl xz-utils nodejs npm && sudo npm i -g @tobilu/qmd`.
4. Do **not** install Hermes or Ollama — both left the box 2026-09-18 (Hermes tree archived
   at `~/OUTBOX/hermes-tree-retired-2026-09-18.tgz`); nothing in this repo execs either.
   - **Fetch backend (NUC-22):** install local headless Chromium once (credential-free):
     `npx --yes agent-browser@latest install` (as `dave`) then
     `sudo npx --yes playwright install-deps chromium`.
5. Restore the config tarball over `$HOME` and `/etc/systemd/system/` (or rsync from this repo of scripts).
   Install **system** units from `systemd/` including job timers (`augustus-content`,
   `bd-stall-radar`, `weekly-pre-assembly`) and `qmd-mcp.service.d/gpu.conf`.
   Then install the **`--user`** units from `systemd/user/` into `~/.config/systemd/user/`
   (`systemctl --user daemon-reload`, then `enable --now` the timers). This step is the whole
   reason D8 exists: it restores `/etc` from the tarball and `systemd/`, so any unit with no
   source in this repo is simply gone afterwards and nothing reports its absence. Until
   2026-09-02 that was the entire Buzz fleet.
   Re-create the drop-in `*.conf` files under `~/.config/systemd/user/*.d/` by hand — they are
   not in the tarball and not in git. The three `auth.conf` files are credentials and are
   re-issued, not restored (`~/.config/buzz-agents/PROVISIONING.md`).
   Finish with `bash bin/check_deploy_drift.sh` — a rebuild is not done until it is clean.
6. Recreate secrets per `~/.config/agent-workforce/README.md` (new deploy key → register on repo,
   new OpenRouter key → re-apply spend cap). Then re-derive the Brave MCP env:
   `umask 077; grep -E '^BRAVE_API_KEY=' ~/.config/agent-workforce/secrets.env > ~/.config/agent-workforce/brave-mcp.env`.
   Install job-override envs from `profiles/*.env.example` (mode 600) — see § Job wiring.
7. `~/agent-workforce/bin/finish_boxsafe_clone.sh` (clone, index, exclusion gates, enable services).
   - Enable the added units (NUC-21/22/23): `sudo systemctl enable --now brave-mcp.service
     scorecard.timer` (`memory-consolidation.timer` was retired at T6.1, 2026-09-16). Leave
     `agent-proposal.timer` per its spend gate.
   - Job timers (`augustus-content.timer`, etc.) enable only when the matching override env exists.
8. Verify: `~/agent-workforce/bin/praetorium-status.sh` — all green; run `llm_smoke_test.sh`.

## Restore-path test log

- 2026-07-06: config tarball created, extracted to a scratch dir, and diffed against live files —
  restore path verified (see NUC-19 card for the transcript reference).

## Research capabilities (NUC-16 / 21 / 22)

The `claudius` profile reaches three services, all via warm localhost transports:

- **qmd (vault memory, read-side):** `url: http://127.0.0.1:8765/mcp` → `qmd-mcp.service` (NUC-16).
  The daemon persists the embedding model; the profile's per-call timeout is 300s so the one-time
  post-restart cold-load (~134s on CPU) never trips it. Status: `praetorium-status.sh` → "qmd MCP daemon".
- **Brave search:** `url: http://127.0.0.1:8766/mcp` → `brave-mcp.service` (NUC-21), key in
  `brave-mcp.env`. Persistent HTTP replaces the per-run npx stdio cold-spawn that lost the
  `hermes -z` background-discovery race. Status → "Research MCP (Brave)" (service + endpoint).
- **Web fetch:** retired with the Hermes runtime (T6.1, 2026-09-16); the CC runners use their
  own fetch. The local headless Chromium (agent-browser, NUC-22) stays installed for it;
  health: `praetorium-status.sh` → "Fetch backend (browser)" shows `chromium: installed`.
  Egress rules: `docs/data_boundary.md`.

**Captured evidence (2026-07-08, AC4/AC5):** an ad-hoc run — `hermes -z "Use brave_web_search to find
the ECB homepage URL, then use the browser fetch tool to load it and report the H1 + first sentence;
if you cannot retrieve a page body reply 'FETCH BLOCKED: <reason>' and invent nothing." -p
claudius` — had Brave return `https://www.ecb.europa.eu/` and local headless Chrome render the
JS page, returning real body text ("Raising interest rates in June was the right choice, President
Christine Lagarde tells Les Echos… external supply shock…") — a rendered page body, not a Brave
snippet. No fabrication; the honesty/degradation instruction was in force (no block needed). This is
the previously-Cloudflare/JS-blocked source class (NUC-15) now completing.

## Agent working memory (NUC-21) — retired

Each Hermes profile kept bounded episodic memory of its own prior runs (`docs/working_memory.md`
records the design). The stores, their nightly consolidation (`memory-consolidation.timer`) and
the status section that counted them were retired at T6.1 (2026-09-16); the per-run record is
the workflow receipt. History: `design/archive/hermes-profiles-2026-09-14.md`.

## Agent-run metrics & scorecard (NUC-23)

Each run appends a structured, append-only record to `~/agent-workforce/logs/cost.log`:

```
ts=<ISO8601> schema=3 profile=<name> model=<PROFILE config.yaml model.name> task=<slug>
outcome=PROPOSAL|NOPROPOSAL|FAIL|VIOLATION|CRASHED|BLOCKED|DEDUP|OPS proposal=<slug|none>
run_seconds=<n> attempts=<n> tokens=unknown usage_before=<usd|unknown> usage_after=<usd|unknown>
cost_usd_delta=<usd|unknown> cost_src=openrouter-key-api memory=recorded|fallback|no-store|na
skills=<csv|none|unknown> skills_offered=<csv|none|unknown> skills_src=transcript|none
```

- `model` is `unknown` since T6.1 (2026-09-16): it was read from the Hermes profile's
  `config.yaml`, and no live job has run on one since 2026-08-13. The measured model is in the
  receipt (`bin/propose_receipt.py`, T5.2).
- `tokens`, `usage_before`, `usage_after` and `cost_usd_delta` are `unknown` since T6.1: the
  shared-key spend probe (NUC-27) read `~/.hermes/.env` and is retired; receipts carry measured
  usage. The keys stay so every reader keeps parsing. **The OpenRouter dashboard is the spend
  source of truth.**
- `skills`, `skills_offered`, `skills_src` (T3.3, 2026-09-11) are the pointer skills this run
  was offered and opened, read from its Claude Code transcript by `bin/skill_telemetry.py`.
  `agent_propose.sh` mints one `AGENT_SESSION_ID` per attempt, the nine Claude runners pass it as
  `--session-id`, and `log_cost()` looks the transcript up as
  `~/.claude/projects/*/<id>.jsonl` — by id, never by mtime. `skills` is the union of `Skill`
  tool calls naming a `praetorium-<owner>:<name>` pointer and `Read`s of its `SKILL.md`
  (canonical `08_skills/<name>/SKILL.md` or the pointer file); `skills_offered` is the
  session's `skill_listing`, namespace-filtered. Names are unqualified, sorted, comma-joined.
  `skills_src=none` ⇔ both values `unknown` ⇔ no transcript for the session: BLOCKED and DEDUP
  records, hermes and codex-acp runs (augustus), a `claude` that never started. `none` with
  `skills_src=transcript` means the transcript was read and the set is empty — a real zero.
  The schema number did not change: every reader is key-based, nothing branches on it.

`bin/scorecard.sh` rolls the log into a de-identified aggregate digest published to the box-safe
repo at `_inbox/agents/_metrics/scorecard.md` (same channel/branch as proposals, pushed via the
`github-boxsafe` deploy key). Since T3.3 the digest also carries a `## Pointer skills (T3.3)`
table — per pointer name, runs that read it and runs offered it, 7d and all-time — and a Signal
row `Pointer skills read (last 7d)` that `bin/deliver_scorecard.sh` forwards to #ops; BLOCKED
and DEDUP records never count, OPS runs do. It runs fail-soft at the end of every `agent_propose.sh` run and on a
weekly `scorecard.timer`; it is idempotent (identical input → byte-identical digest). Approval
outcomes (promoted/rejected/edited) come from `_inbox/agents/_metrics/approvals.tsv`, written
Mac-side by `agent_inbox.py` — the box holds no canonical vault, so this producer is the one
remaining Mac-side hand-off (tracked NUC-26; spec: `docs/nuc23_approval_outcomes_macside.md`).
The box side now SURFACES the raw pending-proposal backlog (count + oldest age) in
`praetorium-status.sh` and the overnight morning report (NUC-26); until the approvals feed lands,
the scorecard's approval cells still read "pending (awaiting Mac sync)". Infra health lives in
`praetorium-status.sh` (NUC-18) — linked, not duplicated.

## Buzz delivery surface

Every scheduled unit's output reaches Buzz through **one** script, `bin/deliver.sh`. Each other
`bin/deliver_*.sh` is an input adapter: it decides what this run produced and calls the transport
once. `tests/test_buzz_unit_wiring.sh` enforces that nothing else invokes `buzz messages send`,
`buzz social publish` or `buzz canvas set`, so "did it actually send?" has exactly
one answer and exactly one receipt (`~/logs/delivery-receipts.jsonl`).

**Where each unit delivers** is `bin/buzz_producers.tsv` — unit, route, payload kind, wired/pending,
and whether silence is allowed. `bin/audit_buzz_dual_run.sh` reads it, not the journal.

**Where a route points, and what kind it publishes**, is `bin/buzz_routes.env`:
`ROUTE_<key>=<channel-uuid>` plus `ROUTE_<key>_kind=<9|45001>`. The kind is a property of the
destination, never of the producer — `ops` and `signals` are streams (kind 9), `research`,
`content`, `bd` and `approvals` are forums (kind 45001). This matters because Desktop's forum view
queries `kinds:[45001]` exclusively: a kind-9 post into a forum channel is accepted by the relay
and receipted `ok` while no reader ever sees it. 45003 (forum comment) is not a legal route kind —
the CLI requires `--reply-to` for it and no producer replies to a thread.

**What an artifact-carrying message looks like** is `docs/buzz-artifact-envelope.md` — a nine-field
typed block above the body, so a reviewer or a Mac-side broker can identify, hash-check and
supersede a delivery without parsing prose. Read that before changing any envelope field; the
consumer is not in this repo and will not fail loudly.

**Canvas** (living documents) is at most one designated writer per route, declared in the
manifest's `canvas` column and enforced by the wiring test. `--canvas mirror` writes the canvas
*and* posts the message; `--canvas only` writes the canvas and posts nothing. An unchanged canvas
is skipped rather than rewritten, so a digest that has not moved does not churn the document.

**As of 2026-08-10 every route is `canvas=none`** — no scheduled job writes any canvas. All six
canvases are hand-authored channel charters (what lands here, the send kind, the silence contract,
what the channel cannot do), and `buzz-acp` injects a pointer to each into the system prompt of
every channel session, so they are an instruction surface the agents read. Sources:
`~/OUTBOX/canvas-proposal/`.

**`--canvas-file <path>` decouples the document from the message.** Without it the canvas gets the
message content, so `mirror` is a snapshot of the last delivery — which is why a scheduled writer
and a charter were mutually exclusive, and why `scorecard.service` held `mirror` on `ops` until it
was flipped. With it, a producer maintains a file and the channel still gets its own message. The
mode stays the declaration of intent: `--canvas-file` with no `--canvas mirror|only` is a
`config_error` and nothing is sent, asserted in both suites. An unreadable, empty or oversized file
is refused rather than written through — `canvas set` has no history to recover from, so truncating
a living document loses the tail permanently. The refusal never costs the message: the canvas
settles `failed`, the delivery settles `partial_success`, and the next run retries because a failed
write records no hash.

Before wiring a new writer, read what the target canvas currently holds.

**The delivery boundary is fail-soft by contract:** a config or transport error exits 0 and files a
categorized receipt. A work-producing unit is never marked failed by a delivery hiccup — that
would fire `OnFailure=agent-alert@`, which would try to deliver the alert down the same broken
path. Silence is not the failure signal; the receipts are.
