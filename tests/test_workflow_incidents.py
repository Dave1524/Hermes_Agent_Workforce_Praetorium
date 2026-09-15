#!/usr/bin/env python3
"""Incident derivation (T5.3c): what an incident is, keyed so one failure is one incident.

Pure: the inputs are the shapes bin/control_room_api.py's `workflows()` and `receipts()`
return, built here by hand. Silence is asserted, never assumed — a healthy or declined run
must derive to nothing, and the paused label must not hide a failed last run.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


wi = load("workflow_incidents")
UTC = dt.timezone.utc
NOW = dt.datetime(2026, 9, 14, 10, 0, tzinfo=UTC)


def trigger(unit, timer_active="inactive", last_trigger=None, running=False):
    return {
        "unit": unit,
        "kind": "timer",
        "state": "running" if running else ("active" if timer_active == "active" else "paused"),
        "systemd": {
            "kind": "timer",
            "service": {"name": f"{unit}.service", "activeState": "active" if running else "inactive",
                        "subState": "running" if running else "dead"},
            "timer": {"name": f"{unit}.timer", "activeState": timer_active, "lastTriggerAt": last_trigger},
        },
    }


def run(outcome, run_id="run-1", failed=(), reason=None, artifact=None, ended="2026-09-14T03:04:00Z",
        started="2026-09-14T03:00:00Z"):
    assertions = [{"id": "artifact-exists", "status": "failed" if "artifact-exists" in failed else "passed"}]
    return {
        "id": run_id, "workflowId": "knowledge-digest", "unit": "knowledge-digest", "agent": "claudius",
        "startedAt": started, "endedAt": ended,
        "outcome": outcome, "reason": reason, "artifact": artifact, "assertions": assertions,
        "nextAction": {"actor": "Dave", "action": "Re-run by hand"},
        "receiptPath": f"knowledge-digest/{run_id}.json",
    }


def workflow(last_run=None, triggers=None, contract="available", wf_id="knowledge-digest"):
    return {
        "id": wf_id, "owner": "claudius", "contractStatus": contract,
        "contractError": None if contract == "available" else "contract file missing",
        "manifestPaths": ["design/agents/claudius.toml"],
        "triggers": triggers if triggers is not None else [trigger(wf_id)],
        "lastRun": last_run, "health": "paused",
    }


def derive(workflows, malformed=(), source_errors=(), declared=(), now=NOW, **kw):
    return wi.derive(list(workflows), list(malformed), list(source_errors), list(declared), now, **kw)


class Derivation(unittest.TestCase):
    def test_healthy_and_declined_runs_are_silent(self):
        # (::incidents-silence)
        healthy = workflow(run("artifact", artifact={"uri": "file:///x.md"}))
        declined = workflow(run("decline", reason="nothing new"))
        self.assertEqual(derive([healthy]), [])
        self.assertEqual(derive([declined]), [])

    def test_failed_check_is_a_failed_assertion_keyed_by_workflow(self):
        # (::incidents-classes)
        found = derive([workflow(run("failed", failed=("artifact-exists",), reason="failed checks: artifact-exists",
                                     artifact={"uri": "file:///y.md"}))])
        self.assertEqual([i["key"] for i in found], ["failed-assertion:knowledge-digest"])
        item = found[0]
        self.assertEqual(item["class"], "failed-assertion")
        self.assertEqual(item["severity"], "high")
        self.assertEqual(item["failed_assertion"], "artifact-exists")
        self.assertEqual(item["run_id"], "run-1")
        self.assertEqual(item["agent"], "claudius")
        self.assertEqual(item["required_action"], "Re-run by hand")
        self.assertIn("knowledge-digest/run-1.json", item["evidence"])
        self.assertIn("file:///y.md", item["evidence"])
        self.assertEqual(item["observed_at"], "2026-09-14T03:04:00Z")

    def test_failed_without_a_failed_check_is_a_missing_artifact(self):
        found = derive([workflow(run("failed", reason="neither artifact nor decline"))])
        self.assertEqual([i["key"] for i in found], ["missing-artifact:knowledge-digest"])
        self.assertEqual(found[0]["issue"], "neither artifact nor decline")

    def test_skipped_is_an_incomplete_run(self):
        found = derive([workflow(run("skipped", reason="lock held"))])
        self.assertEqual([i["key"] for i in found], ["incomplete-run:knowledge-digest"])
        self.assertEqual(found[0]["issue"], "lock held")

    def test_fired_timer_that_wrote_no_receipt_is_incomplete_after_grace(self):
        # (::incidents-stale-trigger)
        stale = workflow(None, [trigger("knowledge-digest", "active", "2026-09-14T07:00:00Z")])
        found = derive([stale])
        self.assertEqual([i["key"] for i in found], ["incomplete-run:knowledge-digest"])
        self.assertTrue(any(e.startswith("journalctl -u knowledge-digest") for e in found[0]["evidence"]))
        recent = workflow(None, [trigger("knowledge-digest", "active", "2026-09-14T09:50:00Z")])
        self.assertEqual(derive([recent]), [])
        paused = workflow(None, [trigger("knowledge-digest", "inactive", "2026-09-14T07:00:00Z")])
        self.assertEqual(derive([paused]), [])
        running = workflow(None, [trigger("knowledge-digest", "active", "2026-09-14T07:00:00Z", running=True)])
        self.assertEqual(derive([running]), [])
        receipted = workflow(run("artifact", artifact={"uri": "file:///z"}, ended="2026-09-14T07:30:00Z",
                                 started="2026-09-14T07:01:00Z"),
                             [trigger("knowledge-digest", "active", "2026-09-14T07:00:00Z")])
        self.assertEqual(derive([receipted]), [])

    def test_paused_label_does_not_hide_a_failed_last_run(self):
        paused = workflow(run("failed", failed=("artifact-exists",)), [trigger("knowledge-digest", "inactive")])
        self.assertEqual([i["class"] for i in derive([paused])], ["failed-assertion"])

    def test_contract_unavailable_is_digest_only(self):
        found = derive([workflow(None, contract="unavailable")])
        self.assertEqual([i["key"] for i in found], ["contract-unavailable:knowledge-digest"])
        self.assertEqual(found[0]["failed_assertion"], "contract-available")
        self.assertNotIn("contract-unavailable", wi.IMMEDIATE_CLASSES)

    def test_malformed_receipts_are_keyed_by_path(self):
        # (::incidents-dedup-key)
        two = [{"path": "daily-plan/a.json", "errors": ["missing schema_version"]},
               {"path": "daily-plan/b.json", "errors": ["root is not an object"]}]
        keys_two = [i["key"] for i in derive([], malformed=two)]
        keys_three = [i["key"] for i in derive([], malformed=two + [{"path": "x/c.json", "errors": ["e"]}])]
        self.assertEqual(keys_two, ["malformed-receipt:daily-plan/a.json", "malformed-receipt:daily-plan/b.json"])
        self.assertEqual(keys_three[:2], keys_two)
        self.assertEqual(derive([], malformed=two)[0]["failed_assertion"], "receipt-schema-valid")

    def test_unreadable_receipt_root_is_a_control_failure_and_a_missing_one_is_not(self):
        unreadable = derive([], source_errors=["receipt directory unreadable: Permission denied"])
        self.assertEqual([i["key"] for i in unreadable], ["control-failure:incident-sweep:receipts"])
        not_dir = derive([], source_errors=["receipt path is not a directory: /x"])
        self.assertEqual([i["key"] for i in not_dir], ["control-failure:incident-sweep:receipts"])
        self.assertEqual(derive([], source_errors=["receipt directory unavailable: /x"]), [])
        degraded = derive([], manifest_errors=["marcus.toml: TOMLDecodeError"])
        self.assertEqual([i["key"] for i in degraded], ["control-failure:incident-sweep:manifests"])
        self.assertFalse(wi.sources_visible(["receipt directory unreadable: x"], []))
        self.assertFalse(wi.sources_visible([], ["bad toml"]))
        self.assertTrue(wi.sources_visible(["receipt directory unavailable: x"], []))

    def test_declared_incidents_pass_through_and_resolved_ones_vanish(self):
        # (::incidents-declared)
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            wi.declare(root, {"class": "blocked-next-action", "workflow_id": "daily-plan", "agent": "marcus",
                              "issue": "waiting on Notion", "required_action": "Unblock", "evidence": ["x"],
                              "id": "notion-1"})
            declared, errors = wi.load_declared(root)
            self.assertEqual(errors, [])
            found = derive([], declared=declared)
            self.assertEqual([i["key"] for i in found], ["blocked-next-action:daily-plan:notion-1"])
            self.assertEqual(found[0]["severity"], "medium")
            self.assertTrue(wi.resolve_declared(root, "blocked-next-action:daily-plan:notion-1"))
            declared, _ = wi.load_declared(root)
            self.assertEqual(derive([], declared=declared), [])
            (root / "declared" / "bogus.json").write_text(json.dumps({"class": "not-a-class", "workflow_id": "w",
                                                                       "id": "z"}))
            _, errors = wi.load_declared(root)
            self.assertEqual(len(errors), 1)
            self.assertIn("not-a-class", errors[0])

    def test_declare_and_resolve_round_trip_through_main(self):
        with tempfile.TemporaryDirectory() as temp:
            root = pathlib.Path(temp)
            rc = wi.main(["declare", "--state-dir", temp, "--class", "control-failure", "--workflow", "daily-plan",
                          "--agent", "marcus", "--issue", "resume refused", "--action", "Resume by hand",
                          "--evidence", "/var/lib/control-room/receipts/1.json", "--id", "resume-1"])
            self.assertEqual(rc, 0)
            declared, _ = wi.load_declared(root)
            self.assertEqual(declared[0]["key"], "control-failure:daily-plan:resume-1")
            self.assertIsNone(declared[0]["resolved_at"])
            rc = wi.main(["resolve", "--state-dir", temp, "--key", "control-failure:daily-plan:resume-1"])
            self.assertEqual(rc, 0)
            self.assertIsNotNone(wi.load_declared(root)[0][0]["resolved_at"])
            self.assertEqual(wi.main(["resolve", "--state-dir", temp, "--key", "nope"]), 1)

    def test_parse_systemd_utc_reads_both_forms(self):
        want = dt.datetime(2026, 9, 14, 7, 10, 10, tzinfo=UTC)
        self.assertEqual(wi.parse_systemd_utc("Mon 2026-09-14 07:10:10 UTC"), want)
        self.assertEqual(wi.parse_systemd_utc("2026-09-14T07:10:10Z"), want)
        self.assertIsNone(wi.parse_systemd_utc(""))
        self.assertIsNone(wi.parse_systemd_utc("n/a"))
        self.assertIsNone(wi.parse_systemd_utc(None))

    def test_sanitised_key_is_a_single_path_segment(self):
        self.assertEqual(wi.sanitise_key("malformed-receipt:daily-plan/a.json"), "malformed-receipt_daily-plan_a.json")
        self.assertNotIn("/", wi.sanitise_key("a/../b"))


if __name__ == "__main__":
    unittest.main()
