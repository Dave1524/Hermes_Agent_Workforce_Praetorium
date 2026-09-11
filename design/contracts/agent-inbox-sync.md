# Contract: agent-inbox-sync

Read on 2026-09-11 from `systemd/agent-inbox-sync.{service,timer}`,
`bin/agent_inbox_pipeline.sh`, `bin/deliver_inbox_sync.sh` (header) and the receipts under
`~/logs/`. A light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

**`ExecStart` runs the SOURCE checkout**, `/home/dave/dev/agent-workforce/bin/…`, not the
deployed copy (`systemd/agent-inbox-sync.service:5`, `:24`); the delivery adapter on
`ExecStopPost` runs the deployed one. Both are drift-checked; the split is recorded here so
nobody "fixes" it into one tree without reading why.

## Identity

| | |
|---|---|
| Unit | `agent-inbox-sync.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic Python; replaced an LLM cron that executed a fully-specified algorithm (`bin/agent_inbox_pipeline.sh:3-5`) |
| Runner | `bin/agent_inbox_pipeline.sh` → `agent_inbox_notion_sync.py` then `agent_inbox_apply.py --apply`; `ExecStopPost=bin/deliver_inbox_sync.sh` |
| Cadence | every 30 minutes (`OnCalendar=*:0/30`), `RandomizedDelaySec=2min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service`; and the adapter reports a failed reconcile on `approvals` because it hangs off `ExecStopPost` (`deliver_inbox_sync.sh:10-13`) |
| Remediation owner | trajan for the pipeline; Dave for a Notion-side state it refuses to reconcile |
| Retirement condition | none — standing; ends with the inbox/approval workflow itself (`docs/inbox_workflow.md`) |
| Contract version | 1 (2026-09-11) |

## Trigger

`agent-inbox-sync.timer`: `OnCalendar=*:0/30`, `RandomizedDelaySec=2min`, `Persistent=true`.
`ExecStartPre` touches the run marker `~/logs/run-markers/agent-inbox-sync.service` so the
adapter can anchor freshness (`:21-23`).

## Inputs

- `$INBOX_WORKTREE/_inbox/agents/*.md` — the box-side proposals.
- The Notion agent-inbox data source, via `bin/notion_rest.py` (token from the deny-listed
  `~/.config/agent-workforce/secrets.env`, never read here).
- `approvals.tsv` — Mac-side promote/reject outcomes to reflect back (`:6-7`).

## Outputs

- **State change** — Notion rows created for new proposals; Mac-side outcomes reflected into
  Notion; REJECTED auto-executed inside the box-safe membrane (archive + remove + push
  `agents/inbox`); APPROVED surfaced as a Mac hand-off (`:6-10`). Canonical promotion stays a
  Mac write, by the vault boundary.
- **Receipt** — `~/agent-workforce/logs/agent_inbox_pipeline.last`, this run's full output
  under a `== agent-inbox pipeline <UTC> ==` header (`:20`, `:29`); overwritten per run, so it
  is always the last run's and never a history.
- **Delivery** — `bin/deliver_inbox_sync.sh` posts a `summary` to #approvals only when
  something moved or the reconcile failed; `~/logs/deliver_inbox_sync.log` records
  `nothing moved — staying silent` otherwise. Receipts: `job = agent-inbox-sync.service`,
  route `approvals`.
- **Beneficiary:** Dave, whose Mac-side promote/reject pass reads the Notion board this keeps
  true.
- **Next actor:** Dave, on a summary that names proposals ready to promote.
- **Next action:** run the `(canonical write)` commands the summary prints
  (`00_system/tools/agent_inbox.py promote <file>`) on the Mac.
- **Benefit hypothesis:** the board and the worktree never disagree for longer than 30
  minutes, and a failed reconcile is announced rather than converging on a lie.
- **Benefit signal:** `Unknown`. Summaries delivered are receipted (64 on 2026-09-11);
  promotions that followed a summary are a Mac-side event this box does not see.

## Decline conditions

none. `sync failed` / `apply failed` lines in the receipt file and a non-zero exit are
failures, reported both by `OnFailure` and by the `ExecStopPost` adapter.

## Side effects

- Notion writes (row create, status flip) — the one outward-facing write on this list, inside
  the approvals membrane only.
- Git: archive/remove of REJECTED proposals and a push of `agents/inbox` in the inbox worktree.
- Overwrites `agent_inbox_pipeline.last`; touches the run marker.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Ninety minutes: two ticks plus jitter.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 5400 ] || { echo "last fired $(( age / 60 ))min ago"; exit 1; }
   ```

2. **This run's receipt exists and reports no failed stage.** The receipt file is anchored to
   the trigger by mtime; a receipt from an older run means this run died before `tee` wrote,
   and a `sync failed` / `apply failed` line means the run said so itself.

   ```check id=receipt-is-this-runs-and-clean when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   r="$HOME/agent-workforce/logs/agent_inbox_pipeline.last"
   [ -n "$(find "$(dirname "$r")" -maxdepth 1 -name "$(basename "$r")" -newermt "@${t#@}" 2>/dev/null)" ] \
     || { echo "no receipt written since $t"; exit 1; }
   head -1 "$r" | grep -q '^== agent-inbox pipeline ' || { echo "receipt has no run header"; exit 1; }
   ! grep -qE '^(sync|apply) failed$' "$r" || { echo "the run reported a failed stage"; exit 1; }
   ```

## Known failure modes

- **A reconcile that fails silently is the failure the adapter exists for.** Hence
  `ExecStopPost`, not `ExecStartPost` (`deliver_inbox_sync.sh:10-13`). Do not move it.
- **The Notion token or network is down.** `sync failed` in the receipt, exit 1, alert. The
  apply half still runs against local state and can remove a REJECTED file whose Notion row
  it could not flip; the next successful sync reconciles it.
- **The receipt is a single overwritten file.** Two failures thirty minutes apart leave one
  trace. History is in the journal, scoped by unit.
- **Run marker touched, pipeline never ran.** `ExecStartPre` succeeds before `ExecStart` can
  fail; the adapter's freshness anchor then says "fresh" for a run that did nothing. Check 2
  reads the pipeline's own receipt, not the marker, for that reason.
