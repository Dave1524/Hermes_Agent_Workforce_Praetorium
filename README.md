# Hermes Agent Workforce – Praetorium

Box-side operational home for the AI agent workforce running on **Praetorium**, the NUC.

## What this repo holds

- `bin/` – orchestration scripts, agent runners, status/verification tooling
- `profiles/` – per-agent profile/task instructions (incl. augustus / bd-stall / weekly-pre)
- `docs/` – runbooks, workflow rules, data-boundary guidelines
- `systemd/` – timers and services for automated tasks (canonical unit sources)
- `ui/` – the Control Room single-page app (`ui/control-room/`, React + Vite); its committed
  build lives under `bin/control_room_ui/app/` so the box serves it without Node
- `config/job-overrides/` – non-secret per-job env templates (`AGENT_JOB_OVERRIDES`)
- `.claude/briefs/` – current and archived NUC improvement briefs

**Source of truth:** this git tree (`main`). The live box also has a deployed copy at
`~/agent-workforce/` (what systemd runs) and secrets/overrides under
`~/.config/agent-workforce/`. See `docs/runbook.md` § Source of truth / Job wiring (NUC-28).

## Branching model

- Work on a branch or in an isolated checkout. Open PRs through `bin/gh_app.sh` as the App.
- Dave approves; the `gate` check must pass; the App merges the approved commit. Deploy after merge.
- Auto-sync was retired in PR #70. Nothing commits or pushes your unfinished work automatically.
- `python3 bin/main_protection.py --live` checks GitHub enforcement. See the runbook's
  GitHub identity section for the remaining rollout steps.

## Verification

Run from repo root:

```bash
bash bin/verify.sh
```

Gate: bash syntax + shellcheck error-level + test suite.

## Quick links

- `CLAUDE.md` – project context for Claude agents
- `docs/runbook.md` – operational runbook
- `docs/data_boundary.md` – de-identification and scope rules
- `docs/inbox_workflow.md` – proposal and approval flow
