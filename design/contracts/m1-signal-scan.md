# Contract: m1-signal-scan

T4.2, 2026-09-10. Read for this contract: `systemctl cat m1-signal-scan.{service,timer}`,
`bin/run_m1_signal_scan_cc.sh`, `profiles/m1_signal_scan_cc_task.md`,
`profiles/m1_signal_scan.env.example`, `bin/agent_propose.sh`, `bin/proposal_or_decline.sh`,
`bin/deliver_proposal.sh`, `bin/deliver.sh` and `bin/buzz_routes.env`. The artifact's shape is
taken from the profile's mandated format, **not** from a live proposal:
`~/agent-worktrees/inbox/` is deny-listed for this session (`~/CLAUDE.md` § Out of scope), so
no run's output was read.

## Identity

| | |
|---|---|
| Unit | `m1-signal-scan.service` / `.timer` |
| Owner | **claudius** (`design/agents/claudius.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-sonnet-5`, box subscription (`bin/run_m1_signal_scan_cc.sh:33`) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Mon,Wed 05:30`, `RandomizedDelaySec=5min`, `Persistent=true`. Recurring; no
expiry. **Twice weekly, not daily** — registry §2 recorded it as daily off a next-elapse
value, and the difference matters here more than anywhere else in the fleet: the profile
carries a same-day idempotency check and deliberately **no weekly-skip guard**, because the
timer owns cadence. A weekly guard reintroduced into the profile would silently eat every
Wednesday run and leave Monday's artifact in place looking current.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| the open web, via `WebSearch` / `WebFetch` | live | **proceed-and-flag**: fewer than three second-order signals is a decline, not a thin artifact |
| `04_operations/` context and the M1 thesis on the mirror | the mirror's own state | **unguarded on this job** — `bin/run_m1_signal_scan_cc.sh` runs no `vault_sync_guard.sh check`, unlike `run_raw_ingest_cc.sh:26` and `run_bd_followup_drafts_cc.sh:26`. It proceeds silently, and `mirror-was-not-dirty` stands in for the missing pre-flight |
| `_inbox/agents/<today>_m1-signal-scan.md` | today's date | **skip**: the profile prints `skip: today's scan already exists` and writes nothing. This is a *same-day* skip and nothing else |
| `profiles/m1_signal_scan_cc_task.md` (deployed copy) | must be readable | wrapper exits 1 with the path named — `-r`, not `-f`: an unreadable file feeds `cat(1)` the identical empty prompt |
| `skills/claudius/.claude-plugin/plugin.json` (deployed) | must be readable | wrapper exits 1; a `--plugin-dir` that does not exist is silent — exit 0, no diagnostic, no skills |
| `~/agent-worktrees/inbox` worktree | checked out and pulled by `agent_propose.sh:264` | `ConditionPathExists` on the unit; the run never starts |

This is one of two jobs in the fleet with web tools in its allowlist (the other is
standing-research). De-identification therefore applies to what it *sends*: queries and
fetched URLs leave the bubble, so client names do not go into them
(`docs/data_boundary.md`).

## Outputs

- **Artifact:** exactly one file, `_inbox/agents/<YYYY-MM-DD>_m1-signal-scan.md`.
- **Mandated sections**, in order: `## Task`, `## Key findings (fact vs inference labeled)`,
  `## Implications for Vantage Point` carrying `target: vault`, `## Proposed vault change
  (target canonical file + exact content)`, `## Confidence & gaps`.
- **At least three second-order signals**, each carrying a `FACT:` with a source URL, a
  `so what for VP` line, and a `content-angle`. Second-order is the whole point: the
  first-order news is already in Dave's feed, and a scan that reports it is a press review.
- **Delivery:** `ExecStartPost=bin/deliver_proposal.sh`, `DELIVERY_ROUTE=signals` → channel
  `a8e99852-…`, **event kind 9 — a chat channel, not a forum.** The three sibling research
  routes are 45001. A 45001 post into this channel is receipted `ok` and shown to nobody,
  which is why `delivery-was-receipted` asserts the kind rather than the outcome alone.

- **Beneficiary:** Dave, on the signals channel — and the content board indirectly, since
  every signal carries a `content-angle`.
- **Next actor:** Dave.
- **Next action:** promote the `## Proposed vault change`, or take a `content-angle` onto the
  content board by hand. Nothing routes an angle there automatically.
- **Benefit hypothesis:** second-order signals reach Dave before they are common knowledge.
  The first-order news is already in his feed, and a scan that reports it is a press review.
- **Benefit signal:** `Unknown`. Whether an angle became a post is visible only on the content
  board, and nothing joins the two ends.

## Decline conditions

One legitimate decline: **fewer than three genuine second-order signals this run.** The run
prints, as its own line:

```
DECLINE: <short reason>
```

and writes no file. `bin/proposal_or_decline.sh m1-signal-scan` matches `^DECLINE:` in **this
run's own output** (`$AGENT_ATTEMPT_LOG`, the per-task file `agent_propose.sh:192` keeps) and
exits 0. Not the shared `agent_run.log`: until T7.1 (2026-09-10) any job's decline satisfied
every other job's check.

Declining is the correct answer to a quiet week. Three thin signals padded to meet the floor
is the failure the floor was meant to prevent, and no check here can tell padding from
substance — that is Dave's read.

The same-day skip is **not** a decline: it prints `skip: …` and no artifact, so
`proposal_or_decline.sh` fails the run. A second run in one day is anomalous and should be
visible.

## Side effects

- Checks out and pulls `~/agent-worktrees/inbox` on `agents/inbox` (`agent_propose.sh:264`).
- Commits the proposal and pushes it to the box-safe repo's `agents/inbox` branch.
- Appends this attempt's output to `~/agent-workforce/logs/agent_run.log`, keeps the attempt
  itself at `logs/last-attempt/m1-signal-scan.log`, and a record to `cost.log`.
- Writes one episodic line to `~/.hermes/profiles/claudius/memories/MEMORY.md` — the store
  exists, so this job records `memory=fallback`, not `no-store`.
- Touches `/home/dave/logs/run-markers/m1-signal-scan.service`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`, the fleet-wide propose lock.
- **Egress**: web queries and page fetches, the only outbound traffic in this contract.
  Reading is not outward *action* — no message reaches a human from this box.
- Delivery receipt appended by `bin/deliver.sh` to `~/logs/delivery-receipts.jsonl`.

Nothing else. `agent_propose.sh:404` discards the whole run when anything outside
`_inbox/agents/` changed, recording `outcome=VIOLATION`.

## Acceptance checks

Ids are the stable names; `## Known failure modes` references them, never the numbers.

1. **The artifact is this run's**, not Monday's left in place — the failure this job is most
   exposed to, running twice a week into a fixed filename.

   ```check id=artifact-is-this-run
   f="$AGENT_INBOX_DIR/${RUN_DATE}_m1-signal-scan.md"
   if [ ! -f "$f" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG" 2>/dev/null; then
     echo "n/a: no artifact and a declared decline"
     exit 77
   fi
   [ -n "$(find "$AGENT_INBOX_DIR" -maxdepth 1 -name "${RUN_DATE}_m1-signal-scan.md" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Or the decline is this run's own.** Polarised against the check above, so exactly one
   decides and a run producing neither fails both.

   ```check id=decline-is-this-runs-own
   f="$AGENT_INBOX_DIR/${RUN_DATE}_m1-signal-scan.md"
   [ -f "$f" ] && { echo "n/a: the run produced an artifact"; exit 77; }
   fresh="$(find "$(dirname "$AGENT_ATTEMPT_LOG")" -maxdepth 1 \
              -name "$(basename "$AGENT_ATTEMPT_LOG")" \
              -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)"
   [ -n "$fresh" ] && grep -qE '^DECLINE:' "$AGENT_ATTEMPT_LOG"
   ```

3. **Three signals, or a decline.** The floor is what separates a scan from a press review;
   an artifact carrying two is neither.

   ```check id=three-signals-or-decline
   f="$AGENT_INBOX_DIR/${RUN_DATE}_m1-signal-scan.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -ci 'so what for VP' "$f")"
   [ "$n" -ge 3 ] || echo "$n signal(s) carry a 'so what for VP' line; the floor is 3 and below it the run should have declined"
   [ "$n" -ge 3 ]
   ```

4. **Every signal cites a public URL.** A second-order read with no source is an assertion,
   and this is the one job in the fleet whose evidence is off-box and unrecoverable later.

   ```check id=each-signal-cites-a-public-url
   f="$AGENT_INBOX_DIR/${RUN_DATE}_m1-signal-scan.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -ci 'so what for VP' "$f")"
   [ "$n" -ge 1 ] || { echo "n/a: no signals to check"; exit 77; }
   u="$(grep -coE 'https?://' "$f")"
   [ "$u" -ge "$n" ] || echo "$n signal(s) but only $u line(s) carrying a URL"
   [ "$u" -ge "$n" ]
   ```

5. **Every signal names a content angle.** The scan feeds augustus's pipeline; a signal with
   no angle is read and dropped.

   ```check id=each-signal-names-a-content-angle
   f="$AGENT_INBOX_DIR/${RUN_DATE}_m1-signal-scan.md"
   [ -f "$f" ] || { echo "n/a: no artifact this run"; exit 77; }
   n="$(grep -ci 'so what for VP' "$f")"
   [ "$n" -ge 1 ] || { echo "n/a: no signals to check"; exit 77; }
   a="$(grep -ci 'content-angle' "$f")"
   [ "$a" -ge "$n" ] || echo "$n signal(s) but only $a content-angle line(s)"
   [ "$a" -ge "$n" ]
   ```

6. **A skip was a same-day skip.** The profile's idempotency check is scoped to today and
   nothing else. A weekly guard reintroduced here would print the same `skip:` line every
   Wednesday, leave Monday's artifact in place, and pass every other check in this file — so
   this one demands today's own artifact behind the skip.

   ```check id=skip-was-a-same-day-skip
   grep -qiE '^[[:space:]]*skip:' "$AGENT_ATTEMPT_LOG" 2>/dev/null \
     || { echo "n/a: the run did not skip"; exit 77; }
   f="$AGENT_INBOX_DIR/${RUN_DATE}_m1-signal-scan.md"
   [ -f "$f" ] || echo "the run skipped with no artifact dated today — this is a weekly skip wearing a same-day skip's message"
   [ -f "$f" ]
   ```

7. **The mirror this run read was not dirty.** This job runs no `vault_sync_guard.sh`
   pre-flight, so nothing else on the path would have refused. `$VAULT` is already resolved
   by the executor — `~/vault` is a symlink and a check that records the link rather than its
   target does not survive cutover.

   ```check id=mirror-was-not-dirty
   [ -d "$VAULT/.git" ] || { echo "n/a: $VAULT is not a git checkout"; exit 77; }
   dirty="$(git -C "$VAULT" status --porcelain)"
   [ -z "$dirty" ] || echo "the mirror carries uncommitted changes and this job has no vault_sync_guard pre-flight: $dirty"
   [ -z "$dirty" ]
   ```

8. **The delivery went out as kind 9.** `sweep`. The signals route is a chat channel; the
   three sibling research routes are 45001 forums, so a copied route block or a changed
   default publishes into this channel as a forum post — receipted `ok`, visible to nobody,
   and indistinguishable from a healthy night in every log this box keeps.

   ```check id=delivery-was-receipted when=sweep
   r="$HOME/logs/delivery-receipts.jsonl"
   [ -f "$r" ] || { echo "n/a: no delivery receipts on this box"; exit 77; }
   line="$(grep -F m1-signal-scan "$r" | tail -1)"
   [ -n "$line" ] || { echo "n/a: this job has never delivered"; exit 77; }
   ok=1
   case "$line" in *'"kind": 9'*|*'"kind":9'*) ;; *) ok=0 ;; esac
   [ "$ok" = 1 ] || echo "the last m1-signal-scan receipt is not kind 9 — the signals channel is chat, and a 45001 post there is shown to nobody: $line"
   [ "$ok" = 1 ]
   ```

9. **The write boundary held**: the commit that added this run's file touched nothing outside
   `_inbox/agents/`. Resolved by path rather than `HEAD~1`, because the inbox worktree takes
   commits from every job.

   ```check id=write-boundary-held
   rel="_inbox/agents/${RUN_DATE}_m1-signal-scan.md"
   [ -f "$INBOX_WORKTREE/$rel" ] || { echo "n/a: no artifact this run"; exit 77; }
   c="$(git -C "$INBOX_WORKTREE" log -1 --format=%H -- "$rel")"
   [ -n "$c" ] || exit 1
   [ -z "$(git -C "$INBOX_WORKTREE" show --name-only --pretty=format: "$c" \
             | grep -Ev '^(_inbox/agents/|$)')" ]
   ```

10. **The run was not silently skipped by the global lock.** `sweep`, because the failure is
    that nothing ran. 05:30 sits between the 04:30 standing-research slot and the 06:00 daily
    plan, sharing one flock with both. journald scopes by unit; the shared `agent_run.log`
    the SKIP also lands in names no job.

    ```check id=not-lock-skipped when=sweep
    t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
    case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
    [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
              | grep -F 'SKIP: previous run still active')" ]
    ```

11. **The timer fired inside its window.** `sweep`, asserted against systemd rather than
    against a report that says it ran. 6 days covers the Wed→Mon gap plus jitter; the
    twice-weekly cadence is exactly why a stopped timer here goes unnoticed for a fortnight.

    ```check id=timer-fired-this-window when=sweep
    t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
    case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
    age=$(( $(date +%s) - ${t#@} ))
    [ "$age" -lt 518400 ] || echo "$UNIT.timer last fired ${age}s ago, past the Wed-to-Mon gap plus jitter"
    [ "$age" -lt 518400 ]
    ```

## Known failure modes

- **A reintroduced weekly guard.** The profile deliberately carries a same-day check and no
  weekly one, because the timer owns cadence and the timer is twice weekly. A weekly guard
  added back — by someone reading "M1 signal scan" as a weekly report, which it once was —
  makes every Wednesday print `skip:` and exit clean, with Monday's artifact still on disk
  looking current. Nothing alerts. Signal: `skip-was-a-same-day-skip`.
- **Kind mismatch on the signals route.** `signals` is kind 9; `research`, `bd` and `content`
  are 45001. `bin/deliver.sh` receipts a wrong-kind post as delivered because the relay
  accepts it. The scan is then written, delivered, receipted — and read by nobody. Signal:
  `delivery-was-receipted`.
- **First-order news dressed as a signal.** The scan's whole value is the second-order read,
  and no check in this file can tell one from the other. `three-signals-or-decline` asserts
  the floor was met, not that the floor was met honestly. That judgement is Dave's, on the
  proposal.
- **Provider death reading as a clean no-op.** The ancestor failure: an OpenRouter 402 killed
  the hermes/claudius path for ten days while `agent_propose.sh` logged *"OK: run completed,
  agent produced no proposal"*. Closed by `AGENT_VERIFY_CMD`. Signals: `artifact-is-this-run`
  / `decline-is-this-runs-own`.
- **Empty prompt.** `$(cat "$TASK_FILE")` sits in an argument, where `set -e` does not
  propagate cat(1)'s failure. Guarded in the wrapper so the journal names the path rather
  than reporting a mission-less run as a decline-less FAIL.
- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging the SKIP. No alert, no
  artifact, and `OnFailure` never fires because nothing failed. This job's 05:30 slot is the
  most collision-prone in the fleet — 04:30 standing research runs Mon-Fri on Opus with web
  tools, and an overrun of 55 minutes swallows it. Signal: `not-lock-skipped`.
- **Stale or dirty mirror, unguarded.** The gap this contract records rather than closes: two
  of five Claudius jobs run `vault_sync_guard.sh check` and this is not one of them, so the
  VP implications can be reasoned off a mirror the Mac replaced days ago. Signal:
  `mirror-was-not-dirty`. Closing it is a change to the runner, not to this file.
- **Egress on the wrong string.** This job and standing-research are the only two carrying
  `WebSearch`/`WebFetch`. A query built from a client name leaves the bubble; the boundary is
  in `docs/data_boundary.md` and nothing on this box enforces it mechanically.
