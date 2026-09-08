# Brief: T6.2 — W19, the design and profiles half
**Date:** 2026-09-08   **Verify:** `bash bin/verify.sh > "$SCRATCH/verify.out" 2>&1` (it is ~200 KB; read it with grep/tail) — exit 0, red lines equal the baseline exactly (baseline on `main`: none)

Task bullet, `docs/dev-plan-2026-09.md:172-175`: *"W19, the design and profiles half:
`design/workflow-registry.md:77-78`, `design/eval-spec.md:166-167`, `augustus.toml`'s scheduled
surface (`present = false` or a stated reason), the two `profiles/` task files declared
runtime-only, the W19 row updated. Gate: verify green; the brief's check 2 grep returns only
historical notes."* Size M, no deploy, ships no red. The parent brief is
`.claude/briefs/w19-campaign-retirement-residue.md` (2026-09-04); this one executes its
items 1-3, 5, and the `profiles/` half of 4, and inherits its check 2.

Land gate (`.claude/workflows/ship-dev-plan.js`, T6.2): `grep -A3 'surfaces.scheduled'
design/agents/augustus.toml | grep -qE 'present *= *false|reason' && [ $(grep -c
'^\[\[runtime_only\]\]' design/deploy-exclusions.toml) = 11 ]`, then a judgement of: *"the
check 2 grep returns only historical notes; registry rows 77-78 and eval-spec 166-167 read as
history; W19 row updated"*.

## Why

The 2026-09-04 retirement (`1bc6a4c`) touched the two files a test forced it to touch and
nothing else; eleven pieces of residue survived, five of them a closed executable chain. The
`bin/` links of that chain cannot go without `bin/deploy --prune` (T6.3, Dave's moment). Every
other piece is `design/` or `profiles/` and can land green now. One of the eleven — *"no test
asserts a present surface has workflows"* (W19 table, item 10) — is a missing join, and this
task adds it, so the next retirement that empties a surface fails by name instead of leaving
`present = true` over nothing.

Two decisions taken in earlier briefs govern the shape here:

- **Registry rows stay; they get a retirement note.** The 09-04 brief said remove them. T6.4
  (09-08) then froze the file with the rule that dated content is kept in order, and wrote
  *"Rows `:77-78` stay as they are — T6.2 owns their retirement note"*. The later decision
  wins. The rows are now `:108-109`.
- **`bin/` is untouched.** Any edit there — even a comment in the two shims or the help-string
  example at `bin/notion_research_page.py:144` — is `content differs` in the drift check until
  `bin/deploy` runs, which this task does not. Those four hits are T6.3's.

## Acceptance criteria

1. `design/workflow-registry.md`: rows `:108-109` keep every cell and gain a footnote marker
   `⁴` on the Decision cell; footnote `⁴` (after `³`) and a dated **RETIRED 2026-09-04** note
   (after the §6.5 CORRECTION paragraph) record the retirement; §7 item 3 gains a `→` line in
   the file's own convention. First 30 lines untouched; no `##` heading changes;
   `tests/test_workflow_registry_frozen.sh` stays green.
2. `design/eval-spec.md`: rows `:166-167` removed and replaced by a dated note under the
   table; the "four suites" backlog paragraph is followed by a dated re-measurement stating
   the checker's current figure (`27 of 29 own a suite, 2 exempt, 0 uncovered`, measured
   2026-09-08) — the "real hole" rows stay as the record of why each was one.
3. `design/agents/augustus.toml`: `[surfaces.scheduled]` reads `present = false` on the line
   after the header, `retired = "2026-09-04"`, keeps `governed_by`/`tools`/`mcp` with a comment
   saying the runner is T6.3's residue, and its `notes` are history. The `augustus-content`
   notes describe the 01:30 collision in the past tense with the date and the word retired.
   The file parses under `tomllib`; no `[[workflows]]` entry changes.
4. `profiles/standing_research_content_strategy_task.md` and
   `profiles/standing_research_faceless_content_task.md` deleted from source (`git rm` by
   path; never `git mv`), and declared in `design/deploy-exclusions.toml` as two
   `[[runtime_only]]` entries (`tree = "profiles"`, `since = "2026-09-08"`), taking the count
   from 9 to exactly 11. `bin/check_deploy_drift.sh` reports both as
   `runtime-only: profiles/… — declared in design/deploy-exclusions.toml, pending bin/deploy --prune`
   (info, not a finding) and ends `drift: clean`.
5. `tests/test_manifest_surfaces.sh` exists, runs in the `tests/*.sh` sweep, is registered in
   `design/fleet-suites.toml` with anchored `asserts`, is **red on the current augustus.toml**
   (names `augustus.toml: [surfaces.scheduled]`) and green after criterion 3.
6. `design/open-decisions.md` W19 row carries a dated status paragraph: what landed (this
   task), what remains (T6.3's `bin/` half; Dave's two envs), and the exact remaining check 2
   hits with why each is historical. Pending actions for Dave gain item 3: delete the two
   campaign override envs.
7. Check 2, split by tree: `grep -rn 'content-strategy\|faceless-content' design/ profiles/
   config/` returns only lines that are dated history (see the expected list under Test
   plan); over `bin/` it returns exactly the four T6.3 hits, unchanged.
8. `bash bin/verify.sh` exits 0 with no red lines. No `bin/deploy`, no `sudo`, no systemd
   action.

## Files to modify

- `design/workflow-registry.md`
  - `:108` and `:109` — Decision cell `keep` → `keep ⁴`. Nothing else in the row.
  - after footnote `³` (ends `:120` "headless CC.") add
    `⁴ Retired 2026-09-04 (W19): the campaign fired its last declared run and its unit files
    were deleted the same day. Row kept as the 2026-09-01 record; RETIRED note below.`
  - after the `**CORRECTION 2026-09-01 (D2 §6.5).**` paragraph (ends `:140` "…not rows in the
    standing-workflow table.") add one paragraph:
    `**RETIRED 2026-09-04 (W19; recorded 2026-09-08, T6.2).** Both campaigns spent their four
    make-up nights — last runs 2026-09-03 23:00 and 2026-09-04 01:30 — and
    `praetorium-content-strategy-research.{service,timer}` and
    `praetorium-faceless-content-research.{service,timer}` were deleted from `/etc` the same
    day (`1bc6a4c`). Nothing in this file describes them now: `design/agents/augustus.toml`
    records the retirement, `design/open-decisions.md` W19 the residue it left.`
  - `:305` (§7 item 3) — append a line in the item-6 convention:
    `   → Both campaigns expired on schedule and were retired 2026-09-04 (W19); the ownership
    decision stands as the record.`
- `design/eval-spec.md`
  - delete `:166-167` (the two `campaign` rows).
  - after the table (blank line, before "So the honest backlog…") add:
    `*Two `campaign` rows — `praetorium-content-strategy-research` and
    `praetorium-faceless-content-research`, bounded, needing no standing suite — were removed
    2026-09-08 (T6.2): both expired on schedule and were retired 2026-09-04 with their unit
    files (W19).*`
  - after the paragraph ending "The four are the number to track; 22/28 is not." add:
    `**Re-measured 2026-09-08 (T6.2): the backlog is zero.** `bash
    tests/test_workflow_coverage.sh` prints `27 of 29 own a suite, 2 exempt, 0 uncovered` —
    each of the four named above has a suite now, and the two campaign rows left the
    denominator with their retirement. The "real hole" rows above stay as the record of why
    each was one; the live figure is the checker's output, never this paragraph.`
- `design/agents/augustus.toml`
  - `:31-40` → 
    ```
    [surfaces.scheduled]
    present     = false
    retired     = "2026-09-04"       # W19. Block kept, not deleted — the kanban block below is the precedent (agent-model.md §3).
    governed_by = "bin/run_standing_research_topic_cc.sh"   # still in bin/ until T6.3's prune; reachable by nothing since the units went
    tools       = ["Bash", "Read", "Write", "Glob", "Grep", "WebSearch", "WebFetch"]
    mcp         = []
    notes       = """
    Hosted exactly two workflows — the D5 research campaigns praetorium-content-strategy-research
    and praetorium-faceless-content-research — and nothing since they were retired 2026-09-04
    with their unit files (comment above the S1 entry below). What ran here: headless Claude
    Code on Opus 5, AGENT_RUN_MODE=ops, no Edit, no delivery step; the executor was never
    codex, and augustus was the accountable owner, not the runtime (registry §7.3). A new
    scheduled workflow for augustus reopens this surface with present = true and its own
    runner; it does not inherit this tool list unexamined.
    """
    ```
  - `:75-79` (augustus-content notes) →
    `Shares AGENT_JOB_OVERRIDES and DELIVERY_TASK with content-change-dispatch below: they are
    two triggers on ONE workflow, not two workflows. Until 2026-09-04 it collided at 01:30 with
    praetorium-faceless-content-research over the global propose lock (agent-model.md §6.6
    keeps the record); that campaign is retired and the slot is its own.`
  - `:93-99` comment — append: `# The scheduled surface above is present = false from the
    same date (recorded 2026-09-08, T6.2).`
- `design/deploy-exclusions.toml`
  - `:32` "this file becomes nine findings" → "this file becomes one finding per entry".
  - append a comment block and two entries:
    ```
    # The two below are W19's profiles half (T6.2, 2026-09-08). The D5 research campaigns that
    # read them were retired 2026-09-04 with their /etc units; the profiles left source four
    # days later and the runtime keeps them until the next --prune. Their runner chain in bin/
    # (run_content_strategy_cc.sh, run_faceless_content_cc.sh, run_standing_research_topic_cc.sh)
    # is NOT declared here: the bin half of the drift check consults no exclusion, so those go
    # with the prune itself (T6.3).

    [[runtime_only]]
    path  = "standing_research_content_strategy_task.md"
    tree  = "profiles"
    since = "2026-09-08"          # T6.2 — W19 profiles half
    why   = "Task profile of praetorium-content-strategy-research, a bounded D5 campaign retired 2026-09-04 with its unit. Read only by bin/run_standing_research_topic_cc.sh, which nothing can reach since the unit went."

    [[runtime_only]]
    path  = "standing_research_faceless_content_task.md"
    tree  = "profiles"
    since = "2026-09-08"          # T6.2 — W19 profiles half
    why   = "Task profile of praetorium-faceless-content-research, the sibling campaign, retired 2026-09-04 with its unit. Same runner, same reachability: none."
    ```
- `design/open-decisions.md`
  - W19 row (`:10-14`): insert, after the `*Opened:*` line, a paragraph
    `**Design and profiles half landed 2026-09-08 (T6.2).** Registry rows footnoted `⁴` with a
    dated RETIRED note (rows kept — the file is frozen, T6.4); eval-spec rows removed with a
    dated note and the backlog re-measured at zero; `augustus.toml` `[surfaces.scheduled]`
    `present = false`, `retired = "2026-09-04"`, the 01:30 collision note past tense; the two
    task profiles deleted from source and declared in `design/deploy-exclusions.toml` (eleven
    entries); `tests/test_manifest_surfaces.sh` now fails a `present = true` surface that hosts
    no workflow, which is the join item 10 lacked. **Still open:** the `bin/` half — three
    runner scripts plus the help-string example at `bin/notion_research_page.py:144` — goes
    with `bin/deploy --prune` at Dave's chosen moment (T6.3), which clears every exclusion
    entry in the same act; and items 1-2, the two override envs, Dave-only (pending action 3).
    Remaining check 2 hits outside `bin/` are all dated history: `agent-model.md` §6.5-6.7,
    `workflow-registry.md` rows + notes + §7.3, `phaseb-brief-queue.toml` (2026-09-01
    measurements, queue spent), `augustus.toml` retirement comment, and `design/archive/`.`
  - same row, "clears nine deferred exclusions" → "clears every entry in
    `design/deploy-exclusions.toml` (eleven since T6.2)".
  - Pending actions: "Both are blocked on a deny-listed path" → "All three are blocked on a
    deny-listed path"; add
    `3. **Delete the two campaign override envs** (W19 items 1-2):
    `rm ~/.config/agent-workforce/content_strategy.env ~/.config/agent-workforce/faceless_content.env`.
    Both are `AGENT_JOB_OVERRIDES` for units deleted 2026-09-04; no surviving unit names
    either path. Safe now; do it before T6.3's prune, or the shims' headers stop describing
    what is on disk.`
- `design/agent-model.md` (the lines T6.4 flagged for "T1.3 / T6.2, whichever lands next";
  T1.3 landed and did not take them)
  - `:381` "Live totals:" → "Totals at D2 (2026-09-01):"; append after the sentence ending
    "not absent.": `The two `campaign` entries were retired 2026-09-04 (W19);
    `tests/test_workflow_coverage.sh` prints the live totals.`
  - `:388-390` rule 1 → `**The manifest names the owner and the workflow.** A workflow appears
    in its owner's manifest and nowhere else claims ownership; two claims is the defect, not a
    redundancy. Until 2026-09-08 the registry named the workflow too — it is the frozen D1
    record now (T6.4), and the manifests are the only list.`
  - `:621-622` step 1: after "claimed by exactly one manifest" insert " (the registry froze
    2026-09-08, T6.4 — the manifests are the only list now)".
  - §6.5 (`:495`, after the heading): first paragraph becomes
    `**RETIRED 2026-09-04 (W19).** Both campaigns fired their last declared runs (09-03 23:00,
    09-04 01:30) and their unit files were deleted from `/etc` the same day. The section below
    is the 2026-09-01 record of why they were left alone to expire.`
  - §6.6, after the paragraph ending "…an opt-out global one." (`:562`): add
    `*The 01:30 collision ended 2026-09-04 with the faceless campaign's retirement (W19); the
    lock mechanism it demonstrated is unchanged.*`
- `design/phaseb-brief-queue.toml` — after `:10` ("Brief 1 … not in this queue.") add
  `# Queue spent: every brief below landed by 2026-09-04. The two campaign units the entries
  # name were retired 2026-09-04 (W19); every "still firing" below is a 2026-09-01
  # measurement, kept as written.`
- `design/fleet-suites.toml` — append an entry for the new suite, same shape as the T1.4
  entry: `path = "tests/test_manifest_surfaces.sh"`, `owner = "fleet"`, `asserts` =
  `manifest-parse-named`, `present-surface-hosts-work`, `retired-surface-silent`,
  `why_no_workflow` (it grades the manifests' internal agreement; nothing schedules it).

## Files to delete

- `profiles/standing_research_content_strategy_task.md`
- `profiles/standing_research_faceless_content_task.md`

## Files to create

- `tests/test_manifest_surfaces.sh` — header comment: W19 item 10 was a `present = true`
  surface over zero workflows that no check compared; this suite is that join, one direction
  only (a present surface must host at least one `[[workflows]]` entry naming it). It does
  NOT assert the reverse — trajan's `platform` entries name a surface that has no block, by
  design — and says so. `set -uo pipefail`, the repo's `assert()` (pipefail scoped off),
  `yes | grep -q y` canary, `exit $fail`, no box precondition (no `SKIP:` line, no change to
  `tests/ci-expected-skips.txt`). Checker `empty_present_surfaces DIR` is one inline
  `python3 - <<'PY'` over `tomllib`: for each `*.toml` in DIR, a parse failure prints
  `<name>.toml: does not parse: <exc>` (named, never dropped), else for each
  `surfaces.<s>` with `present == True` and no workflow whose `surface == s`, prints
  `<name>.toml: [surfaces.<s>] present = true hosts no [[workflows]] entry`. Groups:
  0 canary; 1 fixtures in `$(mktemp -d)` — an unparseable manifest is named
  `(::manifest-parse-named)`; a present surface with no entry is named and a present surface
  with one is not `(::present-surface-hosts-work)`; a `present = false` surface with no entry
  is silent `(::retired-surface-silent)`; 2 the live `design/agents/` — one assert, offenders
  in the description. Anchor each id as a trailing `# (::id)` comment on the assert line, the
  way `tests/test_contract_schema.sh:222-228` does.

## Test plan

TDD order: suite first, red, then the manifest edit.

1. `bash tests/test_manifest_surfaces.sh` on the unmodified tree → group 1 green, group 2
   **FAIL** naming `augustus.toml: [surfaces.scheduled] present = true hosts no [[workflows]] entry`.
   After the augustus edit → exit 0, `FAIL:` count 0.
2. `shellcheck -S error tests/test_manifest_surfaces.sh` clean.
3. `python3 -c 'import tomllib,sys; [tomllib.load(open(p,"rb")) for p in sys.argv[1:]]'
   design/agents/augustus.toml design/deploy-exclusions.toml design/fleet-suites.toml
   design/phaseb-brief-queue.toml` → exit 0.
4. `bash tests/test_workflow_registry_frozen.sh` → exit 0 (header untouched, no live heading).
5. `bash tests/test_workflow_coverage.sh` → exit 0; the new suite is claimed and its three
   anchors resolve both ways (`asserts-anchored`).
6. `bash bin/check_deploy_drift.sh` → two `info` lines naming
   `profiles/standing_research_content_strategy_task.md` and
   `…_faceless_content_task.md` as declared, pending prune; `drift: clean`.
7. Land gate reproduced: `grep -A3 'surfaces.scheduled' design/agents/augustus.toml | grep -qE
   'present *= *false|reason' && [ $(grep -c '^\[\[runtime_only\]\]' design/deploy-exclusions.toml) = 11 ]`
   → 0.
8. Check 2, expected remaining hits (`grep -rn 'content-strategy\|faceless-content' design/ profiles/ config/`):
   `agent-model.md` §6.5 (RETIRED note + the 2026-09-01 record), §6.6 (dated), §6.7 (measured
   2026-09-02, closed); `workflow-registry.md` `:108-109` (`keep ⁴`), the CORRECTION and
   RETIRED paragraphs, §7 item 3 with its `→` line; `phaseb-brief-queue.toml` (header says
   spent, entries dated); `augustus.toml` retirement comment + the two rewritten notes;
   `design/archive/open-decisions-closed-2026-09-07.md` (archive). Nothing under `profiles/`
   or `config/`. Over `bin/`: exactly `run_standing_research_topic_cc.sh:13,14,21,22`,
   `run_faceless_content_cc.sh:5`, `run_content_strategy_cc.sh:5`, `notion_research_page.py:144`.
9. `bash bin/verify.sh > "$SCRATCH/verify.out" 2>&1; echo $?` → 0;
   `grep -nE '^ *FAIL:|PROBLEM|DRIFT|drift: [1-9]|source-only|no exclusion|content differs' "$SCRATCH/verify.out"`
   → nothing.

## Out of scope / do not touch

- `bin/` — all of it. The three runner scripts and `notion_research_page.py:144` are T6.3's
  and go with `bin/deploy --prune`; an edit there is red drift this task cannot clear.
- `bin/deploy` (any flag), `sudo`, any `systemctl` action, `~/.config/agent-workforce/`.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, every existing test,
  `tests/ci-expected-skips.txt`.
- `.claude/briefs/current.md` (T0.3's live brief) and `.claude/briefs/archive/` — this brief
  is committed under its own name and not archived by `/finish`.
- `design/archive/**`, `.claude/briefs/archive/**` — history, correct as history.
- The eval-spec §5 "real hole" rows — dated re-measurement paragraph only, not a rewrite.
- `tests/test_workflow_registry_frozen.sh`'s absence from `design/fleet-suites.toml` — T6.4's
  choice; noted, not changed.
- `docs/dev-plan-2026-09.md` — status lives in Notion.
- The `bin`-half exclusion asymmetry in the drift check — its own decision (W19 brief).

## Notes / preconditions

- Measured 2026-09-08 in this worktree (`main` at `9df0f25`): coverage prints
  `parsed 33 workflow entries … standing coverage: 27 of 29 own a suite, 2 exempt, 0 uncovered`;
  `~/agent-workforce/profiles/` holds both task profiles (dated Sep 2 16:45, 6701 and 6952 B);
  `design/deploy-exclusions.toml` has 9 `[[runtime_only]]` entries; the check 2 grep hits
  are as listed in the W19 row paragraph above plus the two profiles; `systemctl
  list-unit-files | grep -E 'content-strategy|faceless'` is not re-run here — the parent
  brief measured it empty on 09-04 and nothing since installs a unit.
- `bin/check_deploy_drift.sh:220-237` parses the exclusions with `tomllib` and keys on
  `tree` + `path`; `:414-419` prints a declared runtime-only file as `info`, an undeclared one
  as a finding; `:429-433` reports a stale entry once the prune happens. Since the drift check
  runs with source = this worktree, deleting the profiles here is what makes the exclusion
  necessary on the box, and the exclusion is what keeps the gate green.
- Every `present = true` surface in the five manifests hosts ≥1 entry except
  `augustus.[surfaces.scheduled]` — so the new suite's live verdict is red exactly once, on
  the defect this task fixes. trajan's sixteen `platform` entries have no `[surfaces.platform]`
  block; the suite must not assert that direction.
- `tests/test_workflow_coverage.py` `asserts-anchored` is two-way: every id in
  `fleet-suites.toml` must appear as `(::id)` in the suite, and every `(::id)` in a suite must
  be declared. Three ids, three anchors, nothing else in parentheses after `::`.
- `test_fleet_guards.sh` enforces `owner ∈ {fleet, retired-tool}` on `fleet-suites.toml`
  entries; on this box it runs (the fleet files exist), so the entry must be well-formed.
- Worktree branch `worktree-wf_35f2ebd1-24d-3`; the land step fast-forwards `main` and
  deploys from there. Commit by explicit path; never `git add -A`, never `git mv`.
