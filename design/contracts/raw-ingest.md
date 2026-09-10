# Contract: raw-ingest

T4.2, 2026-09-10. Read for this contract: `systemctl cat raw-ingest.{service,timer}`,
`bin/run_raw_ingest_cc.sh`, `profiles/raw_ingest_cc_task.md`,
`profiles/raw_ingest.env.example`, `bin/agent_propose.sh`, `bin/proposal_or_decline.sh`,
`bin/deliver_proposal.sh`, `bin/vault_sync_guard.sh` and `bin/buzz_routes.env`. The artifact's
shape is taken from the profile's mandated format, **not** from a live proposal:
`~/agent-worktrees/inbox/` is deny-listed for this session (`~/CLAUDE.md` § Out of scope), so
no run's output was read.

## Identity

| | |
|---|---|
| Unit | `raw-ingest.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription (`bin/run_raw_ingest_cc.sh:37`) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Tue..Sat 03:00`, `RandomizedDelaySec=5min`, `Persistent=true`. Recurring; no
expiry. Tue-Sat, not daily — registry §2 recorded it as daily off a next-elapse value. 03:00
is deliberately ahead of the 04:30 standing-research slot so a source distilled tonight is
visible to research the same morning; the longest legitimate gap is the Sun/Mon pair, 72h.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `~/vault/05_knowledge/raw/` | the mirror's own state | **refuses**: `bin/vault_sync_guard.sh check` runs first (`bin/run_raw_ingest_cc.sh:26`) and exits 1 with `REFUSING to run — the vault mirror is dirty or stale` rather than distilling a source the Mac has since replaced |
| `~/vault/00_system/ingest_log.md` | same mirror, same guard | same refusal. An absent log is not an empty log: every raw file would read as unprocessed, so the guard's staleness check is what stands between a missing file and a re-ingest of the whole directory |
| existing `05_knowledge/` notes on the same subject | same mirror | proceed-and-flag under `## Existing notes checked` — the section exists to make "I looked" auditable rather than assumed |
| `_inbox/agents/<today>_raw-ingest.md` | today's date | **skip**: a same-day artifact means the run writes nothing |
| `profiles/raw_ingest_cc_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named (`:31`) — `-r`, not `-f`: an unreadable file feeds `cat(1)` the identical empty prompt |
| `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | wrapper exits 1 (`:34`); a `--plugin-dir` that does not exist is silent — exit 0, no diagnostic, no skills |
| `~/agent-worktrees/inbox` worktree | checked out and pulled by `agent_propose.sh:264` | `ConditionPathExists` on the unit; the run never starts |

No web tools. `run_raw_ingest_cc.sh:41` passes an allowlist without `WebSearch` or `WebFetch`
— everything this job needs is already on the mirror, and a distillation that reached out
would be summarising something Dave never filed.

## Outputs

- **Artifact:** exactly one file, `_inbox/agents/<YYYY-MM-DD>_raw-ingest.md`, in the inbox
  worktree. One source per run, the oldest unprocessed by mtime — not a batch.
- **Mandated sections**, in order: `## Task`, `## Source`, `## Distillation (proposed
  05_knowledge/ file + exact content)` carrying `target: vault` plus `source:` and `updates:`
  frontmatter, `## Existing notes checked`, `## Contradictions`, `## Proposed ingest_log.md
  line`, `## Confidence & gaps`.
- The `ingest_log.md` line is **proposed, not written**. This job never edits the log — that
  would be a `main` write from the box, and the promotion that appends it is Mac-side.
- **Delivery:** `ExecStartPost=bin/deliver_proposal.sh`, `DELIVERY_ROUTE=research` → channel
  `6ea596af-…`, **event kind 45001** (forum), notify `claudius`.

- **Beneficiary:** the vault, through Dave — and `standing-research` at 04:30, which reads
  `05_knowledge/` the same morning. That ordering is why this job runs at 03:00.
- **Next actor:** Dave, from the Mac.
- **Next action:** promote the distillation into `05_knowledge/` and append the proposed
  `00_system/ingest_log.md` line. This job proposes that line and never writes it.
- **Benefit hypothesis:** sources dropped into `05_knowledge/raw/` become distilled notes
  without a human doing the distilling — one per night, oldest first.
- **Benefit signal:** the backlog itself, and it is already measurable because it is this
  job's own input: `05_knowledge/raw/` minus `00_system/ingest_log.md`. A gap that does not
  shrink is the job not landing, whatever the receipts say.

## Decline conditions

One legitimate decline, and it is mechanical rather than a judgement call: **every file under
`05_knowledge/raw/` except `README.md` already appears in `00_system/ingest_log.md`.** The run
prints, as its own line, exactly:

```
DECLINE: no unprocessed sources in 05_knowledge/raw/
```

and writes no file. `bin/proposal_or_decline.sh raw-ingest` matches `^DECLINE:` in **this
run's own output** (`$AGENT_ATTEMPT_LOG`, the per-task file `agent_propose.sh:192` keeps) and
exits 0. Not the shared `agent_run.log`: until T7.1 (2026-09-10) any job's decline satisfied
every other job's check.

Because the rule is mechanical, `declined-only-when-nothing-unprocessed` below recomputes it
from the mirror instead of trusting the sentence. A decline is the *expected* outcome most
nights — this job empties a queue Dave refills by hand — which is exactly why a lazy decline
would be invisible.

Not declines: a source too large to distil in one run (distil the part that carries, and say
so under `## Confidence & gaps`), and a source that contradicts an existing note (that is
Mechanism A doing its job, and the contradiction is the finding).

## Side effects

- Checks out and pulls `~/agent-worktrees/inbox` on `agents/inbox` (`agent_propose.sh:264`).
- Commits the proposal and pushes it to the box-safe repo's `agents/inbox` branch.
- Appends this attempt's output to `~/agent-workforce/logs/agent_run.log`, keeps the attempt
  itself at `logs/last-attempt/raw-ingest.log`, and a record to `cost.log`.
- Writes one episodic line to `~/.hermes/profiles/claudius/memories/MEMORY.md` — the store
  exists, so this job records `memory=fallback`, not `no-store`.
- Touches `/home/dave/logs/run-markers/raw-ingest.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`, the fleet-wide propose lock.
- Delivery receipt appended by `bin/deliver.sh` to `~/logs/delivery-receipts.jsonl`.
- `vault_sync_guard.sh check` **reads** the mirror; `sync` is `qmd-refresh.service`'s verb,
  not this job's, so a stale mirror here is a refusal and never a fetch.

Nothing else. `agent_propose.sh:404` discards the whole run when anything outside
`_inbox/agents/` changed, recording `outcome=VIOLATION`. In particular this job does **not**
write `00_system/ingest_log.md` or `05_knowledge/`, on any branch.

## Acceptance checks

Ids are the stable names; `## Known failure modes` references them, never the numbers.

1. **The artifact is this run's**, not yesterday's left in place.

   ```check id=artifact-is-this-run
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no artifact and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_raw-ingest.md" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above, so exactly one
   decides and a run producing neither fails both.

   ```check id=decline-is-this-runs-own
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **The mirror guard passed before the agent launched.** Reads the guard's own OK line and
   the absence of its refusal, not a claim in the artifact that the mirror was fine.

   ```check id=vault-guard-passed
   [ -n "$(grep -F 'vault_sync_guard[check]: OK:' "$AGENT_ATTEMPT_LOG")" ] &&
   [ -z "$(grep -F 'REFUSING to run' "$AGENT_ATTEMPT_LOG")" ]
   ```

4. **The source is named and it exists on the mirror.** A distillation whose `## Source`
   points at nothing is not short evidence — it is a summary of a file nobody can check.

   ```check id=source-is-named-and-exists
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   src="$(sed -n '/^## Source/,/^## Distillation/p' "$f" \
            | grep -oE '05_knowledge/raw/[^[:space:])]+' | head -1)"
   [ -n "$src" ] || echo "the Source section names no path under 05_knowledge/raw/"
   [ -n "$src" ] || exit 1
   [ -e "$VAULT/$src" ] || echo "names $src, which is not on the mirror"
   [ -e "$VAULT/$src" ]
   ```

5. **The distillation carries its provenance.** `target: vault` is what the inbox tooling
   routes on, and `source:` is what makes the resulting note traceable back to the raw file a
   year from now.

   ```check id=distillation-carries-provenance
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   body="$(sed -n '/^## Distillation/,/^## Existing notes/p' "$f")"
   missing=""
   case "$body" in *"target: vault"*) ;; *) missing="$missing [target: vault]" ;; esac
   case "$body" in *"source:"*) ;; *) missing="$missing [source:]" ;; esac
   [ -z "$missing" ] || echo "the Distillation frontmatter is missing:$missing"
   [ -z "$missing" ]
   ```

6. **The existing-notes section was answered, not left blank.** The whole point of the
   section is that a distillation which never looked at `05_knowledge/` produces a duplicate
   note nobody reconciles.

   ```check id=existing-notes-checked-answered
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   body="$(sed -n '/^## Existing notes checked/,/^## Contradictions/{/^## /d; p}' "$f" | tr -d '[:space:]')"
   [ -n "$body" ] || echo "the Existing notes checked section is blank"
   [ -n "$body" ]
   ```

7. **The contradictions section was answered.** `none found this run` passes — Mechanism A's
   failure is the silent supersede, and a blank section is indistinguishable from one.

   ```check id=contradictions-answered
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   body="$(sed -n '/^## Contradictions/,/^## Proposed ingest_log/{/^## /d; p}' "$f" | tr -d '[:space:]')"
   [ -n "$body" ] || echo "the Contradictions section is blank — Mechanism A wants 'none found this run' at minimum"
   [ -n "$body" ]
   ```

8. **An `ingest_log.md` line was proposed.** Without it the source is distilled and still
   reads as unprocessed, so tomorrow's run distils it again.

   ```check id=ingest-log-line-proposed
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   body="$(sed -n '/^## Proposed ingest_log/,/^## Confidence/{/^## /d; p}' "$f" | tr -d '[:space:]')"
   [ -n "$body" ] || echo "no ingest_log.md line proposed — the source stays unprocessed and is re-ingested tomorrow"
   [ -n "$body" ]
   ```

9. **The decline was earned.** Recomputes the profile's own rule against the mirror rather
   than trusting the sentence: a run that declined while an unprocessed file sits in `raw/`
   is the lazy decline this check exists for, and it is otherwise invisible because a decline
   is the expected nightly outcome.

   ```check id=declined-only-when-nothing-unprocessed
   f="$AGENT_INBOX_DIR/${RUN_DATE}_raw-ingest.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null \
     || { echo "n/a: no decline this run"; exit 77; }
   log="$VAULT/00_system/ingest_log.md"
   [ -d "$VAULT/05_knowledge/raw" ] && [ -f "$log" ] \
     || { echo "n/a: the mirror carries no raw/ directory or no ingest log"; exit 77; }
   unprocessed=""
   for p in "$VAULT"/05_knowledge/raw/*; do
     [ -f "$p" ] || continue
     b="$(basename "$p")"
     [ "$b" = README.md ] && continue
     grep -qF "$b" "$log" || unprocessed="$unprocessed $b"
   done
   [ -z "$unprocessed" ] || echo "declined while these sources are absent from ingest_log.md:$unprocessed"
   [ -z "$unprocessed" ]
   ```

10. **The write boundary held**: the commit that added this run's file touched nothing outside
    `_inbox/agents/` — in particular not `00_system/ingest_log.md`, the one file this job is
    most tempted to helpfully update. Resolved by path rather than `HEAD~1`, because the inbox
    worktree takes commits from every job.

    ```check id=write-boundary-held
    rel="_inbox/agents/${RUN_DATE}_raw-ingest.md"
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
    the Sun/Mon gap plus jitter.

    ```check id=timer-fired-this-window when=sweep
    t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
    case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
    age=$(( $(date +%s) - ${t#@} ))
    [ "$age" -lt 345600 ] || echo "$UNIT.timer last fired ${age}s ago, past the Sun/Mon gap plus jitter"
    [ "$age" -lt 345600 ]
    ```

## Known failure modes

- **A lazy decline.** The one this job is built to hide: `DECLINE: no unprocessed sources` is
  the correct output most nights, so a run that declines while `raw/` holds three new files
  looks exactly like a healthy one, in the journal and in the delivery. Nothing upstream would
  ever say otherwise. Signal: `declined-only-when-nothing-unprocessed`, which recomputes the
  rule rather than reading the sentence.
- **Re-ingesting a source already distilled.** The mirror image, and the reason check 8
  exists: the distillation lands, no `ingest_log.md` line is proposed, the promotion appends
  nothing, and tomorrow's run picks the same oldest-by-mtime file again. Two proposals, one
  source, and the second one reads as new work. Signal: `ingest-log-line-proposed`.
- **A stale mirror.** `ingest_log.md` is Mac-published. A mirror 5 days behind reports as
  unprocessed everything the Mac has ingested since, and the run confidently re-distils it.
  Closed by the pre-flight — this job is one of only two that runs it. Signal:
  `vault-guard-passed`.
- **Provider death reading as a clean no-op.** The ancestor failure: an OpenRouter 402 killed
  the hermes/claudius path for ten days while `agent_propose.sh` logged *"OK: run completed,
  agent produced no proposal"*. Closed by `AGENT_VERIFY_CMD` — a run producing neither
  artifact nor sentinel fails. Signals: `artifact-is-this-run` / `decline-is-this-runs-own`.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure: the agent launches with no mission and, given no instructions,
  produces neither artifact nor sentinel — a FAIL with no explanation. `run_raw_ingest_cc.sh:31`
  guards it so the journal names the path instead.
- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging the SKIP. No alert, no
  artifact, and `OnFailure` never fires because nothing failed. 03:00 is the fleet's quietest
  slot, but a 23:30 bd-followup-drafts run that overran by 3.5h lands exactly here. Signal:
  `not-lock-skipped`.
- **A distillation that duplicates an existing note.** Not caught by anything mechanical —
  `existing-notes-checked-answered` asserts the section was written, not that the search was
  good. The residual risk is a near-duplicate under a different title, and it is Dave's
  promotion review that catches it.
- **Midnight rollover is a non-issue here and it is worth saying why.** `RUN_DATE` and
  `AGENT_RUN_STARTED_AT` are exported once (`agent_propose.sh:317`, `:34`) and read, never
  recomputed, so a run spanning midnight cannot disagree with itself about which file it was
  supposed to write. 03:00 is nowhere near the boundary; the sibling that *is* — `bd-stall-radar`
  at 23:00 — recomputes the date inside its kernel and does not have this property.
