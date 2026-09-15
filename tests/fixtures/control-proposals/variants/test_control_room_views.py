#!/usr/bin/env python3
"""Fixture stand-in for T5.3's views suite, no-constants variant: the count is computed and
compared against a joined table, so a retirement has nothing to decrement and pinned-tests
is the only thing that catches the coupling."""
import pathlib
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _entries():
    rows = []
    for path in sorted((ROOT / "design" / "agents").glob("*.toml")):
        rows.extend(tomllib.loads(path.read_text())["workflows"])
    return rows


class Counts(unittest.TestCase):
    def test_alpha_is_listed(self):
        self.assertIn("alpha", {r["unit"] for r in _entries()})


if __name__ == "__main__":
    sys.exit(unittest.main())
