# Contract: agent-buzz-acp-update

Read on 2026-09-11 from `systemd/agent-buzz-acp-update.{service,timer}` and
`bin/buzz_acp_update.sh` (the `check` verb). A light contract (T4.4). Written while the fleet was
paused (`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that
day; the checks report that as "not loaded or never fired", which is the correct answer.

**Why it exists:** between 2026-07-31 and 2026-09-07 this box ran a `buzz-acp` twelve releases
behind upstream and nothing on the box could have said so, because Desktop on the Mac and the
CLI here are two independent installs of one release stream (`bin/buzz_acp_update.sh:4-12`).
The installed binaries carry no version string; the receipt `var/buzz-cli-install.json` is
the only honest identity they have, and every verdict re-hashes the live files before
believing it (`:32-34`, `:166-175`).

## Identity

| | |
|---|---|
| Unit | `agent-buzz-acp-update.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell, one GitHub releases call, sha256 over two binaries |
| Runner | `bin/buzz_acp_update.sh check` (deployed copy), `DELIVERY_JOB=%n` |
| Cadence | daily 07:35, `RandomizedDelaySec=5min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service`; exit 10 (behind) and exit 1 (unpinned / receipt missing / a week offline) both alert, with different text |
| Remediation owner | Dave — `apply` is a supervised install with a canary restart of the fleet (`:41-42`), and the fleet is Dave's to restart |
| Retirement condition | none — standing; retires if the box stops hosting Buzz agents |
| Contract version | 1 (2026-09-11) |

## Trigger

`agent-buzz-acp-update.timer`: `OnCalendar=*-*-* 07:35`, `RandomizedDelaySec=5min`,
`Persistent=true`.

## Inputs

- `~/agent-workforce/var/buzz-cli-install.json` — the receipt: `tag`, `installed_utc`,
  `source_asset`, `binaries.{buzz,buzz-acp}.sha256` (`:55`, `:146-160`).
- `~/.local/bin/buzz` and `~/.local/bin/buzz-acp` — hashed live on every path (`:166-175`).
- GitHub's latest `desktop-v*` release tag; unreachable is fail-soft until
  `STALE_CHECK_DAYS` (`:46-50`, `:361-372`).
- `~/agent-workforce/var/buzz-cli-check-last-ok` — epoch of the last successful upstream
  read, written on every reachable run (`:341`, `:376`).

## Outputs

- **Verdict** — exactly one of: `buzz CLI/ACP is current: <tag>` (exit 0, `:378`);
  `buzz CLI/ACP is behind: installed <tag>, upstream latest <tag>` followed by a staged
  compatibility probe of the real binary (exit 10, `:382-392`); `UNPINNED: …` or
  `no install receipt at …` (exit 1, `:345`, `:354`); `could not reach GitHub; last successful
  check was Nd ago (under 7d, not reporting)` (exit 0, `:367-368`). All in the journal.
- **State** — `buzz-cli-check-last-ok` touched on every reachable run; a staged download
  under `var/buzz-stage/<tag>/` once per new tag, never re-downloaded on the daily reminder
  (`:383-388`).
- **Beneficiary:** the five `buzz-agent@*` units, which run whatever `buzz-acp` this job
  vouches for; Dave, who otherwise reads "Desktop is current" as "the box is current".
- **Next actor:** Dave on exit 10 (`bin/buzz_acp_update.sh apply`, supervised) or exit 1
  (`adopt <tag>` once the installed release is known).
- **Next action:** read the compatibility verdict in the alert body first — a staged binary
  that fails `probe` against the unit's flags must not be applied.
- **Benefit hypothesis:** the box is never more than one day behind knowing it is behind, and
  never a week without knowing whether it knows.
- **Benefit signal:** `Unknown` as a rate. `current:` days are one journal line; the
  2026-07-31..09-07 gap is the one baseline, and it is why the exit codes are split the way
  they are.

## Decline conditions

none. The offline path exits 0 with a note for up to `STALE_CHECK_DAYS`, then exit 1 — a
blip must not page Dave; a week of silence must (`:361-372`).

## Side effects

- Network read of GitHub releases; a ~117 MB download once per new tag (`:384-385`).
- Writes under `~/agent-workforce/var/` only. Never touches `~/.local/bin` — that is `apply`,
  a human verb.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Thirty hours.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **The run reached a verdict, and the job has reached upstream within the week.** One of
   the four verdict lines since the trigger, and `buzz-cli-check-last-ok` younger than
   `STALE_CHECK_DAYS` — the second half is the promise the 2026-09-07 discovery was made to
   keep, checked here independently of the script's own fail-soft counter.

   ```check id=verdict-present-and-upstream-reached-this-week when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   $JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager -o cat \
     | grep -qE '^(buzz CLI/ACP is (current|behind)|UNPINNED:|no install receipt at|could not reach GitHub)' \
     || { echo "no currency verdict since $t"; exit 1; }
   ok="$HOME/agent-workforce/var/buzz-cli-check-last-ok"
   last="$(cat "$ok" 2>/dev/null || echo 0)"
   [ $(( ( $(date +%s) - last ) / 86400 )) -lt 7 ] || { echo "upstream not reached for $(( ( $(date +%s) - last ) / 86400 ))d"; exit 1; }
   ```

## Known failure modes

- **Behind and offline used to read as broken.** Exit 1 preempted exit 10 until the ordering
  was fixed (`:200-203`); and `set -u` once turned a cleanup into a spurious exit 1 over a
  correct "behind" (`:216-219`). Both are regression tests now; a change to `check()` that
  reorders them re-opens the wrong half of a two-part message.
- **Receipt says X, disk says Y.** Something replaced the binaries outside this tool —
  `UNPINNED`, exit 1, daily until `adopt` (`:353-357`). The job cannot infer the tag; only a
  human who knows what was installed can.
- **The daily reminder is a daily alert.** A box that is behind alerts every morning until
  `apply` or a deliberate decision; the 117 MB is downloaded once, the message is not.
- **A stale `last-ok` after a clock jump.** The file holds an epoch; a box whose clock ran
  ahead writes a future `last-ok` and reads as "reached upstream" for as long as the jump
  lasted. Light-contract approximation.
