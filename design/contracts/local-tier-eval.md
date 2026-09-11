# Contract: local-tier-eval

Read on 2026-09-11 from `systemd/local-tier-eval.{service,timer}` and `bin/local_tier_eval.sh`.
A light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

## Identity

| | |
|---|---|
| Unit | `local-tier-eval.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic harness around on-box Ollama models; no OpenRouter egress |
| Runner | `bin/local_tier_eval.sh` (`hermes` at `~/.local/bin/hermes`, per-task timeout 6min) |
| Cadence | six times daily at 02:17, 08:17, 11:17, 14:17, 17:17, 20:17; `Persistent=false` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` (wired 2026-09-01, D2) |
| Remediation owner | Dave — a failed capability row is a model-choice decision, not a fix |
| Retirement condition | none — standing; retire when the local tier is dropped from the routing table, at which point there is nothing to score |
| Contract version | 1 (2026-09-11) |

## Trigger

`local-tier-eval.timer`: `OnCalendar=*-*-* 02,08,11,14,17,20:17:00`, `Persistent=false`. A
missed slot is skipped, not caught up: the score is of the model at that hour, and a stale
catch-up would score the wrong hour.

## Inputs

- The on-box Ollama models the script iterates.
- Task prompts under the runner's `PROMPTS` directory (`t1_extract`, `t2_classify`,
  `t3_format`, `t4_artifact`), with inputs the run generates from live `systemctl` output.
- `~/logs/overnight/morning-report-*.md`, newest, as the t2 classification corpus
  (`bin/local_tier_eval.sh:93`); absent ⇒ the task is skipped and says so.

## Outputs

- **Scorecard** — `~/logs/local-tier-eval/<run_stamp>/scorecard.md` (`:39-41`), one directory
  per run (per-run, not per-day: a per-day dir would let each run overwrite the last, `:36`).
- **History spine** — `~/logs/local-tier-eval/history.psv`,
  `run_ts|task|model|status|score|secs`, appended per task per run (`:167-170`).
- **Alert** — on a non-zero exit, `agent-alert@local-tier-eval.service.service` delivers to
  #ops with the failed unit named.
- **Beneficiary:** Dave, deciding what the local tier may be trusted with.
- **Next actor:** Dave.
- **Next action:** read `history.psv` for the trend of the failing task; a task that fails
  consistently means that capability stays on the remote tier.
- **Benefit hypothesis:** the reason the local tier cannot run a job is named per capability
  (t1-t4) rather than discovered as "it didn't work" during a real run.
- **Benefit signal:** `Unknown`. No routing decision has yet cited a `history.psv` row; until
  one does, the artifact has a reader in principle and none on record.

## Decline conditions

none. A task whose input is missing is recorded as skipped in the scorecard, not declined.

## Side effects

- Writes one run directory and appends to `history.psv`.
- Loads models into Ollama's GPU memory; on this box that is what `ttm-pool-drain` cleans up
  after (see `design/contracts/ttm-pool-drain.md`).
- No network egress, no vault or inbox write.

## Acceptance checks

Two checks, both `sweep`. The anchor is the timer's `LastTriggerUSec`.

1. **The timer fired within its cadence.** Seven hours: the longest gap in the schedule is
   20:17 → 02:17 (six hours), plus slack. `Persistent=false`, so no catch-up allowance.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 25200 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **This run wrote a scorecard and a history row.**

   ```check id=scorecard-and-history-are-this-runs when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   root="$HOME/logs/local-tier-eval"
   card="$(find "$root" -mindepth 2 -maxdepth 2 -name scorecard.md -newermt "@${t#@}" 2>/dev/null | sort | tail -1)"
   [ -n "$card" ] && [ -s "$card" ] || { echo "no scorecard written since $t"; exit 1; }
   [ -n "$(find "$root" -maxdepth 1 -name history.psv -newermt "@${t#@}" 2>/dev/null)" ] \
     || { echo "history.psv not appended since $t"; exit 1; }
   ```

## Known failure modes

- **A run that overlaps the morning agent window.** 08:17 sits inside the daily-rhythm jobs;
  a model load then competes for GPU memory with nothing (the fleet is remote-model), but the
  6min per-task timeout bounds the damage if Ollama is slow.
- **The prompt corpus is a morning report that may not exist.** t2 is skipped and recorded as
  such when `~/logs/overnight/morning-report-*.md` is absent (`:93`); a week of skipped t2 rows
  is a morning-report problem, not a local-tier one.
- **A difficulty change reads as a model change.** `history.psv` scores either side of a
  prompt edit under the same task name (`:54`); compare within a prompt version.
- **Six alerts a day if Ollama is down.** Every slot fails; `bin/agent_alert.sh` throttles to
  one notification plus a daily reminder, so the alert log grows and the channel does not.
