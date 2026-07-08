# Brief: NUC-23 — Instrument agent-run metrics / leverage scorecard
**Date:** 2026-07-08   **Verify:** `bash bin/verify.sh` (run from `~/dev/agent-workforce/` repo root)

> **Where this runs:** primary work is in the agent-workforce repo on Praetorium
> (`~/dev/agent-workforce`); run `/implement` on the box. **One acceptance criterion (AC 2, approval
> outcomes) lands in the *vault* repo** (`~/dev/obsidian-ai-os`, `00_system/tools/agent_inbox.py`),
> which has a different gate (`python3 00_system/tools/agent_inbox_test.py`). Do the box-side capture +
> rollup first — it is the baseline NUC-20 waits on — then wire the Mac-side approval outcomes.
>
> **Deploy note (NUC-16):** the runtime executes `~/agent-workforce/bin/…`, not the git copy. After
> committing, `cp` any changed `bin/` scripts to `~/agent-workforce/bin/` (+ `~/deploy-staging/…`) or
> the change won't run. New timers have the same two-location requirement.

## Goal
Make "is this agent creating leverage?" **measurable** before scaling the roster (NUC-20), instead of a
vibe. The board's Success Criteria are binary pass/fail and NUC-18 covers infra health (uptime/logs), not
agent-output quality or trust maturity. Capture per-run signals and roll them into a review-friendly
scorecard. Source: Hermes masterclass §13 (Measuring & improving) + vision scorecard ("define a simple
scorecard before building more tools") + spec §12.

## What already exists (confirmed on the box 2026-07-08)
- `agent_propose.sh` already appends a per-run line to `~/agent-workforce/logs/cost.log`:
  `run_seconds=… attempts=… outcome=OK|FAIL|VIOLATION model=…`. So **duration, attempts, outcome, model
  are already captured** — the gap is profile/task/tokens/cost fields, a rollup, and the approval side.
- Token/$ accounting from hermes is **unreliable** on OpenAI-compatible endpoints (`model.max_tokens`
  broken, #4404/#20741; `sessions.json` shows `estimated_cost_usd: 0.0`, `cost_status: unknown`). Treat
  the OpenRouter dashboard as the source of truth for actual spend; the scorecard's cost field is
  best-effort (e.g. run count × model, or blank) — do **not** fabricate a precise cost.
- Approval outcomes already have a home: the Mac's `agent_inbox.py promote|reject` records to a local
  audit trail (`.git/agent_inbox_archive/`). That is the raw material for AC 2.

## Acceptance criteria
1. **Per-run capture enriched** — each run records timestamp, profile, task (slug), duration, outcome
   (proposal / no-proposal / error), model, and a best-effort tokens/cost field (clearly marked
   best-effort). Extend the existing `cost.log` line into a structured, parseable record (append-only).
2. **Approval outcome tracked per proposal** (promoted / rejected / edited) — the trust-maturity signal
   that drives the NUC-20 approval matrix. Sourced from the Mac's `agent_inbox.py` archive. *(This AC is
   implemented in the vault repo, gated by `agent_inbox_test.py` — see the "Where this runs" banner.)*
3. **Roll-up of the spec §12 signals** — a scorecard summarizes: agent-runs/week, proposal rate,
   approval/auto-accept rate, % served local vs remote (currently 100% remote — no local inference),
   cost/run (best-effort), and box uptime. Computed from the append-only records, not hand-maintained.
4. **Surfaced reviewably from the Mac** — the scorecard is written where the Mac cockpit can read it with
   no confidential content: a digest file on the **box-safe repo** (same channel as proposals, e.g.
   `_inbox/agents/_metrics/`) or a Notion view. De-identified, box-safe only.
5. **Baseline captured before Phase 2** — a first scorecard snapshot is produced from real runs (starting
   with today's NUC-16 run onward) so NUC-20 roster growth is judged on leverage, not activity.
6. **`bash bin/verify.sh` stays green** — syntax + `shellcheck -S error` clean over `bin/*.sh`, and every
   `tests/*.sh` exits 0 including the new rollup test.

## Files to modify (git-tracked, box)
- `bin/agent_propose.sh` — enrich the `log_cost()` record with profile, task-slug, and a `key=value`
  structured format (keep it append-only; keep it written on FAIL/VIOLATION too, so failure loops stay
  visible). Preserve all guardrails; no `--max-turns` (NUC-16).
- `docs/runbook.md` — document the metrics record schema + where the scorecard is published + that
  OpenRouter is the spend source of truth.

## Files to create (git-tracked, box)
- `bin/scorecard.sh` — parse the append-only run records → compute the §12 roll-up → write the digest to
  the box-safe repo metrics path (fail-soft; never blocks a run; idempotent). Optionally its own weekly
  `systemd/scorecard.{service,timer}` (mirror `qmd-refresh.*`), or invoked at the end of `agent_propose.sh`.
- `tests/test_scorecard.sh` — mocked: given a fixture of run records, the rollup produces correct counts/
  rates; empty input → empty-but-valid digest; malformed line → skipped, not crash.

## Files to modify (vault repo — AC 2, separate gate)
- `00_system/tools/agent_inbox.py` — on `promote`/`reject`, append a structured approval-outcome record
  (slug, decision, date) to a box-safe stats file the scorecard can read; cover it in `agent_inbox_test.py`.

## Test plan
- `tests/test_scorecard.sh` (box) proves the rollup math on a fixture + fail-soft on bad input, via `verify.sh`.
- `agent_inbox_test.py` (vault) covers the new approval-outcome record (AC 2) — TDD, red first.
- Manual baseline (AC 5): run the scorecard after ≥1 real run; eyeball the digest for correct counts and
  zero confidential content.

## Out of scope / do not touch
- Real-time dashboards / Grafana / metrics DBs — a flat append-only log + a rollup digest is the whole scope.
- Precise $ cost reconstruction — best-effort only; OpenRouter dashboard is authoritative.
- Infra health (uptime/logs/service status) — that's NUC-18's `praetorium-status.sh`; link, don't duplicate.
- The approval *policy* (what auto-accepts) — that's NUC-20; this only *measures* approval outcomes.
- No client-identifiable or `_confidential/` content in any record or digest.

## Notes / preconditions
- This scorecard is the evidence NUC-20 ("first agent run quality review") is explicitly waiting on — build
  it before ratifying the Phase-2 roster so the decision is data-driven.
- Keep the record append-only and box-safe: it publishes to the box (same discipline as proposals).
- "% local vs remote" is 100% remote today (local inference dropped, NUC-07). Keep the field for when/if
  that changes, but it is a constant now — don't over-engineer it.
