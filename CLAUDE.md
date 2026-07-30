# CLAUDE.md — agent-workforce (Praetorium, box-side)

## What this is
The box-side operational home for the AI agent workforce running on this machine:
orchestration config, cron/scheduling, inbox/approval tooling, agent profiles.
This is a separate repo from `../vault-boxsafe/` — this one holds *how the agents run*,
the vault holds *what they know*.

## Roster naming
- Box name: **Praetorium**
- Lead orchestrator: **Marcus**
- Keep the Roman-emperor convention for any additional agent profiles added here.

## Hard constraints (short form)
- **Vault data is in-bubble.** The box sits inside Dave's private trust zone (the same zone as
  Notion and Discord): the whole working vault is on the mirror — client names, deals,
  priorities, daily logs — and agents may reason over all of it. `_confidential/` is the one
  data quarantine (never published, tripwired in the publish script). De-identification
  applies only to what *leaves* the bubble — outward-destined drafts, Brave queries, fetched
  URLs. See `docs/data_boundary.md`. (2026-07-08 open-bubble posture.)
- **The one hard gate is outward action.** No email, no social, no messaging humans from this
  box — it holds no outward credentials, ever. Anything for the outside world is a draft Dave
  sends. Notion and Discord are inside the bubble, not outward.
- **No canonical vault access.** This box holds no credential to the canonical `obsidian-ai-os`
  vault — only a repo-scoped deploy key to `obsidian-ai-os-boxsafe`.
- **Vault writes go through `agents`, never `main`.** Any proposal to the vault is committed to
  the box-safe repo's `agents` branch/inbox. `main` is machine-published from the Mac — never
  hand-write or merge into it from here.
- **Publishing is Mac-side only.** Never run `publish_boxsafe.sh` from this box.
- **Inference is remote-first, with a narrow local tier.** Generative agent work (Marcus,
  Claudius, Augustus, Trajan and their synthesis) runs on remote APIs (OpenRouter). A charter-
  scoped **local inference tier** (Ollama on the Arc iGPU) is now permitted for *mechanical*,
  high-volume work only — classification/summarization/tagging — to cut OpenRouter cost and keep
  those tokens on-box. Local inference has zero egress, so it is the safest tier for business
  content; the LLM egress boundary in `docs/data_boundary.md` governs the remote tiers only.
  Do NOT route Tier-A judgment/synthesis to the local model. See
  `~/vault/03_projects/active/ai_agent_workforce/local_inference_charter.md`.
- **Secrets are a separate tree.** `~/.config/agent-workforce/` holds credentials (deploy key,
  mode 600) and is NOT this repo. Never `git add` anything from that path into this repo.

## Where things live
- `../vault-boxsafe/` — the box-safe vault projection (branch `agents`), shared memory/context.
- `~/.config/agent-workforce/` — secrets + per-job override envs (mode 600). Outside git entirely.
- This repo (`~/dev/agent-workforce/`) — **source of truth** for orchestration config, systemd
  unit sources, agent task profiles, inbox/approval tooling.
  **`agent-workforce-auto-sync.timer` fires every 15 min** and runs `bin/auto-sync`:
  `git add -A` → commit → `git push origin main`. Any dirty tree here reaches `origin/main`
  within 15 minutes under a generic `Auto-sync:` message, sweeping unrelated WIP along with
  it. Commit your own work **immediately** after editing — before deploying, before the
  verify gate — or the message explaining *why* is lost. For a long batch, stop the timer
  first and restart it after.
- `~/agent-workforce/` — **deployed runtime copy** (no git) that systemd actually execs. Do not
  treat it as canonical. Deploy with **`bin/deploy`** — additive by default; `--dry-run` to
  preview, `--prune` to also drop files deleted from source. Runtime state (`logs/`, `var/`,
  `backups/`) is never touched. **Nothing deploys automatically:** edit source without
  running this and the runtime keeps executing the old code — that is how this tree fell 6
  days behind and kept serving the retired de-identification posture (NUC-44).
  Job wiring map: `docs/runbook.md` § Job wiring (NUC-28).

## Daily rhythm jobs (NUC-45)
Two jobs own Dave's day and run unattended on this box, both under `agent_propose.sh`
with `AGENT_RUN_MODE=ops`:
- **`praetorium-daily-plan.timer`** — Mon-Fri 06:00 → `<date> — Daily Plan` row in Notion.
- **`praetorium-eod-summary.timer`** — daily 22:15 → `<date> — EOD Summary` (Daily Plans)
  + `<date>` (Daily Log).

Rules that are easy to get wrong:
- **Notion is the artifact; the vault write stays Mac-side.** These jobs never write
  `07_daily/logs/`, on any branch. The Mac's `morning-startup` / `eod-wrap` skills remain
  canonical for interactive runs — the box profiles are a port, not a replacement.
- **All Notion I/O goes through `bin/notion_daily.py`**, which owns the date-keyed
  idempotency: a re-run updates the row and replaces its body instead of stacking a
  second one. Never hand-roll HTTP against the Notion API in a task profile.
- **`bin/vault_sync_guard.sh` is the single owner of "is the mirror current?"** —
  `sync` for `qmd-refresh.service`, `check` as the pre-flight for both jobs. A stale or
  dirty mirror must produce a loud refusal, never a confident wrong briefing. Details and
  the failure table: `docs/runbook.md` § Daily rhythm jobs.

## Research pipeline jobs (2026-07-30 Opus 5 migration)
Three research/knowledge jobs run unattended on headless Claude Code, pinned to **Opus 5**
(the full model name, not the `opus` alias — an alias silently rolls forward on the next
model release):
- **`agent-proposal.timer`** — Mon-Fri 04:30 → standing research (`AGENT_JOB_OVERRIDES` →
  `standing_research.env` → `bin/run_standing_research_cc.sh`). Replaces the
  hermes/claudius-on-OpenRouter path, which was hard-down for ten days on HTTP 402
  "Insufficient credits" while reading as a clean decline.
- **`raw-ingest.timer`** — Tue-Sat 03:00 → diffs `05_knowledge/raw/` against
  `00_system/ingest_log.md` and proposes one distillation per unprocessed source (ahead of
  the 04:30 standing research run, so research sees freshly-ingested knowledge same day).
- **`knowledge-digest.timer`** — Sun 09:00 → reports what `05_knowledge/` / `11_entities/`
  learned in the last 7 days (git-log delta), distinct from `weekly-pre-assembly`'s
  activity pre-read.

Rules that are easy to get wrong:
- **These jobs write only `_inbox/agents/**`; every vault change they describe is a
  proposal for Mac-side promotion, never a direct write to `main`.** The box holds no
  canonical vault credential — see "No canonical vault access" above.
- **A run must produce either a dated proposal or an explicit `DECLINE:` sentinel.**
  `bin/proposal_or_decline.sh <slug>` (wired as `AGENT_VERIFY_CMD`) fails any run that
  produces neither, so a dead run can never again log as a clean NOPROPOSAL.
- **Contradiction flagging (Mechanism A)** is a standing instruction across all three
  profiles: a source that contradicts an existing `05_knowledge/` claim gets named, both
  sides cited, under `## Contradictions` — never silently superseded.

## Verification
Run: `bash bin/verify.sh` from the repo root.
Gate = bash syntax check + shellcheck (error-severity, must be clean) over every script in
`bin/`, plus any test scripts under `tests/*.sh` if present. Full shellcheck output (style/info)
is printed but does not fail the gate.
