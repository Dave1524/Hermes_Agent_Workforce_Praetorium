#!/usr/bin/env python3
"""T5.3b — the W19-class residue scanner: every source class over the fixture repo, the live scan
that never stats the deny-listed env, the W19 regression table and the CLI exit codes.

Anchors: (::residue-source-classes) (::residue-w19-table) (::residue-live-fails-closed)
(::residue-cli). (::residue-fails-closed-on-branch) lives in tests/test_workflow_pr_retire.py
because it needs plan_retire.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import sys
import tempfile
import unittest
from contextlib import redirect_stdout

REPO = pathlib.Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures" / "control-proposals"
sys.path.insert(0, str(REPO / "bin"))
os.environ["PATH"] = f"{FIXTURES / 'bin'}:{os.environ.get('PATH', '')}"

import workflow_retire_residue as residue  # noqa: E402


def by_class(report: dict) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for item in report["items"]:
        out.setdefault(item["class"], []).append(item)
    return out


def paths(items: list[dict]) -> list[str]:
    return sorted(str(item["path"]) for item in items)


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="crr-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        shutil.copytree(FIXTURES / "repo", self.repo)
        self.subjects = residue.subjects_from_manifests(self.repo, "alpha")


class SourceClasses(Fixture):
    """(::residue-source-classes)"""

    def test_subject_set_from_manifests(self):
        s = self.subjects
        self.assertEqual(s["id"], "alpha")
        self.assertEqual(s["units"], ["alpha"])
        self.assertEqual(s["scope"], "system")
        self.assertEqual(s["runners"], ["bin/run_alpha_cc.sh"])
        self.assertEqual(sorted(s["profiles"]), ["profiles/alpha.env.example", "profiles/alpha_task.md"])
        self.assertEqual(s["contract"], "design/contracts/alpha.md")
        self.assertEqual(s["suites"], ["tests/test_alpha_smoke.sh"])
        self.assertEqual(s["env_override"], "/home/dave/.config/agent-workforce/alpha.env")
        self.assertEqual(s["run_markers"], ["/home/dave/logs/run-markers/alpha.service"])
        self.assertEqual(s["owner"], "claudius")
        self.assertIn("alpha", s["slugs"])
        self.assertIsNone(residue.subjects_from_manifests(self.repo, "nope"))

    def test_shared_runner_is_not_owned(self):
        gamma = residue.subjects_from_manifests(self.repo, "gamma")
        self.assertEqual(gamma["units"], ["gamma", "gamma-dispatch"])
        self.assertEqual(gamma["runners"], ["bin/run_gamma_cc.sh"])
        manifest = self.repo / "design/agents/claudius.toml"
        manifest.write_text(manifest.read_text().replace('runner   = "bin/run_beta_cc.sh"', 'runner   = "bin/run_alpha_cc.sh"'))
        self.assertEqual(residue.subjects_from_manifests(self.repo, "alpha")["runners"], [])

    def test_every_class_before_removal(self):
        report = residue.scan_source(self.repo, self.subjects)
        classes = by_class(report)
        self.assertEqual(report["verdict"], "residue")
        executable = paths(classes["executable"])
        for expected in ("systemd/alpha.timer", "systemd/alpha.service", "design/agents/claudius.toml", "bin/run_alpha_cc.sh"):
            self.assertIn(expected, executable, executable)
        whats = " ".join(item["what"] for item in classes["executable"])
        self.assertIn("governed_by", whats)
        self.assertIn("[[workflows]]", whats)
        self.assertIn("runner   = ", whats)
        service = self.repo / "systemd/beta.service"
        service.write_text(service.read_text() + "ExecStartPre=/home/dave/agent-workforce/bin/run_alpha_cc.sh --warm\n")
        exec_whats = " ".join(item["what"] for item in by_class(residue.scan_source(self.repo, self.subjects))["executable"])
        self.assertIn("systemd/beta.service", exec_whats)
        self.assertIn("ExecStartPre", exec_whats)
        self.assertEqual(paths(classes["files"]), ["design/contracts/alpha.md", "profiles/alpha.env.example", "profiles/alpha_task.md", "tests/test_alpha_smoke.sh"])
        self.assertEqual(paths(classes["declared"]), ["bin/buzz_producers.tsv", "config/fleet-units.tsv", "tests/ci-expected-skips.txt"])
        prose = paths(classes["prose"])
        self.assertIn("design/agents/claudius.toml", prose)
        self.assertIn("docs/runbook.md", prose)
        self.assertTrue(all(item["line"] for item in classes["prose"]))
        self.assertNotIn("inert", classes)
        for item in report["items"]:
            self.assertEqual(item["blocks"], item["class"] in residue.BLOCKING_SOURCE, item)
            for key in ("class", "path", "line", "what", "tree", "has_check", "clears", "how", "blocks"):
                self.assertIn(key, item)
            self.assertEqual(item["tree"], "source")
            self.assertIn(item["clears"], residue.CLEARERS)

    def test_after_removal_only_prose_and_pending_prune(self):
        for relative in ("systemd/alpha.timer", "systemd/alpha.service", "bin/run_alpha_cc.sh", "profiles/alpha_task.md",
                         "profiles/alpha.env.example", "design/contracts/alpha.md", "tests/test_alpha_smoke.sh"):
            (self.repo / relative).unlink()
        manifest = self.repo / "design/agents/claudius.toml"
        text = manifest.read_text()
        start = text.index("[[workflows]]")
        end = text.index("[[workflows]]", start + 1)
        manifest.write_text((text[:start] + text[end:]).replace("bin/run_alpha_cc.sh, ", ""))
        for relative, needle in (("config/fleet-units.tsv", "alpha\t"), ("bin/buzz_producers.tsv", "alpha.service"), ("tests/ci-expected-skips.txt", "alpha")):
            path = self.repo / relative
            path.write_text("".join(line for line in path.read_text().splitlines(True) if needle not in line))
        exclusions = self.repo / "design/deploy-exclusions.toml"
        exclusions.write_text(exclusions.read_text() + '\n[[runtime_only]]\npath  = "bin/run_alpha_cc.sh"\ntree  = "bin"\nsince = "2026-09-15"\nwhy   = "retired alpha"\n')
        report = residue.scan_source(self.repo, self.subjects)
        self.assertEqual(report["verdict"], "clear", residue.render_w19_table(report))
        self.assertEqual(set(by_class(report)), {"prose", "declared-pending-prune"})
        pending = by_class(report)["declared-pending-prune"]
        self.assertEqual(paths(pending), ["design/deploy-exclusions.toml"])
        self.assertEqual(pending[0]["clears"], "bin/deploy --prune")

    def test_orphan_runner_is_inert_in_source(self):
        orphan = self.repo / "bin/run_orphan_cc.sh"
        orphan.write_text("#!/usr/bin/env bash\necho orphan\n")
        orphan.chmod(0o755)
        subjects = {**self.subjects, "runners": ["bin/run_orphan_cc.sh"], "units": [], "profiles": [], "contract": "", "suites": [], "slugs": ["orphan"]}
        report = residue.scan_source(self.repo, subjects)
        inert = by_class(report).get("inert", [])
        self.assertEqual(paths(inert), ["bin/run_orphan_cc.sh"])
        self.assertFalse(inert[0]["blocks"])
        self.assertEqual(report["verdict"], "clear")


class W19Table(unittest.TestCase):
    """(::residue-w19-table)"""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="crw19-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "w19"
        shutil.copytree(FIXTURES / "w19", self.repo)
        self.subjects = {"id": "campaign", "units": ["campaign-a", "campaign-b"], "scope": "system", "owner": "augustus",
                         "runners": ["bin/run_campaign_a_cc.sh", "bin/run_campaign_b_cc.sh", "bin/run_topic_cc.sh"],
                         "profiles": ["profiles/campaign_a_task.md", "profiles/campaign_b_task.md"], "contract": "",
                         "suites": ["tests/test_campaign_a_smoke.sh"], "env_override": None, "run_markers": [],
                         "slugs": ["campaign-a", "campaign-b", "campaign_a", "campaign_b"], "env_removed_attested": False}

    def test_reproduces_the_w19_rows(self):
        report = residue.scan_source(self.repo, self.subjects)
        classes = by_class(report)
        executable = paths(classes["executable"])
        self.assertEqual(sorted(set(executable) - {"design/agents/augustus.toml"}), ["bin/run_campaign_a_cc.sh", "bin/run_campaign_b_cc.sh", "bin/run_topic_cc.sh"])
        self.assertTrue(any("shim still execs bin/run_topic_cc.sh" in item["what"] for item in classes["executable"]))
        self.assertTrue(any("campaign-c.service" in item["what"] and "Exec" in item["what"] for item in classes["executable"]))
        self.assertEqual(paths(classes["files"]), ["profiles/campaign_a_task.md", "profiles/campaign_b_task.md"])
        self.assertEqual(paths(classes["declared"]), ["bin/buzz_producers.tsv", "config/fleet-units.tsv", "tests/ci-expected-skips.txt"])
        prose = classes["prose"]
        self.assertEqual(sum(1 for item in prose if item["path"] == "design/workflow-registry.md"), 2)
        self.assertTrue(any(item["path"] == "design/agents/augustus.toml" and "notes" in item["what"] for item in prose))
        self.assertTrue(any(item["path"] == "docs/runbook.md" for item in prose))
        self.assertGreaterEqual(len(report["items"]), 11)
        self.assertEqual(report["verdict"], "residue")
        table = residue.render_w19_table(report)
        self.assertEqual(table.splitlines()[0], "| # | residue | tree | has a check? | who clears it | how |")
        self.assertEqual(len([line for line in table.splitlines() if line.startswith("| ") and not line.startswith("| #")]), len(report["items"]))
        self.assertIn("| this PR |", table)
        self.assertIn("residue-source (this PR)", table)
        self.assertTrue(table.endswith("Verdict: residue"))

    def test_units_removed_alone_is_not_clear(self):
        campaign = self.repo / "systemd/campaign-c.service"
        campaign.write_text("[Service]\nExecStart=/bin/true\n")
        report = residue.scan_source(self.repo, self.subjects)
        self.assertEqual(report["verdict"], "residue")
        self.assertTrue(any(item["class"] == "executable" and item["blocks"] for item in report["items"]))


class LiveFailsClosed(unittest.TestCase):
    """(::residue-live-fails-closed)"""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="crl-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.runtime = self.tmp / "runtime"
        shutil.copytree(FIXTURES / "runtime", self.runtime)
        self.etc = self.tmp / "etc"
        shutil.copytree(FIXTURES / "etc", self.etc)
        self.user_tree = self.tmp / "user"
        self.user_tree.mkdir()
        self.state_file = self.tmp / "systemctl.json"
        self.state_file.write_text("{}")
        self.log = self.tmp / "systemctl.log"
        os.environ["FAKE_SYSTEMCTL_STATE"] = str(self.state_file)
        os.environ["FAKE_SYSTEMCTL_LOG"] = str(self.log)
        self.addCleanup(os.environ.pop, "FAKE_SYSTEMCTL_STATE", None)
        self.addCleanup(os.environ.pop, "FAKE_SYSTEMCTL_LOG", None)
        self.subjects = residue.subjects_from_manifests(FIXTURES / "repo", "alpha")
        self.subjects["env_override"] = str(FIXTURES / "deny/agent-workforce/alpha.env")
        original = residue.path_exists
        deny = pathlib.Path(self.subjects["env_override"])

        def guarded(path):
            if pathlib.Path(path) == deny:
                raise AssertionError(f"stat'ed the deny-listed {path}")
            return original(path)
        residue.path_exists = guarded
        self.addCleanup(setattr, residue, "path_exists", original)

    def scan(self, **overrides):
        subjects = {**self.subjects, **overrides}
        return residue.scan_live(subjects, self.runtime, self.etc, self.user_tree, residue.systemctl_runner)

    def test_installed_and_deployed_block(self):
        report = self.scan()
        classes = by_class(report)
        self.assertEqual(report["verdict"], "residue")
        installed = classes["installed"]
        self.assertEqual(paths(installed), sorted([str(self.etc / "alpha.service"), str(self.etc / "alpha.timer")]))
        self.assertTrue(all(item["clears"] == "sudo" and item["tree"] == "installed" for item in installed))
        self.assertIn(f"sudo rm {self.etc}/alpha.timer", installed[0]["how"] + installed[1]["how"])
        self.assertIn("sudo systemctl daemon-reload", installed[0]["how"])
        deployed = classes["deployed"]
        self.assertIn(str(self.runtime / "bin/run_alpha_cc.sh"), paths(deployed))
        self.assertIn(str(self.runtime / "systemd/alpha.timer"), paths(deployed))
        self.assertTrue(all(item["clears"] == "bin/deploy --prune" for item in deployed))
        dave = classes["dave-only"]
        self.assertEqual(len(dave), 1)
        self.assertIn("unverifiable from an agent", dave[0]["what"])
        self.assertIn(f"ls -l {self.subjects['env_override']}", dave[0]["what"])
        self.assertIn(f"rm {self.subjects['env_override']}", dave[0]["what"])
        self.assertNotIn("present", dave[0]["what"])
        self.assertNotIn("absent", dave[0]["what"])
        self.assertEqual(dave[0]["clears"], "Dave")
        self.assertTrue(dave[0]["blocks"])
        state = classes["runtime-state"]
        self.assertTrue(all(not item["blocks"] for item in state))
        self.assertTrue(any("run-markers" in str(item["path"]) for item in state))

    def test_systemctl_sees_the_unit_only_read_only(self):
        for relative in ("alpha.timer", "alpha.service"):
            (self.etc / relative).unlink()
        self.state_file.write_text(json.dumps({"alpha.timer": {"present": True, "active": "active"}}))
        report = self.scan()
        installed = by_class(report)["installed"]
        self.assertTrue(any("list-unit-files" in item["what"] for item in installed))
        self.assertTrue(any("is-active" in item["what"] and "active" in item["what"] for item in installed))
        verbs = [json.loads(line)[1:] for line in self.log.read_text().splitlines()]
        self.assertTrue(verbs)
        for argv in verbs:
            self.assertIn(argv[0], ("list-unit-files", "is-active"), argv)
        self.assertTrue(all(json.loads(line)[0] == "--no-pager" for line in self.log.read_text().splitlines()))

    def test_clear_only_with_attestation(self):
        for relative in ("alpha.timer", "alpha.service"):
            (self.etc / relative).unlink()
        for relative in ("bin/run_alpha_cc.sh", "profiles/alpha_task.md", "profiles/alpha.env.example", "systemd/alpha.timer", "systemd/alpha.service"):
            (self.runtime / relative).unlink()
        report = self.scan()
        self.assertEqual(report["verdict"], "residue")
        self.assertEqual([item["class"] for item in report["items"] if item["blocks"]], ["dave-only"])
        self.assertEqual(self.scan(env_removed_attested=True)["verdict"], "clear")
        self.assertEqual(self.scan(env_override=None)["verdict"], "clear")


class Cli(unittest.TestCase):
    """(::residue-cli)"""

    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="crc-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.repo = self.tmp / "repo"
        shutil.copytree(FIXTURES / "repo", self.repo)

    def run_cli(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out):
            code = residue.main(list(argv))
        return code, out.getvalue()

    def test_exit_codes_and_json(self):
        code, out = self.run_cli("--source", str(self.repo), "--workflow", "alpha")
        self.assertEqual(code, 1)
        self.assertIn("| # | residue | tree | has a check? | who clears it | how |", out)
        code, _ = self.run_cli("--source", str(self.repo), "--workflow", "nope")
        self.assertEqual(code, 2)
        code, out = self.run_cli("--source", str(self.repo), "--workflow", "alpha", "--json")
        self.assertEqual(code, 1)
        parsed = json.loads(out)
        self.assertEqual(parsed["verdict"], "residue")
        self.assertTrue(parsed["items"])

    def test_all_reads_the_registry(self):
        registry = self.repo / "design/retired-workflows.toml"
        registry.write_text('[[retired]]\nid = "alpha"\nunits = ["alpha"]\nowner = "claudius"\nretired_on = "2026-09-15"\nreason = "x"\n'
                            'proposal = "p"\nbranch = "control-room/retire-alpha-x"\npr = ""\nrunners = ["bin/run_alpha_cc.sh"]\n'
                            'profiles = ["profiles/alpha_task.md"]\ncontract = ""\nsuites = []\nenv_override = ""\nrun_markers = []\n'
                            'artifact_retention = { receipts = "keep", notion = "keep", inbox = "keep", note = "" }\n'
                            'residue_cleared_on = ""\nenv_removed_attested = false\n')
        code, out = self.run_cli("--source", str(self.repo), "--all")
        self.assertEqual(code, 1)
        self.assertIn("alpha", out)
        registry.write_text("# empty\n")
        code, out = self.run_cli("--source", str(self.repo), "--all")
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main()
