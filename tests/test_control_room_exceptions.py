#!/usr/bin/env python3
"""Fixture tests for bin/control_room_exceptions.py — one row per (workflow, kind), Unknown never one."""

from __future__ import annotations

import datetime as dt
import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from control_room_fixture import NOW, build_model  # noqa: E402

import control_room_exceptions as exceptions  # noqa: E402

DAY = 86400


def stamp(delta_seconds: int) -> str:
    return (NOW + dt.timedelta(seconds=delta_seconds)).strftime("%Y-%m-%dT%H:%M:%SZ")


def receipt(run, outcome, ended_seconds_ago, *, reason=None, assertions=(), next_action=None,
            consumption=None, duration=300):
    body = {
        "workflow_id": "w", "run_id": run,
        "started_at": stamp(-ended_seconds_ago - duration), "ended_at": stamp(-ended_seconds_ago),
        "terminal": {"outcome": outcome, "reason": reason},
        "artifact": {"uri": "https://www.notion.so/x", "title": "x"} if outcome == "artifact" else None,
        "state_change": None, "assertions": list(assertions), "next_action": next_action,
        "usage": {"status": "unavailable"}, "cost": {"status": "unavailable"},
    }
    if consumption is not None:
        body["consumption"] = consumption
    return body


def item(receipts=(), *, state="active", next_run=None, last_trigger=None, artifact_declared=True):
    receipts = list(receipts)
    artifacts = [r for r in receipts if r["terminal"]["outcome"] == "artifact"]
    eligible = [r for r in receipts if r["terminal"]["outcome"] != "skipped"]
    last_valid = None
    if artifacts:
        age = int((NOW - dt.datetime.strptime(artifacts[0]["ended_at"], "%Y-%m-%dT%H:%M:%SZ")
                   .replace(tzinfo=dt.timezone.utc)).total_seconds())
        last_valid = {"runId": artifacts[0]["run_id"], "endedAt": artifacts[0]["ended_at"],
                      "uri": artifacts[0]["artifact"]["uri"], "title": "x", "kind": "artifact", "ageSeconds": age}
    return {
        "id": "w", "owner": "claudius",
        "control": {"state": state, "nextRunAt": next_run, "lastTriggerAt": last_trigger},
        "contract": {"artifact": "one Notion page"} if artifact_declared else None,
        "lastValidArtifact": last_valid,
        "eligibleRuns": len(eligible),
        "validArtifactRate": (len(artifacts) / len(eligible)) if eligible else None,
    }


def kinds(rows):
    return [row["kind"] for row in rows]


FAILED_CHECK = {"id": "artifact-is-this-run", "status": "failed", "message": "artifact is dated yesterday"}
OLD_ARTIFACT = receipt("r0", "artifact", 20 * DAY)


class ExceptionsKindTable(unittest.TestCase):  # (::exceptions-kind-table)
    def test_each_kind_from_its_own_workflow_in_kinds_order(self):
        cases = {
            "failed": item([receipt("r1", "failed", 3600, reason="checks failed", assertions=[FAILED_CHECK]), OLD_ARTIFACT]),
            "stale-input": item([receipt("r1", "decline", 3600, reason="DECLINE: mirror stale"), OLD_ARTIFACT]),
            "missing-artifact": item([receipt("r1", "skipped", 3600, reason="SKIP: previous run still active"), OLD_ARTIFACT]),
            "missed-cadence": item([], last_trigger=stamp(-3600)),
            "overdue-next-action": item([receipt("r1", "artifact", 2 * DAY,
                                                 next_action={"actor": "Dave", "action": "review", "due_at": stamp(-DAY)})]),
            "unconsumed-output": item([receipt("r1", "artifact", 8 * DAY,
                                               consumption={"opened": False, "approved": False, "sent": False, "marked_useful": False})]),
        }
        self.assertEqual(tuple(cases), exceptions.KINDS)
        for kind, workflow in cases.items():
            with self.subTest(kind=kind):
                rows = exceptions.classify(workflow, self._receipts_of(kind, cases), NOW)
                self.assertEqual(kinds(rows), [kind])
                self.assertEqual(rows[0]["workflowId"], "w")
                self.assertEqual(rows[0]["owner"], "claudius")
                self.assertTrue(rows[0]["issue"])
                self.assertTrue(rows[0]["requiredAction"])
                self.assertIn("runId", rows[0]["evidence"])
                self.assertIn("artifactUri", rows[0]["evidence"])
                self.assertFalse(rows[0]["paused"])

    @staticmethod
    def _receipts_of(kind, cases):
        return {
            "failed": [receipt("r1", "failed", 3600, reason="checks failed", assertions=[FAILED_CHECK]), OLD_ARTIFACT],
            "stale-input": [receipt("r1", "decline", 3600, reason="DECLINE: mirror stale"), OLD_ARTIFACT],
            "missing-artifact": [receipt("r1", "skipped", 3600, reason="SKIP: previous run still active"), OLD_ARTIFACT],
            "missed-cadence": [],
            "overdue-next-action": [receipt("r1", "artifact", 2 * DAY,
                                            next_action={"actor": "Dave", "action": "review", "due_at": stamp(-DAY)})],
            "unconsumed-output": [receipt("r1", "artifact", 8 * DAY,
                                          consumption={"opened": False, "approved": False, "sent": False, "marked_useful": False})],
        }[kind]

    def test_failed_row_names_the_failed_assertion(self):
        receipts = [receipt("r1", "failed", 3600, reason="checks failed: artifact-is-this-run", assertions=[FAILED_CHECK])]
        row = exceptions.classify(item(receipts), receipts, NOW)[0]
        self.assertEqual(row["failedAssertions"], ["artifact-is-this-run"])
        self.assertIn("artifact-is-this-run", row["issue"])
        self.assertEqual(row["evidence"]["runId"], "r1")
        self.assertEqual(row["since"], receipts[0]["ended_at"])

    def test_missing_artifact_b_when_every_eligible_run_lacks_one(self):
        receipts = [receipt("r2", "decline", 3600, reason="DECLINE: nothing to do"),
                    receipt("r1", "decline", DAY, reason="DECLINE: nothing to do")]
        rows = exceptions.classify(item(receipts), receipts, NOW)
        self.assertEqual(kinds(rows), ["missing-artifact"])
        rows = exceptions.classify(item(receipts, artifact_declared=False), receipts, NOW)
        self.assertEqual(rows, [])

    def test_constants_are_the_briefs(self):
        self.assertEqual(exceptions.UNCONSUMED_GRACE_SECONDS, 7 * DAY)
        self.assertEqual(exceptions.MISSED_GRACE_SECONDS, 900)
        self.assertEqual(exceptions.NEXT_RUN_SLACK_SECONDS, 3600)
        self.assertRegex("input mirror is Out Of Date", exceptions.STALE_INPUT_PATTERN)
        self.assertNotRegex("stalemate", exceptions.STALE_INPUT_PATTERN)
        self.assertRegex("vault-guard-mirror-current", exceptions.INPUT_CHECK_PATTERN)


class ExceptionsStaleInputPrecedence(unittest.TestCase):  # (::exceptions-stale-input-precedence)
    def test_failed_run_with_stale_reason_is_one_stale_input_row(self):
        receipts = [receipt("r1", "failed", 3600, reason="mirror stale — vault_sync_guard refused"), OLD_ARTIFACT]
        rows = exceptions.classify(item(receipts), receipts, NOW)
        self.assertEqual(kinds(rows), ["stale-input"])
        self.assertTrue(rows[0]["alsoFailed"])

    def test_failed_assertion_id_naming_the_input_check_counts(self):
        check = {"id": "mirror-current", "status": "failed", "message": "refused"}
        receipts = [receipt("r1", "failed", 3600, reason="checks failed", assertions=[check]), OLD_ARTIFACT]
        rows = exceptions.classify(item(receipts), receipts, NOW)
        self.assertEqual(kinds(rows), ["stale-input"])
        self.assertEqual(rows[0]["failedAssertions"], ["mirror-current"])

    def test_decline_with_stale_reason_is_not_also_failed(self):
        receipts = [receipt("r1", "decline", 3600, reason="DECLINE: mirror behind origin"), OLD_ARTIFACT]
        rows = exceptions.classify(item(receipts), receipts, NOW)
        self.assertEqual(kinds(rows), ["stale-input"])
        self.assertFalse(rows[0]["alsoFailed"])


class ExceptionsPausedSuppression(unittest.TestCase):  # (::exceptions-paused-suppression)
    def test_paused_timer_rules_yield_nothing(self):
        receipts = [receipt("r1", "decline", DAY, reason="DECLINE: nothing")]
        workflow = item(receipts, state="paused", last_trigger=stamp(-3 * DAY), next_run=stamp(-2 * DAY))
        self.assertEqual(exceptions.classify(workflow, receipts, NOW), [])

    def test_paused_failed_run_is_still_owed(self):
        receipts = [receipt("r1", "failed", DAY, reason="checks failed", assertions=[FAILED_CHECK]), OLD_ARTIFACT]
        rows = exceptions.classify(item(receipts, state="paused"), receipts, NOW)
        self.assertEqual(kinds(rows), ["failed"])
        self.assertTrue(rows[0]["paused"])

    def test_paused_is_never_its_own_row(self):
        rows = exceptions.classify(item([OLD_ARTIFACT], state="paused"), [OLD_ARTIFACT], NOW)
        self.assertEqual(rows, [])


class ExceptionsUnknownIsNotException(unittest.TestCase):  # (::exceptions-unknown-is-not-exception)
    def test_no_receipt_is_no_row(self):
        self.assertEqual(exceptions.classify(item([]), [], NOW), [])

    def test_absent_consumption_is_not_unconsumed(self):
        receipts = [receipt("r1", "artifact", 20 * DAY)]
        self.assertEqual(exceptions.classify(item(receipts), receipts, NOW), [])
        receipts = [receipt("r1", "artifact", 20 * DAY, consumption={"opened": None, "approved": False, "sent": False, "marked_useful": False})]
        self.assertEqual(exceptions.classify(item(receipts), receipts, NOW), [])

    def test_unconsumed_within_grace_is_not_a_row(self):
        receipts = [receipt("r1", "artifact", 2 * DAY,
                            consumption={"opened": False, "approved": False, "sent": False, "marked_useful": False})]
        self.assertEqual(exceptions.classify(item(receipts), receipts, NOW), [])

    def test_null_due_at_is_not_overdue(self):
        receipts = [receipt("r1", "artifact", DAY, next_action={"actor": "Dave", "action": "review", "due_at": None})]
        self.assertEqual(exceptions.classify(item(receipts), receipts, NOW), [])

    def test_unknown_control_state_is_not_missed_cadence(self):
        workflow = item([OLD_ARTIFACT], state="unknown", last_trigger=stamp(-3 * DAY))
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])


class ExceptionsMissedCadence(unittest.TestCase):  # (::exceptions-missed-cadence)
    def test_trigger_without_receipt_since_is_missed(self):
        workflow = item([OLD_ARTIFACT], last_trigger="2026-09-14T07:00:00Z")
        rows = exceptions.classify(workflow, [OLD_ARTIFACT], NOW)
        self.assertEqual(kinds(rows), ["missed-cadence"])
        self.assertEqual(rows[0]["since"], "2026-09-14T07:00:00Z")
        self.assertIn("07:00", rows[0]["issue"])

    def test_receipt_after_the_trigger_is_not_missed(self):
        after = receipt("r1", "artifact", 1500, duration=240)
        after["started_at"] = "2026-09-14T07:31:00Z"
        workflow = item([after], last_trigger="2026-09-14T07:30:00Z")
        self.assertEqual(exceptions.classify(workflow, [after], NOW), [])

    def test_receipt_started_within_grace_before_the_trigger_counts(self):
        early = receipt("r1", "artifact", 1500, duration=240)
        early["started_at"] = "2026-09-14T07:20:00Z"
        workflow = item([early], last_trigger="2026-09-14T07:30:00Z")
        self.assertEqual(exceptions.classify(workflow, [early], NOW), [])

    def test_next_run_long_past_is_missed(self):
        workflow = item([OLD_ARTIFACT], next_run=stamp(-2 * 3600))
        self.assertEqual(kinds(exceptions.classify(workflow, [OLD_ARTIFACT], NOW)), ["missed-cadence"])
        workflow = item([OLD_ARTIFACT], next_run=stamp(-1800))
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])

    def test_running_service_is_not_missed(self):
        workflow = item([OLD_ARTIFACT], state="running", last_trigger="2026-09-14T07:00:00Z")
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])


class ExceptionsEnvelope(unittest.TestCase):
    def test_fixture_queue_is_ordered_by_kind_then_since(self):
        env = build_model().exceptions()
        rows = env["items"]
        order = [exceptions.KINDS.index(row["kind"]) for row in rows]
        self.assertEqual(order, sorted(order))
        self.assertEqual(rows[0]["workflowId"], "raw-ingest")
        self.assertEqual(rows[0]["kind"], "failed")
        by_kind = {row["kind"]: row for row in rows}
        self.assertEqual(by_kind["stale-input"]["workflowId"], "bd-stall-radar")
        self.assertEqual(by_kind["missed-cadence"]["workflowId"], "fleet-turn-check")
        self.assertEqual(by_kind["overdue-next-action"]["workflowId"], "overnight-morning-report")
        self.assertEqual(by_kind["unconsumed-output"]["workflowId"], "bd-followup-drafts")
        paused_ids = {w["id"] for w in build_model().workflows()[0] if w["control"]["state"] == "paused"}
        self.assertNotIn("knowledge-digest", {row["workflowId"] for row in rows})
        for row in rows:
            if row["kind"] in {"missed-cadence"}:
                self.assertNotIn(row["workflowId"], paused_ids)
        self.assertEqual({row["failedAssertion"] for row in env["dataQuality"]},
                         {"receipt-schema-valid", "systemd-available"})
        self.assertTrue(any("aurelian" in row["issue"] for row in env["dataQuality"]))


if __name__ == "__main__":
    unittest.main()
