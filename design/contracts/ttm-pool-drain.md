# Contract: ttm-pool-drain

Read on 2026-09-11 from `systemd/ttm-pool-drain.{service,timer}` and the unit's journal. The
runner, `/usr/local/bin/ttm-pool-drain`, is root-owned, **not tracked in this repo**
(`systemd/ttm-pool-drain.service:2-3`), and was read in place. A light contract (T4.4). Written
while the fleet was paused (`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read
`LastTriggerUSec` empty that day; the checks report that as "not loaded or never fired", which is
the correct answer.

This is the one job on the list whose cadence is two minutes. Its alert is throttled for that
reason — one on the transition into failure, one reminder per 24 h — and the unit file says the
throttle is a precondition for carrying `OnFailure` at all (`:6-9`).

## Identity

| | |
|---|---|
| Unit | `ttm-pool-drain.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic POSIX sh against one debugfs knob |
| Runner | `/usr/local/bin/ttm-pool-drain`, `TTM_DRAIN_THRESHOLD_MB=1024`, `Nice=10`, `IOSchedulingClass=idle` |
| Cadence | `OnBootSec=2min`, then every 2 minutes (`OnUnitActiveSec=2min`), `AccuracySec=1min`, `Persistent=false` |
| Alerted | yes — `OnFailure=agent-alert@%n.service`, throttled by `bin/agent_alert.sh` |
| Remediation owner | Dave — a failing drain is a kernel/driver matter (xe, debugfs), not a workforce one |
| Retirement condition | the `xe` driver stops hoarding pooled pages after an ollama unload (`:1-2`), or the GPU workload leaves this box. Not decidable from the box in a check; recorded as prose |
| Contract version | 1 (2026-09-11) |

## Trigger

`ttm-pool-drain.timer`: monotonic — `OnBootSec=2min`, `OnUnitActiveSec=2min`,
`AccuracySec=1min`, `Persistent=false`.

## Inputs

- `/sys/kernel/debug/ttm/page_pool_shrink` — readable only as root; the script exits 0 when
  it cannot read it, so a box without debugfs is a quiet no-op rather than a failure.
- `TTM_DRAIN_THRESHOLD_MB` (1024) — below it, nothing is drained.

## Outputs

- **State change** — genuinely free pooled pages returned to the kernel; never memory held by
  a loaded model (`:18-19`).
- **Verdict line** — one journal line per run: `ttm-pool-drain: pool <N>MB < threshold
  1024MB — nothing to do` or `ttm-pool-drain: <start>MB -> <end>MB (freed N MB in R rounds)`.
- **Beneficiary:** every process on the box that wants RAM after an ollama unload —
  concretely the agent runs and the interactive CLIs, which otherwise compete with ~14 GB the
  driver is holding for nobody.
- **Next actor:** nobody. Silent success is the whole design.
- **Next action:** none; on a throttled alert, `journalctl -u ttm-pool-drain.service -n 20`
  and `cat /sys/kernel/debug/ttm/page_pool_shrink` as root.
- **Benefit hypothesis:** the pool never sits above 1 GB for more than ~3 minutes.
- **Benefit signal:** `Unknown` as a rate. The journal's `freed N MB` lines are the raw
  material; nothing sums them.

## Decline conditions

none. An unreadable knob exits 0 with no work done — a skip, not a decline, and one that
cannot be distinguished from "nothing to do" in the journal. Known and accepted for a hygiene
job.

## Side effects

- Writes to a debugfs knob as root. Nothing on disk; no delivery, no receipt.
- 720 journal lines a day. `journalctl -u ttm-pool-drain.service` is the only history.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Ten minutes: five ticks, generous for `AccuracySec`
   coalescing.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 600 ] || { echo "last fired $(( age / 60 ))min ago"; exit 1; }
   ```

2. **The last run gave a verdict.** One `ttm-pool-drain:` line since the trigger; a run that
   fired and logged nothing is a script that died before reading the knob.

   ```check id=verdict-present when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   $JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager -o cat \
     | grep -qE '^ttm-pool-drain: (pool [0-9]+MB < threshold|[0-9]+MB -> [0-9]+MB)' \
     || { echo "no ttm-pool-drain verdict since $t"; exit 1; }
   ```

## Known failure modes

- **A stuck drain would page 720 times a day** without the throttle in `bin/agent_alert.sh`.
  The unit comment (`:6-9`) makes the throttle a precondition; do not deploy this unit onto a
  box whose `agent-alert@.service` lacks it.
- **The runner is outside the repo.** `/usr/local/bin/ttm-pool-drain` is not drift-checked and
  has no source of truth here; an edit to it is invisible to `bin/check_deploy_drift.sh`.
  Recorded, not fixed (T4.4 is contracts only).
- **Unreadable knob reads as success.** Exit 0 with no work is indistinguishable from "under
  threshold" except by the verdict text, which check 2 does not distinguish either. A box
  that lost debugfs would pass this contract while draining nothing.
- **`Persistent=false`.** A missed tick is simply missed; correct for a two-minute job, and
  the reason check 1's window is five ticks rather than one.
