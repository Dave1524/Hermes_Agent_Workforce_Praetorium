#!/usr/bin/env python3
"""bin/workflow_requires.py: `requires` resolves statically, agrees across a fold, mirrors the
unit files, and `check` refuses a run whose requirement is down (T5.3f).

Static rules run over the REAL tree and over mktemp fixtures with a known offender each, so a
rule that stops firing is red rather than quiet. `check` is driven as a subprocess with a fake
`systemctl` on PATH — never the live bus. Anchors are the `::` comments;
tests/test_workflow_requires.sh is the gate entry point.
"""

from __future__ import annotations

import os
import pathlib
import subprocess
import sys
import tempfile
import textwrap
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
import workflow_requires as wr  # noqa: E402

SCRIPT = ROOT / "bin" / "workflow_requires.py"

FAKE_SYSTEMCTL = """#!/usr/bin/env bash
# Answers `systemctl [--user] show <unit> --property=ActiveState` from FAKE_STATES ("unit=state,…").
# A unit named in FAKE_DOWN_BUS fails as an unreachable bus does.
unit=""
for a in "$@"; do case "$a" in --*) ;; show) ;; *) unit=$a ;; esac; done
if [ "${FAKE_DOWN_BUS:-}" = "$unit" ]; then
  echo "Failed to connect to user scope bus via local transport: No medium found" >&2; exit 1
fi
IFS=, read -ra pairs <<< "${FAKE_STATES:-}"
for pair in "${pairs[@]}"; do
  case "$pair" in "$unit="*) echo "ActiveState=${pair#*=}"; exit 0 ;; esac
done
echo "ActiveState=inactive"
"""


def fixture(manifest: str, units: dict[str, str] | None = None) -> pathlib.Path:
    root = pathlib.Path(tempfile.mkdtemp(prefix="wr-"))
    (root / "design" / "agents").mkdir(parents=True)
    (root / "design" / "agents" / "fx.toml").write_text(textwrap.dedent(manifest))
    for relative, body in (units or {}).items():
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(textwrap.dedent(body))
    return root


HEALTHY = """
    name = "augustus"
    [[workflows]]
    unit = "augustus-content"
    logical_workflow = "augustus-content"
    surface = "buzz_dispatch"
    runner = "bin/agent_propose.sh -> bin/run_content_via_buzz.sh"
    status = "standing"
    requires = ["buzz-agent@augustus", "user/buzz-notion-broker"]
    [[workflows]]
    unit = "content-change-dispatch"
    logical_workflow = "augustus-content"
    surface = "buzz_dispatch"
    runner = "bin/content_change_dispatch.sh"
    status = "standing"
    requires = ["buzz-agent@augustus", "user/buzz-notion-broker"]
    [[workflows]]
    unit = "local-tier-eval"
    surface = "platform"
    status = "standing"
    requires = ["system/ollama.service"]
    [[workflows]]
    unit = "buzz-agent@augustus"
    surface = "interactive"
    scope = "user"
    kind = "service"
    status = "standing"
"""
HEALTHY_UNITS = {
    "systemd/local-tier-eval.service": "[Unit]\nWants=ollama.service\n",
    "systemd/augustus-content.service": "[Unit]\nWants=network-online.target\n",
    "systemd/content-change-dispatch.service": "[Unit]\n",
    "systemd/user/buzz-notion-broker.service": "[Unit]\n",
    "systemd/user/buzz-agent@.service": "[Unit]\n",
}


class Resolves(unittest.TestCase):  # (::workflow-requires-resolves)
    def test_every_live_entry_resolves_statically(self):
        entries = wr.load_entries(ROOT)
        declared = [(e["unit"], e["requires"]) for e in entries if e.get("requires")]
        self.assertGreaterEqual(len(declared), 3, "the brief declares three entries")
        for entry in entries:
            for requirement in wr.requirements_for(entry, entries, ROOT):
                self.assertIn(requirement.scope, {"system", "user"})
        self.assertEqual(wr.audit(ROOT), [])

    def test_shapes(self):
        root = fixture(HEALTHY, HEALTHY_UNITS)
        entries = wr.load_entries(root)
        by_unit = {e["unit"]: e for e in entries}
        content = wr.requirements_for(by_unit["augustus-content"], entries, root)
        self.assertEqual([(r.unit, r.scope, r.workflow) for r in content],
                         [("buzz-agent@augustus", "user", "buzz-agent@augustus"), ("buzz-notion-broker", "user", None)])
        self.assertEqual([r.service_name for r in content], ["buzz-agent@augustus.service", "buzz-notion-broker.service"])
        eval_reqs = wr.requirements_for(by_unit["local-tier-eval"], entries, root)
        self.assertEqual([(r.unit, r.scope, r.workflow, r.service_name) for r in eval_reqs],
                         [("ollama.service", "system", None, "ollama.service")])
        self.assertEqual(wr.requirements_for(by_unit["buzz-agent@augustus"], entries, root), [])

    def test_bare_name_outside_the_manifests_refuses(self):
        root = fixture(HEALTHY.replace('"system/ollama.service"', '"ollama.service"'), HEALTHY_UNITS)
        entries = wr.load_entries(root)
        entry = next(e for e in entries if e["unit"] == "local-tier-eval")
        with self.assertRaisesRegex(ValueError, "ollama.service"):
            wr.requirements_for(entry, entries, root)
        self.assertTrue(any("ollama.service" in problem for problem in wr.audit(root)))

    def test_scoped_name_must_be_a_repo_unit_or_external(self):
        root = fixture(HEALTHY.replace('"system/ollama.service"', '"system/nothing-here"'), HEALTHY_UNITS)
        self.assertTrue(any("nothing-here" in problem for problem in wr.audit(root)))
        root = fixture(HEALTHY.replace('"system/ollama.service"', '"host/ollama.service"'), HEALTHY_UNITS)
        self.assertTrue(any("host/ollama.service" in problem for problem in wr.audit(root)))

    def test_external_units_are_named(self):
        self.assertIn("system/ollama.service", wr.EXTERNAL_UNITS)
        for key, description in wr.EXTERNAL_UNITS.items():
            self.assertRegex(key, r"^(system|user)/")
            self.assertTrue(description)


class FoldAgrees(unittest.TestCase):  # (::workflow-requires-fold-agrees)
    def test_live_folds_agree(self):
        self.assertEqual([p for p in wr.audit(ROOT) if "fold" in p], [])

    def test_disagreeing_fold_is_named(self):
        root = fixture(HEALTHY.replace(
            'runner = "bin/content_change_dispatch.sh"\n    status = "standing"\n    requires = ["buzz-agent@augustus", "user/buzz-notion-broker"]',
            'runner = "bin/content_change_dispatch.sh"\n    status = "standing"\n    requires = ["buzz-agent@augustus"]'), HEALTHY_UNITS)
        problems = [p for p in wr.audit(root) if "fold" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("content-change-dispatch", problems[0])


class UnitFile(unittest.TestCase):  # (::workflow-requires-unit-file)
    def test_live_unit_files_carry_same_scope_requirements(self):
        self.assertEqual([p for p in wr.audit(ROOT) if "unit file" in p], [])

    def test_same_scope_requirement_missing_from_the_unit_file_is_named(self):
        units = dict(HEALTHY_UNITS, **{"systemd/local-tier-eval.service": "[Unit]\nWants=network-online.target\n"})
        problems = [p for p in wr.audit(fixture(HEALTHY, units)) if "unit file" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("ollama.service", problems[0])

    def test_cross_manager_requirement_is_exempt(self):
        problems = [p for p in wr.audit(fixture(HEALTHY, HEALTHY_UNITS)) if "buzz-notion-broker" in p]
        self.assertEqual(problems, [])

    def test_hard_dependency_in_a_unit_file_must_be_declared(self):
        units = dict(HEALTHY_UNITS, **{"systemd/augustus-content.service": "[Unit]\nRequires=qmd-mcp.service\n",
                                       "systemd/qmd-mcp.service": "[Unit]\n"})
        problems = [p for p in wr.audit(fixture(HEALTHY, units)) if "qmd-mcp.service" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("augustus-content", problems[0])


class BuzzHandoff(unittest.TestCase):  # (::workflow-requires-buzz-handoff)
    def test_live_handoff_requires_the_owner_runtime(self):
        self.assertEqual([p for p in wr.audit(ROOT) if "run_content_via_buzz" in p], [])
        entries = wr.load_entries(ROOT)
        handoffs = [e for e in entries if "run_content_via_buzz.sh" in str(e.get("runner") or "")]
        self.assertTrue(handoffs)
        for entry in handoffs:
            self.assertIn(f"buzz-agent@{entry['owner']}", entry["requires"])

    def test_handoff_without_the_runtime_is_named(self):
        root = fixture(HEALTHY.replace(
            'runner = "bin/agent_propose.sh -> bin/run_content_via_buzz.sh"\n    status = "standing"\n    requires = ["buzz-agent@augustus", "user/buzz-notion-broker"]',
            'runner = "bin/agent_propose.sh -> bin/run_content_via_buzz.sh"\n    status = "standing"\n    requires = ["user/buzz-notion-broker"]'),
            HEALTHY_UNITS)
        problems = [p for p in wr.audit(root) if "run_content_via_buzz" in p]
        self.assertEqual(len(problems), 1, problems)
        self.assertIn("buzz-agent@augustus", problems[0])


class Check(unittest.TestCase):  # (::workflow-requires-check)
    def setUp(self):
        self.root = fixture(HEALTHY, HEALTHY_UNITS)
        self.bin = self.root / "fakebin"
        self.bin.mkdir()
        systemctl = self.bin / "systemctl"
        systemctl.write_text(FAKE_SYSTEMCTL)
        systemctl.chmod(0o755)

    def check(self, unit: str, states: str = "", down_bus: str = "") -> subprocess.CompletedProcess:
        env = dict(os.environ, PATH=f"{self.bin}:{os.environ['PATH']}", FAKE_STATES=states, FAKE_DOWN_BUS=down_bus)
        return subprocess.run([sys.executable, str(SCRIPT), "check", unit, "--repo-root", str(self.root)],
                              capture_output=True, text=True, env=env)

    def test_active_requirements_pass(self):
        done = self.check("augustus-content", "buzz-agent@augustus.service=active,buzz-notion-broker.service=active")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("requires buzz-agent@augustus: active", done.stdout)
        self.assertIn("requires buzz-notion-broker: active", done.stdout)

    def test_inactive_requirement_refuses_naming_the_first(self):
        done = self.check("augustus-content", "buzz-agent@augustus.service=inactive,buzz-notion-broker.service=active")
        self.assertEqual(done.returncode, 1)
        self.assertEqual(done.stdout.strip().splitlines()[-1], "requires buzz-agent@augustus: inactive")

    def test_no_entry_and_no_requires_pass(self):
        for unit in ("buzz-agent@augustus", "no-such-unit"):
            done = self.check(unit)
            self.assertEqual(done.returncode, 0, done.stderr)

    def test_unreachable_bus_is_unknown_not_refused(self):
        done = self.check("augustus-content", "buzz-notion-broker.service=active", down_bus="buzz-agent@augustus.service")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("requires buzz-agent@augustus: unknown", done.stdout)

    def test_satisfied_is_tri_state(self):
        self.assertIs(wr.satisfied("active"), True)
        self.assertIs(wr.satisfied("activating"), True)
        self.assertIs(wr.satisfied("inactive"), False)
        self.assertIs(wr.satisfied("failed"), False)
        self.assertIsNone(wr.satisfied("unknown"))


if __name__ == "__main__":
    unittest.main()
