"""The production-first rule: one canonical block, copied by a script, drift-checked.

Fixture homes only; the live box files are checked by the .sh wrapper.
"""
from __future__ import annotations

import contextlib
import io
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "bin"))
import production_first_sync as pf  # noqa: E402

GOOD_PLAN = "## Design research\n## Decisions for Dave\nProduction first\n"
GOOD_SHIP = "Decisions for Dave\nProduction first\n"


class Fixture(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.home = pathlib.Path(self._tmp.name)
        (self.home / ".claude" / "commands").mkdir(parents=True)
        (self.home / ".codex").mkdir()

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            rc = pf.main([*argv, "--home", str(self.home)] if argv[0] != "render" else list(argv))
        return rc, out.getvalue(), err.getvalue()

    def commands(self, plan: str = GOOD_PLAN, ship: str = GOOD_SHIP) -> None:
        (self.home / ".claude" / "commands" / "plan-feature.md").write_text(plan)
        (self.home / ".claude" / "commands" / "ship.md").write_text(ship)


class Block(Fixture):  # (::production-first-block)
    def test_the_canonical_block_carries_every_clause(self) -> None:
        block = pf.canonical()
        for clause in ("cheaper, quicker or smaller", "Research before designing", "## Design research",
                       "the trigger, the", "## Decisions for Dave", "same architecture"):
            self.assertIn(clause, " ".join(block.split()))
        self.assertEqual(block.count(pf.START), 1)
        self.assertEqual(block.count(pf.END), 1)

    def test_a_rule_file_without_a_marker_pair_is_refused(self) -> None:
        bad = self.home / "rule.md"
        bad.write_text("no markers here\n")
        with self.assertRaises(SystemExit):
            pf.canonical(bad)


class Apply(Fixture):  # (::production-first-apply)
    def test_appends_keeping_existing_content_and_is_idempotent(self) -> None:
        target = self.home / ".claude" / "CLAUDE.md"
        target.write_text("# Mine\n\nKeep this.\n")
        self.assertEqual(self.run_cli("apply", "--create")[0], 0)
        first = target.read_text()
        self.assertTrue(first.startswith("# Mine\n\nKeep this.\n"))
        self.assertIn(pf.START, first)
        self.run_cli("apply", "--create")
        self.assertEqual(target.read_text(), first)

    def test_replaces_a_stale_block_and_leaves_the_text_around_it(self) -> None:
        target = self.home / ".codex" / "AGENTS.md"
        target.write_text(f"before\n\n{pf.START}\nold rule\n{pf.END}\n\nafter\n")
        self.run_cli("apply", "--create")
        text = target.read_text()
        self.assertNotIn("old rule", text)
        self.assertTrue(text.startswith("before\n\n") and text.rstrip().endswith("after"))

    def test_refuses_a_missing_target_unless_asked_to_create_it(self) -> None:
        rc, _, err = self.run_cli("apply")
        self.assertEqual(rc, 1)
        self.assertIn("--create", err)
        self.assertFalse((self.home / ".claude" / "CLAUDE.md").exists())
        self.assertEqual(self.run_cli("apply", "--create")[0], 0)
        self.assertTrue((self.home / ".claude" / "CLAUDE.md").exists())
        self.assertTrue((self.home / ".codex" / "AGENTS.md").exists())


class Check(Fixture):  # (::production-first-check)
    def installed(self) -> None:
        self.run_cli("apply", "--create")
        self.commands()

    def test_passes_when_every_copy_and_command_conforms(self) -> None:
        self.installed()
        self.assertEqual(self.run_cli("check")[0], 0)

    def test_names_a_drifted_copy_a_missing_block_and_a_missing_file(self) -> None:
        self.installed()
        claude = self.home / ".claude" / "CLAUDE.md"
        claude.write_text(claude.read_text().replace("Research before designing", "Research sometimes"))
        (self.home / ".codex" / "AGENTS.md").write_text("no block\n")
        rc, _, err = self.run_cli("check")
        self.assertEqual(rc, 1)
        self.assertIn(f"drifted from docs/production-first.md: {claude}", err)
        self.assertIn("no marked block", err)
        (self.home / ".codex" / "AGENTS.md").unlink()
        self.assertIn("missing:", self.run_cli("check")[2])

    def test_names_a_command_that_lost_a_required_section(self) -> None:
        self.installed()
        self.commands(plan="## Design research\nProduction first\n")
        rc, _, err = self.run_cli("check")
        self.assertEqual(rc, 1)
        self.assertIn("plan-feature.md: lacks '## Decisions for Dave'", err)
        self.assertNotIn("ship.md", err)


if __name__ == "__main__":
    unittest.main()
