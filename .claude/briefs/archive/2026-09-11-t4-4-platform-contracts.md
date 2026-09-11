# Brief: T4.4 — Light contracts for Trajan's 14 standing platform jobs
**Date:** 2026-09-11   **Verify:** `bash bin/verify.sh` (bash -n + shellcheck -S error over `bin/` and `tests/*.sh`, `bin/check_deploy_drift.sh`, then every `tests/*.sh`; retries 1; escalate = print failing command + tail, change nothing else)

Dev-plan card: `docs/dev-plan-2026-09.md` § T4.4 (lines ~293-307). Board: Dev Plan, T4.4 is
next after T4.3. Schema: `design/contract-schema.md`. Validator: `tests/test_contract_schema.py`
(+ `.sh` wrapper). Manifest join: `tests/test_workflow_coverage.py` (T1.1 `contract-exists`).

## Acceptance criteria

Verbatim gate from the card: **14 files pass the validator, and every standing platform
workflow exposes an actionable artifact or state change plus a retirement condition where one
applies.** Concretely:

1. `design/contracts/<unit>.md` exists for each of the 14 standing platform entries in
   `design/agents/trajan.toml`, stem = unit name (rule `named-for-unit`, no `rule1_exempt`):
   `fleet-turn-check`, `fleet-eval`, `local-tier-eval`, `memory-consolidation`,
   `agent-inbox-sync`, `inbox-backlog-alert`, `scorecard`, `qmd-refresh`,
   `agent-workforce-auto-sync`, `ttm-pool-drain`, `overnight-pre-snapshot`, `buzz-pr-watch`,
   `agent-drift-check`, `agent-buzz-acp-update`.
2. Each of those 14 `[[workflows]]` entries gains `contract = "design/contracts/<unit>.md"`.
   The two `status = "spent"` entries (`nekovri-subsidy-kickoff`, `nekovri-subsidy-watchdog`)
   gain `contract_exempt = "<reason>"` and NO `contract` field. No other manifest edits.
3. Every contract passes every validator rule: 8 `##` sections present, in schema order,
   non-empty (`none` is allowed and expected for Inputs / Side effects where true);
   `## Outputs` carries the five `#### Outputs fields` bullets (`Beneficiary`, `Next actor`,
   `Next action`, `Benefit hypothesis`, `Benefit signal`) with non-trivial values;
   `## Acceptance checks` has ≥1 numbered item, each with exactly one indented
   ```check id=<slug> when=run|sweep``` block; blocks are bash-syntax-clean, read only executor
   env vars (`UNIT SYSTEMCTL JOURNALCTL RUN_DATE AGENT_RUN_STARTED_AT AGENT_ATTEMPT_LOG
   AGENT_INBOX_DIR INBOX_WORKTREE VAULT HOME`) or vars they set, exit 0/77/else; Identity
   `Owner` row bold token = `**trajan**`; `Unit` row tokens = the entry's `unit` value.
4. Every contract states, in prose, the six T4.4 facts: **trigger**, **cadence**,
   **artifact or state change**, **evidence location**, **failure-remediation owner**, and a
   **retirement condition** (or `none — standing` with the sentence why).
5. Minimum mappings by category (from the card — a log line alone is NOT an artifact unless a
   named consumer or alert path acts on it):
   - health / eval / drift / update (`fleet-turn-check`, `fleet-eval`, `local-tier-eval`,
     `agent-drift-check`, `agent-buzz-acp-update`) → a **verdict or alert carrying the failed
     assertion and its remediation owner**.
   - sync / refresh / auto-sync / consolidation / drain (`agent-inbox-sync`, `qmd-refresh`,
     `agent-workforce-auto-sync`, `memory-consolidation`, `ttm-pool-drain`) → a **state change
     with before/after or receipt evidence**.
   - snapshot / scorecard (`overnight-pre-snapshot`, `scorecard`) → a **dated artifact and a
     named downstream consumer**.
   - temporary watchers (`buzz-pr-watch`) → a **status-change alert and an explicit
     retirement condition**. `inbox-backlog-alert` is an alert path: silence-by-design, so its
     artifact is the alert line + its receipt, and its check must be decidable on quiet days.
6. Benefit hypothesis / signal: record `Unknown` (with why) rather than estimating risk avoided
   or operator time saved — no failure has been caught / no manual baseline exists.
7. `python3 tests/test_contract_schema.py` prints zero `PROBLEM` lines and
   `SUMMARY contracts=26 declared=26 absent=0 exempt=3 ...` (26 = 12 existing + 14 new;
   `declared` counts distinct paths, so it is 26 too; exempt stays 3).
8. `python3 tests/test_workflow_coverage.py` prints zero `contract-exists` PROBLEM lines;
   `.claude/workflows/ship-dev-plan.js` `MISSING_CONTRACTS = []` stays unchanged.
9. `design/contract-schema.md` § Status: replace the closing "Trajan's platform jobs still
   carry no `contract` field" paragraph with the landed state (26 contracts, 14 of them light
   platform contracts, T4.4, 2026-09-11) and the counted figures under `tomllib` on
   2026-09-11 (see criterion 7). Overwrite the existing counted marker; never add a second.
10. Gate green: `bash bin/verify.sh` exits 0.

## Files to modify

- `design/agents/trajan.toml` — add `contract = "design/contracts/<unit>.md"` to each of the 14
  standing platform entries (place it after `unit =`, matching how marcus/claudius entries do
  it); add `contract_exempt = "spent 2026-08-xx: campaign closed, unit disabled; no contract
  because nothing is promised any more"` (write the real reason from each entry's own notes)
  to `nekovri-subsidy-kickoff` and `nekovri-subsidy-watchdog`. Do not touch `buzz-agent@trajan`.
- `design/contract-schema.md` — § Status only (criterion 9). Also the `#### Outputs fields` /
  sections / env lists MUST NOT change (the validator reads them).
- No change to any `systemd/*` unit, any `bin/*` script, or the deployed `~/agent-workforce/`
  tree. (Editing `bin/` would make the drift check red until `bin/deploy` — not needed here.)

## Files to create

14 contracts, ~80-130 lines each, in `design/contracts/`. Template shape: copy the skeleton
of `design/contracts/overnight-morning-report.md` (Identity table, 8 `##` sections, Outputs
fields bullets, numbered checks with one fenced block each), trimmed to "light": one or two
checks, prose kept to what is true and cited. Per-unit facts, all read from the unit files
and runners on 2026-09-11 (cite `systemd/<unit>.timer|service`, the runner path, and the
line where it matters):

| Contract file | Unit(s) | Trigger / cadence | Runner (cite, don't copy) | Artifact / state change → evidence | Consumer / alert path | Retirement |
|---|---|---|---|---|---|---|
| `fleet-turn-check.md` | `fleet-turn-check.service` / `.timer` | `OnCalendar=hourly`, `RandomizedDelaySec=120`, `Persistent=true` | `buzz-team/fleet-turn-check.sh` (deployed `~/.config/buzz-team/`) | PASS/FAIL verdict line `== fleet-turn-check PASS|FAIL ==` in the journal + per-unit CPU-delta state `~/logs/fleet-turn-check.state`; FAIL → exit≠0 → `OnFailure=agent-alert@%n` → `bin/agent_alert.sh` (throttled) → `~/logs/agent-alert.log` + notify | agent-alert (Dave) | none — standing; retire only if a live turn probe replaces it |
| `fleet-eval.md` | `fleet-eval.service` / `.timer` | `OnCalendar=*-*-* 07:07:00`, `RandomizedDelaySec=90s`, `Persistent=true`; **no OnFailure — deliberate** (`alerted = false` in manifest; exit 1 on regression is a report, `--deliver` posts it) | `bin/fleet_eval.sh --deliver` (`WorkingDirectory=/home/dave`, `QMD_LLAMA_GPU=vulkan`) | `~/logs/fleet-eval/<run>/scorecard.md` + history spine `~/logs/fleet-eval/history.psv`; on regression `bin/deliver.sh` → #ops with a receipt in `~/logs/delivery-receipts.jsonl` | Dave via #ops; remediation owner = trajan (script) / marcus-claudius (behaviour regressions named per row) | none — standing |
| `local-tier-eval.md` | `local-tier-eval.service` / `.timer` | `OnCalendar=*-*-* 02,08,11,14,17,20:17:00`, `Persistent=false`, OnFailure | `bin/local_tier_eval.sh` (Ollama, no egress) | `~/logs/local-tier-eval/<stamp>/scorecard.md` + `~/logs/local-tier-eval/history.psv`, one row per run naming which capability t1-t4 failed | agent-alert on unit failure; history read by whoever decides local-model use (Dave) | none — standing; retire if the local tier is dropped |
| `memory-consolidation.md` | `memory-consolidation.service` / `.timer` | `OnCalendar=*-*-* 03:30`, `RandomizedDelaySec=5min`, `Persistent=true`, OnFailure | `bin/consolidate_memory.sh` | State change: each `~/.hermes/profiles/*/MEMORY.md` deduped + FIFO-capped, with `.bak.consolidate.<ts>` copy beside it as the before; `~/agent-workforce/logs/consolidate_memory.log` records before/after counts per profile or `no-op:` reason. **Card note: "dead limb"** — the Hermes stores it prunes are written by nothing since the Buzz migration; say so and name the retirement condition | agent-alert on failure; nobody reads the log by design | retire when the last `~/.hermes/profiles/*/MEMORY.md` stops changing for 30 days (check can measure this) |
| `agent-inbox-sync.md` | `agent-inbox-sync.service` / `.timer` | `OnCalendar=*:0/30`, `RandomizedDelaySec=2min`, `Persistent=true`, OnFailure, run marker `~/logs/run-markers/agent-inbox-sync.service`, `DELIVERY_ROUTE=approvals` | `bin/agent_inbox_pipeline.sh` → `agent_inbox_notion_sync.py` + `agent_inbox_apply.py --apply` | State change: Notion rows ↔ `_inbox/agents/*.md` reconciled; receipt = `~/agent-workforce/logs/agent_inbox_pipeline.last` (this run's, timestamped header) | Mac-side promote/reject (Dave) reads Notion; agent-alert on `sync failed`/`apply failed` | none — standing |
| `inbox-backlog-alert.md` | `inbox-backlog-alert.service` / `.timer` | `OnCalendar=*-*-* 06:20`, `RandomizedDelaySec=3min`, `Persistent=true`, OnFailure, `DELIVERY_ROUTE=approvals` | `bin/inbox_backlog_alert.sh` (threshold `INBOX_BACKLOG_THRESHOLD_DAYS=2`, silent under threshold, fail-soft exit 0) | Alert line via `bin/deliver.sh` to #approvals with receipt in `~/logs/delivery-receipts.jsonl` — only on days the oldest pending proposal > 2 days. Quiet day = no artifact BY DESIGN; the check must exit 77 or pass on quiet days, not fail | Dave (approvals) | none — standing; retire if the inbox workflow is retired |
| `scorecard.md` | `scorecard.service` / `.timer` | `OnCalendar=Mon 07:00`, `RandomizedDelaySec=5min`, `Persistent=true`, OnFailure, `DELIVERY_ROUTE=ops`, `ExecStartPost=bin/deliver_scorecard.sh` | `bin/scorecard.sh` (idempotent, fail-soft) | Dated artifact: `~/agent-worktrees/inbox/_inbox/agents/_metrics/scorecard.md` (data-derived header carries the week) pushed to the box-safe repo; summary rows delivered to #ops with receipt | Dave via #ops (weekly rollup, silence policy `never`) | none — standing |
| `qmd-refresh.md` | `qmd-refresh.service` / `.timer` | `OnBootSec=5min`, `OnUnitActiveSec=30min`, `RandomizedDelaySec=2min`, `Persistent=true`, OnFailure | `bin/vault_sync_guard.sh sync` then `qmd update && qmd embed --timeout 20` | State change: `~/vault` fast-forwarded (or resynced) to origin — before/after = `git rev-parse HEAD` in journal; qmd index re-embedded. Exit 1 on dirty tracked tree → agent-alert | qmd-mcp consumers (every agent); alert to Dave | none — standing; retire at vault cutover if the mirror is replaced (note, don't promise) |
| `agent-workforce-auto-sync.md` | `agent-workforce-auto-sync.service` / `.timer` | `OnCalendar=*:0/15`, `RandomizedDelaySec=2min`, `Persistent=true`, OnFailure, `WorkingDirectory=/home/dave/dev/agent-workforce` | `bin/auto-sync` — **execs from the source checkout, not the deployed copy** (say so) | State change: commit + `git push origin main` of small safe edits; receipt = the commit on `origin/main` (`git log -1 --format=%H %ci`) and a clean `git status` after | origin/main (Mac pulls); agent-alert on push failure | none — standing |
| `ttm-pool-drain.md` | `ttm-pool-drain.service` / `.timer` | `OnBootSec=2min`, `OnUnitActiveSec=2min`, `Persistent=false`, OnFailure (throttled, see unit comments), runs as root, `TTM_DRAIN_THRESHOLD_MB=1024` | `/usr/local/bin/ttm-pool-drain` — **root-owned, off-repo** (`suite_exempt` already); cite the unit's header comments | State change: TTM pool pages returned to kernel; before/after = the journal line `ttm-pool-drain: <start>MB -> <end>MB (freed N MB in R rounds)` or `pool < threshold — nothing to do` | ollama load-time sizing (implicit consumer); agent-alert on failure | retire when the xe driver stops hoarding (kernel fix) — state as condition, evidence = `/sys/kernel/debug/ttm/page_pool_shrink` absent or pool never > threshold for 30 days |
| `overnight-pre-snapshot.md` | `overnight-pre-snapshot.service` / `.timer` | `OnCalendar=*-*-* 04:25`, `RandomizedDelaySec=2min`, `Persistent=true`, OnFailure, `REPORT_DIR=~/logs/overnight`, `REPORT_GLOB=pre-snapshot-*.log`, `DELIVERY_ROUTE=ops`, run marker, `ExecStartPost=bin/deliver_report.sh` | `bin/overnight_pre_snapshot.sh` (fail-soft per section) | Dated artifact `~/logs/overnight/pre-snapshot-<stamp>.log`; delivered to #ops via `deliver_report.sh` → `deliver.sh` with receipt | Named consumer: `overnight-morning-report` (marcus) reads it — cite `design/contracts/overnight-morning-report.md` Inputs | none — standing |
| `buzz-pr-watch.md` | `buzz-pr-watch.service` / `.timer` (**`scope = "user"` → `$SYSTEMCTL` is `systemctl --user`**) | `OnCalendar=*-*-* 09:23`, `RandomizedDelaySec=20m`, `Persistent=true`, no OnFailure | `~/.local/bin/buzz-pr-watch` (python, off-repo, `suite_exempt`) — polls unauthenticated GitHub API for block/buzz#3816 | Status-change alert: on close, announces once via `hermes send --to discord` (**Discord was retired 2026-08-04 — record as known failure mode: the announce path is likely dead; the stamp still lands**), writes stamp `~/.local/state/buzz-pr-watch/3816.announced`, then self-disables the timer | Dave (unpark Desktop @-mention) | **explicit: retires itself when PR #3816 closes** — stamp file exists ⇒ contract fulfilled ⇒ entry should move to `spent`. Check: stamp present ⇒ pass-and-flag (exit 0 with message) |
| `agent-drift-check.md` | `agent-drift-check.service` / `.timer` | `OnCalendar=*-*-* 05:40`, `RandomizedDelaySec=3min`, `Persistent=true`, OnFailure | `bin/check_deploy_drift.sh` (reports, never converges) | Verdict = exit code + per-file drift lines in journal; failure → agent-alert carrying the failing tree/file; remediation owner = whoever last edited the repo (run `bin/deploy` or `sudo cp` unit) | Dave via agent-alert; the gate itself in `bin/verify.sh` | none — standing |
| `agent-buzz-acp-update.md` | `agent-buzz-acp-update.service` / `.timer` | `OnCalendar=*-*-* 07:35`, `RandomizedDelaySec=5min`, `Persistent=true`, OnFailure | `bin/buzz_acp_update.sh check` — exit 0 current / 10 behind / 1 unpinned or receipt missing (script lines ~46) | Verdict: exit 10 ⇒ agent-alert "behind upstream tag X"; receipt `~/agent-workforce/var/buzz-cli-install.json` carries tag AND sha256 of the live binaries (state evidence) | Dave decides to `bin/buzz_acp_update.sh install`; remediation owner = Dave (install is a human action) | none — standing; retire if Buzz CLI gets a package manager |

Check-block guidance (all `when=sweep` unless stated; Persistent/timers are the sweep vantage):
- Fired-within-window (every contract): `last=$($SYSTEMCTL show "$UNIT.timer" -p LastTriggerUSec --value --timestamp=unix)`; strip `@`; compare against the cadence + RandomizedDelaySec + slack. Copy the pattern from `overnight-morning-report.md` `timer-fired-and-not-skipped`. For `qmd-refresh`/`ttm-pool-drain` (monotonic timers) window = 2× `OnUnitActiveSec`.
- Artifact-is-this-run's (dated-artifact contracts): newest file matching the glob has mtime ≥ `LastTriggerUSec`; `exit 77` when the timer has never fired.
- Verdict/alert contracts: `$JOURNALCTL -u "$UNIT" --since "@$last" -o cat | grep -q '<verdict marker>'`, and for units that exited non-zero, `$SYSTEMCTL show "$UNIT" -p ExecMainStatus`.
- State-change contracts: compare a before/after the script itself prints (journal) or a receipt file's mtime/contents.
- Blocks run under `set -u`, no `-e`, no `pipefail`: guard every empty expansion (`${last:-}`), never rely on a failing pipeline's status. Only the listed executor vars; `$HOME` for paths.
- Fleet is PAUSED (timers disabled 2026-09-11, `~/OUTBOX/fleet-pause-2026-09-11.md`): running any sweep check live today returns stale/77 — that is the correct answer, not a bug. Do not "fix" it by widening windows. Validate checks by syntax (`bash -n`) and the validator's env rule, plus one manual dry run of a block with `UNIT=<unit> SYSTEMCTL=systemctl JOURNALCTL=journalctl` to confirm it exits 0/77/1 deterministically and never hangs.

## Test plan

- `python3 tests/test_contract_schema.py` (from repo root): zero `PROBLEM` lines; `SUMMARY`
  `contracts=26 declared=26 absent=0 exempt=3`. Run it FIRST on the manifest edit alone
  (before any file exists) and confirm 14 `contract-declared`/absent PROBLEM lines — that is the
  red step; each contract written turns one green.
- `bash tests/test_contract_schema.sh`: all `ok:` (its `::validated-count` guard compares the
  summary to `ls design/contracts/*.md | wc -l`, so 26 must equal 26).
- `python3 tests/test_workflow_coverage.py`: zero `contract-exists` PROBLEM lines; the two
  spent entries still print as they did (this suite does not read `contract_exempt` — T4.5
  will; do NOT extend it here).
- `bash tests/test_ship_dev_plan_workflow.sh`: green with `MISSING_CONTRACTS = []` untouched.
- Manual per-block dry run (not a test file): for each of the 14 contracts, extract the
  first check block and run it with the executor env set, expecting 77 (never fired / paused)
  or 0, never a hang, never a `set -u` unbound error.
- `bash bin/verify.sh`: exit 0, no new SKIP lines.
- No new test files: the validator and its fixtures already cover every rule these contracts
  must satisfy; a contract is data the existing suite grades.

## Out of scope / do not touch

- T4.5 (flipping `contract-exists` to "present and resolves", reading `contract_exempt`).
- T7.2 and any change to what the jobs DO: no edits to `systemd/*`, `bin/*`, `buzz-team/*`,
  the deployed `~/agent-workforce/`, `/etc/systemd/system/`, `~/.config/systemd/user/`.
- Fixing `buzz-pr-watch`'s dead Discord announce path — record it as a failure mode only.
- Moving `buzz-pr-watch` or `memory-consolidation` to `spent`/`dormant` — the contract names
  the retirement condition; acting on it is a separate card.
- Re-enabling the paused fleet. Notion board status updates (done by hand after landing).
- Any change to `design/contract-schema.md` outside § Status.
- The `.claude/workflows/ship-dev-plan.js` constant and `tests/test_ship_dev_plan_workflow.sh`.

## Notes / preconditions

- Repo `~/dev/agent-workforce` on `main`, clean, at the T4.3 landing. Work on a branch
  `feat/t4-4-platform-contracts` (Phase 3 creates it; Phase 2 may create it first).
- `agent-workforce-auto-sync.timer` is DISABLED (fleet pause) — nothing will sweep the
  checkout into a commit mid-work. Do not re-enable.
- `check_deploy_drift.sh` reads `design/agents/*.toml` (line 95) for unit ownership only; adding
  `contract`/`contract_exempt` keys cannot make it red. `design/contracts/` is not deployed.
- Validator facts confirmed: file stem must equal one of the entry's units (`.service`/`.timer`
  stripped, brace-expanded); Owner row is the FIRST bold token(s) — write `**trajan**` only;
  Unit row tokens are read from backticks — write `` `fleet-turn-check.service` / `` `fleet-turn-check.timer` ``
  so both match the entry's `unit` value(s) exactly as the manifest spells them (check each
  entry's `unit =` — some name only the `.service`, some both; the tokens must equal the
  declaring entry's set, no more, no less).
- `kind = "service"` entries are exempt from check grading; none of the 14 is one.
- `scope = "user"` on `buzz-pr-watch` sets `SYSTEMCTL=systemctl --user` — its Identity table
  should say so and its checks must use `$SYSTEMCTL` unquoted-expansion-safe (`$SYSTEMCTL show`,
  not `"$SYSTEMCTL" show`).
- Timestamps: `--timestamp=unix` prints `@<epoch>`; strip with `${last#@}`. `n/a` renders as
  the literal `n/a` when never fired — handle before arithmetic.
- The dev-plan card convention is to record the landing commit in the T4.4 row after Phase 3;
  that edit belongs to the finish step, not the implement step.
