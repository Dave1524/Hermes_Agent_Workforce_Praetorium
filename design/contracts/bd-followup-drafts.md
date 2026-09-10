# Contract: bd-followup-drafts

T4.2, 2026-09-10. Read for this contract: `systemctl cat bd-followup-drafts.{service,timer}`,
`bin/run_bd_followup_drafts_cc.sh`, `profiles/bd_followup_drafts_cc_task.md`,
`profiles/bd_followup_drafts.env.example`, `bin/agent_propose.sh`,
`bin/proposal_or_decline.sh`, `bin/deliver_report.sh`, `bin/deliver.sh` and
`bin/buzz_routes.env`. The artifact's shape is taken from the profile's mandated format,
**not** from a live proposal: `~/agent-worktrees/inbox/` is deny-listed for this session
(`~/CLAUDE.md` § Out of scope), so no run's output was read.

**This is the only Claudius job whose output is written to be sent to a human.** Everything
else in the fleet proposes a vault change Dave reviews at leisure; this one writes the text of
a message he pastes into an inbox. The box holds no outward credential and never sends — but a
draft that asserts something false is a draft Dave sends before he catches it, which is why
`no-draft-asserts-silence-or-elapsed-time` is the make-or-break check here rather than one
more item on a list.

## Identity

| | |
|---|---|
| Unit | `bd-followup-drafts.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription (`bin/run_bd_followup_drafts_cc.sh:37`) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Sun,Mon,Tue,Wed,Thu 23:30`, `RandomizedDelaySec=3min`, `Persistent=true`.
Recurring; no expiry. Installed-but-disabled until T2.4 (2026-09-09). The Fri/Sat pair is the
longest legitimate gap, 48h plus jitter.

`After=network-online.target qmd-mcp.service bd-stall-radar.service` and a **3-minute** jitter
rather than the fleet's 5: this slot consumes the 23:00 radar's fresh pack, and the narrower
window keeps the two from overlapping on `agent_propose.sh`'s global flock. `After=` orders
the *start*, not the lock release — a radar run that overruns 25 minutes makes this job log
`SKIP: previous run still active` and exit 0 with no alert (`agent_propose.sh:144`).

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| tonight's `_inbox/agents/<date>_bd-stall-radar.md` | same night | **proceed**: the radar pack is one of three sources, and its absence is normal — the radar declines most nights |
| Notion Client Pipeline `e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e`, rows past `Next action date` | live read | proceed-and-flag; a row with no evidenced last exchange becomes an `⚠ Unverified:` line, never a confident opener |
| Notion Task Inbox `4dbb4389-…`, due BD-scoped rows | live read | same |
| `04_operations/current_priorities.md` for parked-deal suppression | the mirror's own state | **refuses**: `bin/vault_sync_guard.sh check` runs first (`bin/run_bd_followup_drafts_cc.sh:26`) and exits 1 with `REFUSING to run — the vault mirror is dirty or stale` |
| vault evidence of the last **substantive** exchange | same mirror, same guard | same refusal. This is what the guard is protecting: the drafts are grounded in that evidence and nothing else |
| Pipeline `Last contact` | — | **known unreliable and deliberately not trusted.** Outbound email and LinkedIn leave no trace on this box; ProActive read 82d when the real touch was 6d |
| `profiles/bd_followup_drafts_cc_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named — `-r`, not `-f`: an unreadable file feeds `cat(1)` the identical empty prompt |
| `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | wrapper exits 1; a `--plugin-dir` that does not exist is silent — exit 0, no diagnostic, no skills |
| `~/agent-worktrees/inbox` worktree | checked out and pulled by `agent_propose.sh:264` | `ConditionPathExists` on the unit; the run never starts |

No web tools: `run_bd_followup_drafts_cc.sh` passes an allowlist without
`WebSearch`/`WebFetch`. Everything here is in-bubble and stays in-bubble.

## Outputs

- **Artifact:** at most one file, `_inbox/agents/<YYYY-MM-DD>_bd-followup-drafts.md`.
- **Mandated shape:** `## Task` carrying `target: none — send material, not a vault change`,
  then `## Drafts` with one `### <N>. <Company> — <Person>` block each carrying
  `- **Channel:**`, `- **Locale:**`, `- **Why now:**` and `- **The ask:**`, then `## Carried`,
  `## Dropped by the 5-draft cap`, `## Confidence & gaps`.
- **At most five drafts**, after ranking. The cap is real: six copy-paste messages at 23:30 is
  a backlog, not a morning's work, and `## Dropped by the 5-draft cap` is where the rest go so
  the ranking is visible rather than silent.
- **`target: none`.** The pack is send material and the inbox tooling must never promote it
  into the vault.
- **Delivery:** `ExecStartPost=bin/deliver_report.sh` — **not** `deliver_proposal.sh`, the only
  Claudius job wired this way. `DELIVERY_ROUTE=bd` → channel `97b5cf17-…`, kind 45001, notify
  `claudius`. `deliver_report.sh` is fail-soft by design (always exit 0) and picks the
  **newest file by name** from `REPORT_GLOB=*_bd-followup-drafts.md` within
  `MAX_REPORT_AGE_SECS = 26h`. Only `--run-marker` stops a declined run from re-sending
  yesterday's pack inside that window.
- **The job never writes Notion.** `Stage`, `Last contact` and `Next action date` stay Dave's
  call from the Mac — the same boundary the radar holds one slot earlier.

- **Beneficiary:** Dave, the next morning.
- **Next actor:** Dave, from the Mac.
- **Next action:** copy a draft, send it, and update `Stage`, `Last contact` and
  `Next action date` in Notion by hand. This job writes no Notion state, so the pack is inert
  until he acts on it.
- **Benefit hypothesis:** the missing artifact for an overdue follow-up is the message text,
  not the task row — three sends sat `Planned` in the Task Inbox for five days with the task
  already written.
- **Benefit signal:** `Unknown`, and structurally hard here: outbound email and LinkedIn leave
  no trace on this box, which is the same fact that forbids a draft from asserting silence.

## Decline conditions

One legitimate decline: **no Dave-owed BD next action today**, across all three sources, after
suppression. The run prints, as its own line, exactly:

```
DECLINE: no Dave-owed BD next action today
```

and writes no file. `bin/proposal_or_decline.sh bd-followup-drafts` matches `^DECLINE:` in
**this run's own output** (`$AGENT_ATTEMPT_LOG`, the per-task file `agent_propose.sh:192`
keeps) and exits 0. Not the shared `agent_run.log`: until T7.1 (2026-09-10) any job's decline
satisfied every other job's check.

A decline here has a second consequence the other jobs do not have: `deliver_report.sh` will
happily deliver the newest matching file it finds, and on a declined night that is *yesterday's
pack*, up to 26 hours old. The run marker is the only thing that turns that into an
`artifact_error` fault instead of a confident re-send of five messages Dave already sent.
`delivery-is-anchored-to-this-run` asserts it.

Suppression is not a decline either: Stage `Closed` / `On Hold` rows and priorities-parked
deals are dropped before ranking, and if that empties the list the decline is earned.

## Side effects

- Checks out and pulls `~/agent-worktrees/inbox` on `agents/inbox` (`agent_propose.sh:264`).
- Commits the pack and pushes it to the box-safe repo's `agents/inbox` branch.
- Reads Notion. **No Notion write, ever.**
- Appends this attempt's output to `~/agent-workforce/logs/agent_run.log`, keeps the attempt
  itself at `logs/last-attempt/bd-followup-drafts.log`, and a record to `cost.log`.
- Writes one episodic line to `~/.hermes/profiles/claudius/memories/MEMORY.md`.
- Touches `/home/dave/logs/run-markers/bd-followup-drafts.service` — load-bearing here, not
  bookkeeping: `deliver.sh:229` faults `artifact_error` on a marker that is missing or older
  than the artifact.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`, the fleet-wide propose lock.
- Delivery receipt appended by `bin/deliver.sh` to `~/logs/delivery-receipts.jsonl`.
- **No outward action.** The drafts are text in a forum post; every send is Dave's, by hand,
  from the Mac. The box holds no outward credential.

Nothing else. `agent_propose.sh:404` discards the whole run when anything outside
`_inbox/agents/` changed, recording `outcome=VIOLATION`.

## Acceptance checks

Ids are the stable names; `## Known failure modes` references them, never the numbers.

1. **The artifact is this run's**, not last night's left in place — which for this job is also
   a delivery hazard, not only a stale read.

   ```check id=artifact-is-this-run
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no artifact and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_bd-followup-drafts.md" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above, so exactly one
   decides and a run producing neither fails both.

   ```check id=decline-is-this-runs-own
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **No draft asserts silence or elapsed time.** The make-or-break rule. `Last contact` is
   known unreliable — outbound email and LinkedIn leave no trace on this box, and ProActive
   read 82 days when the real touch was 6 — so *"I haven't heard back"* is a claim this box
   cannot support and Dave cannot un-send. An `⚠ Unverified:` line saying the same thing is
   fine: it is marked, and marked is the whole contract.

   ```check id=no-draft-asserts-silence-or-elapsed-time
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   bad="$(grep -inE '(have|has)(n.t)? (heard|responded|replied)|no (response|reply) (yet|since)|still waiting|it (has|.s) been [0-9]|[0-9]+ (days|weeks|months) (ago|since)|since we (last )?(spoke|talked)|last heard from' "$f" \
            | grep -v 'Unverified')"
   [ -z "$bad" ] || echo "a draft asserts silence or elapsed time without an Unverified marker: $bad"
   [ -z "$bad" ]
   ```

4. **Every draft states its channel and its locale.** A draft written in English for a Dutch
   contact, or in email register for a LinkedIn message, is not a draft Dave can paste — and
   both are invisible in a pack that reads well.

   ```check id=every-draft-states-channel-and-locale
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -c '^### [0-9]' "$f")"
   [ "$n" -ge 1 ] || { echo "n/a: the pack carries no drafts"; exit 77; }
   ch="$(grep -c 'Channel:' "$f")"
   lo="$(grep -c 'Locale:' "$f")"
   [ "$ch" -ge "$n" ] && [ "$lo" -ge "$n" ] \
     || echo "$n draft(s), $ch Channel line(s), $lo Locale line(s)"
   [ "$ch" -ge "$n" ] && [ "$lo" -ge "$n" ]
   ```

5. **Every draft closes on a concrete ask.** A follow-up that closes on *"let me know if
   you have any thoughts"* is why the three overdue sends sat `Planned` for five days: the
   missing artifact was never the task row, it was a message with something to answer.

   ```check id=every-draft-closes-on-a-concrete-ask
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -c '^### [0-9]' "$f")"
   [ "$n" -ge 1 ] || { echo "n/a: the pack carries no drafts"; exit 77; }
   asks="$(grep -c 'The ask:' "$f")"
   [ "$asks" -ge "$n" ] || echo "$n draft(s) but only $asks stated ask(s)"
   [ "$asks" -ge "$n" ]
   ```

6. **The five-draft cap was respected.** Ranking is the job; the cap is what forces it. Six
   drafts at 23:30 is a backlog Dave triages instead of sends.

   ```check id=cap-of-five-was-respected
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -c '^### [0-9]' "$f")"
   [ "$n" -le 5 ] || echo "$n drafts — the cap is 5, and everything past it belongs under 'Dropped by the 5-draft cap'"
   [ "$n" -le 5 ]
   ```

7. **The pack is send material, not a vault change.** `target: none` is what keeps the inbox
   tooling from promoting five draft messages into `05_knowledge/`.

   ```check id=target-is-none
   f="$AGENT_INBOX_DIR/${RUN_DATE}_bd-followup-drafts.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   head="$(sed -n '/^## Task/,/^## Drafts/p' "$f")"
   ok=0
   case "$head" in *"target: none"*) ok=1 ;; esac
   [ "$ok" = 1 ] || echo "the Task section does not carry 'target: none' — the inbox tooling will treat send material as a proposed vault change"
   [ "$ok" = 1 ]
   ```

8. **The mirror guard passed before the agent launched.** Reads the guard's own OK line and
   the absence of its refusal, not a claim in the artifact that the mirror was fine. The
   drafts are grounded in vault evidence, so a stale mirror here is a confidently wrong
   message rather than a thin one.

   ```check id=vault-guard-passed
   [ -n "$(grep -F 'vault_sync_guard[check]: OK:' "$AGENT_ATTEMPT_LOG")" ] &&
   [ -z "$(grep -F 'REFUSING to run' "$AGENT_ATTEMPT_LOG")" ]
   ```

9. **The delivery is anchored to this run.** `sweep`. `deliver_report.sh` picks the newest
   file by name inside a 26-hour age budget and is fail-soft — on a declined night that is
   yesterday's pack, delivered again, receipted `ok`. The run marker is the only thing that
   turns it into an `artifact_error` fault (`deliver.sh:229`).

   ```check id=delivery-is-anchored-to-this-run when=sweep
   r="$HOME/logs/delivery-receipts.jsonl"
   [ -f "$r" ] || { echo "n/a: no delivery receipts on this box"; exit 77; }
   line="$(grep -F bd-followup-drafts "$r" | tail -1)"
   [ -n "$line" ] || { echo "n/a: this job has never delivered"; exit 77; }
   ok=0
   case "$line" in *run_marker*) ok=1 ;; esac
   [ "$ok" = 1 ] || echo "the last bd-followup-drafts receipt carries no run_marker — a declined run re-sends yesterday's pack for up to 26h and receipts it ok: $line"
   [ "$ok" = 1 ]
   ```

10. **The write boundary held**: the commit that added this run's file touched nothing outside
    `_inbox/agents/`. Resolved by path rather than `HEAD~1`, because the inbox worktree takes
    commits from every job — and at 23:30 the previous one is routinely the radar's.

    ```check id=write-boundary-held
    rel="_inbox/agents/${RUN_DATE}_bd-followup-drafts.md"
    [ -f "$INBOX_WORKTREE/$rel" ] || { echo "n/a: no artifact this run"; exit 77; }
    c="$(git -C "$INBOX_WORKTREE" log -1 --format=%H -- "$rel")"
    [ -n "$c" ] || exit 1
    [ -z "$(git -C "$INBOX_WORKTREE" show --name-only --pretty=format: "$c" \
              | grep -Ev '^(_inbox/agents/|$)')" ]
    ```

11. **The run was not silently skipped by the global lock.** `sweep`, and the likeliest red in
    this file: the 23:00 radar holds the same flock, `After=` orders the start rather than the
    release, and a skip here exits 0 with no alert and no drafts.

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

- **A draft that asserts silence.** The failure with the largest blast radius on this box,
  because the artifact is a message and the reviewer is the sender. `Last contact` is
  unreliable in a specific, measured way — outbound email and LinkedIn leave no trace here, so
  the field reads long when the real touch was recent (ProActive: 82d against 6d). The draft
  reads fluent and confident, Dave sends it, and the recipient knows better. Signal:
  `no-draft-asserts-silence-or-elapsed-time`.
- **Yesterday's pack, re-delivered.** `deliver_report.sh` is fail-soft (always exit 0), picks
  the newest file matching `*_bd-followup-drafts.md`, and accepts anything under 26 hours old.
  On a declined night that is last night's five drafts — sent to the same forum, receipted
  `ok`, indistinguishable from a fresh pack. Only `DELIVERY_RUN_MARKER` makes `deliver.sh:229`
  fault it. Signal: `delivery-is-anchored-to-this-run`.
- **Silent lock skip behind the radar.** `After=bd-stall-radar.service` orders the start, not
  the flock release. A radar run that overruns its ~25-minute budget makes this job log `SKIP:
  previous run still active` and exit 0 (`agent_propose.sh:144`): no alert, no drafts, nothing
  red. Signals: `not-lock-skipped` here, `cleared-the-2330-slot` in the radar's contract.
- **A stale or dirty mirror.** The drafts are grounded in vault evidence of the last
  substantive exchange; a mirror the Mac has since replaced produces confident references to
  a conversation that went differently. This is one of only two jobs running the pre-flight,
  and it is the one that most needs it. Signal: `vault-guard-passed`.
- **Cap creep.** Six or seven drafts is what happens when ranking is skipped rather than done,
  and it converts a 5-minute morning task into triage. Signal: `cap-of-five-was-respected`;
  the ranking's *quality* is Dave's read, not a check.
- **A closed or parked deal in the pack.** Suppression runs on Stage `Closed`/`On Hold` and on
  priorities-parked deals, upstream of ranking. Not checked here — the radar's
  `no-terminal-stage-was-flagged` covers the same rule one slot earlier, and a pack sourced
  from Notion rows directly could still carry one.
- **Provider death reading as a clean no-op.** The ancestor failure across this fleet: an
  OpenRouter 402 once produced ten days of `OK: run completed, agent produced no proposal`.
  Closed by `AGENT_VERIFY_CMD`. Signals: `artifact-is-this-run` / `decline-is-this-runs-own`.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure. Guarded in the wrapper so the journal names the path.
- **Midnight rollover.** `RUN_DATE` and `AGENT_RUN_STARTED_AT` are exported once
  (`agent_propose.sh:317`, `:34`) and read, never recomputed, so this job cannot disagree with
  itself about the filename the way the radar's kernel can — 23:30 plus 3 minutes of jitter
  plus retries crosses midnight routinely, and the date stays the run's own throughout.
