# Brief: real-time run receipts for platform timers
**Date:** 2026-10-12   **Verify:** `bash bin/verify.sh`

The Control Room's run list, run pages and incidents are built from receipts. Twelve platform
timers have no receipt step of their own. `workflow-receipt-sweep` writes theirs once a day at
05:50, and only for each unit's latest invocation at that moment. So a fix shows the next
morning: on 2026-10-11 Dave's clean drift re-run at 10:39 never got a record, and the incident
stayed open until its failures were closed by hand. This brief gives those twelve units a
finish step that records a change of outcome the moment the run ends. The daily sweep stays,
as backfill and to decide the after-the-run checks.

## Acceptance criteria
1. When one of the twelve units in *Notes* finishes, success or failure, a finish step runs in
   the unit. It writes the run's receipt when the outcome differs from the outcome of the newest
   **judged** receipt of that workflow (`workflow_receipt.judged`: not skipped, not closed), or
   when there is none. It writes within seconds of the main process exiting.
2. An unchanged outcome writes nothing at finish. The finish step logs one line, and the 05:50
   sweep writes that unit's daily receipt exactly as it does today.
3. A finish receipt is the one the sweep would have written, except for its vantage:
   - run id = `$INVOCATION_ID`;
   - the same `systemd: <unit>.service <id> Result=… ExecMainStatus=… exited <iso>` evidence;
   - `failed` iff `$SERVICE_RESULT` ≠ `success`;
   - vantage `run`, every `sweep` check `not_applicable: vantage`;
   - the next sweep amends it when it is still the unit's latest invocation (existing T7.3 path).
4. The finish step cannot change a job's result. It is the last `ExecStopPost=` line,
   `-`-prefixed, bounds its own executor call (20 s), and exits 0. It logs exactly one line
   to the unit's journal: `receipt: written <path> (<old> -> <new>)`, `receipt: unchanged
   (<outcome>), left to the sweep`, or `receipt: errored <reason>`.
5. Live: after land, a failed→success or success→failed flip on one of the twelve opens or
   resolves its incident within one `workflow-incidents` tick (≤ 5 min), with no hand closure.
6. `tests/test_receipt_coverage.py` models it. The twelve rows move from producer class
   `sweep` to a new class `finish`, decided from the unit file. A thirteenth platform timer
   without the finish step fails the suite.
7. The docs that describe receipt producers say so (*Files to modify*).

## Design decisions
- **D1. `ExecStopPost=`, not `OnSuccess=`/`OnFailure=` template units.** It runs as the unit's
  own user and environment, and systemd hands it `INVOCATION_ID`, `SERVICE_RESULT`, `EXIT_CODE`
  and `EXIT_STATUS`. That needs no new units in two scopes.
  - Measured on systemd 259 with throwaway units (`systemd-run --user`, 2026-10-12):
    - main exits 3 → stop-post sees `SERVICE_RESULT=exit-code EXIT_STATUS=3`, `INVOCATION_ID` set;
    - a failing un-prefixed `ExecStopPost` turns a successful unit `exit-code` and **stops
      later stop-post lines**;
    - a `-`-prefixed one does neither.
  - Cost: the finish step sees the main process's result only. `agent-inbox-sync`'s delivery
    (an earlier `ExecStopPost`) failing means the finish step never runs, and the sweep backfills.
- **D2. Record on change, not every run.** The Control Room parses and validates every receipt
  on every request (`ControlRoomReadModel._receipt_files` / `receipts()`, `bin/control_room_api.py`).
  - Measured: 795 receipts, `/api/v1/workflows` in 0.77 s.
  - Every run of the twelve is ~416 receipts/day (workflow-incidents alone 288). That is ~150k a
    year, or minutes per page load.
  - On-change adds only the flips to today's volume, and the workflow page's live systemd
    fields already show every run's result.
- **D3. One evidence builder.** `evidence_flags` / `epoch_of` move out of `bin/receipt_sweep.py`
  into `bin/systemd_evidence.py`, imported by both the sweep and the finish step.
  - `EXIT_STATUS` is a signal *name* when `EXIT_CODE=killed`/`dumped`. It is normalised to the
    number `ExecMainStatus` reports, so the two producers' evidence cannot drift.
- **D4. "Changed" is judged against the newest judged receipt**, the same filter the incident
  derivation uses for `lastEligibleRun`. A write therefore is exactly a run that would move the
  incident.
- **D5. The sweep stays**, for three reasons:
  - it catches a timer that stopped firing;
  - it decides `when=sweep` checks (an OnFailure alert fires *after* stop-post, so "the failure
    was alerted" is undecidable at finish);
  - it backfills any run the finish step skipped or could not record.
  Its retirement condition is rewritten accordingly.

## Files to create
- `bin/systemd_evidence.py`: `epoch_of`, `evidence_flags`, `exit_status_number(code, status)`.
- `bin/receipt_finish.py`, the finish step. `receipt_finish.py [--user] <unit>`:
  - reads `INVOCATION_ID`, `SERVICE_RESULT`, `EXIT_CODE`, `EXIT_STATUS` from the environment;
  - reads `ExecMainStartTimestamp` from `systemctl [--user] show <unit>.service --timestamp=unix`;
  - resolves `workflow_id` through `contract_exec.manifest_row` (as `receipt_sweep.workflow_id` does);
  - reads `<receipt-root>/<workflow_id>/*.json` for the newest judged outcome;
  - on change, calls `contract_exec.py <unit> --vantage run --run-id $INVOCATION_ID
    <evidence> --run-started-at <epoch>` with a 20 s timeout;
  - logs the one line and exits 0 always.
  Fixture overrides: `SYSTEMCTL`, `CONTRACT_EXEC`, `--receipt-root`, `--now`, matching `receipt_sweep.py`.
- `tests/test_receipt_finish.py` and the wrapper `tests/test_receipt_finish.sh`. Cases are in *Test plan*.
- `tests/test_systemd_evidence.py`, or a section of the above. One file per concept, so its own file.

## Files to modify
- The unit files, each gaining the finish step as its **last** `ExecStopPost=` line:
  - `systemd/{agent-buzz-acp-update,agent-config-eval,agent-drift-check,agent-inbox-sync,fleet-eval,fleet-turn-check,inbox-backlog-alert,overnight-pre-snapshot,qmd-refresh,scorecard,workflow-incidents}.service`
    get `ExecStopPost=-/home/dave/agent-workforce/bin/receipt_finish.py %N`;
  - `systemd/user/buzz-pr-watch.service` gets the same line with `--user %N`;
  - in `agent-inbox-sync.service` it goes after `deliver_inbox_sync.sh`.
- `bin/receipt_sweep.py`: import from `systemd_evidence`. The docstring names it backfill +
  amend, and says a finish-written receipt is amended, never rewritten (the existing
  `sweep_owed` path).
- `tests/test_receipt_coverage.py`:
  - add producer class `finish`, recognised by a unit file whose last `ExecStopPost=` names
    `receipt_finish.py`;
  - `EXPECTED_TALLY` becomes `finish: 12, sweep: 0`, and the docstring says five producers;
  - re-measure `LOGICAL_WORKFLOWS` (30) and keep it unchanged;
  - new assertion: every `surface = "platform"` standing timer except the sweep itself has the
    finish step.
- `tests/test_receipt_sweep.py`: one case where the sweep amends a finish-written run-vantage
  receipt of a platform contract (fixture from the real executor, not hand-built JSON).
- `design/agents/trajan.toml`, `workflow-receipt-sweep` entry: `what`/`guards` text (backfill + amend), and the
  new suites appended to its `suite` list. `trigger` stays `daily 05:50`.
- `design/contract-schema.md`:
  - § Vantage: a platform unit's run-vantage receipt comes from the finish step, from
    systemd's verdict alone;
  - § light contract: "There is no `run` vantage" becomes "no `run` *checks*".
- `design/contracts/workflow-receipt-sweep.md`: Outputs (backfill), Retirement condition (the
  sweep keeps the timer-fired and after-the-run checks even when every runner self-receipts),
  contract version 2.
- `CLAUDE.md`, receipts bullet: five producers, the finish step named.
- `docs/runbook.md`: the sweep's job-wiring row, and a short § on reading a `receipt:` journal line.

## Order of work
1. `tests/test_systemd_evidence.py`, failing:
   - success → `--state-change` only;
   - `exit-code 3` → `--failed Result=exit-code ExecMainStatus=3`;
   - `killed TERM` → `ExecMainStatus=15`;
   - missing exit stamp → `exited unknown time`.
   Then extract `bin/systemd_evidence.py` and point `receipt_sweep.py` at it. `tests/test_receipt_sweep.sh` must stay green.
2. `tests/test_receipt_finish.py`, failing, with a stub `systemctl`, the **real**
   `bin/contract_exec.py` and a temp receipt root. Then write `bin/receipt_finish.py` until it passes.
3. The end-to-end case: the finish step writes a failed receipt, then `receipt_sweep.py` (stub
   systemctl naming the same InvocationID, inactive) amends it. Assert the `swept` block and the
   sweep checks are decided, and that no second file appears.
4. The coverage assertions in `tests/test_receipt_coverage.py`, failing on today's unit files.
   Then add the `ExecStopPost=` line to the twelve units. `systemd-analyze verify` each one.
5. The docs and manifest text in *Files to modify*.
6. Mutation pass:
   - drop the `-` prefix → the coverage suite is red;
   - make the change test always-true → the "unchanged success writes nothing" case is red;
   - remove the timeout → the hang case is red.
7. `bash bin/verify.sh`. Expected reds: drift on the twelve undeployed units and the new bin
   files, plus the known in-cgroup `test_interaction_receipt.py` pair. Anything else blocks the PR.

## Test plan
- `test_systemd_evidence.py`: the four evidence shapes, and signal normalisation for both
  `killed` and `dumped`.
- `test_receipt_finish.py`, one case each:
  - no prior receipt → writes;
  - success after a judged success → writes nothing, logs `unchanged`;
  - success after a judged failure → writes (this is the "fix shows" case);
  - failure after success → writes;
  - failure after failure → nothing;
  - newest failure **closed**, previous judged success, this run success → nothing;
  - newest failure closed, this run failure → writes;
  - `INVOCATION_ID` unset → `errored`, writes nothing, exit 0;
  - executor exits 2 (refused) → `errored`, exit 0;
  - executor hangs past the bound → `errored`, exit 0 within ~20 s;
  - `--user` reaches `systemctl`.
- The end-to-end case from *Order of work* 3.
- `test_receipt_coverage.py`: the producer model and the platform-has-finish-step assertion,
  both directions. A fixture unit file without the line must fail.
- Follow the `::` anchor convention the coverage checker reads (`tests/test_workflow_coverage.py`).

## Land-time steps
1. Trajan: `bin/deploy --dry-run`, then `bin/deploy`. This ships `receipt_finish.py`,
   `systemd_evidence.py` and `receipt_sweep.py`; the sweep's next 05:50 run uses the shared module.
2. Trajan: `cp systemd/user/buzz-pr-watch.service ~/.config/systemd/user/ && systemctl --user daemon-reload`.
3. Dave (sudo), from `~/dev/agent-workforce` at the merge commit:
   `sudo install -m 0644 systemd/<the eleven>.service /etc/systemd/system/ && sudo systemctl daemon-reload`.
   Trajan posts the exact line with the eleven names. No restarts are needed: each unit picks up
   the line on its next start. Back up the eleven first:
   `sudo cp /etc/systemd/system/<unit>.service{,.bak-<date>}`.
4. Trajan, within 35 min of step 3, reads each high-frequency unit's journal for its first
   `receipt:` line: workflow-incidents (5 min), qmd-refresh and agent-inbox-sync (30 min),
   fleet-turn-check (:00). Expect `unchanged (artifact)` on a healthy box. That proves the step
   runs and finds the history.
5. `bin/check_deploy_drift.sh` reads `drift: clean`.
6. Acceptance 5 (a live flip) is **not provable on demand without breaking something**. Record
   it as not verified until the first natural failure or recovery, then confirm from the journal
   line, the receipt and the incident timestamps.

**Rollback:** restore the eleven `.bak` units with `sudo cp`, `daemon-reload`, and the user
unit by `git checkout` + `cp`. Then `git revert` the merge and `bin/deploy`. The receipts
already written are valid and stay.

## Out of scope / do not touch
- Every-run receipts, and the retention/pruning policy that would then be needed.
- Caching parsed receipts in the Control Room.
- The agent jobs (`agent_propose.sh` rows already receipt at run) and `buzz-agent@*` (interaction receipts).
- The sweep's cadence and its amend scope (it still amends only the invocation it sees).
- Incident paging policy (`bin/incident_notify.py`). See Risks; that is Dave's call.
- `content-change-dispatch` (paused, self-receipting) and `research-brief` (agent job).

## Risks
- **More pages, sooner.** `incident_notify.py` sends `[incident]` for each newly open
  immediate-class incident and `[recovered]` when it closes.
  - Today a platform failure gives the OnFailure alert at once and `[incident]` the next morning.
    After this, both arrive within 5 min.
  - A flapping unit (fleet-turn-check on a transient 529) produces an `[incident]`/`[recovered]`
    pair per flap.
  - Tell: `[incident]`+`[recovered]` count per day in #incidents against the week before.
  - Response: Dave decides. The small follow-up is a minimum open age before paging (e.g. 60 min).
- **The source checkout drives the executor.** `contract_exec.py` reads `design/` from
  `~/dev/agent-workforce`, so a feature branch checked out there makes it refuse contracts. This
  happened on 2026-10-07/08. Now twelve units, one of them every 5 min, hit that path.
  - Tell: `receipt: errored … exit 2` lines.
  - Response: the job is unaffected (D1), the sweep backfills; restore `main` in the checkout.
- **A finish receipt can resolve an incident the 05:50 amendment re-opens.** This happens when
  the run exited 0 but a sweep check (e.g. the alert check) fails.
  - Tell: an incident `resolvedAt` followed by a reopen at 05:5x.
  - Response: accept; it is the same verdict the sweep reaches today, one morning later.
- **Sweep checks on a finish receipt for a non-latest invocation stay `not_applicable: vantage`
  forever.** Not a regression: today those runs have no receipt at all.
  - Tell: run pages with n/a checks older than a day.
  - Response: accept, or widen the amend scope as its own task.
- **A unit flapping every tick writes a receipt per flip.** Worst case is workflow-incidents
  alternating every 5 min, at 288/day.
  - Tell: `find ~/agent-workforce/var/workflow-receipts/<id> -newermt '-1 day' | wc -l` > 50.
  - Response: fix the flap; add a backoff only if it recurs.
- **Stop-post timeout.** The executor's own bound is 20 s, well inside `TimeoutStopSec` (90 s
  default). A wedged filesystem could still hold the stop.
  - Tell: `receipt: errored timeout` lines, or a unit stuck in `deactivating`.
  - Response: rollback step 1 for that unit.

## Notes / preconditions
All measured 2026-10-12 at `896637a`.
- **The twelve:** `tests/test_receipt_coverage.py` `EXPECTED_TALLY["sweep"] == 12`, and the
  05:50 sweep log `written:` set. All are `surface = "platform"` in `design/agents/trajan.toml`
  and `Type=oneshot`; the eleven system units are `User=dave`:
  agent-buzz-acp-update, agent-config-eval, agent-drift-check, agent-inbox-sync, buzz-pr-watch
  (user scope), fleet-eval, fleet-turn-check, inbox-backlog-alert, overnight-pre-snapshot,
  qmd-refresh, scorecard, workflow-incidents. Only agent-inbox-sync already has an `ExecStopPost=`.
- **Executor at run vantage**, for a platform contract into a temp root: 0.08 s. Both sweep
  checks are `not_applicable: vantage`, terminal `failed` with the given reason, exit 1 on a
  failed receipt. The finish step must treat exit 1 as "written".
- **No race with the sweep:** `receipt_sweep.sweep_unit` skips a unit whose `ActiveState` is
  `deactivating`, which is the state during stop-post.
- `agent-buzz-acp-update` has `SuccessExitStatus=10`. Exit 10 arrives as `SERVICE_RESULT=success`
  and is recorded as success, as the sweep does today.
- `.claude/briefs/current.md` belongs to the B9 broker-decisions work and is untracked in the
  main checkout. This brief does not replace it. Point `/implement` at this file by name.
