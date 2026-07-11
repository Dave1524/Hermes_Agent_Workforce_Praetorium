# Agent Instructions

This file contains instructions for AI agents working in this repository.

## Project context

This is the box-side operations repo for the **Praetorium** AI agent workforce. It contains scripts, systemd units, profiles, and runbooks that manage how agents run on this NUC.

## Default branch

The default branch is `main`. Do not commit large or risky work to `main`.

## Branching rules

- **Small, safe changes** may be committed directly to `main`. `bin/auto-sync` will push them automatically.
- **New features, refactors, or experimental work** must be done on a feature branch or in a separate worktree.
- Open a PR against `main` for review.

## Before committing

- Run `bash bin/verify.sh` and ensure it passes.
- Check `CLAUDE.md` for project-specific constraints.
- Respect the data-boundary rules in `docs/data_boundary.md`.
- Keep secrets out of the repo. Credentials live under `~/.config/agent-workforce/`.

## Code style

- Shell scripts: `set -euo pipefail` and `#!/usr/bin/env bash`
- Prefer small, focused scripts with clear failure modes
- Keep documentation close to the code it describes

## Useful references

- `CLAUDE.md` – project overview and constraints
- `docs/runbook.md` – day-to-day operations
- `docs/data_boundary.md` – what must stay off this box
- `docs/inbox_workflow.md` – proposal and approval flow

