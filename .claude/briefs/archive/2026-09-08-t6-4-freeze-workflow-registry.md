# Brief: T6.4 — freeze `design/workflow-registry.md` as the D1 record
**Date:** 2026-09-08   **Verify:** `bash bin/verify.sh` (redirect to a file; it is ~200 KB) — exit 0, red lines equal the baseline exactly (baseline on `main`: none)

Task bullet, `docs/dev-plan-2026-09.md:180`: *"`design/workflow-registry.md` is joined by no
test or script. Freeze it as the D1 record with a header pointing at the manifests. Gate:
header present, no live claim left in it."* Size S, no deploy, ships no red.

## Why

The registry was the D1 decision record (2026-09-01) and, at the time, the only place that
said which workflows exist. D2 moved that answer into `design/agents/*.toml`, and two suites
now join the manifests to the box — `tests/test_workflow_coverage.py` (every entry names a
unit, suite, owner, status) and `tests/test_fleet_ownership.sh` (manifests <->
`config/fleet-units.tsv`, both directions). Nothing joins the registry to anything, so it
kept reading as live while the fleet moved: W19 found rows `:77-78` still `keep` with live
triggers three days after the units were deleted (`design/open-decisions.md:14`). A registry
nobody joins against is prose, and prose does not get retired. The fix is (a) make the file
say what it is — a dated record — in a header that points at where the live answer lives,
and (b) give it the one join it can honestly have: a test that the header stays, its
pointers resolve, and no heading presents the content as current.

## Acceptance criteria

1. `head -30 design/workflow-registry.md` carries a header that (a) says the file is a
   **frozen** D1 record, (b) names `design/agents/` as where workflows are declared now, and
   (c) names the joins that replaced it: `config/fleet-units.tsv`,
   `tests/test_workflow_coverage.py`, `tests/test_fleet_ownership.sh`; open items go to
   `design/open-decisions.md`, contracts to `design/contracts/`. (The land agent's mechanical
   gate: `head -30 … | grep -qiE 'frozen|d1 record'` and `head -30 … | grep -q 'design/agents/'`.)
2. **No live claim left in the file** — every sentence or cell that reads as a statement about
   the box *now* is either dated to the freeze or rewritten as history. Specifically:
   - the opening paragraph's "this file is the single source of truth for which workflows
     exist" and "every box-owned timer is accounted for here" become past tense with the date;
   - no `##` heading carries `(live`, `(proposed)`, "must resolve" or "required from Dave" —
     they become "as recorded 2026-09-01" / "adopted" / "status as of" / "taken by";
   - §2's `Owner (prop.)` / `Decision (prop.)` columns become `Owner (§7, 2026-09-01)` /
     `Decision (2026-09-01)`; "All run headless…" becomes "At the freeze all ran…";
   - §6.2's "NOT YET ON THE BOX" and §6.5's "**Open:**" are dated and pointed at
     `docs/runbook.md` § W1 handoff / `design/open-decisions.md` as the tracked home;
   - the closing "Decision log" paragraph stays (already dated history).
   Content is **not deleted**: the file's own rule is that dated records are kept in order
   (§5, §7.6). Rows `:77-78` (the two campaigns) stay as they are — T6.2 owns their
   retirement note; under the frozen header they already read as a 2026-09-01 decision.
3. `tests/test_workflow_registry_frozen.sh` exists, runs in the `tests/*.sh` sweep, exits 0
   on the frozen file, and fails **by name** on each of three synthetic fixtures: no header,
   a heading that claims liveness, a header pointer that does not resolve on disk. It carries
   the repo's `assert()` (pipefail scoped off) and the `yes | grep -q y` canary.
4. `bash bin/verify.sh` exits 0 with no red lines (baseline: none). `bin/deploy` is not run —
   neither file is in a deployed tree, so the drift check is unaffected.

## Files to modify

- `design/workflow-registry.md` — new title + status header (within the first 30 lines);
  present-tense authority claims in the opening paragraph rewritten as dated history;
  section headings and the two §2 column headers de-lived as listed under criterion 2;
  §6.2 / §6.5 live-status sentences dated and pointed at their tracked homes. Every table
  row and every dated CORRECTION/RESOLVED note is kept verbatim.

## Files to create

- `tests/test_workflow_registry_frozen.sh` — header comment states why the join exists and
  what it does NOT assert (truth of the historical prose; it asserts the file cannot drift
  back into presenting itself as live). Checker functions, each printing offenders by name:
  - `header_missing FILE` — first 30 lines lack a `FROZEN` marker or lack `design/agents/`;
  - `live_headings FILE` — `^## ` lines matching `\(live|\(proposed\)|must resolve|required from`;
  - `unresolved_pointers FILE` — every backticked repo path in the first 30 lines that
    contains a `/` must exist relative to the repo root (`compgen -G` so `design/agents/*.toml`
    resolves as a glob; a trailing `/` is a directory).
  Groups: 0 canary; 1 fixtures (three failing, one healthy, in `$(mktemp -d)`, pointers in
  the healthy fixture name real repo paths); 2 the live file. `set -uo pipefail`, `exit $fail`.
  No box precondition — every checkout carries both inputs, so no `SKIP:` line and no change
  to `tests/ci-expected-skips.txt`.

## Test plan

- TDD order: write the suite first and run it — group 2 must be **red** on the current file
  (no `FROZEN` marker in the first 30 lines; `## 2 … (live)`, `## 3 … (live, deterministic)`,
  `## Ownership model (proposed)`, `## 6 … this freeze must resolve`, `## 7 Decisions required
  from Dave` all match). Then edit the registry until group 2 is green with group 1 unchanged.
- `bash tests/test_workflow_registry_frozen.sh` — exit 0, `FAIL:` count 0, and the three
  fixture assertions visibly named their offender.
- `shellcheck -S error tests/test_workflow_registry_frozen.sh` clean (the gate only
  shellchecks `bin/`, but the new suite should not be the first dirty one).
- `bash bin/verify.sh > "$SCRATCH/verify.out" 2>&1; echo $?` → 0; `grep -cE '^ *FAIL:|PROBLEM|DRIFT '`
  → 0 (drift red on the box would only mean the runtime is behind `main`, which this task does
  not touch and must not deploy).
- Land-agent gate reproduced locally:
  `head -30 design/workflow-registry.md | grep -qiE 'frozen|d1 record' && head -30 design/workflow-registry.md | grep -q 'design/agents/'` → 0.

## Out of scope / do not touch

- `design/agent-model.md:383-386` (§5 rule 1, "the registry names the workflow") and `:611`
  (§7 step 1, "every workflow in `workflow-registry.md` §2/§4 is claimed by exactly one
  manifest") still describe the registry as a live join input; with this freeze, the manifest
  names both. Not edited here: that file is T1.3's in this launch and the T6.4 gate is judged on
  the registry alone. Flagged for T1.3 / T6.2, whichever lands next on `design/`.
- `design/workflow-registry.md:77-78` retirement wording for the two campaigns — T6.2.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, any existing test, `tests/ci-expected-skips.txt`.
- `docs/dev-plan-2026-09.md` — status lives in Notion, the file owns scope only.
- `.claude/briefs/current.md` and `.claude/briefs/archive/` — belong to a live brief (T0.3);
  this brief is committed under its own name and not archived by `/finish`.
- No `bin/deploy`, no `sudo`, no systemd action of any kind.

## Notes / preconditions

- Confirmed: `grep -rn workflow-registry bin/ tests/` returns nothing — the file is joined by
  no script and no test on `main` at `2e7d0f9`.
- Confirmed: `design/agents/*.toml` = 5 manifests, 36 `[[workflows]]` entries counted by
  `grep -c` today (3+3+17+6+7); the feasibility brief measured 33 — do not write a count into
  the header, name the files.
- Confirmed: the manifests' own headers cite the registry for *ownership origin*
  (`marcus.toml:3` "frozen D1. Do not re-decide it here") — that reference is historical and
  stays correct after the freeze; nothing in this task edits a manifest.
- `bin/verify.sh` runs each `tests/*.sh` with `bash "$t"`; exit 0 or 77 is green, anything
  else is red. Suites without a box precondition print no `SKIP:` line.
- Worktree branch `worktree-wf_6796233d-567-1`; the land step fast-forwards `main`.
