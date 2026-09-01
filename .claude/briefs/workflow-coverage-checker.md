# Brief: Build D6's workflow-coverage checker, reading the declared join in both directions
**Date:** 2026-09-02   **Verify:** `bash bin/verify.sh` from the repo root (syntax + shellcheck -S error over `bin/`, then every `tests/*.sh`)

This is Phase-B brief 3. It builds the mechanism D3 §7.1 asks for and D6 answered: the thing
that computes workflow coverage instead of recording it, so `eval-spec.md` §5 stops being a
number that rots the day it is written.

Read `design/open-decisions.md` D6 (line 472) and `design/eval-spec.md` §7.1 (line 223) before
starting. **Read the answers, not the questions** — D6's premise sentence ("resolves each live
workflow to a suite") has no implementation that works, and four inference rules were measured
against the live tree with all four disagreeing. The join is now *declared* data, not inferred.

**It ships red.** Five assertions fail on arrival, all named in criterion 8. That is the point:
a coverage checker that goes green the moment it lands has not been shown to detect anything.

## Acceptance criteria

1. **The checker runs inside the existing gate with no gate change.** `bin/verify.sh:47` already
   loops `tests/*.sh`, so a new suite is collected automatically.
2. **Ownership resolves through BOTH declared sources.** `design/agents/*.toml` `[[workflows]]`
   `suite = [...]` (R15b, schema at `design/agent-model.md:130`) **and**
   `design/fleet-suites.toml`, where `owner = "fleet"` is a second valid owner
   (`design/fleet-suites.toml:18`; required by `design/eval-spec.md:228-230`). A checker that
   knows only the workflow→suite direction reports `tests/test_fleet_guards.sh` as an orphan,
   and an orphan's recommended fix is deletion — so its first act would be to propose deleting
   the suite that asserts the fleet's security guards. That suite landed with brief 1
   (`b4e20a3`) precisely so this cannot happen; do not let it happen anyway.
3. **Every `status = "standing"` entry with no `suite_exempt` names at least one suite.**
   Measured 2026-09-02: 26 entries, 22 `standing`, 2 `campaign`, 2 `dormant`. 16 covered,
   3 exempt, 4 red.
4. **`suite` key presence is not coverage.** All 26 entries carry the key; 10 carry `suite = []`.
   An `in`/`has_key` test passes all 26 and reports full coverage. Assert length.
5. **Every path named in any `suite` exists on disk.** Green today (0 missing of 19 distinct
   paths) — it is the assertion that catches a suite renamed or deleted later.
6. **Exempt workflows are printed by name on every run, never merely skipped.** Three today:
   `fleet-turn-check`, `ttm-pool-drain`, `buzz-pr-watch`. Required by
   `design/agent-model.md:169-172` — a silent exemption is how a thing stops being looked at,
   and `fleet-turn-check` is the gate that proves an agent can complete a turn.
7. **An unclaimed suite whose subject is no longer reachable is red.** One case today:
   `tests/test_content_inbox_finalize.sh`, testing `bin/content_inbox_finalize.py`, whose unit
   was removed 2026-09-01 to `systemd/archive/content-inbox-finalize.service` with nothing in
   `/etc`. See "the reachability rule" in Notes — this is the criterion most likely to be
   implemented wrongly, and the measurements that say so are recorded there.
8. **The run ships red with exactly five named failures, and no others.** Four uncovered
   standing workflows — `m1-signal-scan` (claudius), `overnight-morning-report` (marcus),
   `agent-workforce-auto-sync` (trajan), `overnight-pre-snapshot` (trajan) — plus the one
   orphan above. Any sixth failure is either a real find or a bug in the checker; resolve it by
   naming the real owner or fixing the checker, **never** by adding an exemption.
9. **The checker refuses to report a coverage figure it did not actually compute.** It fails if
   the total parsed entry count is zero, and fails if any manifest whose text contains
   `[[workflows]]` yields zero parsed entries. Two live traps make this non-theoretical, both
   in Notes; both produce a confident "100% covered" from a walk that read nothing.
10. **Every `*.timer` family in `systemd/` has a manifest entry.** Source tree only. One failure
    today, and it is the reason this criterion exists: `praetorium-phaseb-brief@` runs five
    enabled instance timers and appears **nowhere** in `design/agents/*.toml` or
    `design/workflow-registry.md`. Fix it in this brief by adding the entry (below), so the
    assertion lands green rather than as a sixth red.
11. **`bin/verify.sh` exits non-zero, and the only failing suite is the new one.** Record the
    gate's state *before* you start: brief 2's drift check also ships red and may already have
    landed. Two independent reds in one gate must each name themselves unambiguously or they
    mask each other.

## Files to create

- **`tests/test_workflow_coverage.sh`** — the checker, as a suite. `design/eval-spec.md:223`
  specifies "a suite", and that is the right shape for a second reason: a `bin/` script would
  become a `bin/` entrypoint that no unit execs, which criterion 7's own rule would then have to
  special-case. `bin/verify.sh` is already in that position; do not add a second.
  If it needs `tomllib`, follow the pair convention — a thin `tests/test_*.sh` that `exec`s
  `python3 tests/test_*.py`, as at `tests/test_content_inbox_finalize.sh:8`. Either shape is
  fine; the `.sh` must be the entry point, because that is what the gate globs.

## Files to modify

- **`design/fleet-suites.toml`** — add a second `[[suite]]` for `tests/test_workflow_coverage.sh`
  with `owner = "fleet"`. It is a fleet-level invariant with no owning workflow, exactly like
  `tests/test_fleet_guards.sh`, and without the declaration the checker reports **itself** as an
  orphan. Note this file's array key is `suite` (singular) while the manifests use `workflows`
  (plural) — one checker, two conventions, and `tests/test_fleet_guards.sh:236` already reads
  the singular. `tests/test_fleet_guards.sh:229-249` validates this file's structure (path
  exists, `owner`, `asserts` non-empty); consume it, do not re-validate it.

- **`design/agents/trajan.toml`** — add the missing `[[workflows]]` entry for
  `praetorium-phaseb-brief@`. Owner is trajan: it is unit plumbing on the `platform` surface,
  the same class as his other twelve. Status is **`campaign`**, not `standing` — the five
  instance timers carry absolute one-shot `OnCalendar` dates, all on 2026-09-02, the latest
  being `05:22:00` (`systemd/praetorium-phaseb-brief@6.timer`). So `expires = "2026-09-02
  05:22:00"`, and by `design/agent-model.md:183` it is `spent` the moment that has passed —
  flag-for-removal, needing no owning suite. `suite = ["tests/test_phaseb_brief_jobs.sh"]`
  anyway: that suite exists, is unclaimed today, and this is its owner.
  **The `unit` join key is the template family `praetorium-phaseb-brief@`, one entry, not five.**

- **`design/open-decisions.md:871`** — the W5 row still reads *"Manifest edit, not code. Blocks
  D6."* **W5 is done.** Measured 2026-09-02: all 26 `[[workflows]]` entries across
  `design/agents/*.toml` carry an explicit `status`, and all 26 carry `suite` or `suite_exempt`.
  The same doc already records it at line 571 (`W5 (done, 3a52d42)`) and `eval-spec.md:165`
  records R15 done plus R15b (`6e4fb34`) — so the Carried-work table is the one stale copy of a
  fact three other places have right. Correct it here rather than working around it; brief 6
  reads that table to decide what remains and will otherwise re-do a finished item.

- **`design/eval-spec.md:224`** — §7.1 says the checker "resolves each `status = "live"` workflow
  to a suite". **No workflow entry has ever had `status = "live"`.** That is the *agent-level*
  vocabulary (`design/agents/marcus.toml:9`, `trajan.toml:12`, `claudius.toml:8`,
  `augustus.toml:12`; enum at `design/agent-model.md:106`), deliberately chosen to be different
  words so a grep for one never matches the other (`design/agent-model.md:187-188`). Workflow
  status is `standing | campaign | spent | dormant | planned`
  (`design/agent-model.md:181-186`). An implementer following §7.1 literally filters on `"live"`,
  selects **zero** entries, and reports full coverage. Fix the sentence.

- **`design/eval-spec.md` §5** — replace the hand-written headline count with a pointer to the
  checker's output. Keep the per-workflow table: it carries the *why*, which no checker
  computes. The numbers are what rot — §5 has already been wrong three ways in one document
  (`design/open-decisions.md:548-551`).

- **`design/agent-model.md:207-212`** — it parks an open question explicitly for D6: *"whether a
  deterministic platform job should have a contract … belongs to D6, since a coverage checker
  has to decide what it does with an entry that names no contract."* **Answer it: the checker
  does not require `contract`.** Coverage is suite ownership; contracts are D3's
  acceptance-check layer. Only 14 of 26 entries carry one, trajan's 12 platform jobs carry none,
  and that is correct — a platform job's promise is liveness and an artifact, not output
  quality. Record the answer where the question sits.

## Test plan

**What fails before the change exists: nothing, and that is the defect.** No layer on this box
knows the workflow list, so the four uncovered standing workflows and the one orphan are
currently invisible to every gate. There is no red to turn green — the deliverable *is* the red.
So the test plan is not "run it and see it pass". It is: prove the checker detects, then leave
it detecting.

Follow `tests/test_fleet_guards.sh` verbatim on conventions: `set -uo pipefail`, the `assert()`
helper that scopes `pipefail` **off** inside the condition (`tests/test_fleet_guards.sh:38-45`),
and `yes | grep -q y` as the first assertion. That canary is not decoration — under `pipefail`
a condition fails a true assertion and silently passes a negated one, which is how this gate
certified nothing for a week in August (`CLAUDE.md` § Verification).

**Detection proofs — run each by hand, confirm red, then restore. Commit none of them.**

1. Delete one `suite` entry from a covered workflow (e.g. `knowledge-digest`) → that workflow is
   named as uncovered. Restore.
2. Point one `suite` path at a file that does not exist → named as missing. Restore.
3. Remove `owner = "fleet"` from `design/fleet-suites.toml`'s existing entry →
   `tests/test_fleet_guards.sh` is reported as an orphan. This is the single most important
   proof in the list, because it is the failure mode criterion 2 exists to prevent. Restore.
4. Key the manifest walk on `workflow` (singular) instead of `workflows` → criterion 9 must fire
   ("zero entries parsed"), **not** a clean "100% covered". Restore.
5. Filter on `status == "live"` → same: criterion 9 fires. Restore.
6. Add `systemd/archive/` back into the unit enumeration → the orphan must still be reported.
   `systemd/archive/content-inbox-finalize.service:28` carries a live-looking
   `ExecStart=…/bin/content_inbox_finalize.py`, and counting it makes the one true positive
   disappear.

**Do not weaken anything to get to green.** The four uncovered workflows get suites (later
work), not `suite_exempt`. `suite_exempt` means *the code is not in this repo*
(`design/agent-model.md:131`, `:165`); all four are in-repo and writable —
`bin/run_m1_signal_scan_cc.sh`, `bin/run_overnight_morning_report_cc.sh`, `bin/auto-sync`,
`bin/overnight_pre_snapshot.sh`. Using the exemption field to silence them would be forging the
exact signal this brief exists to produce.

## Out of scope / do not touch

- **Writing the four missing suites.** They are the backlog this checker exists to produce.
  `overnight-morning-report` is the sharp one — it is the unit carrying the entire recurring
  reporting-defect class (`design/agents/marcus.toml` notes; `eval-spec.md:141`) — but it is a
  brief of its own, not a footnote to this one.
- **The reverse rule "every `tests/test_*.sh` is claimed by ≥ 1 entry".** Measured and rejected
  in D6: 24 of 43 suites are unclaimed today and most legitimately test *libraries*
  (`notion_rest`, `notion_markdown`, `buzz_deliver`, `proposal_or_decline`, `qmd_status`), not
  workflows. It fires 24 false positives to catch one real orphan.
- **Asserting `expires` is in the future for `campaign` entries.** It is a correct rule and it is
  a date bomb here: both content campaigns expire 2026-09-03 23:00 and 2026-09-04 01:30, and
  brief 6 deletes those units after their last firings. A checker shipping red for one stated
  reason must not also go red for a second, unrelated, calendar-triggered reason — the two would
  be read as the same failure. Hand it to brief 6 with the deletion.
- **Anything that reads the box.** No `systemctl is-enabled`, no `/etc/systemd/system`, no
  `~/.config/systemd/user`. Criterion 10 is source-tree only, deliberately. Unit membership
  across the four trees is **brief 2's** (D8) subject, and duplicating its ownership filter here
  would put one concept in two places. If brief 2 has landed, consume its filter; if not, do not
  invent a second one. (The four manifest entries with no source timer — `fleet-turn-check`,
  `buzz-pr-watch`, and the two campaigns — are all brief 2's, and all explained.)
- **Liveness inference from timer state.** `NextElapseUSecRealtime` is empty for every
  `OnUnitActiveSec` timer and `NextElapseUSecMonotonic` reads `infinity` mid-trigger
  (`design/agent-model.md:214-218`). Out of scope here; noted so nobody reintroduces it.
- **`~/.config/agent-workforce/*.env`.** Do not read these to resolve runners — see Notes. They
  are the secrets tree, denied to Claude sessions by `~/.claude/settings.json` and listed
  out-of-scope in `~/CLAUDE.md`. The manifests' declared `runner` field carries the same
  information in-repo.
- **`tests/test_fleet_guards.sh`.** Consume its output; change none of its assertions.
- **`.claude/briefs/current.md`.** Choosing what is current is Dave's call.

## Notes / preconditions

**No unmet preconditions.** The queue entry lists none, and both dependencies are satisfied:
W5 done (`3a52d42`, and see the correction above), D4 answered yes (`b49606b`), `fleet` owner
value landed with brief 1 (`b4e20a3`).

**The reachability rule — measured 2026-09-02, and it does not work as recorded.** D6 states
reachability "pinpoints the one real case with no false positives"
(`design/open-decisions.md:518`). That was not reproducible. Two crude static implementations
over `bin/` (80 files), rooted at unit `Exec*` lines plus the manifests' declared `runner`
fields and closed transitively over textual references:

| edge rule | unreachable | the one true orphan |
|---|---|---|
| any textual reference | 29 | **missed** — `bin/notion_rest.py:241` names it in a comment as *"the retired"* path, which marks it reachable |
| comment lines stripped | 44 | found |

The rule that finds the target has the most false positives, and the false positives are real
code: dynamically-constructed invocations, and every runner selected indirectly. So:

- **Scope the question to the unclaimed set, not to all of `bin/`.** 24 suites are unclaimed
  today; that is the only set where "is this still testing live code?" needs an answer, and it
  is small enough that every hit is human-checkable once. Criterion 8's "no sixth failure"
  is the acceptance bar.
- **If you cannot get the false-positive count to zero over those 24, declare the subject
  instead of inferring it.** That is the same conversion D6 already made twice — R15 (`status`)
  and R15b (`suite`) — and its stated reason is exactly this one: *"it converts an inference
  problem into a data problem, which is why the count stops moving"*
  (`design/open-decisions.md:504-505`). **Do not ship an inference that fires twenty false
  positives**; a checker whose output must be filtered by hand is a checker nobody reads.
- **The `runner` indirection is why naive reachability floods.** Eleven units name an env file
  under `~/.config/agent-workforce/` in `Environment=AGENT_JOB_OVERRIDES=…`, and
  `bin/agent_propose.sh:160-163` sources it — that is where the runner is chosen. The edge is
  invisible in-repo. Use the manifests' declared `runner` (11 distinct values, all present in
  `bin/`); **13 of 26 entries carry no `runner` at all**, so it is a supplement to unit
  enumeration, never a replacement for it.

**If you enumerate units at all, five things about `Exec*` lines, all measured:**

- **Two roots, not one.** Most units exec `/home/dave/agent-workforce/bin/…` (the deployed
  copy); two deliberately exec `/home/dave/dev/agent-workforce/bin/…` — the repo itself
  (`systemd/agent-inbox-sync.service:24`, `systemd/agent-workforce-auto-sync.service:36`, each
  with a `NOTE ON PATH` comment saying why). Normalising one root drops the other.
- **`ExecStartPost=` carries five delivery scripts** (`deliver_content.sh`, `deliver_dispatch.sh`,
  `deliver_proposal.sh`, `deliver_report.sh`, `deliver_scorecard.sh`) that appear on no
  `ExecStart` line anywhere — e.g. `systemd/augustus-content.service:21`. Grepping `^ExecStart=`
  alone loses all five. `systemd/agent-inbox-sync.service:25-26` uses `ExecStopPost=` instead,
  and says why.
- **`systemd/archive/` must be excluded.** It is the only reason the one true orphan is
  detectable at all; see test 6.
- **Arguments and `%i` follow the path** (`vault_sync_guard.sh sync`, `fleet_eval.sh --deliver`,
  `run_phaseb_brief_cc.sh %i`), and one unit wraps its command in `/bin/bash -lc '…'`
  (`systemd/qmd-refresh.service:22-23`).
- **Coverage can sit three hops out.** `agent-inbox-sync` → `bin/agent_inbox_pipeline.sh` →
  `bin/agent_inbox_notion_sync.py` (`bin/agent_inbox_pipeline.sh:24`) →
  `tests/test_agent_inbox_body_sync.sh`. Following one wrapper level is not enough.

**Textual subject extraction has two dumb traps if you go that way.** `bin/env` matches on every
`#!/usr/bin/env bash` shebang and is not a file in this repo; and prose references carry trailing
punctuation — `bin/agent_inbox_notion_sync.py.` in `tests/test_agent_inbox_body_sync.py`.
Require any extracted path to exist under `bin/`.

**Re-measure every count; do not trust a recorded one.** Between 2026-09-01 and 2026-09-02 the
suite total moved 41 → 43 and the unclaimed set 23 → 24, because brief 1 and the brief-writer
job each added a suite. A fresh unclaimed suite appears with roughly every work item — which is
itself the argument against the rejected reverse rule.

**Measured baseline, 2026-09-02** (`tomllib`, `design/agents/*.toml`): 26 entries — marcus 4,
claudius 6, augustus 4, trajan 12, aurelian 0 by design. 22 `standing`, 2 `campaign`,
2 `dormant`. 16 with a non-empty `suite`, 3 with `suite_exempt`, 4 standing-and-uncovered,
3 bounded-and-uncovered (2 campaign + `bd-stall-radar`, dormant). 19 distinct claimed suite
paths, all present on disk. This reproduces `eval-spec.md` §5 exactly; if your run disagrees,
the manifests moved and §5 is what needs correcting, not this brief.

**Incidental, for brief 6, not for this one:** `systemd/praetorium-phaseb-brief@.service:5`
describes those units as *"/etc-only scaffolding"*. `d72f562` committed all six to `systemd/`,
so the comment is now wrong in the direction that matters — brief 2's queue entry records the
same correction. Whoever deletes them owns that line.

**Commit as soon as each coherent piece is done.** `agent-workforce-auto-sync.timer` fires every
15 minutes and commits any dirty tree with `git add -A`; work left uncommitted is swept into a
message describing something else.
