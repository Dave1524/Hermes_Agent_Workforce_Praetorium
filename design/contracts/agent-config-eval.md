# Contract: agent-config-eval

Written 2026-09-22 alongside the unit it describes (T8.4), from `systemd/agent-config-eval.{service,timer}`,
`bin/agent_config_eval.sh` and `bin/agent_config_eval_compare.py`. A light contract (T4.4),
laid out like `fleet-eval.md`. The timer is **shipped disabled**, so every check below reads
"not loaded or never fired" until Dave enables it — which is the correct answer, not a red.

**This unit carries no `OnFailure=` and the manifest says `alerted = false` DELIBERATELY**
(`design/agents/trajan.toml`, `agent-config-eval` notes): the exit code is the product — 1
means a case scored below the baseline recorded when it was added — and `--deliver` has
already posted the scorecard to #ops. Wiring the alert path as well would announce every
regression twice, on two surfaces.

**It is the only unit on this box that spends model tokens to check the box.** Every case run
is a full `claude` child on the same claude.ai login as the five `buzz-agent@*` units and the
nine scheduled runners.

## Identity

| | |
|---|---|
| Unit | `agent-config-eval.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic wiring around a non-deterministic measurement |
| Runner | `bin/agent_config_eval.sh --self-check --deliver`, `WorkingDirectory=/tmp` |
| Cadence | weekly, Sat 08:07, `RandomizedDelaySec=90s`, `Persistent=true` |
| Alerted | **no, by design** — regression is delivered as a scorecard, exit 1 is the verdict |
| Remediation owner | whoever changed the agent config the red row points at; if nothing changed, Dave reads the row and decides whether to re-record |
| Retirement condition | none — standing |
| Contract version | 1 (2026-09-22) |

## Trigger

`agent-config-eval.timer`: `OnCalendar=Sat *-*-* 08:07:00`, `RandomizedDelaySec=90s`,
`Persistent=true`. Weekly rather than daily because the subject is agent *configuration*: a
branch that changes it is already caught by the verify gate running the same script with
`--changed-since`. What the timer adds is the class with no diff — a model rollout or a
harness change that moves behaviour while every file stays byte-identical.

Saturday and `:07` are chosen: clear of the working week and of the every-15m auto-sync
(`:00/:15/:30/:45`), `qmd-refresh` (`:20/:50`), `inbox-sync` (`:01/:31`) and `fleet-eval`
(07:07), with which it shares the ops delivery route.

## Inputs

- `~/agent-workforce/skills/<owner>/evals/*/case.yaml` — the cases, one directory each.
- `~/agent-workforce/skills/evals-baseline.json` — the recorded score per case, which is what
  "regression" is measured against. A `ConditionPathExists` on this file, so a runtime tree
  that has not been deployed does not read as a behavioural failure.
- The claude.ai login in `~/.claude/.credentials.json`, spent one full `claude` child per run
  per case.

## Outputs

- **Scorecard** — `~/logs/agent-config-eval/<STAMP>/scorecard.md`, one directory per run,
  stamped `YYYYMMDDTHHMMSSZ`, beside `results.psv` and the raw `--json` of each owner.
- **Verdict** — exit 0 "no regression", 1 with the count of FAILs, 2 for a runner error (a bad
  flag, no credential on PATH, a `TMPDIR` inside `$HOME`). **2 is never a verdict about the
  fleet**, which is why it is a distinct code.
- On regression only: one #ops delivery by `bin/deliver.sh` with subject
  `[Praetorium] Agent-config eval — regression (N)` and a receipt
  `job = agent-config-eval.service`.
- **Beneficiary:** Dave, and whoever last changed the agent configuration.
- **Next actor:** Dave reads the #ops post.
- **Next action:** open the run directory named in the scorecard's `Full run:` line and read
  the FAIL rows. A `REGRESSION` row names the case and the score it fell from; an
  `UNBASELINED` row means a case landed without `--record`; a `MISSING` row means a baselined
  case is gone from the tree.
- **Benefit hypothesis:** a config change that stops a skill firing is seen the same week,
  rather than three days after the fact and only because someone went looking at telemetry —
  which is exactly what happened to T3.3 (48 runs, zero invocations, cause already fixed).
- **Benefit signal:** `Unknown` until the timer is enabled and has run. Regressions delivered
  will be countable from receipts (`job = agent-config-eval.service`); regressions acted on
  are not recorded anywhere, the same gap every delivery on this box has.

## Decline conditions

- **Another run holds the lock.** Non-blocking `flock`; the run exits 0 having measured
  nothing, because two overlapping suites on one rate limit are a collision, not more data.
- **`--changed-since <ref>` with no watched path touched.** Exit 0, one line, no model spend.
  This is the gate's entry point and never the timer's — the timer passes no such flag,
  deliberately, because the class it exists for has no diff.

## Side effects

- Writes one run directory under `~/logs/agent-config-eval/`.
- Copies each owner's plugin to a temp tree **outside `$HOME`** and evaluates the copy. Two
  reasons, both measured: `claude plugin eval` writes `<plugin>/evals/results/`, which
  `agent-workforce-auto-sync.timer` would commit to `origin/main` within 15 minutes; and the
  eval child's cwd decides whether `~/CLAUDE.md` and the shared memory pool load into every
  run, which would make the eval measure Dave's machine instructions instead of the pointer
  descriptions under test. A `TMPDIR` inside `$HOME` is **refused (exit 2)** rather than
  warned about, because the wrong measurement still produces a number.
- Reads the skills tree; writes nothing to the vault, the inbox, or the checkout.

## Acceptance checks

Two checks, both `sweep`; the anchor is the timer's `LastTriggerUSec`.

1. **The timer fired within its cadence.** Nine days: weekly, plus jitter, plus a
   `Persistent=true` catch-up.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 777600 ] || { echo "last fired $(( age / 86400 ))d ago"; exit 1; }
   ```

2. **This run wrote a scorecard, and the negative control ran inside it.** The artifact is the
   scorecard of the run the timer just started, not the newest on disk. `--self-check` is in
   `ExecStart`, so a scorecard with no negative-control line is a run that measured the fleet
   without first proving it could still see a failure.

   ```check id=scorecard-carries-negative-control when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   root="$HOME/logs/agent-config-eval"
   card="$(find "$root" -mindepth 2 -maxdepth 2 -name scorecard.md -newermt "@${t#@}" 2>/dev/null | sort | tail -1)"
   [ -n "$card" ] && [ -s "$card" ] || { echo "no scorecard written since $t"; exit 1; }
   grep -q '^Negative control' "$card" \
     || { echo "scorecard carries no negative control line"; exit 1; }
   ```

## Known failure modes

- **Exit 1 is a verdict, not an incident — and nothing alerts on a crash either.** With no
  `OnFailure`, a run that dies before writing (no credential, rate limit, a hung child hitting
  `TimeoutStartSec`) is visible only as a missing scorecard, which is what check 2 exists to
  see. Do not wire `OnFailure` to "fix" this; it would double-announce every real regression.
- **A model rollout moves every score with no diff.** That is the class this timer exists for,
  and the response is to read the run and re-record the baseline by hand with a commit that
  says why — never to let a job bump its own pass mark.
- **Score quantisation.** At `runs: 3` a score is 0, ⅓, ⅔ or 1, so one flaky run IS a ⅓ drop.
  The tolerance defaults to `1/runs` and absorbs exactly one; two are red. If the weekly run
  proves noisy, **raise `runs`, never the tolerance** — raising the tolerance past `1/runs`
  makes the check blind to a real single-case failure at the same time.
- **A shared rate limit.** Every case is a `claude` child on the login five Buzz agents and
  nine runners already use. The Saturday slot and the non-blocking lock are the mitigation;
  a run that collides skips rather than queues, and reports exit 0 having measured nothing.
- **The suite can only see what a case asks about.** A pointer with no case is not covered,
  and the gate's `baseline-measured-dated` join proves the baseline matches the *case* set —
  not that the case set covers the *pointer* set. That join is the coverage card's job.
