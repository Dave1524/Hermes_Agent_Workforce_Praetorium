# Contract: agent-drift-check

Read on 2026-09-11 from `systemd/agent-drift-check.{service,timer}` and
`bin/check_deploy_drift.sh`. A light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

**The check reports; it never converges** (`bin/check_deploy_drift.sh:4-7`). No writes to
`/etc`, no `bin/deploy`, no `systemctl`, no deletion in any tree. Its exit code and its output
are the whole product, and this contract promises exactly those two things.

The same script is the hard-fail step of `bin/verify.sh`. The two callers ask different
questions of it — the gate asks "may this commit land" and this job asks "is the box still
running what `main` says" — and a green gate at commit time is no evidence about the box at
05:40 tomorrow, which is why both exist.

## Identity

| | |
|---|---|
| Unit | `agent-drift-check.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell (`comm` over sorted `sha256sum` listings) |
| Runner | `bin/check_deploy_drift.sh` from the SOURCE checkout (`ExecStart=/home/dave/dev/agent-workforce/bin/…`), `DELIVERY_JOB=%n` |
| Cadence | daily 05:40, `RandomizedDelaySec=3min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service`; a finding is exit 1, so a finding is an alert |
| Remediation owner | trajan for a tree the box can write (`bin/deploy`, `~/agent-workforce/`, `~/.config/systemd/user/`); Dave for `/etc/systemd/system/`, which needs sudo (`:6-7`) |
| Retirement condition | none — standing; it retires with the source/deployed split itself |
| Contract version | 1 (2026-09-11) |

## Trigger

`agent-drift-check.timer`: `OnCalendar=*-*-* 05:40`, `RandomizedDelaySec=3min`,
`Persistent=true`.

## Inputs

- The source trees under `~/dev/agent-workforce/` (`bin/`, `systemd/`, `systemd/user/`,
  `buzz-team/`, …) and their deployed counterparts: `~/agent-workforce/`, `/etc/systemd/system/`,
  `~/.config/systemd/user/`, `~/.config/buzz-team/`.
- `design/deploy-exclusions.toml` — the declared box-only files, content-pinned by sha256
  (`:284-307`); a pinned exclusion whose subject is gone is itself a finding (`:428-436`).
- `design/agents/*.toml` — ownership only, so the alert can name an owner.

## Outputs

- **Verdict line** — the last journal line is `drift: clean` or `drift: N finding(s)`
  (`:645-650`), each finding printed above it as `DRIFT [<kind>] <detail>` (`:147`); exit is
  `findings > 0`. A `SKIP:` line and exit 0 when no deployed tree exists at all (`:167-172`)
  — CI, never this box.
- **Alert** — on exit 1, `agent-alert@agent-drift-check.service` delivers the unit name and
  the journal tail; the findings are in it.
- **Beneficiary:** whoever next runs a unit believing it runs the code in `main` — every
  agent on the box, and every interactive session that reasons from the repo.
- **Next actor:** trajan on a writable tree; Dave on `/etc`.
- **Next action:** `bin/check_deploy_drift.sh` by hand to see the finding, then `bin/deploy`
  (or `sudo cp` + `daemon-reload` for `/etc`), or an entry in `deploy-exclusions.toml` if the
  box-only file is deliberate.
- **Benefit hypothesis:** the box never runs a unit or script that `main` does not describe
  for longer than a day without someone being told.
- **Benefit signal:** `Unknown` as a rate. Findings are receipted as alerts; "clean" days are
  one journal line and nothing else.

## Decline conditions

none. Exit 2 is a usage or precondition error (`:114-139`), distinct from a finding, and
alerts the same way.

## Side effects

- None on disk. Read-only over every tree it compares (`:4-5`).
- One alert per day with findings; the throttle in `agent_alert.sh` does not apply to a daily
  job, so a standing finding is a daily message until resolved. That is the intended pressure.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Thirty hours.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **The run reached a verdict, and a verdict with findings was alerted.** The journal since
   the trigger carries `drift: clean` or `drift: N finding(s)`; on findings, an alert receipt
   for this unit dated the trigger's UTC day must exist. A `SKIP:` on this box is a finding
   about the box (a deployed tree vanished), not a pass.

   ```check id=verdict-present-and-findings-alerted when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   j="$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager -o cat)"
   v="$(printf '%s\n' "$j" | grep -E '^drift: (clean|[0-9]+ finding)' | tail -1)"
   [ -n "$v" ] || { printf '%s\n' "$j" | grep -q '^SKIP:' && echo "the check SKIPped: a deployed tree is missing on this box" || echo "no drift verdict since $t"; exit 1; }
   case "$v" in "drift: clean"*) exit 0 ;; esac
   day="$(date -u -d "@${t#@}" +%Y-%m-%d)"
   grep -F "\"job\": \"agent-alert@$UNIT.service.service\"" "$HOME/logs/delivery-receipts.jsonl" 2>/dev/null \
     | grep -q "\"ts\": \"$day" || { echo "$v — and no alert receipt dated $day"; exit 1; }
   ```

## Known failure modes

- **A finding that nobody resolves is a daily alert forever.** By design; the fix is to
  resolve it or declare it in `deploy-exclusions.toml` with its hash, never to mute the job.
- **`/etc` drift needs a human.** The box cannot write it (`:6-7`); an alert naming an
  `/etc/systemd/system/` finding is a task for Dave, and stays red until then.
- **Runs from the SOURCE checkout.** If `main` is mid-edit at 05:40 the comparison is against
  the edit, not the last commit — a source-vs-deployed finding that `auto-sync` will publish
  fifteen minutes later anyway. Work on a branch (see `agent-workforce-auto-sync.md`).
- **Exit 2 and exit 1 alert identically.** A usage error (`:114-139`) reads like drift in the
  alert subject; the journal tail in the alert body says which.
