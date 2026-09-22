# Brief: T8.1 — PreToolUse hook turns the ship RAILS into blocks
**Date:** 2026-09-22   **Verify:** `bash bin/verify.sh` (extra-gates: none for this repo; smoke: none)

Tracker card: Notion `3e38d768-1ede-81fc-af39-f736668518a9` (Phase "1 Self-checking gate", size S,
Assignee Claude). Source: `~/OUTBOX/sdlc-playbook-gap-2026-09-15.md` gap 1 — every rail in
`.claude/workflows/ship-dev-plan.js` `RAILS` (lines 71-75) is prose an agent keeps; the repo's
hooks are graft telemetry only. Same move `~/CLAUDE.md` made for the path deny: a rule kept
*for* you, not by you.

## Acceptance criteria

Card gate, verbatim: *a session that edits `tests/`, `bin/verify.sh` or `bin/check_deploy_drift.sh`,
or runs `--no-verify`, `git add -A`, `deploy --prune` or `systemctl start|stop|restart|enable|disable`,
is refused by the hook; one fixture per rail; the graft telemetry hooks are untouched.*

- [ ] One `PreToolUse` hook in `.claude/settings.json` (matcher `Bash|Write|Edit|MultiEdit`) runs
      `python3 "${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/ship_rails.py"`; the four existing graft
      entries (`PostToolUse` ×2, `UserPromptSubmit`, `SessionStart`, `Stop`) are byte-identical.
- [ ] Each of the six rails below has a fixture that is **refused** (exit 2, one stderr line naming
      the rail) and a **near-miss** that is **allowed** (exit 0, empty stderr).
- [ ] Every command class the ship and land prompts issue on a clean (non-deploy) task passes
      the hook unchanged — pinned as a fixture table (see Test plan, group 3). The live proof is
      the next `ship-dev-plan` launch after landing; that is Dave's (tokens), not this task's.
- [ ] `bash bin/verify.sh` green; `tests/ci-expected-skips.txt` unchanged (the suite needs only
      `python3` and `git`, both on the runner).

## The rails

Six rails, two kinds. A **protected path** is, relative to the nearest ancestor directory of the
target that contains `bin/verify.sh` (the repo marker — finds the main checkout, a
`.claude/worktrees/*` checkout and the deployed tree alike; no marker ⇒ not protected):
`tests/**` (and `tests` itself), `bin/verify.sh`, `bin/check_deploy_drift.sh`,
`.claude/hooks/ship_rails.py` (the hook guards itself — editing it out is this design's
`--no-verify`). A protected path is **existing** when `git -C <root> cat-file -e <ref>:<rel>`
exits 0, `<ref>` = first of `origin/main`, `main`, `HEAD` that `git rev-parse --verify -q`
resolves. Git failing for any other reason ⇒ treat as existing (fail closed).
"Existing" is the point of the tests rail: RAILS says *any existing test*. A test file new on
this branch — untracked, or committed here but absent on `origin/main` — stays editable, so TDD
red→green iteration on the test you are writing is not refused; a test main already has is.

| # | rail (stderr name) | refused when | near-miss that is allowed |
|---|---|---|---|
| 1 | `edit-existing-test` | `Write`/`Edit`/`MultiEdit` whose `file_path` is an existing protected path under `tests/`; or a Bash **write shape** (below) targets one | `Write` to `tests/test_new_thing.sh` that is not on `origin/main`; `Edit` of an untracked `tests/x.sh`; `bash tests/test_x.sh`; `git add tests/test_x.sh`; `bash tests/test_x.sh \| tee /tmp/out` |
| 2 | `edit-gate-script` | same shapes on `bin/verify.sh`, `bin/check_deploy_drift.sh`, `.claude/hooks/ship_rails.py` | `bash bin/verify.sh > /tmp/v.out 2>&1`; `grep FAIL /tmp/v.out`; `shellcheck bin/verify.sh`; `Edit` of `bin/deploy` |
| 3 | `no-verify` | Bash: token `--no-verify` (or `--no-verify=…`) anywhere, also inside a `bash -c`/`sh -c`/`eval` string; or `git commit` with a short flag cluster containing `n` (`-n`, `-an`) | `git commit -m "fix: verify gate"`; `git pull --no-verify-signatures`; `git push -n origin x` (push's `-n` is dry-run) |
| 4 | `git-add-all` | Bash: segment `git … add` with an arg matching `^-[A-Za-z]*A` or `--all` / `--no-ignore-removal` | `git add -p`; `git add -u`; `git add bin/x.sh tests/test_x.sh`; `git add .claude/briefs/t8-1-ship-rails-hook.md` |
| 5 | `deploy-prune` | Bash: segment whose command word is `deploy` or ends in `/deploy`, with `--prune` and **without** `--dry-run` | `bin/deploy`; `bin/deploy --dry-run --prune` (rsync `--dry-run --delete` — a preview, `bin/deploy:62-63`); `git fetch --prune`; `git remote prune origin` |
| 6 | `systemctl-lifecycle` | Bash: segment whose command word is `systemctl` (after `sudo`, env assignments, `command`, `nice`, `time`) with any arg in `start stop restart enable disable reenable try-restart reload-or-restart mask unmask kill` | `systemctl --user status buzz-agent@marcus`; `systemctl --user show buzz-agent@marcus -p ExecMainStartTimestamp --value`; `systemctl list-unit-files --state=enabled --no-legend \| wc -l`; `sudo systemctl daemon-reload`; `systemctl is-active x`; `journalctl --user -u buzz-agent@x` |

**Bash write shapes** (rails 1-2). Tokenise with `shlex.shlex(cmd, posix=True, punctuation_chars=True)`
(on `ValueError` — an apostrophe in a heredoc — fall back to `cmd.split()`), split into segments at
`; | || && & ( )`, and in each segment: command word = first token that is not `sudo`, `command`,
`nice`, `time`, `env` or a `NAME=value` assignment. A segment writes a protected existing path when:
- a redirection operator (`>`, `>>`, `&>`, `&>>`, `>|`; also a token that *starts* with `>` in the
  fallback tokeniser) is followed by it — this is what catches `cat <<EOF > tests/x.sh` and
  `echo x >> bin/verify.sh`; `2>&1` is not a redirect to a path (`>&` operator);
- command word `sed` or `perl` with an in-place flag (`--in-place*`, or `^-[A-Za-z]*i`) and it as an arg;
- command word in `tee truncate rm unlink shred mv` with it as any arg; `cp install rsync` with
  it as the **last** arg (a copy *from* a test is a read);
- command word `git` whose subcommand (first non-flag token after `git`, skipping the value of
  `-C`/`-c`/`--git-dir`/`--work-tree`) is `rm mv checkout restore clean` with it as an arg —
  `git checkout -- tests/x.sh` reverts an existing test, which is editing it; `git add`, `git diff`,
  `git mv .claude/briefs/…` are not;
- command word `bash`/`sh`/`zsh` with `-c`, or `eval`: recurse into the next token as a command.
Relative tokens resolve against the hook input's `cwd`; `~` expands; tokens starting with `-` or
containing `://` are skipped. `python3 -c`/`node -e` bodies are **not** inspected — the hook holds
the rails for an agent that has not read the prompt, not against an adversary; say so in the
helper's docstring in one sentence.

**Override — edit rails only, named and recorded.** Precedent: the vault's `pre-push` guard
(`VAULT_MAIN_PUSH="<reason>"`, logged to `.git/vault_main_pushes.log`; `~/CLAUDE.md`). When the
hook's environment carries `SHIP_RAILS_OVERRIDE=<non-empty reason>`, rails 1-2 allow the call and
append one line `<UTC ISO ts>\t<tool>\t<rail>\t<rel path>\t<reason>` to
`<git rev-parse --git-common-dir>/ship_rails_overrides.log` (the main `.git/` even from a
worktree). If that log cannot be written, refuse — an override without its record is the outcome
worse than the edit. Rails 3-6 ignore the variable: a command Dave wants run is run from a
terminal. The env var is the launching shell's (`SHIP_RAILS_OVERRIDE="fix fake in test_x" claude`);
an agent cannot set it for its own hook, which is what makes it supervision rather than a knob.

**Hook protocol** (Claude Code PreToolUse): JSON on stdin — `tool_name`, `tool_input`
(`Bash`: `command`; `Write`: `file_path`, `content`; `Edit`: `file_path`, `old_string`,
`new_string`; `MultiEdit`: `file_path`, `edits`), `cwd`, `hook_event_name`, `session_id`. Exit 0 =
allow (print nothing). Exit 2 = refuse; stderr is shown to the model. Non-JSON stdin, a missing
`tool_name`, or any other tool ⇒ exit 0. An unexpected exception ⇒ `ship-rails: internal error —
<exc>` on stderr and exit 2 (loud beats a rail that silently stopped holding; the fixture suite is
what keeps this from ever landing). `timeout` in settings.json is **seconds** — write `10`, not the
`10000`/`8000` the graft entries carry (that was graft's installer; harmless there, do not copy it).

Refusal line, one per call, shape fixed so the test can pin the rail name:
`ship-rails: refused <rail> — <target or command excerpt ≤80 chars>. Rails: .claude/workflows/ship-dev-plan.js RAILS. Edit rails lift with SHIP_RAILS_OVERRIDE="<reason>" in the launching shell (recorded in .git/ship_rails_overrides.log); command rails do not.`

## Files to modify
- `.claude/settings.json` — add `"PreToolUse": [{"matcher": "Bash|Write|Edit|MultiEdit", "hooks": [{"type": "command", "command": "python3 \"${CLAUDE_PROJECT_DIR:-.}/.claude/hooks/ship_rails.py\"", "timeout": 10}]}]` inside the existing `hooks` object. Touch nothing else in the file; the test diffs the other four event arrays against their current content.
- `.claude/workflows/ship-dev-plan.js` — **no code change.** Append one sentence to the `RAILS` string after "Always run bash bin/verify.sh …": `The first four rails and the test/gate-script rail are also enforced by the PreToolUse hook in .claude/settings.json (T8.1); a refusal names the rail — report it, do not route around it.` (`tests/test_ship_dev_plan_workflow.sh` group 1 pins task ids and red lists, not the RAILS text — confirm it stays green.)
- `docs/runbook.md` — one short subsection under the Verification/Deploy-ordering area: "Ship rails hook": what is refused, the near-misses that are not (the `--dry-run --prune` preview, `systemctl show/status`), the override and its log, and that a `t.deploy` land step's `sudo systemctl restart` now hits rail 6 and is Dave's hand. Keep it under 25 lines; the table above is the source, do not duplicate it — name the helper.

## Files to create
- `.claude/hooks/ship_rails.py` — the helper, `#!/usr/bin/env python3`, stdlib only (`json os re shlex subprocess sys datetime pathlib`). ~120-150 lines despite the card's "about 30": the tests rail has to decide *existing*, and auto mode routes edits through Bash, so a Write/Edit-only rail would be bypassed by the very sessions it is for. Functions ≤10 lines, one concept each: `read_hook_input`, `repo_root(path)`, `protected_rel(path, cwd)`, `is_existing(root, rel)`, `tokenize(cmd)`, `segments(tokens)`, `command_word(seg)`, `write_targets(seg, cwd)`, `git_subcommand(seg)`, one predicate per command rail, `override_reason()`, `record_override(root, …)`, `refuse(rail, target)`, `main`. No comments restating the rules — the table above is the spec; the docstring carries the one-sentence scope statement and the override sentence.
- `tests/test_ship_rails.py` — `unittest`, `::`-anchored cases per repo convention (`tests/test_turn_rate.py` is the shape). `setUp` builds **two** fixture repos under `tempfile.mkdtemp()` (bin/verify.sh honours `TMPDIR`): (a) `upstream` bare-ish repo with `bin/verify.sh`, `bin/check_deploy_drift.sh`, `bin/deploy`, `tests/test_existing.sh`, `tests/fixtures/data.txt`, `.claude/hooks/ship_rails.py` (a copy) committed on `main`; a `git clone` of it as the working repo, branched to `feat/x` with `tests/test_new.sh` committed and `tests/test_wip.sh` untracked — `origin/main` resolves here; (b) a `git init` repo with no remote and the same tree — proves the `HEAD` fallback. Helper `run_hook(tool, tool_input, cwd, env=None)` pipes the JSON to `python3 .claude/hooks/ship_rails.py` (the **repo's** copy under `ROOT`, not the fixture's) and returns the `CompletedProcess`. Groups:
  1. `(::rails-refused-<rail>)` ×6 and `(::rails-near-miss-<rail>)` ×6 — the table, parametrised with `subTest`; every refused case asserts `returncode == 2` and `"refused <rail>"` in stderr; every allowed case asserts `returncode == 0` and `stderr == ""`.
  2. `(::rails-existing-is-origin-main)` — `Write` to `tests/test_new.sh` (on the branch, not on origin/main) allowed; same path in repo (b) where `HEAD` is the ref and the file is committed → refused; `Edit` of untracked `tests/test_wip.sh` allowed; `Write` to `tests/test_existing.sh` refused in both.
  3. `(::rails-ship-dev-plan-pass-through)` — a table of the commands `shipPrompt` and `landPrompt` direct on a clean task, all allowed: `bash bin/verify.sh > /tmp/land-T.out 2>&1`, `grep -E '^\s*FAIL:|^PROBLEM\t|^\s*DRIFT ' /tmp/land-T.out`, `git fetch origin`, `git diff --name-only main..feat/x`, `git worktree add .claude/worktrees/land-T feat/x`, `git rebase main`, `git merge --ff-only feat/x`, `git add .claude/briefs/t8-1-ship-rails-hook.md bin/x.py tests/test_x.sh`, `git commit -m "feat: x"`, `git push origin HEAD`, `git push origin main`, `git push origin --delete feat/x`, `git mv .claude/briefs/x.md .claude/briefs/archive/2026-09-22-x.md`, `git reset --keep origin/main`, `git rev-parse --abbrev-ref HEAD`, `git diff --binary origin/main..main | sha256sum`, `sha256sum ~/.config/buzz-team/aurelian-calibration.md`, `systemctl --user show -p ExecMainStartTimestamp --value buzz-agent@marcus`, `systemctl list-unit-files --state=enabled --no-legend | wc -l`, `systemctl --user list-unit-files --state=enabled --no-legend | wc -l`, `git worktree remove .claude/worktrees/land-T`, plus `Write` of `.claude/briefs/t8-1-ship-rails-hook.md` and `Write` of a new `tests/test_x.sh`. Also one **refused** line with a comment: `sudo cp systemd/brave-mcp.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl restart brave-mcp.service` — the `t.deploy` land step, which now stops at rail 6 by design.
  4. `(::rails-bash-write-shapes)` — refused: `cat <<'EOF' > tests/test_existing.sh`, `echo x >> bin/verify.sh`, `sed -i 's/a/b/' tests/test_existing.sh`, `perl -pi -e 's/a/b/' bin/check_deploy_drift.sh`, `tee tests/test_existing.sh < /tmp/x`, `mv tests/test_existing.sh /tmp/`, `rm -rf tests`, `cp /tmp/x bin/verify.sh`, `git checkout -- tests/test_existing.sh`, `git rm tests/test_existing.sh`, `bash -c "sed -i s/a/b/ tests/test_existing.sh"`, `printf 'x' >tests/test_existing.sh` (glued redirect), a command with an apostrophe in a heredoc body that still redirects into `tests/test_existing.sh` (the fallback tokeniser). Allowed: `cp tests/fixtures/data.txt /tmp/`, `sed -n 5p tests/test_existing.sh`, `cat tests/test_existing.sh | tee /tmp/copy`, `bash tests/test_existing.sh 2>&1 | tail -5`, `mkdir -p tests/fixtures/new`, `git diff tests/`, `git checkout main`, `git clean -n`, `python3 tests/test_turn_rate.py`, `sed -i 's/a/b/' /tmp/scratch.sh`.
  5. `(::rails-override)` — with `SHIP_RAILS_OVERRIDE="fixture reason"`: `Edit` of `tests/test_existing.sh` allowed and the log under `<git-common-dir>/ship_rails_overrides.log` gains exactly one tab-separated line ending in the reason (run it from the worktree-less fixture and once from a `git worktree add` of it to prove the log lands in the main `.git/`); `--no-verify` still refused; empty `SHIP_RAILS_OVERRIDE=""` behaves as unset; log directory made unwritable (`chmod 500`, restored in cleanup, skipped when running as root) ⇒ refused with `override` in the stderr line.
  6. `(::rails-inert-input)` — non-JSON stdin, `{}`, `tool_name: "Read"`, `Bash` with no `command`, `Write` with a `file_path` outside any marker root (`/tmp/elsewhere/tests/x.sh`) ⇒ exit 0, empty stderr. An `Edit` where `git cat-file` cannot run (the marker root is not a git repo) ⇒ refused (fail closed).
  7. `(::rails-hook-wired)` — loads `ROOT/.claude/settings.json`: `hooks.PreToolUse` is exactly one entry, matcher `Bash|Write|Edit|MultiEdit`, one command hook whose `command` contains `.claude/hooks/ship_rails.py` and whose `timeout` is an int ≤ 30; and `hooks.PostToolUse`, `UserPromptSubmit`, `SessionStart`, `Stop` each still carry their `graft-hooks.cjs` command(s) with the same matchers as today (pin the four literal command strings and the two PostToolUse matchers). This is the "graft telemetry hooks untouched" half of the card gate and it is what makes removing the hook a red gate rather than a quiet loss.
- `tests/test_ship_rails.sh` — the gate entry point, the `tests/test_turn_rate.sh` shape verbatim (`set -uo pipefail`, `cd` to root, `python3 tests/test_ship_rails.py`). No box precondition.

## Test plan
- Red first: write `tests/test_ship_rails.py` + `.sh`, run `bash tests/test_ship_rails.sh` — every group fails (helper absent, hook not wired). Then the helper, then the settings entry; re-run until green.
- `bash bin/verify.sh > /tmp/t8-1-verify.out 2>&1; tail -5 /tmp/t8-1-verify.out; grep -cE '^\s*FAIL:|^PROBLEM\t|^\s*DRIFT ' /tmp/t8-1-verify.out` — exit 0, zero red lines, the skip summary equal to `tests/ci-expected-skips.txt`. shellcheck at error severity covers the new `.sh` wrapper; the helper is exercised only through the suite.
- Live check in **this** session after wiring (one call, no fixture): the running session's hook snapshot predates the edit, so the refusal will **not** fire here — do not read that as a bug; `python3 .claude/hooks/ship_rails.py <<<'{"tool_name":"Bash","tool_input":{"command":"git add -A"},"cwd":"'"$PWD"'"}'; echo $?` printing the refusal line and `2` is the hand proof.
- Not run: a `ship-dev-plan` launch (tokens; Dave's). Group 3 is its deterministic stand-in.

## Out of scope / do not touch
- The other RAILS lines (`buzz agents` / `buzz-admin generate-key`, the five secret paths) — the paths are already denied by `/etc/claude-code/managed-settings.json` (2026-09-19); key minting is not on the card.
- `git add .` / `git add -u` / `git commit -a` — not named by the card; the rail is `-A`/`--all`.
- Gaps 2-7 of the playbook analysis (main protection, rubric into the repo, brief template, measurements) — separate cards.
- Anything under `bin/` — the helper lives in `.claude/hooks/` on purpose: `bin/` is deployed and drift-checked, and a hook is not runtime.
- `tests/ci-expected-skips.txt`, `bin/verify.sh`, `bin/check_deploy_drift.sh`, `.claude/helpers/*` (graft), `.claude/settings.local.json` (untracked, Dave's).
- The workflow's control flow (`ship-dev-plan.js` beyond the one RAILS sentence) and `tests/test_ship_dev_plan_workflow.sh`.
- The Notion card's Status — set after the push if at all (`notion_update_page` over `/run/user/1000/buzz-notion.sock`); not part of the gate. The `Brief` property is already set to this file's path.

## Notes / preconditions
- Confirmed 2026-09-22: `.claude/settings.json` has no `PreToolUse`; `.claude/hooks/` does not exist; `.claude/helpers/` holds only the two graft `.cjs` files; no `.claude/commands/` override, so the generic /implement loop applies. `python3` is 3.14 on the box and present on the CI runner (`verify.yml` prints its version). `git rev-parse --git-common-dir` is `.git` in the main checkout.
- Hook snapshot: Claude Code captures hooks at process start, so the session that lands this is not governed by it and neither is the /implement session that writes it — TDD order (tests first, helper, then the settings entry) needs no override. The first governed session is the next one launched in this repo, Dave's interactive ones included; that is the feature.
- Consequence to state, not soften: after landing, extending an **existing** suite from Claude Code needs `SHIP_RAILS_OVERRIDE` in the launching shell; a new suite file per feature (the repo's co-location rule anyway) does not. `tests/ci-expected-skips.txt` and `tests/fixtures/*` count as existing tests. The `/fewer-permission-prompts` skill writes `.claude/settings.json`, which is deliberately **not** a protected path — group 7 pins the wiring instead, so a removed hook is a red gate, not a refused edit.
- The `.claude/worktrees/*` checkouts carry the committed settings.json, but a Workflow/Agent subagent shares the parent process's hook snapshot; the helper's marker-walk (nearest ancestor with `bin/verify.sh`) is what makes the same helper judge a worktree path correctly whichever checkout's copy runs.
- Auto mode ("make file changes with sed, heredocs … rather than Edit/Write") is why the Bash write shapes exist; without them the rail covers the tool an agent in auto mode never uses.
- Do not `git add -A` while implementing this (the hook is not yet live for you, the rail is). Stage by name; commit the named brief with the code.
