# Brief: NUC-21 — Give agent profiles working memory + run continuity
**Date:** 2026-07-08   **Verify:** `bash bin/verify.sh` (run from `~/dev/agent-workforce/` repo root)

> **Where this runs:** the agent-workforce repo lives **only on Praetorium** (`~/dev/agent-workforce`).
> Run `/implement` in a Claude Code session on the box (SSH `praetorium`, `cd ~/dev/agent-workforce`).
> This brief was authored from the Mac vault session but targets the box — the vault has no verify gate.
>
> **Deploy note (learned 2026-07-08, NUC-16):** the runtime executes the **deployed mirror**
> `~/agent-workforce/bin/…`, NOT the git copy. There is no deploy script yet — after committing in
> `~/dev/agent-workforce`, you must `cp` changed `bin/` scripts to `~/agent-workforce/bin/` (and
> `~/deploy-staging/agent-workforce/bin/`) or the change won't run. Any new timer/script here has the
> same two-location requirement. (A real deploy step is tracked separately — see NUC-18 hardening.)

## Goal
Each `hermes -z … -p research_analyst` run is currently **stateless** beyond what it reads from qmd:
the agent can't see what it proposed yesterday, so it can re-propose the same thing and can't build on
its last run. Give the profile persistent, bounded memory of its **own prior runs** (write-side /
episodic memory), distinct from qmd (which is read-side retrieval of the canonical vault).
Source: Hermes masterclass (@cyrilXBT, 2026-05-31) §6 Memory system + §8 `memory-consolidation` cron.
Vision tie-in: "Context is the moat" at the agent-run layer.

## Two surfaces (read this first)
1. **Git-tracked, gated by `bin/verify.sh`** — inside `~/dev/agent-workforce/`: the task file, the
   runner, a new consolidation script + its systemd unit, a new test, and a docs note. These get committed.
2. **Live box state, OUTSIDE this repo — never committed** — the actual memory store the agent reads/writes
   (recommended: the Hermes-native per-profile memory under `~/.hermes/profiles/research_analyst/memories/`,
   which is empty today while the main profile's `~/.hermes/memories/MEMORY.md` is already populated). Edits
   there are runtime state, not repo content.

## Decision to make first (AC 1) — the store
Pick ONE store and record the choice in the docs note. Recommended: **Hermes-native per-profile memory**
(`hermes memory` subcommand + the profile's `memories/` tree), because it already exists, is auto-injected
into the agent's context by Hermes, and mirrors how the main profile's `MEMORY.md` works — least new
machinery. Alternatives considered: a per-profile JSONL/SQLite run-log the task reads/writes explicitly
(more control, more code), or a `_inbox/agents/_memory/` markdown trail on the box-safe repo (visible to
the Mac cockpit, but pollutes the proposal branch). **Constraint:** the store is box-safe only — no
`_confidential/` or client-identifiable content ever enters it (same rule as the proposal output).

## Acceptance criteria
1. **Store decided and documented** — the run-history store is chosen (recommend Hermes-native per-profile
   memory) and the decision + its location is written into a docs note. Box-safe only.
2. **Each run records an episodic entry** — after a run, a durable, timestamped, tagged record exists
   containing: the task, key findings, decisions/assumptions made, the proposal filename produced (or
   "no proposal" + why), and any self-flagged gaps. One entry per run.
3. **Pre-run retrieval + build-on instruction** — before the agent works, its relevant prior entries are
   surfaced into its context, and the task instructs it to **build on / avoid repeating** them (explicitly:
   "if you already proposed X, advance it or pick something else; do not re-propose").
4. **Bounded via consolidation/prune** — a scheduled step keeps the store from growing without limit
   (the masterclass's nightly `memory-consolidation` analogue): summarize/merge old entries, drop
   superseded ones, cap size. Runs on its own timer, same pattern as `qmd-refresh.timer` /
   `agent-proposal.timer` (systemd unit + Persistent=true).
5. **Continuity verified end-to-end** — run the profile twice on the same standing task; the second run
   demonstrably references the first (builds on it / declines to duplicate) rather than producing the same
   proposal cold. Capture both runs' memory entries + the two proposals as evidence.
6. **`bash bin/verify.sh` stays green** — bash `-n` + `shellcheck -S error` clean over `bin/*.sh`, and every
   `tests/*.sh` exits 0, including the new consolidation-script smoke test.

## Files to modify (git-tracked)
- `profiles/research_analyst_task.md` — add a first step "read your prior run-memory and build on it, don't
  repeat", and a final step "record this run to memory (task, findings, decisions, proposal filename,
  gaps)". This is the behavioral change that makes runs continuous.
- `bin/agent_propose.sh` — only if the chosen store needs runner glue (e.g. a post-run memory-write call or
  a pre-run retrieval injection the task can't do itself via a memory tool). Keep the guardrails intact
  (flock, retry/backoff, write-boundary reset, cost logging). Do **not** reintroduce a `--max-turns` flag
  (NUC-16: hermes `-z` has none; the ceiling is `agent.max_turns` in the profile config).
- `docs/` — a short note (new or appended) recording the store decision, the entry schema, and the
  consolidation policy. Reference it from `runbook.md`.

## Files to create (git-tracked)
- `bin/consolidate_memory.sh` — the prune/consolidation step (bounded, idempotent, fail-soft: never deletes
  the store on error). Same defensive style as `agent_propose.sh`.
- `systemd/memory-consolidation.service` + `systemd/memory-consolidation.timer` — nightly, `Persistent=true`,
  `After=network-online.target`. Mirror the existing `agent-proposal.*` / `qmd-refresh.*` units.
- `tests/test_consolidate_memory.sh` — mocked smoke test (scratch `$HOME`, no network): store grows past the
  cap → consolidation bounds it; empty store → no-op exit 0; malformed entry → fail-soft, store preserved.

## Test plan
- New `tests/test_consolidate_memory.sh` proves the consolidation script is bounded, idempotent, and
  fail-soft (three scenarios above), run by `bin/verify.sh`.
- Manual continuity check (AC 5): two real runs on the same standing task; assert the 2nd run's memory entry
  cites the 1st and the 2nd proposal is not a duplicate. Record commands + redacted evidence in the docs note.
- Existing `tests/test_agent_propose_smoke.sh` must still pass (don't regress the runner guardrails).

## Out of scope / do not touch
- qmd / NUC-10 read-side retrieval — this is the **write-side** memory, kept strictly separate.
- Other profiles' memory — scope to `research_analyst` only; generalize later once proven.
- The approval membrane (`agent_inbox.py`, `_inbox/agents/**` boundary) — unchanged.
- Do not put memory entries on the box-safe `main` or in the proposal files themselves.
- No client-identifiable or `_confidential/` content in the store, ever.

## Notes / preconditions (confirmed on the box 2026-07-08)
- `~/.hermes/profiles/research_analyst/memories/`, `/plans/`, `/sessions/` are all **empty** today —
  greenfield; nothing to migrate.
- The main profile already uses Hermes-native memory (`~/.hermes/memories/MEMORY.md` populated), so the
  mechanism is proven on the box.
- Hermes exposes `memory` and `memory-graph` subcommands (`hermes memory -h`) — inspect these before
  choosing the store; they may cover AC 2–3 with minimal custom code.
- The standing task (`research_analyst_task.md`) is qmd-only today (reads priorities/open-loops/daily-log,
  picks one question, writes one proposal). Memory steps slot in around it.
- Turn ceiling is `agent.max_turns` (currently 24) in the profile config — the single owner (NUC-16).
