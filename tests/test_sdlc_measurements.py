#!/usr/bin/env python3
"""bin/sdlc_measurements.py: the three SDLC numbers, read from LAND records (T8.7).

A git history is built in a tempdir — T9.1 shipped, reworked once and archived with a LAND
body; T9.2 archived first-pass by git but lost to the harness by the run records; T9.3
archived with no body; T9.4 added in a batch commit — and read against the run-record
fixtures under tests/fixtures/sdlc-measurements/. Anchors are the `::` comments;
tests/test_sdlc_measurements.sh is the gate entry point.
"""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "sdlc-measurements"
TOOL = ROOT / "bin" / "sdlc_measurements.py"
RUNS = str(FIX / "runs" / "wf_*.json")
GIT_ENV = {"GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example.invalid",
           "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example.invalid",
           "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"}
LAND_BODY = "Landed by fast-forward.\n\nverifyExit: 0\n  bash bin/verify.sh\n"
BRIEFS = ".claude/briefs"


def load_tool():
    spec = importlib.util.spec_from_file_location("sdlc_measurements", TOOL)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


sdlc = load_tool()


class FixtureRepo:
    def __init__(self, root: pathlib.Path):
        self.root = root
        self.git("init", "-q", "-b", "main")

    def git(self, *args: str) -> None:
        subprocess.run(["git", "-C", str(self.root), *args], check=True, capture_output=True,
                       env={**os.environ, **GIT_ENV})

    def write(self, rel: str, body: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(body)

    def commit(self, message: str, writes: dict[str, str] | None = None, rm: tuple[str, ...] = ()) -> None:
        for rel, body in (writes or {}).items():
            self.write(rel, body)
        for rel in rm:
            self.git("rm", "-q", rel)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def archive(self, slug: str, task: str, body: str = "") -> None:
        self.git("mv", f"{BRIEFS}/{slug}.md", f"{BRIEFS}/archive/2026-09-20-{slug}.md")
        self.git("commit", "-q", "-m", f"docs(briefs): archive {task} — {slug}\n\n{body}")


def brief(task: str) -> str:
    return f"# Brief: {task}\n**Date:** 2026-09-20\n\n## Files to modify\n- `bin/{task}.sh` — x\n"


def build_history(repo: FixtureRepo) -> None:
    repo.commit("chore: base", {"bin/old.sh": "old\n", "README.md": "r\n", f"{BRIEFS}/archive/.keep": ""})
    repo.commit("feat: T9.1", {f"{BRIEFS}/t9-1-fixture.md": (FIX / "briefs" / "t9-1-fixture.md").read_text(),
                               "bin/a.sh": "a\n", "tests/test_a.sh": "t\n"}, rm=("bin/old.sh",))
    repo.commit("fix(a): review finding", {"bin/a.sh": "a2\n", "docs/extra.md": "unplanned\n"})
    repo.archive("t9-1-fixture", "T9.1", LAND_BODY)
    repo.commit("feat: T9.2", {f"{BRIEFS}/t9-2-second.md": brief("T9.2"), "bin/T9.2.sh": "b\n"})
    repo.archive("t9-2-second", "T9.2", LAND_BODY)
    repo.commit("feat: T9.3", {f"{BRIEFS}/t9-3-bodiless.md": brief("T9.3"), "bin/T9.3.sh": "c\n"})
    repo.archive("t9-3-bodiless", "T9.3")
    repo.commit("docs(briefs): plan T9.4 and T9.5", {f"{BRIEFS}/t9-4-batch.md": brief("T9.4"),
                                                     f"{BRIEFS}/t9-5-other.md": brief("T9.5")})
    repo.commit("feat: T9.4", {"bin/T9.4.sh": "d\n"})
    repo.archive("t9-4-batch", "T9.4", LAND_BODY)


class SdlcMeasurementsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._tmp = tempfile.TemporaryDirectory()
        cls.repo = pathlib.Path(cls._tmp.name) / "repo"
        cls.repo.mkdir()
        build_history(FixtureRepo(cls.repo))
        cls.runs = sdlc.load_runs(RUNS)
        cls.rows = {r.task: r for r in sdlc.measure(str(cls.repo), None, cls.runs)}
        cls.git_rows = {r.task: r for r in sdlc.measure(str(cls.repo), None, [])}

    @classmethod
    def tearDownClass(cls):
        cls._tmp.cleanup()

    def run_main(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            rc = sdlc.main(list(argv))
        return rc, out.getvalue()

    def test_record_set(self):
        # (::sdlc-record-set)
        self.assertEqual(sorted(self.rows), ["T9.1", "T9.2", "T9.3", "T9.4"])
        self.assertIsNone(self.rows["T9.3"].record)
        self.assertEqual(sdlc.cells(self.rows["T9.3"], True)[2:], ["none"] + ["-"] * 9)
        self.assertIsNone(self.rows["T9.4"].commits)
        self.assertEqual(sdlc.cells(self.rows["T9.4"], True)[-1], "undefined")
        self.assertEqual([r["workflowName"] for r in self.runs], ["ship-dev-plan", "ship-dev-plan"])
        self.assertEqual(self.rows["T9.1"].attempts, ["review", "landed"])

    def test_first_pass_rework(self):
        # (::sdlc-first-pass-rework)
        t91, t92 = self.rows["T9.1"], self.rows["T9.2"]
        self.assertEqual(sdlc.run_numbers(t91), (False, 1, 0))
        self.assertEqual(t91.landed_by, "workflow")
        self.assertEqual(sdlc.git_numbers(self.git_rows["T9.1"]), (False, 1))
        self.assertIsNone(t91.warn)
        self.assertEqual(sdlc.run_numbers(t92), (False, 0, 1))
        self.assertEqual(t92.landed_by, "hand")
        self.assertIn("WARN T9.2", t92.warn)
        rc, out = self.run_main("--repo", str(self.repo), "--runs", RUNS)
        self.assertEqual(rc, 0)
        self.assertIn("WARN T9.2", out)
        self.assertIn("first_pass (git)", self.run_main("--repo", str(self.repo))[1].splitlines()[0])

    def test_plan_fidelity(self):
        # (::sdlc-plan-fidelity)
        text = (FIX / "briefs" / "t9-1-fixture.md").read_text()
        named = sdlc.brief_files(text, {f"{BRIEFS}/t9-1-fixture.md"})
        self.assertEqual(named, {"bin/a.sh", "bin/never.sh", "tests/test_a.sh", "bin/old.sh"})
        t91 = self.rows["T9.1"]
        self.assertEqual(t91.touched - t91.named, {"docs/extra.md"})
        self.assertEqual(t91.named - t91.touched, {"bin/never.sh"})
        self.assertEqual(sdlc.fidelity_cells(t91), ["3", "1", "1", "0.60"])
        md = sdlc.render_markdown(list(self.rows.values()), True, [], "2026-09-22")
        self.assertIn("unplanned: docs/extra.md; not_done: bin/never.sh", md)

    def test_markdown_once(self):
        # (::sdlc-markdown-once)
        argv = ("--repo", str(self.repo), "--runs", RUNS, "--markdown", "--today", "2026-09-22")
        first, second = self.run_main(*argv)[1], self.run_main(*argv)[1]
        self.assertEqual(first, second)
        self.assertIn("MEASURED 2026-09-22", first)
        self.assertIn("python3 bin/sdlc_measurements.py --repo", first)
        self.assertIn("## No LAND record", first)
        self.assertIn("- T9.3 — `", first)
        with self.assertRaises(SystemExit), contextlib.redirect_stderr(io.StringIO()):
            sdlc.main(["--repo", str(self.repo), "--markdown"])


if __name__ == "__main__":
    unittest.main()
