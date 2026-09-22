#!/usr/bin/env python3
""".claude/hooks/ship_rails.py: the PreToolUse hook that turns the ship RAILS into blocks.

Two fixture repos: a clone with origin/main (the ship-dev-plan shape) and a bare git init
with no remote (the HEAD fallback). The hook under test is always the repo's own copy.
Anchors are the `::` comments; tests/test_ship_rails.sh is the gate entry point.
"""
from __future__ import annotations

import json
import os
import pathlib
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
HOOK = ROOT / ".claude" / "hooks" / "ship_rails.py"
SETTINGS = ROOT / ".claude" / "settings.json"
GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
TREE = {"bin/verify.sh": "#!/usr/bin/env bash\n", "bin/check_deploy_drift.sh": "#!/usr/bin/env bash\n",
        "bin/deploy": "#!/usr/bin/env bash\n", "tests/test_existing.sh": "#!/usr/bin/env bash\n",
        "tests/fixtures/data.txt": "data\n", ".claude/hooks/ship_rails.py": "#!/usr/bin/env python3\n"}
GRAFT = 'node "${CLAUDE_PROJECT_DIR:-.}/.claude/helpers/graft-hooks.cjs" '

REFUSED = {
    "edit-existing-test": [
        ("Write", {"file_path": "tests/test_existing.sh", "content": "x"}),
        ("Edit", {"file_path": "tests/test_existing.sh", "old_string": "a", "new_string": "b"}),
        ("MultiEdit", {"file_path": "tests/fixtures/data.txt", "edits": []}),
        "sed -i 's/a/b/' tests/test_existing.sh",
        "echo x > tests/test_existing.sh",
    ],
    "edit-gate-script": [
        ("Write", {"file_path": "bin/verify.sh", "content": "x"}),
        ("Edit", {"file_path": "bin/check_deploy_drift.sh", "old_string": "a", "new_string": "b"}),
        ("Edit", {"file_path": ".claude/hooks/ship_rails.py", "old_string": "a", "new_string": "b"}),
        "echo x >> bin/verify.sh",
        "perl -pi -e 's/a/b/' bin/check_deploy_drift.sh",
    ],
    "no-verify": [
        "git commit --no-verify -m x",
        "git commit -m x --no-verify=true",
        "git commit -n -m x",
        "git commit -anm x",
        "git push --no-verify origin HEAD",
        'bash -c "git commit -m x --no-verify"',
        'eval "git commit -m x --no-verify"',
    ],
    "git-add-all": [
        "git add -A",
        "git add --all",
        "git add -A .",
        "git add -fA",
        "git add --no-ignore-removal",
        "git -C /tmp/elsewhere add -A",
        "cd /tmp && git add -A",
    ],
    "deploy-prune": [
        "bin/deploy --prune",
        "./bin/deploy --prune",
        "~/dev/agent-workforce/bin/deploy --prune",
        "deploy --prune",
        "bash bin/verify.sh > /tmp/v.out 2>&1 && bin/deploy --prune",
    ],
    "systemctl-lifecycle": [
        "systemctl --user restart buzz-agent@marcus",
        "sudo systemctl restart brave-mcp.service",
        "systemctl --user enable --now x.timer",
        "systemctl --user start buzz-agent@marcus",
        "systemctl stop x",
        "systemctl disable x",
        "sudo systemctl daemon-reload && sudo systemctl restart x",
        "SYSTEMD_PAGER= systemctl --user restart x",
        "command systemctl kill x",
        "systemctl mask x",
        "systemctl --user try-restart x",
        "systemctl --user reload-or-restart x",
    ],
}

ALLOWED = {
    "edit-existing-test": [
        ("Write", {"file_path": "tests/test_new.sh", "content": "x"}),
        ("Edit", {"file_path": "tests/test_wip.sh", "old_string": "a", "new_string": "b"}),
        "bash tests/test_existing.sh",
        "git add tests/test_existing.sh",
        "bash tests/test_existing.sh | tee /tmp/out",
    ],
    "edit-gate-script": [
        "bash bin/verify.sh > /tmp/v.out 2>&1",
        "grep FAIL /tmp/v.out",
        "shellcheck bin/verify.sh",
        ("Edit", {"file_path": "bin/deploy", "old_string": "a", "new_string": "b"}),
    ],
    "no-verify": [
        'git commit -m "fix: verify gate"',
        "git pull --no-verify-signatures",
        "git push -n origin x",
    ],
    "git-add-all": [
        "git add -p",
        "git add -u",
        "git add bin/x.sh tests/test_x.sh",
        "git add .claude/briefs/t8-1-ship-rails-hook.md",
    ],
    "deploy-prune": [
        "bin/deploy",
        "bin/deploy --dry-run --prune",
        "bin/deploy --prune --dry-run",
        "git fetch --prune",
        "git remote prune origin",
    ],
    "systemctl-lifecycle": [
        "systemctl --user status buzz-agent@marcus",
        "systemctl --user show buzz-agent@marcus -p ExecMainStartTimestamp --value",
        "systemctl list-unit-files --state=enabled --no-legend | wc -l",
        "sudo systemctl daemon-reload",
        "systemctl is-active x",
        "journalctl --user -u buzz-agent@x",
    ],
}

SHIP_DEV_PLAN_COMMANDS = [
    "bash bin/verify.sh > /tmp/land-T.out 2>&1",
    r"grep -E '^\s*FAIL:|^PROBLEM\t|^\s*DRIFT ' /tmp/land-T.out",
    "git fetch origin",
    "git diff --name-only main..feat/x",
    "git worktree add .claude/worktrees/land-T feat/x",
    "git rebase main",
    "git merge --ff-only feat/x",
    "git add .claude/briefs/t8-1-ship-rails-hook.md bin/x.py tests/test_x.sh",
    'git commit -m "feat: x"',
    "git push origin HEAD",
    "git push origin main",
    "git push origin --delete feat/x",
    "git mv .claude/briefs/x.md .claude/briefs/archive/2026-09-22-x.md",
    "git reset --keep origin/main",
    "git rev-parse --abbrev-ref HEAD",
    "git diff --binary origin/main..main | sha256sum",
    "sha256sum ~/.config/buzz-team/aurelian-calibration.md",
    "systemctl --user show -p ExecMainStartTimestamp --value buzz-agent@marcus",
    "systemctl list-unit-files --state=enabled --no-legend | wc -l",
    "systemctl --user list-unit-files --state=enabled --no-legend | wc -l",
    "git worktree remove .claude/worktrees/land-T",
    ("Write", {"file_path": ".claude/briefs/t8-1-ship-rails-hook.md", "content": "# brief"}),
    ("Write", {"file_path": "tests/test_x.sh", "content": "#!/usr/bin/env bash\n"}),
]

WRITE_SHAPES_REFUSED = {
    "edit-existing-test": [
        "cat <<'EOF' > tests/test_existing.sh\nline\nEOF",
        "sed -i 's/a/b/' tests/test_existing.sh",
        "tee tests/test_existing.sh < /tmp/x",
        "mv tests/test_existing.sh /tmp/",
        "rm -rf tests",
        "git checkout -- tests/test_existing.sh",
        "git rm tests/test_existing.sh",
        'bash -c "sed -i s/a/b/ tests/test_existing.sh"',
        "printf 'x' >tests/test_existing.sh",
        "cat <<EOF > tests/test_existing.sh\nit's broken\nEOF",
    ],
    "edit-gate-script": [
        "echo x >> bin/verify.sh",
        "perl -pi -e 's/a/b/' bin/check_deploy_drift.sh",
        "cp /tmp/x bin/verify.sh",
    ],
}

WRITE_SHAPES_ALLOWED = [
    "cp tests/fixtures/data.txt /tmp/",
    "sed -n 5p tests/test_existing.sh",
    "cat tests/test_existing.sh | tee /tmp/copy",
    "bash tests/test_existing.sh 2>&1 | tail -5",
    "mkdir -p tests/fixtures/new",
    "git diff tests/",
    "git checkout main",
    "git clean -n",
    "python3 tests/test_turn_rate.py",
    "sed -i 's/a/b/' /tmp/scratch.sh",
]


def git(cwd: pathlib.Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True,
                   env={**os.environ, **GIT_ENV})


def write_tree(root: pathlib.Path, extra: dict[str, str] | None = None) -> None:
    for rel, body in {**TREE, **(extra or {})}.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)


class ShipRailsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="ship-rails-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.work = self._clone_fixture()
        self.local = self._local_fixture()

    def _clone_fixture(self) -> pathlib.Path:
        upstream = self.tmp / "upstream"
        upstream.mkdir()
        git(upstream, "init", "-q", "-b", "main")
        write_tree(upstream)
        git(upstream, "add", "bin", "tests", ".claude")
        git(upstream, "commit", "-q", "-m", "main tree")
        work = self.tmp / "work"
        git(self.tmp, "clone", "-q", str(upstream), str(work))
        git(work, "checkout", "-q", "-b", "feat/x")
        (work / "tests" / "test_new.sh").write_text("#!/usr/bin/env bash\n")
        git(work, "add", "tests/test_new.sh")
        git(work, "commit", "-q", "-m", "test: new suite on the branch")
        (work / "tests" / "test_wip.sh").write_text("#!/usr/bin/env bash\n")
        return work

    def _local_fixture(self) -> pathlib.Path:
        local = self.tmp / "local"
        local.mkdir()
        git(local, "init", "-q", "-b", "main")
        write_tree(local, {"tests/test_new.sh": "#!/usr/bin/env bash\n"})
        git(local, "add", "bin", "tests", ".claude")
        git(local, "commit", "-q", "-m", "main tree")
        (local / "tests" / "test_wip.sh").write_text("#!/usr/bin/env bash\n")
        return local

    def run_raw(self, stdin: str, cwd: pathlib.Path, env: dict | None = None) -> subprocess.CompletedProcess:
        base = {k: v for k, v in os.environ.items() if k != "SHIP_RAILS_OVERRIDE"}
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, cwd=str(cwd), capture_output=True,
                              text=True, env={**base, **GIT_ENV, **(env or {})})

    def run_hook(self, tool: str, tool_input: dict, cwd: pathlib.Path, env: dict | None = None):
        payload = {"tool_name": tool, "tool_input": tool_input, "cwd": str(cwd),
                   "hook_event_name": "PreToolUse", "session_id": "fixture"}
        return self.run_raw(json.dumps(payload), cwd, env)

    def run_case(self, case, cwd: pathlib.Path, env: dict | None = None):
        if isinstance(case, str):
            return self.run_hook("Bash", {"command": case}, cwd, env)
        tool, tool_input = case
        return self.run_hook(tool, tool_input, cwd, env)

    def assert_refused(self, rail: str, cases, cwd: pathlib.Path, env: dict | None = None) -> None:
        for case in cases:
            with self.subTest(rail=rail, case=case):
                done = self.run_case(case, cwd, env)
                self.assertEqual(done.returncode, 2, done.stderr or done.stdout)
                self.assertIn(f"refused {rail}", done.stderr)
                self.assertEqual(done.stderr.count("\n"), 1, done.stderr)

    def assert_allowed(self, rail: str, cases, cwd: pathlib.Path, env: dict | None = None) -> None:
        for case in cases:
            with self.subTest(rail=rail, case=case):
                done = self.run_case(case, cwd, env)
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertEqual(done.stderr, "")

    def test_rail_edit_existing_test(self):
        # (::rails-refused-edit-existing-test) an existing test, by tool or by Bash write shape.
        self.assert_refused("edit-existing-test", REFUSED["edit-existing-test"], self.work)
        # (::rails-near-miss-edit-existing-test) new on the branch, untracked, run, staged, piped.
        self.assert_allowed("edit-existing-test", ALLOWED["edit-existing-test"], self.work)

    def test_rail_edit_gate_script(self):
        # (::rails-refused-edit-gate-script) verify.sh, the drift check and the hook itself.
        self.assert_refused("edit-gate-script", REFUSED["edit-gate-script"], self.work)
        # (::rails-near-miss-edit-gate-script) running, reading and linting the gate is not editing it.
        self.assert_allowed("edit-gate-script", ALLOWED["edit-gate-script"], self.work)

    def test_rail_no_verify(self):
        # (::rails-refused-no-verify) the token anywhere, nested strings, and commit's -n cluster.
        self.assert_refused("no-verify", REFUSED["no-verify"], self.work)
        # (::rails-near-miss-no-verify) a message that says verify, --no-verify-signatures, push -n.
        self.assert_allowed("no-verify", ALLOWED["no-verify"], self.work)

    def test_rail_git_add_all(self):
        # (::rails-refused-git-add-all) -A in any cluster, --all, --no-ignore-removal, after -C or cd.
        self.assert_refused("git-add-all", REFUSED["git-add-all"], self.work)
        # (::rails-near-miss-git-add-all) -p, -u and staging by name.
        self.assert_allowed("git-add-all", ALLOWED["git-add-all"], self.work)

    def test_rail_deploy_prune(self):
        # (::rails-refused-deploy-prune) --prune without --dry-run, whatever path names deploy.
        self.assert_refused("deploy-prune", REFUSED["deploy-prune"], self.work)
        # (::rails-near-miss-deploy-prune) the additive deploy, the preview, git's own prune.
        self.assert_allowed("deploy-prune", ALLOWED["deploy-prune"], self.work)

    def test_rail_systemctl_lifecycle(self):
        # (::rails-refused-systemctl-lifecycle) every lifecycle verb, after sudo, env or command.
        self.assert_refused("systemctl-lifecycle", REFUSED["systemctl-lifecycle"], self.work)
        # (::rails-near-miss-systemctl-lifecycle) status, show, list, is-active, daemon-reload, journal.
        self.assert_allowed("systemctl-lifecycle", ALLOWED["systemctl-lifecycle"], self.work)

    def test_existing_means_on_origin_main(self):
        # (::rails-existing-is-origin-main) a test the branch added is editable; the same path
        # committed where HEAD is the only ref is not; untracked stays free; main's test is
        # refused in both.
        new = ("Write", {"file_path": "tests/test_new.sh", "content": "x"})
        wip = ("Edit", {"file_path": "tests/test_wip.sh", "old_string": "a", "new_string": "b"})
        old = ("Write", {"file_path": "tests/test_existing.sh", "content": "x"})
        self.assert_allowed("edit-existing-test", [new, wip], self.work)
        self.assert_refused("edit-existing-test", [new, old], self.local)
        self.assert_allowed("edit-existing-test", [wip], self.local)
        self.assert_refused("edit-existing-test", [old], self.work)

    def test_ship_dev_plan_commands_pass_through(self):
        # (::rails-ship-dev-plan-pass-through) every command class the ship and land prompts
        # issue on a clean task is allowed; the t.deploy land step's restart stops at rail 6.
        self.assert_allowed("ship-dev-plan", SHIP_DEV_PLAN_COMMANDS, self.work)
        deploy_land = ("sudo cp systemd/brave-mcp.service /etc/systemd/system/ && sudo systemctl daemon-reload"
                       " && sudo systemctl restart brave-mcp.service")
        self.assert_refused("systemctl-lifecycle", [deploy_land], self.work)

    def test_bash_write_shapes(self):
        # (::rails-bash-write-shapes) redirects (glued too), in-place sed/perl, tee/mv/rm/cp,
        # git checkout/rm, bash -c, and the fallback tokeniser on an unbalanced quote; reads,
        # copies from, pipes out of and paths elsewhere are not writes.
        for rail, cases in WRITE_SHAPES_REFUSED.items():
            self.assert_refused(rail, cases, self.work)
        self.assert_allowed("write-shapes", WRITE_SHAPES_ALLOWED, self.work)

    def test_override_lifts_edit_rails_and_records(self):
        # (::rails-override) a named override lifts the edit rails and lands one line in the
        # main .git, from the checkout and from a worktree of it; command rails ignore it; an
        # empty reason is unset; a log that cannot be written refuses.
        env = {"SHIP_RAILS_OVERRIDE": "fixture reason"}
        edit = ("Edit", {"file_path": "tests/test_existing.sh", "old_string": "a", "new_string": "b"})
        log = self.work / ".git" / "ship_rails_overrides.log"
        self.assert_allowed("override", [edit], self.work, env)
        lines = log.read_text().splitlines()
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0].split("\t")[1:], ["Edit", "edit-existing-test", "tests/test_existing.sh", "fixture reason"])
        worktree = self.tmp / "wt"
        git(self.work, "worktree", "add", "-q", str(worktree), "-b", "wt")
        self.assert_allowed("override", [edit], worktree, env)
        self.assertEqual(len(log.read_text().splitlines()), 2)
        self.assertFalse((worktree / ".git" / "ship_rails_overrides.log").exists())
        self.assert_refused("no-verify", ["git commit --no-verify -m x"], self.work, env)
        self.assert_refused("edit-existing-test", [edit], self.work, {"SHIP_RAILS_OVERRIDE": ""})
        self._assert_unwritable_log_refuses(edit, env)

    def _assert_unwritable_log_refuses(self, edit, env) -> None:
        if os.geteuid() == 0:
            self.skipTest("root ignores directory modes")
        git_dir = self.local / ".git"
        mode = stat.S_IMODE(git_dir.stat().st_mode)
        self.addCleanup(git_dir.chmod, mode)
        git_dir.chmod(0o500)
        done = self.run_case(edit, self.local, env)
        self.assertEqual(done.returncode, 2, done.stderr)
        self.assertIn("refused edit-existing-test", done.stderr)
        self.assertIn("override", done.stderr)

    def test_inert_input(self):
        # (::rails-inert-input) non-JSON, empty, other tools, a Bash with no command and a path
        # under no marker root all pass silently; a marker root that is not a git repo fails closed.
        for stdin in ["not json", "{}", json.dumps({"tool_name": "Read", "tool_input": {"file_path": "tests/test_existing.sh"}, "cwd": str(self.work)}),
                      json.dumps({"tool_name": "Bash", "tool_input": {}, "cwd": str(self.work)})]:
            with self.subTest(stdin=stdin):
                done = self.run_raw(stdin, self.work)
                self.assertEqual((done.returncode, done.stderr), (0, ""))
        elsewhere = self.tmp / "elsewhere"
        (elsewhere / "tests").mkdir(parents=True)
        self.assert_allowed("no-marker", [("Write", {"file_path": str(elsewhere / "tests" / "x.sh"), "content": "x"})], elsewhere)
        nogit = self.tmp / "nogit"
        write_tree(nogit)
        edit = ("Edit", {"file_path": "tests/test_existing.sh", "old_string": "a", "new_string": "b"})
        self.assert_refused("edit-existing-test", [edit], nogit)

    def test_hook_wired_and_graft_untouched(self):
        # (::rails-hook-wired) one PreToolUse entry runs the helper; the four graft telemetry
        # events carry the same commands and matchers as before T8.1.
        hooks = json.loads(SETTINGS.read_text())["hooks"]
        pre = hooks["PreToolUse"]
        self.assertEqual(len(pre), 1)
        self.assertEqual(pre[0]["matcher"], "Bash|Write|Edit|MultiEdit")
        self.assertEqual(len(pre[0]["hooks"]), 1)
        command = pre[0]["hooks"][0]
        self.assertEqual(command["type"], "command")
        self.assertIn(".claude/hooks/ship_rails.py", command["command"])
        self.assertIsInstance(command["timeout"], int)
        self.assertLessEqual(command["timeout"], 30)
        post = hooks["PostToolUse"]
        self.assertEqual([entry["matcher"] for entry in post], ["Write|Edit|MultiEdit", "Bash|mcp__graft__|Read|Grep|Glob"])
        self.assertEqual([entry["hooks"][0]["command"] for entry in post], [GRAFT + "post-edit", GRAFT + "tool-savings"])
        for event, verb in [("UserPromptSubmit", "prompt"), ("SessionStart", "session-start"), ("Stop", "stop")]:
            self.assertEqual([entry["hooks"][0]["command"] for entry in hooks[event]], [GRAFT + verb])
            self.assertNotIn("matcher", hooks[event][0])


if __name__ == "__main__":
    unittest.main()
