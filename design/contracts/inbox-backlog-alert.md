# Contract: inbox-backlog-alert

Read on 2026-09-11 from `systemd/inbox-backlog-alert.{service,timer}`,
`bin/inbox_backlog_alert.sh`, `bin/delivery_common.sh` and `~/logs/inbox_backlog_alert.log`. A
light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

**Silence is the product** (`bin/inbox_backlog_alert.sh:7-11`). On most mornings this job
produces no delivery and that is correct; its artifact on those days is the one adapter-log
line saying why it stayed quiet. The checks are shaped so a quiet day passes and an
undelivered *due* alert fails.

## Identity

| | |
|---|---|
| Unit | `inbox-backlog-alert.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell + one Python count |
| Runner | `bin/inbox_backlog_alert.sh`, `DELIVERY_ROUTE=approvals`, threshold `INBOX_BACKLOG_THRESHOLD_DAYS=2` |
| Cadence | daily 06:20, `RandomizedDelaySec=3min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service`; but the script is fail-soft (exit 0 even on delivery error, `:20`), so OnFailure covers only a crash |
| Remediation owner | Dave — the alert asks for a Mac-side promote/reject pass; nothing on the box may decide |
| Retirement condition | none — standing; ends with the inbox/approval workflow |
| Contract version | 1 (2026-09-11) |

## Trigger

`inbox-backlog-alert.timer`: `OnCalendar=*-*-* 06:20`, `RandomizedDelaySec=3min`,
`Persistent=true`.

## Inputs

- `bin/agent_inbox_notion_sync.py --count` — `PENDING_COUNT` and `OLDEST_PENDING_DATE` from
  Notion status, so decided-but-uncleared files are not counted (`:12-19`, `:35-39`).
- Fallback when the count is unavailable: the raw `*.md` count under
  `$INBOX_WORKTREE/_inbox/agents`, labelled `approx=1` (`:40-44`).

## Outputs

- **Alert** — one line, `[Praetorium] Approvals aging` / `N proposals pending, oldest Nd
  (awaiting Mac-side promote/reject)`, handed to `bin/deliver.sh` on route `approvals` only
  when the oldest pending proposal is older than the threshold (`:63-69`). Receipt:
  `job = inbox-backlog-alert.service`, route `approvals`.
- **Quiet-day artifact** — `~/logs/inbox_backlog_alert.log` gets exactly one line per run:
  `inbox clear`, `backlog under threshold (N pending, oldest Nd <= 2d, approx=0) — no alert`,
  or `alerting: …` followed by `handed to deliver.sh (route=approvals)`
  (`bin/delivery_common.sh:32-40`). That line is what makes silence decidable.
- **Beneficiary:** Dave.
- **Next actor:** Dave, on an alert.
- **Next action:** run the Mac-side promote/reject pass over the inbox.
- **Benefit hypothesis:** a proposal never waits longer than two days unnoticed; the channel
  stays readable because it is only written to when there is something to say.
- **Benefit signal:** `Unknown`. Alerts delivered are receipted (24 on 2026-09-11); whether
  the backlog then cleared faster than it would have is not baselined.

## Decline conditions

none. An absent inbox worktree logs `nothing to check` and exits 0 (`:30-33`) — that is a
skip with a reason, not a decline, and a week of it is a worktree problem.

## Side effects

- One adapter-log line per run; one delivery and receipt on alert days.
- Reads Notion (count); writes nothing there. No file writes in the inbox.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Thirty hours.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **The run decided, and a due alert was handed off.** The adapter log must carry this run's
   decision line; if that line says `alerting:`, a `handed to deliver.sh` line and a receipt
   must follow. A quiet decision passes on its own.

   ```check id=decided-and-due-alert-delivered when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   log="$HOME/logs/inbox_backlog_alert.log"
   since="$(date -u -d "@${t#@}" +%Y-%m-%dT%H:%M:%SZ)"
   lines="$(awk -v s="$since" '$1 >= s' "$log" 2>/dev/null)"
   printf '%s\n' "$lines" | grep -qE ' (inbox clear|backlog under threshold|alerting:|nothing to check)' \
     || { echo "no decision line since $since"; exit 1; }
   printf '%s\n' "$lines" | grep -q ' alerting:' || exit 0
   printf '%s\n' "$lines" | grep -q 'handed to deliver.sh' || { echo "alert was due and not handed off"; exit 1; }
   grep -F '"job": "inbox-backlog-alert.service"' "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null \
     | tail -1 | grep -q "\"ts\": \"${since%T*}" || { echo "alert handed off and no receipt today"; exit 1; }
   ```

## Known failure modes

- **Fail-soft hides a broken delivery.** A `deliver.sh` error exits 0 (`:20`); only the
  adapter log's missing `handed to deliver.sh` line and the missing receipt show it, which is
  why check 2 reads both rather than the exit status.
- **The approximate count overstates.** With Notion unreachable the raw file count includes
  decided-but-uncleared files (`:14-16`); the alert says `approximate` and may fire a day
  early. Accepted: erring toward one extra alert, never toward silence (`:19`).
- **`OLDEST_PENDING_DATE` is a date, not a timestamp.** Age is computed in whole days from
  midnight; a proposal filed at 23:59 reads a day older than one filed at 00:01. Threshold
  semantics are "calendar days", by construction.
- **Receipt matched by calendar day.** Check 2 compares the receipt `ts` date prefix, so an
  alert at 06:20 and a receipt written after a stalled delivery at 00:30 the next day would
  read as unreceipted for one sweep. Light-contract approximation.
