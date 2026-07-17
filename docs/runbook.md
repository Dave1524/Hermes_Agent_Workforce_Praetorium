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
| Standing / Claudius proposal | `agent-proposal.timer` (disabled by default — spend gate) | `agent-proposal.{service,timer}` | *(none — uses `AGENT_RUNTIME_CMD` from `secrets.env`)* | `profiles/claudius_task.md` | `claudius` |
| Augustus content pitch+draft | daily **01:30** (backstop) | `augustus-content.{service,timer}` | `~/.config/agent-workforce/augustus-content.env` | `profiles/augustus_content_task.md` | `augustus` |
| Content change-dispatch (poll) | every **15 min** | `content-change-dispatch.{service,timer}` | `~/.config/agent-workforce/augustus-content.env` (reused) | *(triggers the augustus run)* | `augustus` |
| BD stall radar | **Sun–Thu 23:00** | `bd-stall-radar.{service,timer}` | `~/.config/agent-workforce/bd_stall_radar.env` | `profiles/bd_stall_radar_task.md` | `claudius` |
| Weekly pre-assembly | **Fri 22:00** | `weekly-pre-assembly.{service,timer}` | `~/.config/agent-workforce/weekly_pre_assembly.env` | `profiles/weekly_pre_assembly_task.md` | `claudius` |
| Overnight pre-snapshot (no LLM) | daily **04:25** | `overnight-pre-snapshot.{service,timer}` | n/a | `bin/overnight_pre_snapshot.sh` | n/a |
| Overnight morning report (ops) | daily **06:15** | `overnight-morning-report.{service,timer}` | `~/.config/agent-workforce/overnight_morning_report.env` | `profiles/overnight_morning_report_task.md` | `claudius` |
| Agent inbox → Notion sync | `agent-inbox-sync.timer` | `agent-inbox-sync.{service,timer}` | *(service embeds the pipeline cmd)* | n/a | n/a |

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
| `qmd-refresh.timer` | Index refresh every 30m |
| `brave-mcp.service` | Brave search MCP on `:8766` |
| `memory-consolidation.timer` | Nightly MEMORY.md trim, all agent profiles |
| `scorecard.timer` | Weekly scorecard publish |
| `discord-bot.service` | Phase-2 bot — **do not enable** until token + private server exist |
| `agent-workforce-auto-sync.timer` | Shell auto-sync of this git repo (no LLM) |
| `overnight-pre-snapshot.timer` | Model-free pre-run state capture → `~/logs/overnight/` (NUC-36) |

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
