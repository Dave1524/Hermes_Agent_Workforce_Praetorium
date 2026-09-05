# AGENTS.md — agent-workforce (Codex)

**Read `CLAUDE.md` in this repo root before doing anything else.** It is the single source of
truth for this project — the roster, the hard constraints, where things live, the scheduled-job
wiring, and the verification gate. Everything in it applies to Codex too.

This file used to restate project rules in its own words and drifted three weeks stale doing it
(1.4 KB against an 11 KB `CLAUDE.md`). It is now a pointer so that cannot recur. Do not re-fork
it — project rules belong in `CLAUDE.md`; only Codex-specific mechanics belong here.
Re-confirmed a pointer and not a fork on 2026-09-05, and `tests/test_instruction_scaffolding.sh`
now asserts it on every run: this file must name its sibling and stay well under its size.

## Read these before making changes

From `CLAUDE.md`, in this order:

- **Hard constraints (short form)** — the outward-action gate, the canonical-vault credential this
  box turns out to *have*, `agents`-branch-only vault writes, Mac-only publishing, and the separate
  secrets tree. These are the rules that make this box safe to run unattended, and the vault ones
  are rules kept rather than boundaries enforced — read them there, not from this summary.
- **Where things live** — in particular that `~/dev/agent-workforce/` is source and
  `~/agent-workforce/` is the deployed runtime copy that systemd actually execs. Nothing deploys
  automatically; edit source without running `bin/deploy` and the runtime keeps running old code.

## The auto-sync race — commit immediately

`agent-workforce-auto-sync.timer` fires **every 15 minutes** and runs `bin/auto-sync`:
`git add -A` → commit → `git push origin main`. Any dirty tree here reaches `origin/main` inside
15 minutes under a generic `Auto-sync:` message, sweeping unrelated work-in-progress along with
it. Commit your own work **immediately** after editing — before deploying, before the verify gate
— or the message explaining why is lost. For a long batch, stop the timer first and restart it
after. Also `git fetch origin` and compare against `origin/main` before committing; local
checkouts here can be silently merged-and-stale.

## Verification

`bash bin/verify.sh` from the repo root — bash syntax check plus error-severity shellcheck over
every script in `bin/` and any `tests/*.sh`. It must pass before you commit.

## Codex-specific — not inherited from CLAUDE.md

- **No Claude Code slash commands.** This repo has `.claude/` but no `.codex/skills/`; there is no
  Codex equivalent of those workflows here. Work directly.
- **Machine-level guardrails live in `~/.codex/AGENTS.md`** (loaded globally, every session,
  regardless of cwd). That file carries this box's off-limits paths — including
  `~/.config/agent-workforce/`, whose contents must never be `git add`ed into this repo — and the
  vault MCP entry point.

## Code style

Shell scripts: `#!/usr/bin/env bash` and `set -euo pipefail`. Small, focused scripts with clear
failure modes. Keep documentation next to the code it describes.
