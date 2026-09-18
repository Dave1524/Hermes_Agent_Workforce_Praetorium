# Contract: workflow-incidents

Written 2026-09-15 with `systemd/workflow-incidents.{service,timer}`, `bin/incident_notify.py`,
`bin/workflow_incidents.py` and `bin/incident_state.py` (T5.3c). A light contract in the
section set of `workflow-receipt-sweep.md`. The unit ships **disabled**: its `[Install]`
section exists so Dave can enable it, and no script or test does. The `incidents` route is
empty in `bin/buzz_routes.env` until Dave creates the channel; until then every sweep logs
`route 'incidents' has no channel UUID` and sends nothing, keeping its state.

**One failure is one incident.** The key is `<class>:<workflow_id>` (a malformed receipt is
keyed by its path, a control failure by its source, a declared incident by its id), so a
failure the fleet keeps reproducing is one open entry with a rising observation count, not a
message per sweep. Absence of evidence is not recovery: a sweep whose receipt root or manifests
cannot be read closes nothing and opens a `control-failure` for the sweep itself.

## Identity

| | |
|---|---|
| Unit | `workflow-incidents.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic python over the Control Room read model, `bin/deliver.sh` for transport |
| Runner | `bin/deliver_incidents.sh` → `bin/incident_notify.py` (exit non-zero only when the state file cannot be written; a failed send is recorded on the entry, exit 0) |
| Cadence | `OnCalendar=*:0/5`, `RandomizedDelaySec=30`, `Persistent=true` — **disabled at ship** |
| Alerted | yes — `OnFailure=agent-alert@%n.service` to `ops`; fires on a sweep that could not run, never on a failed send |
| Remediation owner | trajan |
| Retirement condition | the Control Room pushes incidents itself (then this stream has one writer too many) |
| Contract version | 1 (2026-09-15) |
| Retry | idempotent: an incident already notified is never re-sent; a failed send is retried on the next sweep up to `INCIDENT_MAX_SEND_ATTEMPTS` (6) |

## Trigger

`workflow-incidents.timer`: every five minutes, thirty seconds of jitter, `Persistent=true`.
Not enabled by any deploy step; `systemctl is-enabled workflow-incidents.timer` reads
`disabled` after land. A `--digest` run by hand sends the digest regardless of the 07:00 gate.

## Inputs

- The Control Room read model (`bin/control_room_api.py` `workflows()` and `receipts()`):
  `design/agents/*.toml` from the source checkout (`CONTROL_ROOM_REPO_ROOT`), receipts under
  `~/agent-workforce/var/workflow-receipts/`, `systemctl show --timestamp=utc` per trigger.
  Current as of the sweep; a receipt root that is unreadable or not a directory, or a manifest
  that does not parse, is itself an incident (`control-failure:incident-sweep:<source>`) and
  suspends closing.
- `~/agent-workforce/var/incidents/declared/*.json` — incidents declared by hand
  (`bin/workflow_incidents.py declare`), absent is fine.
- `~/agent-workforce/var/incidents/state.json` — the previous sweep's state; absent starts
  fresh, unparseable is moved aside as `state.json.corrupt-<stamp>` and logged, never reset in
  place.
- `bin/buzz_routes.env` `ROUTE_incidents` — the channel; empty means send nothing, keep state.
- `~/logs/delivery-receipts.jsonl` — read after each send for the `buzz_event_id` that the
  recovery message points back to.

## Outputs

- **Artifact** — Buzz messages on the `incidents` stream: `[incident] <key>` once per newly
  open immediate-class incident (workflow, agent, failure, failed check, first seen · run ·
  seen N×, required action, Control Room link, evidence), `[recovered] <key>` once per closed
  incident that was alerted (with the pointer `buzz://message?channel=…&id=…` to its alert),
  `[incident digest] N unresolved` once a day after 07:00 while anything stays open, each line
  marked `unsent (…)` where the alert never reached Buzz. State at
  `~/agent-workforce/var/incidents/state.json`; log `~/logs/workflow-incidents.log`.
- **Beneficiary:** Dave, reading the `incidents` stream.
- **Next actor:** Dave
- **Next action:** the incident's `required action` — the run's own `next_action` where the
  receipt carries one, else the class default (re-run by hand, repair the receipt, read the
  journal, restore the source).
- **Benefit hypothesis:** a failed or missing run is read within one cadence instead of at the
  next morning report, and the same failure is read once.
- **Benefit signal:** `Unknown` until the route is live; then the gap between a receipt's
  `ended_at` and its alert's event time should sit under ten minutes, and no key should carry
  more than one `[incident]` per open interval.

## Decline conditions

none. `0 open, 0 sent` is the normal sweep; an empty route, a failed send and a degraded
source are each logged with their reason and are not declines.

## Side effects

- One `bin/deliver.sh` call per message sent — never a direct Buzz call.
- `state.json` rewritten atomically every sweep; `declared/*.json` read only.
- `systemctl show` calls, read-only, for every standing trigger.

## Acceptance checks

Two `sweep` checks; both read `not applicable` (77) while the timer is disabled.

1. **The timer fired within its window.** Thirty minutes: six cadences.

   ```check id=timer-fired-within-window when=sweep
   [ "$($SYSTEMCTL show "$UNIT.timer" -p UnitFileState --value)" = "disabled" ] && exit 77
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is enabled but has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 1800 ] || { echo "last fired $(( age / 60 ))m ago"; exit 1; }
   ```

2. **The state file is fresh while the timer is active.** A sweep that runs writes it.

   ```check id=state-fresh-when-active when=sweep
   [ "$($SYSTEMCTL show "$UNIT.timer" -p UnitFileState --value)" = "disabled" ] && exit 77
   state="$HOME/agent-workforce/var/incidents/state.json"
   [ -f "$state" ] || { echo "no state file at $state"; exit 1; }
   age=$(( $(date +%s) - $(stat -c %Y "$state") ))
   [ "$age" -lt 1800 ] || { echo "state last written $(( age / 60 ))m ago"; exit 1; }
   ```

## Known failure modes

- **An empty route is silence, not an error.** Until `ROUTE_incidents` carries a UUID every
  sweep opens and closes incidents in state and sends nothing; the digest's `unsent` markers
  show what was never delivered once the route is live.
- **Recovery is only ever inferred from the next healthy run.** A workflow whose timer is
  paused after a failure stays open until it runs clean; pausing is not fixing.
- **A stale trigger is judged by the receipt sweep, not by the clock.** A timer that fired is
  an `incomplete-run` only once `workflow-receipt-sweep` has started at least
  `INCIDENT_RECEIPT_GRACE_SECS` (7200) after the fire and still no receipt started after it
  (bin/missed_receipt.py). Most standing timers are receipted by that daily sweep, so between
  a fire and the next sweep the missing receipt is the normal case, never an incident; a
  long-running job that legitimately exceeds two hours needs a larger grace on the unit, not a
  suppressed class. A `LastTriggerUSec` at or before the timer's `ActiveEnterTimestamp` is the
  `Persistent=` stamp read back on resume, not a fire, and the fleet resume touches that stamp
  on purpose — until 2026-09-17 every timer resumed that way alerted within two hours.
- **A skipped receipt is not a run.** A flock skip or a same-day dedup skip is the timer
  accounted for; the run judged is the workflow's `lastEligibleRun`, so a skip after a failed
  run neither masks nor resolves it.
- **A closed receipt is a reviewed failure, not a run to judge.** `bin/receipt_close.py`
  records who closed it and why on the receipt (T7.5); the incident it raised resolves on the
  next sweep and the recovery cites the closure. The recorded outcome is unchanged, and a new
  failed run is a new incident.
- **`contract-unavailable` never alerts.** It is a manifest gap the coverage checker owns; it
  rides the digest only.
- **The flood cap defers, it does not drop.** More than `INCIDENT_MAX_SENDS_PER_SWEEP` (10)
  new incidents in one sweep send oldest-first and the rest on the next cadence.
