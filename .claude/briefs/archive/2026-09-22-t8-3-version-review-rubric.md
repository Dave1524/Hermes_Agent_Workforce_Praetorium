# Brief: T8.3 — Version the review rubric with the code it judges
**Date:** 2026-09-22   **Verify:** `bash bin/verify.sh` (extra-gates: none for this repo; smoke: none)

Source: `~/OUTBOX/sdlc-playbook-gap-2026-09-15.md` gap 3 + row "AI PR review" (rubric outside the repo). Live file measured
2026-09-22: `~/.config/buzz-team/aurelian-calibration.md`, 7121 B, mtime 2026-08-13 11:28 +0200, sha256
`6e3b7a575558…9b3` = the pin at `buzz-team/MANIFEST.toml:252` (no drift today). No repo copy anywhere:
`git log --all -- '*aurelian-calibration*'` and `git ls-files | grep -i calibration` are both empty.

## Acceptance criteria
- `buzz-team/aurelian-calibration.md` exists, byte-identical to the live file (`cmp`), declared `[[adopted]]` (path/read_by/why, the
  shape at `MANIFEST.toml:65-68`); the `[[excluded]]` block at `MANIFEST.toml:249-258` is gone.
- `bash bin/verify.sh` exits 0 with no `DRIFT [buzz]` line for the file — the in-both-trees loop (`bin/check_deploy_drift.sh:643-654`)
  finds it adopted and `cmp`-equal; no converge and no restart is needed to get there.
- `bin/deploy_buzz_team.sh --dry-run` prints `live tree already current. Nothing to do.` (`:112-113` skips equal files, `:130-133`).
- `.claude/workflows/ship-dev-plan.js` land step 5 (`:98`) reads `buzz-team/aurelian-calibration.md` and computes
  `calibration_digest = sha256sum buzz-team/aurelian-calibration.md`; the string `.config/buzz-team/aurelian-calibration` no longer
  appears in the script. Step 7 (`:101`) still records the digest in the archive commit — unchanged.
- New suite `tests/test_review_rubric.sh` green and claimed in `design/fleet-suites.toml` (orphan rule: `tests/test_workflow_coverage.py:629-647`).

## Design decision
The land prompt reads the **checkout-relative** repo copy (the land agent works in the main checkout after the ff-merge, `ship-dev-plan.js:91-92`),
not the deployed path. Step 3's `bin/verify.sh` (`:95`) runs the drift check before step 5, so the copy it digests is proven byte-identical to what
aurelian's live session and `buzz-team/verify-fleet.sh:422-429` (gate 12) read — and the digest is of the rubric *at the landed commit*, which is the
card's title. `verify-fleet.sh:422` keeps the deployed path: it measures the box. The pack's own § Binding says `calibration_digest` is "sha256sum of
this file" (`:49`), so the move changes no digest semantics, and byte-identity keeps the digest history continuous (`6e3b7a57…` before and after).

## Files to modify
- `buzz-team/MANIFEST.toml` — delete `:249-258`; append after `watch-test.sh` (`:210-214`) one `[[adopted]]` entry: `path = "aurelian-calibration.md"`,
  `read_by = "ship-dev-plan.js land step 5 (sha256sum -> calibration_digest in every archive commit); verify-fleet.sh gate 12 on the deployed copy; aurelian, as instruction"`,
  `why` stating: the review policy that gates every land was outside the repo it gates (T8.3); the prose-out rule's two reasons answered — public repo:
  read 2026-09-22, no client string (tool, folder and Notion database names only; re-read before every edit, as TEAM.md's pin rule at `:229-230` demands);
  "second home to drift in": `cmp` both directions every verify run is stronger than a pin, and the repo is now the source; adopted byte-identical
  (`ADOPT WHAT IS LIVE`, `:47-51`), edits are commits after adoption that bump `**version: N**` and the H1's `vN` together; a rubric-editing task is a
  deploy task whose runtime action is `bin/deploy_buzz_team.sh` (nothing execs the file — no restart). Add one sentence after `:27` ("Stays machine-level."):
  one prose file is adopted, `aurelian-calibration.md`, for the reason in its entry.
- `.claude/workflows/ship-dev-plan.js:98` — replace `Read ~/.config/buzz-team/aurelian-calibration.md § "Code / config"` with
  `Read buzz-team/aurelian-calibration.md (the repo copy at the merged main; step 3's drift check has proven it byte-identical to ~/.config/buzz-team/) § "Code / config"`
  and `calibration_digest = sha256sum of that file` with `calibration_digest = sha256sum buzz-team/aurelian-calibration.md`. Template literal: no backticks, no `${`.
- `design/agents/aurelian.toml:79` — `profile` parenthetical: `.prompt` deny-listed, no repo source; the calibration pack's source is `buzz-team/aurelian-calibration.md` (T8.3). Keep `profile_in_repo = false` (`:80`, the `.prompt` half).
- `design/fleet-suites.toml` — new `[[suite]]` (`path`, `owner = "fleet"`, `asserts`, `why_no_workflow`; shape at `:696-714`) claiming the three anchors below.

## Files to create
- `buzz-team/aurelian-calibration.md` — `cp -p ~/.config/buzz-team/aurelian-calibration.md buzz-team/ && cmp` the two. Not edited on the way in.
- `tests/test_review_rubric.sh` — `set -uo pipefail`, the repo's `assert()` (pipefail scoped off, `tests/test_adapter_versions.sh:12-15`), `yes | grep -q y` canary. Anchors:
  `(::rubric-adopted)` file on disk; `tomllib`: in `adopted` with non-empty `read_by`+`why`, in no `excluded` row.
  `(::rubric-version-line)` repo copy has `^\*\*version: [0-9]+\*\*` (the shape gate 12 greps at `verify-fleet.sh:427`) and the H1 `— v<N>` agrees.
  `(::land-reads-repo-rubric)` `ship-dev-plan.js` contains `sha256sum buzz-team/aurelian-calibration.md` and not `.config/buzz-team/aurelian-calibration` (grep on source; no node).

## Test plan
- `bash tests/test_review_rubric.sh` red on main before the change (file absent), green after; each anchor proven to bite once (delete the entry / edit the version line / restore the old path in a temp copy via `SHIP_DEV_PLAN_SCRIPT`-style env or a fixture copy).
- `tests/test_buzz_interactive_harness.sh` already asserts tree ⇔ manifest both directions, `why` present, and no 64-hex in any adopted file (`:80-104`, `:118-160`); the pack has none (`grep -cE '[0-9a-f]{64}'` = 0). Unchanged, must stay green.
- `bash bin/verify.sh` green: the `[buzz]` info line `box-only: aurelian-calibration.md — declared excluded, content pinned` (`check_deploy_drift.sh:627`) disappears, no `DRIFT` replaces it.

## Order of work
1. One commit: copy + `cmp`, manifest flip (delete excluded block, add adopted entry, header sentence), `aurelian.toml:79`, new suite + `fleet-suites.toml` entry. **Copy and manifest never split:** copy-first reads red at `check_deploy_drift.sh:647` (in both trees, declared EXCLUDED); manifest-first reads red at `:634` (box-only, no source). Drift is clean at this commit with no deploy.
2. Second commit, same branch, after 1: the `ship-dev-plan.js:98` path change. Never before 1 on main — the next land's step 5 would `sha256sum` a path main does not have. The T8.3 land itself runs the pre-merge script text (loaded at workflow launch), which reads the deployed path — present and identical — so either text resolves during this land.
3. After land, proof only: `bin/deploy_buzz_team.sh --dry-run` → "already current"; `bash bin/check_deploy_drift.sh` → no `[buzz]` line for the file. Nothing to restart (`deploy_buzz_team.sh:15-22` is about rules files; nothing execs this one).
4. If shipped through `ship-dev-plan.js`, add a `TASKS` row (`:32-59` has no T8.3): `deploy: false, shipsRed: false, expectedRed: [], gateCmd: "bash tests/test_review_rubric.sh"`.

## Out of scope / do not touch
- Four stale mentions of the file as excluded, all comment text: `bin/deploy_buzz_team.sh:25-26` (also its `--help`, `:44`), `bin/check_deploy_drift.sh:216-218,292-298`,
  `tests/test_deploy_drift.sh:479-483`, `tests/test_ship_rails.py:146` (mirror of the old `sha256sum` line; still rails-allowed). Rails refuse the last three
  (`.claude/hooks/ship_rails.py:20,74-77`) and the `bin/` one would make this a deploy task for a comment. Named follow-up **"T8.3 comment sweep"**: one interactive commit under
  `SHIP_RAILS_OVERRIDE="T8.3 comment sweep"` then `bin/deploy`. Rubric `:126` makes a named scope-out a non-finding; `:72` does not apply — the declaration has one owner.
- The rubric text and its version: no edit, no bump (byte-identity). `buzz-team/verify-fleet.sh:422` (deployed path). `design/phaseb-brief-queue.toml:104` (historical brief record).
- `~/.config/buzz-agents/**` (deny-listed; `aurelian.prompt` untouched, unread). No unit restart, no `bin/deploy`, no `.claude/briefs/current.md`.

## Risks
- **Publication.** Merge publishes the pack within 15 min (auto-sync). Read in full 2026-09-22: no client name; it names Notion databases, a vault skill slug and box paths — the class TEAM.md already carries. Every future edit is a reviewed PR; the `why` says re-read for client content.
- **Self-judged edits.** A PR that weakens the rubric is reviewed under its own copy — same property as a PR editing its own tests, which the rails refuse (`ship_rails.py:74`). Follow-up option: add `buzz-team/aurelian-calibration.md` to `GATE_SCRIPTS` (`:20`) so a rubric edit needs `SHIP_RAILS_OVERRIDE`. Not this task.
- **Future rubric edits land red** at `check_deploy_drift.sh:653` (`content differs`) until `bin/deploy_buzz_team.sh` runs — the rule every adopted file already lives under; a rubric task is `deploy: true` with that one runtime action.
- **Land reviewer flags the stale comments** despite the named scope-out; if so, the comment sweep is the fix, not a rewrite of this brief.

## Notes / preconditions
- Live sha equals the pin today; if `bin/check_deploy_drift.sh` reports `content pin: aurelian-calibration.md changed` before step 1, stop — settle the pin first, then adopt the live bytes.
- The rails hook is active in every session in this repo (`.claude/settings.json:17`): a new `tests/` file is allowed, existing ones refused — which is why the test plan is a new suite.
- `MANIFEST.toml:34` ("every prose entry carries a sha256") stays true for the two remaining prose exclusions; the harness key guard parses pins from `[[excluded]]` only (`test_buzz_interactive_harness.sh:144-152`), so removing this pin needs no suite edit.
