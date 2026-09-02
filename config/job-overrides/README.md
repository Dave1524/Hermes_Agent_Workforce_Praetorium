# Per-job override env files

These files are **non-secret task wiring**. They live at runtime under
`~/.config/agent-workforce/*.env` and are pointed at by systemd via
`Environment=AGENT_JOB_OVERRIDES=…`.

`agent_propose.sh` sources the canonical `secrets.env` first, then the override
file — so overrides may set `AGENT_PROFILE` / `AGENT_TASK_SLUG` / `AGENT_RUNTIME_CMD`
only. Never put API keys here.

## Install

```bash
# From a checkout of this repo:
install -m 600 config/job-overrides/augustus-content.env.example \
  ~/.config/agent-workforce/augustus-content.env
# same for bd_stall_radar, weekly_pre_assembly, overnight_morning_report
# edit paths if your deploy root is not ~/agent-workforce
```

`AGENT_RUN_MODE=ops` (NUC-36) is for non-proposal LLM jobs (e.g. overnight morning
report): same lock/preflight/cost.log, no inbox write-boundary or commit.

See `docs/runbook.md` § Job wiring for the full map.

## Where the CURRENT examples live (2026-09-01)

**The example files in this directory were stale and are now under `archive/`.** They
invoked retired runtimes — `~/.local/bin/hermes -z …` (hermes cron era) and
`kanban_run_and_wait.sh` (kanban-dispatch era) — while every live job execs a
`bin/run_*_cc.sh` headless Claude Code runner. Provisioning a live `.env` from one of
them installed a runtime that no longer works.

Since 2026-09-02 that is literal rather than figurative for the kanban one:
`bin/kanban_run_and_wait.sh` was **deleted** with the S3 retirement (open-decisions.md
D7), so `archive/augustus-content.env.example` names a path that is not on disk. The
archived files stay — a retired mention in an archived file is a correct record — but
nothing may cite them as a revert path.

Until the two homes are consolidated, the **current** examples are
`profiles/<job>.env.example`. Verified against live behaviour by reading each unit's
journal (`run attempt N/M: <cmd>`), which reveals the effective `AGENT_RUNTIME_CMD`
without reading the deny-listed `~/.config/agent-workforce/*.env`.

Consolidation is tracked as inconsistency 5 in `design/workflow-registry.md` §6.
