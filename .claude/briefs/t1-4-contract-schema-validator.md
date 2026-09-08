# Brief: T1.4 — contract schema validator in the gate
**Date:** 2026-09-08   **Verify:** `bash bin/verify.sh` (redirect to a file; ~200 KB) — exit 0, red lines (`^\s*FAIL:|^PROBLEM\t|^\s*DRIFT `) equal the baseline exactly (baseline on `main`: none)

Task bullet, `docs/dev-plan-2026-09.md:79`: *"Contract schema validator in the gate: every
`design/contracts/*.md` carries the eight sections in order, Identity's owner equals the declaring
manifest, one contract per unit. Gate: green on the two existing contracts; a fixture missing a
section fails."* Size M, no deploy (nothing under `bin/`, `systemd/`, `buzz-team/` moves), ships
no red. T4.0 extends this validator with the executable-check syntax; T1.1 (contract path
resolves) is a separate rule in the coverage checker and is **not** built here.

## Why

`design/contract-schema.md` says "the owner here must match `design/agents/<owner>.toml` — that
is the one duplication in this design, and D3's validator exists to keep the two ends equal", and
no validator exists. Two contracts are written; ten more land in Phase 4 (T4.1–T4.4, 20 files
counting Trajan's), each by a different session. Without a gate rule, the eight-section shape,
the owner join and rule 1 (one contract per unit) hold by convention only — the same class W9
found in `asserts` (32 declared ids, 19 anchored nowhere). The validator lands before the
contracts do, so every one of them is written against a rule that fails by name.

## Acceptance criteria

1. `tests/test_contract_schema.py` — the validator. `python3 tests/test_contract_schema.py [ROOT]`
   (default: repo root) reads `ROOT/design/contracts/*.md` and `ROOT/design/agents/*.toml`
   (`tomllib`), always exits 0, prints a human report plus tagged lines
   `PROBLEM<TAB><id><TAB><detail>`, `EXEMPT<TAB><file><TAB><reason>`,
   `SUMMARY<TAB>contracts=N declared=M exempt=E`. Same protocol as
   `tests/test_workflow_coverage.py` so the `.sh` asserts per rule. Rules, each an id:
   - `manifest-parse` — a manifest that does not parse is named (the join below would silently
     shrink the owner set otherwise).
   - `sections-present` — the eight `## ` headings (`Identity`, `Trigger`, `Inputs`, `Outputs`,
     `Decline conditions`, `Side effects`, `Acceptance checks`, `Known failure modes`) each
     appear exactly once; a missing or duplicated one is named with the file. Headings inside
     fenced code blocks are ignored. Extra `##` sections are allowed
     (`buzz-interactive.md` carries `## The three obligations`).
   - `sections-ordered` — the present required headings appear in schema order; the first one
     out of place is named.
   - `sections-nonempty` — every required section has at least one non-blank line before the
     next `##` heading ("none" counts; an omitted body does not).
   - `contract-declared` — every `design/contracts/*.md` is named by at least one
     `[[workflows]].contract` in some manifest. An undeclared contract is a promise nothing
     joins. The three joins below are skipped for an undeclared file — the missing declaration
     is the finding.
   - `owner-matches-manifest` — the `## Identity` table row whose first cell is `Owner` or
     `Owners` carries the owners as bold tokens (`**claudius**`); the set of bold tokens equals
     the set of manifest stems that name this contract, both directions. No such row, or a
     bold token that is no manifest, is named.
   - `units-match-manifest` — the row whose first cell is `Unit` or `Units`, brace-expanded
     (`buzz-agent@{marcus,trajan}.service` → two units), every token ending `.service`/`.timer`
     with the suffix stripped, equals the set of `unit` values of the declaring entries, both
     directions.
   - `one-contract-per-unit` — across all manifests, no `unit` value is named by entries
     pointing at two different contract paths.
   - `named-for-unit` — the file stem is one of its declared units (rule 1), **or** the text
     before `## Identity` contains `breaks rule 1`, in which case an `EXEMPT` line names the
     file and the exemption is printed on every run, never silently skipped
     (`buzz-interactive.md` is the live case).
   Missing contract files named by a manifest are **not** reported (T1.1 owns that rule and
   ships red on the ten). No `(::id)` literal in the `.py`.
2. `tests/test_contract_schema.sh` — the entry point (`bin/verify.sh` globs `tests/*.sh`).
   `set -uo pipefail`, the repo's `assert()` (pipefail scoped off), the `yes | grep -q y`
   canary, `exit $fail`. Group 1: fixture roots under `$(mktemp -d)` — a healthy root (one
   single-unit contract + one shared two-unit contract that says it breaks rule 1) yields zero
   `PROBLEM` lines, one `EXEMPT` line, `contracts=2`; a broken root yields one named `PROBLEM`
   per rule (section missing, section duplicated, out of order, empty section, wrong owner, no
   owner row, wrong unit, undeclared file, misnamed file without the exemption, two contracts
   on one unit, a manifest that does not parse) and nothing else — the total is asserted.
   Fixture output goes to a temp file and is grepped, never catted on success, so no
   `PROBLEM\t` line reaches the gate output. Group 2: the live tree — `check <id>` per rule
   (anchored `(::id)`), `exempt-named` (EXEMPT lines == `exempt=` in SUMMARY),
   `validated-count` (`contracts=N` equals `ls design/contracts/*.md | wc -l` computed in bash,
   N ≥ 1). No box precondition, no `SKIP:` line, no change to `tests/ci-expected-skips.txt`.
3. `design/contracts/buzz-interactive.md` Identity row `| Owners |` names the five as bold
   tokens: `**marcus**, **claudius**, **augustus**, **trajan**, **aurelian**` — the one edit
   to a contract, making the declared duplication explicit so it can be joined.
   `knowledge-digest.md` passes unedited.
4. `design/fleet-suites.toml` gains a `[[suite]]` for `tests/test_contract_schema.sh`,
   `owner = "fleet"`, `asserts` = the ids above + `exempt-named` + `validated-count`, with a
   `why_no_workflow`. `tests/test_workflow_coverage.sh::asserts-anchored` then joins both ways.
5. `design/contract-schema.md` — one short dated paragraph under `## Rules` naming the
   validator, the Owner-row convention (bold tokens), the Unit-row convention (brace form for
   shared contracts), and the `breaks rule 1` exemption phrase. No rewrite of `## Status`.
6. TDD order: suite first — group 1 red on the missing `.py`, then green on fixtures while
   group 2 is red on `buzz-interactive.md`'s owner row; edit the row; green.
7. `bash bin/verify.sh` exits 0 with no red lines.

## Files to modify

- `design/contracts/buzz-interactive.md:26` — the `| Owners |` row, bold tokens for the five.
- `design/fleet-suites.toml` — append the `[[suite]]` block.
- `design/contract-schema.md` — the validator paragraph under `## Rules`.

## Files to create

- `tests/test_contract_schema.py` — parser (`parse_contract`: sections by `##` heading, fenced
  blocks skipped; Identity table rows by first cell), manifest join (`contract path → [(stem,
  unit)]`), the rules, the report. `sys.argv[1]` is the root.
- `tests/test_contract_schema.sh` — fixtures + live run, as in criterion 2.
- `.claude/briefs/t1-4-contract-schema-validator.md` — this file, committed with the code.

## Test plan

- `bash tests/test_contract_schema.sh` → exit 0, `FAIL:` count 0.
- Mutation: delete the `sections-ordered` block from the `.py` → group 1's out-of-order
  fixture assert goes red (proves the fixture reaches the rule).
- `shellcheck -S error tests/test_contract_schema.sh` clean; `python3 -m py_compile`.
- `bash tests/test_workflow_coverage.sh` green after the fleet-suites entry (both join
  directions; `asserts-join-counted` still holds).
- `bash bin/verify.sh > "$SCRATCH/verify.out" 2>&1; echo $?` → 0;
  `grep -cE '^ *FAIL:|^PROBLEM	|^ *DRIFT '` → 0.

## Out of scope / do not touch

- T1.1's rule (contract path resolves; ships red on ten). `tests/test_workflow_coverage.py`
  is not edited.
- T4.0's check syntax; `## Status` in `contract-schema.md` (stale counts — T4.x's to fix).
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, existing tests, `tests/ci-expected-skips.txt`,
  `.claude/workflows/ship-dev-plan.js`.
- `.claude/briefs/current.md` and `.claude/briefs/archive/` — belong to a live brief (T0.3).
- No `bin/deploy`, no `sudo`, no systemd action.

## Notes / preconditions

- Measured 2026-09-08: 33 `[[workflows]]` entries, 17 carry `contract`, 12 distinct paths, 2
  exist. `buzz-interactive.md` is named by five manifests (units `buzz-agent@{marcus,claudius,
  augustus,trajan,aurelian}`); `knowledge-digest.md` by claudius (unit `knowledge-digest`).
  No unit appears in two entries. `augustus-content.md` (absent) is named by two units of one
  manifest — the future shared-contract case the Units-row brace form is for.
- `buzz-interactive.md` headings: the eight in order plus `## The three obligations` between
  Outputs and Decline conditions (with `###` children). Its preamble says "breaks rule 1".
- `knowledge-digest.md` Identity: `| Owner | **claudius** (…) |`, `| Unit |
  `knowledge-digest.service` / `.timer` |` — the `.timer` token strips to empty and is dropped.
- Python 3.14 on the box; `tomllib` stdlib. `bin/verify.sh` runs each `tests/*.sh` with
  `bash "$t"`; exit 0 or 77 is green.
- `tests/test_workflow_coverage.py::suite_sources` follows a `python3 tests/<x>.py` invocation
  in command position, so the `.py` is in the anchor scan set: keep anchors in the `.sh` only.
- Worktree branch `worktree-wf_35f2ebd1-24d-1`; the land step fast-forwards `main`.
