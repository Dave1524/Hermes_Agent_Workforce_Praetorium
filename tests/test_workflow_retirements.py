#!/usr/bin/env python3
"""T5.3b — the retired-workflows registry consumer. Group 1 runs in every checkout: each
[[retired]] entry is well-formed and leaves no blocking residue in the source tree. Group 2 runs
on the box only (the wrapper guards it): a cleared entry must stay clear live, and an uncleared
one FAILS naming its pending items and the clear command — the same red the drift check shows
post-merge, with names.

Anchors: (::retired-registry-clean-source) (::retired-registry-live-clean)
"""
from __future__ import annotations

import os
import pathlib
import shutil
import sys
import tempfile
import tomllib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "bin"))

import workflow_retire_residue as residue  # noqa: E402

FIXTURES = ROOT / "tests" / "fixtures" / "control-proposals"
REQUIRED = {"id": str, "units": list, "owner": str, "scope": str, "retired_on": str, "reason": str, "proposal": str,
            "branch": str, "pr": str, "runners": list, "profiles": list, "contract": str, "suites": list,
            "env_override": str, "run_markers": list, "artifact_retention": dict, "residue_cleared_on": str,
            "env_removed_attested": bool}
RETENTION_KEYS = ("receipts", "notion", "inbox")
LIVE = {"runtime_root": pathlib.Path.home() / "agent-workforce", "etc_dir": pathlib.Path("/etc/systemd/system"),
        "user_tree": pathlib.Path.home() / ".config/systemd/user"}


def entry_problems(entry: dict) -> list[str]:
    problems = [f"{key} missing or not {kind.__name__}" for key, kind in REQUIRED.items() if not isinstance(entry.get(key), kind)]
    retention = entry.get("artifact_retention") or {}
    problems += [f"artifact_retention.{key} missing" for key in RETENTION_KEYS if not isinstance(retention.get(key), str)]
    return problems


def source_findings(root: pathlib.Path, entry: dict) -> list[str]:
    report = residue.scan_source(root, residue.subjects_from_entry(entry))
    return [f"{i['class']} {i['path']}: {i['what']}" for i in report["items"] if i["blocks"]]


def live_findings(entry: dict, live: dict) -> list[str]:
    report = residue.scan_live(residue.subjects_from_entry(entry), live["runtime_root"], live["etc_dir"], live["user_tree"])
    return [f"{i['class']} {i['path']}: {i['what']} — {i['how']}" for i in report["items"] if i["blocks"]]


def clear_command(entry: dict) -> str:
    env = " --env-removed" if entry.get("env_override") else ""
    return f"bin/workflow_pr.py clear {entry['id']}{env} --pr <url>"


class RegistrySource(unittest.TestCase):
    """(::retired-registry-clean-source)"""

    def test_registry_entries_are_clean_in_source(self):
        entries = residue.registry_entries(ROOT)
        if not entries:
            print("checked 0 retired entries (registry created empty, T5.3b)")
            return
        for entry in entries:
            with self.subTest(entry=entry.get("id")):
                self.assertEqual(entry_problems(entry), [])
                self.assertEqual(source_findings(ROOT, entry), [], f"{entry['id']}: residue in source")
        print(f"checked {len(entries)} retired entries")

    def test_half_retired_entry_is_named(self):
        tmp = pathlib.Path(tempfile.mkdtemp(prefix="retirements-"))
        self.addCleanup(shutil.rmtree, tmp, True)
        shutil.copytree(FIXTURES / "repo", tmp / "repo")
        root = tmp / "repo"
        entry = synthetic_entry()
        (root / "design/retired-workflows.toml").write_text(render_entry(entry), encoding="utf-8")
        self.assertEqual(entry_problems(entry), [])
        findings = source_findings(root, entry)
        self.assertTrue(any(f.startswith("executable systemd/alpha.timer") for f in findings), findings)
        for relative in ("systemd/alpha.timer", "systemd/alpha.service", "bin/run_alpha_cc.sh", "profiles/alpha_task.md",
                         "profiles/alpha.env.example", "tests/test_alpha_smoke.sh", "design/contracts/alpha.md"):
            (root / relative).unlink()
        manifest = root / "design/agents/claudius.toml"
        lines = manifest.read_text().splitlines(keepends=True)
        start = next(i for i, line in enumerate(lines) if line.startswith("[[workflows]]") and 'unit     = "alpha"' in "".join(lines[i:i + 3]))
        end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[[")), len(lines))
        manifest.write_text("".join(lines[:start] + lines[end:]).replace("governed_by = \"bin/run_alpha_cc.sh, ", "governed_by = \""))
        (root / "config/fleet-units.tsv").write_text("".join(l for l in (root / "config/fleet-units.tsv").read_text().splitlines(keepends=True) if not l.startswith("alpha\t")))
        (root / "bin/buzz_producers.tsv").write_text("".join(l for l in (root / "bin/buzz_producers.tsv").read_text().splitlines(keepends=True) if "alpha.service" not in l))
        (root / "tests/ci-expected-skips.txt").write_text("".join(l for l in (root / "tests/ci-expected-skips.txt").read_text().splitlines(keepends=True) if "alpha" not in l))
        self.assertEqual(source_findings(root, entry), [])
        broken = dict(entry, units=["alpha"], id="alpha")
        del broken["pr"]
        self.assertIn("pr missing or not str", entry_problems(broken))
        del broken["artifact_retention"]["inbox"]
        self.assertIn("artifact_retention.inbox missing", entry_problems(broken))


class RegistryLive(unittest.TestCase):
    """(::retired-registry-live-clean) — the wrapper runs this group on the box only."""

    def test_fixture_live_verdicts(self):
        live = {"runtime_root": FIXTURES / "runtime", "etc_dir": FIXTURES / "etc", "user_tree": FIXTURES / "user"}
        pending = synthetic_entry()
        findings = live_findings(pending, live)
        self.assertTrue(any("installed" in f and "alpha.timer" in f for f in findings), findings)
        self.assertIn("unverifiable from an agent", " ".join(findings))
        self.assertEqual(clear_command(pending), "bin/workflow_pr.py clear alpha --env-removed --pr <url>")
        cleared = dict(pending, residue_cleared_on="2026-09-14", env_removed_attested=True)
        self.assertTrue(live_findings(cleared, live), "a cleared entry whose units came back must be red")

    def test_registry_entries_are_clean_live(self):
        if os.environ.get("RETIREMENTS_LIVE") != "1":
            self.skipTest("live group runs through tests/test_workflow_retirements.sh on the box")
        entries = residue.registry_entries(ROOT)
        if not entries:
            print("checked 0 retired entries live")
            return
        for entry in entries:
            with self.subTest(entry=entry.get("id")):
                findings = live_findings(entry, LIVE)
                if entry.get("residue_cleared_on"):
                    self.assertEqual(findings, [], f"{entry['id']}: cleared on {entry['residue_cleared_on']} but live residue came back")
                else:
                    self.fail(f"{entry['id']}: retirement not cleared — pending: " + "; ".join(findings or ["(nothing live)"]) + f". Run: {clear_command(entry)}")


def synthetic_entry() -> dict:
    return {"id": "alpha", "units": ["alpha"], "owner": "claudius", "scope": "system", "retired_on": "2026-09-14",
            "reason": "synthetic half-retired entry", "proposal": "20260914T080000Z-retire-alpha-abc123",
            "branch": "control-room/retire-alpha-20260914T080000Z", "pr": "", "runners": ["bin/run_alpha_cc.sh"],
            "profiles": ["profiles/alpha_task.md", "profiles/alpha.env.example"], "contract": "design/archive/contracts/alpha.md",
            "suites": ["tests/test_alpha_smoke.sh"], "env_override": "/home/dave/.config/agent-workforce/alpha.env",
            "run_markers": ["/home/dave/logs/run-markers/alpha.service"],
            "artifact_retention": {"receipts": "archive", "notion": "keep", "inbox": "delete", "note": ""},
            "residue_cleared_on": "", "env_removed_attested": False}


def render_entry(entry: dict) -> str:
    def value(v):
        if isinstance(v, bool):
            return "true" if v else "false"
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, list):
            return "[" + ", ".join(value(x) for x in v) + "]"
        return "{ " + ", ".join(f"{k} = {value(x)}" for k, x in v.items()) + " }"
    return "[[retired]]\n" + "".join(f"{k} = {value(v)}\n" for k, v in entry.items())


if __name__ == "__main__":
    unittest.main()
