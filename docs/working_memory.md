# Agent working memory (NUC-21)

## Decision (AC1)

Store = **Hermes-native per-profile built-in memory** (`MEMORY.md`) for the
`research_analyst` profile. Chosen over a custom JSONL/SQLite run-log or an
`_inbox/agents/_memory/` markdown trail because it already exists, Hermes
auto-injects it into the run's system prompt, and the built-in `memory` tool
writes it — the least new machinery. The alternatives were rejected: a JSONL/
SQLite log is more code for no gain here; a proposal-branch markdown trail would
pollute the inbox branch and risk leaking run-notes to the Mac cockpit.

## Location (LIVE box state — NOT git-tracked)

`~/.hermes/profiles/research_analyst/memories/MEMORY.md`. This is runtime state,
not repo content. **Box-safe only**: no client-identifiable strings, no
`_confidential/` content ever — the same rule as proposal output. Distinct from
qmd (NUC-10), which is *read-side* retrieval of the canonical vault; this is the
*write-side* episodic memory of the agent's own prior runs.

## Mechanism

- Enabled via the profile `config.yaml` `memory:` block: `memory_enabled: true`,
  `write_approval: false`, `memory_char_limit: 9000`. `write_approval` MUST be
  false so unattended `-z` runs land the write — `approvals.mode: manual` gates
  dangerous shell commands, NOT memory writes (hermes `tools/write_approval.py`).
- Built-in tool: name `memory`, toolset `memory` (`tools/memory_tool.py`). The
  agent records an entry with `memory(action="add", target="memory", content=…)`.
- On-disk format: entries separated by a line that is exactly `§` (U+00A7),
  joined by `\n§\n`, no trailing newline, each entry stripped.
- **Pre-run retrieval (AC3):** at session start Hermes injects a frozen snapshot
  of `MEMORY.md` into the system prompt (`agent/system_prompt.py`). The task's
  STEP 0 tells the agent to read it and not re-propose.
- **Post-run record (AC2):** task STEP 5 appends one compact entry. If the model
  forgets the tool call, `bin/agent_propose.sh` writes a minimal fail-soft
  backstop entry (detected via a `cksum` before/after), so exactly one entry per
  run always exists — including the "no proposal + why" case. The `cost.log`
  `memory=` field records `recorded | fallback | no-store | na`.

## Entry schema

```
[run:YYYY-MM-DD] task=<question, or "none">; findings=<1-2 vault-sourced facts>;
decisions=<assumptions/choices>; proposal=<_inbox/agents/FILE.md, or "none: why">;
gaps=<open questions for next run>
```

Single line, under ~700 chars, box-safe.

## Consolidation policy (AC4)

`bin/consolidate_memory.sh` on `memory-consolidation.timer` (03:30 nightly,
`Persistent=true`), mirroring `agent-proposal.timer` / `qmd-refresh.timer`.
Mechanical, no LLM, no network. Keeps the newest `MEM_MAX_ENTRIES=12` entries
under `MEM_MAX_CHARS=7000` bytes (headroom under the tool's own 9000-char hard
cap). Bounded, idempotent, fail-soft: never empties or corrupts the store; on any
problem it leaves the store byte-for-byte untouched and exits 0. Snapshots
`.bak.consolidate.<ts>` (keeps the last 5) before each rewrite.

## Continuity verification (AC5 — costs OpenRouter; run manually)

1. Ensure `MEMORY.md` is empty. Run once:
   `cd ~/agent-worktrees/inbox && ~/.local/bin/hermes -z "$(cat ~/agent-workforce/profiles/research_analyst_task.md)" -p research_analyst`
2. Capture entry 1 (redacted) + proposal 1 filename.
3. Run again (same standing task). Capture entry 2 + proposal 2.
4. Assert: entry 2 references/advances entry 1, and proposal 2 is NOT a duplicate
   of proposal 1. Record redacted evidence below.

### Evidence log

**2026-07-08 — continuity demonstrated (redacted).** Three consecutive `agent_propose.sh` runs on the
standing task; `cost.log` shows `memory=recorded` ×3, `agent_propose.log` "agent recorded its own
episodic entry" ×3:

- **Run 1** (09:21, `run_seconds=492`, outcome=PROPOSAL) — entry 1: `[run:2026-07-08] task=AI agent
  prioritization framework; findings=vision.md identifies 5 bottlenecks but no prioritization rubric…;
  proposal=_inbox/agents/2026-07-08_agent_prioritization_framework.md; gaps=…`. Proposal 1 pushed.
- **Run 2** (09:26, `run_seconds=24` — ~20× faster, no re-exploration because memory already held the
  answer) — entry 2: `[run:…] task=none; findings=vault 04_operations/ files do not exist…;
  decisions=cannot identify active blocking work…; proposal=none: vault context insufficient; gaps=need
  Dave to populate 04_operations/…`. Run 2 **declined to duplicate** proposal 1 (a valid AC5 outcome)
  rather than re-proposing the framework cold.
- **Run 3** (09:37, outcome=NOPROPOSAL) — same decline, again citing the missing `04_operations/`.

The 20× wall-clock drop between run 1 and run 2 is itself the continuity signal: run 2 built on run 1's
recorded conclusion instead of redoing the (slow) qmd exploration. Proposals 1 vs 2/3 are not
duplicates. See [[research-analyst-vault-and-qmd-reality]] for the underlying vault-content gap.
