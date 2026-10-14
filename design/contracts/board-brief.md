# Contract: board-brief

2026-10-14. One card's brief, started per card by the board reactor. It carries over the brief
run first shipped as the timed `research-brief` (B2, 2026-10-07), whose files it no longer
shares. Read for this contract: `bin/agent_propose.sh` (the `board` run mode and the pick),
`bin/run_board_brief_cc.sh`, `bin/brief_or_decline.sh`, `bin/board.py`,
`profiles/board_brief_cc_task.md`, `profiles/board_brief.env.example`,
`systemd/board-brief@.service`, `design/contracts/board-reactor.md` and
`.claude/briefs/agent-board-refinement-2026-09-23.md` §3.2a, §3.5 and §3.6.3-§3.6.8.

## Identity

| | |
|---|---|
| Unit | `board-brief@.service` (one instance per card, started by `board-reactor`) |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription (`bin/run_board_brief_cc.sh`) |
| Task slug | `board-brief` |
| Contract version | 1 (2026-10-14: its own files, split from research-brief) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` |
| Retry | not idempotent as a restart: a new start is a new run id. Within one run id it is: `board.py pick` returns the card the id already holds and `board.py brief` the hash it already recorded |

## Trigger

`board-brief@<card>.service`, started by `board-reactor` (`design/contracts/board-reactor.md`)
within seconds of the card wanting a brief (created, returned, or answered) when no run of it is
active, within its cooldown, the daily cap and the slot limit. `board-reconcile.timer` repeats
the same pass every five minutes, so a lost wake costs at most five minutes. No timer of its own.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| the card named by `AGENT_BOARD_CARD`, owned by claudius, kind `research`, in Backlog, via `board.py pick` under `$BOARD_ROOT` | the ledger as it stands at the start | **skipped before any model**: the wrapper writes a `skipped` receipt naming the pick, no run record, no notice |
| the card's `scope` on the vault mirror | the mirror, guarded by `vault_sync_guard.sh check` | the run `DECLINE:`s naming the missing path |
| reasons a previous brief was returned, and Dave's answers to its questions (in `card.md`) | the broker's decision stream | none yet is fine; a reason is answered, not restated |
| `profiles/board_brief_cc_task.md` and `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | the runner exits 1 naming the path; a `--plugin-dir` that does not exist is silent |
| web queries, de-identified per `docs/data_boundary.md` (generic public names only) | live | a source that cannot be fetched is skipped and the gap named in the brief |

## Outputs

- **Artifact:** one `questions` note (from `questions.out.md`, at most `board.QUESTION_ROUNDS`
  — two — per card) or one `brief` event on the card, recorded by the wrapper from
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

- The per-card lock `/tmp/agent_board_card_<card>.lock` (`AGENT_BOARD_CARD`), not the fleet
  propose lock, so two cards brief side by side.
- One `picked` event, written by the pick before the model, and one `brief` event or
  `questions` note after it.
- The run's scratch directory `$BOARD_ROOT/runs/<run_id>/` (`card.md`, `brief.out.md` or
  `questions.out.md`).
- The attempt log at `logs/last-attempt/board-brief-<card>.log`, a `cost.log` record, one
  notice line.
- Nothing in git, the inbox worktree, the vault, Notion or the ledger beyond those events.

## Acceptance checks

1. **The brief is this run's**, not an earlier one left in place. Not applicable on a run that
   declined or asked questions.

   ```check id=brief-is-this-run
   f="$AGENT_CARD_DIR/brief.out.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no brief and a declared decline"
     exit 77
   fi
   if [ ! -f "$f" ] && [ -s "$AGENT_CARD_DIR/questions.out.md" ]; then
     echo "n/a: this run asked questions"
     exit 77
   fi
   [ -n "$(find "$AGENT_CARD_DIR" -maxdepth 1 -name brief.out.md -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above, so a run producing
   neither fails both rather than passing both.

   ```check id=decline-is-this-runs-own
   [ -f "$AGENT_CARD_DIR/brief.out.md" ] && { echo "n/a: the run produced a brief"; exit 77; }
   [ -s "$AGENT_CARD_DIR/questions.out.md" ] && { echo "n/a: the run asked questions"; exit 77; }
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


A card left in Refine waits on Dave, not on this run, so it is the board sweep's `refine-stale`
exception (B6), not a check here.

8. **Questions are this run's, and within the rounds.** A run that asked questions wrote a
    fresh, non-empty `questions.out.md`; the wrapper refuses a third round and fails the run, so
    a `QUESTIONS` receipt past round two cannot exist.

    ```check id=questions-are-this-runs-own
    q="$AGENT_CARD_DIR/questions.out.md"
    [ -f "$q" ] || { echo "n/a: no questions this run"; exit 77; }
    [ -s "$q" ] || { echo "questions.out.md is empty"; exit 1; }
    [ -n "$(find "$AGENT_CARD_DIR" -maxdepth 1 -name questions.out.md -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ] \
      || { echo "questions.out.md predates this run"; exit 1; }
    ```

## Known failure modes

- **A brief that restates the idea.** Prose cannot be checked, but the bar can: a restatement
  has no checkable acceptance lines. Signal: `acceptance-has-three-to-five-lines`.
- **A scope path renamed in the vault.** The run declines naming the path, loudly, rather than
  briefing a card it cannot ground. Signal: `decline-is-this-runs-own`.
- **A returned brief re-briefed identically.** `board.py brief` refuses a text whose hash was
  already returned; the wrapper receipts the run `failed`. Signal: the receipt's reason.
- **The model writing the ledger.** The detector discards the run as a `VIOLATION`. Signal:
  `ledger-untouched-during-model`.
- **A start that never reaches a pick.** The reactor counts it; three in a row hold the card
  `poison-start` (`design/contracts/board-reactor.md`). Signal: the card's `held` event.
- **A dirty or stale mirror.** The runner runs `vault_sync_guard.sh check` first and refuses;
  `mirror-was-not-dirty` is the second lock.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure; the runner's `-r` guard names the path first.
