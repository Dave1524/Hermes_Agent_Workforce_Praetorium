# Brief: the drift check covers the systemd staging tree
**Date:** 2026-09-04   **Verify:** `bash bin/verify.sh` (repo root)

## The defect, stated once

`bin/deploy` ships eight paths (`bin/deploy:20`):

    PATHS=(bin profiles docs CLAUDE.md AGENTS.md README.md config systemd)

`bin/check_deploy_drift.sh:72` compares six of them against their deploy destination:

    CONTENT_TREES="${DRIFT_CONTENT_TREES:-profiles docs config CLAUDE.md AGENTS.md README.md}"

`bin` is the seventh, compared separately (`SRC_BIN` vs `RUNTIME_BIN`). **`systemd` is the
eighth and its deploy destination is compared by nothing.** `systemd/` IS compared — against
`/etc/systemd/system/`, as a unit tree — but that is a different destination. The copy
`bin/deploy` actually writes, `~/agent-workforce/systemd/`, has no comparison at all.

**The assertion that should have caught this is what hides it.** `tests/test_deploy_drift.sh`
16b (lines 710-722) builds the "compared" set as:

    checked=$( { sed -n 's/^CONTENT_TREES=...//p' "$CHECK" | tr ' ' '\n'
                 printf 'bin\nsystemd\n'; } | LC_ALL=C sort)

`systemd` is credited by a **hardcoded `printf` in the test itself**, not measured from what
the check compares. So 16b asserts 8 = 8 and passes while one of the eight is uncovered. The
test's own comment calls itself "that join, asserted instead — in both directions, so neither
list can grow or shrink alone", which is true of `bin` and false of `systemd`.

**The gap is already populated.** Measured 2026-09-04: source `systemd/` holds 67 files, the
runtime staging copy holds **70**. The three extras are exactly what `bin/deploy --dry-run
--prune` names, and no check has ever reported them:

| runtime file | source |
|---|---|
| `systemd/discord-bot.service` | none, in any tree |
| `systemd/content-inbox-finalize.service` | `systemd/archive/` (deliberately not deployed) |
| `systemd/content-inbox-finalize.timer` | `systemd/archive/` (deliberately not deployed) |

Same class as W7, which widened this check from 2 of 8 paths to 7 of 8 on 2026-09-03.

## Acceptance criteria

1. `bin/check_deploy_drift.sh` compares source `systemd/` against `$RUNTIME_ROOT/systemd/` in
   all three membership directions the other content trees get — `content differs`,
   `source-only`, `runtime-only` — with the same `design/deploy-exclusions.toml` lookup on the
   runtime-only direction.
2. Run against this box **before** the orphans are resolved, the check reports exactly three
   new findings, naming `discord-bot.service` and both `content-inbox-finalize` files. Not two,
   not four. This is the proof the widening reaches something; assert the count.
3. `tests/test_deploy_drift.sh` 16b no longer credits `systemd` from a hardcoded `printf`.
   After the change the literal added by the test is `bin` alone, and `systemd` arrives from
   parsing the real `CONTENT_TREES`. The `8 = 8` vacuity guard on line 721-722 stays.
4. The fixture suite proves the staging tree is compared, not merely listed — see Test plan.
5. `bash bin/verify.sh`: **0 `FAIL:` lines.** Drift on the branch is expected and bounded (see
   Notes); `rc=0` comes after merge + deploy + the operator step in criterion 6.
6. The three staging orphans are removed from `~/agent-workforce/systemd/` by targeted `rm`,
   **not** by `bin/deploy --prune`.

## Files to modify

- **`bin/check_deploy_drift.sh`**
  - line 72: add `systemd` to the `CONTENT_TREES` default. This is the whole functional change —
    the loop at 333+ already handles nested trees (`systemd/user/`, `systemd/archive/`,
    `systemd/qmd-mcp.service.d/` all exist in both copies and their shapes match).
  - lines 68-71: the comment says "The six trees bin/deploy ships that were compared by
    nothing until 2026-09-03 (W7)". Make it seven, and record WHY `systemd` was missed — it
    was compared against `/etc` and that read as covered. One tree, two destinations, and only
    one of them was being checked.
  - line 389: the `scope=bin` info line says "the three unit trees are NOT compared by this
    invocation (the six content trees above ARE)". Update the count.
  - Keep the findings under the existing `content` category. `report content` is correct here:
    the header comment at 325-327 says content trees belong to `SCOPE=bin` *because bin/deploy
    writes them*, which is exactly true of the staging copy. The `systemd/` path prefix in the
    message keeps it distinguishable from the `[system]` (`/etc`) findings.

- **`tests/test_deploy_drift.sh`**
  - 16b (710-722): drop `systemd` from the `printf`. Leave the count assertion at 8.
  - Section 16 fixture group: add the three staging assertions. **The fixture overrides the
    list** — `drift()` at line 93 passes `DRIFT_CONTENT_TREES="profiles config NOTE.md"`, so a
    change to the production default is invisible to every fixture test. Add `systemd` to that
    fixture list, or the new assertions silently test nothing.

- **`tests/ci-expected-skips.txt`** — only if the `check_deploy_drift.sh` SKIP line's absent-path
  list changes. It currently names `~/agent-workforce/bin ~/.config/systemd/user
  ~/.config/buzz-team`. Content trees resolve under `AGENT_WORKFORCE_RUNTIME`, already covered
  by the `~/agent-workforce/bin` probe, so it likely does **not** change — verify, don't assume.
  If the printed line changes and this file does not, CI's skip diff fails.

## Files to create

None. Every new assertion belongs in `tests/test_deploy_drift.sh`, which already owns this
check; a second suite would split one subject across two files.

## Test plan

In `tests/test_deploy_drift.sh`, section 16 (fixture-based, after adding `systemd` to the
fixture's `DRIFT_CONTENT_TREES`):

- a file in `$root/run_content/systemd/` with no source counterpart is reported
  `runtime-only: systemd/<name> has no source and is declared in no exclusion`
- declaring it in the fixture `exclusions.toml` with `tree = "systemd"` clears the finding and
  still prints the `info:` line naming `pending bin/deploy --prune`
- a file in `$root/src_content/systemd/` absent from the runtime is `source-only`
- differing bytes are `content differs: systemd/<name>`
- a file in a **nested** staging path (`$root/run_content/systemd/user/orphan.service`) is
  reported — the tree is not flat, and a `-maxdepth 1` regression would pass every assertion
  above while missing `systemd/user/` and `systemd/archive/` entirely

In 16b (reads the real script, no fixture):

- the two `comm` directions and the `8 = 8` vacuity guard, unchanged in shape
- the `printf` literal is `bin` only — add an assertion that the test does not itself supply
  `systemd`, so this laundering cannot be reintroduced:
  `! grep -q "printf 'bin\\\\nsystemd\\\\n'" tests/test_deploy_drift.sh`

**Mutation proof required before declaring done.** Revert the one-word `CONTENT_TREES` change
and confirm the new assertions go red — specifically that 16b fails. If 16b still passes with
`systemd` absent from `CONTENT_TREES`, the laundering has been reproduced rather than removed,
and that is the entire point of this brief.

Keep the `yes | grep -q y` canary; `assert()` scopes `pipefail` off and must stay that way.

## Out of scope / do not touch

- **Item 6 — `AGENT_VERIFY_CMD` in the live `m1_signal_scan.env`.** The path
  `~/.config/agent-workforce/` is on the Claude Code deny-list, so no agent on this box can
  read, write or verify it. Dave-only, one line appended to
  `~/.config/agent-workforce/m1_signal_scan.env`:
  `AGENT_VERIFY_CMD="$HOME/agent-workforce/bin/proposal_or_decline.sh m1-signal-scan"`
  — the value is already in `profiles/m1_signal_scan.env.example` (W15). Do not attempt it.
- **`bin/deploy --prune`.** Still 12 files: 9 declared exclusions (5 `profiles/`, 4
  `config/job-overrides/`) plus the 3 this brief makes visible. `--prune` is `rsync --delete`
  across all eight paths with no per-tree scoping — it cannot be aimed. The 9 stay a human
  decision; the 3 go by targeted `rm`.
- `~/deploy-staging/` — a different tree, not in `bin/deploy`'s PATHS.
- The unit-tree half of the check (`systemd/` vs `/etc`). It is correct and unchanged.
- Do not add an expiry-dated exclusion for the 3 orphans. `design/deploy-exclusions.toml`
  carries no dates by design, and an exclusion outliving its subject is the same defect
  pointing the other way — the file's own header says so.

## Notes / preconditions

- **Worktree**: `/home/dave/agent-worktrees/briefs` was 24 commits behind and is now on
  `feat/drift-covers-staging-systemd` off `f738ff7`. Confirm with `git rev-parse --short HEAD`
  before starting.
- **The gate cannot be green on this branch.** It edits `bin/check_deploy_drift.sh`, so
  `content differs: check_deploy_drift.sh` is reported until `bin/deploy` runs, and the repo's
  loop is edit → deploy → verify → commit. Deploying an unmerged branch to the live runtime is
  not something to do casually. Expected branch state: **0 `FAIL:`**, drift limited to
  `[bin] content differs: check_deploy_drift.sh` plus the 3 staging orphans. Report that; do
  not soften the check to reach `rc=0`.
- **Baseline as of `f738ff7`, measured 2026-09-04**: `bin/verify.sh` exits 0 with `drift:
  clean`, 2558 assertions, 0 FAIL, 53 suites, one expected skip (`OpenCode`, a cost opt-in).
  Any FAIL you see is yours.
- `~/dev/agent-workforce` has `agent-workforce-auto-sync.timer` firing every 15 minutes over
  the SOURCE checkout — it does `git add -A` and pushes to `origin/main`. This worktree is a
  different path and is not swept, but commit promptly regardless.
- Never `git add -A`; stage by explicit path. The repo is public — no key material.
