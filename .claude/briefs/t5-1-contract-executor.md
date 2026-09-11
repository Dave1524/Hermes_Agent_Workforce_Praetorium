# Brief: T5.1 — contract executor and run receipt
**Date:** 2026-09-11   **Verify:** `bash bin/verify.sh` from the repo root

Source of scope: `docs/dev-plan-2026-09.md:322-341` (T5.1, phase 5, size L, dep T4.0 — Done).
Check syntax, executor environment and vantage: `design/contract-schema.md:92-160` — committed
on `main`, and **unchanged** by the T4.4 branch (`feat/t4-4-platform-contracts` rewrites only
`## Status` and adds contracts).
Receipt reader that already exists: `bin/control_room_api.py:29-32` (vocabularies) and
`:258-308` (`_validate_receipt`) — the T5.3 foundation slice. T5.1 writes what that reads.

Written in parallel with T4.4 so `/implement` can start the moment T4.4 merges. Nothing in
scope edits a file T4.4 touches (see Notes: branch base).

## Acceptance criteria

1. One executor, `bin/contract_exec.py`, runs every check of a unit's contract for one run
   and writes one receipt. It takes the unit name, the vantage (`run` | `sweep`) and the
   run's facts (artifact URI or state-change evidence; optional usage JSON; optional
   `--skipped <reason>`). Exit non-zero when any check fails or the run has no valid terminal
   outcome; zero otherwise. Stdout is the per-check result table; the receipt is the record.
2. **One result per check.** Every ```` ```check ```` block under the contract's
   `## Acceptance checks` is run as bash under `set -u` (never `-e`), in the environment the
   schema declares and nothing else. Exit 0 → `passed`, 77 → `not_applicable`, anything else
   → `failed`. Captured stdout+stderr lands in that assertion's `output`. A block whose
   `when=` does not match the vantage is recorded `not_applicable` with `reason: "vantage"`,
   never omitted — the receipt lists every check the contract declares, so a reader can tell
   "not run here" from "never written".
3. **Environment is exactly the schema's list.** The child sees `UNIT`, `SYSTEMCTL`,
   `JOURNALCTL`, `RUN_DATE`, `AGENT_RUN_STARTED_AT`, `AGENT_ATTEMPT_LOG`, `AGENT_INBOX_DIR`,
   `INBOX_WORKTREE`, `VAULT`, `HOME` (`design/contract-schema.md` `#### Executor
   environment`) plus `PATH`, and nothing else from the parent. `SYSTEMCTL`/`JOURNALCTL`
   derive from the manifest row (`scope = "user"` → `systemctl --user` / `journalctl --user`).
   The name list is read from the schema doc through the same function
   `tests/test_contract_schema.py` uses — one owner, so validator and executor cannot disagree.
4. **Exactly one terminal outcome, derived, never defaulted to success:**
   any `failed` assertion → `failed`; else a fresh `^DECLINE:` line in `$AGENT_ATTEMPT_LOG`
   (file newer than `AGENT_RUN_STARTED_AT`, the definition `bin/proposal_or_decline.sh:46-49`
   already uses) → `decline`; else an artifact URI or state-change evidence was supplied →
   `artifact`; else `failed` with `reason: "neither artifact nor decline"`. `skipped` only
   when the caller passes `--skipped` (the lock-skip path T5.2 will wire), with that reason
   and zero checks run. `terminal.reason` is set on every non-`artifact` outcome.
5. **The receipt** is written atomically (temp file + rename, same directory) to
   `$CONTROL_ROOM_RECEIPT_ROOT/<workflow_id>/<run_id>.json` — default
   `~/agent-workforce/var/workflow-receipts/`, the root `control_room_api.py` already globs —
   with `schema_version: 1`, and it passes `_validate_receipt` **unchanged**. Fields:
   `workflow_id` (manifest `logical_workflow`, else `unit` — the rule at
   `control_room_api.py:212`), `run_id`, `unit`, `agent` (manifest file stem), `model`
   (manifest `model`), `vantage`, `started_at` / `ended_at` (ISO-8601, UTC),
   `terminal {outcome, reason}`, `assertions [{id, when, status, reason?, output}]` with unique
   ids in contract order, `artifact {uri}` and/or `state_change {evidence}`, `usage`, `cost`,
   `next_action {actor, action}` copied from the contract's `## Outputs` **Next actor** /
   **Next action** bullets (`null` where the contract says `none`), optional `parent_run_id`
   and `handoff {actor, recipient, event}` passed through from flags. Silent success is
   impossible by construction: a receipt with no outcome cannot be written.
6. **Run identity preserves T7.1.** `run_id` is systemd's `$INVOCATION_ID` when present; else
   `<unit>-<AGENT_RUN_STARTED_AT>`; at vantage `sweep` it is
   `$SYSTEMCTL show <unit>.service -p InvocationID --value`. The attempt log is the per-run,
   per-job file; `logs/agent_run.log` is never read, per the schema's stated reason.
7. **Truthful usage and cost.** Default `usage {status: "unavailable", input_tokens: null,
   output_tokens: null, cache_tokens: null, total_tokens: null}` and `cost {status:
   "unavailable", amount: null, currency: null, source: null, confidence: null}`. `measured`
   only when `--usage-json <file>` is given and parses. Accepted shape: the Claude Code
   `claude -p --output-format json` envelope — `usage.input_tokens`, `usage.output_tokens`,
   `usage.cache_creation_input_tokens + usage.cache_read_input_tokens` → `cache_tokens`, their
   sum → `total_tokens`, `total_cost_usd` → `amount` with `currency: "USD"`, `source:
   "claude-code"`, `confidence` = `modelUsage.<model>.costBasis` (`"list"` today); the
   `modelUsage` key overrides `model`. A zero is written only when the runtime reported zero.
   A missing, empty or unparsable file → `unavailable`, never 0. `tokens=unknown` from
   `cost.log` is not an input and is never mapped.
8. Manifest rows with `kind = "service"` or `contract_exempt` are refused (exit 2, reason on
   stderr, no receipt) — those rows have no run to decide from, by the schema's own rule.
9. `bash bin/verify.sh` is green after `bin/deploy` has run (new `bin/` files are deploy
   drift until then).

Dev-plan gate wording: "green on knowledge-digest fixtures including checks 7-9; a run
producing neither a current artifact nor a valid decline fails; the receipt validates against
the declared workflow, carries truthful tokens and cost, and never renders unavailable usage
as zero." Criteria 2, 4, 5 and 7 are that gate; the test plan names a fixture for each clause.

## Files to modify

- `tests/test_contract_schema.py` — the check-block parser and vocabularies
  (`check_vocabulary` :128, `acceptance_checks` :259, `attrs_of` :293, `block_reads` :305)
  move to `bin/contract_checks.py`; this file imports them and keeps every rule, its
  `PROBLEM\t<rule>\t<detail>` output and its `::id` anchors unchanged. Why it moves rather
  than being imported: this file reads `ROOT` from `sys.argv[1]` and runs `schema_sections()`
  at import, so nothing can import it. Run `bash tests/test_contract_schema.sh` before and
  after; the `SUMMARY` line must be byte-identical.
- `bin/control_room_api.py` — `RECEIPT_SCHEMA_VERSION`, `TERMINAL_OUTCOMES`,
  `ASSERTION_STATUSES`, `MEASUREMENT_STATUSES` and the body of `_validate_receipt` move to
  `bin/workflow_receipt.py`; this file imports them (sibling import via
  `sys.path.insert(0, dirname(__file__))`, as its peers do). Behaviour identical;
  `tests/test_control_room_api.sh` stays green with no edits.
- `design/fleet-suites.toml` — one `[[suite]]` for `tests/test_contract_exec.sh`,
  `owner = "fleet"`, `asserts = [...]` naming the rule ids in the test plan, and a
  `why_no_workflow` (it tests the executor every workflow will call, not any one row). Every
  declared id must appear in the suite as a parenthesised `::`-id anchor and vice versa
  (W9, `tests/test_workflow_coverage.py:368-400`; precedent
  `tests/test_control_room_api.sh:2`).
- `docs/dev-plan-2026-09.md` — the T5.1 row: landed, date, and one line naming the two
  extractions (parser → `bin/contract_checks.py`, receipt schema → `bin/workflow_receipt.py`)
  so T5.2 reads the right owner.
- `CLAUDE.md` (repo) — one short paragraph: where run receipts live, the one-outcome rule, and
  that `unavailable` is a value the Control Room renders, not an absence. Note the two other
  "receipt" files it must not be confused with (`bin/delivery_receipt.py`, `bin/run_record.sh`).

## Files to create

- `bin/contract_checks.py` — single owner of check-block parsing. Given a contract's text,
  returns the numbered items of `## Acceptance checks` and each fenced ```` ```check ````
  block (`id`, `when`, body, source line, the item it sits under); given the schema doc path,
  returns the executor-environment names and the vantage names. Pure functions; no argv, no
  I/O beyond the paths it is handed.
- `bin/workflow_receipt.py` — receipt schema v1 as data, `validate(receipt) -> list[str]`
  (moved from `control_room_api.py`), `write(receipt, root) -> Path` (atomic),
  `unavailable_usage()` / `unavailable_cost()`, and `usage_from_claude_code(envelope) ->
  (usage, cost, model)`. The one place that knows the field names.
- `bin/contract_exec.py` — the executor CLI (criteria 1-8). Reads the manifest row from
  `design/agents/*.toml` (`unit`, `scope`, `kind`, `logical_workflow`, `contract`, `model`,
  `contract_exempt`); loads the contract; builds the child env; runs blocks; derives the
  outcome; writes the receipt; prints the table; exits. Overrides so fixtures never touch
  live paths: `--manifest-dir`, `--schema-doc`, `--receipt-root`, `--attempt-log`,
  `--inbox-worktree`, `--vault`, `--home`, `--now`, `--run-started-at`, `--run-date`.
- `tests/test_contract_exec.py` — the fixture suite (test plan below), importing the three
  `bin` modules via `importlib.util.spec_from_file_location` like its siblings.
- `tests/test_contract_exec.sh` — wrapper: `set -uo pipefail; cd "$(dirname "$0")/..";
  python3 tests/test_contract_exec.py`, header comment carrying the `::` anchors (or anchor
  them in the `.py` — the join reads both).
- `tests/fixtures/contract-exec/` — `agents/fixture.toml` with a `knowledge-digest`-shaped
  row, a `scope = "user"` row, a `logical_workflow` row, a `kind = "service"` row and a
  `contract_exempt` row; fake `systemctl` and `journalctl` on `PATH` (precedent:
  `tests/test_brave_status.sh`, `tests/test_buzz_deliver.sh`) answering
  `show … LastTriggerUSec`, `show … InvocationID`, `is-active` and `--unit … --since` from
  files the test writes; a tiny contract with a check that reads a forbidden variable;
  `claude-json-envelope.json`, a real `claude -p --output-format json` result captured
  2026-09-11 (Haiku; `total_cost_usd` 0.0555477; full `usage` and `modelUsage` maps). The
  suite runs the **live** `design/contracts/knowledge-digest.md`, not a copy, so the
  fixtures cannot drift from the contract.

## Test plan

One rule id per bullet; each is a `::` anchor in the suite and an entry in `fleet-suites.toml`.

- `exec-one-result-per-check` — `knowledge-digest` at vantage `run` yields exactly nine
  assertions, in contract order, with the contract's ids; the two `when=sweep` checks are
  `not_applicable` / `reason: vantage`; at vantage `sweep` the seven `run` checks are.
- `exec-env-is-schema-list` — a fixture check reading `$SECRET_PROBE` (set in the parent)
  sees it unset; the child env key set equals the schema list + `PATH`; `SYSTEMCTL` is
  `systemctl --user` for the `scope = "user"` row and bare `systemctl` otherwise; the list
  comes from the schema doc (edit a copy of the doc, the list follows).
- `exec-artifact-is-this-run` (class: artifact is this run's) — check 1 passes when
  `<RUN_DATE>_knowledge-digest.md` is newer than `AGENT_RUN_STARTED_AT`; fails on
  yesterday's file with the same name.
- `exec-decline-is-own` (class: sentinel branch) — check 2 passes on a fresh `^DECLINE:` in
  the attempt log; fails on a stale one; fails when the DECLINE sits in another job's log;
  outcome is `decline` and `terminal.reason` quotes the line.
- `exec-write-boundary` (class: write boundary) — check 5: a stray file outside
  `_inbox/agents/` in the inbox worktree fails; a clean tree passes.
- `exec-lock-skip` (class: lock skip; check 7) — fake `journalctl` emitting
  `SKIP: previous run still active` since the last trigger fails; a clean journal passes; a
  timer that never fired fails and the check's own message is in `output`.
- `exec-timer-window` (class: timer fired within window; check 8) — `LastTriggerUSec` inside
  the week passes, outside fails, `n/a` fails.
- `exec-input-freshness` (class: input freshness; check 9 `vault-guard-passed`) — fresh
  passes, stale fails, with the fixture's own `vault-guard` marker.
- `exec-outcome-is-exactly-one` — neither artifact nor decline → `failed` /
  `neither artifact nor decline` / exit ≠ 0; artifact + all passed → `artifact` / exit 0;
  artifact + one failed assertion → `failed`; `--skipped "lock held"` → `skipped` with that
  reason, zero assertions run, exit 0; a receipt can never carry two outcomes.
- `exec-receipt-validates` — every receipt the suite writes passes
  `workflow_receipt.validate` **and** is returned under `valid` (not `malformed`) by
  `control_room_api`'s `receipts()` when pointed at the fixture root; `workflow_id` for the
  `logical_workflow` row is the logical id; the file lands at
  `<root>/<workflow_id>/<run_id>.json`; an exception raised mid-write leaves no partial file.
- `exec-run-identity` — `INVOCATION_ID` in the env becomes `run_id`; absent, it is
  `<unit>-<AGENT_RUN_STARTED_AT>`; at `sweep` it is what the shim's `InvocationID` says.
- `exec-usage-never-zero` — no `--usage-json` → `usage.status == "unavailable"` with all four
  token fields `null`, `cost.amount` `null`; the captured envelope → `measured` with its exact
  integers and `amount == 0.0555477`, `currency == "USD"`, `model` from `modelUsage`; an
  envelope with `usage: {}` → `unavailable`, not zeros; the serialised receipt contains no
  `0` token value unless the envelope said 0.
- `exec-next-action-from-contract` — `next_action` equals knowledge-digest's **Next actor**
  / **Next action** bullets; a contract saying `none` yields `null`.
- `exec-refuses-non-contract-rows` — `kind = "service"` and `contract_exempt` rows exit 2 with
  the reason on stderr and write no receipt.
- Regression: `bash tests/test_contract_schema.sh` prints the same `SUMMARY` before and after
  the parser move; `bash tests/test_control_room_api.sh` green after the schema move.
- Live smoke, once, recorded in the commit message rather than gated:
  `python3 bin/contract_exec.py knowledge-digest --vantage sweep --receipt-root
  "$CLAUDE_JOB_DIR/tmp/receipts"` on the box, then `python3 bin/control_room_api.py`
  pointed at that root lists the run.

## Out of scope / do not touch

- **T5.2** — wiring `agent_propose.sh` / the CC runners to call the executor, and switching
  any runner to `--output-format json`. The executor *accepts* the envelope; nothing produces
  one yet. Do not edit `bin/agent_propose.sh`, `bin/run_*_cc.sh`, `bin/proposal_or_decline.sh`,
  `bin/run_record.sh`, `bin/deliver_proposal.sh`.
- **T4.4 / T4.5** — `design/contracts/*.md`, `design/agents/*.toml`, `design/contract-schema.md`,
  and the *rules* in `tests/test_contract_schema.py`. Read only. If a T4.4 check block fails
  to parse or fails live, report it in the commit message; do not fix the contract.
- **T5.3 API shape** — no new endpoints; `_run_summary`'s output keys stay as they are.
- `bin/delivery_receipt.py` (delivery receipts, JSONL) and `bin/run_record.sh` (`cost.log`
  records) share a word with this receipt and nothing else; leave them.
- The live receipt root under `~/agent-workforce/var/`; fixtures use temp roots only.
- `.claude/briefs/current.md` in the **main** checkout while the T4.4 session still holds it.

## Notes / preconditions

- **Branch base.** `feat/t4-4-platform-contracts` is pushed (`96c9019` at writing) and adds
  14 contracts (12 on `main` → 26). Start from `origin/main` once it has merged; if it has
  not, base on that branch — T5.1 needs its contracts only as *inputs* and edits none of its
  files, so either base gives the same diff.
- **The contract set at writing (T4.4 branch):** 26 contracts; 11 carry `run`-vantage checks
  (`knowledge-digest` 9 checks / 2 sweep, `augustus-content` 10/4, `bd-followup-drafts` 12/3,
  `bd-stall-radar` 12/3, `m1-signal-scan` 11/3, `overnight-morning-report` 8/2,
  `praetorium-daily-plan` 9/2, `praetorium-eod-summary` 9/2, `raw-ingest` 12/2,
  `standing-research` 10/2, `weekly-pre-assembly` 8/2); the other 15 are light contracts with
  exactly two `sweep` checks. Live checks read `$SYSTEMCTL`, `$JOURNALCTL`,
  `$INBOX_WORKTREE`, `$AGENT_ATTEMPT_LOG`, `$AGENT_INBOX_DIR`, `$RUN_DATE`, `$HOME/logs/…`.
- **Env defaults** are the schema's: `AGENT_INBOX_DIR = $INBOX_WORKTREE/_inbox/agents`,
  `INBOX_WORKTREE = $HOME/agent-worktrees/inbox`, `VAULT` = `readlink -f ~/vault` (a symlink;
  record the target, never the link), `RUN_DATE` / `AGENT_RUN_STARTED_AT` / `AGENT_ATTEMPT_LOG`
  from the parent env when the runner exported them, else derived from `--now` / the flags.
  `PATH` is not in the schema list but must reach the child or `grep`/`find` in checks cannot
  run; the "nothing else" rule is about the *parent's* variables.
- **Why the parser moves to `bin/`.** `bin/` is deployed, `tests/` is not
  (`bin/deploy` `PATHS=(bin profiles docs CLAUDE.md AGENTS.md README.md config systemd skills)`),
  and the executor runs from the deployed tree, so it may only import from `bin/`. Two parsers
  would be the D6 class of defect the repo already names; the validator keeps its rules and
  loses only the parsing.
- **Why the receipt schema moves.** `control_room_api.py` owns the field names today; the
  executor must write exactly what that reads. Move, do not copy.
- **Declines.** "Fresh" is `bin/proposal_or_decline.sh`'s definition — attempt log newer than
  `AGENT_RUN_STARTED_AT` and containing `^DECLINE:`. Re-implement it in Python; do not shell
  out to the script (it exits non-zero on its failure branch and is T5.2's caller, not ours).
- **Cost source.** The only structured usage on this box is the `claude -p --output-format
  json` envelope (`total_cost_usd`, `usage.*`, `modelUsage.<model>.{costUSD, costBasis}`).
  OpenRouter's `cost_usd_delta` in `cost.log` is a key-balance diff — the frozen `0.000000`
  the dev plan calls a defect; never map it.
- **`next_action`** has no section of its own: it is the **Next actor** / **Next action**
  bold-label bullets under `## Outputs` (`design/contract-schema.md:66-68`), the labels
  `tests/test_contract_schema.py` `outputs_fields()` already reads from the schema doc.
- `bin/check_deploy_drift.sh` is red until `bin/deploy` ships the three new `bin/*.py`;
  run `bin/deploy` (no sudo needed for scripts) before the final `bash bin/verify.sh`.
- Copy this file to `.claude/briefs/current.md` in the checkout you implement from; the
  branch commits only the named brief, matching how the other briefs in this directory travel.
