# Contract: board-reconcile

Written 2026-10-13 with `systemd/board-reconcile.{service,timer}` and `bin/board_reactor.py
--once`. The level-triggered half of the board reactor (`design/contracts/board-reactor.md`):
one pass every five minutes under the same flock, so a lost inotify event or a wedged daemon
costs at most five minutes, and a dead daemon is receipted.

## Identity

| | |
|---|---|
| Unit | `board-reconcile.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | platform — deterministic python, no model |
| Runner | `bin/board_reactor.py --once` (exit 0 after a pass or when paused; 2 on a permanent error) |
| Cadence | `OnBootSec=2min`, `OnUnitActiveSec=5min`, `AccuracySec=30s`, `Persistent=false` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` |
| Remediation owner | claudius |
| Retirement condition | none while the reactor is edge-triggered: inotify is a wake-up, never the source of truth |
| Contract version | 1 (2026-10-13) |
| Retry | idempotent: the pass re-derives its plan from the ledger and systemd |

## Trigger

`board-reconcile.timer`, every five minutes from two minutes after boot. A tick missed while the
box was off does not fire at boot; the boot tick covers it.

## Inputs

- Everything the reactor's pass reads (`design/contracts/board-reactor.md` § Inputs).
- `systemctl is-active board-reactor.service`.
- `/var/lib/control-room/receipts/board-reactor/*.json`: the latest applied broker action on the
  reactor. A `stop` there means Dave paused it.

## Outputs

- **Artifact** — one reactor pass (the same actions the daemon would take), and, when the daemon
  is not active and not paused, a `board-reactor` receipt `failed: permanent: daemon-dead`. Its
  own run receipt comes from the finish step (`bin/receipt_finish.py`) on a flip only.
- **Log** — the journal: the pass's action lines, or `paused`.
- **Beneficiary:** Dave, through the reactor.
- **Next actor:** none
- **Next action:** none
- **Benefit hypothesis:** with it, a card waits at most five minutes past a missed event and a dead
  reactor is red in the Control Room within five minutes.
- **Benefit signal:** `Unknown` — a pass that applies an action the daemon missed is not
  distinguished in the log yet.

## Decline conditions

none. A paused reactor is a correct exit 0 with `paused` logged.

## Side effects

- The reactor's lock, state and heartbeat under `$BOARD_ROOT/reactor/`.
- The run-unit starts, stops and ledger events its pass applies.

## Acceptance checks

1. **The timer fired within its cadence.** Fifteen minutes: three ticks.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 900 ] || { echo "last fired ${age}s ago"; exit 1; }
   ```

## Known failure modes

- **Reconcile and daemon racing.** They share `$BOARD_ROOT/reactor/lock`; the second waits.
- **A pause the broker did not receipt.** `systemctl stop` by hand leaves no broker receipt, so
  the reconcile reads the reactor as dead and receipts it; pause from the Control Room.
