# Contract: bd-stall-radar

T4.2, 2026-09-10. Read for this contract: `systemctl cat bd-stall-radar.{service,timer}`,
`bin/run_bd_stall_radar_cc.sh`, `bin/bd_stall_radar_kernel.py`,
`profiles/bd_stall_radar_task.md`, `profiles/bd_stall_radar.env.example`,
`bin/agent_propose.sh`, `bin/proposal_or_decline.sh`, `bin/deliver_proposal.sh` and
`bin/buzz_routes.env`. The artifact's shape is taken from the kernel's own output format,
**not** from a live proposal: `~/agent-worktrees/inbox/` is deny-listed for this session
(`~/CLAUDE.md` § Out of scope), so no run's output was read.

**The rules are deterministic and they live in Python.** `bin/bd_stall_radar_kernel.py` owns
`IN_SCOPE_STAGES`, `STALL_DAYS = 7`, `AGING_FLOOR = 60` and `DEDUP_WINDOW_DAYS = 3`; the profile
forbids reimplementing any of them in prose. The agent's job is to run the kernel, read its
output, and write it up. That split is why most checks below read the kernel's own lines out
of the attempt log rather than judging the artifact's reasoning.

## Identity

| | |
|---|---|
| Unit | `bd-stall-radar.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-sonnet-5`, box subscription (`bin/run_bd_stall_radar_cc.sh:28`) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Sun,Mon,Tue,Wed,Thu 23:00`, `RandomizedDelaySec=5min`, `Persistent=true`.
Recurring; no expiry. Installed-but-disabled until T2.4 (2026-09-09) — registry §7.5 called it
"not yet wired" and this repo's manifest called it `planned`; it is `standing` now because the
box says so. The Fri/Sat pair is the longest legitimate gap, 48h plus jitter.

23:00 exists to feed 23:30: `bd-followup-drafts.service` has `After=bd-stall-radar.service`
and consumes this pack the same night. That half-hour is a budget, not a coincidence — see
`cleared-the-2330-slot`.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| Notion Client Pipeline `e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e`, read by the kernel | live read at run time | the kernel fails loudly rather than reporting zero deals — but **a query that returns an empty set is not distinguishable from a quiet pipeline** in the summary line alone, which is what `deal-count-was-not-zero` is for |
| `04_operations/current_priorities.md` via qmd, for suppression | the mirror's own state | **proceeds, degraded, and says so**: the kernel prints `[warn] current_priorities.md empty via qmd — suppression degraded` and flags deals Dave has already parked. A warning, not a refusal |
| `~/.hermes/profiles/claudius/memories/MEMORY.md`, for the 3-day dedup window | whatever is on disk | absent means no dedup: the same stall is flagged three nights running |
| `~/vault` mirror as a whole | **unguarded on this job** — `bin/run_bd_stall_radar_cc.sh` runs no `vault_sync_guard.sh check`, unlike `run_raw_ingest_cc.sh:26` and `run_bd_followup_drafts_cc.sh:26` | proceeds silently; `mirror-was-not-dirty` stands in for the missing pre-flight |
| `profiles/bd_stall_radar_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named — `-r`, not `-f`: an unreadable file feeds `cat(1)` the identical empty prompt |
| `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | wrapper exits 1; a `--plugin-dir` that does not exist is silent — exit 0, no diagnostic, no skills |
| `~/agent-worktrees/inbox` worktree | checked out and pulled by `agent_propose.sh:264` | `ConditionPathExists` on the unit; the run never starts |

No web tools: `run_bd_stall_radar_cc.sh` passes an allowlist without `WebSearch`/`WebFetch`.
Everything this job reasons over is in-bubble by construction.

## Outputs

- **Artifact:** at most one file, `_inbox/agents/<YYYY-MM-DD>_bd-stall-radar.md`, written by
  the kernel, which announces it as `=> wrote _inbox/agents/<date>_bd-stall-radar.md (N flagged)`.
- **Kernel summary line**, always, on stdout:
  `bd-stall-radar (deterministic) <today> — N deals, M Prospect&unworked, K flagged (W warm, A aging, U never contacted)`.
  This line is the run's own audit trail and several checks below read it.
- **Delivery:** `ExecStartPost=bin/deliver_proposal.sh`, `DELIVERY_ROUTE=bd` → channel
  `97b5cf17-…`, **event kind 45001** (forum), notify `claudius`.
- **The radar flags and stops.** It never writes Notion — not `Stage`, not `Last contact`, not
  `Next action date` — and it never drafts the message. The draft is 23:30's job; the state
  change is Dave's, from the Mac.

- **Beneficiary:** Dave — and `bd-followup-drafts` one slot later, which is the only job on
  this box whose input is another job's artifact.
- **Next actor:** `bd-followup-drafts` at 23:30, then Dave.
- **Next action:** the 23:30 job drafts a message for each flagged deal; Dave sends it and
  moves `Stage` and `Last contact` from the Mac. The radar flags and stops.
- **Benefit hypothesis:** a deal that has gone quiet surfaces while it is still warm instead
  of at the next pipeline review.
- **Benefit signal:** `Unknown`. The right measure is flagged-to-sent within the week, and it
  needs Notion `Last contact`, which is known-unreliable on this box for exactly the reason
  `bd-followup-drafts` forbids any claim about elapsed silence.

## Decline conditions

One legitimate decline: **no genuine new stalls tonight**, after suppression and the 3-day
dedup window. The kernel prints, as its own line, exactly:

```
DECLINE: no genuine new stalls
```

and writes no file. `bin/proposal_or_decline.sh bd-stall-radar` matches `^DECLINE:` in **this
run's own output** (`$AGENT_ATTEMPT_LOG`, the per-task file `agent_propose.sh:192` keeps) and
exits 0. Not the shared `agent_run.log`: until T7.1 (2026-09-10) any job's decline satisfied
every other job's check.

A decline here is common and correct — a pipeline where nothing newly stalled for 7 days is a
pipeline being worked. The dangerous decline is the *vacuous* one: a Notion read that returned
nothing, a `current_priorities.md` that suppressed everything, or a dedup window that ate a
stall it should have re-raised. `deal-count-was-not-zero` and `priorities-suppression-was-live`
exist because all three of those produce the same clean, quiet, correct-looking night.

## Side effects

- Checks out and pulls `~/agent-worktrees/inbox` on `agents/inbox` (`agent_propose.sh:264`).
- Commits the proposal and pushes it to the box-safe repo's `agents/inbox` branch.
- Reads Notion. **No Notion write, ever** — a state change from this box would silently
  overwrite Dave's own pipeline edits and there is no audit trail on the far side.
- Appends this attempt's output to `~/agent-workforce/logs/agent_run.log`, keeps the attempt
  itself at `logs/last-attempt/bd-stall-radar.log`, and a record to `cost.log`.
- Writes one episodic line to `~/.hermes/profiles/claudius/memories/MEMORY.md` — the same file
  the kernel reads for its dedup window, so this job's memory is load-bearing rather than
  decorative.
- Touches `/home/dave/logs/run-markers/bd-stall-radar.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`, the fleet-wide propose lock — and
  must give it back before 23:30.
- Delivery receipt appended by `bin/deliver.sh` to `~/logs/delivery-receipts.jsonl`.

Nothing else. `agent_propose.sh:404` discards the whole run when anything outside
`_inbox/agents/` changed, recording `outcome=VIOLATION`.

## Acceptance checks

Ids are the stable names; `## Known failure modes` references them, never the numbers.

1. **The artifact is this run's**, not last night's left in place.

   ```check id=artifact-is-this-run
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-stall-radar.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no artifact and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_bd-stall-radar.md" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above, so exactly one
   decides and a run producing neither fails both.

   ```check id=decline-is-this-runs-own
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-stall-radar.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **The kernel actually ran.** The deterministic pass is the whole contract; an agent that
   reasoned its way to a plausible stall list without invoking it produces an artifact that
   looks right and obeys none of the thresholds.

   ```check id=kernel-actually-ran
   [ -n "$(grep -F 'bd-stall-radar (deterministic)' "$AGENT_ATTEMPT_LOG")" ] \
     || echo "the kernel's summary line is absent — nothing proves bd_stall_radar_kernel.py ran this night"
   [ -n "$(grep -F 'bd-stall-radar (deterministic)' "$AGENT_ATTEMPT_LOG")" ]
   ```

4. **The deal count was not zero.** A Notion query that returns an empty set produces
   `0 deals, 0 Prospect&unworked, 0 flagged` and then a perfectly ordinary `DECLINE:` — the same
   output as a healthy pipeline with nothing newly stalled. This is the check that tells the
   two apart, and without it the job can be silently dead for weeks.

   ```check id=deal-count-was-not-zero
   line="$(grep -F 'bd-stall-radar (deterministic)' "$AGENT_ATTEMPT_LOG" | tail -1)"
   [ -n "$line" ] || { echo "n/a: no kernel summary line to read"; exit 77; }
   deals="$(echo "$line" | sed -n 's/.*[^0-9]\([0-9][0-9]*\) deals.*/\1/p')"
   [ -n "$deals" ] || { echo "the summary line carries no deal count: $line"; exit 1; }
   [ "$deals" -gt 0 ] || echo "the pipeline query returned 0 deals — the decline is vacuous, not earned"
   [ "$deals" -gt 0 ]
   ```

5. **Priorities suppression was live.** With `current_priorities.md` unreadable via qmd the
   kernel keeps going and flags deals Dave has already parked. It says so, once, and the line
   scrolls past in a 300-line journal.

   ```check id=priorities-suppression-was-live
   [ -z "$(grep -F 'suppression degraded' "$AGENT_ATTEMPT_LOG")" ] \
     || echo "the kernel ran with current_priorities.md empty via qmd — parked deals were not suppressed"
   [ -z "$(grep -F 'suppression degraded' "$AGENT_ATTEMPT_LOG")" ]
   ```

6. **No out-of-scope-stage deal was flagged.** `IN_SCOPE_STAGES` is `{"Prospect"}` since
   2026-09-11: `Closed` and `On Hold` were never in scope, and `Qualified` / `Proposal` /
   `Active` are the accounts Dave is working. A pack naming any of them is a rule that stopped
   being applied — a follow-up on a closed deal, or a report of the work being done instead of
   the work that is not.

   ```check id=no-terminal-stage-was-flagged
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-stall-radar.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   hits="$(grep -nE 'Stage[^A-Za-z]*(Closed|On Hold|Qualified|Proposal|Active)' "$f")"
   [ -z "$hits" ] || echo "an out-of-scope-stage deal was flagged: $hits"
   [ -z "$hits" ]
   ```

7. **The file the kernel wrote is dated for this run.** The kernel takes its date from
   `dt.date.today()`; everything else on the path takes it from `RUN_DATE`, exported once at
   `agent_propose.sh:317`. At 23:00 plus jitter, with retries, those two can disagree — and
   when they do, every check keyed on `RUN_DATE` reports a missing artifact for a file that
   exists under tomorrow's name.

   ```check id=kernel-date-matched-the-run
   wrote="$(grep -oE '_inbox/agents/[0-9]{4}-[0-9]{2}-[0-9]{2}_bd-stall-radar\.md' \
              "$AGENT_ATTEMPT_LOG" | tail -1)"
   [ -n "$wrote" ] || { echo "n/a: the kernel wrote no proposal this run"; exit 77; }
   want="_inbox/agents/${RUN_DATE}_bd-stall-radar.md"
   [ "$wrote" = "$want" ] || echo "the kernel wrote $wrote while this run is dated $RUN_DATE — dt.date.today() crossed midnight ahead of RUN_DATE"
   [ "$wrote" = "$want" ]
   ```

8. **The run cleared the 23:30 slot.** `sweep`. `bd-followup-drafts` takes the same fleet-wide
   flock half an hour later and consumes this pack; an overrun does not fail this job, it
   makes the *next* one exit 0 with `SKIP: previous run still active` and no alert. 1500s is
   the budget: 23:00 plus up to 5 minutes of jitter leaves ~25 minutes.

   ```check id=cleared-the-2330-slot when=sweep
   c="$HOME/agent-workforce/logs/cost.log"
   [ -f "$c" ] || { echo "n/a: no cost.log on this box"; exit 77; }
   row="$(grep -F ' task=bd-stall-radar ' "$c" | tail -1)"
   [ -n "$row" ] || { echo "n/a: this job has no cost.log record yet"; exit 77; }
   secs=""
   for tok in $row; do
     case "$tok" in run_seconds=*) secs="${tok#run_seconds=}" ;; esac
   done
   [ -n "$secs" ] || { echo "n/a: the record carries no run_seconds"; exit 77; }
   [ "$secs" -lt 1500 ] || echo "the last run took ${secs}s — past the ~25min this slot has before bd-followup-drafts wants the same flock"
   [ "$secs" -lt 1500 ]
   ```

9. **The mirror this run read was not dirty.** This job runs no `vault_sync_guard.sh`
   pre-flight, so nothing else on the path would have refused. `$VAULT` is already resolved
   by the executor — `~/vault` is a symlink and a check that records the link rather than its
   target does not survive cutover.

   ```check id=mirror-was-not-dirty
   [ -d "$VAULT/.git" ] || { echo "n/a: $VAULT is not a git checkout"; exit 77; }
   dirty="$(git -C "$VAULT" status --porcelain)"
   [ -z "$dirty" ] || echo "the mirror carries uncommitted changes and this job has no vault_sync_guard pre-flight: $dirty"
   [ -z "$dirty" ]
   ```

10. **The write boundary held**: the commit that added this run's file touched nothing outside
    `_inbox/agents/`. Resolved by path rather than `HEAD~1`, because the inbox worktree takes
    commits from every job — and at 23:00 the sibling half an hour behind is the likeliest
    author of the previous one.

    ```check id=write-boundary-held
    rel="_inbox/agents/${RUN_DATE}_bd-stall-radar.md"
    [ -f "$INBOX_WORKTREE/$rel" ] || { echo "n/a: no artifact this run"; exit 77; }
    c="$(git -C "$INBOX_WORKTREE" log -1 --format=%H -- "$rel")"
    [ -n "$c" ] || exit 1
    [ -z "$(git -C "$INBOX_WORKTREE" show --name-only --pretty=format: "$c" \
              | grep -Ev '^(_inbox/agents/|$)')" ]
    ```

11. **The run was not silently skipped by the global lock.** `sweep`, because the failure is
    that nothing ran. journald scopes by unit; the shared `agent_run.log` the SKIP also lands
    in names no job.

    ```check id=not-lock-skipped when=sweep
    t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
    case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
    [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
              | grep -F 'SKIP: previous run still active')" ]
    ```

12. **The timer fired inside its window.** `sweep`, asserted against systemd. 4 days covers
    the Fri/Sat gap plus jitter with room to spare.

    ```check id=timer-fired-this-window when=sweep
    t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
    case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
    age=$(( $(date +%s) - ${t#@} ))
    [ "$age" -lt 345600 ] || echo "$UNIT.timer last fired ${age}s ago, past the Fri/Sat gap plus jitter"
    [ "$age" -lt 345600 ]
    ```

## Known failure modes

- **The vacuous decline.** The defining failure of this job: an empty pipeline read, a
  suppression list that swallowed everything, or a dedup window that ate a re-raise all end in
  `DECLINE: no genuine new stalls` — the same line a healthy quiet night produces, delivered
  to the same forum, receipted the same way. Signals: `deal-count-was-not-zero`,
  `priorities-suppression-was-live`, `kernel-actually-ran`.
- **Midnight rollover between the kernel and the run.** `bd_stall_radar_kernel.py` computes
  its date with `dt.date.today()` while everything around it uses `RUN_DATE`, exported once at
  `agent_propose.sh:317` and never recomputed. A 23:00 run with jitter and up to two retries
  can cross midnight; the kernel then writes tomorrow's filename into today's run, and every
  `RUN_DATE`-keyed check reports a missing artifact that is sitting right there. Signal:
  `kernel-date-matched-the-run`. The real fix is passing `RUN_DATE` into the kernel, which is
  a change to `bin/`, not to this file.
- **Overrunning into the 23:30 slot.** This job's overrun is charged to its sibling:
  `bd-followup-drafts` finds the flock held, logs `SKIP: previous run still active`, exits 0
  (`agent_propose.sh:144`), and Dave gets no drafts with nothing red anywhere. The `After=`
  ordering makes 23:30 wait for 23:00 to *finish starting*, not to release the lock. Signals:
  `cleared-the-2330-slot` here, `not-lock-skipped` in the sibling's contract.
- **Rules drifting into prose.** The thresholds live in Python precisely so a task profile
  cannot quietly hold a second copy. A profile that reimplements "7 days" is a fork of the
  rule that no test compares. `kernel-actually-ran` catches the extreme case — the kernel not
  running at all — and nothing catches a subtler paraphrase.
- **A Notion write.** Out of contract, and the one side effect with no undo: `Stage` and
  `Last contact` are Dave's, edited from the Mac, and an overwrite from here leaves no trace
  on the far side. Not mechanically checked — the profile forbids it and the broker's write
  policy is a separate surface from this runner.
- **Provider death reading as a clean no-op.** The ancestor failure across this fleet: a
  provider error that produces neither artifact nor sentinel used to log as `OK: run
  completed, agent produced no proposal`. Closed by `AGENT_VERIFY_CMD`. Signals:
  `artifact-is-this-run` / `decline-is-this-runs-own`.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure. Guarded in the wrapper so the journal names the path.
- **Stale or dirty mirror, unguarded.** Suppression reads `current_priorities.md` off the
  mirror; a stale mirror suppresses last week's priorities. The kernel's `[warn]` line covers
  *empty*, not *stale*. Signal: `mirror-was-not-dirty`.
