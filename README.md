# Hermes Agent Workforce – Praetorium

Box-side operational home for the AI agent workforce running on **Praetorium**, the NUC.

## What this repo holds

- `bin/` – orchestration scripts, agent runners, status/verification tooling
- `profiles/` – per-agent profile/task instructions
- `docs/` – runbooks, workflow rules, data-boundary guidelines
- `systemd/` – timers and services for automated tasks
- `discord-bot/` – lightweight bot for inbox/approval notifications
- `.claude/briefs/` – current and archived NUC improvement briefs

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

