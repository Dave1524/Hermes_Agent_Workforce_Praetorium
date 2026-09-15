#!/usr/bin/env python3
"""Fixture tests for bin/control_room_benefit.py — Unknown preferred, four signals kept apart."""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest
import urllib.request

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from control_room_fixture import FIXTURE, ROOT, api, build_model, serving  # noqa: E402

import control_room_benefit as benefit  # noqa: E402


def receipt(run, outcome, started, ended, consumption=None):
    body = {
        "workflow_id": "w", "run_id": run, "started_at": started, "ended_at": ended,
        "terminal": {"outcome": outcome, "reason": None},
        "artifact": {"uri": "https://www.notion.so/x", "title": "x"} if outcome == "artifact" else None,
        "state_change": None, "assertions": [],
        "usage": {"status": "unavailable"}, "cost": {"status": "unavailable"},
    }
    if consumption is not None:
        body["consumption"] = consumption
    return body


ITEM = {"id": "w", "contract": {"artifact": "one file"}}


class BenefitUnknownPreferred(unittest.TestCase):  # (::benefit-unknown-preferred)
    def test_no_receipts_and_no_ledger_entry_is_unknown_everywhere(self):
        row = benefit.benefit_row(ITEM, [], None)
        self.assertEqual(row["decision"], "Unknown")
        self.assertEqual(row["eligibleRuns"], 0)
        self.assertIsNone(row["validArtifactRate"])
        self.assertIsNone(row["latencySeconds"])
        self.assertEqual(row["consumption"]["status"], "unavailable")
        for signal in benefit.CONSUMPTION_SIGNALS:
            self.assertIsNone(row["consumption"][signal])
        self.assertIsNone(row["baseline"])
        self.assertIsNone(row["manualMinutesAvoided"])

    def test_missing_ledger_file_is_unavailable_in_data_status(self):
        with tempfile.TemporaryDirectory() as empty:
            entries, errors = benefit.load_ledger(pathlib.Path(empty))
        self.assertIsNone(entries)
        self.assertTrue(errors and "benefit-ledger.toml" in errors[0])
        with tempfile.TemporaryDirectory() as empty:
            model = build_model(paths=api.SourcePaths(repo=pathlib.Path(empty), runtime=FIXTURE,
                                                      receipts=FIXTURE / "receipts"))
            self.assertEqual(model.benefit()["dataStatus"]["benefitLedger"], "unavailable")


class BenefitFourSignalsSeparate(unittest.TestCase):  # (::benefit-four-signals-separate)
    def test_counts_are_per_signal_and_never_a_score(self):
        receipts = [
            receipt("r2", "artifact", "2026-09-10T00:00:00Z", "2026-09-10T00:10:00Z",
                    {"opened": True, "approved": True, "sent": False, "marked_useful": False}),
            receipt("r1", "artifact", "2026-09-09T00:00:00Z", "2026-09-09T00:05:00Z",
                    {"opened": True, "approved": False, "sent": True, "marked_useful": False}),
        ]
        consumption = benefit.benefit_row(ITEM, receipts, None)["consumption"]
        self.assertEqual(consumption["status"], "measured")
        self.assertEqual((consumption["opened"], consumption["approved"], consumption["sent"],
                          consumption["marked_useful"]), (2, 1, 1, 0))
        self.assertEqual(consumption["artifactRuns"], 2)
        self.assertFalse({key for key in consumption if "score" in key.lower()})

    def test_artifact_without_consumption_leaves_it_unavailable(self):
        receipts = [receipt("r1", "artifact", "2026-09-09T00:00:00Z", "2026-09-09T00:05:00Z")]
        consumption = benefit.benefit_row(ITEM, receipts, None)["consumption"]
        self.assertEqual(consumption["status"], "unavailable")
        self.assertIsNone(consumption["opened"])


class BenefitLedgerJoin(unittest.TestCase):  # (::benefit-ledger-join)
    def test_fixture_ledger_joins_by_logical_id(self):
        rows = {row["workflowId"]: row for row in build_model().benefit()["items"]}
        self.assertEqual(rows["knowledge-digest"]["decision"], "Improve")
        self.assertEqual(rows["knowledge-digest"]["manualMinutesAvoided"], 30)
        self.assertEqual(rows["knowledge-digest"]["baseline"], "weekly digest read Monday")
        self.assertEqual(rows["agent-proposal"]["decision"], "Keep")
        self.assertEqual(rows["weekly-pre-assembly"]["decision"], "Unknown")

    def test_decision_outside_vocabulary_is_named_and_renders_unknown(self):
        entries, errors = benefit.load_ledger(ROOT, FIXTURE / "benefit-ledger.toml")
        self.assertNotIn("scorecard", entries)
        self.assertTrue(any("scorecard" in error and "Maybe" in error for error in errors))
        env = build_model().benefit()
        self.assertEqual(env["dataStatus"]["benefitLedger"], "degraded")
        self.assertTrue(any("Maybe" in error for error in env["dataStatus"]["errors"]["benefitLedger"]))
        scorecard = next(row for row in env["items"] if row["workflowId"] == "scorecard")
        self.assertEqual(scorecard["decision"], "Unknown")
        self.assertEqual(benefit.DECISIONS, ("Keep", "Improve", "Retire", "Unknown"))

    def test_benefit_route_serves_the_envelope(self):
        with serving(build_model()) as base:
            with urllib.request.urlopen(f"{base}/api/v1/benefit", timeout=5) as response:
                env = json.loads(response.read())
        self.assertEqual(env["dataStatus"]["benefitLedger"], "degraded")
        # one row per logical workflow; the pair itself is pinned by ::control-room-30-of-31
        standing = [e for e in build_model()._manifests()[0] if e.get("status") == "standing"]
        self.assertEqual(len(env["items"]), len({e.get("logical_workflow") or e["unit"] for e in standing}))


class BenefitRateAndLatency(unittest.TestCase):  # (::benefit-rate-and-latency)
    def test_three_artifacts_one_decline_one_skipped(self):
        receipts = [
            receipt("r5", "skipped", "2026-09-14T00:00:00Z", "2026-09-14T00:00:01Z"),
            receipt("r4", "artifact", "2026-09-13T00:00:00Z", "2026-09-13T00:08:00Z"),
            receipt("r3", "decline", "2026-09-12T00:00:00Z", "2026-09-12T00:01:00Z"),
            receipt("r2", "artifact", "2026-09-11T00:00:00Z", "2026-09-11T00:04:00Z"),
            receipt("r1", "artifact", "2026-09-10T00:00:00Z", "2026-09-10T00:06:00Z"),
        ]
        row = benefit.benefit_row(ITEM, receipts, None)
        self.assertEqual(row["eligibleRuns"], 4)
        self.assertEqual(row["validArtifactRate"], 0.75)
        self.assertEqual(row["latencySeconds"], 300)


if __name__ == "__main__":
    unittest.main()
