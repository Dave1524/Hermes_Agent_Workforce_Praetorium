#!/usr/bin/env python3
"""Fixture tests for bin/control_room_cadence.py — timer cadence, freshness, UTC timestamps."""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from control_room_fixture import ROOT, FakeCalendar  # noqa: E402

import control_room_cadence as cadence  # noqa: E402


class CadenceFromTimerFile(unittest.TestCase):  # (::cadence-from-timer-file)
    def test_knowledge_digest_is_weekly_via_calendar_runner(self):
        result = cadence.cadence_for(ROOT, "knowledge-digest", "system", runner=FakeCalendar())
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["seconds"], 604800)
        self.assertEqual(result["source"], "OnCalendar")
        self.assertEqual(result["spec"], "Sun 09:00")
        self.assertIs(result["persistent"], True)
        self.assertEqual(result["randomizedDelaySec"], 300)
        self.assertIsNone(result["error"])

    def test_qmd_refresh_is_a_monotonic_span_without_the_runner(self):
        def refuse(spec):
            raise AssertionError(f"runner must not be called for a monotonic timer ({spec})")
        result = cadence.cadence_for(ROOT, "qmd-refresh.timer", "system", runner=refuse)
        self.assertEqual(result["status"], "measured")
        self.assertEqual(result["seconds"], 1800)
        self.assertEqual(result["source"], "OnUnitActiveSec")
        self.assertEqual(result["spec"], "30min")

    def test_user_scope_reads_systemd_user(self):
        result = cadence.cadence_for(ROOT, "buzz-pr-watch", "user", runner=FakeCalendar())
        self.assertEqual(result["seconds"], 86400)
        self.assertEqual(result["randomizedDelaySec"], 1200)

    def test_span_parser(self):
        cases = [("20m", 1200), ("120", 120), ("5min", 300), ("90s", 90), ("2h", 7200),
                 ("1d", 86400), ("1h 30min", 5400), ("", None), ("soon", None)]
        for raw, expected in cases:
            with self.subTest(raw=raw):
                self.assertEqual(cadence.parse_span(raw), expected)


class CadenceUnavailableNamed(unittest.TestCase):  # (::cadence-unavailable-named)
    def test_missing_timer_file_is_unavailable_with_error(self):
        result = cadence.cadence_for(ROOT, "no-such-unit", "system", runner=FakeCalendar())
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["seconds"])
        self.assertIn("no-such-unit.timer", result["error"])

    def test_unmapped_spec_is_unavailable_never_zero(self):
        def unmapped(spec):
            raise ValueError(f"no entry for {spec}")
        result = cadence.cadence_for(ROOT, "knowledge-digest", "system", runner=unmapped)
        self.assertEqual(result["status"], "unavailable")
        self.assertIsNone(result["seconds"])
        self.assertIn("Sun 09:00", result["error"])
        self.assertNotEqual(result["seconds"], 0)


class FreshnessTwoCadences(unittest.TestCase):  # (::freshness-two-cadences)
    WEEKLY = {"status": "measured", "seconds": 604800}

    def test_thirteen_days_on_a_weekly_cadence_is_current(self):
        self.assertEqual(cadence.freshness(13 * 86400, self.WEEKLY), "current")

    def test_fifteen_days_on_a_weekly_cadence_is_stale(self):
        self.assertEqual(cadence.freshness(15 * 86400, self.WEEKLY), "stale")

    def test_unavailable_cadence_or_age_is_unknown(self):
        self.assertEqual(cadence.freshness(15 * 86400, {"status": "unavailable", "seconds": None}), "unknown")
        self.assertEqual(cadence.freshness(None, self.WEEKLY), "unknown")


class SystemdTimestampUtc(unittest.TestCase):  # (::systemd-timestamp-utc)
    def test_utc_string_parses_to_aware_datetime(self):
        parsed = cadence.parse_systemd_timestamp("Mon 2026-09-14 07:10:10 UTC")
        self.assertEqual(parsed, dt.datetime(2026, 9, 14, 7, 10, 10, tzinfo=dt.timezone.utc))

    def test_empty_na_and_local_zone_are_none(self):
        for raw in ("", "n/a", "Mon 2026-09-14 09:10:10 CEST", None):
            with self.subTest(raw=raw):
                self.assertIsNone(cadence.parse_systemd_timestamp(raw))

    def test_default_runner_output_parses_utc_lines(self):
        output = (
            "  Original form: Sun 09:00\nNormalized form: Sun *-*-* 09:00:00\n"
            "    Next elapse: Sun 2026-09-20 09:00:00 CEST\n       (in UTC): Sun 2026-09-20 07:00:00 UTC\n"
            "       From now: 5 days left\n   Iteration #2: Sun 2026-09-27 09:00:00 CEST\n"
            "       (in UTC): Sun 2026-09-27 07:00:00 UTC\n       From now: 1 week 5 days left\n"
        )
        elapses = cadence.parse_calendar_output(output)
        self.assertEqual(len(elapses), 2)
        self.assertEqual((elapses[1] - elapses[0]).total_seconds(), 604800)

    def test_default_runner_output_without_utc_lines(self):
        output = ("    Next elapse: Sun 2026-09-20 09:00:00 UTC\n   Iteration #2: Sun 2026-09-27 09:00:00 UTC\n")
        elapses = cadence.parse_calendar_output(output)
        self.assertEqual((elapses[1] - elapses[0]).total_seconds(), 604800)


if __name__ == "__main__":
    unittest.main()
