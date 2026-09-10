# Contract: knowledge-digest

Worked example for `design/contract-schema.md`. Everything below was read on 2026-09-01
from `systemctl cat knowledge-digest.service`, `bin/run_knowledge_digest_cc.sh`,
`profiles/knowledge_digest_cc_task.md` and `bin/proposal_or_decline.sh`.

## Identity

| | |
|---|---|
| Unit | `knowledge-digest.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-opus-5`, box subscription |
| Contract version | 1 (2026-09-01) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Sun 09:00`, `RandomizedDelaySec=5min`. Recurring; no expiry.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `~/vault` mirror (`05_knowledge/`, `11_entities/`) | must be clean and current — the digest is a 7-day git-log delta over it | **refuse**: `bin/vault_sync_guard.sh check` runs before the model starts and exits 1 with a loud message. A digest off a frozen mirror is a confident wrong answer |
| `~/vault/04_operations/open_loops.md` | same mirror, same guard | covered by the guard above |
| `~/agent-worktrees/inbox` worktree | checked out fresh by `agent_propose.sh` before the run | runner fails before the model starts |
| `profiles/knowledge_digest_cc_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named |
| existing `_inbox/agents/<today>_knowledge-digest.md` | today's date | **skip**: STEP 0 idempotency — prints `skip: today's knowledge-digest already exists` and writes nothing |

The 7-day window is computed with `git log --since='7 days ago'`, explicitly **not** file
mtimes, which are unreliable across a re-clone or resync.

## Outputs

- **Artifact:** exactly one file, `_inbox/agents/<YYYY-MM-DD>_knowledge-digest.md`, in the
  inbox worktree. Body **under 500 words** — it is a pointer digest, not a re-summary.
- **Header must state** that this is the *knowledge* digest (git-log delta over
  `05_knowledge/` + `11_entities/`) and does **not** replace `weekly-pre-assembly`, which
  is the *activity* pre-read. Two adjacent weekly reports that do not say how they differ
  is how one gets read as the other.
- **Delivery:** `ExecStartPost=bin/deliver_proposal.sh`, `DELIVERY_ROUTE=research` →
  channel `6ea596af-…`, **event kind 45001** (forum), notify `claudius`. A kind-9 post
  into that channel is receipted `ok` and shown to nobody.
- Downstream: the proposal syncs to the Notion Agent Inbox and is Mac-gated for approval.

- **Beneficiary:** Dave, weekly; claudius is the notified reader on the route.
- **Next actor:** Dave, from the Mac.
- **Next action:** read the digest and decide whether anything it points at needs promoting.
  The proposal syncs to the Notion Agent Inbox and is Mac-gated for approval.
- **Benefit hypothesis:** a week's growth in `05_knowledge/` and `11_entities/` is visible
  without reading the git log, so knowledge that landed is knowledge known to exist.
- **Benefit signal:** `Unknown`. This is a pointer digest, so a promotion is the wrong measure
  — the question is whether the pointers were followed, and nothing records that.

## Decline conditions

Exactly one legitimate decline: **no `05_knowledge/` or `11_entities/` paths changed in
the window.** The run then prints, verbatim and as its own line:

```
DECLINE: no 05_knowledge/ or 11_entities/ changes in the last 7 days
```

and writes no file. `bin/proposal_or_decline.sh knowledge-digest` matches `^DECLINE:` in
**this run's own output** — `$AGENT_ATTEMPT_LOG`, the per-task file agent_propose.sh keeps
for the attempt — and exits 0. It is deliberately not the shared `agent_run.log`: that
stream carries every job with no run boundary in it, so until T7.1 (2026-09-10) any job's
decline satisfied every other job's check. There is no tail window left to tune, because
the file holds one attempt of one job.

The idempotency skip in STEP 0 is **not** a decline — it prints `skip: …` and no artifact,
so `proposal_or_decline.sh` fails the run. That is the intent (a second run in one day is
anomalous and should be visible) and, since T7.1, it is also what happens: before the fix
the skip passed by borrowing whichever sibling had declined most recently. It means a
manual re-run on a Sunday now genuinely reads as a failure, and a canary-then-schedule
night costs one red run. Recorded so it is a known behaviour rather than a surprise;
whether that is the alerting Dave wants is a policy question, not a defect.

## Side effects

- Checks out / resets `~/agent-worktrees/inbox`.
- Commits the proposal and pushes to the box-safe repo's `agents/inbox` branch.
- Writes a run record to `~/agent-workforce/logs/agent_run.log`, this attempt's own output
  to `~/agent-workforce/logs/last-attempt/knowledge-digest.log` (truncated per attempt,
  kept after the run so `ExecStartPost` can read it), and a cost line to `cost.log`; writes `memory=no-store` because `AGENT_PROFILE` is `claude-opus`, a model
  name with no `~/.hermes/profiles/` store (registry §6.6).
- Touches `/home/dave/logs/run-markers/knowledge-digest.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`.
- Delivery receipt appended by `bin/deliver.sh`.

Nothing else. The runner discards any run that writes outside `_inbox/agents/`, and the
task never writes `~/vault` directly on any branch.

## Acceptance checks

Converted to the executable syntax on 2026-09-10 (T4.0). Three of the nine were wrong as
prose, and writing the command is what showed it — each says so under its own item. Ids are
the stable names; `## Known failure modes` below references them, never the numbers.

1. **The artifact is this run's**, not last week's left in place. Not applicable on a run
   that declined, which is the only other legitimate outcome.

   ```check id=artifact-is-this-run
   f="$AGENT_INBOX_DIR/${RUN_DATE}_knowledge-digest.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no artifact and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_knowledge-digest.md" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** The two branches are polarised against each other —
   an artifact makes this one n/a, its absence makes the one above n/a — so exactly one of
   them decides, and a run producing neither fails both rather than passing both. The
   sentinel is read from `$AGENT_ATTEMPT_LOG` and its freshness asserted, because until T7.1
   a sibling job's decline in the shared `agent_run.log` satisfied this check.

   ```check id=decline-is-this-runs-own
   f="$AGENT_INBOX_DIR/${RUN_DATE}_knowledge-digest.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **The body is under 500 words.** "Body" had to be made exact before it could be decided:
   the 2026-09-09 digest is **508 words whole and 499 from line 2**, so the obvious
   `wc -w < file` would have shipped a red on a run that complied. The H1 title line is not
   body.

   ```check id=body-under-500-words
   f="$AGENT_INBOX_DIR/${RUN_DATE}_knowledge-digest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   [ "$(tail -n +2 "$f" | wc -w)" -lt 500 ]
   ```

4. **The header carries the `weekly-pre-assembly` disclaimer.** In the header, not anywhere
   in the file — a mention buried in the body does not stop the two reports being read as
   each other.

   ```check id=names-weekly-pre-assembly
   f="$AGENT_INBOX_DIR/${RUN_DATE}_knowledge-digest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   [ -n "$(head -12 "$f" | grep -F 'weekly-pre-assembly')" ]
   ```

5. **The write boundary held**: the commit that added this run's file touched nothing outside
   `_inbox/agents/`. It resolves that commit by path rather than taking `HEAD~1`, which was
   the prose version and is wrong here: the inbox worktree takes commits from every job, and
   on 2026-09-10 its three most recent were all scorecard commits, none of them a digest.

   ```check id=write-boundary-held
   rel="_inbox/agents/${RUN_DATE}_knowledge-digest.md"
   [ -f "$INBOX_WORKTREE/$rel" ] || { echo "n/a: no artifact this run"; exit 77; }
   c="$(git -C "$INBOX_WORKTREE" log -1 --format=%H -- "$rel")"
   [ -n "$c" ] || exit 1
   [ -z "$(git -C "$INBOX_WORKTREE" show --name-only --pretty=format: "$c" \
             | grep -Ev '^(_inbox/agents/|$)')" ]
   ```

6. **Every vault note the digest cites resolves**, or is named under *Confidence & gaps* as
   renamed or removed inside the window. The digest cites `[[wikilinks]]`, not backticked
   paths.

   ```check id=cited-paths-resolve
   f="$AGENT_INBOX_DIR/${RUN_DATE}_knowledge-digest.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   gaps="$(sed -n '/^## Confidence & gaps/,$p' "$f")"
   missing=""
   for link in $(grep -o '\[\[[^]|]*' "$f" | sed 's/^\[\[//' | sort -u); do
     [ -f "$VAULT/$link.md" ] && continue
     case "$gaps" in *"$link"*) continue ;; esac
     missing="$missing $link"
   done
   [ -z "$missing" ] || echo "unresolved:$missing"
   [ -z "$missing" ]
   ```

7. **The run was not silently skipped by the global lock.** `sweep`, because the failure is
   that nothing ran. It reads the **unit's journal** since the timer's last trigger, not "the
   run log": `SKIP: previous run still active` is written through `log()`
   (`bin/agent_propose.sh:144`), which tees to the shared `logs/agent_propose.log` naming no
   job — `2026-09-04T01:34:49+02:00 SKIP: previous run still active` and nothing else on the
   line. That is T7.1's defect one layer over. journald scopes by unit; the shared file does
   not.

   ```check id=not-lock-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

8. **The timer actually fired this week.** `sweep`, and asserted against systemd rather than
   against a report that says it ran. A never-fired timer reports a `LastTriggerUSec` that is
   not an epoch, and fails rather than reading as 1970.

   ```check id=timer-fired-this-week when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ "$(( $(date +%s) - ${t#@} ))" -lt 691200 ]
   ```

9. **The vault guard ran and passed.** The `OK:` line must be **present**, not merely the
   refusal absent — `bin/vault_sync_guard.sh check` prints `OK:` on every success path
   (`:129`, `:137`), so its absence means the guard never ran, which is the same silence a
   dead run produces.

   ```check id=vault-guard-passed
   [ -n "$(grep -F 'vault_sync_guard[check]: OK:' "$AGENT_ATTEMPT_LOG")" ] &&
   [ -z "$(grep -F 'REFUSING to run' "$AGENT_ATTEMPT_LOG")" ]
   ```

`not-lock-skipped`, `timer-fired-this-week` and `vault-guard-passed` catch the failures this
box actually produces; the first six catch a bad digest. D3 needs both.

## Known failure modes

- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging `SKIP: previous run
  still active`. No alert, no artifact, and `OnFailure` never fires because nothing
  failed. Signal: `not-lock-skipped`.
- **Stale mirror.** Guarded — this is the one already closed by
  `bin/vault_sync_guard.sh check`, and the reason the guard exists.
- **Provider death reading as a clean no-op.** The ancestor failure: an OpenRouter 402
  killed the hermes/claudius path for ten days while logging *"OK: run completed, agent
  produced no proposal"*, because the error went to the profile's own `errors.log` and
  never reached the attempt's stdout. `proposal_or_decline.sh` was written for exactly
  this and closes it — a run that produces neither artifact nor sentinel now fails.
- **Confusion with `weekly-pre-assembly`.** Both are weekly, both land in the research
  route, both are pre-reads. Mitigated by the mandatory header line;
  `names-weekly-pre-assembly`.
- **Kind mismatch on delivery.** The research route is a forum (45001). A producer
  publishing kind 9 there is receipted `ok` and invisible. Not currently possible for this
  job — `deliver.sh` reads the kind from the route table — but it is the failure this
  route has already produced once, from a different producer.
- **Midnight rollover.** `RUN_DATE` and `AGENT_RUN_STARTED_AT` are exported once by
  `agent_propose.sh` and read, never recomputed, so a run spanning midnight cannot
  disagree with itself about which file it was supposed to write.
