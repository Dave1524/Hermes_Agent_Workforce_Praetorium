# Brief: agent_propose timeout budget — make retries finishable and timeouts recorded
**Date:** 2026-10-06
**Requested by:** Dave, ops-praetorium thread `a6cf9c58` (diagnosis in reply `7a4d759f`)
**Owner:** Trajan
**Isolation:** `branch` — use `fix/agent-propose-timeout-budget`.
**Verify:** `bash bin/verify.sh` from the repo root (CLAUDE.md § Verification). Nothing deploys
before Dave approves and the App merges; then `bin/deploy` → verify.

## Problem

Every unit that runs `bin/agent_propose.sh` gives the job less wall time than the job's own
retry loop can spend. The units are `Type=oneshot`, so `TimeoutStartSec` covers ExecStartPre,
the whole attempt loop **and** the ExecStartPost delivery. In every unit it is smaller than
`AGENT_MAX_ATTEMPTS × AGENT_TIMEOUT_MINUTES` plus backoff. So when attempt 1 runs long:

1. the retry starts but can never finish — systemd kills the job partway through it; and
2. the kill lands outside the script's own accounting. The run leaves **no cost.log row and no
   receipt**, so the scorecard and fleet-eval never see it. Only the journal and the OnFailure
   alert record the failure.

## Evidence — `praetorium-daily-plan`, 2026-10-06 (CEST)

| Time | Event | Source |
|---|---|---|
| 06:01:33 | unit start | `journalctl -u praetorium-daily-plan` |
| 06:01:37 | `claude-auth: ok`; attempt 1/2, session `c8fb8cf3-2474-410f-a1db-d8d800b661eb` | `~/agent-workforce/logs/agent_propose.log` |
| 06:07:57 | last transcript record of attempt 1: a tool result; the next model call never returned | `~/.claude/projects/-home-dave-agent-workforce/c8fb8cf3-….jsonl` |
| 06:16:37 | attempt 1 reaches its 15-min limit (start + 15 min; the 30 s backoff gives the next line exactly) | derived |
| 06:17:07 | attempt 2/2, session `d41a863d-5b72-48b3-87f9-4439a43da4af` | `agent_propose.log` |
| 06:19:56 | `overnight-morning-report`: `SKIP: previous run still active`, exit 0, no report today | journal |
| 06:21:33 | `start operation timed out. Terminating.` → `Result=timeout`, status 15/TERM | journal |

After the kill: `~/agent-workforce/logs/cost.log` has no `task=daily-plan` row for 10-06, and
the newest receipt in `~/agent-workforce/var/workflow-receipts/praetorium-daily-plan/` is from
10-05.

**The trigger was upstream latency, not job growth.** Same model (`claude-sonnet-5`); peak
context ~162K tokens against 167K on the clean 10-02 run; 21 model calls against 22. But the
slowest single call took 196 s (attempt 1) and 126 s (attempt 2), against 36 s on 10-02 and
50 s on 10-01. The cause upstream is unknown.

Measured successful durations (cost.log `run_seconds`, all OPS rows on file):
`daily-plan` 143–576 s, `overnight-morning-report` up to 458 s, `eod-summary` up to 334 s.

## Budgets as committed

These are the repo's `profiles/*.env.example` values plus script defaults
(`AGENT_MAX_ATTEMPTS` 3, `AGENT_TIMEOUT_MINUTES` 30, `AGENT_RETRY_BASE_SECONDS` 30). The
**live** overrides in `~/.config/agent-workforce/` are deny-listed to every agent and may
differ. Today's timeline confirms only that daily-plan's live values are 2 attempts × 15 min.

| Unit | TimeoutStartSec | Attempts × per-attempt | Loop worst case, before delivery |
|---|---|---|---|
| praetorium-daily-plan | 20 min | 2 × 15 | 30.5 min |
| praetorium-eod-summary | 20 min | 2 × 15 | 30.5 min |
| overnight-morning-report | 15 min | 2 × 15 | 30.5 min — the retry can never start |
| agent-proposal, bd-followup-drafts, bd-stall-radar, knowledge-digest, m1-signal-scan, raw-ingest, weekly-pre-assembly | 45 min | 2 × 30 (default) | 60.5 min |
| augustus-content, content-change-dispatch | 45 min | no example in `profiles/` — derive it | — |

## Acceptance criteria

1. **The budget adds up for every unit that runs `agent_propose.sh`, not only the three report
   jobs.** For each unit, the worst-case attempt loop + backoff + preflight + delivery fits
   inside `TimeoutStartSec` with a stated margin. Fix it by growing the unit, shrinking the
   loop, or dropping to one attempt — choose per job and record the rule in the PR.
2. **One invariant, pinned by a test.** A regression test reads every agent_propose unit and
   its committed override example, and fails red when the invariant breaks. An edit to either
   side must not be able to break it silently.
3. **The live values are checked too.** No agent can read the live overrides. So the job itself
   must detect, at run time and from the values it actually loaded, a budget that cannot fit
   its unit's limit, and record that loudly rather than run into a systemd kill. Checking only
   the examples does not close this.
4. **Size from measurement, not from today.** Budgets come from the measured success durations
   above (pull each job's samples from cost.log). Do not raise a per-attempt limit to absorb a
   10-minute API stall: a hung call should still fail its attempt. Record the samples and the
   rule beside the values.
5. **A run that times out is recorded.** Whether an attempt or the unit hits the limit, the run
   leaves a cost.log row and a terminal receipt that name the timeout. The scorecard and
   fleet-eval must see it as a FAIL. Today a per-attempt timeout (rc 124) is not even named in
   the log — the next line is simply "run attempt 2/2". Name it, with elapsed seconds.
6. **State the lock consequence.** All 12 units share one lock (`/tmp/agent_propose.lock`, no
   unit overrides `AGENT_PROPOSE_LOCK`). The morning report fires 18 min after the daily plan,
   so a longer daily-plan budget makes the morning report lose its slot more often. The PR must
   give the resulting worst-case lock hold for the 06:01 → 06:19 pair (and any other pair the
   new budgets make collide), so Dave can decide the lock question with that number.
7. Fixtures stay local (stub runtime, no live model or relay). `bash bin/verify.sh` exits 0.

## Out of scope

- **The lock-skip behaviour itself.** Whether a lock SKIP stays a silent exit 0, becomes
  `exit 75`, or waits (`flock -w`) is Dave's open decision (ops-praetorium `8e3181ee`). Do not
  change it here. `agent_propose.sh` (~line 215) also documents why SKIP is deliberately silent.
- Timer schedules. Moving the 06:19 morning report is a way to resolve criterion 6, not part
  of this fix — propose it in the PR if the numbers call for it.
- The model choice, the upstream latency, or the daily-plan prompt's size.
- Anything under `~/.config/agent-workforce/` — do not read it. If a live value must change,
  write the exact line for Dave in the PR description.
- Vault files and branches.

## Notes

- Work in `~/dev/agent-workforce`, not the deployed `~/agent-workforce`. The auto-sync timer
  commits dirty paths on `main` every 15 min — branch before editing.
- `git fetch origin` and diff against `origin/main` before starting; this brief was written
  at `e30df0a`.
- For each unit, read the timeout in force with `systemctl show <unit> -p TimeoutStartUSec`,
  not from the file alone.
