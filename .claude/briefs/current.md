# Current brief

**T7.1 shipped 2026-09-10** — the decline sentinel is now scoped to this run of this job.
Archived at `.claude/briefs/archive/2026-09-10-t7-1-run-scoped-decline-sentinel.md`.

**Next: T4.0**, per `docs/dev-plan-2026-09.md` § Execution order for Claude. The gate stays
red on T1.1's ten `contract-exists` lines until Phase 4 lands, so until then a real
regression arrives in the same colour as the designed red — read the failing list, never
the exit code.

Open follow-ups this task surfaced, neither of them defects:

- **The idempotent skip now genuinely fails a run.** Six task profiles print `skip: …`,
  which `proposal_or_decline.sh` does not accept — recorded as intended in
  `design/contracts/knowledge-digest.md`, and true in practice only since T7.1. A manual
  same-day re-run, and a canary-then-schedule night, each cost one red run. Whether that
  is the alerting Dave wants is a policy call.
- **`~/.claude/projects/-home-dave/memory/MEMORY.md` has one index entry at 203/200 chars**,
  failing `tests/test_memory_index_budget.sh`. Outside this repo — it is the pool the five
  `buzz-agent@*` units and Dave's `~` sessions share — so nothing here should trim another
  runtime's memory without being asked.
