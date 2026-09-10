# Brief: T7.1 — the decline sentinel must belong to this run of this job

**Date:** 2026-09-10
**Task:** dev-plan-2026-09 § Phase 7, T7.1 [Claude, S]
**Verify:** `bash bin/verify.sh` from the repo root. Fleet gates are NOT in scope — this
task touches `bin/`, `profiles/`-adjacent docs and `tests/`, never `buzz-team/` or a
`buzz-agent@*` unit.
**Deploy ordering:** edit → `bin/deploy` → `bash bin/verify.sh` → commit. `check_deploy_drift.sh`
is inside the gate, so the gate is RED on drift until `bin/deploy` runs. Expected.

## What green means for this task

**The gate does not go green, and must not be made to.** `bin/verify.sh` exits 1 today on
exactly ten `PROBLEM contract-exists` lines — T1.1 shipping red by design until Phase 4 writes
the contracts. The gate for T7.1 is therefore:

- `bash bin/verify.sh` exits 1 with **exactly** those ten PROBLEM lines and no other failing
  assertion, measured against the pre-change baseline in `/tmp/.../verify.log`.
- `bin/check_deploy_drift.sh` says `drift: clean`.
- `tests/test_proposal_or_decline.sh` and `tests/test_buzz_adapters.sh` both exit 0 on their own.

Anything that turns one of the ten into eleven, or adds a FAIL elsewhere, stops the ship.

## The defect

`bin/proposal_or_decline.sh` is the `AGENT_VERIFY_CMD` for every proposal job. It answers
"did THIS run legitimately produce no proposal?" by grepping the last 40 lines of
`~/agent-workforce/logs/agent_run.log` for `^DECLINE:`. That log is a raw concatenation of
every job's attempt stdout with no run boundary in it — `bin/deliver_proposal.sh:5-7` says so
in its own header — so the sentinel carries **no job identity and no run identity**.

Proved with a fixture: with a log holding only
`DECLINE: no genuine new stalls, no proposal written` (written by `bd-stall-radar`),
`proposal_or_decline.sh bd-followup-drafts` exits **0**.

It happened live. On 2026-09-09 the `bd-followup-drafts` scheduled run at 23:31 wrote no
proposal, printed only `skip: today's pack already exists`, and logged
`OK: run completed, agent produced no proposal` — five log lines after `bd-stall-radar`'s
23:04 decline. The check built to make a dead run impossible certified one.

`bin/deliver_proposal.sh:31` has the same defect one step narrower: `grep '^DECLINE:' "$RUN_LOG"
| tail -1` picks the newest decline in the whole shared log, so a sibling's *reason* can be
delivered as this job's. Its `$MARKER` mtime guard bounds the run window but not the job.

**One concept, two sites. Both change together.**

## The fix

Give the run boundary a name instead of guessing at it with a tail window.

`agent_propose.sh` already captures each attempt's own stdout+stderr in `$attempt_out` and
holds it alive across the `AGENT_VERIFY_CMD` call before deleting it. Persist that per task
instead of discarding it, and let both consumers read it:

1. **`bin/agent_propose.sh`** — write the attempt's output to a stable per-task path under
   `logs/`, keyed by `$run_task`, and export its path so `AGENT_VERIFY_CMD` sees it. It
   replaces the `rm -f` of the temp file, so it costs no extra write.
2. **`bin/proposal_or_decline.sh`** — read the sentinel from this run's own output, never
   from the shared log. `AGENT_DECLINE_TAIL_LINES` and the tail heuristic go away entirely:
   the file holds one attempt of one job, so there is nothing to window. Fall back to the
   slug-derived path when the export is absent, so a hand invocation stays job-scoped.
3. **`bin/deliver_proposal.sh`** — take the reason from the same per-task file. Keep the
   existing `$MARKER` freshness guard; the path now supplies the job identity it lacked.

### What is deliberately NOT in scope

Six task profiles (`standing_research`, `raw_ingest`, `weekly_pre_assembly`,
`knowledge_digest`, `m1_signal_scan`, `bd_followup_drafts`) instruct an idempotent
`skip: today's … already exists`, which this checker does not accept. My Phase 7 note
proposed giving that branch its own sentinel. **Dropped after reading
`design/contracts/knowledge-digest.md:60-64`, which already records the opposite decision**:
the skip is not a decline, `proposal_or_decline.sh` fails the run, and that is called correct
because "a second run in one day is anomalous and should be visible".

That recorded decision is not what the box does today — the skip passes by borrowing a
sibling's decline. This fix makes the recorded behaviour real rather than overturning it.
The consequence becomes live: a manual re-run of a job that already ran today now goes red,
and a canary-then-schedule night (the T2.4 pattern) costs one red run. Whether that is the
alerting Dave wants is a policy call, not a defect — flagged, not decided here.

## Files to touch

| File | Change |
|---|---|
| `bin/agent_propose.sh` | persist the attempt output per task; export its path |
| `bin/proposal_or_decline.sh` | read this run's own output; drop the shared-log tail |
| `bin/deliver_proposal.sh` | `decline_reason()` reads the same per-task file |
| `tests/test_proposal_or_decline.sh` | the cross-job regression + run-scoping cases |
| `tests/test_buzz_adapters.sh` | deliver_proposal's decline-reason cases move sources |
| `design/contracts/knowledge-digest.md` | checks 1-2 and the decline section describe the new mechanism |
| `docs/dev-plan-2026-09.md` | T7.1 records the dropped half and why |

## Test plan — red before green

Extend `tests/test_proposal_or_decline.sh`. Every case below must fail against the current
script before the fix exists:

1. **Cross-job (THE regression).** Job A's `DECLINE:` is the only sentinel present; the
   checker is asked about job B, which produced nothing. → exit 1. Fails today with 0.
2. **This run's own decline.** The sentinel is in this job's own attempt output. → exit 0.
3. **Stale same-job decline.** This job's attempt output predates `AGENT_RUN_STARTED_AT`
   (an earlier run's file never overwritten). → exit 1.
4. **The shared log alone certifies nothing.** A shared `agent_run.log` full of declines,
   no attempt output for this job. → exit 1.
5. **The idempotent skip is not a sentinel**, parametrized across all six task profiles that
   instruct one: each profile's literal skip line, fed as the run's own output, → exit 1.
   Pins the recorded decision so a later change to it is deliberate.

Existing cases (a)-(d), the tail-window case and both fail-closed cases stay, rewritten onto
the new source where they named `AGENT_RUN_LOG`. No assertion is dropped: byte-compare the
`ok:` description sets before and after, the way `test_standing_research_smoke` did for W18.

`tests/test_buzz_adapters.sh`: the two `deliver_proposal` decline cases keep their assertions
and change only where the reason is written. Add one for a sibling's reason not being quoted.

## Preconditions

- `agent-workforce-auto-sync.timer` sweeps a dirty tree every 15 min under a generic message.
  Commit immediately after editing and push by hand — a commit on an otherwise clean tree is
  never pushed by that job.
- Stage by explicit path. Never `git add -A`.
- Never end a pipeline in `grep -q`/`head` while `pipefail` is on — `assert()` scopes it off;
  outside one, use `grep … >/dev/null`. Each suite carries `yes | grep -q y` as the canary.
