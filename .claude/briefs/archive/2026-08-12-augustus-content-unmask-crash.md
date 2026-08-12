# Brief: Un-mask the augustus-content crash chain (NUC-44)

**Date:** 2026-08-12   **Verify:** `bash bin/verify.sh` (repo root, `~/dev/agent-workforce`)

## Problem

`augustus-content` has crashed on **every** run since at least 2026-07-25 (20 consecutive
nights) while reporting `outcome=NOPROPOSAL` + exit 0. Three layers each convert a hard
failure into a benign-looking no-op, so nothing in logs, delivery receipts, or the morning
report ever says "broken".

Verified chain:

| Layer | Behaviour | Evidence |
|---|---|---|
| OpenRouter | `402 Insufficient credits` — non-retryable | `~/.hermes/logs/agent.log` 2026-08-12 09:33:59 |
| hermes worker | exits `rc=0` without `kanban_complete`/`kanban_block` | run `status=crashed`, `protocol_violation`, 3× 60s (`max_retries=2`) |
| kanban card | 3 crashed runs → `blocked` | `hermes kanban show t_6692a6e6` |
| `bin/kanban_run_and_wait.sh:78` | NUC-25: treats **any** `blocked` as "benign decline" | `exit 0` |
| `bin/agent_propose.sh` | exit 0 → records `outcome=NOPROPOSAL`, `memory=fallback` | `logs/cost.log`, 20/20 runs |
| `bin/content_change_dispatch.sh:91` | `rc=0` → **advances `var/content_picked.state`** | orphans every Picked row |

Crash signature: `run_seconds` ∈ {200,215,230,231,245,246} across 20 runs — `3 × 60s` worker
crashes quantised by `POLL_INTERVAL_SECONDS=15`. Real work would show variance.
`usage_before=42.113538083` is byte-identical across all 20 runs: zero spend, because every
call is rejected before billing. This is the reservation trap — OpenRouter reserves worst-case
`max_tokens` up front, so the job 402s with ~$7.89 nominally remaining on the $50 cap.

**The orphaning bug is the expensive one.** `content_change_dispatch.sh` only advances state
"after a successful dispatch" — but `agent_propose.sh` returns 0 on the masked crash, so the
guard never fires. Picked rows are marked seen, never drafted, and never retried even after
credits are restored.

## Acceptance criteria

1. A run whose underlying hermes runs are `crashed`/`protocol_violation` **must not** be
   recorded as `NOPROPOSAL`. It records a distinct failing outcome (`CRASHED`).
2. `kanban_run_and_wait.sh` distinguishes a **deliberate** `kanban_block` (agent chose to
   decline; still exit 0) from a card that reached `blocked` via crashed runs (non-zero exit).
   The NUC-25 intent — don't retry a genuine decline — is preserved.
3. `content_change_dispatch.sh` leaves `var/content_picked.state` **untouched** unless the
   dispatched run actually reached a terminal success. A crashed run retries next tick.
4. `deliver_content.sh` surfaces run status, not just outcome; a crashed run does not report
   as a clean no-op.
5. `notion_rest.py draft` refuses to append to a page already at `Status=Drafted` unless
   `--force` is passed (guards the 6 already-Drafted holiday rows against variant-stacking).
6. The per-run draft cap (currently prose-only, "handle max 2") is enforced in code, not
   only in the profile markdown.
7. The stale `ONE-OFF FOR THE NEXT RUN` block (dated 2026-08-09) is removed from
   `profiles/augustus_content_task.md`.
8. `bash bin/verify.sh` is green.

## Files to modify

- `bin/kanban_run_and_wait.sh` — in the `blocked)` branch, read the card's `runs[]` via
  `hermes kanban show --json`. If every run has `outcome=crashed` / `protocol_violation`,
  exit non-zero with the run `error` on stderr. Only a card with a genuine agent-authored
  block reason keeps `exit 0`. Keep the existing comment's NUC-25 rationale, extend it.
- `bin/agent_propose.sh` — map that new non-zero into `outcome=CRASHED` in the schema-3
  `cost.log` line (do not reuse `NOPROPOSAL`). Keep `block_exit` semantics for the
  by-design "no API key" path.
- `bin/content_change_dispatch.sh` — the `rc -ne 0` guard at :81-89 already does the right
  thing; it just never fires. Once (1)/(2) land it will. Add an assertion that state is not
  advanced when the recorded outcome for this run is `CRASHED`, so the guard is defended
  even if a future runner regresses to exit 0.
- `bin/deliver_content.sh` — `content_summary()` prints `run: <outcome>`; include the hermes
  run status so a crash is legible in the delivery receipt.
- `bin/notion_rest.py` — `cmd_draft`: fetch the page's current Status before appending;
  refuse when already `Drafted` unless `--force`. Add `--max-rows` (default 2) usable by the
  caller. Keep stdlib-only, keep `DATA_SOURCE_ID` untouched.
- `profiles/augustus_content_task.md` — delete the stale ONE-OFF block; state the draft cap
  as enforced-by-tooling rather than an instruction the model may ignore.

## Files to create

- `tests/test_kanban_crash_not_benign.sh` — the core regression. Fixture a `hermes kanban
  show --json` payload whose `runs[]` are all `outcome=crashed` and assert the wrapper exits
  non-zero; a second fixture with an agent-authored block reason asserts exit 0.
- `tests/test_content_dispatch_state_hold.sh` — assert `content_picked.state` is unchanged
  when the dispatched runner reports a crash, and advanced when it reports success.

## Test plan

- Both new `tests/*.sh` are picked up by `bin/verify.sh` (syntax + shellcheck error-severity).
- Follow the repo's `pipefail` rule: no early-exiting reader (`grep -q`, `head`) ends a
  pipeline; use `grep … >/dev/null` inside conditions, and carry the `yes | grep -q y` canary.
- Fixtures must be local (a stub `hermes` on `PATH`), no live Notion or OpenRouter calls.
- Manual post-fix check: `systemctl start augustus-content.service`, then confirm `cost.log`
  shows `outcome=CRASHED` (while credits are still exhausted) rather than `NOPROPOSAL`.

## Out of scope / do not touch

- **Restoring OpenRouter credit** — Dave-gated, and a separate decision from un-masking.
  The alternative (swap `AGENT_RUNTIME_CMD` to headless Claude Code, precedent: the M1
  signal-scan migration) is a follow-up card, not this one.
- `augustus-content.timer` / `.service` unit files — the schedule is not the bug.
- The `linkedin-content-engine` dangling symlink — Mac-side fix, separate card.
- The Notion content board's data, the vault, and any `~/.config/**` secret.

## Notes / preconditions

- Repo `~/dev/agent-workforce` on `main`, clean, level with `origin/main` (checked 2026-08-12).
- **Deploy is not automatic.** Source edits alone leave systemd on old code — deploy with
  `bin/deploy` (rsync + atomic rename), never a manual `cp`.
- A 15-min auto-sync timer does `git add -A` + commit + push to `origin/main`; commit
  promptly after editing or the message is lost to a generic "Auto-sync" commit.
- `max_retries=2` on the card yields 3 runs; any crash detection must consider all of them.
- Board state at time of writing: 10 `Picked`, 6 of which were already `Drafted` (the
  Mon 18 Aug → Fri 29 Aug holiday batch) — hence criterion (5).
