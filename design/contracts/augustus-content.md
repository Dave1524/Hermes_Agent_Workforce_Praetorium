# Contract: augustus-content

One workflow, two triggers — rule 1's named live case. Everything below was read on
2026-09-10 from `systemctl cat augustus-content.{service,timer}` and
`content-change-dispatch.{service,timer}`, `bin/run_content_via_buzz.sh`,
`bin/content_change_dispatch.sh`, `bin/published_corpus.py`, `bin/content_state.sh`,
`bin/deliver_content.sh`, `bin/deliver_dispatch.sh`, `profiles/augustus_content_task.md`
and `.claude/briefs/content-corpus-namespace-and-sentinels.md`.

The two units share `AGENT_JOB_OVERRIDES` and `DELIVERY_TASK` and dispatch the same run to
the same agent over the same route. They differ only in what wakes them: a clock, or a new
`Picked` row. Splitting them into two contracts would give the corpus gate, the sentinel
table and the write boundary two places to drift.

## Identity

| | |
|---|---|
| Units | `augustus-content.service` / `.timer` + `content-change-dispatch.service` / `.timer` |
| Owner | **augustus** (`design/agents/augustus.toml`) |
| Surface | `buzz_dispatch` — a timer triggers the live augustus session over the content route and waits |
| Executor | none on this box. `run_content_via_buzz.sh` sends a trigger; the model is augustus's own `buzz-agent@augustus` session on `codex-acp`, inside its bwrap namespace |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on both live units |

The executor row is the reason this contract reads unlike its siblings. Nothing here runs a
model: the run's whole job is to prove the agent was asked, to arm what he cannot reach
himself, and to decide from outside whether he answered.

## Trigger

- `augustus-content.timer`: `OnCalendar=*-*-* 01:30`, `RandomizedDelaySec=5min`,
  `Persistent=true`. Recurring; no expiry.
- `content-change-dispatch.timer`: `OnCalendar=*:0/15`, `RandomizedDelaySec=2min`,
  `Persistent=true`. Recurring; no expiry.

Both are declared values from the unit files, not next-elapse.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| the Notion content board, via `bin/content_board_digest.sh` | read immediately before dispatch as the movement baseline | **crash (4)**: `run_content_via_buzz.sh:61` refuses to dispatch on an unknown baseline. An unreadable board makes "the board moved" undecidable, so the run would be unable to tell a draft from silence |
| `vantagepointconsulting.nl` published corpus, via `bin/published_corpus.py snapshot` on the **host** | a live `git fetch` in this run — the snapshot refuses to be written from anything else (`:314-319`) | **crash (4)**: `:84-87`. Augustus cannot fetch from inside bwrap, so a run dispatched without this gate drafts with the duplicate-title check silently not running |
| `~/agent-workforce/var/published_corpus.json` — the file augustus actually reads | written this run by the gate above; `published_corpus.py` treats a snapshot older than `SNAPSHOT_MAX_AGE_HOURS` (24) as absent | augustus's read falls through to `local-ref`, which prints `OFFLINE — origin unreachable and no host snapshot` and **exits 0**. Failing open is the nine-night failure; the gate above is what closes it |
| `profiles/augustus_content_task.md` (deployed copy) | must be readable by augustus in his own namespace | he replies `SKILL-READ-FAILED:` or `RUN-FAILED:`; the runner exits 1 and names which |
| `~/logs/delivery-receipts.jsonl` | this run's own tail, sliced at `receipts_before` | **crash (4)**: no `buzz_result == "ok"` receipt means the trigger never reached the relay — `:136`, "augustus was never asked" |
| Notion `Picked` rows, via `notion_rest.py board --status Picked --json --max-rows 0` (`content-change-dispatch` only) | current at the tick | **fail-soft**: log `FAIL-SOFT:`, exit 0, `STATE` byte-for-byte untouched. A transient Notion outage must never mark an undrafted row as seen |
| `~/agent-workforce/var/content_picked.state` (`content-change-dispatch` only) | advanced only after a dispatch that returned and recorded no `outcome=CRASHED` | absent on a fresh deploy, which makes every current `Picked` row new — deliberate |

`--max-rows 0` is load-bearing in the dispatcher. The tool caps at 2 rows for the agent that
has to draft them; a capped read here would write a truncated set to `STATE` and mark the
rows it never saw as seen.

## Outputs

- **No file artifact, by design.** The output is Notion board rows — an Idea or a Draft
  appended by augustus through `notion_rest.py`, capped at 2 per run. `deliver_content.sh`
  says so in its header and carries board state instead of attaching an invented file.
- **Delivery (`augustus-content`):** `ExecStartPost=bin/deliver_content.sh`,
  `DELIVERY_ROUTE=content` → channel `36dc03cb-…`, **event kind 45001** (forum), notify
  `augustus`. The summary is `board_delta` + `corpus_line` + the run line, and a failing
  outcome is spelled out as a failure rather than left as a `cost.log` token.
- **Delivery (`content-change-dispatch`):** `ExecStartPost=bin/deliver_dispatch.sh`,
  `DELIVERY_RUNTIME=none`. It reads back only the lines bounded by this run's marker, and a
  `no new Picked rows` tick delivers nothing at all — a quiet tick that posted would put 96
  messages a day into the content route.
- The trigger itself is also an output: one kind-45001 message on the content route
  mentioning augustus, sent by `bin/deliver.sh`, which is the only script permitted to call
  `buzz messages send`.

## Decline conditions

Exactly one legitimate decline: **augustus judges there is nothing to draft.** He replies in
the channel with a single line beginning `DECLINE:` and the reason, the runner logs
`augustus declined (event <id>) — nothing to draft`, appends `decline_event=<id>` to
`~/agent-workforce/var/content_board.snapshot`, and exits 0.

The decline is read off the **relay**, not off a log file: `sentinel_reply` gates on
augustus's pubkey and on `created_at >= dispatch_epoch`, so a decline from a previous night
cannot satisfy this one. The event id is recorded so the claim stays checkable afterwards —
`buzz social event --event <id>`.

Three things that look like declines and are not:

- `SKILL-READ-FAILED:` — a named section did not resolve in the vault `SKILL.md`. Exit 1.
- `RUN-FAILED:` — a command the profile makes non-optional exited non-zero, which is what
  the profile mandates when `published_corpus.py list` fails. Exit 1, and the profile is
  explicit that he must **not** `DECLINE:` in that case: the corpus being unreachable is not
  a judgement that there is nothing to write.
- Silence. The deadline is not proof of silence — `:236-242` re-reads the channel for any
  reply before recording one, because on 2026-09-07 augustus answered 110 seconds in, no
  branch matched, and the run spent its remaining 18 minutes logging the opposite of what
  happened.

The sentinel table is ordered so that a reply carrying both a failure prefix and `DECLINE:`
is a failed run, not a quiet night.

## Side effects

- Writes `~/agent-workforce/var/content_board.snapshot` (the pre-dispatch board digest, plus
  `decline_event=` on a decline) and `~/agent-workforce/var/published_corpus.json` (the host
  corpus capture, replaced atomically).
- `content-change-dispatch` writes `~/agent-workforce/var/content_picked.state` and appends
  to `~/agent-workforce/logs/content_change_dispatch.log`.
- Sends one message to the content route and appends a delivery receipt to
  `~/logs/delivery-receipts.jsonl`; `deliver_content.sh` / `deliver_dispatch.sh` append the
  completion receipt.
- Writes a run record to `~/agent-workforce/logs/agent_run.log`, this attempt's own output to
  `~/agent-workforce/logs/last-attempt/augustus-content.log`, and a cost line to `cost.log`.
- Touches `/home/dave/logs/run-markers/augustus-content.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`.
- **Notion writes are augustus's, not this box's.** The runner touches no board row; the rows
  move because the agent moved them, which is why board movement is the evidence the run
  reads. It writes no vault file on any branch, and runs no `git fetch` on augustus's behalf.

## Acceptance checks

Ten checks — six `run`, four `sweep`. Every block branches on `$UNIT`, because the executor
runs this file once per declaring unit and the two units are not decidable the same way: a
dispatch tick writes no attempt log of its own, and the run it dispatches records itself
under `augustus-content`. A check that does not apply to the unit it is running for exits 77
and says which.

1. **The corpus gate was armed off a live fetch this run.** The nine-night failure
   (2026-08-14 → 09-06) in one assertion. Augustus reported the corpus unreachable while the
   host receipt, seconds later, read `corpus: fetched` — both true, because they are two
   namespaces reading two things. `source=origin` is asserted rather than the mere presence
   of a corpus line, since `local-ref` prints `OFFLINE` and exits 0.

   ```check id=corpus-gate-armed
   case "$UNIT" in
     content-change-dispatch)
       echo "n/a: a tick arms no gate of its own — the run it dispatches records under augustus-content"
       exit 77 ;;
   esac
   [ -n "$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
             -name "$(basename "$AGENT_ATTEMPT_LOG")" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ] \
     || { echo "the attempt log is not this run's"; exit 1; }
   line="$(grep -F 'corpus gate armed' "$AGENT_ATTEMPT_LOG")"
   [ -n "$line" ] \
     || { echo "no corpus gate line — nobody proved the corpus was reachable before augustus was asked"; exit 1; }
   case "$line" in
     *source=origin*) ;;
     *) echo "armed off something other than a live fetch: $line"; exit 1 ;;
   esac
   ```

2. **The snapshot augustus reads is this run's own live capture.** The other half of the
   same failure, and the half the host receipt cannot see: `corpus_line()` reports what the
   *host* just fetched, never what the agent managed to read. The file is what crosses the
   namespace, so the file is what gets asserted.

   ```check id=snapshot-is-a-live-capture
   case "$UNIT" in
     content-change-dispatch) echo "n/a: a tick writes no corpus snapshot"; exit 77 ;;
   esac
   snap="$HOME/agent-workforce/var/published_corpus.json"
   [ -f "$snap" ] \
     || { echo "no snapshot at $snap — augustus's read falls through to local-ref and fails open"; exit 1; }
   [ -n "$(find "$(dirname "$snap")" -maxdepth 1 -name "$(basename "$snap")" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ] \
     || { echo "the snapshot predates this run"; exit 1; }
   grep -F '"source": "origin"' "$snap" >/dev/null
   ```

3. **The trigger reached the relay.** Asserted from the receipt, not from the send's exit
   code — `deliver.sh` is fail-soft by contract and exits 0 on a rejected send, so the
   receipt is the only evidence. A run that refused to dispatch because the corpus gate could
   not be armed is n/a here rather than a second red for one cause.

   ```check id=trigger-reached-the-relay
   case "$UNIT" in
     content-change-dispatch) echo "n/a: a tick sends no trigger; the run it dispatches does"; exit 77 ;;
   esac
   [ -n "$(grep -F 'trigger published to content' "$AGENT_ATTEMPT_LOG")" ] && exit 0
   [ -n "$(grep -F 'CRASH: the corpus gate could not be armed' "$AGENT_ATTEMPT_LOG")" ] \
     && { echo "n/a: the run refused to dispatch — corpus-gate-armed owns that failure"; exit 77; }
   echo "neither a published trigger nor the crash that would explain its absence"
   exit 1
   ```

4. **The run ended on exactly one of the seven branches this contract names.** Not "it exited
   0" — `TimeoutStartSec=45min` kills the unit with none of them written, and the three-state
   exit is only meaningful if every terminal path names itself. Two present would mean the
   wait loop fell through a branch it should have exited on.

   ```check id=run-ended-in-a-named-outcome
   case "$UNIT" in
     content-change-dispatch) echo "n/a: decided for the run this tick dispatched"; exit 77 ;;
   esac
   n=0
   for phrase in "board moved" "augustus declined (event" \
                 "augustus could not read the skill" \
                 "augustus could not complete a mandatory step" \
                 "augustus replied and no sentinel matched" \
                 "no board movement and no reply within" "CRASH: "; do
     [ -n "$(grep -F "$phrase" "$AGENT_ATTEMPT_LOG")" ] && n=$(( n + 1 ))
   done
   [ "$n" -eq 1 ] || echo "$n of the seven terminal lines present — the run ended on no named branch"
   [ "$n" -eq 1 ]
   ```

5. **Augustus was not answering with a failure.** `RUN-FAILED:` is what the profile makes him
   say when his own `published_corpus.py list` exits non-zero, so this is the agent-side tell
   for a corpus split that `corpus-gate-armed` cannot see from the host. Both prefixes were
   once handled as special cases and both were once read as declines.

   ```check id=no-failure-sentinel
   case "$UNIT" in
     content-change-dispatch) echo "n/a: decided for the run this tick dispatched"; exit 77 ;;
   esac
   hits="$(grep -F -e 'augustus could not read the skill' \
                  -e 'augustus could not complete a mandatory step' "$AGENT_ATTEMPT_LOG")"
   [ -z "$hits" ] || echo "answered, and the answer was a failure: $hits"
   [ -z "$hits" ]
   ```

6. **A decline names the event that carries it.** The decline is the one exit-0 path that
   produces nothing at all, so it is the one that most needs to stay checkable after the fact.
   `decline_event=` is appended to this run's board snapshot; `buzz social event --event <id>`
   is how a reader gets back to the words.

   ```check id=decline-is-evidenced
   case "$UNIT" in
     content-change-dispatch) echo "n/a: decided for the run this tick dispatched"; exit 77 ;;
   esac
   [ -n "$(grep -F 'augustus declined (event' "$AGENT_ATTEMPT_LOG")" ] \
     || { echo "n/a: this run did not decline"; exit 77; }
   snap="$HOME/agent-workforce/var/content_board.snapshot"
   [ -n "$(find "$(dirname "$snap")" -maxdepth 1 -name "$(basename "$snap")" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ] \
     || { echo "the board snapshot is not this run's"; exit 1; }
   grep -E '^decline_event=.+' "$snap" >/dev/null
   ```

7. **The nightly unit was not silently skipped by its own condition.** `sweep`.
   `augustus-content.service` carries `ConditionPathExists=/home/dave/agent-worktrees/inbox`.
   A failed condition makes systemd mark the unit *skipped*: exit 0, no failure state, and
   `OnFailure` never fires — so `agent-alert@` stays quiet and the nightly run simply stops
   happening. `content-change-dispatch.service` carries no condition at all, which is why
   this check is n/a there rather than duplicated.

   ```check id=not-condition-skipped when=sweep
   case "$UNIT" in
     content-change-dispatch)
       echo "n/a: content-change-dispatch.service declares no ConditionPathExists (systemctl cat, 2026-09-10)"
       exit 77 ;;
   esac
   r="$($SYSTEMCTL show "$UNIT.service" -p ConditionResult --value)"
   [ "$r" != no ] \
     || echo "ConditionPathExists=/home/dave/agent-worktrees/inbox failed — systemd skipped the unit, exit 0, no OnFailure"
   [ "$r" != no ]
   ```

8. **Each timer fired inside its own cadence.** `sweep`, and per unit — a single window would
   have to be the nightly one, and a 15-minute timer that stopped firing would then be
   invisible for a day. 26 h covers 01:30 plus the 5-minute jitter and a late `Persistent=true`
   catch-up; 1 h covers four ticks of the quarter-hourly one. The lock-skip half applies only
   to the nightly unit: for the dispatcher an overlap `SKIP` is documented, expected
   behaviour, and what it costs is asserted by `state-advanced-only-on-a-recorded-run`.

   ```check id=timer-fired-this-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   case "$UNIT" in
     augustus-content|content-change-dispatch) ;;
     *) echo "no cadence declared for $UNIT"; exit 1 ;;
   esac
   window=93600
   [ "$UNIT" = content-change-dispatch ] && window=3600
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt "$window" ] \
     || { echo "$UNIT.timer last fired ${age}s ago, past its ${window}s window"; exit 1; }
   [ "$UNIT" = content-change-dispatch ] \
     && { echo "fired ${age}s ago; an overlap SKIP is expected on this unit"; exit 0; }
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

9. **The dispatcher is not stuck fail-soft.** `sweep`, and the check the fail-soft contract
   makes necessary: every Notion read error exits 0 with `STATE` untouched and no alert, so a
   dead credential or a revoked integration is indistinguishable from a quiet board and stays
   that way indefinitely. One non-`FAIL-SOFT` tick in the last forty is the whole assertion.

   ```check id=dispatcher-is-not-stuck-fail-soft when=sweep
   case "$UNIT" in
     augustus-content)
       echo "n/a: the nightly trigger has no fail-soft path — its Notion read is augustus's, not the runner's"
       exit 77 ;;
   esac
   f="$HOME/agent-workforce/logs/content_change_dispatch.log"
   [ -f "$f" ] || { echo "the dispatcher has never logged a tick"; exit 1; }
   [ -n "$(find "$(dirname "$f")" -maxdepth 1 -name "$(basename "$f")" \
             -newermt '-2 hours' 2>/dev/null)" ] \
     || { echo "no tick logged in two hours, on a 15-minute timer"; exit 1; }
   live="$(tail -40 "$f" | grep -Fv 'FAIL-SOFT:')"
   [ -n "$live" ] \
     || echo "all of the last 40 ticks fail-softed — the Notion read has been dead and every tick exited 0"
   [ -n "$live" ]
   ```

10. **State advanced only over rows a recorded run actually drafted.** `sweep`. The 2026-08-12
    outage was rc=0 taken as evidence, and the dispatcher's own `outcome=CRASHED` guard closes
    that path — but not the one underneath it: the global flock `SKIP` exits 0 **and writes no
    `cost.log` record at all** (`bin/agent_propose.sh:144`, and the comment at `:147-151`
    explaining why it deliberately records nothing), so `crashed=0` holds vacuously and the
    tick advances `STATE` over `Picked` rows nobody drafted. Written to be red when that
    happens, because today nothing else would say so.

    ```check id=state-advanced-only-on-a-recorded-run when=sweep
    case "$UNIT" in
      augustus-content) echo "n/a: the nightly trigger keeps no picked-row state"; exit 77 ;;
    esac
    d="$HOME/agent-workforce/logs/content_change_dispatch.log"
    c="$HOME/agent-workforce/logs/cost.log"
    [ -f "$d" ] && [ -f "$c" ] || { echo "the dispatcher log or the cost log is missing"; exit 1; }
    at="$(grep -F 'dispatching Augustus draft run' "$d" | tail -1 | cut -d' ' -f1)"
    [ -n "$at" ] || { echo "n/a: no tick has ever dispatched"; exit 77; }
    backing="$(awk -v since="$at" '{ split($1, f, "="); if (f[1] == "ts" && f[2] >= since) print }' "$c" \
                 | grep -F 'task=augustus-content')"
    [ -n "$backing" ] \
      || echo "the dispatch at $at is backed by no cost.log record — a flock SKIP exits 0 and writes none, and the tick then advanced state over rows nobody drafted"
    [ -n "$backing" ]
    ```

Both logs stamp with `date -Is`, so the string comparison in the last check is a comparison of
identically-shaped local timestamps; it decides on the datetime prefix and would only be
ambiguous inside a DST repeat hour.

## Known failure modes

- **The corpus namespace split.** Nine consecutive nights, 2026-08-14 → 09-06: augustus
  reported `origin unreachable` from inside bwrap (`--tmpfs ~/.ssh`, and the site remote is
  the ssh-alias `git@github-website:`) while the host-side receipt read `corpus: fetched`.
  Neither statement was false and nothing looked broken. Closed by the transport split — the
  host runs `snapshot`, the sandbox reads the file — never by widening the namespace, which
  would hand a credential to the agent's shell to solve a problem that needs none. Signals:
  `corpus-gate-armed`, `snapshot-is-a-live-capture`, `no-failure-sentinel`.
- **Failing open on a stale corpus.** `local-ref` prints `OFFLINE — last known ref` and exits
  0, so the duplicate-title check answers "no collision" for live articles. Ten posts shipped
  2026-09-02 → 09-05 with the gate not running. The site tip was `1785209` (2026-08-11),
  644.5 h old, against a `MAX_LAG_HOURS` of 72.
- **An unrecognised sentinel logging the opposite of what happened.** `RUN-FAILED:` arrived
  2026-09-06 and fell through the same hole `SKILL-READ-FAILED:` had been special-cased out of
  in August, because a special case ends an instance and leaves the class alive. Now one row
  in `SENTINELS` plus one message, pinned against `profiles/augustus_content_task.md` in both
  directions by the verify gate. Signal: `run-ended-in-a-named-outcome`.
- **The profile never defining the corpus-refusal outcome.** Three behaviours were improvised
  across the nine nights because "what do I do when the corpus is unreachable" had no answer
  in `profiles/augustus_content_task.md`. It now does, and it is not `DECLINE:`.
- **rc=0 as a claim of success.** 2026-08-12: `agent_propose.sh` returned 0 on a run whose
  every hermes attempt had crashed, and 20 nights of `Picked` rows were marked seen without
  being drafted. Guarded by the `outcome=CRASHED` re-read; the flock `SKIP` underneath it is
  not, which is what `state-advanced-only-on-a-recorded-run` exists for.
- **Permanent fail-soft.** By contract every Notion error in the dispatcher exits 0 with state
  untouched. Correct for a blip, indistinguishable from a dead credential over a week, and
  `OnFailure` never fires either way. Signal: `dispatcher-is-not-stuck-fail-soft`.
- **A silent condition skip.** `ConditionPathExists` on the nightly unit is a skip, not a
  failure. Signal: `not-condition-skipped`.
- **Kind mismatch on delivery.** The content route is a forum (45001). A producer publishing
  kind 9 there is receipted `ok` and shown to nobody. Not currently possible — `deliver.sh`
  reads the kind from `bin/buzz_routes.env` — and the reply direction has its own version of
  this trap: augustus answers as 45003, so the wait loop deliberately filters on author and
  epoch and **never** on kind.
