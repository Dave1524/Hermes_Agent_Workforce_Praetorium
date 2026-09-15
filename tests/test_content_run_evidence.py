#!/usr/bin/env python3
"""bin/content_run_evidence.py: a run_content_via_buzz.sh attempt log -> the three facts a
receipt needs. Run by tests/test_propose_receipt.sh; anchors are the `::` comments."""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "receipt-wiring"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence = load("content_run_evidence")
EVENT = "e0" * 32
DECLINE_EVENT = "d2" * 32


class ContentRunEvidenceTest(unittest.TestCase):
    def test_from_log(self):  # (::content-evidence-from-log)
        draft = evidence.read(FIX / "attempt-content-draft.log")
        self.assertEqual(draft, {"state_change": "page=0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a from=Picked to=Draft",
                                 "decline_reason": None, "handoff_event": EVENT})

        decline = evidence.read(FIX / "attempt-content-decline.log")
        self.assertEqual(decline, {"state_change": None,
                                   "decline_reason": f"augustus declined: decline_event={DECLINE_EVENT}",
                                   "handoff_event": "e1" * 32})

        neither = evidence.read(FIX / "attempt-content-neither.log")
        self.assertEqual(neither, {"state_change": None, "decline_reason": None, "handoff_event": "e2" * 32})

        self.assertEqual(evidence.read(FIX / "attempt-decline.log"),
                         {"state_change": None, "decline_reason": None, "handoff_event": None})
        self.assertEqual(evidence.read(FIX / "no-such-file.log"),
                         {"state_change": None, "decline_reason": None, "handoff_event": None})

    def test_failed_lines_never_count(self):  # (::content-evidence-from-log)
        text = (FIX / "attempt-content-neither.log").read_text()
        self.assertIn("content-board-transition-produced-draft failed", text)
        self.assertIn("owned-reply-evidences-decline failed", text)
        found = evidence.read(FIX / "attempt-content-neither.log")
        self.assertIsNone(found["state_change"])
        self.assertIsNone(found["decline_reason"])


if __name__ == "__main__":
    unittest.main()
