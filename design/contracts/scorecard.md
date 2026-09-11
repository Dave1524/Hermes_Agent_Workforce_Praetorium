# Contract: scorecard

Read on 2026-09-11 from `systemd/scorecard.{service,timer}`, `bin/scorecard.sh`,
`bin/deliver_scorecard.sh` and `~/logs/deliver_scorecard.log`. A light contract (T4.4). Written
while the fleet was paused (`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read
`LastTriggerUSec` empty that day; the checks report that as "not loaded or never fired", which
is the correct answer.

**The digest is idempotent and is not rewritten on an unchanged week** (`bin/scorecard.sh:4-5`,
`bin/deliver_scorecard.sh:4-8`). So the digest's mtime is NOT this run's evidence, and the
delivery adapter deliberately has no freshness anchor: its silence policy is `never`, and a
Monday with nothing new still posts the rollup. The run's artifact is the delivery.

## Identity

| | |
|---|---|
| Unit | `scorecard.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell over the append-only `cost.log` |
| Runner | `bin/scorecard.sh` (fail-soft, exit 0 on every path); `ExecStartPost=bin/deliver_scorecard.sh`, `DELIVERY_ROUTE=ops` |
| Cadence | weekly, `OnCalendar=Mon 07:00`, `RandomizedDelaySec=5min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` (wired 2026-09-01, D2); covers a crash only, since the script exits 0 by design |
| Remediation owner | trajan (rollup or adapter); Dave for what the numbers say |
| Retirement condition | none — standing |
| Contract version | 1 (2026-09-11) |

## Trigger

`scorecard.timer`: `OnCalendar=Mon 07:00`, `RandomizedDelaySec=5min`, `Persistent=true`.

## Inputs

- `~/agent-workforce/logs/cost.log`, append-only, one line per agent run (`:13`).
- The previous digest, for the idempotence comparison (`:184`).

## Outputs

- **Dated artifact** — `$INBOX_WORKTREE/_inbox/agents/_metrics/scorecard.md` (`:15-16`), header
  `_As of last recorded run: <ISO ts>_` (`:149`), aggregate counts only: runs 7d / all-time,
  proposals, proposal rate, error bucket. De-identified and box-safe by construction (`:6-7`),
  and published with the proposals into the box-safe repo.
- **Delivery** — `bin/deliver_scorecard.sh` forwards the digest's headline rows to #ops every
  run (`summarising N headline row(s)` → `handed to deliver.sh (route=ops)` in
  `~/logs/deliver_scorecard.log`); receipt `job = scorecard.service`, route `ops`.
- **Beneficiary:** Dave — the one weekly view of how many runs, how many proposals, how many
  failures.
- **Next actor:** Dave.
- **Next action:** read the #ops rollup; a rising error bucket or a falling proposal rate is
  the cue to open `cost.log` and name the job.
- **Benefit hypothesis:** fleet throughput and failure rate are seen weekly without reading
  logs.
- **Benefit signal:** `Unknown`. Rollups delivered are receipted (5 on 2026-09-11); whether a
  rollup ever prompted an action is not recorded. The digest itself carries `unknown` for
  tokens and cost, honestly (`:7-8`).

## Decline conditions

none. `another rollup running — skip`, `cannot open lock`, `digest write failed — skip` all
exit 0 with the reason in the journal (`:24-25`, `:144-184`); the adapter still delivers the
previous digest, which is the right thing for a weekly rollup.

## Side effects

- Writes the digest into the inbox worktree (published onward by the inbox pipeline).
- One #ops delivery and receipt per week.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Eight days: weekly plus jitter plus a catch-up.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 691200 ] || { echo "last fired $(( age / 86400 ))d ago"; exit 1; }
   ```

2. **The digest exists and this run's rollup was delivered.** The digest is asserted to exist
   with its header, not to be fresh (idempotence); the delivery is asserted to have followed
   this run, because silence policy `never` means every Monday must receipt.

   ```check id=digest-exists-and-rollup-receipted when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   d="$INBOX_WORKTREE/_inbox/agents/_metrics/scorecard.md"
   [ -s "$d" ] && grep -q '^_As of last recorded run: ' "$d" || { echo "no digest with a header at $d"; exit 1; }
   since="$(date -u -d "@${t#@}" +%Y-%m-%dT%H:%M:%SZ)"
   awk -v s="$since" '$1 >= s' "$HOME/logs/deliver_scorecard.log" 2>/dev/null | grep -q 'handed to deliver.sh' \
     || { echo "no rollup handed to deliver.sh since $since"; exit 1; }
   ```

## Known failure modes

- **Anchoring delivery on the digest's mtime would silence the quiet weeks.** Named in the
  adapter (`deliver_scorecard.sh:4-8`); do not add a run-marker freshness check there.
- **Every path exits 0.** A lock the rollup cannot take, a digest it cannot write — all
  `skip`, all green to systemd. Only the journal and the adapter log say so; check 2 reads the
  latter.
- **Cost is `unknown` forever.** Hermes token accounting is unreliable (#4404/#20741); the
  digest says so and never fabricates. The OpenRouter dashboard is the source of truth.
- **The digest lands in the inbox worktree, so it rides the inbox pipeline.** If
  `agent-inbox-sync` stalls, the digest is still written locally and delivered to #ops; only
  its box-safe publication lags.
