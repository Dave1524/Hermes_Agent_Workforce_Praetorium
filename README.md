# Hermes Agent Workforce – Praetorium

Box-side operational home for the AI agent workforce running on **Praetorium**, the NUC.

## What this repo holds

- `bin/` – orchestration scripts, agent runners, status/verification tooling
- `profiles/` – per-agent profile/task instructions (incl. augustus / bd-stall / weekly-pre)
- `docs/` – runbooks, workflow rules, data-boundary guidelines
- `systemd/` – timers and services for automated tasks (canonical unit sources)
- `config/job-overrides/` – non-secret per-job env templates (`AGENT_JOB_OVERRIDES`)
- `discord-bot/` – lightweight bot for inbox/approval notifications
- `.claude/briefs/` – current and archived NUC improvement briefs

**Source of truth:** this git tree (`main`). The live box also has a deployed copy at
`~/agent-workforce/` (what systemd runs) and secrets/overrides under
`~/.config/agent-workforce/`. See `docs/runbook.md` § Source of truth / Job wiring (NUC-28).

## Branching model

- `main` – stable box-side code. Small, safe updates can be auto-committed here.
- Feature work / new agents – do on a branch or in a local worktree, then open a PR against `main`.

## Auto-sync

`bin/auto-sync` runs on a cron schedule. On `main` it fast-forwards from origin, commits any dirty changes, and pushes. Keep large or risky work in a branch.

## Verification

Run from repo root:

```bash
bash bin/verify.sh
```

Gate: bash syntax + shellcheck error-level + test suite.

## Quick links

- `CLAUDE.md` – project context for Claude/Hermes agents
- `docs/runbook.md` – operational runbook
- `docs/data_boundary.md` – de-identification and scope rules
- `docs/inbox_workflow.md` – proposal and approval flow

