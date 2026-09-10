# Contract: overnight-morning-report

Read on 2026-09-10 from `systemd/overnight-morning-report.{service,timer}`,
`bin/run_overnight_morning_report_cc.sh`, `profiles/overnight_morning_report_cc_task.md`,
`bin/deliver.sh`, `profiles/overnight_morning_report.env.example`, and the artifacts under
`~/logs/overnight/`. `bin/check_deploy_drift.sh` reported `drift: clean` the same day.

`~/.config/agent-workforce/overnight_morning_report.env` is deny-listed and was **not** read;
the wiring claims come from the committed `.env.example` it mirrors.

**This job has no Notion receipt, unlike its two Marcus siblings.** It writes no Notion row at
all — its artifact is the report file itself, and the only end-to-end evidence is that file
plus the delivery receipt. The checks below are shaped around that, and the absence is stated
here so nobody adds a receipt check that could never pass.

## Identity

| | |
|---|---|
| Unit | `overnight-morning-report.service` / `.timer` |
| Owner | **marcus** (`design/agents/marcus.toml`) |
| Surface | S2 — scheduled headless Claude Code |
| Executor | `claude -p --model claude-sonnet-5`, box subscription, marcus's pointer-skill tree (T3.1) |
| Contract version | 1 (2026-09-10) |
| Alerted | yes — `OnFailure=agent-alert@%n.service` |

## Trigger

`OnCalendar=*-*-* 06:15`, `RandomizedDelaySec=5min`, `Persistent=true`. Daily.

It is the **second half of a two-unit pair**: `overnight-pre-snapshot.timer` runs at 04:25
(2min jitter) and writes `~/logs/overnight/pre-snapshot-<stamp>.log`; this job diffs the night
against that snapshot. The gap is ~1h50m, which is the slack that makes a missed snapshot
invisible here — see `## Known failure modes`.

## Inputs

| Source | Freshness requirement | If stale or absent |
|---|---|---|
| `~/logs/overnight/pre-snapshot-*.log`, newest | **last night's** — the report is a diff against it | proceed and say so. A report diffed against a two-day-old snapshot describes the wrong night while reading normally |
| `systemctl list-timers`, `journalctl -p warning`, unit states | live | proceed; a unit that did not fire is the finding |
| `~/logs/agent-alert.log` | **must be dated before it is read** | proceed *and mark it*: the profile's W17 rule (`:76`) — "date the log before you read it; a bare tail is how a dead alert gets reported as last night's". Two or more days old ⇒ the report must say "no new alerts since `<date>`; the lines below are history". Unreadable age ⇒ report `UNKNOWN` as unverified, never as fresh |
| `~/agent-workforce/logs/cost.log` (`tail -20`) | last night's | proceed; FAIL/BLOCKED lines are the report's spine |
| `~/agent-worktrees/inbox` — new filenames since the snapshot stamp, and the snapshot's `## Inbox lifecycle summary` | last night's | proceed. The lifecycle summary is read from the snapshot, **not** recounted from disk: the worktree lags the Mac-side promote pass |
| MCP health — `curl 127.0.0.1:8765/health`, `ss -ltn \| grep 8766` | live | proceed; a down daemon is a line item |
| `profiles/overnight_morning_report_cc_task.md` (deployed) | readable | runner exits 1 naming the path (`:32`) |
| `~/agent-workforce/skills/marcus/.claude-plugin/plugin.json` | readable | runner exits 1 naming the path (`:33`). Otherwise silent — exit 0, no diagnostic, no skills (T3.1) |

**`~/vault` is not an input, and there is no vault guard here.** That is deliberate and
documented in the runner (`:13-15`): *"this report reads systemd, journals, logs and the inbox
worktree — never the vault mirror — so a stale mirror is not a reason to withhold it, and
gating on one would invent a new way to lose the report."* The absence of `vault-guard-passed`
from the checks below is therefore correct, not an oversight — the two daily-rhythm siblings
carry it and this job must not.

## Outputs

- **Report file** — `~/logs/overnight/morning-report-<stamp>.md`, **mode 600**. The runner sets
  `umask 077` explicitly (`:23`) because "every report written under the hermes path was mode
  600; Claude Code writes with the inherited umask (0002 under systemd here), which would
  silently widen them to 664". This is the only one of Marcus's four whose artifact has a
  stated permission, so it is the only one with a mode check.
- **Delivery** — `ExecStartPost=bin/deliver_report.sh`, `REPORT_DIR=/home/dave/logs/overnight`,
  `REPORT_GLOB=morning-report-*.md`, `DELIVERY_ROUTE=ops` → channel
  `62f321f3-bd6a-4b31-b19b-b8b49bed30f4`, event kind 9, notify `marcus`; plus Discord, subject
  `[Praetorium] Morning report`. Anchored by `DELIVERY_RUN_MARKER=/home/dave/logs/run-markers/%n`,
  stamped by an `ExecStartPre` before `ExecStart` because `ExecStartPost` cannot see
  `agent_propose.sh`'s `AGENT_RUN_STARTED_AT`.
- **No Notion row, no vault write, no proposal.** `AGENT_RUN_MODE=ops`.
- **Shape:** no markdown tables, no horizontal rules (`profiles/…:165`, `:173`), target under
  1800 characters (`:176`). See `## Known failure modes` for the target.

## Decline conditions

**None.** A night with nothing wrong is still a report — "all nine timers fired, nothing
failed" is the output, not a reason to stay silent, and it is the output Dave reads to know the
box is alive. The report *is* the heartbeat, so silence and health are the two states it exists
to distinguish; letting it decline would collapse them.

The profile has no decline path and `agent_propose.sh` would treat a `^DECLINE:` here as this
job's own sentinel, so `no-decline-sentinel` asserts its absence for the same reason as the two
sibling contracts.

## Side effects

- Writes `~/logs/overnight/morning-report-<stamp>.md` (mode 600, per `umask 077`).
- `mkdir -p ~/logs/overnight` (`:36`).
- Touches `~/logs/run-markers/overnight-morning-report.service` (`ExecStartPre`).
- Appends to `~/agent-workforce/logs/agent_run.log`,
  `logs/last-attempt/overnight-morning-report.log`, `cost.log`, and one line to
  `~/logs/delivery-receipts.jsonl`.
- Takes `${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}`.
- Runs with cwd `$HOME/agent-workforce` (`:42`), **not** a vault checkout — the inbox worktree
  is read by absolute path.

Nothing else. It reads `~/agent-worktrees/inbox` and never writes it; it never touches
`~/vault` at all.

## Acceptance checks

Eight checks. Six `run`, two `sweep`. There is no `vault-guard-passed` (no guard, by design)
and no receipt check (no Notion). `alert-staleness-reported` is the one that encodes a rule
this job has already broken once.

1. **A report was written by this run.** The whole point of `AGENT_VERIFY_CMD`, restated here
   because the delivery path re-posts whatever the glob finds: without a this-run anchor,
   `deliver_report.sh` posts yesterday's file for up to 26 hours and the failure is invisible
   at the reading end (2026-07-21 regression, cited in the env example).

   ```check id=report-is-this-runs
   r="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'morning-report-*.md' \
          -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$r" ] || { echo "no report written by this run"; exit 1; }
   [ -s "$r" ]
   ```

2. **The report is mode 600.** The runner's `umask 077` is a single line with no test behind
   it, and the failure it prevents is silent: a report at 664 is readable by group and world,
   contains last night's alerts, unit failures and inbox activity, and looks identical to a
   correct one. Measured 2026-09-10 — all eight most recent reports are `-rw-------`, while the
   `pre-snapshot-*.log` files beside them are 644, so the two units genuinely differ and this
   is asserting a real, currently-held property rather than a hope.

   ```check id=report-is-mode-600
   r="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'morning-report-*.md' \
          -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$r" ] || { echo "n/a: no report this run"; exit 77; }
   m="$(stat -c '%a' "$r")"
   [ "$m" = 600 ] || echo "report mode $m, expected 600 — umask 077 did not apply"
   [ "$m" = 600 ]
   ```

3. **A stale alert log is reported as stale.** The W17 rule, and the only check here that
   asserts report *content*. It is written to be `77` on a healthy box and to fail exactly when
   the mistake it names becomes possible: if the alert log is under two days old there is
   nothing to report, so it is not applicable. Measured 2026-09-10 — the log's newest entry is
   the same day, so this check is `77` today; it can only go red on a box where the rule
   actually matters.

   ```check id=alert-staleness-reported when=sweep
   log="$HOME/logs/agent-alert.log"
   [ -f "$log" ] || { echo "n/a: no alert log yet"; exit 77; }
   age=$(( ( $(date +%s) - $(stat -c %Y "$log") ) / 86400 ))
   [ "$age" -ge 2 ] || { echo "n/a: alert log is $age day(s) old, nothing to declare"; exit 77; }
   r="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'morning-report-*.md' 2>/dev/null | sort | tail -1)"
   [ -n "$r" ] || { echo "n/a: no report to inspect"; exit 77; }
   [ -n "$(grep -iE 'stale|no new alerts since|history|unverified' "$r")" ] \
     || echo "alert log is $age days old and the newest report does not say so (W17)"
   [ -n "$(grep -iE 'stale|no new alerts since|history|unverified' "$r")" ]
   ```

4. **What was delivered is what this run wrote.** By `artifact_sha256` (`bin/deliver.sh:158`),
   not by assumption. `deliver_report.sh` is fail-soft and always exits 0 so a transport hiccup
   cannot fire the `OnFailure` alert (stated in the unit at `:24-26`) — which means a delivery
   that silently did not happen leaves no other trace.

   ```check id=delivered-this-runs-artifact
   r="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'morning-report-*.md' \
          -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$r" ] || { echo "n/a: no artifact this run"; exit 77; }
   sha="$(sha256sum "$r" | cut -d' ' -f1)"
   line="$(grep -F '"job": "overnight-morning-report.service"' \
             "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null | tail -1)"
   [ -n "$line" ] || { echo "no delivery receipt for this unit"; exit 1; }
   case "$line" in *'"outcome": "delivered"'*) ;; *) echo "newest delivery not delivered: $line"; exit 1 ;; esac
   case "$line" in *"$sha"*) echo "delivered $sha" ;; *) echo "delivered an artifact this run did not write"; exit 1 ;; esac
   ```

5. **The report was diffed against last night's snapshot, not an older one.** This job is one
   half of a pair; if `overnight-pre-snapshot` failed at 04:25 the newest snapshot is 26+ hours
   old and this report describes the *previous* night while reading exactly like a correct one.
   Nothing else on the box compares the two units' timing.

   ```check id=snapshot-is-last-nights
   s="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'pre-snapshot-*.log' 2>/dev/null | sort | tail -1)"
   [ -n "$s" ] || { echo "no pre-snapshot at all — the report has nothing to diff against"; exit 1; }
   age=$(( $(date +%s) - $(stat -c %Y "$s") ))
   [ "$age" -lt 93600 ] || echo "newest pre-snapshot is $(( age / 3600 ))h old — this report diffs the wrong night"
   [ "$age" -lt 93600 ]
   ```

6. **This run did not decline.**

   ```check id=no-decline-sentinel
   [ -f "$AGENT_ATTEMPT_LOG" ] || { echo "no attempt log for this run"; exit 1; }
   [ -z "$(grep -E '^DECLINE:' "$AGENT_ATTEMPT_LOG")" ]
   ```

7. **No markdown table and no horizontal rule.** Discord renders neither; the splitter breaks a
   table across messages mid-row. Not hypothetical for *this* job specifically — four morning
   reports from July 2026 carry `^|` rows and four carry `^---`, from before the Discord-subset
   rules reached the profile. Measured 2026-09-10: none since.

   ```check id=discord-subset-held
   r="$(find "$HOME/logs/overnight" -maxdepth 1 -name 'morning-report-*.md' \
          -newermt "@$AGENT_RUN_STARTED_AT" 2>/dev/null | sort | tail -1)"
   [ -n "$r" ] || { echo "n/a: no artifact this run"; exit 77; }
   bad="$(grep -nE '^\||^---' "$r")"
   [ -z "$bad" ] || echo "unrenderable in Discord:$bad"
   [ -z "$bad" ]
   ```

8. **The timer fired within its own cadence, and was not silently lock-skipped.** `sweep`, both
   halves, because the failure is that nothing ran. 26 hours: daily plus 5min jitter plus slack
   for a late `Persistent=true` catch-up. The skip line is read from the unit's journal, not
   from the shared `logs/agent_propose.log`, which names no job (`bin/agent_propose.sh:144`).

   ```check id=timer-fired-and-not-skipped when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer has never fired"; exit 1 ;; esac
   [ "$(( $(date +%s) - ${t#@} ))" -lt 93600 ] || { echo "last fired $(( ( $(date +%s) - ${t#@} ) / 3600 ))h ago"; exit 1; }
   [ -z "$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager \
             | grep -F 'SKIP: previous run still active')" ]
   ```

## Known failure modes

- **The filename's `Z` is not reliably UTC, so never derive the run from it.** Measured
  2026-09-10 across the eight most recent reports: four carry a genuine UTC stamp
  (`…T0418Z.md` written 06:18 CEST) and four carry **local time labelled `Z`**
  (`…T0620Z.md` written 06:21 CEST — 04:21 UTC). The agent composes the filename itself and is
  inconsistent about it. Consequence: a check that sorts or parses these names to find "this
  run's report" would silently pick the wrong file whenever the two conventions interleave,
  which they do. Every check above uses `-newermt "@$AGENT_RUN_STARTED_AT"` on the mtime for
  exactly this reason. Not worth a check of its own — the filename is cosmetic and the mtime is
  authoritative — but it is worth knowing before writing the ninth check.
- **A dead alert log read as last night's.** The W17 defect: every line already carries
  `failed at <ISO>Z`, so "there is a timestamp in it" proves nothing and an eight-day-dead log
  renders identically to a live one. Closed in the profile by requiring `stat` before `tail`;
  `alert-staleness-reported` is the assertion, and it is `77` whenever the log is fresh — which
  means **on a healthy box this check tests nothing and that is correct**. It exists for the
  week the alerting itself is broken, which is precisely the week no other signal fires.
- **The pre-snapshot silently missing.** `overnight-pre-snapshot` at 04:25 and this job at
  06:15 are separate units with separate alerts; if the first fails, this one succeeds, writes
  a well-formed report, delivers it, and describes the wrong night. Signal:
  `snapshot-is-last-nights`. Nothing else pairs them.
- **Silent lock skip.** `agent_propose.sh:144` exits 0 after logging the skip — no alert, no
  artifact, `OnFailure` never fires. 06:15 is a quiet slot (the 06:00 daily-plan run is the
  only neighbour, and a 15-minute budget makes an overlap possible), so this is real but less
  likely than for the 22:15 job. Signal: `timer-fired-and-not-skipped`.
- **The report is delivered but nobody reads it — and it exits 0 either way.**
  `deliver_report.sh` is deliberately fail-soft (unit `:24-26`) so a Discord or Buzz hiccup
  cannot mark the report unit failed. Correct for alert hygiene, and it means transport failure
  has *no* signal in the unit's status. Signal: `delivered-this-runs-artifact`, from the
  receipt line, which is the only place it is recorded.
- **The 1800-character target is not met and is deliberately not asserted.** Measured
  2026-09-10 with `wc -m` over the eight most recent reports: 1840, 2231, 2325, 2417, 2437,
  2638, 2704 and 2833 characters against a stated 1800. **None complies**, and seven of the
  eight exceed Discord's 2000-char single-message limit — this job misses the budget more
  consistently than either daily-rhythm sibling, and is the only one of the three that never
  meets it. Asserting it would ship a check that is red on every run from the day
  it lands. Recorded here as the open finding, shared across all three reporting contracts:
  either the target moves or the delivery path splits properly. The hard rule that *is*
  asserted is `discord-subset-held`.
- **No vault guard, on purpose.** Named as a failure mode only because the two sibling
  contracts carry `vault-guard-passed` and the omission here looks like one. The runner
  explains it at `:13-15`; adding a guard would gate a report that reads no vault data on the
  freshness of data it never opens, and would "invent a new way to lose the report".
