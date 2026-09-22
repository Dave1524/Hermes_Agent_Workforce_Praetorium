# Brief: T8.7 — SDLC measurements from ship-dev-plan LAND records
**Date:** 2026-09-22   **Verify:** `bash bin/verify.sh > /tmp/t87.out 2>&1; tail -5 /tmp/t87.out` (gate: syntax + shellcheck + `bin/check_deploy_drift.sh` + every `tests/*.sh`)

## What a LAND record is (measured 2026-09-22)
A ship-dev-plan land emits the same object twice; neither form carries a file list.
1. **In-repo, durable:** the archive commit the land agent writes at `.claude/workflows/ship-dev-plan.js:101` —
   subject `docs(briefs): archive <id> — <slug>`, a `R100 .claude/briefs/<slug>.md → .claude/briefs/archive/<date>-<slug>.md`
   rename, body carrying `verifyExit:`, `newRed:`, gate command + verdict, `diff_digest:`, `calibration_digest:`, plausible
   findings. Four September commits carry it: `9e028e6` T6.4, `0745241` T1.3, `9df0f25` T1.4, `e43b85d` T6.2 (hand-landed,
   same body shape, names its run `wf_b81f20cf-d44`). The nine other September archive commits (T5.3 `4421dce` … T5.3g
   `7f942cc`, T8.1 `5de7bcb`) have **no** land fields — PR/hand lands; `git log --since=2026-09-01 --format='%h %s' -- .claude/briefs/archive/`.
2. **Off-repo run records:** `~/.claude/projects/-home-dave-dev-agent-workforce/*/workflows/wf_*.json` (0600, not deny-listed),
   written by the Workflow harness: `workflowName`, `args.tasks`, `args.preShipped`, `result.{stoppedAt, failingAssertion,
   landed[{id,commit,archive,plausible}], ship{SHIP :56-59}, land{LAND :61-69}}`, `workflowProgress[]` one entry per agent
   with `label` (`ship:<id>`/`land:<id>`), `state`, `tokens`, `startedAt`. Eight `ship-dev-plan` runs on 2026-09-08 in session
   `dd1af567-…`; `wf_368e8723-8ae` (09-14) is `plan-dev-plan-briefs` and must be filtered out by `workflowName`.
   Every land attempt is recoverable: a run stops at the first failing task, so each attempt is either in `result.landed[]`
   or is `result.land` for `result.stoppedAt` (`ship-dev-plan.js:136-156`).
3. **The plan** is the archived brief itself: `## Files to modify|create|delete` bullets (`- \`path[:NN]\` — …`; T6.2 has all
   three sections, T1.4 names its own brief and a `:26` line suffix). The ship prompt commits the brief with the code
   (`ship-dev-plan.js:82`), so `git log --diff-filter=A -- .claude/briefs/<slug>.md` is the task's first commit on main.

## The three numbers — derivation, and which are clean
Per task `id` (from the archive subject), `brief = <slug>.md`, `first = git log --diff-filter=A --format=%H -- .claude/briefs/<slug>.md`
(exactly one; else `range: undefined`), `archive = the archive commit`, range = `first^..archive^` (excludes the rename).
- **first_pass** — CLEAN with run records: order `land:<id>` attempts by `startedAt`; outcome per attempt = `landed` (id in
  `result.landed[]`), `review` (`stoppedAt==id` and `result.land.reviewConfirmed` non-empty), `harness` (`result.land` absent,
  or `failingAssertion` contains `returned null`/`did not return`, or the progress entry `state=='error'`), else `other`.
  `first_pass = outcomes[0]=='landed'`; `landed_by = workflow|hand` (hand = id in no `result.landed[]`).
  GIT PROXY (no `--runs`): `first_pass = commits in range == 1`. Agrees on all four: T1.4 yes; T6.4, T1.3, T6.2 no.
- **rework** — CLEAN: `rework = count(review)`, reported next to `harness = count(harness)` so a stuck reviewer is never
  a rework. GIT PROXY: `commits in range − 1` (every later commit is a `fix(` here). Both give T6.4=3, T1.3=1, T1.4=0,
  T6.2=1; harness T6.4=1, T6.2=1 (land attempts 5/2/1/2). Cross-check when both exist; disagreement prints a `WARN` row, never fails.
- **plan_fidelity** — NOT in the LAND record, PROXY by construction: `named` = paths in the archived brief's three Files
  sections (strip backticks, `:NN`, the ` — …` tail, and the brief's own path); `touched = git diff --name-only first^ archive^`
  minus the brief. Report `|named∩touched|`, `unplanned = touched−named`, `not_done = named−touched`, `fidelity = |∩|/|∪|`.
  File-set overlap is a stand-in for the playbook's plan fidelity, and it saturates on this sample: 2/2, 2/2, 5/5, 11/11 → 1.0
  each (`git diff --name-only 5c93ea6^ 9e028e6^` vs the brief's bullets). The doc says so rather than dressing it up.
- **Not derivable without new instrumentation:** who approved (no reviewer identity anywhere), review effort actually used
  (only requested, `TASKS[id].review`), time-in-review. Out of scope; say so in the doc's footer.

## Acceptance criteria
- `python3 bin/sdlc_measurements.py --repo <path> [--since 2026-09-01] [--runs '<glob>'] [--markdown]` prints one row per
  archive commit that renames a brief into `.claude/briefs/archive/`; rows whose body lacks `verifyExit:` read `record: none`
  with `-` in every numeric column; nothing is ever defaulted to a success value.
- With `--runs`, first_pass/rework/harness come from the run records; without, from the git proxy, and the column header
  says which (`first_pass (git)` vs `first_pass`).
- `docs/sdlc-measurements-2026-09.md` exists, written once by redirecting `--markdown`, headed `MEASURED 2026-09-22`, with
  the exact command line that produced it, the table, a "No LAND record" list, and the two "not derivable" bullets above.
- `tests/test_sdlc_measurements.sh` green on and off the box (no box precondition, no new line in `tests/ci-expected-skips.txt`).
- `bash bin/verify.sh` exit 0, red lines equal today's baseline; `bin/check_deploy_drift.sh` clean after `bin/deploy`.

## Files to modify
- `design/fleet-suites.toml` — append a `[[suite]]` after `:786` (`path = "tests/test_sdlc_measurements.sh"`, `owner = "fleet"`,
  `asserts` = the four anchors below, `why_no_workflow` = it grades the ship pipeline's own record, no unit execs it).
  `tests/test_workflow_coverage.py:761-772` joins every declared id to a `(::id)` comment in the .sh/.py pair, both directions.

## Files to create
- `bin/sdlc_measurements.py` — stdlib only, `#!/usr/bin/env python3` (excluded from shellcheck by `bin/verify.sh:10-25`).
  Functions: `archive_commits(repo, since)` (`git log --diff-filter=R -M --name-status --format=…`), `parse_record(body)`,
  `brief_files(text)`, `git_range(repo, slug, archive)`, `land_attempts(runs, id)`, `measure(...)`, `render_markdown(rows)`.
  Shape after `bin/receipt_close.py:29` (argparse, `main(argv)`, importable).
- `tests/fixtures/sdlc-measurements/wf_fixture-a.json`, `wf_fixture-b.json` — trimmed copies of the real shape: run a stops
  at `T9.1` with `land.reviewConfirmed=["x"]`; run b has `preShipped.T9.1`, lands it (`result.landed=[{id:'T9.1',…}]`) and
  stops at `T9.2` with a `harness` attempt (`state:'error'`, `failingAssertion:'land agent returned null'`). Plus one
  `plan-dev-plan-briefs` record that must be ignored.
- `tests/fixtures/sdlc-measurements/briefs/t9-1-fixture.md` — modify (one with `:12`), create, delete sections, names itself.
- `tests/test_sdlc_measurements.py` — builds the git history in a tempdir with `GIT_ENV` as `tests/test_ship_rails.py:23-27,189`:
  commit brief+code, one `fix(` commit, archive commit with a `verifyExit:` body and the `R100` rename; a second task
  archived with no body; a third whose brief was added in a batch commit (range undefined).
- `tests/test_sdlc_measurements.sh` — the eight-line wrapper (`tests/test_receipt_sweep.sh` shape): `python3 tests/test_sdlc_measurements.py`.

## Test plan (anchors)
- `(::sdlc-record-set)` — only rename-into-archive commits with `verifyExit:` are records; the bodiless one reads `record: none`; the batch-brief one reads `range: undefined`; the non-ship-dev-plan run is ignored.
- `(::sdlc-first-pass-rework)` — from runs: T9.1 first_pass false, rework 1, harness 0, landed_by workflow; T9.2 harness 1; git proxy on the tempdir agrees; a forced disagreement prints WARN and exits 0.
- `(::sdlc-plan-fidelity)` — named parsing strips backticks/`:NN`/tail/own brief; unplanned and not_done sets exact; fidelity for a brief that names an untouched file is < 1.0 and both sets are printed.
- `(::sdlc-markdown-once)` — `--markdown` carries `MEASURED <date>`, the argv line, the record-none list; a second run is byte-identical (no clock reads beyond `--today`).

## Order of work
1. Fixture json + fixture brief + `tests/test_sdlc_measurements.py` (red) → wrapper → `[[suite]]` entry with the anchors.
2. `bin/sdlc_measurements.py` until the suite is green: `bash tests/test_sdlc_measurements.sh`.
3. **`bin/deploy`** — a new `bin/` file is DRIFT until then (`docs/runbook.md:168`); then `bash bin/verify.sh > /tmp/t87.out 2>&1`.
4. Live run: `python3 bin/sdlc_measurements.py --repo . --since 2026-09-01 --runs '/home/dave/.claude/projects/-home-dave-dev-agent-workforce/*/workflows/wf_*.json' --markdown --today 2026-09-22 > docs/sdlc-measurements-2026-09.md`; read it against the numbers in § The three numbers.
5. Commit by explicit path (six files + the doc + fleet-suites.toml); never `git add -A`.

## Out of scope / do not touch
- No change to `.claude/workflows/ship-dev-plan.js`, no new fields in the LAND schema, no hook, no timer, no manifest row.
- No per-task token/cost column (derivable from `workflowProgress[].tokens`, not asked; the 47M/29M figure stays in memory).
- PR/hand lands (T5.x, T6.1, T8.1): listed as `record: none`, not measured through merge commits.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, existing tests, `tests/ci-expected-skips.txt`.

## Risks
- `~/.claude/projects/**/workflows/` is session state the harness may prune; the git proxy is the durable path and the doc
  records which path produced each column. The run glob is an argument, never a default outside the repo.
- The fixture is the only test of the run-record shape; a harness format change shows up as `record: none`/`harness`
  counts, not as a crash — assert the parser tolerates missing keys (`result.land` absent in `wf_d02ea773-4c0`).
- Fidelity saturating at 1.0 invites "the number is useless"; it is the finding (deviation lands as fix commits inside
  named files), and rework carries the signal. Say that in the doc once.
- `docs(briefs)` subjects are prose (`T5.3g — runtime controls: start / stop …`); key rows on the rename target, not the subject.

## Notes / preconditions
- Baseline red on main today: read it from the verify output before step 3, do not assume 0.
- Author env for the fixture repo must set `GIT_CONFIG_GLOBAL=/dev/null` or the box's `Marcus (Praetorium)` identity and hooks leak in.
- The T8.1 PreToolUse hook blocks edits under `tests/` of *existing* suites and `git add -A`; new files under `tests/` are fine.
