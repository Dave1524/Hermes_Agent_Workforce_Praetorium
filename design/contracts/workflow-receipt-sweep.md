# Contract: workflow-receipt-sweep

Written 2026-09-15 with `systemd/workflow-receipt-sweep.{service,timer}` and
`bin/receipt_sweep.py` (T5.2, criterion 6). A light contract in the section set of
`scorecard.md`. The unit ships **disabled**: its `[Install]` section exists so Dave can enable
it at resume, and no script or test does. Until then the timer reads `LastTriggerUSec` empty
and the sweep check reports "not loaded or has never fired", which is the correct answer.

**The sweep writes a receipt for a run it was not inside.** Every platform row's contract
carries only `when=sweep` checks — its runner is deterministic shell with no receipt seam — so
the only honest evidence for those runs is systemd's own record: `InvocationID` names the run,
`Result` and `ExecMainStatus` decide artifact-or-failed, and the contract's sweep checks decide
the rest. A run-path receipt always wins: the sweep never overwrites
`<workflow_id>/<InvocationID>.json`, and a paused timer writes nothing.

## Identity

| | |
|---|---|
| Unit | `workflow-receipt-sweep.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic python over `config/fleet-units.tsv` and `systemctl show` |
| Runner | `bin/receipt_sweep.py` (exit 1 only when the receipt machinery itself errored; a paused fleet and a refused row are logged, exit 0) |
| Cadence | daily, `OnCalendar=*-*-* 05:50`, `Persistent=true` — **disabled at ship** |
| Alerted | yes — `OnFailure=agent-alert@%n.service`; fires on an executor that left no receipt, never on a paused timer |
| Remediation owner | trajan |
| Retirement condition | every platform runner receipts its own run (then the sweep has nothing to write) |
| Contract version | 1 (2026-09-15) |
| Retry | idempotent: a receipt that exists is skipped, so a rerun writes only what the last one missed |

## Trigger

`workflow-receipt-sweep.timer`: `OnCalendar=*-*-* 05:50`, `Persistent=true`. Not enabled by any
deploy step; `systemctl is-enabled workflow-receipt-sweep.timer` reads `disabled` after land.

## Inputs

- `config/fleet-units.tsv` — rows `status=standing kind=timer`, the sweep itself excluded.
- `systemctl show <unit>.timer -p ActiveState` and `systemctl show <unit>.service -p
  InvocationID,ExecMainStartTimestamp,ExecMainExitTimestamp,Result,ExecMainStatus,ActiveState`
  (`--user` for `scope=user` rows; `XDG_RUNTIME_DIR` is set on the unit for that reason).
- The manifest row of each unit (`design/agents/*.toml`, read from the source checkout as
  `bin/contract_exec.py` does) for the `logical_workflow` fold.
- `~/agent-workforce/var/workflow-receipts/<workflow_id>/<InvocationID>.json` — its existence.

## Outputs

- **Artifact** — receipts under `~/agent-workforce/var/workflow-receipts/<workflow_id>/`, one
  per finished invocation not already receipted, vantage `sweep`, run id the `InvocationID`,
  `state_change.evidence` = systemd's record, terminal `failed` when `Result` is not `success`;
  plus the sweep's own vantage-`run` receipt whose evidence is the `swept N: M written, K
  paused, J refused, S skipped` line it logged.
- **Log** — `~/agent-workforce/logs/receipt_sweep.log`, one line per unit (`paused:`,
  `never ran:`, `running:`, `already receipted:`, `refused:`, `written:`, `errored:`) and the
  `swept` summary.
- **Beneficiary:** the Control Room (`bin/control_room_api.py`), which reads receipts and
  nothing else — without the sweep every platform row is `no receipt` forever.
- **Next actor:** none
- **Next action:** none
- **Benefit hypothesis:** every standing timer's last run is visible on the screen with an
  honest outcome, including the runners that cannot write their own.
- **Benefit signal:** `Unknown` until the first enabled morning; then the Control Room's
  `no receipt` count for platform rows should read zero after 05:50.

## Decline conditions

none. `paused`, `never ran`, `running`, `already receipted` and `refused` are per-unit reasons
in the log, each counted in the summary line; none is a decline of the sweep.

## Side effects

- Receipt files written under the receipt root; never one that already exists.
- `systemctl show` calls, read-only, for every standing timer row.

## Acceptance checks

One `run` check and one `sweep` check.

1. **This run swept.** The summary line is written before the sweep receipts itself, so the
   run's own check reads a `swept` line stamped at or after the run started.

   ```check id=swept-this-run
   log="$HOME/agent-workforce/logs/receipt_sweep.log"
   since="$(date -u -d "@$AGENT_RUN_STARTED_AT" +%Y-%m-%dT%H:%M:%SZ)"
   awk -v s="$since" '$1 >= s' "$log" 2>/dev/null | grep -q ' swept [0-9]' \
     || { echo "no swept line since $since in $log"; exit 1; }
   ```

2. **The timer fired within its cadence.** Forty-eight hours: daily plus a missed morning.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 172800 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

## Known failure modes

- **A receipt written from outside the run knows nothing the run did not leave in systemd.**
  Usage and cost are `unavailable` on every sweep receipt, honestly; the artifact is the
  state change systemd recorded, not a file the runner wrote.
- **`InvocationID` survives only until the next boot or the next run.** A run that finished
  before a reboot the sweep never saw is unreceipted for good; the log says `never ran` for
  the unit until its next invocation.
- **The fleet-units projection is the walk.** A standing timer missing from
  `config/fleet-units.tsv` is invisible here; `tests/test_fleet_ownership.sh` keeps the
  projection equal to the manifests.
- **A refused row is a manifest gap, not a sweep fault.** Exit 2 from the executor (no
  `[[workflows]]` row, `kind = "service"`, no contract) is logged and skipped; the coverage
  checker owns that class.
