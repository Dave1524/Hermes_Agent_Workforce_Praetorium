# Contract: overnight-pre-snapshot

Read on 2026-09-11 from `systemd/overnight-pre-snapshot.{service,timer}`,
`bin/overnight_pre_snapshot.sh`, `bin/deliver_report.sh` and the receipts under `~/logs/`. A
light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

This is a model-free snapshot of the box taken before the overnight campaign, and it exists so
the morning report has a *before* to diff against
(`design/contracts/overnight-morning-report.md` § Inputs). Its consumer is another contract.

## Identity

| | |
|---|---|
| Unit | `overnight-pre-snapshot.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell, no model (`Description=… (model-free) — NUC-36`) |
| Runner | `bin/overnight_pre_snapshot.sh`; `ExecStartPost=bin/deliver_report.sh` with `REPORT_DIR=~/logs/overnight`, `REPORT_GLOB=pre-snapshot-*.log`, `DELIVERY_ROUTE=ops`, `DELIVERY_JOB=%n`, `DELIVERY_RUN_MARKER=~/logs/run-markers/%n` |
| Cadence | daily 04:25, `RandomizedDelaySec=2min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` |
| Remediation owner | trajan |
| Retirement condition | ends with the overnight campaign it snapshots for (`overnight-morning-report`); no separate condition |
| Contract version | 1 (2026-09-11) |

## Trigger

`overnight-pre-snapshot.timer`: `OnCalendar=*-*-* 04:25`, `RandomizedDelaySec=2min`,
`Persistent=true`. `ExecStartPre` touches the run marker so the adapter can anchor on this run.

## Inputs

- Live box state only: unit lists, timers, disk, memory, git heads, the things a morning diff
  needs. No vault, no Notion, no model.

## Outputs

- **Dated artifact** — `~/logs/overnight/pre-snapshot-<stamp>.log`
  (`bin/overnight_pre_snapshot.sh:9`), one per run, never overwritten; the journal ends with
  `wrote /home/dave/logs/overnight/pre-snapshot-<stamp>.log` (`:237`).
- **Delivery** — `bin/deliver_report.sh` hands the newest file matching the glob and newer
  than the run marker to #ops (`~/logs/deliver_report.log`: `handing pre-snapshot-<stamp>.log`
  → `handed to deliver.sh (route=ops)`); receipt `job = overnight-pre-snapshot.service`,
  route `ops`, `anchor = run_marker` (34 on 2026-09-11).
- **Beneficiary:** `overnight-morning-report`, which diffs against the newest pre-snapshot;
  Dave secondarily, in #ops.
- **Next actor:** the morning-report job, ~12 hours later.
- **Next action:** none for a human; the diff is automatic.
- **Benefit hypothesis:** the morning report can say what changed overnight rather than what
  is; without this file it degrades to a status page.
- **Benefit signal:** `Unknown`. The morning report's contract asserts the diff was made; how
  often the diff carried a finding is not counted.

## Decline conditions

none. The snapshot has no reason to refuse.

## Side effects

- One new file under `~/logs/overnight/` per day (never pruned by this job).
- One #ops delivery and receipt per day; the run marker is touched.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Thirty hours.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **This run wrote a snapshot and it was handed to delivery.** A non-empty
   `pre-snapshot-*.log` newer than the trigger, and a receipt for this job stamped on the
   trigger's UTC date. The morning report's own contract reads the same file, so this check
   failing predicts that one.

   ```check id=snapshot-written-and-receipted when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   f="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'pre-snapshot-*.log' -newermt "@${t#@}" 2>/dev/null | sort | tail -1)"
   [ -n "$f" ] && [ -s "$f" ] || { echo "no pre-snapshot written since $t"; exit 1; }
   day="$(date -u -d "@${t#@}" +%Y-%m-%d)"
   grep -F '"job": "overnight-pre-snapshot.service"' "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null \
     | grep -q "\"ts\": \"$day" || { echo "snapshot written and no receipt dated $day"; exit 1; }
   ```

## Known failure modes

- **Snapshot written, delivery failed.** `ExecStartPost` failure fails the unit, so it alerts;
  the file is still on disk and the morning report still diffs against it. Check 2 fails on
  the missing receipt, correctly.
- **Run marker touched, snapshot script died.** The adapter finds no file newer than the
  marker and stays silent with `no new report since marker`; `OnFailure` alerts. The morning
  report then diffs against yesterday's snapshot and says so.
- **The directory is never pruned.** One file a day since NUC-36; disk, eventually. Not this
  job's contract.
- **Receipt matched by UTC date.** A 04:25 CEST run is 02:25 UTC, same calendar day either
  way; a run delayed past 02:00 CEST by `Persistent=true` catch-up is not, and would read as
  unreceipted for one sweep.
