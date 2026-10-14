#!/usr/bin/env python3
"""config/polkit/50-board-reactor.rules: the reactor may start and stop its own card units only."""
from __future__ import annotations

import importlib.util
import pathlib
import re
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RULES = (ROOT / "config" / "polkit" / "50-board-reactor.rules").read_text()
spec = importlib.util.spec_from_file_location("board", ROOT / "bin" / "board.py")
board = importlib.util.module_from_spec(spec)
spec.loader.exec_module(board)


def unit_pattern() -> re.Pattern[str]:
    found = re.search(r"/(\^board-.*?\$)/\.test\(unit\)", RULES)
    assert found, "no unit pattern in the rule"
    return re.compile(found.group(1))


class Rule(unittest.TestCase):  # (::board-polkit-scope)
    def test_the_slug_part_is_board_py_s_card_grammar(self):
        self.assertIn(board.SLUG.pattern.strip("^$"), unit_pattern().pattern)

    def test_only_card_units_match(self):
        pattern = unit_pattern()
        for unit in ("board-brief@alpha.service", "board-work@a-1.service"):
            with self.subTest(unit):
                self.assertTrue(pattern.match(unit))
        for unit in ("board-reactor.service", "board-brief@.service", "board-brief@../x.service",
                     "agent-proposal.service", "board-work@Alpha.service", "board-brief@a.service.d"):
            with self.subTest(unit):
                self.assertFalse(pattern.match(unit))

    def test_only_start_and_stop_for_dave(self):
        self.assertIn('subject.user != "dave"', RULES)
        verbs = set(re.findall(r'verb == "(\w+)"', RULES))
        self.assertEqual(verbs, {"start", "stop"})
        self.assertIn('"org.freedesktop.systemd1.manage-units"', RULES)

    def test_the_reactor_runs_as_dave_and_its_units_exist(self):
        for name in ("board-reactor.service", "board-brief@.service", "board-work@.service"):
            with self.subTest(name):
                self.assertIn("User=dave", (ROOT / "systemd" / name).read_text())


if __name__ == "__main__":
    unittest.main()
