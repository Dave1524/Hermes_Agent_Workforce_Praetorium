# Per-job override env files — this is NOT where the examples live

**The examples live in `profiles/<job>.env.example`. This directory holds history only.**

Consolidated 2026-09-02 (W4). Until then there were two homes and the pointers disagreed:
`docs/runbook.md` sent installers here in five places, including an `install -m 600` line
naming `config/job-overrides/augustus-content.env.example` — a path that has existed only
under `archive/` since 2026-09-01. Following the runbook provisioned a runtime that no
longer exists, and the instruction looked authoritative the whole time.

## What these files are

Non-secret **task wiring**. At runtime they live at `~/.config/agent-workforce/*.env`
(mode 600, outside git) and systemd points at them with
`Environment=AGENT_JOB_OVERRIDES=…`. `agent_propose.sh` sources the canonical
`secrets.env` first, then the override file, so an override may set `AGENT_PROFILE` /
`AGENT_OWNER` / `AGENT_TASK_SLUG` / `AGENT_RUNTIME_CMD` / `AGENT_RUN_MODE` only.
**Never put API keys here.**

## Install (from a checkout of this repo)

```bash
install -m 600 profiles/<job>.env.example ~/.config/agent-workforce/<job>.env
# edit paths if your deploy root is not ~/agent-workforce
```

The nine live examples are `bd_followup_drafts`, `daily_plan`, `eod_summary`,
`knowledge_digest`, `m1_signal_scan`, `overnight_morning_report`, `raw_ingest`,
`standing_research`, `weekly_pre_assembly`.

## Two live jobs have no example, and that gap is real

`augustus-content` and `bd-stall-radar` have no `profiles/*.env.example`. Their only
templates were the archived ones here, which name retired runtimes. Do not install from
`archive/` to fill the gap — derive the wiring from the unit's own journal instead, which
reveals the effective `AGENT_RUNTIME_CMD` without reading the deny-listed live `.env`:

```bash
journalctl -u augustus-content.service -o cat | grep -o 'run attempt [0-9]*/[0-9]*: .*' | tail -1
```

Measured 2026-09-02 — `augustus-content` runs
`~/agent-workforce/bin/run_content_via_buzz.sh` at `1/1` attempts, and `bd-stall-radar`
runs `cd ~/agent-worktrees/inbox && python3 ~/agent-workforce/bin/bd_stall_radar_kernel.py`
at `1/3`. That is the runner and the retry cap; the remaining keys are not observable this
way, so writing the two missing examples is a task with its own verification, not a
copy-paste. Tracked as a follow-up rather than guessed at here.

## Why `archive/` stays

The four files under `archive/` invoke retired runtimes — `~/.local/bin/hermes -z …`
(hermes cron era) and `kanban_run_and_wait.sh` (kanban-dispatch era, and that script was
**deleted** 2026-09-02 with the S3 retirement, open-decisions.md D7). A retired mention in
an archived file is a correct record, not drift, so they are not "fixed" to name live
runtimes. **Nothing may cite them as a revert path.**
