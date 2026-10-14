#!/usr/bin/env python3
"""Incident debounce (criterion 15): open after a sustained red, recover after a sustained green.

The pure half drives bin/incident_state.py sweep by sweep through a table of verdict sequences
and replays bin/incident_notify.py's send rule over it; the CLI half flaps a real receipt pair
through the notifier with the fake transport and counts the sends. A flapping workflow pages at
most once and never sends an [incident]/[recovered] pair per flip.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import shutil
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_incident_notify import FIXTURES, NotifierCase  # noqa: E402


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = load("incident_state")
UTC = dt.timezone.utc
T0 = dt.datetime(2026, 10, 14, 3, 0, tzinfo=UTC)
KEY = "failed-assertion:board-reactor"
DEFAULT = st.Debounce(open_after=900, recover_after=900)


def red(minute: int) -> dict:
    return {"key": KEY, "class": "failed-assertion", "workflow_id": "board-reactor", "run_id": None,
            "observed_at": st.iso_utc(T0 + dt.timedelta(minutes=minute))}


def replay(sequence: list[tuple[int, bool]], debounce: st.Debounce = DEFAULT) -> list[tuple[int, str]]:
    """Each (minute, is_red) is one sweep; returns the (minute, subject) the notifier would send."""
    state, sends = st.empty(), []
    for minute, is_red in sequence:
        now = T0 + dt.timedelta(minutes=minute)
        st.reconcile(state, [red(minute)] if is_red else [], now, debounce=debounce)
        for entry in state["incidents"].values():
            if entry["resolved_at"] is None and entry["notified_at"] is None and st.due_to_open(entry, now, debounce):
                entry["notified_at"] = st.iso_utc(now)
                sends.append((minute, "incident"))
            if entry["resolved_at"] and entry["notified_at"] and not entry["recovery_notified_at"]:
                entry["recovery_notified_at"] = st.iso_utc(now)
                sends.append((minute, "recovered"))
    return sends


def every(step: int, until: int, pattern) -> list[tuple[int, bool]]:
    return [(m, pattern(i)) for i, m in enumerate(range(0, until + 1, step))]


class Table(unittest.TestCase):
    def test_sequences(self):
        # (::incident-debounce-table)
        long = st.Debounce(open_after=3600, recover_after=3600)
        cases = {
            "one red blip is silent": ([(0, True), (5, False), (10, False), (15, False)], DEFAULT, []),
            "two reds then green is silent": ([(0, True), (5, True), (10, False), (25, False)], DEFAULT, []),
            "third consecutive red opens": ([(0, True), (1, True), (2, True)], DEFAULT, [(2, "incident")]),
            "fifteen minutes red opens on time": ([(0, True), (15, True)], DEFAULT, [(15, "incident")]),
            "fourteen minutes red stays quiet": ([(0, True), (14, False)], long, []),
            "three greens recover": ([(0, True), (1, True), (2, True), (3, False), (4, False), (5, False)],
                                     long, [(2, "incident"), (5, "recovered")]),
            "fifteen minutes green recovers": ([(0, True), (1, True), (2, True), (3, False), (18, False)],
                                               DEFAULT, [(2, "incident"), (18, "recovered")]),
            "a green blip inside the hold does not recover": (
                [(0, True), (1, True), (2, True), (3, False), (4, True), (5, False), (6, True)],
                long, [(2, "incident")]),
            "zero windows send at once": ([(0, True), (5, False)], st.Debounce(0, 0),
                                          [(0, "incident"), (5, "recovered")]),
        }
        for name, (sequence, debounce, want) in cases.items():
            with self.subTest(name):
                self.assertEqual(replay(sequence, debounce), want)

    def test_flapping_pages_at_most_once(self):
        # (::incident-debounce-flap) — red/green each 5-min sweep for two hours: a restart storm
        sends = replay(every(5, 120, lambda i: i % 2 == 0))
        self.assertEqual([s for _, s in sends], ["incident"], sends)

    def test_flap_then_steady_green_recovers_once(self):
        # (::incident-debounce-flap)
        sequence = every(5, 60, lambda i: i % 2 == 0) + [(m, False) for m in range(65, 125, 5)]
        self.assertEqual([s for _, s in replay(sequence)], ["incident", "recovered"])

    def test_open_window_is_kept_across_a_flap(self):
        # (::incident-debounce-table) — first_seen survives a green sweep inside the hold
        state = st.empty()
        st.reconcile(state, [red(0)], T0, debounce=DEFAULT)
        st.reconcile(state, [], T0 + dt.timedelta(minutes=5), debounce=DEFAULT)
        st.reconcile(state, [red(10)], T0 + dt.timedelta(minutes=10), debounce=DEFAULT)
        entry = state["incidents"][KEY]
        self.assertEqual(entry["first_seen"], st.iso_utc(T0))
        self.assertIsNone(entry["resolved_at"])
        self.assertTrue(st.due_to_open(entry, T0 + dt.timedelta(minutes=15), DEFAULT))

    def test_legacy_entries_without_streaks_load(self):
        # (::incident-debounce-table) — a state file written before the debounce has no streak fields
        state = st.empty()
        st.reconcile(state, [red(0)], T0)
        for field in ("red_streak", "green_streak", "green_since"):
            state["incidents"][KEY].pop(field, None)
        st.reconcile(state, [red(5)], T0 + dt.timedelta(minutes=5), debounce=DEFAULT)
        self.assertEqual(state["incidents"][KEY]["red_streak"], 1)


class Cli(NotifierCase):
    debounce_env = {"INCIDENT_OPEN_AFTER": "900", "INCIDENT_RECOVER_AFTER": "900"}

    def flip(self, is_red: bool) -> None:
        recovered = self.receipts / "knowledge-digest" / "synthetic-recovered.json"
        if is_red:
            recovered.unlink(missing_ok=True)
        else:
            shutil.copy(FIXTURES / "receipts" / "knowledge-digest" / "synthetic-recovered.json", recovered)

    def test_cli_flap_pages_once_and_recovers_once(self):
        # (::incident-debounce-cli)
        self.receipt("synthetic-failed.json")
        start = dt.datetime(2026, 9, 14, 9, 10, tzinfo=UTC)
        for i in range(12):
            self.flip(i % 2 == 0)
            self.sweep(now=st.iso_utc(start + dt.timedelta(minutes=5 * i)))
        self.flip(False)
        for i in range(12, 16):
            self.sweep(now=st.iso_utc(start + dt.timedelta(minutes=5 * i)))
        subjects = [c.split("subject=")[1].split(" ")[0] for c in self.invocations() if "digest]" not in c]
        self.assertEqual(subjects, ["[incident]", "[recovered]"], self.invocations())

    def test_cli_defaults_hold_the_first_sweep(self):
        # (::incident-debounce-cli) — a fresh red seen once, minutes after the run, sends nothing yet
        self.receipt("synthetic-failed.json")
        self.sweep(now="2026-09-14T03:05:00Z")
        self.assertEqual(self.invocations(), [])
        entry = json.loads((self.state_dir / "state.json").read_text())["incidents"]["failed-assertion:knowledge-digest"]
        self.assertIsNone(entry["notified_at"])
        self.sweep(now="2026-09-14T03:20:00Z")
        self.assertEqual(len(self.invocations()), 1)


if __name__ == "__main__":
    unittest.main()
