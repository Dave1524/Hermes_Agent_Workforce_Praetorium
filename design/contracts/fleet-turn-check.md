# Contract: fleet-turn-check

Read on 2026-09-11 from `systemd/fleet-turn-check.{service,timer}` and
`buzz-team/fleet-turn-check.sh` (deployed as `~/.config/buzz-team/fleet-turn-check.sh`). A
light contract (T4.4): trigger, cadence, artifact, evidence, remediation owner, retirement
condition, and the checks that decide them from the `sweep` vantage. Written while the fleet was
paused (`~/OUTBOX/fleet-pause-2026-09-11.md`), so every timer read `LastTriggerUSec` empty that
day; the checks report that as "not loaded or never fired", which is the correct answer.

This is the job written after the four-day outage of 2026-08-27..31 in which every conventional
signal stayed green. Its whole product is one verdict line per hour, and an alert when the
verdict is FAIL.

## Identity

| | |
|---|---|
| Unit | `fleet-turn-check.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell, no model |
| Runner | `buzz-team/fleet-turn-check.sh` (deployed copy at `~/.config/buzz-team/`), `XDG_RUNTIME_DIR=/run/user/1000` so it can see the `--user` fleet |
| Cadence | hourly, `RandomizedDelaySec=120`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` → `bin/agent_alert.sh`, throttled to one notification per transition plus one reminder per 24h |
| Remediation owner | Dave, via the alert. The script asserts; it never restarts a unit |
| Retirement condition | none — standing. Retire only when a live turn probe with the same coverage replaces it |
| Contract version | 1 (2026-09-11) |

## Trigger

`fleet-turn-check.timer`: `OnCalendar=hourly`, `RandomizedDelaySec=120`, `Persistent=true`. A
missed hour is caught up on the next boot. The service is `Type=oneshot`.

## Inputs

- `systemctl --user list-units 'buzz-agent@*'` — the roster is asked for, never asserted
  (design rule 1 in the script header). A unit that appears is checked; a hardcoded list is
  how the newest agent silently stops being covered.
- Per-unit CPU counters, compared against the previous run's `~/logs/fleet-turn-check.state`
  (`fleet-turn-check.sh:32`). Absent or unwritable state degrades to "CPU deltas unavailable
  this run" (`:95`) and the run still decides on the other signals.
- The interaction receipts under `~/agent-workforce/var/workflow-receipts/buzz-agent@<name>/`
  (gate 5, since 2026-09-19), read through the deployed `bin/turn_rate.py`: every turn's
  `origin` says what woke it, and more than `FLEET_UNOWNED_MAX` (3) turns in
  `FLEET_RATE_WINDOW_MIN` (60) minutes with `origin = scheduled` — the session's own
  CronCreate or `/loop` re-prompting it — is a FAIL naming the unit and the run ids. Owner
  turns are counted and never alarmed on. The in-session scheduler is open to the Claude
  agents by decision (2026-09-19: the bundled skills stay); this gate is the alarm on its
  effect, and it also sees a Bash loop that re-prompts the session the same way — but not one
  that never does.
- The same receipts (gate 6, since 2026-09-23, T8.5): one relay event that started more than
  one relay turn for one agent in the window — distinct `started_at`, so two receipts of one
  turn are one — is a FAIL naming the agent and the event prefix. It sees a second dispatcher
  **on this box** only; a Mac-side Desktop head answering the same mention writes no receipt
  here. A deployed `turn_rate.py` without the column is a FAIL, not a pass.

## Outputs

- **Verdict** — the last line of the run's journal is `== fleet-turn-check PASS ==` or
  `== fleet-turn-check FAIL ==` (`fleet-turn-check.sh:245`), preceded by one line per failed
  assertion naming the unit and the signal.
- **Alert** — on FAIL the unit exits non-zero, `OnFailure` starts
  `agent-alert@fleet-turn-check.service.service`, and `bin/agent_alert.sh` appends to
  `~/logs/agent-alert.log` and delivers to #ops with a receipt in
  `~/logs/delivery-receipts.jsonl` (`job = agent-alert@fleet-turn-check.service.service`).
- **State** — `~/logs/fleet-turn-check.state`, rewritten each run (`:167`); an input to the next
  run, not an artifact anyone reads.
- **Beneficiary:** Dave — the one person who can re-authenticate a fleet whose OAuth refresh
  has died, which is the failure this job exists to see.
- **Next actor:** Dave, on a FAIL alert. Nobody, on PASS.
- **Next action:** read the failed assertion lines in `journalctl -u fleet-turn-check.service`,
  then `~/.config/buzz-team/check-loaded.sh` for the named unit.
- **Benefit hypothesis:** a fleet that cannot answer is known within the hour instead of after
  four days.
- **Benefit signal:** `Unknown`. It has fired real FAILs (2026-09-11 07:00, 08:01 — the pause)
  but no outage has yet been caught by it first, so "time to detection" has one data point and
  it is the pause itself.

## Decline conditions

none — a deterministic check has nothing to decline. A run that cannot write its state file
says so and still decides (`:95`).

## Side effects

- Rewrites `~/logs/fleet-turn-check.state` (`:167`).
- On FAIL: one alert delivery and one `~/logs/agent-alert.log` line, throttled by
  `bin/agent_alert.sh`.
- Nothing else. The script never starts, stops or restarts a unit.

## Acceptance checks

Two checks, both `sweep`: the failure this job guards against is that nothing ran, or that a
FAIL went unannounced. There is no `run` vantage — the runner is not `bin/agent_propose.sh`, so
no executor sets `AGENT_RUN_STARTED_AT` for it; the timer's own `LastTriggerUSec` is the anchor.

1. **The timer fired within its cadence.** Three hours: hourly, plus 2min jitter, plus slack for
   a `Persistent=true` catch-up after a boot.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 10800 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **The last run produced a verdict, and a FAIL was announced.** A journal with no verdict
   line means the script died before deciding. A FAIL verdict whose alert never receipted means
   the OnFailure path is broken — which is the outage of 2026-08-27 one layer up.

   ```check id=verdict-present-and-fail-alerted when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   v="$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager -o cat \
          | grep -E '^== fleet-turn-check (PASS|FAIL) ==$' | tail -1)"
   [ -n "$v" ] || { echo "no verdict line since $t"; exit 1; }
   case "$v" in *PASS*) exit 0 ;; esac
   hour="$(date -u -d "@${t#@}" +%Y-%m-%dT%H)"
   sent="$(grep -F "\"job\": \"agent-alert@$UNIT.service.service\"" "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null \
             | grep -oE '"ts": "[^"]+"' | cut -d'"' -f4)"
   grep -q "^$hour" <<<"$sent" && exit 0
   since="$(grep -F "unit $UNIT.service failed at $hour" "$HOME/logs/agent-alert.log" 2>/dev/null \
              | grep -F 'notification throttled' | grep -oE 'failing since [0-9TZ:-]+' | tail -1 | cut -d' ' -f3)"
   [ -n "$since" ] || { echo "verdict was FAIL and no alert receipt followed it"; exit 1; }
   first="$(awk -v s="$since" '$0 >= s' <<<"$sent" | head -1)"
   [ -n "$first" ] || { echo "verdict was FAIL, the repeat was throttled, and the episode failing since $since never receipted an alert"; exit 1; }
   echo "throttled repeat: the episode failing since $since was alerted at $first"
   ```

## Known failure modes

- **A PASS that proves nothing.** The check asks each unit for a real turn; if the
  `buzz-agent@*` roster is empty (the fleet paused, as on 2026-09-11) there is nothing to ask
  and the verdict is FAIL, not PASS — by design. A PASS therefore always covers at least one
  unit.
- **Alert throttling hides repetition, not the first failure.** `bin/agent_alert.sh` collapses
  hourly repeats into one notification plus a daily reminder. A FAIL that persists for a day
  produces one receipt per day, and that is correct — so check 2 passes a FAIL in either of two
  shapes: an alert receipt in the same hour (the transition into failure, or the daily
  reminder), or an `agent-alert.log` line for that hour marked `notification throttled` whose
  episode (`failing since`) has a receipt at or after its start. Until 2026-09-25 it accepted
  only the first shape, contradicting this paragraph: during Augustus's Codex quota outage
  every hourly repeat after 20:00 CEST read "no alert receipt followed it" beside a real,
  delivered alert.
- **State file unwritable.** CPU deltas are skipped and said so (`:95`); the run still decides.
  Not a failure of this contract.
- **A loop slower than the limit is not seen.** Four self-scheduled turns an hour trips gate
  5; three do not. A `/loop` at 20-minute cadence runs unalarmed. The limit is a knob
  (`FLEET_UNOWNED_MAX`), and the receipts still record every fire for anyone reading the
  Control Room.
- **Receipts from before the `origin` field read as `relay` or `unknown`,** never as
  self-scheduled — claudius's 14:21Z one-shot of 2026-09-19 is under Dave's event for good.
  Receipts are not rewritten; the gate judges from the deploy onward.
- **The alert receipt match is by hour.** `delivery-receipts.jsonl` carries UTC `ts` and the
  timer stamp is epoch; the check compares the `YYYY-MM-DDTHH` prefix. A FAIL at :59 alerted at
  the next :00 reads as unalerted for one sweep. Accepted as a light-contract approximation.
