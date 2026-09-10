# Brief: T4.0 — executable acceptance-check syntax; convert knowledge-digest
**Date:** 2026-09-10   **Verify:** `bash bin/verify.sh` (redirect; ~200 KB) — exit 0, red lines
(`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal the baseline exactly (baseline on `main`: none)

Task bullet, `docs/dev-plan-2026-09.md:170`: *"Executable check syntax. Extend
`design/contract-schema.md` so every acceptance check carries a decidable command the executor
runs, given unit, `RUN_DATE`, run-log path and systemd properties. Convert `knowledge-digest.md`.
The validator enforces the syntax. Gate: validator green on the converted file; a prose-only
check fails it."* Size M, blocked by T1.4 (landed 2026-09-08). No deploy — nothing under `bin/`,
`systemd/`, `buzz-team/` moves, and `bin/check_deploy_drift.sh` does not cover `tests/` or
`design/`. Ships no red.

## Why

`design/contract-schema.md` already says contracts "are therefore written to be executable by D3,
not to be read as prose. Every `## Acceptance checks` line must be something a shell command can
decide." Nothing enforces that, and the two contracts written so far do not meet it: they name a
command in prose next to the assertion, which is not the same thing as carrying one. T5.1 builds
the executor; it needs a syntax to read and an environment contract to honour, and eighteen more
contracts (T4.1-T4.4) are written by as many sessions between now and then. The syntax lands
first, so every one of those is written against a rule that fails by name.

Converting the nine prose checks is not clerical. Three of them are wrong as prose, and the
conversion is what shows it (all measured 2026-09-10):

- Check 7 says the lock skip is caught by *"the run log for this trigger"*. `SKIP: previous run
  still active` is written by `agent_propose.sh:144` through `log()`, which tees to the shared
  `logs/agent_propose.log` **naming no job** — `2026-09-04T01:34:49+02:00 SKIP: previous run
  still active`, and nothing else on the line. That is T7.1's defect one layer over: a line in a
  shared stream that belongs to nobody. The unit's own journal is scoped by journald and is
  decidable; the shared file is not.
- Check 3 says *"body under 500 words, `wc -w` on the file body"*. The live artifact
  `_inbox/agents/2026-09-09_knowledge-digest.md` is **508 words whole and 499 without its H1
  title** — so the naive `wc -w < file` ships a red on a run that complied, and "body" has to
  mean something exact before it can be a check.
- Check 5 asserts the write boundary against `HEAD~1` of the inbox worktree. That worktree takes
  commits from every job: its HEAD right now is `2495b2a metrics: scorecard 2026-09-10`, three
  scorecard commits deep, none of them a digest. `HEAD~1` names whatever committed second-most
  recently, which on most days is not this run.

A check that cannot fail is not a check, and a check that decides the wrong thing is worse. The
syntax exists to make that visible at write time rather than at execution time.

## The syntax

A check is a list item under `## Acceptance checks` — prose stating the assertion and why —
carrying exactly one fenced block:

    ```check id=<slug> when=<vantage>
    <bash>
    ```

- `id` mandatory, `[a-z][a-z0-9-]*`, unique within the file. It is the stable name: receipts
  (T5.2), the morning report and the scorecard (T5.3) name a failed check by id, and prose
  elsewhere in the contract references checks by id, never by number.
- `when` optional, default `run`. Declared vantages: `run` (decided from inside the run that
  just finished) and `sweep` (decided from outside, on a cadence — the only vantage that can see
  a run that never happened). A check whose failure mode is "nothing ran" is `sweep` or it is
  vacuous.
- The block is bash. The executor runs it with `set -u`, **no `-e` and no `pipefail`** — this
  repo's gate has already paid once for `pipefail` under an early-exiting reader
  (`CLAUDE.md` § Verification), and these blocks are boolean conditions, which is exactly the
  shape that trap eats. The block's exit status is its last command's, so a multi-line block
  puts the decision last.
- **Exit 0 pass, 77 not applicable, anything else fail.** 77 is already this box's "green skip"
  (`bin/verify.sh` treats 0 and 77 alike). A check that does not apply to this run — every
  artifact check on a run that declined — must say so with 77, never by exiting 0, so a receipt
  can tell "passed" from "did not apply".
- Stdout is captured into the receipt; a check that decides a branch prints which.

The executor environment is declared in the schema doc as a bullet list and **read from there by
the validator**, not retyped — the same shape, and the same vacuity guard, as the eight section
names T1.4 already reads. `logs/agent_run.log` is deliberately not in it: one stream for every
job with no run boundary in it is what T7.1 removed from the decline check yesterday, and putting
it in the executor's vocabulary would invite it straight back.

Contracts for an always-on unit are exempt, by manifest join and not by their own prose: a
contract all of whose declaring `[[workflows]]` entries carry `kind = "service"` has no run —
no `RUN_DATE`, no attempt log, no `LastTriggerUSec` — for the executor to be given. That is
`buzz-interactive.md` and its five `buzz-agent@*` units, whose checks are executed by the fleet
gates instead. `kind` is not self-assertion: `tests/test_fleet_ownership.sh::kind-matches-unit-files`
already joins it against the unit files on disk. The exemption is printed as an `EXEMPT` line on
every run, never silently skipped.

## Acceptance criteria

1. `design/contract-schema.md` — `### `## Acceptance checks`` rewritten to carry the syntax
   above, plus two new `#### ` sub-blocks the validator parses:
   - `#### Executor environment` — one `- `VAR` — meaning` bullet per variable, each citing
     where it comes from: `UNIT`, `SYSTEMCTL`, `JOURNALCTL`, `RUN_DATE`
     (`bin/agent_propose.sh:317`), `AGENT_RUN_STARTED_AT` (`:34`), `AGENT_ATTEMPT_LOG` (`:192`),
     `AGENT_INBOX_DIR`, `INBOX_WORKTREE`, `VAULT`, `HOME`; and the sentence saying why
     `agent_run.log` is absent.
   - `#### Vantage` — `- `run`` and `- `sweep`` with what each can and cannot see.
   The eight `### `## X`` section headings are untouched (T1.4 counts exactly eight).
   `## Status` counts refreshed to the 2026-09-10 measurement (33 entries, 17 carry `contract`,
   12 distinct paths, 2 exist) — the file is being edited and its numbers are three weeks stale.
2. `design/contracts/knowledge-digest.md` — all nine checks converted, each with an `id`, a
   `when`, and a block that runs. The three corrections above are made **in the check and named
   in the prose**, so the contract records why the obvious formulation was wrong:
   `not-lock-skipped` reads the unit's journal since the timer's last trigger; `body-under-500-words`
   counts from line 2; `write-boundary-held` resolves the commit that added *this run's* file
   (`git log -1 --format=%H -- <rel>`) instead of `HEAD~1`. `## Known failure modes` references
   checks by id. Nothing else in the file changes.
3. `tests/test_contract_schema.py` — six new rules, ids as in `design/fleet-suites.toml`:
   - `checks-vocabulary` — the schema doc declares a non-empty executor environment and a
     non-empty vantage list. Without this the five rules below would grade every contract
     against an empty vocabulary and call the tree clean.
   - `checks-executable` — every list item under `## Acceptance checks` carries exactly one
     `check` block, and no `check` block sits outside one. **A prose-only check is named by its
     item number** — the plan's gate.
   - `checks-declared` — the info line parses: `check`, `id=<slug>` present, well-formed and
     unique in the file; `when=` only from the declared vantages; any other attribute named.
   - `checks-decidable` — the block is non-empty and not trivially true (`true`, `:`, `exit 0`,
     a bare `echo`). The schema's own rule: a check that cannot fail is not a check.
   - `checks-syntax` — `bash -n` accepts the block. The difference between "a fence exists" and
     "a command exists".
   - `checks-env` — every `$VAR`/`${VAR}` the block reads is either declared in the executor
     environment or assigned earlier in that same block (`x=`, `for x in`).
   All six are skipped, with an `EXEMPT` line, for a contract whose declaring entries are all
   `kind = "service"`. `SUMMARY` gains `checks=<blocks graded>` and `env=<vars declared>`.
4. `tests/test_contract_schema.sh` — `mk_contract` emits a conforming check block so the
   existing roots stay clean and the eleven-finding total is unchanged; a new group `1f` builds
   one root where each new rule has exactly one offender and asserts the total, plus a healthy
   contract carrying a `when=sweep` check and a 77 branch. Live-tree `check <id>` per new rule,
   anchored `(::id)`, and a `checks-graded` assertion that the number of blocks graded is
   `>= 9` — the vacuity guard for the live half, so a validator that found no blocks is red
   rather than quiet. Fixture output to a file, grepped, never printed on a pass.
5. `design/fleet-suites.toml` — the six ids plus `checks-graded` appended to the
   `tests/test_contract_schema.sh` suite's `asserts`, so
   `tests/test_workflow_coverage.sh::asserts-anchored` joins both ways.
6. TDD order: the `.sh` group 1f first (red on the missing rules), then the rules, then the
   live tree goes red on the unconverted `knowledge-digest.md`, then the conversion, then green.
7. `bash bin/verify.sh` exits 0 with no red lines.

## Files to modify

- `design/contract-schema.md` — the `## Acceptance checks` schema section, two new `#### `
  blocks, `## Status` counts.
- `design/contracts/knowledge-digest.md` — nine checks; id references in Known failure modes.
- `tests/test_contract_schema.py` — the six rules, the exemption, the summary fields.
- `tests/test_contract_schema.sh` — `mk_contract`, group 1f, the live-tree checks.
- `design/fleet-suites.toml` — the suite's `asserts`.

## Files to create

- `.claude/briefs/t4-0-executable-check-syntax.md` — this file, committed with the code.

## Test plan

- `bash tests/test_contract_schema.sh` → exit 0, no `FAIL:`.
- Mutation, the plan's gate literally: delete one check block from `knowledge-digest.md` →
  `checks-executable` names that item number; restore.
- Mutation: point a converted block at `$NOT_DECLARED` → `checks-env` names it.
- Mutation: replace a block body with `true` → `checks-decidable` names it.
- Each of the nine converted commands run by hand against the live box, with the branch it takes
  recorded in this brief's Notes. This is the only pass they get before T5.1 executes them.
- `bash tests/test_workflow_coverage.sh` green (the `asserts` join, both directions).
- `shellcheck -S error tests/test_contract_schema.sh`; `python3 -m py_compile`.
- `bash bin/verify.sh > $SCRATCH/verify.out 2>&1; echo $?` → 0; red-line count 0.

## Out of scope / do not touch

- The executor itself (T5.1) and its wiring (T5.2). This brief defines the syntax it reads and
  the environment it must export; it runs nothing on a schedule.
- Converting `buzz-interactive.md`. It is exempt by `kind = "service"`, and its checks 7-10 name
  `~/.config/buzz-agents/check-loaded.sh`, a path that moved to `agent-workforce/buzz-team/` on
  2026-09-06 — a real staleness, and not this task's.
- The ten missing contracts (T4.1-T4.4) and T1.1's red list.
- `bin/`, `systemd/`, `buzz-team/`, `bin/verify.sh`, `bin/check_deploy_drift.sh`,
  `tests/ci-expected-skips.txt`. No `bin/deploy`, no `sudo`, no systemd action.

## Notes / preconditions

Measured on the box 2026-09-10 unless stated:

- `systemctl show knowledge-digest.timer -p LastTriggerUSec --value --timestamp=unix` →
  `@1788678252` (Sun 2026-09-06 09:04:12 CEST). `LastTriggerUSecMonotonic` is `0` and useless
  here. A never-fired timer must be handled: the block requires an `@`-prefixed value.
- `journalctl -u knowledge-digest.service --since @<epoch>` works unprivileged (the account is
  in `adm`) and attributes `agent_propose.sh[...]` lines to the unit — which is what makes the
  lock skip decidable per unit at all.
- `bin/vault_sync_guard.sh check` prints `vault_sync_guard[check]: OK: …` on **every** success
  path (`:129`, `:137`) and `REFUSE:` on refusal, with `run_knowledge_digest_cc.sh:23` adding
  `knowledge-digest: REFUSING to run`. So the guard check asserts the OK line is **present**,
  not merely that the refusal is absent.
- The live artifact cites vault notes as `[[05_knowledge/...]]` wikilinks, not backticked paths;
  all four in the 09-09 digest resolve under `~/vault`. `## Confidence & gaps` is the last
  section, per `profiles/knowledge_digest_cc_task.md:52-78`.
- `knowledge-digest` has no `scope` field, so it is a system unit and `SYSTEMCTL` is bare
  `systemctl`. The five `buzz-agent@*` entries are the only `kind = "service"` rows in any
  manifest.
- 33 `[[workflows]]` entries, 17 carry `contract`, 12 distinct paths, 2 exist (buzz-interactive,
  knowledge-digest), 10 absent — T1.1's red list.
