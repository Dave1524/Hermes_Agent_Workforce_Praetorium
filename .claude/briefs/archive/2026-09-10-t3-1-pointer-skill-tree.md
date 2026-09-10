# Brief: T3.1 — pointer-skill tree `skills/`, deployed and drift-checked
**Date:** 2026-09-10   **Verify:** `bash bin/verify.sh` from the repo root

Source of scope: `docs/dev-plan-2026-09.md:107-111` (T3.1, phase "3 Skills", size L).
Allocation source: `design/archive/open-decisions-closed-2026-09-07.md:330-360` (frozen).

## Acceptance criteria

1. `skills/` exists in this repo as a tree of **pointers** — each `SKILL.md` a few lines naming
   the canonical vault path, never a copy of the vault body.
2. `bin/deploy` ships `skills/` (`PATHS` gains it), so `~/agent-workforce/skills/` mirrors source.
3. `bin/check_deploy_drift.sh` compares `skills/` as an **additional content tree**
   (`CONTENT_TREES` gains it), in both membership directions like the other seven.
4. The nine **scheduled** runners load skills from an **explicit path in the deployed tree**
   (`--plugin-dir $HOME/agent-workforce/skills/<owner>`), never from `~/.claude/skills/`.
5. A test asserts the skill list the runtime sees equals the repo's — statically, with no model
   call: the plugin tree each runner names, the drift coverage that keeps it equal to source, and
   the allocation table joined to the tree in both directions.
6. The 13 drafted pointers are the initial content (see the 14-vs-13 note below).
7. `bash bin/verify.sh` is green after `bin/deploy` has run.

Gate wording in the dev plan is "drift covers `skills/`; a headless run lists the skills". The
second half is a **one-off recorded live run**, not a gate step — see Notes.

## Layout (decided, do not re-open)

One plugin per owner, because a single flat tree offered to every runner is `~/.claude/skills/`
moved into the repo and answers nothing about *which* skills an agent has for a workflow. T3.2
joins `skills = [...]` in `design/agents/*.toml` against a narrow per-owner set.

```
skills/README.md                                  # allocation table + the two rules, joined by the suite
skills/<owner>/.claude-plugin/plugin.json         # name = "praetorium-<owner>"
skills/<owner>/skills/<skill-name>/SKILL.md       # the pointer
```

`<owner>` ∈ {marcus, claudius, trajan, augustus}. Aurelian gets none (frozen decision).

**The `skills/<owner>/skills/` nesting is load-bearing and was measured, not guessed:** a skill
directory at the plugin root is silently ignored; only `<dir>/skills/<name>/SKILL.md` loads.

### Allocation — 13 pointers

| owner | pointers |
|---|---|
| augustus | `linkedin-content-engine`, `linkedin-review`, `blog-engine` |
| claudius | `prospect-research`, `meeting-prep`, `investment-research` |
| trajan | `systematic-debugging`, `test-driven-development`, `verification-before-completion`, `spec-to-code-enforcement` |
| marcus | `weekly-review`, `agent-inbox-sync`, `post-call-capture` |
| aurelian | none |

All 13 targets confirmed present as `~/vault/08_skills/<name>/SKILL.md` on 2026-09-10.

### Pointer body (exact shape)

```markdown
---
name: <skill-name>
description: <one line, lifted from the vault skill's own description>
---

Canonical source: `08_skills/<skill-name>/SKILL.md` in the vault.
On this box: `~/vault/08_skills/<skill-name>/SKILL.md`

This file is a pointer, never a copy. Read the canonical file before acting.
```

Both paths are named: vault-relative because that is the canonical identity, and absolute
because Marcus's `run_daily_rhythm_cc.sh` and `run_overnight_morning_report_cc.sh` run with
cwd `$HOME/agent-workforce`, not a vault worktree, so a relative path resolves to nothing.
Precedent: `profiles/augustus_content_task.md` and `tests/ci-expected-skips.txt` already
write `~/vault/08_skills/...`.

## Files to modify

- `bin/deploy:20` — `PATHS=(bin profiles docs CLAUDE.md AGENTS.md README.md config systemd skills)`.
- `bin/check_deploy_drift.sh:93` — `CONTENT_TREES` gains `skills`. Update the header comment
  above it (currently "The seven trees bin/deploy ships") to eight, appending why rather than
  rewriting the W7/W17 history it records.
- `tests/test_deploy_drift.sh:814-839` (group 16b) — the two hardcoded counts `8` become `9`.
  This is the join that keeps `CONTENT_TREES` and `PATHS` in agreement; it fails loudly in both
  directions and **will go red the moment `bin/deploy` changes**, which is the intended order.
- The nine scheduled runners — marcus: `bin/run_daily_rhythm_cc.sh`,
  `bin/run_overnight_morning_report_cc.sh`, `bin/run_weekly_pre_assembly_cc.sh`; claudius:
  `bin/run_knowledge_digest_cc.sh`, `bin/run_standing_research_cc.sh`, `bin/run_raw_ingest_cc.sh`,
  `bin/run_m1_signal_scan_cc.sh`, `bin/run_bd_stall_radar_cc.sh`,
  `bin/run_bd_followup_drafts_cc.sh`. Each gains, beside the existing `TASK_FILE` guard:

  ```bash
  SKILLS_DIR="${PRAETORIUM_SKILLS_DIR:-$HOME/agent-workforce/skills/<owner>}"
  [ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || {
    echo "<job>: skills plugin not readable: $SKILLS_DIR" >&2; exit 1; }
  ```

  and `--plugin-dir "$SKILLS_DIR"` in the `exec` flag list. The guard is not decoration: a
  nonexistent `--plugin-dir` path is **silent** — exit 0, no warning — so without it a runner
  launches with no skills and nothing anywhere says so.
- `design/fleet-suites.toml` — a fifth `[[suite]]` entry for `tests/test_pointer_skills.sh`,
  `owner = "fleet"`, with every assert id below listed and a `why_no_workflow` block. Each id
  must be anchored as `(::id)` on the group-opening line in the suite (W9 join, both directions).
- `tests/ci-expected-skips.txt` — one new `SKIP:` line for the box-gated group, plus a dated
  paragraph appended in its own block (never interleaved, per the file's own rule) recording
  that eleven becomes twelve.
- `docs/dev-plan-2026-09.md` — `14` → `13` at `:24`, `:111`, `:116`, with a parenthetical
  naming the arithmetic slip; see the 14-vs-13 note below.
- `docs/runbook.md:189` — the drift-timer row enumerates "the seven content trees (`profiles`,
  `docs`, `config`, `CLAUDE.md`, `AGENTS.md`, `README.md` and `systemd`)"; it becomes eight
  with `skills`.
- `CLAUDE.md` § Where things live — one bullet for `skills/`: pointer tree, deployed, read by
  the scheduled runners via `--plugin-dir`, never a copy of vault content.

## Files to create

- `skills/README.md` — the allocation table above, the "pointer never a copy" rule, and the
  exclusion rule ("a pointer skill must not duplicate a task profile that already owns the same
  surface" — which is why `morning-startup` and `eod-wrap` are absent: `profiles/daily_plan_task.md`
  and `profiles/eod_summary_task.md` own that surface). The table is **joined** by the suite, so
  it cannot rot. Also record that the pointer `agent-inbox-sync` shares a name with trajan's
  `surface = "platform"` unit and is a different thing — a vault skill, not the timer.
- `skills/{marcus,claudius,trajan,augustus}/.claude-plugin/plugin.json` — 4 files,
  `{"name": "praetorium-<owner>", "description": "...", "version": "0.1.0"}`.
- 13 × `skills/<owner>/skills/<name>/SKILL.md` — the pointer shape above.
- `tests/test_pointer_skills.sh` — fixture groups first, live verdict last, following
  `tests/test_instruction_scaffolding.sh`'s idiom: `assert()` with `pipefail` scoped off, a
  `yes | grep -q y` canary as group 0, `box_only_with` for the one box-reading group.

## Test plan

`tests/test_pointer_skills.sh`, assert ids (each anchored `(::id)` and declared in
`design/fleet-suites.toml`):

| id | what it proves |
|---|---|
| `pointer-not-copy` | every `SKILL.md` is under a line ceiling and names its canonical path; no vault body copied in |
| `pointer-names-match` | directory name == front-matter `name` == the path segment in the body |
| `plugin-manifest-valid` | each owner tree has `.claude-plugin/plugin.json`, parses as JSON, `name == praetorium-<owner>` |
| `skills-nested-under-skills` | no `SKILL.md` at a plugin root — the layout the CLI silently ignores |
| `runner-offers-owner-tree` | each of the nine runners passes `--plugin-dir` at its manifest owner's tree, joined from `design/agents/*.toml`, both directions |
| `runner-skills-guard` | each of the nine guards `plugin.json` readability before `exec` — the silent-missing-dir trap |
| `runner-join-counted` | the runner join reports how many entries it checked, so a parse that matched nothing cannot pass as clean |
| `drift-covers-skills` | `skills` is in `bin/deploy`'s `PATHS` **and** in `CONTENT_TREES` — the T3.1 gate, read from both scripts, not from a literal here |
| `allocation-matches-readme` | the README table equals the on-disk tree in both directions, and sums to 13 |
| `no-profile-duplicate` | `morning-startup` and `eod-wrap` are absent, and no pointer's snake form is a `profiles/<stem>_task.md` |
| `pointer-target-exists` | **box-gated** — every named `~/vault/08_skills/<name>/SKILL.md` exists (existence only, never a read) |

Fixture groups precede each live group and prove the checker detects the failure, not just that
the tree happens to pass: a pointer that copied a body, a mismatched name, a plugin.json with the
wrong name, a skill at the plugin root, a runner missing `--plugin-dir`, a runner missing the
guard, a README row with no directory and a directory with no README row.

`bin/verify.sh` runs the suite automatically (it sweeps `tests/*.sh`); exit 0 or 77 both pass.

## Out of scope / do not touch

- `design/agents/*.toml` `skills = [...]` and `design/agent-model.md`'s record of the allocation
  as a bet — that is **T3.2**, and doing it here would take the join T3.2 exists to build.
- Skill-usage telemetry — **T3.3**.
- `bin/run_standing_research_topic_cc.sh` and the two campaign runners: retired residue, reachable
  by nothing since 2026-09-04 (`design/open-decisions.md:28`). No `--plugin-dir`, no pointer tree.
- Trajan's and Augustus's trees reach **no S2 runner**: trajan's 15 workflows are all
  `surface = "platform"` (no model) and augustus is `buzz_dispatch` on codex-acp. The trees are
  built because the frozen allocation names them and T3.2 joins them; that they are offered to
  nobody today is recorded state, not an omission. Do not "fix" it by inventing a runner.
- The interactive Buzz surface (`buzz-team/`), `~/.claude/skills/`, and anything under
  `~/.config/`. The runners read the **deployed** tree by explicit path; nothing here touches the
  user-scope skill directory.
- Vault content. Pointers name paths; nothing copies, reads or edits `~/vault/**`.
- The `14` in `design/archive/open-decisions-closed-2026-09-07.md` — an archive file is a record
  of what was decided, not a live document. Correct the dev plan, leave the archive.

## Notes / preconditions

**The 14-vs-13 discrepancy.** The frozen allocation table sums to **13**, while the prose beside
it says "1 of these 14 is named by a live workflow". 14 is an arithmetic slip in
`design/archive/open-decisions-closed-2026-09-07.md`, carried into `docs/dev-plan-2026-09.md` at
`:24`, `:111` and `:116`. Implement the table (13) and correct the dev plan; the archive keeps
its number as the record of what was written.

**Measured on this box 2026-09-10, claude 2.1.267** — each of these decided a design point:
- `--plugin-dir <dir>` loads only `<dir>/skills/<name>/SKILL.md`. A skill directory at the plugin
  root is **not** discovered. → forces the `skills/<owner>/skills/<name>/` nesting.
- A `--plugin-dir` path that does not exist is **silent**: exit 0, no warning, no skills.
  → forces the explicit `plugin.json` readability guard in every runner.
- Skill invocation works under `--allowedTools "Read,Glob,Grep"`; no allowlist change is needed,
  so `test_workflow_coverage.py`'s `runner-tools` join (runner `--allowedTools` ==
  `surfaces.scheduled.tools`) stays green untouched. **Confirm in Phase 2** that its parser does
  not assume `--allowedTools` is the last flag.
- `claude plugin details` does **not** accept `--plugin-dir` (`error: unknown option`), so there
  is no deterministic CLI way to enumerate a session-loaded plugin's skills. The gate test is
  therefore static; "a headless run lists the skills" is satisfied by one recorded live run whose
  output goes in the commit message. **No suite in this repo spends model tokens** and this one
  will not be the first.
- Neither runner cwd has a `.claude/` directory, and `~/.claude/skills/` does not exist — so the
  runners are not silently inheriting a skill set today.
- The vault has 29 `08_skills/*/` directories; all 13 named pointers resolve.

**Deploy ordering inverts the usual loop.** `bin/verify.sh` hard-fails on deploy drift, so this
task's loop is **edit → `bin/deploy` → `bash bin/verify.sh` → commit**, not edit → verify →
commit (`CLAUDE.md` § Verification, `docs/runbook.md` § Deploy ordering). `bin/deploy` refuses a
git destination and post-checks itself with `check_deploy_drift.sh --scope bin`.

**Baseline is green.** `bash bin/verify.sh` was run on `main` at 8440e7d before any edit: exit 0,
one SKIP line (`live OpenCode agent contract tests`). So Gate 2 means *green*, with no
pre-existing red to discount. Any red after this change is this change's.

**pipefail trap.** Never end a pipeline in an early-exiting reader (`grep -q`, `head`) inside a
boolean condition — the upstream stage dies of SIGPIPE and the pipeline reports 141, which
inverts twice in a condition. `assert()` scopes `pipefail` off; sites outside an assert use
`grep ... >/dev/null` or drop the pipe. Carry the `yes | grep -q y` canary.

**Auto-sync.** `agent-workforce-auto-sync.timer` fires every 15 min and sweeps any dirty tree into
a generic `Auto-sync:` commit on `main`. Commit this work promptly, and push it by hand — the
timer pushes only what it commits itself.

**Branch.** Currently on `main` with a clean tree. Phase 3 branches first. Note that a feature
branch adding no `bin/` **script** can still be green here: `bin/deploy` and the nine runners
already exist and are deployed, so deploying edits to them plus the new `skills/` tree is an
ordinary deploy, not installing a unit. No `sudo`, no `/etc` change.
