# Contract: standing-research

T4.2, 2026-09-10. Read for this contract: `systemctl cat agent-proposal.{service,timer}`,
`bin/run_standing_research_cc.sh`, `profiles/standing_research_cc_task.md`,
`profiles/standing_research.env.example`, `bin/agent_propose.sh`,
`bin/proposal_or_decline.sh`, `bin/deliver_proposal.sh`, `bin/published_corpus.py` and
`bin/buzz_routes.env`. The artifact's shape is taken from the profile's mandated format,
**not** from a live proposal: `~/agent-worktrees/inbox/` is deny-listed for this session
(`~/CLAUDE.md` § Out of scope), so no run's output was read.

**The file stem is not the unit name.** The unit is `agent-proposal` — the generic name it
was installed under in NUC-16 — and the workflow is standing research. Rule 1 is opted out
of in the manifest (`rule1_exempt` on the declaring `[[workflows]]` entry), never in this
prose. Every check below therefore hardcodes the `standing-research` slug and uses `$UNIT`
only for systemd and the journal, which know it by the other name.

## Identity

| | |
|---|---|
| Unit | `agent-proposal.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription (`bin/run_standing_research_cc.sh:43`) |
| Task slug | `standing-research` — the artifact name, the attempt log and `AGENT_VERIFY_CMD` all key on this, not on `agent-proposal` |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Mon..Fri 04:30`, `RandomizedDelaySec=5min`, `Persistent=true`. Recurring; no
expiry. Weekday-only, so the longest legitimate gap between runs is the 72h weekend —
registry §2 recorded this as "daily" off a next-elapse value (`agent-model.md` §6.8).

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `04_operations/box_brief/queue.md` (qmd CLI over the mirror) | regenerated at Dave's EOD wrap; a run works the soonest-deadline OPEN item | **proceed**: falls through to a standing mission, and to `DECLINE:` if nothing qualifies. Nothing detects a queue that stopped being regenerated |
| `04_operations/box_brief/standing_missions.md` | same mirror | same fall-through; the missions carry their own cadences |
| `04_operations/current_priorities.md`, `open_loops.md` | same mirror, background context only | proceed-and-flag under *Confidence & gaps* |
| `~/vault` mirror as a whole | **unguarded on this job** — `bin/run_standing_research_cc.sh` runs no `vault_sync_guard.sh check`, unlike `run_raw_ingest_cc.sh:26` and `run_bd_followup_drafts_cc.sh:26` | **proceeds silently.** This is the one input with no refusal behind it, and `mirror-was-not-dirty` is what stands in its place |
| `_inbox/agents/` recent proposals + `_metrics/approvals.tsv` | last 5 files, working-memory substitute (no hermes MEMORY on this runtime) | absent is fine — the profile reads it with `2>/dev/null` |
| existing `_inbox/agents/<today>_standing-research.md` | today's date | **skip**: STEP 0 prints `skip: today's standing-research already exists` and writes nothing |
| the published corpus, via `bin/published_corpus.py list` / `check` | a git read of the site repo's `origin/main`, not a web fetch | **refuses**: `published_corpus.py:152` exits with `REFUSING — origin unreachable` rather than answering off a stale snapshot |
| `profiles/standing_research_cc_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named (`:33`) — `-r`, not `-f`, because an unreadable file feeds `cat(1)` the identical empty prompt |
| `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | wrapper exits 1 (`:36`); a `--plugin-dir` that does not exist is silent — exit 0, no diagnostic, no skills |
| `~/agent-worktrees/inbox` worktree | checked out and pulled by `agent_propose.sh:264` | `ConditionPathExists` on the unit; the run never starts |

## Outputs

- **Artifact:** exactly one file, `_inbox/agents/<YYYY-MM-DD>_standing-research.md`, in the
  inbox worktree. A **fixed** filename, not a topic slug — that is what makes the run
  verifiable deterministically rather than by guessing at a name.
- **Mandated sections**, in order: `## Task`, `## Key findings (fact vs inference labeled)`,
  `## Contradictions`, `## Proposed vault change (target canonical file + exact content)`
  carrying `target: vault`, `## Confidence & gaps`.
- Every claim is labelled `FACT:` (with its source) or `INFERENCE:`. Mechanism A —
  contradiction flagging — is mandatory, and `## Contradictions` says `none found this run`
  rather than being left blank.
- **Delivery:** `ExecStartPost=bin/deliver_proposal.sh`, `DELIVERY_ROUTE=research` → channel
  `6ea596af-…`, **event kind 45001** (forum), notify `claudius`. A kind-9 post into that
  channel is receipted `ok` and shown to nobody.
- Downstream: the proposal syncs to the Notion Agent Inbox and is Mac-gated for approval.

## Decline conditions

One legitimate decline: **nothing in the queue or the standing missions can be completed at
quality this run.** The run then prints, as its own line:

```
DECLINE: <short reason>
```

and writes no file. `bin/proposal_or_decline.sh standing-research` matches `^DECLINE:` in
**this run's own output** (`$AGENT_ATTEMPT_LOG`, the per-task file `agent_propose.sh:192`
keeps) and exits 0. Not the shared `agent_run.log`: until T7.1 (2026-09-10) any job's
decline satisfied every other job's check.

A **collision** is not a decline. When `published_corpus.py check` reports the brief's title
already published, the correct output is a short collision report naming the live slug —
still one proposal file, still this run's — because the brief was faulty and Dave needs to
see that, not silence.

The STEP 0 idempotency skip is **not** a decline: it prints `skip: …` and no artifact, so
`proposal_or_decline.sh` fails the run. Measured on this box — the 2026-09-09 09:50 and
10:03 canary rows in `cost.log` are exactly that, `outcome=FAIL attempts=2` on a job that
had already run that morning. Intended (a second run in one day is anomalous and should be
visible), and worth knowing before a canary night is scheduled.

## Side effects

- Checks out and pulls `~/agent-worktrees/inbox` on `agents/inbox` (`agent_propose.sh:264`).
- Commits the proposal and pushes it to the box-safe repo's `agents/inbox` branch.
- Appends this attempt's output to `~/agent-workforce/logs/agent_run.log`, keeps the attempt
  itself at `logs/last-attempt/standing-research.log` (truncated per attempt, kept after the
  run so `ExecStartPost` can read it), and a record to `cost.log`.
- Writes one episodic line to `~/.hermes/profiles/claudius/memories/MEMORY.md` — the store
  exists, so this job records `memory=fallback`, not `no-store` (measured 2026-09-10 04:46).
- Touches `/home/dave/logs/run-markers/agent-proposal.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`, the fleet-wide propose lock.
- Delivery receipt appended by `bin/deliver.sh` to `~/logs/delivery-receipts.jsonl`.

Nothing else. `agent_propose.sh:404` discards the whole run when anything outside
`_inbox/agents/` changed, recording `outcome=VIOLATION`; the task never writes `~/vault` on
any branch, and never acts outward.

## Acceptance checks

Ids are the stable names; `## Known failure modes` references them, never the numbers.

1. **The artifact is this run's**, not yesterday's left in place. Not applicable on a run
   that declined, which is the only other legitimate outcome.

   ```check id=artifact-is-this-run
   f="$AGENT_INBOX_DIR/${RUN_DATE}_standing-research.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no artifact and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_standing-research.md" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above — an artifact
   makes this one n/a, its absence makes that one n/a — so exactly one decides and a run
   producing neither fails both rather than passing both.

   ```check id=decline-is-this-runs-own
   f="$AGENT_INBOX_DIR/${RUN_DATE}_standing-research.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **Every mandated section is present.** A proposal missing `## Contradictions` is not a
   short proposal, it is one that skipped Mechanism A.

   ```check id=sections-are-all-present
   f="$AGENT_INBOX_DIR/${RUN_DATE}_standing-research.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   missing=""
   for h in "## Task" "## Key findings" "## Contradictions" "## Proposed vault change" "## Confidence & gaps"; do
     grep -qF "$h" "$f" || missing="$missing [$h]"
   done
   [ -z "$missing" ] || echo "missing sections:$missing"
   [ -z "$missing" ]
   ```

4. **The contradictions section was answered, not left blank.** Presence of the heading is
   what check 3 decides; this one decides that something was written under it. `none found
   this run` passes — a silent supersede is the failure Mechanism A exists to stop, and a
   blank section is indistinguishable from one.

   ```check id=contradictions-answered
   f="$AGENT_INBOX_DIR/${RUN_DATE}_standing-research.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   body="$(sed -n '/^## Contradictions/,/^## /{/^## /d; p}' "$f" | tr -d '[:space:]')"
   [ -n "$body" ] || echo "the Contradictions section is blank — Mechanism A wants 'none found this run' at minimum"
   [ -n "$body" ]
   ```

5. **Claims carry the FACT/INFERENCE labels.** The profile makes the split mandatory because
   an unlabelled research proposal reads as evidence when half of it is reasoning.

   ```check id=claims-are-labelled
   f="$AGENT_INBOX_DIR/${RUN_DATE}_standing-research.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -c 'FACT:' "$f")"
   [ "$n" -ge 1 ] || echo "no FACT: label anywhere — every claim is unlabelled"
   [ "$n" -ge 1 ]
   ```

6. **A published-corpus collision was obeyed.** The gate outranks the brief's own wording
   (profile step 2b), so the failure this catches is the one where the tool said COLLISION
   and the duplicate was drafted anyway. It reads the gate's own output, not a claim in the
   proposal that the gate was run.

   ```check id=corpus-collision-was-obeyed
   f="$AGENT_INBOX_DIR/${RUN_DATE}_standing-research.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   [ -n "$(grep -F 'COLLISION' "$AGENT_ATTEMPT_LOG")" ] \
     || { echo "n/a: the corpus gate reported no collision this run"; exit 77; }
   [ -n "$(grep -Fi 'collision' "$f")" ] \
     || echo "published_corpus.py reported a COLLISION and the proposal never names it — the duplicate was drafted over a faulty brief"
   [ -n "$(grep -Fi 'collision' "$f")" ]
   ```

7. **The mirror this run read was not dirty.** This job runs no `vault_sync_guard.sh`
   pre-flight, so nothing else on the path would have refused; a red here is the finding,
   not a flake. `$VAULT` is already resolved by the executor — `~/vault` is a symlink and a
   check that records the link rather than its target does not survive cutover.

   ```check id=mirror-was-not-dirty
   [ -d "$VAULT/.git" ] || { echo "n/a: $VAULT is not a git checkout"; exit 77; }
   dirty="$(git -C "$VAULT" status --porcelain)"
   [ -z "$dirty" ] || echo "the mirror carries uncommitted changes and this job has no vault_sync_guard pre-flight: $dirty"
   [ -z "$dirty" ]
   ```

8. **The write boundary held**: the commit that added this run's file touched nothing
   outside `_inbox/agents/`. Resolved by path rather than `HEAD~1` — the inbox worktree
   takes commits from every job, so the previous commit is routinely somebody else's.

   ```check id=write-boundary-held
   rel="_inbox/agents/${RUN_DATE}_standing-research.md"
   [ -f "$INBOX_WORKTREE/$rel" ] || { echo "n/a: no artifact this run"; exit 77; }
   c="$(git -C "$INBOX_WORKTREE" log -1 --format=%H -- "$rel")"
   [ -n "$c" ] || exit 1
   [ -z "$(git -C "$INBOX_WORKTREE" show --name-only --pretty=format: "$c" \
             | grep -Ev '^(_inbox/agents/|$)')" ]
   ```

9. **The run was not silently skipped by the global lock.** `sweep`, because the failure is
   that nothing ran. It reads the unit's journal since the timer's last trigger: `SKIP:
   previous run still active` goes through `log()` (`bin/agent_propose.sh:144`), which tees
   to a shared file naming no job. journald scopes by unit; the shared file does not.

   ```check id=not-lock-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

10. **The timer fired inside its weekday window.** `sweep`, asserted against systemd rather
    than against a report that says it ran. 4 days covers the 72h weekend plus jitter; a
    never-fired timer reports a `LastTriggerUSec` that is not an epoch and fails rather than
    reading as 1970.

    ```check id=timer-fired-this-window when=sweep
    t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
    case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
    age=$(( $(date +%s) - ${t#@} ))
    [ "$age" -lt 345600 ] || echo "$UNIT.timer last fired ${age}s ago, past the 72h weekend gap plus jitter"
    [ "$age" -lt 345600 ]
    ```

`not-lock-skipped`, `timer-fired-this-window` and `mirror-was-not-dirty` catch the failures
this box actually produces; the rest catch a bad proposal. D3 needs both.

## Known failure modes

- **Provider death reading as a clean no-op.** The ancestor failure and the reason this job
  exists in its current form: an OpenRouter 402 killed the hermes/claudius path for ten days
  while `agent_propose.sh` logged *"OK: run completed, agent produced no proposal"*, because
  the error went to the hermes profile's own `errors.log` and never reached the attempt's
  stdout. Closed by `AGENT_VERIFY_CMD` — a run producing neither artifact nor sentinel fails.
  Signals: `artifact-is-this-run` / `decline-is-this-runs-own`.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure: the agent launches with no mission. `run_standing_research_cc.sh:33`
  guards it, and unlike m1 that guard is all this job needed — the `DECLINE:` sentinel and
  `AGENT_VERIFY_CMD` were already wired, so an empty-prompt run fails loudly rather than
  logging NOPROPOSAL. The guard buys the named path in the journal, not the alert.
- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging the SKIP. No alert, no
  artifact, and `OnFailure` never fires because nothing failed. 04:30 shares the fleet lock
  with 03:00 raw-ingest and 05:30 m1; a raw-ingest run overrunning 90 minutes swallows this
  one. Signal: `not-lock-skipped`.
- **Stale or dirty mirror, unguarded.** The gap this contract records rather than closes:
  every sibling that writes outward-facing text runs `vault_sync_guard.sh check` first and
  this one does not. Signal: `mirror-was-not-dirty`. Closing it is a change to the runner,
  not to this file.
- **A queue that stopped being regenerated.** `queue.md` comes from Dave's Mac-side EOD wrap.
  A stale queue does not fail anything — the run silently falls through to standing missions
  and keeps producing plausible proposals about the wrong week. Nothing on the box detects
  it today.
- **Corpus gate overruled by the brief.** The gate is a local git read of the site's
  `blog.ts`, so it is cheap and always available; the failure mode is the model treating the
  brief's title as authoritative after `check` returned 2. Signal:
  `corpus-collision-was-obeyed`.
- **Unit/slug mismatch.** `agent-proposal.service` produces `*_standing-research.md`. A check
  or a query that derives the artifact name from the unit finds nothing and reads it as a
  missing artifact. Everything in this file hardcodes the slug for that reason.
- **Midnight rollover.** `RUN_DATE` and `AGENT_RUN_STARTED_AT` are exported once
  (`agent_propose.sh:317`, `:34`) and read, never recomputed, so a run spanning midnight
  cannot disagree with itself about which file it was supposed to write. 04:30 is nowhere
  near midnight; this holds anyway because the profile takes the date from `RUN_DATE` with a
  `date` fallback rather than computing it independently.
