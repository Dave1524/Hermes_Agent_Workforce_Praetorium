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
import threading
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "control-proposals"
NOW = dt.datetime(2026, 9, 14, 8, 0, tzinfo=dt.timezone.utc)
GUARDED_SOURCES = ("bin/control_room_proposals.py", "bin/workflow_pr.py", "bin/workflow_pr_git.py",
                   "bin/workflow_pr_schedule.py", "bin/workflow_pr_retire.py", "bin/workflow_pr_checks.py",
                   "bin/workflow_pr_body.py", "bin/workflow_pr_record.py", "bin/workflow_retire_residue.py")

sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "tests"))
import control_room_api as api  # noqa: E402
import control_room_proposals as proposals_module  # noqa: E402
import workflow_pr as worker_module  # noqa: E402
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


def make_worker(tmp: pathlib.Path, remote: pathlib.Path, now: dt.datetime = NOW, runner=None, live=None) -> worker_module.Worker:
    """A Worker over a temp state root, the fixture shims on PATH, suite runs faked."""
    state = tmp / "state"
    os.environ["FAKE_GH_LOG"] = str(tmp / "gh.log")
    os.environ["FAKE_SYSTEMCTL_LOG"] = str(tmp / "systemctl.log")
    os.environ.pop("FAKE_GH_PR_LIST", None)
    os.environ.pop("FAKE_GH_FAIL", None)
    clock = {"now": now}
    live = live or {"runtime_root": str(FIXTURES / "runtime"), "etc_dir": str(FIXTURES / "etc"), "user_tree": str(FIXTURES / "user")}
    worker = worker_module.Worker(state, str(remote), "fixture/repo", "Fixture Author <fixture@example.invalid>",
                                  clock=lambda: clock["now"], runner=runner or FakeRunner(),
                                  tz_reader=lambda: {"name": "Europe/Amsterdam", "source": "timedatectl"}, live=live)
    worker.set_now = lambda value: clock.__setitem__("now", value)
    worker.init()
    return worker


def gh_log(tmp: pathlib.Path) -> list[dict]:
    path = tmp / "gh.log"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def schedule_request(workflow_id="alpha", specs=("Sun 07:00",), stage="preview", token=None, **proposed) -> dict:
    proposed = {"on_calendar": list(specs), "randomized_delay_sec": None, "persistent": None, "trigger": None,
                "manifest_trigger": None, "contract_trigger": None, "acknowledge_pinned_tests": False, **proposed}
    return {"workflow_id": workflow_id, "kind": "schedule", "reason": "move the digest earlier", "stage": stage,
            "preview_token": token, "proposed": proposed}


ACTOR = {"kind": "screen", "remote": "100.86.82.17", "local": "100.86.82.16", "label": "dave via control-room from 100.86.82.17"}


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
                prose_stripped = re.sub(r"`[^`\n]*`", "", text)
                self.assertNotIn("~/dev/agent-workforce", prose_stripped, f"{relative} names the live checkout outside a code span")


class Outcomes(TempState):
    def setUp(self) -> None:
        super().setUp()
        self.worker = make_worker(self.tmp, self.remote)

    def records(self, workflow_id="alpha", kind="schedule"):
        return record.list_records(self.state, workflow_id, kind, with_diff=True)

    def test_preview_before_pr(self):
        """(::proposal-preview-before-pr)"""
        rec, response = self.worker.preview(schedule_request(), ACTOR)
        self.assertEqual(rec["stage"], "previewed")
        for key in ("diff", "diff_sha256", "checks", "preview_token", "submit_allowed", "branch", "base", "files", "expires_at"):
            self.assertIn(key, response)
        self.assertEqual(response["preview_token"], rec["proposal_id"])
        self.assertEqual(response["branch"], f"control-room/schedule-alpha-{rec['proposal_id'].split('-')[0]}")
        self.assertIn("+OnCalendar=Sun 07:00", response["diff"])
        self.assertEqual(response["diff_sha256"], hashlib.sha256(response["diff"].encode()).hexdigest())
        self.assertEqual(sorted(f["path"] for f in response["files"]), ["design/agents/claudius.toml", "design/contracts/alpha.md", "systemd/alpha.timer"])
        self.assertEqual(remote_heads(self.remote), ["main"])
        self.assertEqual(gh_log(self.tmp), [])
        self.assertFalse((self.state / "work" / rec["proposal_id"]).exists())
        self.assertEqual(response["base"]["sha"], self.seed_sha)
        self.assertEqual(record.validate_record(rec), [])

    def test_submit_needs_fresh_preview(self):
        """(::proposal-submit-needs-fresh-preview)"""
        rec, response = self.worker.submit(schedule_request(stage="submit"), ACTOR)
        self.assertEqual(response["error"]["code"], "preview_required")
        self.assertEqual(rec["stage"], "refused")
        self.assertEqual(remote_heads(self.remote), ["main"])
        preview, _ = self.worker.preview(schedule_request(), ACTOR)
        token = preview["proposal_id"]
        commit_on_main(self.tmp, "systemd/alpha.timer", (FIXTURES / "repo/systemd/alpha.timer").read_text().replace("5min", "7min"))
        rec, response = self.worker.submit(schedule_request(stage="submit", token=token), ACTOR)
        self.assertEqual(response["error"]["code"], "preview_stale")
        self.assertIn("+OnCalendar=Sun 07:00", response["error"]["diff"])
        self.assertIn("7min", response["error"]["diff"])
        self.assertEqual(remote_heads(self.remote), ["main"])
        preview, _ = self.worker.preview(schedule_request(), ACTOR)
        self.worker.set_now(NOW + dt.timedelta(minutes=31))
        rec, response = self.worker.submit(schedule_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        self.assertEqual(response["error"]["code"], "preview_stale")
        self.worker.set_now(NOW + dt.timedelta(minutes=5))
        preview, previewed = self.worker.preview(schedule_request(), ACTOR)
        new_base = commit_on_main(self.tmp, "docs/unrelated.md", "unrelated\n")
        rec, response = self.worker.submit(schedule_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        self.assertEqual(rec["stage"], "submitted", response)
        self.assertEqual(rec["base"]["sha"], new_base)
        branch = rec["branch"]
        self.assertEqual(remote_heads(self.remote), [branch, "main"])
        self.assertEqual(remote_diff(self.remote, branch), previewed["diff"])
        self.assertEqual(rec["diff_sha256"], preview["diff_sha256"])
        creates = [entry for entry in gh_log(self.tmp) if entry["call"] == "pr create"]
        self.assertEqual(len(creates), 1)
        argv = creates[0]["argv"]
        for flag, value in (("--repo", "fixture/repo"), ("--base", "main"), ("--head", branch)):
            self.assertEqual(argv[argv.index(flag) + 1], value)
        self.assertIn("--title", argv)
        self.assertIn("--body-file", argv)
        self.assertNotIn("--draft", argv)
        for section in ("# Schedule change: alpha (alpha.timer)", "## Current → proposed", "## Diff", "## Checks", "## Reviewer attention", "## Land (Dave-only"):
            self.assertIn(section, creates[0]["body"])
        self.assertEqual(response["pr"]["url"], "https://github.com/fixture/repo/pull/1")
        self.assertEqual(response["stage"], "submitted")
        self.assertFalse((self.state / "work" / rec["proposal_id"]).exists())
        self.assertNotIn(branch, subprocess.run(["git", "branch", "--list"], cwd=self.state / "repo.git", capture_output=True, text=True).stdout)

    def test_never_touches_main_or_runtime(self):
        """(::proposal-never-touches-main-or-runtime) — the tree half."""
        checkout_copy = self.tmp / "dev-agent-workforce"
        shutil.copytree(FIXTURES / "repo", checkout_copy)
        before_runtime, before_checkout = tree_digest(FIXTURES / "runtime"), tree_digest(checkout_copy)
        before_main = _git(self.remote, "rev-parse", "main")
        preview, _ = self.worker.preview(schedule_request(), ACTOR)
        rec, _ = self.worker.submit(schedule_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        self.assertEqual(rec["stage"], "submitted")
        self.assertEqual(tree_digest(FIXTURES / "runtime"), before_runtime)
        self.assertEqual(tree_digest(checkout_copy), before_checkout)
        self.assertEqual(_git(self.remote, "rev-parse", "main"), before_main)
        pushes = [c["argv"] for r in self.records() for c in r["commands"] if c["argv"][:2] == ["git", "push"]]
        self.assertEqual(len(pushes), 1)
        self.assertRegex(pushes[0][3], r"^HEAD:refs/heads/control-room/schedule-alpha-\d{8}T\d{6}Z$")
        self.assertEqual(pushes[0][:3], ["git", "push", "origin"])
        for r in self.records():
            for c in r["commands"]:
                self.assertNotIn("--force", c["argv"])

    def test_refusals_and_status_map(self):
        """(::proposal-refusals-and-status-map) — the worker half; HTTP codes live in HttpSeam."""
        rec, response = self.worker.preview(schedule_request("nope"), ACTOR)
        self.assertEqual(response["error"]["code"], "unknown_workflow")
        rec, response = self.worker.preview(schedule_request("buzz-agent@trajan"), ACTOR)
        self.assertEqual(response["error"]["code"], "not_a_timer")
        rec, response = self.worker.preview(schedule_request("refresh"), ACTOR)
        self.assertEqual(response["error"]["code"], "not_calendar_timer")
        rec, response = self.worker.preview(schedule_request("gamma", specs=("Tue 03:30",)), ACTOR)
        self.assertEqual(response["error"]["code"], "trigger_required")
        self.assertEqual(response["error"]["choices"], ["gamma", "gamma-dispatch"])
        preview, _ = self.worker.preview(schedule_request(), ACTOR)
        os.environ["FAKE_GH_PR_LIST"] = json.dumps([{"url": "https://github.com/fixture/repo/pull/7", "headRefName": "control-room/schedule-alpha-20260901T000000Z"}])
        rec, response = self.worker.submit(schedule_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        self.assertEqual(response["error"]["code"], "open_proposal_exists")
        self.assertEqual(response["error"]["choices"], ["https://github.com/fixture/repo/pull/7"])
        self.assertEqual(remote_heads(self.remote), ["main"])
        os.environ.pop("FAKE_GH_PR_LIST")
        os.environ["FAKE_GH_FAIL"] = "create"
        rec, response = self.worker.submit(schedule_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        os.environ.pop("FAKE_GH_FAIL")
        self.assertEqual(rec["stage"], "failed")
        self.assertTrue(response["branch_pushed"])
        self.assertIn(rec["branch"], remote_heads(self.remote))
        self.assertEqual(rec["refusal"]["code"], "failed")
        shutil.rmtree(self.state)
        rec, response = self.worker.preview(schedule_request(), ACTOR)
        self.assertEqual(response["error"]["code"], "worker_unavailable")
        self.assertIn("doctor", response["error"]["message"])

    def test_every_outcome_recorded(self):
        """(::proposal-every-outcome-recorded) — the worker half."""
        preview, _ = self.worker.preview(schedule_request(), ACTOR)
        self.worker.submit(schedule_request(stage="submit"), ACTOR)
        os.environ["FAKE_GH_FAIL"] = "create"
        self.worker.submit(schedule_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        os.environ.pop("FAKE_GH_FAIL")
        stages = sorted(r["stage"] for r in self.records())
        self.assertEqual(stages, ["failed", "previewed", "refused"])
        for rec in self.records():
            self.assertEqual(record.validate_record(rec), [], rec["proposal_id"])
            for command in rec["commands"]:
                self.assertIn(command["argv"][0], ("git", "gh"))
                self.assertIn("exit", command)
        failed = next(r for r in self.records() if r["stage"] == "failed")
        self.assertTrue(any(c["argv"][:2] == ["gh", "pr"] and c["exit"] == 1 for c in failed["commands"]))
        self.assertEqual(list(self.state.rglob("*.tmp")), [])
        results = []

        def run():
            results.append(self.worker.preview(schedule_request(), ACTOR)[0])
        threads = [threading.Thread(target=run) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        stages = sorted(r["stage"] for r in results)
        self.assertIn(stages, (["previewed", "previewed"], ["previewed", "refused"]))
        if "refused" in stages:
            self.assertEqual(next(r for r in results if r["stage"] == "refused")["refusal"]["code"], "locked")
        self.assertEqual(sorted(p.name for p in (self.state / "work").iterdir()), ["base"])

    def test_list_stage(self):
        """(::proposal-list-stage)"""
        first, _ = self.worker.preview(schedule_request(), ACTOR)
        self.worker.set_now(NOW + dt.timedelta(minutes=1))
        second, _ = self.worker.preview(schedule_request(), ACTOR)
        before = len(self.records())
        listed = self.worker.list("alpha", "schedule")
        self.assertEqual(listed["stage"], "list")
        self.assertEqual([r["proposal_id"] for r in listed["items"]], [second["proposal_id"], first["proposal_id"]])
        self.assertTrue(all("diff" not in r for r in listed["items"]))
        self.assertEqual(len(self.records()), before)
        self.assertEqual(self.worker.git.commands, [])

    def test_doctor(self):
        """(::proposal-doctor)"""
        lines = self.worker.doctor()
        self.assertTrue(all(status == "ok" for status, _ in lines), lines)
        shutil.rmtree(self.state / "repo.git")
        lines = self.worker.doctor()
        self.assertIn(("fail", "repo.git missing — run: bin/workflow_pr.py init"), lines)
        saved = os.environ["PATH"]
        os.environ["PATH"] = "/nonexistent"
        try:
            lines = self.worker.doctor()
        finally:
            os.environ["PATH"] = saved
        self.assertTrue(any(status == "fail" and "gh" in line for status, line in lines), lines)
        self.assertEqual(worker_module.main(["--state", str(self.state), "--remote", str(self.remote), "doctor"]), 1)


class HttpSeam(TempState):
    """(::proposal-refusals-and-status-map) — the HTTP half over the T5.3 fixture helper."""

    def setUp(self) -> None:
        super().setUp()
        self.worker = make_worker(self.tmp, self.remote)
        self.control = proposals_module.ProposalsControl(self.worker)
        repo = (FIXTURES / "repo").resolve()
        self.model = api.ControlRoomReadModel(paths=api.SourcePaths(repo=repo, runtime=repo, receipts=repo / "var" / "receipts"),
                                              systemd=FakeSystemd(), clock=lambda: NOW, calendar_runner=lambda spec: [])
        self.server = api.make_server("127.0.0.1", 0, self.model)
        self.server.RequestHandlerClass.proposals = self.control
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"
        self.addCleanup(self._close)

    def _close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)

    def post(self, payload, headers=None, method="POST"):
        body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        request = urllib.request.Request(f"{self.base}/api/v1/control/proposals", data=body, method=method,
                                         headers={"Content-Type": "application/json", "X-Control-Room": "1"} if headers is None else headers)
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                raw, status = response.read(), response.status
        except urllib.error.HTTPError as error:
            raw, status = error.read(), error.code
        try:
            return status, json.loads(raw)
        except json.JSONDecodeError:
            return status, None

    def test_shape_and_status_map(self):
        status, body = self.post(schedule_request("nope"))
        self.assertEqual((status, body["error"]["code"]), (404, "unknown_workflow"))
        status, body = self.post({**schedule_request(), "kind": "rm"})
        self.assertEqual((status, body["error"]["code"]), (400, "unknown_kind"))
        status, body = self.post({**schedule_request(), "stage": "merge"})
        self.assertEqual((status, body["error"]["code"]), (400, "unknown_stage"))
        status, body = self.post(schedule_request(), headers={"Content-Type": "application/json"})
        self.assertEqual(status, 400)
        status, body = self.post(b"not json")
        self.assertEqual(status, 400)
        status, body = self.post(schedule_request("../x"))
        self.assertEqual((status, body["error"]["code"]), (400, "bad_request"))
        status, body = self.post(schedule_request("buzz-agent@trajan"))
        self.assertEqual(status, 400)
        status, body = self.post(schedule_request("refresh"))
        self.assertEqual((status, body["error"]["code"]), (400, "not_calendar_timer"))
        status, body = self.post(schedule_request("gamma", specs=("Tue 03:30",)))
        self.assertEqual((status, body["error"]["code"], body["error"]["choices"]), (400, "trigger_required", ["gamma", "gamma-dispatch"]))
        status, body = self.post(schedule_request())
        self.assertEqual((status, body["stage"]), (200, "preview"), body)
        self.assertEqual(body["control"], self.model.workflow_detail("alpha")[0]["control"])
        self.assertTrue(body["submit_allowed"], body["submit_blockers"])
        status, body = self.post({**schedule_request(stage="list"), "kind": "schedule"})
        self.assertEqual((status, body["stage"], len(body["items"])), (200, "list", 1))
        for method in ("GET", "HEAD"):
            status, _ = self.post(schedule_request(), method=method)
            self.assertEqual(status, 405, method)

    def test_peer_gate(self):
        self.assertFalse(proposals_module.peer_allowed("100.86.82.16", "100.86.82.16")[0])
        self.assertFalse(proposals_module.peer_allowed("127.0.0.1", "100.86.82.16")[0])
        self.assertTrue(proposals_module.peer_allowed("100.86.82.20", "100.86.82.16")[0])
        self.assertTrue(proposals_module.peer_allowed("100.86.82.16", "127.0.0.1")[0])
        original = proposals_module._actor
        proposals_module._actor = lambda handler: {"kind": "screen", "remote": "100.86.82.16", "local": "100.86.82.16", "label": "t"}
        self.addCleanup(setattr, proposals_module, "_actor", original)
        status, body = self.post(schedule_request())
        self.assertEqual((status, body["error"]["code"]), (403, "peer_denied"))
        self.assertEqual(remote_heads(self.remote), ["main"])

    def test_open_pr_failed_and_unavailable(self):
        status, preview = self.post(schedule_request())
        self.assertEqual(status, 200, preview)
        os.environ["FAKE_GH_PR_LIST"] = json.dumps([{"url": "https://github.com/fixture/repo/pull/7", "headRefName": "control-room/schedule-alpha-20260901T000000Z"}])
        status, body = self.post(schedule_request(stage="submit", token=preview["proposal_id"]))
        os.environ.pop("FAKE_GH_PR_LIST")
        self.assertEqual((status, body["error"]["code"], body["error"]["choices"]), (400, "open_proposal_exists", ["https://github.com/fixture/repo/pull/7"]))
        os.environ["FAKE_GH_FAIL"] = "create"
        status, body = self.post(schedule_request(stage="submit", token=preview["proposal_id"]))
        os.environ.pop("FAKE_GH_FAIL")
        self.assertEqual(status, 500)
        self.assertTrue(body["branch_pushed"])
        self.assertIn(body["record"]["branch"], remote_heads(self.remote))
        status, body = self.post(schedule_request(stage="submit", token=preview["proposal_id"]))
        self.assertEqual((status, body["error"]["code"]), (400, "open_proposal_exists"), body)
        self.assertIn(preview["branch"], body["error"]["message"])
        shutil.rmtree(self.state)
        status, body = self.post(schedule_request())
        self.assertEqual((status, body["error"]["code"]), (503, "worker_unavailable"))
        self.assertIn("doctor", body["error"]["message"])

    def test_stub_when_nothing_bound(self):
        self.server.RequestHandlerClass.proposals = None
        status, body = self.post(schedule_request())
        self.assertEqual((status, body["status"]), (501, "not_implemented"))
        status, body = self.post(schedule_request("nope"))
        self.assertEqual(status, 404)


if __name__ == "__main__":
    unittest.main()
