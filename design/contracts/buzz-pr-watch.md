# Contract: buzz-pr-watch

Read on 2026-09-11 from `~/.config/systemd/user/buzz-pr-watch.{service,timer}` (backported into
`systemd/user/` 2026-09-02) and `~/.local/bin/buzz-pr-watch`. A light contract (T4.4). Written
while the fleet was paused (`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read
`LastTriggerUSec` empty that day; the checks report that as "not loaded or never fired", which is
the correct answer.

**User scope.** This is the one `--user` unit on Trajan's list; `SYSTEMCTL` resolves to
`systemctl --user` under the executor and the checks below are written for that. Do not debug it
with `sudo` (`design/agents/trajan.toml`, notes).

**It watches one pull request and retires itself.** block/buzz#3816 (Desktop `@`-mention
autocomplete fix) was still `open` on 2026-09-11. When it closes, the script announces once,
writes a stamp, disables its own timer, and from then on every run exits 0 at line 33 having
done nothing. The manifest calls it `standing` because its cadence is open-ended, and warns
that no status transition will announce the moment it becomes a job with nothing to watch. This
contract is that announcement: **check 2 fails the day the stamp exists**, with the instruction
to move the entry to `spent`.

## Identity

| | |
|---|---|
| Unit | `buzz-pr-watch.service` / `.timer` (**user scope**) |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic Python, one unauthenticated GitHub API call |
| Runner | `~/.local/bin/buzz-pr-watch` (not in this repo; `suite_exempt` in the manifest) |
| Cadence | daily 09:23, `RandomizedDelaySec=20m`, `Persistent=true` |
| Alerted | no — no `OnFailure` on the user unit |
| Remediation owner | Dave |
| Retirement condition | **decidable**: `~/.local/state/buzz-pr-watch/3816.announced` exists (`buzz-pr-watch:15`, `:47-48`). Then the timer is already disabled by the script itself (`:49`) and the manifest entry moves to `spent` |
| Contract version | 1 (2026-09-11) |

## Trigger

`buzz-pr-watch.timer` (user): `OnCalendar=*-*-* 09:23`, `RandomizedDelaySec=20m`,
`Persistent=true`.

## Inputs

- `https://api.github.com/repos/block/buzz/pulls/3816`, unauthenticated (`:4-5`, `:14`).
- The stamp file, whose existence short-circuits everything (`:33-34`).

## Outputs

- **Nothing, daily, while the PR is open** (`:40-41`). No log line, no file; the journal shows
  only systemd's start/finish lines. Silence is correct and undistinguishable from a run that
  never polled — accepted for a one-subject watch with no alert.
- **Once, on close** — a message via `hermes send --to discord` (`:23-29`) naming the verdict
  (`MERGED` / `CLOSED WITHOUT MERGE`), the PR and the unpark instructions (`:16-20`); then the
  stamp `~/.local/state/buzz-pr-watch/3816.announced` holding `<verdict> <timestamp>`; then
  `systemctl --user disable --now buzz-pr-watch.timer`.
- **Beneficiary:** Dave, who parked the `@`-mention question on this PR
  (`~/CLAUDE.md` § Addressing an agent).
- **Next actor:** Dave, once.
- **Next action:** update Buzz Desktop, type `@Marcus-Box`, confirm the sent event carries a
  non-empty `p_tag` (`:18-19`); then move this manifest entry to `spent`.
- **Benefit hypothesis:** the parked question is unparked on the day it can be, not weeks
  later when someone remembers it.
- **Benefit signal:** `Unknown` — a one-shot outcome. Either the announcement lands and the
  stamp exists, or it does not.

## Decline conditions

none.

## Side effects

- One outbound message, once, to Hermes' Discord home channel — **outside the delivery
  adapters, so no receipt will record it** (`~/logs/delivery-receipts.jsonl` never sees it).
- Writes one stamp file; disables its own timer.

## Acceptance checks

Two checks, both `sweep`. Under the executor `$SYSTEMCTL` is `systemctl --user` for this unit
(manifest `scope = "user"`).

1. **The timer fired within its cadence — until it retired itself.** With the stamp present the
   timer is disabled by design, so this check answers `n/a` rather than red; check 2 then
   carries the message.

   ```check id=timer-fired-within-window when=sweep
   [ ! -e "$HOME/.local/state/buzz-pr-watch/3816.announced" ] || { echo "retired: stamp exists"; exit 77; }
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   ```

2. **The retirement condition has not been met — or, if it has, the manifest still says
   `standing`.** This is the check the manifest note asked for: the day the stamp appears,
   this goes red once with the instruction, and stays red until the entry is moved.

   ```check id=retire-when-announced when=sweep
   s="$HOME/.local/state/buzz-pr-watch/3816.announced"
   [ -e "$s" ] || exit 0
   echo "retire: block/buzz#3816 closed ($(head -1 "$s")) and was announced — move this entry to spent in design/agents/trajan.toml"
   exit 1
   ```

## Known failure modes

- **The announce path has never run.** `hermes send --to discord` resolves to Hermes' home
  channel (`hermes send --list` on 2026-09-11 shows `#praetorium-main-chat`), which is not the
  fleet's delivery route and leaves no receipt. If `hermes send` raises, `check=True` (`:26`)
  aborts the run **before the stamp is written** (`:47-48`), the unit fails with no
  `OnFailure`, and the script retries the announce every morning and never retires. Check 2
  cannot see that; the journal can (`journalctl --user -u buzz-pr-watch.service`).
- **GitHub unreachable.** `urlopen` raises, the unit fails silently (no alert), tomorrow
  retries. A week of that is a week of not knowing; nothing counts it.
- **The stamp is written after the announce.** Correct order for "announce once", wrong order
  for "never announce twice on a partial failure": a crash between `:45` and `:48` re-announces
  tomorrow. One duplicate message, at worst.
