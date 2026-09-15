#!/usr/bin/env python3
"""Incident state (T5.3c): open → update → close → re-open, atomic saves, the daily digest gate.

Pure reconcile over a dict, plus the two I/O functions. A sweep that cannot see its sources
closes nothing; a corrupt state file is moved aside and named, never silently reset.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import unittest
import zoneinfo

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


st = load("incident_state")
UTC = dt.timezone.utc
T0 = dt.datetime(2026, 9, 14, 3, 5, tzinfo=UTC)


def observed(key="failed-assertion:knowledge-digest", run_id="run-1", observed_at="2026-09-14T03:04:00Z"):
    return {"key": key, "class": key.split(":")[0], "severity": "high", "workflow_id": "knowledge-digest",
            "agent": "claudius", "unit": "knowledge-digest", "issue": "failed checks: artifact-exists",
            "failed_assertion": "artifact-exists", "required_action": "Re-run", "run_id": run_id,
            "evidence": [f"knowledge-digest/{run_id}.json"], "observed_at": observed_at}


class Reconcile(unittest.TestCase):
    def test_open_update_close_reopen(self):
        # (::incident-state-lifecycle)
        state = st.empty()
        t = st.reconcile(state, [observed()], T0)
        self.assertEqual((t["opened"], t["updated"], t["closed"]), (["failed-assertion:knowledge-digest"], [], []))
        entry = state["incidents"]["failed-assertion:knowledge-digest"]
        self.assertEqual(entry["first_seen"], "2026-09-14T03:04:00Z")
        self.assertEqual((entry["observations"], entry["run_ids"], entry["resolved_at"]), (1, ["run-1"], None))
        self.assertIsNone(entry["notified_at"])
        self.assertEqual(entry["send_attempts"], 0)

        t = st.reconcile(state, [observed()], T0 + dt.timedelta(minutes=5))
        self.assertEqual(t["updated"], ["failed-assertion:knowledge-digest"])
        self.assertEqual(entry["observations"], 1)
        self.assertEqual(entry["last_seen"], "2026-09-14T03:10:00Z")

        t = st.reconcile(state, [observed(run_id="run-2", observed_at="2026-09-15T03:04:00Z")], T0 + dt.timedelta(days=1))
        self.assertEqual((entry["observations"], entry["run_id"], entry["run_ids"]), (2, "run-2", ["run-1", "run-2"]))
        self.assertEqual(entry["first_seen"], "2026-09-14T03:04:00Z")

        entry["notified_at"] = "2026-09-14T03:06:00Z"
        t = st.reconcile(state, [], T0 + dt.timedelta(days=2))
        self.assertEqual(t["closed"], ["failed-assertion:knowledge-digest"])
        self.assertEqual(entry["resolved_at"], "2026-09-16T03:05:00Z")

        t = st.reconcile(state, [observed(run_id="run-9", observed_at="2026-09-17T03:04:00Z")], T0 + dt.timedelta(days=3))
        self.assertEqual(t["opened"], ["failed-assertion:knowledge-digest"])
        reopened = state["incidents"]["failed-assertion:knowledge-digest"]
        self.assertEqual(reopened["first_seen"], "2026-09-17T03:04:00Z")
        self.assertIsNone(reopened["notified_at"])
        self.assertIsNone(reopened["resolved_at"])
        self.assertEqual(reopened["observations"], 1)

    def test_degraded_sources_close_nothing_but_still_open_and_update(self):
        # (::incident-state-degraded-closes-nothing)
        state = st.empty()
        st.reconcile(state, [observed()], T0)
        other = observed(key="control-failure:incident-sweep:receipts", run_id=None)
        t = st.reconcile(state, [other], T0 + dt.timedelta(minutes=5), sources_ok=False)
        self.assertEqual(t["closed"], [])
        self.assertEqual(t["opened"], ["control-failure:incident-sweep:receipts"])
        self.assertIsNone(state["incidents"]["failed-assertion:knowledge-digest"]["resolved_at"])
        t = st.reconcile(state, [observed(), other], T0 + dt.timedelta(minutes=10), sources_ok=False)
        self.assertEqual(sorted(t["updated"]), sorted(["failed-assertion:knowledge-digest",
                                                       "control-failure:incident-sweep:receipts"]))

    def test_prune_drops_only_old_resolved_entries(self):
        state = st.empty()
        st.reconcile(state, [observed(), observed(key="incomplete-run:daily-plan")], T0)
        st.reconcile(state, [observed()], T0 + dt.timedelta(hours=1))
        self.assertIsNotNone(state["incidents"]["incomplete-run:daily-plan"]["resolved_at"])
        self.assertEqual(st.prune(state, T0 + dt.timedelta(days=10), 14), [])
        self.assertEqual(st.prune(state, T0 + dt.timedelta(days=15), 14), ["incomplete-run:daily-plan"])
        self.assertEqual(list(state["incidents"]), ["failed-assertion:knowledge-digest"])
        self.assertEqual(st.prune(state, T0 + dt.timedelta(days=400), 14), [])

    def test_open_entries_and_digest_gate(self):
        # (::incident-state-digest-gate)
        ams = zoneinfo.ZoneInfo("Europe/Amsterdam")
        state = st.empty()
        self.assertFalse(st.digest_due(state, dt.datetime(2026, 9, 15, 6, 59, tzinfo=ams), "07:00"))
        self.assertTrue(st.digest_due(state, dt.datetime(2026, 9, 15, 7, 0, tzinfo=ams), "07:00"))
        state["last_digest_at"] = "2026-09-14T05:01:00Z"
        self.assertTrue(st.digest_due(state, dt.datetime(2026, 9, 15, 7, 3, tzinfo=ams), "07:00"))
        state["last_digest_at"] = "2026-09-15T05:03:00Z"
        self.assertFalse(st.digest_due(state, dt.datetime(2026, 9, 15, 7, 7, tzinfo=ams), "07:00"))
        self.assertFalse(st.digest_due(state, dt.datetime(2026, 9, 15, 23, 59, tzinfo=ams), "07:00"))
        self.assertTrue(st.digest_due(state, dt.datetime(2026, 9, 16, 7, 0, tzinfo=ams), "07:00"))
        st.reconcile(state, [observed(), observed(key="incomplete-run:daily-plan")], T0)
        st.reconcile(state, [observed()], T0 + dt.timedelta(hours=1))
        self.assertEqual([e["key"] for e in st.open_entries(state)], ["failed-assertion:knowledge-digest"])


class Persistence(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = pathlib.Path(self.temp.name) / "incidents" / "state.json"

    def tearDown(self):
        self.temp.cleanup()

    def test_save_is_atomic_and_load_round_trips(self):
        # (::incident-state-atomic)
        state = st.empty()
        st.reconcile(state, [observed()], T0)
        st.save(state, self.path)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["state.json"])
        loaded, notice = st.load(self.path)
        self.assertIsNone(notice)
        self.assertEqual(loaded, state)
        before = self.path.read_bytes()
        with self.assertRaises(TypeError):
            st.save({"schema": 1, "last_digest_at": None, "incidents": {"k": object()}}, self.path)
        self.assertEqual(self.path.read_bytes(), before)
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["state.json"])

    def test_missing_file_is_fresh_and_corrupt_file_is_moved_aside(self):
        loaded, notice = st.load(self.path)
        self.assertEqual(loaded, st.empty())
        self.assertIsNone(notice)
        self.path.parent.mkdir(parents=True)
        self.path.write_text("{not json")
        loaded, notice = st.load(self.path, now=T0)
        self.assertEqual(loaded, st.empty())
        self.assertIn("state.json.corrupt-20260914T030500Z", notice)
        self.assertFalse(self.path.exists())
        self.assertTrue((self.path.parent / "state.json.corrupt-20260914T030500Z").is_file())
        self.path.write_text(json.dumps({"schema": 99}))
        loaded, notice = st.load(self.path, now=T0 + dt.timedelta(seconds=1))
        self.assertEqual(loaded, st.empty())
        self.assertIn("corrupt-20260914T030501Z", notice)


if __name__ == "__main__":
    unittest.main()
