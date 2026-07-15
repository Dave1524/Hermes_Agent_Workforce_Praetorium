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
- **Remote APIs only for inference.** No local model runtime (Ollama, vLLM, IPEX-LLM) — under
  the current "scope it away" posture the box never holds client-identifiable data, so remote
  APIs (OpenRouter) are sufficient and simpler.
- **Secrets are a separate tree.** `~/.config/agent-workforce/` holds credentials (deploy key,
  mode 600) and is NOT this repo. Never `git add` anything from that path into this repo.

## Where things live
- `../vault-boxsafe/` — the box-safe vault projection (branch `agents`), shared memory/context.
- `~/.config/agent-workforce/` — secrets + per-job override envs (mode 600). Outside git entirely.
- This repo (`~/dev/agent-workforce/`) — **source of truth** for orchestration config, systemd
  unit sources, agent task profiles, inbox/approval tooling.
- `~/agent-workforce/` — **deployed runtime copy** (no git) that systemd actually execs. Do not
  treat it as canonical; after merging to `main`, rsync `bin/` `profiles/` `docs/` into it.
  Job wiring map: `docs/runbook.md` § Job wiring (NUC-28).

## Verification
Run: `bash bin/verify.sh` from the repo root.
Gate = bash syntax check + shellcheck (error-severity, must be clean) over every script in
`bin/`, plus any test scripts under `tests/*.sh` if present. Full shellcheck output (style/info)
is printed but does not fail the gate.
