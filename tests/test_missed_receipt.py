#!/usr/bin/env python3
"""bin/missed_receipt.py: a stamp read-back is not a fire, and a fire is owed a receipt only
once the sweep has looked after it."""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import missed_receipt as mr  # noqa: E402

UTC = dt.timezone.utc


def at(text: str) -> dt.datetime:
    return dt.datetime.fromisoformat(text.replace("Z", "+00:00"))


class FiredAt(unittest.TestCase):  # (::missed-receipt-fired-at)
    def test_a_trigger_after_activation_is_a_fire(self):
        self.assertEqual(mr.fired_at("2026-09-17T09:00:33Z", "2026-09-16T17:00:26Z"), "2026-09-17T09:00:33Z")

    def test_a_trigger_at_or_before_activation_is_the_stamp_read_back(self):
        self.assertIsNone(mr.fired_at("2026-09-16T17:00:25Z", "2026-09-16T17:00:26Z"))
        self.assertIsNone(mr.fired_at("2026-09-16T17:00:26Z", "2026-09-16T17:00:26Z"))

    def test_no_activation_keeps_the_trigger_and_no_trigger_is_none(self):
        self.assertEqual(mr.fired_at("2026-09-17T09:00:33Z", None), "2026-09-17T09:00:33Z")
        self.assertIsNone(mr.fired_at(None, "2026-09-16T17:00:26Z"))
        self.assertIsNone(mr.fired_at("", ""))


class SweepStartedAt(unittest.TestCase):  # (::missed-receipt-sweep-started)
    def test_reads_the_sweep_workflows_last_run(self):
        workflows = [{"id": "qmd-refresh", "lastRun": {"startedAt": "2026-09-17T09:05:40Z"}},
                     {"id": mr.SWEEP_WORKFLOW_ID, "lastRun": {"startedAt": "2026-09-17T03:50:03Z"}}]
        self.assertEqual(mr.sweep_started_at(workflows), at("2026-09-17T03:50:03Z"))

    def test_no_sweep_row_or_no_run_is_none(self):
        self.assertIsNone(mr.sweep_started_at([{"id": "qmd-refresh", "lastRun": None}]))
        self.assertIsNone(mr.sweep_started_at([{"id": mr.SWEEP_WORKFLOW_ID, "lastRun": None}]))


class MissedFire(unittest.TestCase):  # (::missed-receipt-missed-fire)
    FIRED = at("2026-09-17T04:22:08Z")

    def test_unjudged_until_the_sweep_has_looked_after_the_grace(self):
        self.assertFalse(mr.missed_fire(self.FIRED, None, None, 900))
        self.assertFalse(mr.missed_fire(self.FIRED, None, at("2026-09-17T03:50:03Z"), 900))
        self.assertFalse(mr.missed_fire(self.FIRED, None, at("2026-09-17T04:30:00Z"), 900))

    def test_missed_once_swept_with_no_receipt_after_the_fire(self):
        swept = at("2026-09-18T03:50:03Z")
        self.assertTrue(mr.missed_fire(self.FIRED, None, swept, 900))
        self.assertTrue(mr.missed_fire(self.FIRED, at("2026-09-16T04:22:08Z"), swept, 900))
        self.assertFalse(mr.missed_fire(self.FIRED, at("2026-09-17T04:22:09Z"), swept, 900))
        self.assertFalse(mr.missed_fire(self.FIRED, at("2026-09-17T04:10:00Z"), swept, 900))

    def test_no_fire_is_never_missed(self):
        self.assertFalse(mr.missed_fire(None, None, at("2026-09-18T03:50:03Z"), 900))


if __name__ == "__main__":
    unittest.main()
