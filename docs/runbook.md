# Praetorium runbook — backup, restore, rebuild (NUC-19)

## Source of truth (NUC-28)

| Tree | Role |
|---|---|
| `~/dev/agent-workforce/` (git, `main`) | **Source of truth.** Edit here; open PRs for non-trivial work. |
| `~/agent-workforce/` | **Deployed runtime** (no `.git`). What systemd `ExecStart=` runs. Update by copying from the git tree after merge — not by editing in place. |
| `/etc/systemd/system/*.service|.timer` | Installed units. Canonical unit *sources* live in this repo under `systemd/`; install with `sudo cp` + `daemon-reload`. |
| `~/.config/agent-workforce/` | Secrets + per-job override env files (mode 600). **Never git.** Templates: `config/job-overrides/*.env.example`. |

If a reviewer only looks at git and concludes a path is "dead code", check `AGENT_RUNTIME_CMD` / `AGENT_JOB_OVERRIDES` under `~/.config/agent-workforce/` — production wiring often lives there.

## Job wiring (names only — no secret values)

Scheduled **proposal** agent jobs share `bin/agent_propose.sh` (lock, preflight, cost.log, write-boundary, scorecard). Per-job differences are injected via `AGENT_JOB_OVERRIDES` after `secrets.env`.

**NUC-36:** the Hermes cron fleet is folded under systemd + this runner. Model-free jobs get a direct `ExecStart` script; non-proposal LLM jobs use `AGENT_RUN_MODE=ops` (same lock/preflight/cost, no inbox write-boundary/commit). Do not re-add fleet schedules to `~/.hermes/cron/jobs.json`.

**NUC-35 — change-triggered content dispatch.** `content-change-dispatch.timer` polls every 15 min and runs `bin/content_change_dispatch.sh`: a deterministic, **model-free** tick that reads the Notion "Picked" content-board IDs (`notion_rest.py board --status Picked --json`), diffs them against `~/agent-workforce/var/content_picked.state`, and dispatches the **existing** Augustus draft run (`bin/agent_propose.sh`, reusing `augustus-content.env` via `AGENT_JOB_OVERRIDES`) **only when a Picked ID appears that is not already in the state file**. A quiet tick spends nothing — no `agent_propose.sh` call, so no `cost.log` line and no `agent_run.log` entry — it just refreshes the state file and exits 0. This cuts Picked→Drafted latency from the ~24h nightly cadence to ~15 min at zero steady-state cost. Fail-soft by contract: on any Notion API/parse error the script logs to `logs/content_change_dispatch.log` and exits 0 **without touching the state file**, so a transient outage never drops a pending row or corrupts state; the state is only advanced after a clean board read (empty diff) or after a dispatched run returns 0. The nightly `augustus-content.timer` stays as the backstop — a 01:30 poll tick that overlaps the 01:30 nightly run SKIPs safely on `agent_propose.sh`'s flock (`/tmp/agent_propose.lock`, "previous run still active"), so there is no double-draft and no new flag is needed.

| Job | Timer (Europe/Amsterdam) | Unit pair | Override env (runtime path) | Task profile | Hermes profile |
|---|---|---|---|---|---|
| Standing research (Opus 5, NUC research pipeline brief 2026-07-30) | `agent-proposal.timer` Mon–Fri 04:30 | `agent-proposal.{service,timer}` | `~/.config/agent-workforce/standing_research.env` | `profiles/standing_research_cc_task.md` | *(headless Claude Code)* |
| Raw source ingestion (Mechanism B) | **Tue–Sat 03:00** | `raw-ingest.{service,timer}` | `~/.config/agent-workforce/raw_ingest.env` | `profiles/raw_ingest_cc_task.md` | *(headless Claude Code)* |
| Knowledge digest (Mechanism C) | **Sun 09:00** | `knowledge-digest.{service,timer}` | `~/.config/agent-workforce/knowledge_digest.env` | `profiles/knowledge_digest_cc_task.md` | *(headless Claude Code)* |
| M1 signal scan (NUC-32/34) | **Mon,Wed 05:30** | `m1-signal-scan.{service,timer}` | `~/.config/agent-workforce/m1_signal_scan.env` | `profiles/m1_signal_scan_cc_task.md` | *(headless Claude Code)* |
| Augustus content pitch+draft | daily **01:30** (backstop) | `augustus-content.{service,timer}` | `~/.config/agent-workforce/augustus-content.env` | `profiles/augustus_content_task.md` | `augustus` |
| Content change-dispatch (poll) | every **15 min** | `content-change-dispatch.{service,timer}` | `~/.config/agent-workforce/augustus-content.env` (reused) | *(triggers the augustus run)* | `augustus` |
| BD stall radar | **Sun–Thu 23:00** | `bd-stall-radar.{service,timer}` | `~/.config/agent-workforce/bd_stall_radar.env` | `profiles/bd_stall_radar_task.md` | `claudius` |
| BD follow-up drafts | **Sun–Thu 23:30** | `bd-followup-drafts.{service,timer}` | `~/.config/agent-workforce/bd_followup_drafts.env` | `profiles/bd_followup_drafts_cc_task.md` | *(headless Claude Code)* |
| Weekly pre-assembly | **Fri 22:00** | `weekly-pre-assembly.{service,timer}` | `~/.config/agent-workforce/weekly_pre_assembly.env` | `profiles/weekly_pre_assembly_task.md` | `claudius` |
| Overnight pre-snapshot (no LLM) | daily **04:25** | `overnight-pre-snapshot.{service,timer}` | n/a | `bin/overnight_pre_snapshot.sh` | n/a |
| Overnight morning report (ops) | daily **06:15** | `overnight-morning-report.{service,timer}` | `~/.config/agent-workforce/overnight_morning_report.env` | `profiles/overnight_morning_report_task.md` | `claudius` |
| Daily plan (ops) | **Mon–Fri 06:00** | `praetorium-daily-plan.{service,timer}` | `~/.config/agent-workforce/daily_plan.env` | `profiles/daily_plan_task.md` | *(headless Claude Code)* |
| EOD summary (ops) | daily **22:15** | `praetorium-eod-summary.{service,timer}` | `~/.config/agent-workforce/eod_summary.env` | `profiles/eod_summary_task.md` | *(headless Claude Code)* |
| Agent inbox → Notion sync | `agent-inbox-sync.timer` | `agent-inbox-sync.{service,timer}` | *(service embeds the pipeline cmd)* | n/a | n/a |

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

**BD follow-up drafts is chained after the radar, deliberately.** `bd-stall-radar` (23:00)
decides *which* deals are owed a touch and stops at flagging; `bd-followup-drafts` (23:30)
reads that night's pack as one of its three inputs and writes the actual text, so the 30-min
offset is a data dependency, not cosmetic — and both slots clear the 04:30/05:30/06:00
morning jobs that share `agent_propose.sh`'s global `flock` on `/tmp/agent_propose.lock`,
where a collision is a **silent** `SKIP: previous run still active`. The pack is send
material, not a vault proposal: it carries `target: none`, is never promoted, and the job
never writes Notion pipeline state.

Override files set only non-secret keys:

- `AGENT_PROFILE` (optional; else parsed from `AGENT_RUNTIME_CMD -p …`)
- `AGENT_TASK_SLUG` (metrics / cost.log label)
- `AGENT_RUNTIME_CMD` (actual hermes / kanban invocation; paths point at the **deployed** tree `~/agent-workforce/`)
- `AGENT_RUN_MODE` (`proposal` default, or `ops` for non-inbox LLM jobs — NUC-36)

Templates (checked in): `config/job-overrides/*.env.example`. Install:

```bash
install -m 600 config/job-overrides/augustus-content.env.example \
  ~/.config/agent-workforce/augustus-content.env
# same for bd_stall_radar, weekly_pre_assembly, overnight_morning_report
```

Supporting daemons (not override-driven):

| Unit | Role |
|---|---|
| `qmd-mcp.service` (+ `qmd-mcp.service.d/gpu.conf`) | Vault MCP on `:8765`; GPU drop-in sets `QMD_LLAMA_GPU=vulkan` |
| `qmd-refresh.timer` | Index refresh every 30m; the pull leg is `bin/vault_sync_guard.sh sync` (NUC-45) |
| `brave-mcp.service` | Brave search MCP on `:8766` |
| `memory-consolidation.timer` | Nightly MEMORY.md trim, all agent profiles |
| `scorecard.timer` | Weekly scorecard publish |
| `agent-workforce-auto-sync.timer` | Shell auto-sync of this git repo (no LLM) |
| `overnight-pre-snapshot.timer` | Model-free pre-run state capture → `~/logs/overnight/` (NUC-36) |
| `inbox-backlog-alert.timer` | Daily 06:20 approvals-aging Discord alert (>2d oldest pending) — NUC-30 |
| `local-tier-eval.timer` | Tier-0 capability eval 6×/day (02,08,11,14,17,20:17) via `bin/local_tier_eval.sh`. No `EnvironmentFile` by design — it must never reach a paid provider |

Deploy a unit after changing `systemd/`:

```bash
sudo cp systemd/<unit> /etc/systemd/system/
sudo systemctl daemon-reload
# timers: sudo systemctl enable --now <name>.timer
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
| Discord | `ExecStartPost=deliver_report.sh` (`REPORT_DIR`/`REPORT_GLOB`/`REPORT_SUBJECT` per unit) | same |

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
| Unit failed, log says `AGENT_VERIFY_CMD found no artifact` | the agent produced no Notion write | Read `logs/agent_run.log` for the real error; do **not** trust the exit code |
| No Discord message, unit green | `deliver_report.sh` is fail-soft | `~/logs/deliver_report.log` |
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
| Service units | Every deployed `.service`/`.timer` whose name matches a unit in this repo's `systemd/` (incl. `agent-workforce-auto-sync`, `overnight-*`, `agent-alert@`, `agent-inbox-sync` alongside the qmd/agent-proposal/augustus/bd-stall/brave/memory/scorecard/discord families) — enumerated automatically by `backup_config.sh` | `backup_config.sh` tarball |
| Scripts & docs | `~/agent-workforce/{bin,docs,profiles}` | `backup_config.sh` tarball |
| Job-override templates | this repo `config/job-overrides/` | git |
| Job-override runtime envs | `~/.config/agent-workforce/{augustus-content,bd_stall_radar,weekly_pre_assembly}.env` | **not secrets**, but recreate from templates if lost |
| qmd config | `~/.config/qmd/index.yml` | `backup_config.sh` tarball |
| Secrets template | `~/.config/agent-workforce/.env.example` + README | `backup_config.sh` tarball |
| Hermes profiles | `~/.hermes/profiles/` (SOUL.md, config.yaml — no .env) | add on first profile change |
| Working memory | `~/.hermes/profiles/<profile>/memories/MEMORY.md` (all profiles) | runtime state — NOT backed up; regenerated by agent runs, consolidated nightly (NUC-21) |
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
4. Install Hermes: `curl -fsSL https://hermes-agent.nousresearch.com/install.sh | bash -s -- --skip-browser`.
   - **Fetch backend (NUC-22):** the `--skip-browser` above is why the browser was never
     bootstrapped. Install local headless Chromium once (credential-free): `npx --yes
     agent-browser@latest install` (as `dave`) then `sudo npx --yes playwright install-deps chromium`.
5. Restore the config tarball over `$HOME` and `/etc/systemd/system/` (or rsync from this repo of scripts).
   Install units from `systemd/` including job timers (`augustus-content`, `bd-stall-radar`,
   `weekly-pre-assembly`) and `qmd-mcp.service.d/gpu.conf`.
6. Recreate secrets per `~/.config/agent-workforce/README.md` (new deploy key → register on repo,
   new OpenRouter key → re-apply spend cap, new Discord token). Then re-derive the Brave MCP env:
   `umask 077; grep -E '^BRAVE_API_KEY=' ~/.config/agent-workforce/secrets.env > ~/.config/agent-workforce/brave-mcp.env`.
   Install job-override envs from `config/job-overrides/*.env.example` (mode 600) — see § Job wiring.
7. `~/agent-workforce/bin/finish_boxsafe_clone.sh` (clone, index, exclusion gates, enable services).
   - Enable the added units (NUC-21/22/23): `sudo systemctl enable --now brave-mcp.service
     memory-consolidation.timer scorecard.timer`. Leave `agent-proposal.timer` per its spend gate.
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
- **Web fetch:** built-in Hermes `browser` toolset, local headless Chromium via agent-browser
  (credential-free — no Browserbase key), pinned in the profile `config.yaml` `browser:` block
  (NUC-22). Health: `praetorium-status.sh` → "Fetch backend (browser)" shows `chromium: installed`.
  Deeper spend-free check — **source `~/.hermes/.env` first** (a bare python invocation does NOT load
  it, so `AGENT_BROWSER_EXECUTABLE_PATH` is unset and the check returns `False`):
  `set -a; . ~/.hermes/.env; set +a; ~/.hermes/hermes-agent/venv/bin/python -c 'from tools.browser_tool
  import check_browser_requirements as c; print(c())'` → `True`. Egress rules: `docs/data_boundary.md`.

Test fetch (spends OpenRouter): `cd ~/agent-worktrees/inbox && ~/.local/bin/hermes -z "Fetch
<public-url> and give the H1 + first paragraph; if the body can't be retrieved reply exactly
'FETCH BLOCKED: <reason>' and invent nothing." -p claudius` — a real page body proves fetch;
the FETCH BLOCKED line proves graceful degradation (no fabrication).

**Captured evidence (2026-07-08, AC4/AC5):** an ad-hoc run — `hermes -z "Use brave_web_search to find
the ECB homepage URL, then use the browser fetch tool to load it and report the H1 + first sentence;
if you cannot retrieve a page body reply 'FETCH BLOCKED: <reason>' and invent nothing." -p
claudius` — had Brave return `https://www.ecb.europa.eu/` and local headless Chrome render the
JS page, returning real body text ("Raising interest rates in June was the right choice, President
Christine Lagarde tells Les Echos… external supply shock…") — a rendered page body, not a Brave
snippet. No fabrication; the honesty/degradation instruction was in force (no block needed). This is
the previously-Cloudflare/JS-blocked source class (NUC-15) now completing.

## Agent working memory (NUC-21)

Each agent profile keeps bounded episodic memory of its own prior runs — see **`docs/working_memory.md`**
for the store decision, entry schema, consolidation policy, and the two-run continuity recipe.
Consolidation runs nightly for every profile (`memory-consolidation.timer`, 03:30). Status:
`praetorium-status.sh` → "Working memory" (entry count + bytes per profile).

## Agent-run metrics & scorecard (NUC-23)

Each run appends a structured, append-only record to `~/agent-workforce/logs/cost.log`:

```
ts=<ISO8601> schema=2 profile=<name> model=<PROFILE config.yaml model.name> task=<slug>
outcome=PROPOSAL|NOPROPOSAL|FAIL|VIOLATION proposal=<slug|none> run_seconds=<n> attempts=<n>
tokens=unknown cost_usd=unknown cost_src=openrouter-dashboard memory=recorded|fallback|no-store|na
```

- `model` is the **profile's** real model (`~/.hermes/profiles/<profile>/config.yaml` `model.name`),
  not `LLM_MODEL_BUSINESS` (which was stale, echoing sonnet-5 while the profile runs haiku-4.5).
- `tokens`/`cost_usd` are best-effort `unknown` — hermes accounting is broken on OpenAI-compatible
  endpoints (#4404/#20741). **The OpenRouter dashboard is the spend source of truth.**

`bin/scorecard.sh` rolls the log into a de-identified aggregate digest published to the box-safe
repo at `_inbox/agents/_metrics/scorecard.md` (same channel/branch as proposals, pushed via the
`github-boxsafe` deploy key). It runs fail-soft at the end of every `agent_propose.sh` run and on a
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
`buzz social publish`, `buzz canvas set` or `hermes send`, so "did it actually send?" has exactly
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

**Canvas** (living documents) is one designated writer per route, declared in the manifest's
`canvas` column and enforced by the wiring test. `--canvas mirror` writes the canvas *and* posts
the message; `--canvas only` writes the canvas and posts nothing. An unchanged canvas is skipped
rather than rewritten, so a digest that has not moved does not churn the document.

**The delivery boundary is fail-soft by contract:** a config or transport error exits 0 and files a
categorized receipt. A work-producing unit is never marked failed by a delivery hiccup — that
would fire `OnFailure=agent-alert@`, which would try to deliver the alert down the same broken
path. Silence is not the failure signal; the receipts are.
