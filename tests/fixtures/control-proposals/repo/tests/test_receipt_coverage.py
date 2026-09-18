#!/usr/bin/env python3
"""Fixture stand-in for T5.2's receipt-coverage suite: the producer tally and the logical count
pinned as module-level literals, derived the way the real suite derives them — a standing row's
producer is decided by its service's ExecStart basename, never by a list kept here."""
import pathlib
import re
import sys
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
EXEC_START = re.compile(r"^ExecStart=(\S+)", re.MULTILINE)

SELF_RECEIPTING = {"agent_propose.sh": "scheduled", "content_change_dispatch.sh": "dispatch",
                   "receipt_sweep.py": "sweep-self"}
EXPECTED_TALLY = {"scheduled": 2, "sweep": 3, "interaction": 1}
LOGICAL_WORKFLOWS = 5


def standing_rows():
    rows = []
    for line in (ROOT / "config" / "fleet-units.tsv").read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        unit, scope, status, _owner, kind = (c.strip() for c in line.split("\t")[:5])
        if status == "standing":
            rows.append((unit, scope, kind))
    return rows


def producer(unit, scope, kind):
    if kind == "service" and unit.startswith("buzz-agent@"):
        return "interaction"
    unit_dir = ROOT / "systemd" / "user" if scope == "user" else ROOT / "systemd"
    service = unit_dir / f"{unit}.service"
    match = EXEC_START.search(service.read_text()) if service.is_file() else None
    program = pathlib.Path(match.group(1)).name if match else None
    return SELF_RECEIPTING.get(program, "sweep" if kind == "timer" else None)


class Coverage(unittest.TestCase):
    def test_tally(self):
        tally = {}
        for row in standing_rows():
            tally[producer(*row)] = tally.get(producer(*row), 0) + 1
        self.assertEqual(tally, EXPECTED_TALLY)

    def test_logical_workflows(self):
        ids = set()
        for path in sorted((ROOT / "design" / "agents").glob("*.toml")):
            for entry in tomllib.loads(path.read_text())["workflows"]:
                if entry["status"] == "standing":
                    ids.add(entry.get("logical_workflow", entry["unit"]))
        self.assertEqual(len(ids), LOGICAL_WORKFLOWS)


if __name__ == "__main__":
    sys.exit(unittest.main())
