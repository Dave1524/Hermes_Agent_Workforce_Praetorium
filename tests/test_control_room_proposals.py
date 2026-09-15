#!/usr/bin/env python3
"""T5.3b — schedule changes and retirements as reviewed PRs: the worker, the records, the
HTTP seam. Also the common harness the other T5.3b suites import (make_remote, make_worker,
FakeRunner, snapshot_repo). Every git and gh call in every test goes to a temp bare remote
built from tests/fixtures/control-proposals/repo; `origin` is never named.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "control-proposals"
NOW = dt.datetime(2026, 9, 14, 8, 0, tzinfo=dt.timezone.utc)
GUARDED_SOURCES = ("bin/control_room_proposals.py", "bin/workflow_pr.py", "bin/workflow_pr_git.py",
                   "bin/workflow_pr_schedule.py", "bin/workflow_pr_retire.py", "bin/workflow_pr_checks.py",
                   "bin/workflow_pr_body.py", "bin/workflow_pr_record.py", "bin/workflow_retire_residue.py")

sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "tests"))
import control_room_api as api  # noqa: E402
import workflow_pr_git as prgit  # noqa: E402
import workflow_pr_record as record  # noqa: E402
from control_room_fixture import FakeSystemd  # noqa: E402

os.environ["PATH"] = f"{FIXTURES / 'bin'}:{os.environ.get('PATH', '')}"
os.environ["FAKE_CALENDAR"] = str(FIXTURES / "calendar.json")
os.environ.pop("FAKE_GH_FAIL", None)


def _git(cwd: pathlib.Path, *args: str) -> str:
    return subprocess.run(["git", "-c", "user.name=fixture", "-c", "user.email=fixture@example.invalid",
                           "-c", "commit.gpgsign=false", *args], cwd=cwd, check=True, text=True,
                          capture_output=True, env={**os.environ, "GIT_CONFIG_NOSYSTEM": "1"}).stdout.strip()


def make_remote(tmp: pathlib.Path, src: pathlib.Path = FIXTURES / "repo", variant: str | None = None) -> tuple[pathlib.Path, str]:
    """git init a copy of the mini-repo, commit, clone it bare: (remote_bare, seed_sha)."""
    seed = tmp / "seed"
    shutil.copytree(src, seed)
    if variant:
        shutil.copy(FIXTURES / "variants" / variant, seed / "tests" / variant)
    _git(seed, "init", "-q", "-b", "main", ".")
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", "fixture seed")
    sha = _git(seed, "rev-parse", "HEAD")
    remote = tmp / "remote.git"
    _git(tmp, "clone", "-q", "--bare", str(seed), str(remote))
    return remote, sha


def commit_on_main(tmp: pathlib.Path, relative: str, text: str, message: str = "upstream change") -> str:
    """A later commit on the remote's main, made through the seed checkout."""
    seed = tmp / "seed"
    path = seed / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    _git(seed, "add", "-A")
    _git(seed, "commit", "-q", "-m", message)
    _git(seed, "push", "-q", str(tmp / "remote.git"), "main:main")
    return _git(seed, "rev-parse", "HEAD")


def remote_heads(remote: pathlib.Path) -> list[str]:
    out = _git(remote, "for-each-ref", "--format=%(refname:short)", "refs/heads/")
    return sorted(out.splitlines())


def remote_diff(remote: pathlib.Path, branch: str) -> str:
    return subprocess.run(["git", "--no-pager", "diff", "--no-color", "--binary", "-M", f"main..{branch}"],
                          cwd=remote, check=True, text=True, capture_output=True).stdout


def tree_digest(root: pathlib.Path) -> dict[str, str]:
    digest = {}
    for path in sorted(root.rglob("*")):
        if path.is_file() and ".git" not in path.parts:
            digest[str(path.relative_to(root))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return digest


def make_item(worktree: pathlib.Path, workflow_id: str, control_state: str = "paused") -> dict:
    """The read model's workflow dict over a checkout, with the live control state pinned."""
    root = worktree.resolve()
    model = api.ControlRoomReadModel(paths=api.SourcePaths(repo=root, runtime=root, receipts=root / "var" / "receipts"),
                                     systemd=FakeSystemd(), clock=lambda: NOW, calendar_runner=lambda spec: [])
    item, status = model.workflow_detail(workflow_id)
    if item is None:
        raise AssertionError(f"{workflow_id} not in {root}: {status}")
    item["control"]["state"] = control_state
    return item


def checkout(tmp: pathlib.Path, name: str = "wt") -> pathlib.Path:
    """A plain working copy of the remote's main for the pure planners."""
    path = tmp / name
    _git(tmp, "clone", "-q", str(tmp / "remote.git"), str(path))
    return path


class FakeRunner:
    """Stands in for the check bundle's subprocess: records argv, answers from a table."""

    def __init__(self, failures: dict[str, tuple[int, str]] | None = None) -> None:
        self.calls: list[list[str]] = []
        self.failures = failures or {}

    def __call__(self, argv: list[str], cwd, env, timeout) -> tuple[int, str, str]:
        self.calls.append(list(argv))
        key = argv[-1] if argv else ""
        for needle, (code, output) in self.failures.items():
            if needle in " ".join(argv):
                return code, output, ""
        return 0, f"  ok: {key}\n", ""


class TempState(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="crp-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.remote, self.seed_sha = make_remote(self.tmp)
        self.state = self.tmp / "state"


class RecordSchema(TempState):
    """(::proposal-every-outcome-recorded) — the record half; the worker half lives in Outcomes."""

    def _record(self, **over):
        base = record.new_record(kind="schedule", workflow_id="alpha", actor={"kind": "cli", "label": "t"},
                                 reason="r", now=NOW)
        base.update(over)
        return base

    def test_proposal_id_shape(self):
        pid = record.proposal_id(NOW, "schedule", "alpha")
        self.assertRegex(pid, r"^20260914T080000Z-schedule-alpha-[0-9a-f]{6}$")

    def test_new_record_validates_and_round_trips(self):
        rec = self._record(stage="previewed", completed_at=record.stamp(NOW))
        self.assertEqual(record.validate_record(rec), [])
        path = record.write(self.state, rec)
        self.assertEqual(oct(path.stat().st_mode & 0o777), "0o644")
        self.assertEqual(record.load(path), rec)
        self.assertEqual(list(self.state.glob("**/*.tmp")), [])

    def test_validate_names_every_defect(self):
        rec = self._record(stage="done", commands="x", diff_sha256=5)
        del rec["actor"]
        problems = record.validate_record(rec)
        self.assertTrue(any("stage" in p for p in problems), problems)
        self.assertTrue(any("commands" in p for p in problems), problems)
        self.assertTrue(any("actor" in p for p in problems), problems)
        self.assertTrue(any("diff_sha256" in p for p in problems), problems)

    def test_newest_and_list_order_and_token(self):
        older = self._record(stage="previewed", proposal_id="20260914T070000Z-schedule-alpha-aaaaaa",
                             requested_at=record.stamp(NOW - dt.timedelta(hours=1)),
                             completed_at=record.stamp(NOW - dt.timedelta(hours=1)), diff="old")
        newer = self._record(stage="refused", proposal_id="20260914T080000Z-schedule-alpha-bbbbbb",
                             completed_at=record.stamp(NOW), diff="new", refusal={"code": "bad_request", "message": "x"})
        other = self._record(stage="previewed", workflow_id="beta", proposal_id="20260914T090000Z-schedule-beta-cccccc",
                             completed_at=record.stamp(NOW))
        for rec in (older, newer, other):
            record.write(self.state, rec)
        self.assertEqual(record.newest(self.state, "alpha", "schedule")["proposal_id"], newer["proposal_id"])
        listed = record.list_records(self.state, "alpha", "schedule")
        self.assertEqual([r["proposal_id"] for r in listed], [newer["proposal_id"], older["proposal_id"]])
        self.assertTrue(all("diff" not in r for r in listed))
        self.assertEqual(record.find(self.state, older["proposal_id"])["diff"], "old")
        self.assertEqual(record.token_valid(older, NOW), (False, "preview expired"))
        self.assertEqual(record.token_valid(older, NOW - dt.timedelta(minutes=45)), (True, None))
        self.assertEqual(record.token_valid(newer, NOW), (False, "record is refused, not previewed"))


class GitGuard(TempState):
    """(::proposal-never-touches-main-or-runtime) — the guard half; the tree half lives in Outcomes."""

    def _repo(self) -> prgit.GitRepo:
        repo = prgit.GitRepo(self.state, str(self.remote), "Fixture Author <fixture@example.invalid>")
        repo.init()
        return repo

    def test_branch_re(self):
        good = "control-room/schedule-alpha-20260914T080000Z"
        self.assertTrue(prgit.BRANCH_RE.match(good))
        for bad in ("main", "refs/heads/main", "control-room/../x", good + " ", "control-room/schedule-Alpha-20260914T080000Z",
                    "control-room/merge-alpha-20260914T080000Z", "control-room/schedule--20260914T080000Z"):
            self.assertIsNone(prgit.BRANCH_RE.match(bad), bad)

    def test_push_guarded_refuses_everything_but_a_proposal_branch(self):
        repo = self._repo()
        for bad in ("main", "refs/heads/main", "control-room/../x", "control-room/schedule-x-20260914T080000Z "):
            with self.assertRaises(prgit.GitFailed):
                repo.push_guarded(bad, cwd=self.state)
        self.assertEqual([c for c in repo.commands if "push" in c["argv"]], [])
        self.assertEqual(remote_heads(self.remote), ["main"])

    def test_init_writes_gitconfig_and_refuses_another_remote(self):
        repo = self._repo()
        config = (self.state / "gitconfig").read_text()
        for line in ("[user]", "name = Fixture Author", "email = fixture@example.invalid",
                     '[credential "https://github.com"]', "helper = !/usr/bin/gh auth git-credential",
                     "[push]", "default = nothing", "[advice]", "detachedHead = false", "[core]", "hooksPath = /dev/null"):
            self.assertIn(line, config)
        self.assertTrue((self.state / "repo.git" / "HEAD").exists())
        other = prgit.GitRepo(self.state, str(self.tmp / "elsewhere.git"), "x <x@x>")
        with self.assertRaises(prgit.GitFailed):
            other.init()

    def test_worktree_diff_commit_push_round_trip(self):
        repo = self._repo()
        repo.fetch_main()
        self.assertEqual(repo.base_sha(), self.seed_sha)
        path = repo.worktree_add("pid1")
        timer = path / "systemd" / "alpha.timer"
        timer.write_text(timer.read_text().replace("OnCalendar=Sun 09:00", "OnCalendar=Sun 07:00"))
        (path / "profiles" / "alpha_task.md").unlink()
        (path / "docs" / "new.md").write_text("new\n")
        subprocess.run(["git", "mv", "design/contracts/beta.md", "design/contracts/beta-renamed.md"], cwd=path, check=True)
        text, stat, files = repo.diff(path)
        self.assertIn("-OnCalendar=Sun 09:00\n+OnCalendar=Sun 07:00", text)
        changes = {f["path"]: f["change"] for f in files}
        self.assertEqual(changes["systemd/alpha.timer"], "modified")
        self.assertEqual(changes["profiles/alpha_task.md"], "deleted")
        self.assertEqual(changes["docs/new.md"], "added")
        self.assertEqual(changes["design/contracts/beta-renamed.md"], "renamed")
        self.assertEqual([f["from"] for f in files if f["change"] == "renamed"], ["design/contracts/beta.md"])
        self.assertIn("4 files changed", stat)
        branch = "control-room/schedule-alpha-20260914T080000Z"
        repo.commit(path, branch, "control-room(schedule): alpha — test\n\nbody\n")
        repo.push_guarded(branch, cwd=path)
        self.assertEqual(remote_heads(self.remote), [branch, "main"])
        self.assertEqual(remote_diff(self.remote, branch), text)
        self.assertEqual(repo.remote_heads("control-room/"), [branch])
        pushes = [c["argv"] for c in repo.commands if c["argv"][:2] == ["git", "push"]]
        self.assertEqual(pushes, [["git", "push", "origin", f"HEAD:refs/heads/{branch}"]])
        self.assertTrue(all(c["exit"] == 0 and "seconds" in c and "stderr" in c for c in repo.commands))
        self.assertTrue(all(str(self.remote) in c["argv"] or "origin" in c["argv"] or "push" not in c["argv"]
                            for c in repo.commands))
        repo.cleanup("pid1", branch)
        self.assertFalse(path.exists())
        self.assertNotIn(branch, subprocess.run(["git", "branch", "--list"], cwd=self.state / "repo.git",
                                                capture_output=True, text=True).stdout)

    def test_sources_carry_no_forbidden_argv(self):
        forbidden = [r"""["']pr["'],\s*["']merge["']""", r"""["']--force["']""", r"""["']push["'],\s*["']\+""",
                     r"""["']systemctl["'].*["'](enable|disable|start|stop|restart|mask|unmask|daemon-reload)["']""",
                     r"""["']--no-verify["']"""]
        for relative in GUARDED_SOURCES:
            path = ROOT / relative
            if not path.exists():
                continue
            text = path.read_text()
            for pattern in forbidden:
                for match in re.finditer(pattern, text):
                    line = text[:match.start()].count("\n") + 1
                    context = text.splitlines()[line - 1]
                    if context.lstrip().startswith("#") or '"""' in context or context.lstrip().startswith(('"', "'")) and "(" not in context:
                        continue
                    self.fail(f"{relative}:{line} carries forbidden argv {pattern!r}: {context.strip()}")
            for match in re.finditer(r"deploy[\"' ]", text):
                line = text[:match.start()].count("\n") + 1
                context = text.splitlines()[line - 1]
                if "argv" in context or "[" in context and "bin/deploy" in context:
                    self.assertIn("--dry-run", context, f"{relative}:{line} runs deploy without --dry-run")
            if relative != "bin/workflow_pr.py":
                self.assertNotIn("~/dev/agent-workforce", text.replace("`~/dev/agent-workforce`", ""),
                                 f"{relative} names the live checkout")


if __name__ == "__main__":
    unittest.main()
