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
from workflow_receipt import close, judged  # noqa: E402

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


def requirement(unit, satisfied, *, scope="user", workflow=None):
    state = {True: "active", False: "inactive", None: "unknown"}[satisfied]
    return {"unit": unit, "scope": scope, "workflow": workflow, "state": state, "satisfied": satisfied}


def item(receipts=(), *, state="active", next_run=None, last_trigger=None, fired=None, artifact_declared=True,
         requires=()):
    receipts = list(receipts)
    artifacts = [r for r in receipts if r["terminal"]["outcome"] == "artifact"]
    eligible = [r for r in receipts if judged(r)]
    last_valid = None
    if artifacts:
        age = int((NOW - dt.datetime.strptime(artifacts[0]["ended_at"], "%Y-%m-%dT%H:%M:%SZ")
                   .replace(tzinfo=dt.timezone.utc)).total_seconds())
        last_valid = {"runId": artifacts[0]["run_id"], "endedAt": artifacts[0]["ended_at"],
                      "uri": artifacts[0]["artifact"]["uri"], "title": "x", "kind": "artifact", "ageSeconds": age}
    return {
        "id": "w", "owner": "claudius",
        "control": {"state": state, "nextRunAt": next_run, "lastTriggerAt": last_trigger,
                    "lastFiredAt": last_trigger if fired is None else fired},
        "contract": {"artifact": "one Notion page"} if artifact_declared else None,
        "lastValidArtifact": last_valid,
        "eligibleRuns": len(eligible),
        "validArtifactRate": (len(artifacts) / len(eligible)) if eligible else None,
        "requires": list(requires),
    }


def kinds(rows):
    return [row["kind"] for row in rows]


FAILED_CHECK = {"id": "artifact-is-this-run", "status": "failed", "message": "artifact is dated yesterday"}
OLD_ARTIFACT = receipt("r0", "artifact", 20 * DAY)
SKIPPED = receipt("r9", "skipped", 600, reason="dedup: today's proposal already exists", duration=20)
NEVER_DELIVERED = [receipt("r2", "decline", 3600, reason="DECLINE: nothing to do"),
                   receipt("r1", "failed", DAY, reason="CRASHED: rc=1")]


class ExceptionsKindTable(unittest.TestCase):  # (::exceptions-kind-table)
    def test_each_kind_from_its_own_workflow_in_kinds_order(self):
        cases = {
            "failed": item([receipt("r1", "failed", 3600, reason="checks failed", assertions=[FAILED_CHECK]), OLD_ARTIFACT]),
            "stale-input": item([receipt("r1", "decline", 3600, reason="DECLINE: mirror stale"), OLD_ARTIFACT]),
            "missing-artifact": item(NEVER_DELIVERED),
            "missed-cadence": item([], last_trigger=stamp(-3600)),
            "overdue-next-action": item([receipt("r1", "artifact", 2 * DAY,
                                                 next_action={"actor": "Dave", "action": "review", "due_at": stamp(-DAY)})]),
            "unconsumed-output": item([receipt("r1", "artifact", 8 * DAY,
                                               consumption={"opened": False, "approved": False, "sent": False, "marked_useful": False})]),
            "dependency-down": item([OLD_ARTIFACT], requires=[requirement("buzz-agent@augustus", False, workflow="buzz-agent@augustus")]),
        }
        self.assertEqual(tuple(cases), exceptions.KINDS)
        for kind, workflow in cases.items():
            with self.subTest(kind=kind):
                rows = exceptions.classify(workflow, self._receipts_of(kind, cases), NOW, swept_at=NOW)
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
            "missing-artifact": NEVER_DELIVERED,
            "missed-cadence": [],
            "overdue-next-action": [receipt("r1", "artifact", 2 * DAY,
                                            next_action={"actor": "Dave", "action": "review", "due_at": stamp(-DAY)})],
            "unconsumed-output": [receipt("r1", "artifact", 8 * DAY,
                                          consumption={"opened": False, "approved": False, "sent": False, "marked_useful": False})],
            "dependency-down": [OLD_ARTIFACT],
        }[kind]

    def test_failed_row_names_the_failed_assertion(self):
        receipts = [receipt("r1", "failed", 3600, reason="checks failed: artifact-is-this-run", assertions=[FAILED_CHECK])]
        row = exceptions.classify(item(receipts), receipts, NOW)[0]
        self.assertEqual(row["failedAssertions"], ["artifact-is-this-run"])
        self.assertIn("artifact-is-this-run", row["issue"])
        self.assertEqual(row["evidence"]["runId"], "r1")
        self.assertEqual(row["since"], receipts[0]["ended_at"])

    def test_missing_artifact_b_when_every_eligible_run_lacks_one(self):
        rows = exceptions.classify(item(NEVER_DELIVERED), NEVER_DELIVERED, NOW)
        self.assertEqual(kinds(rows), ["missing-artifact"])
        self.assertIn("2 eligible run(s)", rows[0]["issue"])
        self.assertEqual(rows[0]["evidence"]["runId"], "r2")
        rows = exceptions.classify(item(NEVER_DELIVERED, artifact_declared=False), NEVER_DELIVERED, NOW)
        self.assertEqual(rows, [])

    def test_clean_declines_are_the_contract_honoured_not_a_missing_artifact(self):
        # (::exceptions-clean-decline)
        receipts = [receipt("r2", "decline", 3600, reason="DECLINE: no unprocessed sources"),
                    receipt("r1", "decline", DAY, reason="DECLINE: no unprocessed sources")]
        self.assertEqual(exceptions.classify(item(receipts), receipts, NOW), [])
        check = {"id": "declined-only-when-nothing-unprocessed", "status": "failed", "message": "raw/ has 2 files"}
        unclean = [receipt("r2", "decline", 3600, reason="DECLINE: nothing", assertions=[check]), receipts[1]]
        self.assertEqual(kinds(exceptions.classify(item(unclean), unclean, NOW)), ["failed", "missing-artifact"])

    def test_skipped_latest_is_not_a_run(self):
        # (::exceptions-skipped-not-a-run)
        receipts = [SKIPPED, receipt("r1", "artifact", 4 * 3600)]
        self.assertEqual(exceptions.classify(item(receipts), receipts, NOW), [])
        receipts = [SKIPPED, receipt("r1", "failed", 4 * 3600, reason="checks failed", assertions=[FAILED_CHECK]), OLD_ARTIFACT]
        rows = exceptions.classify(item(receipts), receipts, NOW)
        self.assertEqual([(row["kind"], row["evidence"]["runId"]) for row in rows], [("failed", "r1")])
        self.assertEqual(exceptions.classify(item([SKIPPED]), [SKIPPED], NOW), [])

    def test_a_closed_failure_is_not_a_run_to_judge(self):
        # (::exceptions-closed-run)
        failed = receipt("r1", "failed", 4 * 3600, reason="FAIL: rc=91 skip: today's proposal exists", assertions=[FAILED_CHECK])
        receipts = [SKIPPED, failed, receipt("r0", "failed", DAY, reason="checks failed", assertions=[FAILED_CHECK])]
        self.assertEqual(kinds(exceptions.classify(item(receipts), receipts, NOW)), ["failed", "missing-artifact"])
        closed = [SKIPPED, close(failed, "Dave", "skip receipted failed before 73dea03", NOW),
                  close(receipts[2], "Dave", "mirror-was-not-dirty: stray graft/ tree, excluded", NOW)]
        self.assertEqual(exceptions.classify(item(closed), closed, NOW), [])
        half = [closed[0], closed[1], receipts[2]]
        rows = exceptions.classify(item(half), half, NOW)
        self.assertEqual([(row["kind"], row["evidence"]["runId"]) for row in rows], [("failed", "r0"), ("missing-artifact", "r0")])

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
    def test_fire_the_sweep_found_no_receipt_for_is_missed(self):
        workflow = item([OLD_ARTIFACT], last_trigger="2026-09-14T07:00:00Z")
        rows = exceptions.classify(workflow, [OLD_ARTIFACT], NOW, swept_at=NOW)
        self.assertEqual(kinds(rows), ["missed-cadence"])
        self.assertEqual(rows[0]["since"], "2026-09-14T07:00:00Z")
        self.assertIn("07:00", rows[0]["issue"])
        self.assertIn("2026-09-14T08:00:00Z", rows[0]["issue"])

    def test_fire_the_sweep_has_not_looked_at_is_not_missed(self):
        # (::exceptions-sweep-vantage)
        workflow = item([OLD_ARTIFACT], last_trigger="2026-09-14T07:00:00Z")
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])
        early = NOW - dt.timedelta(seconds=exceptions.MISSED_GRACE_SECONDS + 3600 - 60)
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW, swept_at=early), [])

    def test_stamp_read_back_on_resume_is_not_a_fire(self):
        # (::exceptions-stamp-not-a-fire)
        workflow = item([OLD_ARTIFACT], last_trigger="2026-09-14T07:00:00Z", fired=None)
        workflow["control"]["lastFiredAt"] = None
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW, swept_at=NOW), [])

    def test_receipt_after_the_trigger_is_not_missed(self):
        after = receipt("r1", "artifact", 1500, duration=240)
        after["started_at"] = "2026-09-14T07:31:00Z"
        workflow = item([after], last_trigger="2026-09-14T07:30:00Z")
        self.assertEqual(exceptions.classify(workflow, [after], NOW, swept_at=NOW), [])

    def test_receipt_started_within_grace_before_the_trigger_counts(self):
        early = receipt("r1", "artifact", 1500, duration=240)
        early["started_at"] = "2026-09-14T07:20:00Z"
        workflow = item([early], last_trigger="2026-09-14T07:30:00Z")
        self.assertEqual(exceptions.classify(workflow, [early], NOW, swept_at=NOW), [])

    def test_a_skip_receipt_is_the_fire_accounted_for(self):
        skip = receipt("r1", "skipped", 1700, reason="SKIP: previous run still active", duration=1)
        skip["started_at"] = "2026-09-14T07:30:01Z"
        workflow = item([skip], last_trigger="2026-09-14T07:30:00Z")
        self.assertEqual(exceptions.classify(workflow, [skip], NOW, swept_at=NOW), [])

    def test_next_run_long_past_is_missed(self):
        workflow = item([OLD_ARTIFACT], next_run=stamp(-2 * 3600))
        self.assertEqual(kinds(exceptions.classify(workflow, [OLD_ARTIFACT], NOW)), ["missed-cadence"])
        workflow = item([OLD_ARTIFACT], next_run=stamp(-1800))
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])

    def test_running_service_is_not_missed(self):
        workflow = item([OLD_ARTIFACT], state="running", last_trigger="2026-09-14T07:00:00Z")
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])


class ExceptionsDependencyDown(unittest.TestCase):  # (::exceptions-dependency-down)
    def test_a_requirement_known_down_is_one_row_naming_every_down_unit(self):
        workflow = item([OLD_ARTIFACT], requires=[requirement("buzz-agent@augustus", False, workflow="buzz-agent@augustus"),
                                                  requirement("buzz-notion-broker", True),
                                                  requirement("index-daemon.service", False, scope="system")])
        rows = exceptions.classify(workflow, [OLD_ARTIFACT], NOW)
        self.assertEqual(kinds(rows), ["dependency-down"])
        row = rows[0]
        self.assertIn("buzz-agent@augustus (user): inactive", row["issue"])
        self.assertIn("index-daemon.service (system): inactive", row["issue"])
        self.assertNotIn("buzz-notion-broker", row["issue"])
        self.assertIn("pre-flight", row["requiredAction"])
        self.assertIsNone(row["since"])
        self.assertFalse(row["paused"])
        self.assertEqual(row["evidence"], {"runId": None, "artifactUri": None})

    def test_unknown_and_satisfied_are_not_exceptions(self):
        for satisfied in (True, None):
            workflow = item([OLD_ARTIFACT], requires=[requirement("buzz-agent@augustus", satisfied)])
            self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [], satisfied)
        self.assertEqual(exceptions.classify(item([OLD_ARTIFACT]), [OLD_ARTIFACT], NOW), [])
        no_field = item([OLD_ARTIFACT])
        del no_field["requires"]
        self.assertEqual(exceptions.classify(no_field, [OLD_ARTIFACT], NOW), [])

    def test_paused_suppresses_it(self):
        workflow = item([OLD_ARTIFACT], state="paused", requires=[requirement("buzz-agent@augustus", False)])
        self.assertEqual(exceptions.classify(workflow, [OLD_ARTIFACT], NOW), [])

    def test_it_sorts_after_every_other_kind(self):
        self.assertEqual(exceptions.KINDS[-1], "dependency-down")
        receipts = [receipt("r1", "failed", 3600, reason="checks failed", assertions=[FAILED_CHECK]), OLD_ARTIFACT]
        workflow = item(receipts, requires=[requirement("buzz-agent@augustus", False)])
        self.assertEqual(kinds(exceptions.classify(workflow, receipts, NOW)), ["failed", "dependency-down"])


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
        self.assertIn("2026-09-14T07:20:00Z", by_kind["missed-cadence"]["issue"], "the fixture sweep's start")
        self.assertNotIn("agent-inbox-sync", {row["workflowId"] for row in rows}, "fired after the fixture sweep")
        self.assertEqual(by_kind["overdue-next-action"]["workflowId"], "overnight-morning-report")
        self.assertEqual(by_kind["unconsumed-output"]["workflowId"], "bd-followup-drafts")
        self.assertNotIn("dependency-down", by_kind, "the fixture bus runs the broker and the index daemon, and augustus-content is paused")
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
