# Contract: praetorium-daily-plan

Everything below was read on 2026-09-10 from `systemd/praetorium-daily-plan.{service,timer}`,
`bin/run_daily_rhythm_cc.sh`, `profiles/daily_plan_task.md`, `bin/notion_daily.py`,
`bin/deliver.sh`, `profiles/daily_plan.env.example` and the live artifacts under
`~/logs/daily-plan/`. Where the repo source and the deployed copy could differ the repo
source was read; `bin/check_deploy_drift.sh` reported `drift: clean` the same day, so they
are the same bytes.

The live per-job env (`~/.config/agent-workforce/daily_plan.env`) is deny-listed and was
**not** read. Every claim about job wiring below comes from the committed
`profiles/daily_plan.env.example`, which that file is documented to mirror.

## Identity

| | |
|---|---|
| Unit | `praetorium-daily-plan.service` / `.timer` |
| Owner | **marcus** (`design/agents/marcus.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-sonnet-5`, box subscription, `--plugin-dir` at marcus's pointer-skill tree (T3.1) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` on the live unit |

## Trigger

`OnCalendar=Mon..Fri 06:00`, `RandomizedDelaySec=2min`, `Persistent=true`. Recurring; no
expiry.

**Weekdays only, and the jitter is deliberately small.** 06:00 is a slot Dave plans around,
unlike the overnight jobs where jitter only spreads load — so the unit caps drift at two
minutes rather than the five its siblings use. The consequence for check design is that the
longest *legitimate* gap between firings is Friday 06:00 to Monday 06:00: 72 hours, not 24.
A daily-cadence freshness window would report every Monday morning as a stopped timer.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| Notion Daily Plans / Task Inbox / Client Pipeline, via `python3 bin/notion_daily.py inputs --date "$DATE"` | live at run time | **proceed and flag** — the profile's rule is "a missing input is reported as missing"; an errored query becomes one `UNCONFIRMED:` line, never a silently thinner plan |
| `~/vault` mirror (`04_operations/current_priorities.md`, `open_loops.md`, `daily_routines.md`, `key_decisions.md`, `wins_ledger.md`, `07_daily/logs/`, `03_projects/active/*/status.md`) | clean, and within `vault_sync_guard.sh`'s lag budget | **refuse**: the guard gates the run at `bin/run_daily_rhythm_cc.sh:36` and a failure exits 1 with `REFUSING to run`. A plan off a frozen mirror is confidently wrong rather than absent — the 2026-07-23 → 07-27 freeze is why the gate is there |
| `~/agent-workforce/config/fleet-units.tsv` | present and 5-column | **refuse the section**: the profile prints `FATAL: … Unit coverage is UNKNOWN` rather than reporting "nothing scheduled". A 4-column copy matches `NF>=5` nowhere, and `systemctl list-timers` with an empty argument array lists all 44 timers on the box — a silently empty list renders as a full report derived from nothing |
| `python3 bin/agent_inbox_notion_sync.py --dry-run`, first line | this run's | **proceed and flag** as `UNCONFIRMED: pending count`. The profile forbids deriving the count from `ls` of the inbox worktree: that directory lags the Mac-side promote pass, and on 2026-08-10 a raw file count put "40 pending" in the plan the same morning the correct figure, 25, ran in the morning report ten minutes later |
| `~/logs/agent-alert.log`, `journalctl -p warning`, `logs/cost.log`, newest `~/logs/overnight/morning-report-*.md` | last night's | proceed; anything FAILED or BLOCKED overnight is a line item, not a footnote |
| `~/dev/AI_Trading_Bot` refs | fetched at run time — an unmerged branch **is** the in-flight thread, so a stale fetch names the wrong one | proceed; a failed fetch is reported rather than silently answered from the old ref list |
| `profiles/daily_plan_task.md` (deployed copy) | readable | wrapper exits 1 with the path named (`run_daily_rhythm_cc.sh:31`) |
| `~/agent-workforce/skills/marcus/.claude-plugin/plugin.json` | readable | wrapper exits 1 with the path named. A `--plugin-dir` that does not exist is **silent** — exit 0, no diagnostic, no skills — so this guard is the only thing that would ever say so (T3.1) |

## Outputs

- **Notion row** — `<YYYY-MM-DD> — Daily Plan` in the Daily Plans data source
  `3288d768-1ede-8190-ad5a-000b9710833e`, upserted by title so a re-run replaces the row and
  its children instead of stacking a second one. `Events Count` and `Tasks Count` are the two
  numbers counted from `notion_daily.py inputs`.
- **Body file** — `~/logs/daily-plan/daily-plan-<UTC ISO minute>Z.md`, the exact bytes that
  become both the Notion body and the Discord message. Mode 644; the runner sets no `umask`,
  unlike `run_overnight_morning_report_cc.sh`.
- **Receipt** — `~/logs/daily-plan/receipt-<YYYY-MM-DD>.json`, written by
  `notion_daily.py:157` **only after** Notion accepts the upsert, carrying
  `{kind, date, page, action, title}`. It is the only proof the run reached Notion; the exit
  code is not, because the runtime exits 0 when a provider error becomes the agent's final
  response (2026-07-21 regression).
- **Delivery** — `ExecStartPost=bin/deliver_report.sh` with `REPORT_DIR=~/logs/daily-plan`,
  `REPORT_GLOB=daily-plan-*.md`, `DELIVERY_ROUTE=ops` → channel
  `62f321f3-bd6a-4b31-b19b-b8b49bed30f4`, **event kind 9** (stream), notify `marcus`; plus
  Discord. Anchored by `DELIVERY_RUN_MARKER=~/logs/run-markers/%n`, stamped by an
  `ExecStartPre` before `ExecStart`, because `ExecStartPost` cannot see
  `agent_propose.sh`'s `AGENT_RUN_STARTED_AT`.
- **Shape:** no markdown tables and no horizontal rules — Discord renders neither, and the
  2000-char splitter breaks a table across messages mid-row. Target under 1800 characters;
  see `## Known failure modes` for what that target is actually worth.

## Decline conditions

**None. There is no state in which this job legitimately produces nothing**, and that is a
claim worth testing rather than an omission.

The profile says it twice: *"Run this every time, including when a row for today already
exists"* and *"Never end the run by concluding 'the plan is already live, no action
needed': a run that writes nothing has failed."* The helper's upsert is the designed path
for a re-run, a manual run and the `Persistent=true` reboot catch-up — a late firing
**always** finds a row already there, so "already exists" can never be a reason to stop.

Consequently a `^DECLINE:` line in this run's output is a **failure**, not a legitimate
branch, and `no-decline-sentinel` asserts its absence. This is the opposite polarity from
`knowledge-digest`, where the sentinel is one of two correct outcomes, and the difference is
the whole reason both are written down.

## Side effects

- Upserts one Notion page and **replaces all of its children** (`notion_daily.py:137`).
- Writes the body file and the date-keyed receipt under `~/logs/daily-plan/`.
- Touches `~/logs/run-markers/praetorium-daily-plan.service` (`ExecStartPre`).
- Writes a run record to `~/agent-workforce/logs/agent_run.log`, this attempt's own output
  to `logs/last-attempt/daily-plan.log`, and a cost line to `cost.log`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`.
- Appends one line to `~/logs/delivery-receipts.jsonl` (`bin/deliver.sh:136`).
- **`git -C ~/dev/AI_Trading_Bot fetch --quiet --all` — the one write outside this job's own
  paths.** It updates remote-tracking refs in a repo the job otherwise only reads. It is in
  contract because a job that says it is read-only and is not would fail a write-boundary
  audit for a reason nobody would find; no merge, no push, no working-tree change.

Nothing else. No inbox worktree and no proposal commit — `AGENT_RUN_MODE=ops`. The task
never writes `~/vault`, `~/dev/*` or `07_daily/logs/` on any branch.

## Acceptance checks

Nine checks. Six decide the artifact from inside the run; `not-lock-skipped` and
`timer-fired-this-window` are `sweep`, because their failure mode is that nothing ran at
all and no run-vantage check can see that. Ids are the stable names; `## Known failure
modes` references them, never the numbers.

1. **The receipt is this run's, and it is keyed to this run's date.** `AGENT_VERIFY_CMD`
   globs `receipt-*.json`, which any receipt newer than the run start satisfies — including
   one written under a *different* date by a run that disagreed with itself about which day
   it was. The filename is `receipt-${RUN_DATE}.json` (`notion_daily.py:160`), so naming the
   date costs nothing and closes that.

   ```check id=receipt-is-this-runs
   f="$HOME/logs/daily-plan/receipt-${RUN_DATE}.json"
   [ -f "$f" ] || { echo "no receipt for $RUN_DATE — the run never reached Notion"; exit 1; }
   [ -n "$(find "$HOME/logs/daily-plan" -maxdepth 1 -name "receipt-${RUN_DATE}.json" \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null)" ]
   ```

2. **The receipt names a real Notion page and a real upsert.** An empty `page`, or an
   `action` outside `created`/`updated`, means the helper reached the API and got something
   it could not use — which the exit code does not distinguish from success.

   ```check id=receipt-names-a-notion-row
   f="$HOME/logs/daily-plan/receipt-${RUN_DATE}.json"
   [ -f "$f" ] || { echo "n/a: no receipt this run"; exit 77; }
   grep -q '"kind": "daily-plan"' "$f" || { echo "receipt is not this job's"; exit 1; }
   grep -q "\"date\": \"$RUN_DATE\"" "$f" || { echo "receipt names another date"; exit 1; }
   grep -qE '"action": "(created|updated)"' "$f" || { echo "no upsert action"; exit 1; }
   grep -qE '"page": "[0-9a-f]{8}-[0-9a-f-]{27}"' "$f"
   ```

3. **The body file is this run's.** The receipt proves Notion accepted the upsert; it does
   not prove the file `deliver_report.sh` is about to post came from this run. On a night the
   agent fails after writing nothing, the glob still finds yesterday's.

   ```check id=body-is-this-runs
   body="$(find "$HOME/logs/daily-plan" -maxdepth 1 -name 'daily-plan-*.md' \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$body" ] || { echo "no body file written by this run"; exit 1; }
   [ -s "$body" ]
   ```

4. **What was delivered is what this run wrote.** The delivery receipt carries
   `artifact_sha256` (`bin/deliver.sh:158`), so the two ends can be compared rather than
   assumed. This is the check that separates "the report was written" from "Dave read it",
   and it catches a stale artifact re-delivered on a night the agent produced nothing —
   which at the reading end is indistinguishable from a fresh one.

   ```check id=delivered-this-runs-artifact
   body="$(find "$HOME/logs/daily-plan" -maxdepth 1 -name 'daily-plan-*.md' \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$body" ] || { echo "n/a: no artifact this run"; exit 77; }
   sha="$(sha256sum "$body" | cut -d' ' -f1)"
   line="$(grep -F '"job": "praetorium-daily-plan.service"' \
             "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null | tail -1)"
   [ -n "$line" ] || { echo "no delivery receipt for this unit"; exit 1; }
   case "$line" in *'"outcome": "delivered"'*) ;; *) echo "newest delivery not delivered: $line"; exit 1 ;; esac
   case "$line" in *"$sha"*) echo "delivered $sha" ;; *) echo "delivered an artifact this run did not write"; exit 1 ;; esac
   ```

5. **This run did not decline.** Asserted because the contract above claims declining is
   impossible here — a claim that is only worth writing if something tests it. A `DECLINE:`
   from this job means the profile's "run it every time" rule was reasoned around.

   ```check id=no-decline-sentinel
   [ -f "$AGENT_ATTEMPT_LOG" ] || { echo "no attempt log for this run"; exit 1; }
   [ -z "$(grep -E '^DECLINE:' "$AGENT_ATTEMPT_LOG")" ]
   ```

6. **The vault guard ran and passed.** Present, not merely un-refused:
   `bin/vault_sync_guard.sh check` prints `OK:` on every success path (`:129`, `:137`), so
   its absence means the guard never ran — the same silence a dead run produces.

   ```check id=vault-guard-passed
   [ -n "$(grep -F 'vault_sync_guard[check]: OK:' "$AGENT_ATTEMPT_LOG")" ] &&
   [ -z "$(grep -F 'REFUSING to run' "$AGENT_ATTEMPT_LOG")" ]
   ```

7. **No markdown table and no horizontal rule in the delivered body.** Discord renders
   neither, and the splitter breaks a table across messages mid-row. This is not
   hypothetical: four morning reports from July 2026 carry `^|` rows and four carry `^---`,
   all from before the Discord-subset rules were written into the profiles. Measured
   2026-09-10 — no artifact of any of the three reporting jobs has carried either since.

   ```check id=discord-subset-held
   body="$(find "$HOME/logs/daily-plan" -maxdepth 1 -name 'daily-plan-*.md' \
             -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$body" ] || { echo "n/a: no artifact this run"; exit 77; }
   bad="$(grep -nE '^\||^---' "$body")"
   [ -z "$bad" ] || echo "unrenderable in Discord:$bad"
   [ -z "$bad" ]
   ```

8. **The run was not silently skipped by the global lock.** `sweep`, because the failure is
   that nothing ran. It reads the unit's journal since the timer's last trigger, not the
   shared `logs/agent_propose.log`, whose `SKIP: previous run still active` line names no job
   (`bin/agent_propose.sh:144`). journald scopes by unit; that file does not.

   ```check id=not-lock-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

9. **The timer fired within its own cadence.** `sweep`, asserted against systemd rather than
   against a report that says it ran. The window is **four days, not one**: Friday 06:00 to
   Monday 06:00 is a legitimate 72-hour gap on a `Mon..Fri` timer, so a daily budget would
   ship red every Monday and be ignored by the second week. A never-fired timer reports a
   `LastTriggerUSec` that is not an epoch and fails rather than reading as 1970.

   ```check id=timer-fired-this-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ "$(( $(date +%s) - ${t#@} ))" -lt 345600 ]
   ```

## Known failure modes

- **The 1800-character target is not met and is deliberately not asserted.** Measured
  2026-09-10 with `wc -m` over the eight most recent bodies: 1745, 1797, 1799, 1812, 1834,
  1849, 3220 and 3521 characters against a stated target of 1800 — three of eight comply, and
  two run past Discord's 2000-char single-message limit by more than half. Count characters,
  not bytes: `wc -c` reads 20-50 higher on these files and flips the two borderline ones to
  failing. A check red on five of eight otherwise-good runs is not a check, it is a
  broken promise with an alarm attached, so what is asserted here is the *hard* rule the
  surface actually breaks on (`discord-subset-held`) and the length is recorded as this
  open finding. Either the profile's budget or the delivery path needs a decision; the
  contract should not pretend one was made.
- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging `SKIP: previous run
  still active`. No alert, no artifact, and `OnFailure` never fires because nothing failed.
  22:15 EOD and 23:00 bd-stall-radar are the near neighbours; 06:00 is quiet, which makes
  this the least likely of the three to be caught by someone noticing. Signal:
  `not-lock-skipped`.
- **Stale mirror.** Guarded — this is the closed one, and the reason `vault_sync_guard.sh`
  exists. Signal: `vault-guard-passed`, which asserts the guard *ran*, because a guard that
  was skipped and a guard that passed look identical from the outside.
- **The plan lands but nobody reads it.** Two distinct causes with one appearance: a
  delivery that never happened, and a delivery of the previous day's file. Both are
  `delivered-this-runs-artifact`; neither is visible in the unit's exit status, since
  `deliver_report.sh` is fail-soft and always exits 0 so a transport hiccup cannot fire the
  `OnFailure` alert.
- **Inbox backlog overstated.** The profile's `--dry-run` rule exists because counting files
  in the inbox worktree includes items already decided in Notion but not yet cleared from
  disk (2026-08-10: "40 pending" in the plan, 25 in the morning report ten minutes later).
  Not currently decidable from the artifact — the plan quotes a number without saying where
  it came from. Closing this needs the profile to emit the source, not a cleverer check.
- **Monday reads as a stopped timer.** Only to a check with a daily window; see
  `timer-fired-this-window`. Recorded because the obvious 26-hour budget every sibling job
  uses is wrong here, and copying one in is the likely edit.
- **Midnight rollover.** `RUN_DATE` and `AGENT_RUN_STARTED_AT` are exported once by
  `agent_propose.sh` (`:317`, `:34`) and read, never recomputed, so a run spanning midnight
  cannot disagree with itself about which date it was writing. A 06:00 job is far from
  midnight; the receipt is date-keyed anyway, so the guarantee is worth naming rather than
  relying on the slot.
