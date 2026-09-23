#!/usr/bin/env python3
"""bin/turn_rate.py: turns per agent in a window, split by what woke them.

Synthetic receipts under a temp root; the clock is pinned with --now. Anchors are the `::`
comments; tests/test_turn_rate.sh is the gate entry point.
"""
from __future__ import annotations

import json
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
TOOL = ROOT / "bin" / "turn_rate.py"
NOW = "2026-09-19T15:00:00Z"


def receipt(run_id: str, ended: str, origin: str | None, handoff: dict | None = None) -> dict:
    data = {"schema_version": 1, "workflow_id": "buzz-agent@marcus", "run_id": run_id,
            "started_at": ended, "ended_at": ended, "terminal": {"outcome": "artifact", "reason": None},
            "handoff": handoff}
    if origin:
        data["origin"] = origin
    return data


class TurnRateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="turn-rate-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)

    def write(self, agent: str, *receipts: dict) -> None:
        directory = self.tmp / f"buzz-agent@{agent}"
        directory.mkdir(parents=True, exist_ok=True)
        for data in receipts:
            (directory / f"{data['run_id']}.json").write_text(json.dumps(data))

    def run_tool(self, *agents: str, window: int = 60) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(TOOL), "--receipts", str(self.tmp), "--window-min", str(window),
                               "--now", NOW, *agents], capture_output=True, text=True)

    def test_counts_by_origin_inside_the_window(self):
        # (::turn-rate-by-origin) — relay turns count in total only; scheduled ones are the
        # alarm column and are named by run id; a receipt older than the window is not a turn
        # in it.
        self.write("marcus",
                   receipt("r1", "2026-09-19T14:10:00Z", "relay", {"actor": "Dave_VPC", "event": "e0" * 32, "recipient": "marcus"}),
                   receipt("s1", "2026-09-19T14:20:00Z", "scheduled"),
                   receipt("s2", "2026-09-19T14:50:00Z", "scheduled"),
                   receipt("old", "2026-09-19T13:30:00Z", "scheduled"))
        done = self.run_tool("marcus")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "marcus\t3\t2\t0\ts1,s2\t-\n")

    def test_receipts_before_the_origin_field(self):
        # (::turn-rate-legacy-origin) — a receipt with no origin key is relay when its handoff
        # names an event and unknown otherwise; neither is ever counted as self-scheduled.
        self.write("claudius",
                   receipt("h1", "2026-09-19T14:30:00Z", None, {"actor": "Dave_VPC", "event": "e0" * 32, "recipient": "claudius"}),
                   receipt("n1", "2026-09-19T14:40:00Z", None, None))
        done = self.run_tool("claudius")
        self.assertEqual(done.stdout, "claudius\t2\t0\t1\t-\t-\n")

    def test_missing_agent_and_broken_file(self):
        # (::turn-rate-never-fails) — an agent with no receipts is a line of zeros; a file
        # that does not parse is skipped, named on stderr, and the other agents still read.
        self.write("trajan", receipt("t1", "2026-09-19T14:59:00Z", "scheduled"))
        (self.tmp / "buzz-agent@trajan" / "broken.json").write_text("{not json")
        done = self.run_tool("aurelian", "trajan")
        self.assertEqual(done.returncode, 0)
        self.assertEqual(done.stdout, "aurelian\t0\t0\t0\t-\t-\ntrajan\t1\t1\t0\tt1\t-\n")
        self.assertIn("broken.json", done.stderr)

    def test_one_event_answered_twice(self):
        # (::turn-rate-doubled) — two receipts naming one relay event are one mention answered
        # twice, named by event prefix and count; two events once each, turns with no event,
        # two receipts of one turn (same started_at), and a self-scheduled fire whose handoff
        # still names the last inbound event, are not.
        mention = {"actor": "Dave_VPC", "event": "ab" * 32, "recipient": "trajan"}
        other = {"actor": "Dave_VPC", "event": "cd" * 32, "recipient": "trajan"}
        self.write("trajan",
                   receipt("d1", "2026-09-19T14:10:00Z", "relay", mention),
                   receipt("d2", "2026-09-19T14:11:00Z", "relay", mention),
                   receipt("o1", "2026-09-19T14:20:00Z", "relay", other),
                   dict(receipt("o2", "2026-09-19T14:25:00Z", "relay", other), started_at="2026-09-19T14:20:00Z"),
                   receipt("s1", "2026-09-19T14:30:00Z", "scheduled", other),
                   receipt("s2", "2026-09-19T14:40:00Z", "scheduled"))
        done = self.run_tool("trajan")
        self.assertEqual(done.stdout, f"trajan\t6\t2\t0\ts1,s2\t{'ab' * 6}x2\n")


if __name__ == "__main__":
    unittest.main()
