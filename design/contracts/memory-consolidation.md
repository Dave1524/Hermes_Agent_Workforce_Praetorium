# Contract: memory-consolidation

Read on 2026-09-11 from `systemd/memory-consolidation.{service,timer}` and
`bin/consolidate_memory.sh`. A light contract (T4.4). Written while the fleet was paused
(`~/OUTBOX/fleet-pause-2026-09-11.md`), so the timer read `LastTriggerUSec` empty that day; the
checks report that as "not loaded or never fired", which is the correct answer.

**This job prunes Hermes-native memory stores, and the Hermes timer fleet is mostly retired.**
The manifest calls it a dead limb. Measured 2026-09-11: four stores under
`~/.hermes/profiles/*/memories/MEMORY.md`; trajan's last written 2026-07-20, marcus's
2026-09-09, augustus's and claudius's the same day as the reading. So two stores are still
written by something and two are not; the retirement condition below is written to be
measured, not remembered.

## Identity

| | |
|---|---|
| Unit | `memory-consolidation.service` / `.timer` |
| Owner | **trajan** (`design/agents/trajan.toml`) |
| Surface | platform — deterministic shell; no LLM, no network (`bin/consolidate_memory.sh:3`) |
| Runner | `bin/consolidate_memory.sh` |
| Cadence | daily 03:30, `RandomizedDelaySec=5min`, `Persistent=true` |
| Alerted | yes — `OnFailure=agent-alert@%n.service` (wired 2026-09-01, D2) |
| Remediation owner | trajan (the script) for a failed run; Dave for the retirement decision |
| Retirement condition | **no store under `~/.hermes/profiles/*/memories/MEMORY.md` modified for 30 days** — nothing writes what this prunes. Check 2 measures it and goes red when met, so the sweep says "retire" rather than the entry saying "standing" forever |
| Contract version | 1 (2026-09-11) |

## Trigger

`memory-consolidation.timer`: `OnCalendar=*-*-* 03:30`, `RandomizedDelaySec=5min`,
`Persistent=true`.

## Inputs

- Every `$PROFILES_ROOT/*/memories/MEMORY.md` (`bin/consolidate_memory.sh:20`, `:149`), read
  under a `flock` on `MEMORY.md.lock` (`:47-48`); a busy lock is a logged no-op, not a failure.
- Policy constants `MEM_MAX_ENTRIES` / `MEM_MAX_CHARS` (exact-duplicate dedup, then FIFO cap).

## Outputs

- **State change** — each store rewritten only when dedup or the cap changes it, with the
  before preserved beside it as `MEMORY.md.bak.consolidate.<ts>` (`:125`) and the after
  written via temp file + move (`:126-127`). Unchanged stores are left untouched.
- **Receipt** — one line per profile per run in `~/agent-workforce/logs/consolidate_memory.log`
  (`:28`): `<ISO ts> consolidate_memory: [<profile>] consolidated: <before> -> <after> entries, <bytes> bytes (cap …)`
  on a change (`:138`), or `no-op: <reason>` when nothing changed. That line is the
  before/after evidence the T4.4 mapping asks for; a bare "ran" is never written.
- **Beneficiary:** the Hermes profiles still being written (augustus, claudius on 2026-09-11)
  — a store that grows without bound is injected whole into every turn.
- **Next actor:** nobody on a normal night; Dave when check 2 says the retirement condition is
  met.
- **Next action:** on retirement, move the entry to `status = "spent"` and disable the timer.
- **Benefit hypothesis:** bounded per-turn memory cost for the Hermes runtime.
- **Benefit signal:** `Unknown`. The log records what was pruned; whether any Hermes turn was
  cheaper for it is not measured anywhere.

## Decline conditions

none. Every early-out (`lock busy`, `no parseable entries`, `already bounded`, backup failed)
exits 0 and logs its reason (`:47-127`); the store is preserved on every path.

## Side effects

- Rewrites `MEMORY.md` files and leaves `.bak.consolidate.<ts>` copies beside them; nothing
  deletes the backups.
- Appends to `~/agent-workforce/logs/consolidate_memory.log`.

## Acceptance checks

Two checks, both `sweep`.

1. **The timer fired within its cadence and every profile got a receipt line.** Thirty hours.
   The log line carries the profile name, so "ran" and "ran for whom" are the same fact.

   ```check id=timer-fired-and-receipted when=sweep
   t="$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)"
   case "$t" in @*) ;; *) echo "the timer is not loaded or has never fired"; exit 1 ;; esac
   age=$(( $(date +%s) - ${t#@} ))
   [ "$age" -lt 108000 ] || { echo "last fired $(( age / 3600 ))h ago"; exit 1; }
   log="$HOME/agent-workforce/logs/consolidate_memory.log"
   [ -n "$(find "$(dirname "$log")" -maxdepth 1 -name "$(basename "$log")" -newermt "@${t#@}" 2>/dev/null)" ] \
     || { echo "no receipt line written since $t"; exit 1; }
   ```

2. **The job still has a subject.** Red when no store has been written for 30 days: the
   retirement condition is met and the entry should move to `spent`. `77` when there are no
   stores at all — then the job was retired by deletion and the manifest is what is stale.

   ```check id=retirement-condition-not-met when=sweep
   root="$HOME/.hermes/profiles"
   stores="$(find "$root" -mindepth 3 -maxdepth 3 -path '*/memories/MEMORY.md' 2>/dev/null)"
   [ -n "$stores" ] || { echo "no Hermes memory stores under $root — retire the entry"; exit 77; }
   recent="$(find "$root" -mindepth 3 -maxdepth 3 -path '*/memories/MEMORY.md' -mtime -30 2>/dev/null)"
   [ -n "$recent" ] || { echo "no store written in 30 days: retirement condition met — move the entry to spent"; exit 1; }
   ```

## Known failure modes

- **A no-op forever that reads as healthy.** The receipt line says `already bounded` every
  night and the timer keeps firing; without check 2, nothing would ever say the job is
  finished. That is the dead-limb failure the manifest names, made measurable.
- **Backups accumulate.** One `.bak.consolidate.<ts>` per real change, never pruned. Small in
  practice (stores are capped), but a store that flaps at the cap grows a backup a night.
- **Lock held by a live Hermes turn.** `flock -w 30` gives up and logs `lock busy`; the store is
  skipped that night. Two nights in a row is worth reading, one is not.
- **The consolidation's own rewrite refreshes the mtime check 2 reads.** Only when it changed
  something, which requires new entries — so a store can only look "recently written" in check
  2 if something wrote to it. A no-op leaves the mtime alone (`:111`, `:119`).
