# Contract: research-brief

B2, 2026-10-07. Read for this contract: `bin/agent_propose.sh` (the `board` run mode and the
pick), `bin/run_research_brief_cc.sh`, `bin/brief_or_decline.sh`, `bin/board.py`,
`profiles/research_brief_cc_task.md`, `profiles/research_brief.env.example`,
`systemd/research-brief.{service,timer}` and `.claude/briefs/agent-board-refinement-2026-09-23.md`
§3.2a, §3.5 and §3.6.3-§3.6.8. No live brief was read: the board has no card yet.

## Identity

| | |
|---|---|
| Unit | `research-brief.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription (`bin/run_research_brief_cc.sh`) |
| Task slug | `research-brief` |
| Contract version | 1 (2026-10-07) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` |
| Retry | not idempotent as a restart: a new start is a new run id and picks the next Backlog card, or none. Within one run id it is: `board.py pick` returns the card the id already holds and `board.py brief` the hash it already recorded |

## Trigger

`OnCalendar=Mon..Fri 08..18:07`, `RandomizedDelaySec=3min`, `Persistent=false` — hourly on
weekdays; a tick missed while the box was off must not fire at boot. Recurring; no expiry. The
longest legitimate gap between runs is the weekend plus the overnight gap, 72 hours.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| a Backlog card owned by claudius, kind `research`, via `board.py pick` under `$BOARD_ROOT` | the ledger as it stands at the tick | **skipped before any model**: the wrapper writes a `skipped` receipt naming the pick, no run record, no notice |
| the card's `scope` on the vault mirror | the mirror, guarded by `vault_sync_guard.sh check` | the run `DECLINE:`s naming the missing path |
| reasons a previous brief was returned (in `card.md`) | the broker's decision stream | none yet is fine; a reason is answered, not restated |
| `profiles/research_brief_cc_task.md` and `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | the runner exits 1 naming the path; a `--plugin-dir` that does not exist is silent |
| web queries, de-identified per `docs/data_boundary.md` (generic public names only) | live | a source that cannot be fetched is skipped and the gap named in the brief |

## Outputs

- **Artifact:** one `brief` event on the card, recorded by the wrapper from
  `$AGENT_CARD_DIR/brief.out.md` after the model exits; the text sits at
  `cards/<id>/briefs/<hash>.md`. The receipt's `artifact.uri` is `board://<card>/brief/<hash>`.
- **Shape:** first line `# Brief: <card id>`, then Question, Why, Scope in / out, Sources,
  Acceptance (three to five lines), Size and Questions for Dave — `board.py template --kind
  research` owns the headings and `board.py validate-brief` enforces them.
- **Delivery:** `ExecStartPost=bin/deliver_board_brief.sh`, route `research`: one line naming
  the card and where it waits, never the brief; silent on a quiet tick.
- **Beneficiary:** Dave.
- **Next actor:** Dave, in the Control Room card popup.
- **Next action:** answer the brief's questions, edit it, and approve or return it.
- **Benefit hypothesis:** an approved acceptance bar costs one extra half-day per card and
  replaces one the research run would have to infer.
- **Benefit signal:** the share of briefs approved without an edit, and the return rate, both
  countable from the ledger and the broker's stream.

## Decline conditions

The run prints, as its own line, `DECLINE: <short reason>` and writes no file when the idea is
not intelligible enough to ask a question about, the card's scope path does not exist on the
mirror, or the idea duplicates one already on the board or already proposed.
`bin/brief_or_decline.sh` matches `^DECLINE:` in **this run's own output** (`$AGENT_ATTEMPT_LOG`)
and exits 0. The STEP 0 idempotency skip prints `skip: …`, exits 3 and is receipted `skipped`.

## Side effects

- The fleet-wide propose lock, `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`; a tick that
  lands while another job holds it is the ordinary lock skip and tries again next hour.
- One `picked` event, written by the pick before the model, and one `brief` event after it.
- The run's scratch directory `$BOARD_ROOT/runs/<run_id>/` (`card.md`, `brief.out.md`).
- The attempt log at `logs/last-attempt/research-brief.log`, a `cost.log` record, one notice line.
- Nothing in git, the inbox worktree, the vault, Notion or the ledger beyond those two events.

## Acceptance checks

1. **The brief is this run's**, not an earlier one left in place. Not applicable on a run that
   declined.

   ```check id=brief-is-this-run
   f="$AGENT_CARD_DIR/brief.out.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no brief and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_CARD_DIR" -maxdepth 1 -name brief.out.md -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above, so a run producing
   neither fails both rather than passing both.

   ```check id=decline-is-this-runs-own
   [ -f "$AGENT_CARD_DIR/brief.out.md" ] && { echo "n/a: the run produced a brief"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **Every template heading is present.** A brief missing `## Acceptance` is not a short brief,
   it is one with no bar for the research run to clear.

   ```check id=brief-has-all-headings
   f="$AGENT_CARD_DIR/brief.out.md"
   [ -f "$f" ] || { echo "n/a: no brief this run"; exit 77; }
   missing=""
   for h in "Question" "Why" "Scope in / out" "Sources" "Acceptance" "Size" "Questions for Dave"; do
     grep -qxF "## $h" "$f" || missing="$missing [$h]"
   done
   [ -z "$missing" ] || echo "missing headings:$missing"
   [ -z "$missing" ]
   ```

4. **Three to five acceptance lines.** Fewer is a brief with no bar, more is a brief that will
   not fit one run.

   ```check id=acceptance-has-three-to-five-lines
   f="$AGENT_CARD_DIR/brief.out.md"
   [ -f "$f" ] || { echo "n/a: no brief this run"; exit 77; }
   n="$(sed -n '/^## Acceptance$/,/^## /{/^## /d; p}' "$f" | grep -cE '^[[:space:]]*([-*]|[0-9]+[.)])[[:space:]]+[^[:space:]]')"
   [ "$n" -ge 3 ] && [ "$n" -le 5 ] || echo "the Acceptance section has $n lines, wanted 3 to 5"
   [ "$n" -ge 3 ] && [ "$n" -le 5 ]
   ```

5. **The brief names its own card.**

   ```check id=brief-names-card
   f="$AGENT_CARD_DIR/brief.out.md"
   [ -f "$f" ] || { echo "n/a: no brief this run"; exit 77; }
   [ "$(head -n 1 "$f")" = "# Brief: $AGENT_CARD" ] || echo "first line is not '# Brief: $AGENT_CARD'"
   [ "$(head -n 1 "$f")" = "# Brief: $AGENT_CARD" ]
   ```

6. **The model did not write the ledger.** The wrapper counts the card's `events.jsonl` lines
   before and after every attempt and moves any growth to `rejected-events.jsonl`; a run that
   attempted it is already a `VIOLATION`, so this finds the leftover.

   ```check id=ledger-untouched-during-model
   [ -n "$AGENT_CARD" ] || { echo "n/a: no card this run"; exit 77; }
   f="$AGENT_CARD_DIR/rejected-events.jsonl"
   [ ! -s "$f" ] || echo "the model wrote to the ledger; the lines are in $f"
   [ ! -s "$f" ]
   ```

7. **The mirror this run read was not dirty.**

   ```check id=mirror-was-not-dirty
   [ -d "$VAULT/.git" ] || { echo "n/a: $VAULT is not a git checkout"; exit 77; }
   dirty="$(git -C "$VAULT" status --porcelain)"
   [ -z "$dirty" ] || echo "the mirror carries uncommitted changes: $dirty"
   [ -z "$dirty" ]
   ```

8. **The timer fired inside its weekday window.** `sweep`, against systemd. 4 days covers the
   72-hour weekend plus jitter; a never-fired timer fails rather than reading as 1970.

   ```check id=timer-fired-this-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 345600 ] || echo "$UNIT.timer last fired ${age}s ago, past the weekend gap plus jitter"
   [ "$age" -lt 345600 ]
   ```

9. **The run was not silently skipped by the global lock.** `sweep`: the failure is that
   nothing ran, and `SKIP: previous run still active` goes through `log()`, which tees to a
   shared file naming no job; journald scopes by unit.

   ```check id=not-lock-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

A card left in Refine waits on Dave, not on this run, so it is the board sweep's `refine-stale`
exception (B6), not a check here.

## Known failure modes

- **A brief that restates the idea.** Prose cannot be checked, but the bar can: a restatement
  has no checkable acceptance lines. Signal: `acceptance-has-three-to-five-lines`.
- **A scope path renamed in the vault.** The run declines naming the path, loudly, rather than
  briefing a card it cannot ground. Signal: `decline-is-this-runs-own`.
- **A returned brief re-briefed identically.** `board.py brief` refuses a text whose hash was
  already returned; the wrapper receipts the run `failed`. Signal: the receipt's reason.
- **The model writing the ledger.** The detector discards the run as a `VIOLATION`. Signal:
  `ledger-untouched-during-model`.
- **Silent lock skip.** Exits 0, no alert. The card stays in Backlog and the next hourly tick
  tries again, so the cost is an hour, not a night. Signal: `not-lock-skipped`.
- **A dirty or stale mirror.** The runner runs `vault_sync_guard.sh check` first and refuses;
  `mirror-was-not-dirty` is the second lock.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure; the runner's `-r` guard names the path first.
