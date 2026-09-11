# Brief: T4.5 — Make the contract field mandatory
**Date:** 2026-09-11   **Verify:** `bash bin/verify.sh` (bash -n + shellcheck -S error over `bin/` and `tests/*.sh`, `bin/check_deploy_drift.sh`, then every `tests/*.sh`; retries 1; escalate = print failing command + tail, change nothing else)
**Notion:** [T4.5 — Make the contract field mandatory](https://app.notion.com/p/3d48d7681ede8146a8bcec02ce95668f) — card still reads Blocked; its last blocker T4.4 landed `96c9019` (PR #31) and the dev-plan says "Next: T4.5".
**Isolation:** worktree `.claude/worktrees/t4-5-contract-field` on `feat/t4-5-contract-field-mandatory` — `current.md` is T7.2's slot (`3b3c0da`) and is not touched; this brief lands as its own file plus the archive copy, the way T4.4 did.

Dev-plan card: `docs/dev-plan-2026-09.md` § T4.5 (lines ~318-328) and § "T4.5 stays last"
(lines ~570-585). Schema: `design/contract-schema.md` § Status. Validator: T1.1's
`contract-exists` in `tests/test_workflow_coverage.py` (comment at ~233: "Resolves if present.
T4.5 flips this to present-and-resolves"), asserted by `tests/test_workflow_coverage.sh`, whose
assert ids are declared in `design/fleet-suites.toml` and joined both ways by `asserts-anchored`.

## Scope, as reviewed on the card

Half of the original T4.5 already landed (`063e6ce`, `outputs-actionability`). What remains is
the **manifest-side flip only**: every `[[workflows]]` entry must name a contract that resolves,
or carry `contract_exempt` with a named reason — and that exemption is accepted only for
`status = "spent"`. Plus the card's second gate clause: the 31 standing entries must reconcile
to 30 logical standing workflows with no unexplained duplicate (`augustus-content` and
`content-change-dispatch` are two triggers of one workflow, already declared as such by their
`logical_workflow` field). The valid no-output state stays in `## Decline conditions`; nothing
is added to `## Outputs`.

**Assumption stated:** "present" applies to every entry regardless of status, not only
standing ones. The card says "make the contract field mandatory" with `spent` as the sole
exemption, and today's manifests carry only `standing` and `spent` entries, so the live tree is
green either way; a future `planned` or `dormant` entry must therefore name its contract before
it is listed, which is the "field definition goes first" ordering the dev-plan argues for.

## Acceptance criteria

Verbatim gate from the card: **green with no exemption beyond the two spent entries; 31
standing manifest entries reconcile to 30 logical standing workflows without an unexplained
duplicate.** Concretely:

1. `tests/test_workflow_coverage.py` emits `PROBLEM<TAB>contract-declared<TAB>…` for any entry
   that carries neither a non-empty `contract` nor a non-empty `contract_exempt`, and for any
   entry that carries **both** (an exemption claimed for a promise that is named is two owners
   of one fact). The existing `contract-exists` keeps reporting a named path that is not a file.
2. It emits `PROBLEM<TAB>contract-exempt-spent<TAB>…` for a `contract_exempt` on an entry whose
   `status` is not `"spent"`, or whose reason is not a non-empty string.
3. Every accepted exemption is printed by name on every run as
   `CONTRACT_EXEMPT<TAB><unit><TAB><reason>`, and `SUMMARY` gains `contract_declared=<n>
   contract_exempt=<n>`; the `.sh` asserts named == counted (`contract-exempt-named`), the
   same shape as `exempt-named`. No hardcoded "2" anywhere — the rule "exempt only if spent"
   is what makes the number derived.
4. It reconciles **standing** entries by `logical_workflow` (default: the entry's own `unit`)
   and emits `PROBLEM<TAB>logical-workflow-reconciled<TAB>…` when: a `unit` value appears in
   more than one entry across the manifests; a `logical_workflow` names a unit no entry
   declares; or the entries of one logical workflow do not all name the same contract path.
   The report prints one line of the shape
   `standing reconciliation: 31 entries -> 30 logical workflow(s); 1 second trigger(s): content-change-dispatch -> augustus-content`
   and `SUMMARY` gains `standing_logical=<n>`. The `.sh` asserts, from figures it derives
   itself, that `standing - standing_logical` equals the number of second triggers the report
   names and that `standing_logical > 0` — so a deleted rule is red, not quiet.
5. `tests/test_workflow_coverage.py` takes an optional root argument (`sys.argv[1]`, default
   the repo root), exactly as `tests/test_contract_schema.py` already does, so the `.sh` can run
   it against mktemp fixtures. Every other read in the script is already `is_file()`-guarded, so
   a sparse fixture root (`design/agents/*.toml` + `design/contracts/*.md`) runs without a
   traceback.
6. `tests/test_workflow_coverage.sh` gains a fixture group that runs **before** the live-tree
   report: a healthy root (contract present and resolving; one spent entry with a reason; one
   two-trigger logical workflow sharing a contract) yields none of the four new ids, and an
   offending root yields each of `contract-declared` (missing; both present), `contract-exempt-spent`
   (standing with an exemption; spent with an empty reason) and `logical-workflow-reconciled`
   (duplicate unit; dangling `logical_workflow`; split contract) — asserted by exact count per
   id so a rule that stops firing is red rather than quiet. Fixture output goes to a file and is
   grepped, never printed.
7. The four new ids are declared in `design/fleet-suites.toml` under
   `tests/test_workflow_coverage.sh` with a one-line comment each, and anchored `(::id)` in the
   `.sh`, so `asserts-anchored` stays green in both directions.
8. On the live tree the report reads `contract join: checked 33 of 33 entries, 31 declared,
   2 exempt (spent), 0 missing file(s)` and the reconciliation line in criterion 4; zero
   `PROBLEM` lines for all four new ids; `SUMMARY … contract_declared=31 contract_exempt=2
   standing_logical=30`.
9. `design/contract-schema.md` § Status: the T1.1 sentence and the "coverage checker's answer"
   closing paragraph say the field is now **present and resolves** (T4.5, 2026-09-11), exempt
   only for `status = "spent"` with a reason, and that the standing entries are reconciled by
   `logical_workflow`. Overwrite the counted marker's sentence rather than adding a second
   count beside it.
10. `.claude/workflows/ship-dev-plan.js` `MISSING_CONTRACTS = []` stays unchanged; T1.1's
    `contract-exists` red list is still empty.
11. Gate green: `bash bin/verify.sh` exits 0. No `bin/` or `systemd/` file changes, so the
    drift check is unaffected and the branch can be green without a deploy.
12. `docs/dev-plan-2026-09.md` T4.5 row gains a `**DONE 2026-09-11, <sha>**` line in the
    style of T4.4's, and the "Next: T4.5" pointer moves to T5.1 — as a second, docs-only commit
    on the same branch once the feature commit's hash exists.

## Files to modify

- `tests/test_workflow_coverage.py` — `ROOT` from `sys.argv[1]`; the T1.1 block becomes
  present-and-resolves; the exemption rule; `CONTRACT_EXEMPT` lines; the standing
  reconciliation; report + SUMMARY fields.
- `tests/test_workflow_coverage.sh` — fixture builders + group, four `check`/`assert` lines
  with anchors, two derived-figure asserts.
- `design/fleet-suites.toml` — four ids appended to the suite's `asserts` list.
- `design/contract-schema.md` — § Status prose (two paragraphs).
- `docs/dev-plan-2026-09.md` — T4.5 DONE line (second commit).

## Files to create

- `.claude/briefs/t4-5-contract-field-mandatory.md` (this) and
  `.claude/briefs/archive/2026-09-11-t4-5-contract-field-mandatory.md` (copy, at finish).

## Test plan

1. **Red first.** Add the fixture group and the four anchored assertions to the `.sh`, and the
   four ids to `design/fleet-suites.toml`. Run `bash tests/test_workflow_coverage.sh`: the
   offender-count asserts FAIL (no such `PROBLEM` id is emitted yet), the reconciliation-figure
   assert FAILS (no report line), and `python3 tests/test_workflow_coverage.py <fixture>`
   ignores the argument. `asserts-anchored` stays green (ids declared and anchored).
2. **Green.** Implement in the `.py`. Re-run the suite: every assert `ok`, live tree emits the
   figures in criterion 8.
3. **Gate.** `bash bin/verify.sh` from the worktree root. Retries 1; on red print the failing
   command and the tail and stop.
4. **No-regression control.** `python3 tests/test_workflow_coverage.py | grep -c '^PROBLEM'`
   is 0 before and after on the live tree; `tests/test_ship_dev_plan_workflow.sh` and
   `tests/test_contract_schema.sh` still green (they read the same manifests).

## Out of scope / do not touch

- `## Outputs` fields and `outputs-actionability` — already landed, not re-opened.
- Any `design/contracts/*.md` or `design/agents/*.toml` edit — the tree already complies; the
  flip is safe only because nothing needs to change there. If a manifest edit turns out to be
  needed, that is a finding to report, not to make.
- `bin/control_room_api.py` — it reconciles by the same field for the UI; the gate is the
  earlier catch, and the two stay separate readers of one manifest field.
- `.claude/briefs/current.md` — T7.2's.
- `bin/`, `systemd/` — nothing to deploy.

## Notes / preconditions

- `gh` is not authenticated on this box; the branch is pushed and the PR is opened from the Mac.
- The Notion card was read through the fleet Notion broker socket (`notion_fetch`); its
  Status/Blocked-By are stale relative to the repo and are Dave's to update.
- The fixture root must carry `design/contracts/<stub>.md` so `contract-exists` does not fire
  beside the ids under test and muddy the per-id counts.
