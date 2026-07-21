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
- **De-identified/public content only.** Client-identifiable work happens on the Mac, never here.
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
  those tokens on-box. Client-identifiable data still never touches this box, so the boundary is
  unchanged. Do NOT route Tier-A judgment/synthesis to the local model. See
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
  treat it as canonical; after merging to `main`, rsync `bin/` `profiles/` `docs/` into it.
  Job wiring map: `docs/runbook.md` § Job wiring (NUC-28).

## Verification
Run: `bash bin/verify.sh` from the repo root.
Gate = bash syntax check + shellcheck (error-severity, must be clean) over every script in
`bin/`, plus any test scripts under `tests/*.sh` if present. Full shellcheck output (style/info)
is printed but does not fail the gate.
