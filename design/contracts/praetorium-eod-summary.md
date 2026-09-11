# Contract: praetorium-eod-summary

Read on 2026-09-10 from `systemd/praetorium-eod-summary.{service,timer}`,
`bin/run_eod_summary_cc.sh`, `bin/run_daily_rhythm_cc.sh`, `profiles/eod_summary_task.md`,
`bin/notion_daily.py`, `bin/deliver.sh`, `profiles/eod_summary.env.example` and the artifacts
under `~/logs/eod-summary/`. `bin/check_deploy_drift.sh` reported `drift: clean` the same day,
so the deployed copies are the same bytes.

`~/.config/agent-workforce/eod_summary.env` is deny-listed and was **not** read; the wiring
claims below come from the committed `.env.example` it mirrors.

## Identity

| | |
|---|---|
| Unit | `praetorium-eod-summary.service` / `.timer` |
| Owner | **marcus** (`design/agents/marcus.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-sonnet-5`, box subscription, marcus's pointer-skill tree (T3.1) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` |

## Trigger

`OnCalendar=*-*-* 22:15`, `RandomizedDelaySec=5min`, `Persistent=true`. Daily, including
weekends — unlike its morning sibling, because a Saturday still has a day to close even when
nobody planned it.

`bd-stall-radar` ran at 23:00 and `bd-followup-drafts` at 23:30 until 2026-09-11 (weekly Mon
09:07 and monthly 09:37 since), both under the same global `agent_propose.sh` lock. The
neighbours still sharing it are the `*:0/15` content-change-dispatch ticks, so the race is
smaller but not gone: a 15-minute job starting as late as 22:20 has margin; a slow one does
not, and the loser of that race exits 0 having done nothing (see `## Known failure modes`).

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| Notion task deltas since `${DATE}T00:00:00+02:00`, Client Pipeline, via `bin/notion_daily.py` | live at run time | **proceed and flag** — the profile's rule is "Evidence or `UNCONFIRMED`. … There is no third option". A failed query becomes an `UNCONFIRMED:` line, never a thinner day that reads as a quiet one |
| `~/vault` mirror — `07_daily/logs/`, `04_operations/`, `03_projects/active/*/status.md` | clean, within `vault_sync_guard.sh`'s lag budget | **refuse**: gated at `bin/run_daily_rhythm_cc.sh:36`, exits 1 with `REFUSING to run`. A day closed off a frozen mirror is confidently wrong, which is worse than a missing summary — the 2026-07-23 → 07-27 freeze is the precedent |
| This box's own evidence — `git log --since` across `~/dev/*`, `_inbox/agents/` proposals written today, `~/agent-workforce/logs/agent_run.log`, `cost.log` | today's | proceed; absence is itself the finding. "A day that Dave spent entirely off-box looks, from here, like a day with no evidence — and the correct output then is an honest thin summary, not a plausible one" |
| `profiles/eod_summary_task.md` (deployed copy) | readable | wrapper exits 1 naming the path (`run_daily_rhythm_cc.sh:31`) |
| `~/agent-workforce/skills/marcus/.claude-plugin/plugin.json` | readable | wrapper exits 1 naming the path. A missing `--plugin-dir` is otherwise silent — exit 0, no diagnostic, no skills (T3.1) |

## Outputs

**Two Notion rows, in two different data sources, from one helper call** — this is the
structural difference from `praetorium-daily-plan` and the thing most worth asserting:

- `<YYYY-MM-DD> — EOD Summary` in **Daily Plans** (`3288d768-1ede-8190-ad5a-000b9710833e`),
  upserted on `Plan Title`, body as blocks (`notion_daily.py:206`).
- `<YYYY-MM-DD>` in **Daily Log** (`f184eddd-2793-4560-8d04-dcfbb8b55f85`), upserted on
  `Date`, structured fields — energy, focus, tags (`notion_daily.py:212`).

Both happen inside `cmd_eod`, sequentially, and **the receipt is written only after the
second one returns** (`:213`). So a receipt that exists but carries an empty `log_page` is
the signature of a partial run: Daily Plans updated, Daily Log not. Nothing else on the box
reports that state.

- **Receipt** — `~/logs/eod-summary/receipt-<YYYY-MM-DD>.json`, carrying
  `{kind, date, title, page, action, log_page, log_action}`.
- **Body file** — `~/logs/eod-summary/eod-summary-<UTC ISO minute>Z.md`, mode 644 (the runner
  sets no `umask`).
- **Delivery** — `ExecStartPost=bin/deliver_report.sh`, `DELIVERY_ROUTE=ops` → channel
  `62f321f3-bd6a-4b31-b19b-b8b49bed30f4`, event kind 9, notify `marcus`; plus Discord.
  Anchored by `DELIVERY_RUN_MARKER=~/logs/run-markers/%n`.
- **Shape:** no markdown tables, no horizontal rules, target under 1800 characters
  (`profiles/eod_summary_task.md:162`). See `## Known failure modes` for what the target is
  worth in practice.

- **Beneficiary:** Dave that evening, through the EOD Summary row; and Dave's future self
  through the Daily Log row, which is the one artifact here with a reader more than a day out.
- **Next actor:** Dave.
- **Next action:** read the summary, correct energy, focus and tags where they are wrong, and
  leave the Daily Log row standing as the day's record. `weekly-pre-assembly` reads that
  record, not this run.
- **Benefit hypothesis:** the day is closed in writing rather than remembered, so the weekly
  pre-read has a dated record to work from instead of reconstruction.
- **Benefit signal:** `Unknown` for whether either row is read. Half of it is already
  measurable in the other direction: a receipt carrying an empty `log_page` says the Daily Log
  never landed, and that is the only consumption failure this job can see today.

## Decline conditions

**None.** The profile is explicit at `:150`: *"Never end the run by concluding 'the summary is
already live, no action needed': a run that writes nothing has failed"* — and, at `:149`,
re-running *"updates both in place — that is the designed path for a manual re-run and for the
reboot catch-up (a `Persistent=true` timer firing late always finds rows already there)"*.

A thin day is not a decline. The profile's own answer to a day with no evidence is *"an honest
thin summary, not a plausible one"* (`:11`) — output, not silence. So a `^DECLINE:` from this
job means the agent reasoned its way around a rule stated twice, and `no-decline-sentinel`
asserts its absence.

## Side effects

- Upserts two Notion pages and **replaces the Daily Plans row's children**
  (`notion_daily.py:137`). The Daily Log row is field-level, not body-replacing.
- Writes the body file and the date-keyed receipt under `~/logs/eod-summary/`.
- Touches `~/logs/run-markers/praetorium-eod-summary.service` (`ExecStartPre`).
- Appends to `~/agent-workforce/logs/agent_run.log`, `logs/last-attempt/eod-summary.log`,
  `cost.log`, and one line to `~/logs/delivery-receipts.jsonl`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`.

Nothing else. `AGENT_RUN_MODE=ops`, so no inbox worktree and no proposal commit. The profile
forbids writes anywhere but the two Notion rows (`:24`): no commits or pushes in `~/vault` or
`~/dev/*`, and specifically **never `07_daily/logs/`** — that vault write stays Mac-side.
Unlike `praetorium-daily-plan` this job runs no `git fetch`, so it has no write outside its
own paths at all.

## Acceptance checks

Nine checks. Seven `run`, two `sweep`. `both-notion-rows-landed` is the one that does not
exist in the sibling contract and is the highest-value check here.

1. **The receipt is this run's, and keyed to this run's date.** `AGENT_VERIFY_CMD` globs
   `receipt-*.json`, so a receipt written under a *different* date by a run confused about the
   day would satisfy it. The filename is `receipt-${RUN_DATE}.json` (`notion_daily.py:160`).

   ```check id=receipt-is-this-runs
   f="$HOME/logs/eod-summary/receipt-${RUN_DATE}.json"
   [ -f "$f" ] || { echo "no receipt for $RUN_DATE — the run never reached Notion"; exit 1; }
   [ -n "$(find "$HOME/logs/eod-summary" -maxdepth 1 -name "receipt-${RUN_DATE}.json" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **Both Notion rows landed, not just the first.** `cmd_eod` writes Daily Plans, then Daily
   Log, then the receipt. An empty `log_page` means the second upsert returned nothing while
   the first succeeded — the day's summary is in Notion, the structured Daily Log row is not,
   and every other signal on the box reads clean. This is the check the sibling contract has
   no equivalent of, because the sibling writes one row.

   ```check id=both-notion-rows-landed
   f="$HOME/logs/eod-summary/receipt-${RUN_DATE}.json"
   [ -f "$f" ] || { echo "n/a: no receipt this run"; exit 77; }
   grep -q '"kind": "eod-summary"' "$f" || { echo "receipt is not this job's"; exit 1; }
   grep -qE '"page": "[0-9a-f]{8}-[0-9a-f-]{27}"' "$f" || { echo "no Daily Plans row"; exit 1; }
   grep -qE '"log_page": "[0-9a-f]{8}-[0-9a-f-]{27}"' "$f" \
     || { echo "Daily Plans row landed but the Daily Log row did not"; exit 1; }
   grep -qE '"log_action": "(created|updated)"' "$f"
   ```

3. **The body file is this run's.** The receipt proves Notion accepted the upserts; it does
   not prove the file `deliver_report.sh` is about to post came from this run.

   ```check id=body-is-this-runs
   body="$(find "$HOME/logs/eod-summary" -maxdepth 1 -name 'eod-summary-*.md' \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$body" ] || { echo "no body file written by this run"; exit 1; }
   [ -s "$body" ]
   ```

4. **What was delivered is what this run wrote.** Compared by `artifact_sha256`
   (`bin/deliver.sh:158`) rather than assumed, which is what separates "the summary was
   written" from "Dave read tonight's summary" — and catches yesterday's file re-posted on a
   night the agent produced nothing.

   ```check id=delivered-this-runs-artifact
   body="$(find "$HOME/logs/eod-summary" -maxdepth 1 -name 'eod-summary-*.md' \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$body" ] || { echo "n/a: no artifact this run"; exit 77; }
   sha="$(sha256sum "$body" | cut -d' ' -f1)"
   line="$(grep -F '"job": "praetorium-eod-summary.service"' \
             "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null | tail -1)"
   [ -n "$line" ] || { echo "no delivery receipt for this unit"; exit 1; }
   case "$line" in *'"outcome": "delivered"'*) ;; *) echo "newest delivery not delivered: $line"; exit 1 ;; esac
   case "$line" in *"$sha"*) echo "delivered $sha" ;; *) echo "delivered an artifact this run did not write"; exit 1 ;; esac
   ```

5. **This run did not decline.** Asserted because `## Decline conditions` claims declining is
   impossible here, and a claim nothing tests is decoration.

   ```check id=no-decline-sentinel
   [ -f "$AGENT_ATTEMPT_LOG" ] || { echo "no attempt log for this run"; exit 1; }
   [ -z "$(grep -E '^DECLINE:' "$AGENT_ATTEMPT_LOG")" ]
   ```

6. **The vault guard ran and passed.** Present, not merely un-refused — `vault_sync_guard.sh
   check` prints `OK:` on every success path (`:129`, `:137`), so its absence means the guard
   never ran, which from the outside looks exactly like a guard that passed.

   ```check id=vault-guard-passed
   [ -n "$(grep -F 'vault_sync_guard[check]: OK:' "$AGENT_ATTEMPT_LOG")" ] &&
   [ -z "$(grep -F 'REFUSING to run' "$AGENT_ATTEMPT_LOG")" ]
   ```

7. **No markdown table and no horizontal rule in the delivered body.** Discord renders
   neither, and the 2000-character splitter breaks a table across messages mid-row.

   ```check id=discord-subset-held
   body="$(find "$HOME/logs/eod-summary" -maxdepth 1 -name 'eod-summary-*.md' \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$body" ] || { echo "n/a: no artifact this run"; exit 77; }
   bad="$(grep -nE '^\||^---' "$body")"
   [ -z "$bad" ] || echo "unrenderable in Discord:$bad"
   [ -z "$bad" ]
   ```

8. **The run was not silently skipped by the global lock.** `sweep`, because the failure is
   that nothing ran at all. Reads the unit's own journal since the timer's last trigger, not
   the shared `logs/agent_propose.log`, whose `SKIP: previous run still active` line names no
   job (`bin/agent_propose.sh:144`) — journald scopes by unit, that file does not. This is the
   likeliest of the nine to fire: until 2026-09-11, 22:15 sat 45 minutes ahead of
   `bd-stall-radar` and 75 ahead of `bd-followup-drafts`, all three sharing one lock; those
   two are on Monday mornings now, and the `*:0/15` content-change-dispatch ticks are what
   remains on the lock at this hour.

   ```check id=not-lock-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

9. **The timer fired within its own cadence.** `sweep`, against systemd rather than against a
   report claiming it ran. 26 hours: daily cadence plus the 5-minute jitter and slack for a
   late `Persistent=true` catch-up. Deliberately **not** the sibling's 4-day window — this job
   runs every day, so a 4-day budget would stay green through three missed nights.

   ```check id=timer-fired-this-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ "$(( $(date +%s) - ${t#@} ))" -lt 93600 ]
   ```

## Known failure modes

- **The Notion row is not evidence this job wrote it.** Dave's Mac-side `eod-wrap` overwrites
  the same row in place — the profile says so at `:26` and asks for this summary to be written
  "as a first draft he corrects, not as the last word". So a present, well-formed
  `<date> — EOD Summary` row proves only that *something* wrote it, possibly hours later from
  a different machine. **The receipt is the only box-side evidence**, which is why every check
  above reads the receipt and none reads Notion. Anyone adding a "the row exists" check here
  would be asserting Dave's laptop.
- **Partial Notion write.** Daily Plans lands, Daily Log does not: the exit code is 0, the
  receipt exists, the body file exists, Discord gets the summary, and the structured row Dave
  reviews weekly is silently missing. Signal: `both-notion-rows-landed`. Not observed in the
  receipts under `~/logs/eod-summary/` as of 2026-09-10 — recorded because it is unobservable
  by every other means, not because it has happened.
- **Silent lock skip, and this is the job most exposed to it.** `agent_propose.sh:144` exits 0
  after logging the skip: no alert, no artifact, and `OnFailure` never fires because nothing
  failed. Signal: `not-lock-skipped`.
- **The 1800-character target is not met and is deliberately not asserted.** Measured
  2026-09-10 with `wc -m` over the eight most recent bodies: 1754, 1774, 2516, 3046, 3134,
  3274, 3306 and 3812 characters against the stated 1800 — two comply, and **six of eight
  exceed Discord's 2000-char single-message limit**, the worst record of the three reporting
  jobs. A check red on six good runs in eight is an alarm nobody reads, so
  what is asserted is the hard rule the surface actually breaks on (`discord-subset-held`) and
  the budget is recorded here as an open finding shared with `praetorium-daily-plan`. Either
  the profiles' target or the delivery path needs a decision; the contract should not imply
  one was made.
- **A thin day looks like a broken job.** By design — the profile forbids inventing a brain
  dump and calls an empty section a finding (`:21`). No check distinguishes "Dave was off-box"
  from "the agent failed to gather evidence", and none can from the artifact alone. The
  receipt and the delivery checks establish that the run happened and reached Dave; whether
  the day was really that quiet is a question for Dave, not for a check.
- **Midnight rollover, and this job runs closest to it.** `RUN_DATE` and
  `AGENT_RUN_STARTED_AT` are exported once by `agent_propose.sh` (`:317`, `:34`) and read, never
  recomputed, so a run starting 22:20 and finishing after midnight still writes
  `receipt-<the date it started>.json` and upserts rows for that date. The profile re-derives
  `DATE="${RUN_DATE:-$(date +%F)}"` from the same export. Worth naming because a 15-minute
  budget starting at 22:20 makes this the one job where the question comes up.
