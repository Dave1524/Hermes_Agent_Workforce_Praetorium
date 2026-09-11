# Contract: qmd-refresh

Read on 2026-09-11 from `systemd/qmd-refresh.{service,timer}`, `bin/vault_sync_guard.sh` and
the unit's journal. A light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`); **this timer was deliberately kept running** through the
pause with `qmd-mcp`, so it is the one platform job whose sweep checks were live that day.

The guard exists because of a four-day frozen mirror (2026-07-23..27): a rejected pull was
masked as an offline blip, the unit exited 0, and qmd re-indexed a stale tree while every
health check read green (`bin/vault_sync_guard.sh:3-9`). A pull the remote refused and a pull
the network prevented exit differently now, and that difference is this contract.

## Identity

| | |
|---|---|
| Unit | `qmd-refresh.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic: git fast-forward guard, then `qmd update && qmd embed` |
| Runner | `bin/vault_sync_guard.sh sync`, then `/bin/bash -lc 'qmd update && qmd embed --timeout 20'` |
| Cadence | `OnBootSec=5min`, then every 30 minutes (`OnUnitActiveSec=30min`), `RandomizedDelaySec=2min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` (11 alert receipts on record, 2026-09-11) |
| Remediation owner | Dave — a REJECTED sync names local tracked edits in the mirror that only a human should route; a RESYNC is automatic |
| Retirement condition | none — standing. **Note:** at vault cutover (`~/vault` → the canonical clone, per `~/CLAUDE.md`) the mirror this syncs is replaced; the job survives if it is repointed, and retires if qmd indexes the canonical clone directly. Not a promise either way |
| Contract version | 1 (2026-09-11) |

## Trigger

`qmd-refresh.timer`: monotonic — `OnBootSec=5min`, `OnUnitActiveSec=30min`,
`RandomizedDelaySec=2min`, `Persistent=true`.

## Inputs

- `~/vault` (a symlink; the guard resolves it) and its `origin` — the box-safe mirror
  published from the Mac with `--force-with-lease`, so upstream legitimately rewrites history
  (`:12-19`).
- `qmd`'s config at `~/.config/qmd/index.yml` and index at `~/.cache/qmd/`.

## Outputs

- **State change** — the mirror is fast-forwarded (`OK: fast-forwarded to <sha>`), reset onto
  a rewritten upstream (`RESYNC: … mirror reset to <sha>`, old tip parked at a recovery ref),
  or left in place (`OK: already current`, `SOFT: cannot reach origin`); then the qmd index is
  updated and embedded (`Indexed: N new, N updated, N unchanged, N removed`). Every outcome is
  one journal line naming the before and after sha (`:90`, `:97`, `:104`, `:109`).
- **Verdict** — exit 1 with `FAIL: sync onto <ref> REJECTED — local tracked changes` and the
  file list (`:80`); `OnFailure` alerts with the unit name.
- **Beneficiary:** every qmd consumer — the five `buzz-agent@*` units, the scheduled jobs that
  read the vault, and both interactive CLIs.
- **Next actor:** nobody on OK/RESYNC; Dave on FAIL (route the local edit, then the next tick
  converges).
- **Next action:** on FAIL, `git -C ~/vault status` and move or discard the named tracked
  changes — never commit them to the mirror.
- **Benefit hypothesis:** no consumer answers from a tree more than ~32 minutes behind the
  Mac's publish, and a frozen mirror is an alert within one tick instead of a four-day silence.
- **Benefit signal:** `Unknown` as a rate; the one baseline is the 2026-07-27 wedge (four days
  frozen, zero alerts), which the guard's exit codes were written against.

## Decline conditions

none. `SOFT: cannot reach origin` exits 0 and leaves the tree untouched — an outage, not a
decline, and `qmd update` still runs over the unchanged tree.

## Side effects

- Git fast-forward or hard reset of `~/vault` (never a commit, never a push).
- Rewrites the qmd index and embeddings under `~/.cache/qmd/`.
- `qmd-mcp` serves the new index live; its own start-time blurb does not update
  (`~/CLAUDE.md` § qmd).

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence.** Sixty-five minutes: two intervals plus jitter.
   Monotonic timers still expose `LastTriggerUSec`.

   ```check id=timer-fired-within-window when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 3900 ] || { echo "last fired $(( age / 60 ))min ago"; exit 1; }
   ```

2. **The last run converged, or said why it could not.** The journal since the trigger must
   carry a guard verdict line and a qmd `Indexed:` line; a `FAIL:` verdict is a kept contract
   only if the unit exited non-zero (so the alert fired) — a FAIL that exited 0 is the
   2026-07-27 defect returned.

   ```check id=synced-and-indexed-or-alerted when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 77 ;; esac
   j="$($JOURNALCTL --unit "$UNIT.service" --since "$t" --no-pager -o cat)"
   v="$(printf '%s\n' "$j" | grep -E 'vault_sync_guard\[sync\]: (OK|RESYNC|SOFT|FAIL):' | tail -1)"
   [ -n "$v" ] || { echo "no guard verdict since $t"; exit 1; }
   case "$v" in *FAIL:*) ;; *) v=""; esac
   rc="$($SYSTEMCTL show "$UNIT.service" -p ExecMainStatus --value)"
   [ -z "$v" ] || { [ "${rc:-0}" != 0 ] && exit 0; echo "guard FAILed and the unit exited 0"; exit 1; }
   printf '%s\n' "$j" | grep -q '^Indexed: ' || { echo "synced but qmd did not report an index pass"; exit 1; }
   ```

## Known failure modes

- **A rejected pull read as offline.** The defect the guard replaced; `SOFT` and `FAIL` are
  now different exits, and check 2 refuses a FAIL that did not fail the unit.
- **Upstream rewritten while the tree is dirty.** RESYNC needs a clean tree; a local tracked
  edit blocks it and the mirror freezes with an alert per tick until routed. Correct: the
  local edit is the one thing upstream does not have (`:17-19`).
- **`qmd embed --timeout 20` times out on a large publish.** The index is updated, embeddings
  lag one tick; `qmd-mcp` answers lexically in the meantime. Not alerted, by the `&&` — a
  failed embed fails the unit.
- **The blurb qmd-mcp shows is a start-time snapshot.** This job refreshes the index, not the
  daemon's self-description; a document count in the MCP banner is stale by design
  (`~/CLAUDE.md` § qmd).
