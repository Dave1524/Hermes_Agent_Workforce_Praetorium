#!/usr/bin/env python3
"""Fixture stand-in for T5.3's views suite: counts pinned as module-level literals."""
import pathlib
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
STANDING_ENTRIES = 5
LOGICAL_WORKFLOWS = 4
RETRY_BUDGET = 3  # unrelated literal; must survive a retirement untouched


def _entries():
    rows = []
    for path in sorted((ROOT / "design" / "agents").glob("*.toml")):
        rows.extend(tomllib.loads(path.read_text())["workflows"])
    return rows


class Counts(unittest.TestCase):
    def test_standing_scheduled_entries(self):
        rows = [r for r in _entries() if r["surface"] == "scheduled" and r["status"] == "standing"]
        self.assertEqual(len(rows), STANDING_ENTRIES)

    def test_logical_workflows(self):
        rows = [r for r in _entries() if r["surface"] == "scheduled"]
        self.assertEqual(len({r.get("logical_workflow", r["unit"]) for r in rows}), LOGICAL_WORKFLOWS)


if __name__ == "__main__":
    sys.exit(unittest.main())
