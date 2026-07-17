# NUC-30 — Outbound Notification Channel

**Status:** Fully implemented and live ✅  
**Effort:** S  
**Workstream:** Observability & delivery  
**Sprint:** Batch 1

---

## Objective

Give the box a reliable, model-free push channel to Dave over Discord so unattended runs (nightly reports, approval backlogs, agent failures) reach human attention without waiting for Dave to poll the box.

## Why / Problem

The workforce produces but nothing proactively delivers. Without a notification channel:
- A failed agent run sits silently until Dave checks in.
- The approval backlog can age for days unnoticed.
- Operational trust in unattended mode stays low.

## Existing Infrastructure Audit

**All components implemented and live (verified 2026-07-17):**

| Component | Status | Evidence |
|-----------|--------|----------|
| Hermes gateway (`hermes-gateway.service`) | ✅ Running as user unit | `systemctl --user status hermes-gateway.service` |
| Discord bot token | ✅ Configured in `secrets.env` + `~/.hermes/.env` | `DISCORD_BOT_TOKEN` set, `hermes send --list` returns `discord:#praetorium-main-chat` |
| `deliver_report.sh` | ✅ Delivers morning report via `hermes send --to discord` | Log: `delivered morning-report-... to discord` (2026-07-17) |
| `inbox_backlog_alert.sh` | ✅ Fires when proposals age >2d | Timer runs, logic sound |
| `deliver_report.service/timer` | ✅ Deployed | Runs after overnight report generation |
| `inbox-backlog-alert.service/timer` | ✅ Deployed | Runs daily at 06:21 |
| `notify.sh` | ✅ Consolidated dispatch entrypoint | Created at `bin/notify.sh`; 96 lines, fail-soft, supports text + `--file` mode |
| `agent-alert@.service` | ✅ OnFailure handler with Discord delivery | Extended to call `notify.sh` via `secrets.env`; tested with `agent-alert@test-hello.service` |
| `agent-proposal.service` | ✅ OnFailure + completion notification | `OnFailure=agent-alert@%n.service` + `ExecStartPost` with `notify.sh` |
| `augustus-content.service` | ✅ OnFailure + completion notification | `OnFailure=agent-alert@%n.service` + `ExecStartPost` with `notify.sh` |
| Stale hermes cron cleanup | ✅ Removed | `hermes cron rm 1dee98c14b36` — `overnight-morning-report` LLM job deleted |

## Implementation Completed

### Step 1 — OnFailure alert chain (DONE ✅)

`agent-alert@.service` was extended to call `notify.sh` (via the shared `secrets.env` for `DISCORD_BOT_TOKEN`) after the existing journal+log entry. Verified by running `sudo systemctl start agent-alert@test-hello.service` — the alert was logged to journal, written to `/home/dave/logs/agent-alert.log`, and dispatched to `#praetorium-main-chat` via Discord.

### Step 2 — Consolidated dispatch script (DONE ✅)

`bin/notify.sh` created at 96 lines. Single entrypoint for all box-side notifications:
- Resolves the hermes CLI (venv → `.local` → `python -m hermes_cli.main`)
- Supports text mode: `notify.sh <subject> <message>`
- Supports file mode: `notify.sh <subject> --file <path>`
- Fail-soft: always exits 0; logs to `$HOME/logs/notify.log`

### Step 3 — Missed-run notifications (DONE ✅)

Added `OnFailure=agent-alert@%n.service` to `agent-proposal.service` and `augustus-content.service` (were missing it). Also added `ExecStartPost` to both services that sends a completion heartbeat via `notify.sh`. The OnFailure handler covers failure in real-time; the ExecStartPost covers successful completion.

### Step 4 — Stale hermes cron cleanup (DONE ✅)

Removed the superseded `overnight-morning-report` hermes cron job (id `1dee98c14b36`). Only two legitimate cron jobs remain: `overnight-pre-snapshot` and `hl-strategy-research-overnight`.

## Files Touched

| File | Action | Status |
|------|--------|--------|
| `~/dev/agent-workforce/bin/notify.sh` | **Create** — consolidated notification dispatch | ✅ Done |
| `~/agent-workforce/bin/notify.sh` | **Deploy** — copy to live tree | ✅ Done |
| `~/dev/agent-workforce/systemd/agent-alert@.service` | **Update** — add `EnvironmentFile` + `notify.sh` call | ✅ Done |
| `/etc/systemd/system/agent-alert@.service` | **Install** — updated template | ✅ Done |
| `~/dev/agent-workforce/systemd/agent-proposal.service` | **Update** — add `OnFailure` + `ExecStartPost` | ✅ Done |
| `/etc/systemd/system/agent-proposal.service` | **Install** — updated unit | ✅ Done |
| `~/dev/agent-workforce/systemd/augustus-content.service` | **Update** — add `OnFailure` + `ExecStartPost` | ✅ Done |
| `/etc/systemd/system/augustus-content.service` | **Install** — updated unit | ✅ Done |
| Hermes state | **Clean up** stale `overnight-morning-report` cron id `1dee98c14b36` | ✅ Done |

## Deployment Verification

```bash
# Verify the units are installed and correct:
sudo systemctl cat agent-alert@.service
sudo systemctl cat agent-proposal.service
sudo systemctl cat augustus-content.service

# Test the alert handler directly:
sudo systemctl start agent-alert@test-hello.service
sudo journalctl -u agent-alert@test-hello.service --no-pager
cat /home/dave/logs/agent-alert.log | tail -3
cat /home/dave/logs/notify.log | tail -3

# Verify stale cron removed:
hermes cron list   # should show only overnight-pre-snapshot + hl-strategy-research-overnight
```

All verified live on 2026-07-17. The `agent-alert@` template is OnDemand — no `enable` needed, just referenced from other units' `OnFailure=` directives.

## Risk & Open Questions

- **Token rotation:** The Discord bot token lives in 5+ files (secrets.env, each hermes profile .env). Rotation requires updating all of them. Consider a single source-of-truth pattern (secrets.env only, referenced from profiles). **Note:** `agent-alert@.service` now reads `secrets.env`, so rotation there is handled.
- **Notification fatigue:** Currently 4 scripts push to Discord (`deliver_report.sh`, `inbox_backlog_alert.sh`, `notify.sh` via alert handler, `notify.sh` via ExecStartPost). Ensure each is meaningful — the morning report is the daily digest, backlog alerts are only when threshold breached, failure alerts are exceptions. The ExecStartPost completion messages for agent-proposal and augustus-content are once-daily heartbeats.
- **Delivery reliability:** `hermes send` is a CLI call to a third-party gateway. If the gateway is down, notifications silently fail (the fail-soft design is intentional — a notification failure should never crash the reporting service). Consider a local spool as future work.

---

*Brief generated 2026-07-17. Last updated 2026-07-17 after implementation. Based on Notion NUC-30 spec + box audit.*
