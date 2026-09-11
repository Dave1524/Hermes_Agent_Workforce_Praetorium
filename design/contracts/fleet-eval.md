# Contract: fleet-eval

Read on 2026-09-11 from `systemd/fleet-eval.{service,timer}`, `bin/fleet_eval.sh` and its two
runners `bin/fleet_eval_behaviour.py` / `bin/fleet_eval_grounding.py` (by header only). A light
contract (T4.4). Written while the fleet was paused (`~/OUTBOX/fleet-pause-2026-09-11.md`), so
the timer read `LastTriggerUSec` empty that day; the checks report that as "not loaded or never
fired", which is the correct answer.

**This unit carries no `OnFailure=` and the manifest says `alerted = false` DELIBERATELY**
(`design/agents/trajan.toml`, `fleet-eval` notes; `bin/fleet_eval.sh:22-24`): the exit code is
the product — 1 means "something moved backwards" — and a regression is a report to read, not
an incident. `--deliver` posts the scorecard to #ops on regression; wiring `OnFailure` as well
would announce every regression twice.

## Identity

| | |
|---|---|
| Unit | `fleet-eval.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic; the grounding tier queries qmd, no LLM |
| Runner | `bin/fleet_eval.sh --deliver`, `WorkingDirectory=/home/dave`, `QMD_LLAMA_GPU=vulkan` |
| Cadence | daily 07:07, `RandomizedDelaySec=90s`, `Persistent=true` |
| Alerted | **no, by design** — regression is delivered as a scorecard, exit 1 is the verdict |
| Remediation owner | the owner of whichever row regressed: a tier-1 delivery-conformance row names the producing unit's owner (see `design/agents/*.toml`); a tier-2 grounding row is the vault (Mac-side publish) |
| Retirement condition | none — standing |
| Contract version | 1 (2026-09-11) |

## Trigger

`fleet-eval.timer`: `OnCalendar=*-*-* 07:07:00`, `RandomizedDelaySec=90s`, `Persistent=true`.
Runs after the morning-report pair so last night's deliveries are in the receipts it grades.

## Inputs

- `~/logs/delivery-receipts.jsonl` — tier 1 grades receipts against `bin/buzz_routes.env`
  (kind / channel / notify per route).
- qmd over the vault mirror — tier 2 asks the questions the fleet previously got wrong.
- `~/logs/fleet-eval/history.psv` — the previous rows, which is what "regression" is measured
  against (`bin/fleet_eval.sh:30`).

## Outputs

- **Scorecard** — `~/logs/fleet-eval/<STAMP>/scorecard.md` (`:62`, `:65`), one directory per
  run, stamped `YYYYMMDDTHHMMSSZ`.
- **History spine** — `~/logs/fleet-eval/history.psv`, `run_ts|tier|check|status|value`, one
  row per check per run, appended (`:100-104`).
- **Verdict** — exit 0 "no regression", exit 1 with the count of FAILs (`:107`, `:142`); on
  regression the scorecard is delivered to #ops by `bin/deliver.sh` with subject
  `[Praetorium] Fleet eval — regression (N)` (`:136`) and a receipt `job = fleet-eval.service`.
- **Beneficiary:** Dave, and the owner of the regressed row.
- **Next actor:** Dave reads the #ops post; the named owner fixes the row.
- **Next action:** open the run directory named in the journal's `History:` line and read the
  FAIL rows; for a tier-1 row, fix the producer's delivery wiring; for tier-2, republish the
  vault or fix the question.
- **Benefit hypothesis:** a behaviour or grounding regression is seen the morning after it
  lands instead of when a human notices the wrong channel weeks later (the 2026-08-25 loss of
  twelve research runs is the reference case).
- **Benefit signal:** `Unknown`. Regressions delivered: countable from receipts
  (`job = fleet-eval.service`, 10 on 2026-09-11); regressions *acted on* are not recorded
  anywhere, so the signal cannot yet be computed.

## Decline conditions

none. `--skip-probes` / `--no-coverage` narrow a run when passed by hand; the timer passes
neither.

## Side effects

- Writes one run directory under `~/logs/fleet-eval/` and appends to `history.psv`.
- On regression only: one #ops delivery and one receipt.
- Reads qmd; writes nothing to the vault or the inbox.

## Acceptance checks

Two checks, both `sweep`; the anchor is the timer's `LastTriggerUSec`.

1. **The timer fired within its cadence.** Thirty hours: daily plus jitter plus a
   `Persistent=true` catch-up.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **This run wrote a scorecard and a history row.** The artifact is the scorecard of the run
   the timer just started, not the newest scorecard on disk; the history spine must have grown
   at the same time or the run died between the two writes.

   ```check id=scorecard-and-history-are-this-runs when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   root="$HOME/logs/fleet-eval"
   card="$(find "$root" -mindepth 2 -maxdepth 2 -name scorecard.md -newermt "@${t#@}" 2>/dev/null | sort | tail -1)"
   [ -n "$card" ] && [ -s "$card" ] || { echo "no scorecard written since $t"; exit 1; }
   [ -n "$(find "$root" -maxdepth 1 -name history.psv -newermt "@${t#@}" 2>/dev/null)" ] \
     || { echo "history.psv not appended since $t"; exit 1; }
   ```

## Known failure modes

- **Exit 1 is a verdict, not an incident — and nothing alerts on a crash either.** With no
  `OnFailure`, a run that dies before writing (qmd down, python traceback) is only visible as a
  missing scorecard, which is what check 2 exists to see. Do not wire `OnFailure` to "fix"
  this; it would double-announce every real regression.
- **A regression posted to #ops that nobody reads.** The receipt says delivered; the read is
  not recorded. Same class as every delivery on this box.
- **The scorecard says `unknown` for cost, always.** Hermes token accounting is unreliable
  (#4404/#20741); the OpenRouter dashboard is the source of truth. Not a defect of this run.
- **First run after a vault rewrite grades against a moved target.** Tier 2's questions live
  in the runner; a vault republish that renames a document reads as a grounding regression
  until the question is updated. Remediation owner is the vault side, as the Identity row says.
