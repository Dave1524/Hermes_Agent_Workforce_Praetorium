# Contract: agent-workforce-auto-sync

Read on 2026-09-11 from `systemd/agent-workforce-auto-sync.{service,timer}` and `bin/auto-sync`.
A light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

**This job commits and pushes whatever is in the working tree of `~/dev/agent-workforce` on
`main`, every fifteen minutes** (`bin/auto-sync:36`, `git add -A`). That is its purpose and its
hazard in one line: an interactive session that leaves half-finished work on `main` has it
published under an `Auto-sync:` subject within a quarter of an hour. Work on a branch; the job
refuses every branch but `main` (`:12-14`).

## Identity

| | |
|---|---|
| Unit | `agent-workforce-auto-sync.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic git |
| Runner | `bin/auto-sync` (`WorkingDirectory=/home/dave/dev/agent-workforce`, the SOURCE checkout — the one repo on this list whose runner is its own subject) |
| Cadence | every 15 minutes (`OnCalendar=*:0/15`), `RandomizedDelaySec=2min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` (5 alert receipts on record, 2026-09-11) |
| Remediation owner | Dave — every failure path is a repo state only a human should resolve: wrong branch, non-fast-forward, staged gitlinks |
| Retirement condition | none — standing; ends when the source repo stops being edited on this box |
| Contract version | 1 (2026-09-11) |

## Trigger

`agent-workforce-auto-sync.timer`: `OnCalendar=*:0/15`, `RandomizedDelaySec=2min`,
`Persistent=true`.

## Inputs

- The working tree and index of `~/dev/agent-workforce` on `main`.
- `origin` over `~/.ssh/id_agent_workforce` (mapped by `~/.ssh/config`; never read here).

## Outputs

- **State change** — `main` fast-forwarded from origin, then every pending path committed
  (`Auto-sync: <UTC>`) and pushed. A clean tree is a no-op.
- **Verdict line** — one journal line per run, `auto-sync: working tree clean. Nothing to do.`
  (`:41`) or `auto-sync: pushed main at <short sha>` (`:79`); the refusals (`not on main`,
  `could not fast-forward`, `REFUSING to sync — nested repositories staged as gitlinks`) go to
  stderr and exit 1 (`:13-20`, `:67-72`).
- **Beneficiary:** the deployed tree and the Mac — both consume `origin/main`, which this keeps
  within fifteen minutes of the box's edits.
- **Next actor:** nobody on OK; Dave on a refusal.
- **Next action:** on `not on main`, finish and merge the branch (the refusal is correct, not a
  fault); on `could not fast-forward`, rebase by hand; on gitlinks, add the nested repo to
  `.git/info/exclude` (`:69-71`).
- **Benefit hypothesis:** no edit made on this box is ever unpublished for longer than a
  quarter of an hour, and nothing is ever force-pushed to get there.
- **Benefit signal:** `Unknown`. Pushes are visible in `git log origin/main` as `Auto-sync:`
  commits; how often a Mac session found `origin/main` stale is not recorded.

## Decline conditions

none. A refusal (exit 1) is a failure by design, so that the alert says *which* repo state needs
a human (`:12-20`, `:62-72`).

## Side effects

- Commits with `git add -A` — honours `.gitignore` and `.git/info/exclude`, nothing else
  (`:32-34`). A file the deny-list withholds from agents is not withheld from this job; it is
  kept out by never being written into the repo.
- Push to `origin main`. Never `--force`, never a branch.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Forty-five minutes: three ticks.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 2700 ] || { echo "last fired $(( age / 60 ))min ago"; exit 1; }
   ```

2. **The last run gave a verdict, and the tree it left is on `main` and not behind origin.**
   A verdict line since the trigger proves the run reached its end; `main` behind `origin/main`
   after a run says the fast-forward step is being skipped or failing silently.

   ```check id=verdict-present-and-main-in-sync when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   $JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager -o cat \
     | grep -qE '^auto-sync: (working tree clean\. Nothing to do\.|pushed main at [0-9a-f]+|not on main|could not fast-forward|REFUSING to sync)' \
     || { echo "no auto-sync verdict since $t"; exit 1; }
   repo="$HOME/dev/agent-workforce"
   [ "$(git -C "$repo" rev-parse --abbrev-ref HEAD 2>/dev/null)" = main ] || { echo "source checkout is not on main (the job refuses until it is)"; exit 1; }
   [ "$(git -C "$repo" rev-list --count main..origin/main 2>/dev/null || echo 0)" -eq 0 ] \
     || { echo "main is behind origin/main after a run"; exit 1; }
   ```

## Known failure modes

- **The job publishes work in progress.** Named at the top. A session on `main` that wants
  to hold uncommitted work must move to a branch first; there is no "pause" short of
  disabling the timer, and that is what the 2026-09-11 fleet pause did.
- **New-only trees looked clean until 2026-09-03.** `git diff` misses untracked files;
  `git status --porcelain` is now the test (`:23-34`, W16). Do not "simplify" it back.
- **A nested checkout becomes a gitlink.** A worktree or stray clone under the repo would be
  committed as a submodule pointer with no `.gitmodules`; the job refuses and names the path
  (`:60-72`).
- **Offline.** `git fetch` fails, `set -e` exits 1, alert. The next tick retries; nothing is
  lost, and the tree is untouched.
