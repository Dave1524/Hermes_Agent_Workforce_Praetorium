# Brief: T8.2 — Protect main: PR + `gate` check required; auto-sync retired
**Date:** 2026-09-22   **Verify:** `bash bin/verify.sh` (repo root)   **Phase:** D, Dave-only — decision packet first; `/implement` only after the decision is on the card.

## Measured 2026-09-22 (all read-only)
- Repo is `Dave1524/Hermes_Agent_Workforce_Praetorium` (`git remote -v`), public, one collaborator (`gh api …/collaborators` → `Dave1524`). The card's probe named `Dave1524/agent-workforce`, which 404s as a *repo*; the real probe answers `Branch not protected` (404), `…/rulesets` → `[]`, `…/rules/branches/main` → `[]`.
- Every push from this box is Dave1524: `~/.gitconfig` `credential.https://github.com.helper = !/usr/bin/gh auth git-credential`; `gh auth status` → Dave1524, scopes `repo workflow`. The contract's "origin over `~/.ssh/id_agent_workforce`" (`design/contracts/agent-workforce-auto-sync.md:36`) is stale — the remote is HTTPS.
- PRs #57–#62: `author=Dave1524, mergedBy=Dave1524, reviews=[]` (CodeRabbit comments only). GitHub refuses self-approval, so with one login the card's "approver distinct from the login that landed it" is unsatisfiable. **A second identity is a precondition of every protect option.**
- The CI check-run is named **`gate`** (job id, `.github/workflows/verify.yml:22`; `check-runs` on #62's head → `{"name":"gate","app":"github-actions"}`, Actions app id `15368`). The workflow is `verify`; a ruleset requires the *check* name. `verify.yml:13-16` triggers on `pull_request` only.
- Main, last 14 days, first-parent: **160 commits — 29 PR merges, 12 auto-sync, 119 direct.** 82% bypassed a PR. Auto-sync carried real work: `9070016` = T8.1's `ship_rails.py` + 717 test lines, no PR, no CI.
- The App the vault pushes with (`~/.local/bin/github_app_credential.py`, config `~/.config/agent-workforce/vault_app.env`, repo-local helper in the vault clone's `.git/config`) is installed on **one** repo, `Dave1524/Obsidian_AI_Operating_System` (`GET /installation/repositories`, token never printed). The vault's ruleset `protect-main-agent-membrane` (id 20737589) is `update`+`deletion`+`non_fast_forward` with admin (`RepositoryRole 5`) bypass — a membrane, no PR or check rule.
- `agent-workforce-auto-sync.timer`: `ActiveState=active`, `UnitFileState=disabled` (started, not enabled). Manifest row `design/agents/trajan.toml:214-225`, suite `tests/test_auto_sync.sh` (43 assertions, offline).
- Land phase today (`.claude/workflows/ship-dev-plan.js:94-101`): rebase in `land-<id>` worktree → `git merge --ff-only` on main → deploy → verify → gate → `/code-review` → `git push origin main` → archive-brief commit → `git push origin main`. Both pushes are refused under any protect option.

## The decision (Dave)
| | Costs | What breaks |
|---|---|---|
| **A. Protect + retire auto-sync** (recommended) | Every change to main is a PR the box opens as the App and Dave approves: ~2–4/day if chores fold into task PRs, ~9/day at the raw rate above. The dirty tree is no longer pushed every 15 min (backup value gone). | `bin/auto-sync:76`; land phase `:94,:101`; every interactive `git push origin main`; control-room PRs (`bin/workflow_pr_git.py:25-26` opens as Dave1524 → unapprovable). All in this plan. |
| **B. Protect + auto-sync pushes a branch** | Same approval load as A, plus a standing `box/auto-sync` branch nobody owns: generic `Auto-sync:` commits pile up until someone opens a PR from them, and a PR-per-sweep bills a CI run per housekeeping commit — the cost `verify.yml:10-12` refused on purpose. | Same as A. `bin/auto-sync:6,:76` push target changes; 8 `origin_head` assertions in `tests/test_auto_sync.sh` rewrite. |
| **C. Keep as is, record the reason** | Nothing now. The record stays unable to show approval; T8.1's rails (`.claude/hooks/ship_rails.py`) are the only push guard, and rails are rules you keep. | Nothing. Close the card with the reason. |

**Recommendation: A.** One reason: the PR is already this repo's unit of review — CodeRabbit and `gate` run on it and nowhere else — and protection sends the 82% that bypass it through the same door; once a `main` push is refused, auto-sync has no purpose left to keep on a branch.

## Design (A)
- **Identity split.** Box authors, pushes and merges as the App (`<slug>[bot]`); Dave approves as Dave1524. The App needs `contents: write`, `pull_requests: write` — *unverified*: the JWT probe was denied by the classifier; Dave reads them on the App's settings page.
- **Ruleset** on `~DEFAULT_BRANCH`, `enforcement: active`, `bypass_actors: []`: `pull_request {required_approving_review_count: 1, dismiss_stale_reviews_on_push: true, require_last_push_approval: false, required_review_thread_resolution: false}`, `required_status_checks {strict_required_status_checks_policy: false, required_status_checks: [{context: "gate", integration_id: 15368}]}`, `deletion`, `non_fast_forward`. No admin bypass: an emergency is Dave editing the ruleset (audit-logged), not pushing around it. Created by Dave (`gh api -X POST repos/$R/rulesets` from the Mac, or the UI); the box's test reads it back.
- **Land phase becomes two runs.** Run 1 (`land:<id>`): rebase in the worktree, verify, plan gate, review **in the worktree**, archive-brief commit **on the branch**, push branch, `bin/gh_app.sh pr create` with the evidence body, return `awaiting: {pr, headSha}` — a clean return, not a stop. Run 2 (`args.approvedPR[id] = {pr, headSha}`, label `land-merge:<id>`): assert `gh pr view --json reviewDecision,statusCheckRollup,headRefOid` = `APPROVED` / `gate` success / same sha, `bin/gh_app.sh pr merge --merge --delete-branch`, `git pull --ff-only origin main`, deploy (`deploy: true` only), fleetStart/enabled checks, `mainHead === originMainHead`.
- **Deploy moves after merge** (nothing unapproved reaches the runtime). Consequence: for `deploy: true` tasks run 1's verify shows `DRIFT` on the task's changed `bin/` files; treat `DRIFT` lines naming a path in `git diff --name-only origin/main..HEAD` as expected in run 1, and run 2 re-verifies against the baseline alone after deploying.

## Acceptance criteria
- `gh api repos/$R/rules/branches/main` lists `pull_request`, `required_status_checks` (context `gate`), `deletion`, `non_fast_forward`; `git push origin main` from the box is refused server-side (proven once, output kept).
- `agent-workforce-auto-sync` retired through `bin/workflow_pr.py retire` — `design/retired-workflows.toml` entry, unit files gone from `systemd/` and `/etc/systemd/system/`, `bin/auto-sync` and `tests/test_auto_sync.sh` deleted, contract archived, `tests/test_workflow_retirements.sh` green after `workflow_pr.py clear`.
- One task landed through the new land phase: its PR shows `author: <app>[bot]`, a review `Dave1524 APPROVED`, check `gate` success, `mergedBy: <app>[bot]`; the sha and PR number recorded on the card.
- Control-room PRs are App-authored (`gh pr view <n> --json author` on the next schedule/retire PR).
- `bash bin/verify.sh` green on main; CI `gate` green on every PR of this work.

## Files to modify
- `.claude/workflows/ship-dev-plan.js` — `:7` phase detail; `:11-15` args doc (+`approvedPR`); `LAND` schema `:61-67` (+`pr`, `awaiting`); `landPrompt` `:92-102` steps 1, 2, 7 per Design; loop `:136-157`: `awaiting` → collect and return `{awaitingApproval: [...]}` with no `stoppedAt`; `approvedPR` → skip ship, run `land-merge:<id>`; `WORKFLOW_ENTRIES` `:29` 32→31 (the retire plan does this: `bin/workflow_pr_retire.py:28`).
- `tests/test_ship_dev_plan_workflow.sh` — scenarios: run 1 ends awaiting with nothing stopped; run 2 lands; land prompt carries `gh_app.sh pr create` and no `--ff-only`/`git push origin main`; land-merge prompt refuses on `reviewDecision != APPROVED` or sha mismatch.
- `bin/workflow_pr_git.py:25-26` — `GITCONFIG` helper → `!python3 /home/dave/.local/bin/github_app_credential.py`; `bin/workflow_pr.py` ~`:300` — run `gh pr create`/`gh pr list` through `bin/gh_app.sh` (or mint `GH_TOKEN` the same way). `tests/test_workflow_pr_schedule.py` / `test_workflow_pr_retire.py` expectations follow.
- `CLAUDE.md` § Where things live (the auto-sync paragraph → "main is protected; branch + PR; the box is the App; check = `gh api …/rules/branches/main`"); § Hard constraints (main push refused server-side, like the vault); § Verification (the protection suite skips off-box).
- `README.md:25-27` (Auto-sync section → replaced), `docs/runbook.md:160,:250` + § Control Room proposals (author is the App), `.github/workflows/verify.yml:10-12` (reason for no `push` trigger is now protection), one-line mentions in `design/agent-model.md`, `design/eval-spec.md`, `design/contract-schema.md`, `design/contracts/agent-drift-check.md`.
- `tests/test_control_room_views.py:169` — `assertIsNone(rows["agent-workforce-auto-sync"]["guards"])` names the retired row by hand; drop it (the retire plan covers count literals, `bin/workflow_pr_retire.py:26,:28`, not this line).
- `tests/ci-expected-skips.txt` — the new protection suite's `SKIP:` line.
- `~/dev/agent-workforce/.git/config` (not in git) — repo-local `credential.https://github.com.helper` pair as the vault clone has, so branch pushes are the App; record the command in the runbook.

## Files to create
- `bin/gh_app.sh` — `exec env GH_TOKEN="$(printf 'protocol=https\nhost=github.com\n' | python3 ~/.local/bin/github_app_credential.py get | sed -n 's/^password=//p')" gh "$@"`; refuses with a message and exit 2 on an empty token; never echoes it. Deployed by `bin/deploy` like any `bin/` script.
- `tests/test_gh_app.sh` — offline: a fake helper on `PATH`/`VAULT_APP_ENV` and a fake `gh` that prints `$GH_TOKEN`; asserts argv passthrough, the token reaches `gh`'s env only, empty token → exit 2, token string absent from stdout/stderr. Carries the `yes | grep -q y` canary.
- `tests/test_main_protection.sh` — box-only (`tests/box_precondition.sh`; the one suite that reads GitHub): asserts the four rule types and the `gate` context on `rules/branches/main`, and that the App installation lists this repo. `SKIP:` off-box.
- `design/retired-workflows.toml` entry + `design/archive/contracts/agent-workforce-auto-sync.md` — written by the retire plan, not by hand.

## Test plan
- `tests/test_gh_app.sh`, `tests/test_main_protection.sh`, the `test_ship_dev_plan_workflow.sh` scenarios above — all under `bin/verify.sh`.
- Retirement residue: `tests/test_workflow_retirements.sh` red between merge and `workflow_pr.py clear`, green after; `bin/check_deploy_drift.sh` green once `/etc` units are removed and `bin/deploy --prune` has dropped `bin/auto-sync`.
- Live proof (acceptance 3): one S task via `/ship-dev-plan`, two runs; the PR's `author/reviews/mergedBy/checks` JSON pasted into the archive-brief commit body.

## Order of work
1. Dave: add this repo to the App installation (GitHub → Settings → Applications → the App → Repository access); confirm `contents: write`, `pull_requests: write`. Box proves: `GET /installation/repositories` → 2 repos.
2. `bin/gh_app.sh` + test + repo-local helper; prove a branch push and `bin/gh_app.sh pr create` show `<app>[bot]`.
3. Retire auto-sync via `bin/workflow_pr.py retire` **before** protection (Dave can still merge his own PR); Dave clears residue by hand (`sudo systemctl stop`, rm units, `daemon-reload`, `bin/deploy --prune`); `workflow_pr.py clear`.
4. Land-phase PR (ship-dev-plan.js + tests) and the control-room PR authorship change — one PR, merged pre-protection.
5. Dave creates the ruleset. Box runs `tests/test_main_protection.sh` and one refused `git push origin main`.
6. Docs PR (CLAUDE.md, README, runbook, verify.yml comment) — the first PR landed through the new phase; its evidence closes acceptance 3.

## Risks
- **Approval latency**: a shipped task waits on Dave between runs; nothing deploys meanwhile. Mitigation: `awaitingApproval` is a clean return; `approvedPR` resumes without re-shipping (same shape as `preShipped`, `:16-23`).
- **Pre-merge DRIFT for deploy tasks** (Design, last bullet): a set-diff mistake there lands or blocks wrongly — the scenario test must cover a `deploy: true` task.
- **Local main divergence**: an interactive session that commits on main can no longer push; `git pull --ff-only` fails. Rails and CLAUDE.md say branch first; optionally `git config branch.main.pushRemote no_push` for a local fast failure.
- **Control-room PRs unapprovable** if step 4 lands after step 5 — order matters.
- **Token lifetime**: installation tokens live 1 h; the helper caches and re-mints, so a >1 h land-merge run still works.
- **`vault_app.env` name is now misleading** (it is the box's App for two repos); rename is out of scope, note it in the runbook.
- **Dave's own Mac pushes to main are refused too** (no bypass actor). Intended; say so on the card.

## Out of scope / do not touch
- The vault repo's ruleset (a membrane; separate decision). `required_signatures`. CodeRabbit as an approver. New `ship_rails.py` rules. `bin/verify.sh`, `bin/check_deploy_drift.sh`, existing tests' semantics. `~/CLAUDE.md`'s stale `id_agent_workforce` line (box-level file; note it).

## Notes / preconditions
- Rulesets with a PR rule work on a free account's public repo; the vault's active ruleset shows the account can create them. Actions app id `15368` (`gh api apps/github-actions`).
- Pushes with an installation token from outside Actions **do** trigger `pull_request` workflows (only `GITHUB_TOKEN` pushes are suppressed).
- `control-room.service` runs as `dave`, no `ProtectHome` (`systemctl cat`), so the helper's config path is readable there.
- `bin/workflow_pr_git.py:73` already passes `GH_TOKEN` through.
- **Where B differs**: `bin/auto-sync` keeps `PRIMARY=main` for the pull and pushes `HEAD:refs/heads/box/auto-sync` at `:76`; no retire; `tests/test_auto_sync.sh` asserts on that ref; a PR from that branch is opened by hand when wanted. Land phase and identity changes are identical to A.
- **Where C differs**: no code; the card records the reason and `tests/test_main_protection.sh` is not written. The stale contract line (`:36`) still gets fixed.
