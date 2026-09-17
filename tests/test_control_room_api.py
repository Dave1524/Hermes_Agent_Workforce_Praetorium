#!/usr/bin/env python3
"""Fixture tests for the read-only Control Room backend."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import pathlib
import tempfile
import threading
import unittest
import urllib.error
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("control_room_api", ROOT / "bin" / "control_room_api.py")
assert SPEC and SPEC.loader
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)
import control_room_state as state  # noqa: E402  (bin/ is on sys.path once the module above ran)


CONTRACT = """# Contract: {unit}

## Identity

| | |
|---|---|
| Unit | `{unit}.service` / `.timer` |
| Owner | **{owner}** |
| Surface | platform |

## Trigger

Every hour.

## Inputs

`input.txt`, current; refuse if absent.

## Outputs

- **Artifact:** one JSON receipt.
- **Beneficiary:** Dave.
- **Next actor:** Dave.
- **Next action:** Review the result.
- **Benefit hypothesis:** failures become visible.
- **Benefit signal:** acknowledged incidents.

## Decline conditions

None.

## Side effects

Writes its own receipt.

## Acceptance checks

1. The artifact exists.

   ```check id=artifact-exists when=run
   [ -f "$AGENT_ATTEMPT_LOG" ]
   ```

## Known failure modes

Missing output.
"""


class FakeSystemd:
    """Answers as `systemctl show --timestamp=utc` prints them; `paused` flips every timer off;
    `user_units` answers the user bus per unit name (absent = the bus is unreachable)."""

    def __init__(self, paused: bool = False, user_units: dict | None = None,
                 active_since: str = "Thu 2026-09-10 06:00:00 UTC") -> None:
        self.paused = paused
        self.user_units = user_units
        self.active_since = active_since

    def show(self, name: str, scope: str):
        if scope == "user":
            if self.user_units is None:
                return {}, "user bus unavailable in fixture"
            return dict(self.user_units.get(name) or {"ActiveState": "inactive", "SubState": "dead"}), None
        if name.endswith(".timer"):
            if self.paused:
                return {"ActiveState": "inactive", "SubState": "dead", "UnitFileState": "disabled",
                        "LastTriggerUSec": "", "NextElapseUSecRealtime": "", "Persistent": "yes"}, None
            return {
                "ActiveState": "active",
                "SubState": "waiting",
                "UnitFileState": "enabled",
                "ActiveEnterTimestamp": self.active_since,
                "LastTriggerUSec": "Thu 2026-09-10 08:00:00 UTC",
                "NextElapseUSecRealtime": "Thu 2026-09-10 09:00:00 UTC",
                "Persistent": "yes",
            }, None
        return {"ActiveState": "inactive", "SubState": "dead", "Result": "success", "ExecMainStatus": "0"}, None


class ControlRoomApiTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.repo = root / "repo"
        self.runtime = root / "runtime"
        self.receipts = self.runtime / "var" / "workflow-receipts"
        (self.repo / "design" / "agents").mkdir(parents=True)
        (self.repo / "design" / "contracts").mkdir(parents=True)
        self.receipts.mkdir(parents=True)
        (self.repo / "design" / "agents" / "marcus.toml").write_text(
            'name="marcus"\n[[workflows]]\nunit="daily-plan"\nsurface="scheduled"\n'
            'trigger="daily"\nstatus="standing"\ncontract="design/contracts/daily-plan.md"\n'
        )
        (self.repo / "design" / "agents" / "augustus.toml").write_text(
            'name="augustus"\n[[workflows]]\nunit="augustus-content"\nlogical_workflow="augustus-content"\n'
            'surface="buzz_dispatch"\ntrigger="daily"\nstatus="standing"\ncontract="design/contracts/augustus-content.md"\n'
            'requires=["buzz-agent@aurelian", "user/buzz-notion-broker"]\n'
            '[[workflows]]\nunit="content-change-dispatch"\nlogical_workflow="augustus-content"\n'
            'surface="buzz_dispatch"\ntrigger="every 15 min"\nstatus="standing"\ncontract="design/contracts/augustus-content.md"\n'
            'requires=["buzz-agent@aurelian", "user/buzz-notion-broker"]\n'
        )
        (self.repo / "systemd" / "user").mkdir(parents=True)
        (self.repo / "systemd" / "user" / "buzz-notion-broker.service").write_text("[Unit]\nDescription=fixture broker\n")
        (self.repo / "design" / "agents" / "aurelian.toml").write_text(
            'name="aurelian"\n[[workflows]]\nunit="buzz-agent@aurelian"\nsurface="interactive"\nscope="user"\n'
            'kind="service"\ntrigger="event-driven"\nstatus="standing"\n'
        )
        (self.repo / "design" / "agents" / "trajan.toml").write_text(
            'name="trajan"\n[[workflows]]\nunit="drift-check"\nsurface="platform"\n'
            'trigger="daily"\nstatus="standing"\ncontract="design/contracts/drift-check.md"\n'
            'what="Compares source against the deployed tree for Dave."\n'
            'requires=["system/ollama.service"]\n'
            'guards="Without it a hand edit under /etc is caught by nothing."\n'
            '[[workflows]]\nunit="spent-kickoff"\nsurface="scheduled"\ntrigger="once, 2026-08-03"\n'
            'status="spent"\ncontract_exempt="spent: its one date fired 2026-08-03; nothing is promised any more"\n'
        )
        (self.repo / "design" / "contracts" / "daily-plan.md").write_text(CONTRACT.format(unit="daily-plan", owner="marcus"))
        (self.repo / "design" / "contracts" / "drift-check.md").write_text(CONTRACT.format(unit="drift-check", owner="trajan"))
        (self.repo / "design" / "contracts" / "augustus-content.md").write_text(CONTRACT.format(unit="augustus-content", owner="augustus"))
        self.now = dt.datetime(2026, 9, 11, 8, 0, tzinfo=dt.timezone.utc)
        self.model = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(),
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_receipt(self, workflow="daily-plan", run="run-1", outcome="artifact", measured=False,
                      vantage=None, ended_at="2026-09-11T07:01:00Z"):
        target = self.receipts / workflow
        target.mkdir(exist_ok=True)
        usage = {
            "status": "measured" if measured else "unavailable",
            "input_tokens": 10 if measured else None,
            "output_tokens": 5 if measured else None,
            "cache_tokens": 2 if measured else None,
            "total_tokens": 17 if measured else None,
        }
        cost = {
            "status": "measured" if measured else "unavailable",
            "amount": 0.01 if measured else None,
            "currency": "USD" if measured else None,
            "source": "runtime" if measured else None,
            "confidence": "exact" if measured else None,
        }
        body = {
            "schema_version": 1,
            "workflow_id": workflow,
            "run_id": run,
            "unit": workflow,
            "agent": "marcus",
            "model": "claude-sonnet-5",
            "started_at": "2026-09-11T07:00:00Z",
            "ended_at": ended_at,
            "terminal": {"outcome": outcome, "reason": "failed checks: artifact-exists" if outcome == "failed" else None},
            "artifact": {"uri": "https://notion.so/demo", "title": "Daily plan"} if outcome == "artifact" else None,
            "state_change": None,
            "assertions": [{"id": "artifact-exists", "status": "failed" if outcome == "failed" else "passed", "message": "ok"}],
            "usage": usage,
            "cost": cost,
            "next_action": {"actor": "Dave", "action": "Review", "due_at": None},
            "parent_run_id": None,
            "handoff": None,
        }
        if vantage:
            body["vantage"] = vantage
            body["agent"] = workflow.partition("@")[2]
            body["unit"] = workflow
        (target / f"{run}.json").write_text(json.dumps(body))

    def test_reconciles_two_triggers_to_one_logical_workflow(self):
        response = self.model.list_workflows({"role": ["all"]})
        ids = [item["id"] for item in response["items"]]
        self.assertEqual(ids, ["augustus-content", "buzz-agent@aurelian", "daily-plan", "drift-check"])
        content = response["items"][0]
        self.assertEqual([trigger["unit"] for trigger in content["triggers"]], ["augustus-content", "content-change-dispatch"])

    def test_role_is_derived_from_surface_by_one_function(self):  # (::control-room-role)
        items = {item["id"]: item for item in self.model.list_workflows({"role": ["all"]})["items"]}
        self.assertEqual((items["daily-plan"]["surface"], items["daily-plan"]["role"]), ("scheduled", "agent-workflow"))
        self.assertEqual((items["augustus-content"]["surface"], items["augustus-content"]["role"]), ("buzz_dispatch", "agent-workflow"))
        self.assertEqual((items["drift-check"]["surface"], items["drift-check"]["role"]), ("platform", "system-workflow"))
        self.assertEqual((items["buzz-agent@aurelian"]["surface"], items["buzz-agent@aurelian"]["role"]), ("interactive", "agent-runtime"))
        for item in items.values():
            for trigger in item["triggers"]:
                self.assertEqual(trigger["surface"], item["surface"])
        self.assertEqual(state.role_of("platform"), "system-workflow")
        with self.assertRaises(ValueError):
            state.role_of("kanban")
        with self.assertRaises(ValueError):
            state.role_of(None)

    def test_runtimes_leave_the_list_at_the_http_layer_only(self):  # (::control-room-role)
        default_ids = [item["id"] for item in self.model.list_workflows({})["items"]]
        self.assertEqual(default_ids, ["augustus-content", "daily-plan", "drift-check"])
        model_ids = [item["id"] for item in self.model.workflows()[0]]
        self.assertIn("buzz-agent@aurelian", model_ids)
        detail, _ = self.model.workflow_detail("buzz-agent@aurelian")
        self.assertEqual(detail["role"], "agent-runtime")
        only_runtimes = [item["id"] for item in self.model.list_workflows({"role": ["agent-runtime"]})["items"]]
        self.assertEqual(only_runtimes, ["buzz-agent@aurelian"])

    def test_requires_rows_are_tri_state_from_the_bus(self):  # (::control-room-requires)
        items = {item["id"]: item for item in self.model.list_workflows({"role": ["all"]})["items"]}
        self.assertEqual(items["augustus-content"]["requires"], [
            {"unit": "buzz-agent@aurelian", "scope": "user", "workflow": "buzz-agent@aurelian", "state": "unknown", "satisfied": None},
            {"unit": "buzz-notion-broker", "scope": "user", "workflow": None, "state": "unknown", "satisfied": None},
        ])
        self.assertEqual(items["drift-check"]["requires"],
                         [{"unit": "ollama.service", "scope": "system", "workflow": None, "state": "inactive", "satisfied": False}])
        self.assertEqual(items["daily-plan"]["requires"], [])
        self.assertEqual(items["drift-check"]["guards"], "Without it a hand edit under /etc is caught by nothing.")
        self.assertIsNone(items["daily-plan"]["guards"])
        up = FakeSystemd(user_units={"buzz-agent@aurelian.service": {"ActiveState": "active", "SubState": "running"}})
        model = api.ControlRoomReadModel(api.SourcePaths(self.repo, self.runtime, self.receipts), systemd=up, clock=lambda: self.now)
        rows = {item["id"]: item for item in model.list_workflows({"role": ["all"]})["items"]}
        self.assertEqual([(r["unit"], r["state"], r["satisfied"]) for r in rows["augustus-content"]["requires"]],
                         [("buzz-agent@aurelian", "active", True), ("buzz-notion-broker", "inactive", False)])

    def test_required_by_carries_the_dependent_and_whether_it_is_enabled(self):  # (::control-room-requires)
        items = {item["id"]: item for item in self.model.list_workflows({"role": ["all"]})["items"]}
        self.assertEqual(items["buzz-agent@aurelian"]["requiredBy"], [{"workflow": "augustus-content", "enabled": True}])
        self.assertEqual(items["augustus-content"]["requiredBy"], [])
        self.assertEqual(items["drift-check"]["requiredBy"], [])
        paused = api.ControlRoomReadModel(api.SourcePaths(self.repo, self.runtime, self.receipts),
                                          systemd=FakeSystemd(paused=True), clock=lambda: self.now)
        rows = {item["id"]: item for item in paused.list_workflows({"role": ["all"]})["items"]}
        self.assertEqual(rows["augustus-content"]["control"]["state"], "paused")
        self.assertEqual(rows["buzz-agent@aurelian"]["requiredBy"], [{"workflow": "augustus-content", "enabled": False}])
        agent, _ = self.model.agent_detail("aurelian")
        self.assertEqual(agent["requiredBy"], [{"workflow": "augustus-content", "enabled": True}])

    def test_dependency_down_is_an_exception_only_while_the_dependent_runs(self):  # (::control-room-dependency-down)
        rows = [row for row in self.model.exceptions()["items"] if row["kind"] == "dependency-down"]
        self.assertEqual([(row["workflowId"], row["issue"]) for row in rows],
                         [("drift-check", "requires ollama.service (system): inactive")])
        self.assertFalse(rows[0]["paused"])
        paused = api.ControlRoomReadModel(api.SourcePaths(self.repo, self.runtime, self.receipts),
                                          systemd=FakeSystemd(paused=True), clock=lambda: self.now)
        self.assertEqual([row for row in paused.exceptions()["items"] if row["kind"] == "dependency-down"], [])
        self.assertNotIn("augustus-content", {row["workflowId"] for row in rows},
                         "an unreachable bus is unknown, and unknown is not an exception")

    def test_agents_are_one_per_persona_manifest(self):  # (::control-room-agents)
        items = self.model.agents()["items"]
        self.assertEqual([item["name"] for item in items], ["augustus", "aurelian", "marcus", "trajan"])
        by_name = {item["name"]: item for item in items}
        aurelian = by_name["aurelian"]
        self.assertEqual(aurelian["runtime"], {"unit": "buzz-agent@aurelian", "scope": "user", "state": "unknown",
                                               "since": None, "unitFileState": "unknown"})
        self.assertEqual(aurelian["health"], "unknown")
        self.assertEqual([a["id"] for a in aurelian["control"]["actions"]], ["start", "stop", "restart"])
        self.assertTrue(all(a["enabled"] is False and a["reason"] == "systemd state unavailable"
                            for a in aurelian["control"]["actions"]), aurelian["control"]["actions"])
        self.assertEqual(aurelian["control"]["state"], "unknown")
        self.assertIsNone(aurelian["lastTurn"])
        self.assertEqual(aurelian["turns7d"], 0)
        self.assertEqual(aurelian["usage7d"]["status"], "unavailable")
        self.assertIsNone(aurelian["usage7d"]["totalTokens"])
        self.assertEqual(aurelian["cost7d"]["status"], "unavailable")
        self.assertIsNone(aurelian["cost7d"]["amount"])
        self.assertEqual(aurelian["ownedWorkflows"], [])
        self.assertEqual(aurelian["requiredBy"], [{"workflow": "augustus-content", "enabled": True}])
        self.assertEqual(by_name["marcus"]["runtime"], {"unit": None, "scope": None, "state": "unknown", "since": None,
                                                        "unitFileState": None})
        self.assertIsNone(by_name["marcus"]["control"])
        self.assertEqual(by_name["marcus"]["ownedWorkflows"], [{"id": "daily-plan", "role": "agent-workflow"}])
        self.assertEqual(by_name["augustus"]["ownedWorkflows"], [{"id": "augustus-content", "role": "agent-workflow"}])
        self.assertEqual(by_name["trajan"]["ownedWorkflows"], [{"id": "drift-check", "role": "system-workflow"}])
        detail, _ = self.model.agent_detail("aurelian")
        self.assertEqual(detail["name"], "aurelian")
        self.assertIsNone(self.model.agent_detail("nobody")[0])

    def test_agent_turns_come_from_interaction_receipts_only(self):  # (::control-room-agents)
        self.write_receipt(workflow="buzz-agent@aurelian", run="turn-1", measured=True, vantage="interaction")
        self.write_receipt(workflow="buzz-agent@aurelian", run="turn-0", measured=True, vantage="interaction",
                           ended_at="2026-09-01T07:01:00Z")
        self.write_receipt(workflow="daily-plan", run="run-1", measured=True)
        aurelian = next(item for item in self.model.agents()["items"] if item["name"] == "aurelian")
        self.assertEqual(aurelian["lastTurn"]["id"], "turn-1")
        self.assertEqual(aurelian["lastTurn"]["outcome"], "artifact")
        self.assertEqual(aurelian["turns7d"], 1)
        self.assertEqual(aurelian["usage7d"], {"status": "measured", "inputTokens": 10, "outputTokens": 5,
                                               "cacheTokens": 2, "totalTokens": 17})
        self.assertEqual(aurelian["cost7d"], {"status": "measured", "amount": 0.01, "currency": "USD"})
        marcus = next(item for item in self.model.agents()["items"] if item["name"] == "marcus")
        self.assertIsNone(marcus["lastTurn"])
        self.assertEqual(marcus["usage7d"]["status"], "unavailable")

    def test_agent_runtime_state_buckets(self):  # (::control-room-agents)
        model = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(user_units={"buzz-agent@aurelian.service": {
                "ActiveState": "active", "SubState": "running", "UnitFileState": "enabled",
                "ExecMainStartTimestamp": "Thu 2026-09-11 06:00:00 UTC"}}),
            clock=lambda: self.now,
        )
        aurelian = next(item for item in model.agents()["items"] if item["name"] == "aurelian")
        self.assertEqual(aurelian["runtime"]["state"], "active")
        self.assertEqual(aurelian["runtime"]["since"], "2026-09-11T06:00:00Z")
        self.assertEqual(aurelian["runtime"]["unitFileState"], "enabled")
        actions = {a["id"]: a for a in aurelian["control"]["actions"]}
        self.assertEqual((actions["start"]["enabled"], actions["stop"]["enabled"], actions["restart"]["enabled"]),
                         (False, True, True))
        self.assertEqual(actions["start"]["reason"], "runtime is active, not paused")
        self.assertEqual(model.overview()["summary"]["agents"], {"total": 4, "up": 1, "down": 0, "unknown": 3})
        down = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(user_units={"buzz-agent@aurelian.service": {
                "ActiveState": "failed", "SubState": "failed", "ExecMainExitTimestamp": "Thu 2026-09-11 06:30:00 UTC"}}),
            clock=lambda: self.now,
        )
        aurelian = next(item for item in down.agents()["items"] if item["name"] == "aurelian")
        self.assertEqual((aurelian["runtime"]["state"], aurelian["runtime"]["since"]), ("failed", "2026-09-11T06:30:00Z"))
        self.assertEqual(down.overview()["summary"]["agents"], {"total": 4, "up": 0, "down": 1, "unknown": 3})
        self.assertEqual(aurelian["control"]["state"], "paused", "a failed always-on service is startable")
        actions = {a["id"]: a for a in aurelian["control"]["actions"]}
        self.assertEqual((actions["start"]["enabled"], actions["stop"]["enabled"], actions["restart"]["enabled"]),
                         (True, False, False))
        self.assertEqual(actions["stop"]["reason"], "runtime is paused, not active")

    def test_runtime_row_control_is_the_runtime_vocabulary(self):  # (::control-room-runtime-control)
        row, _ = self.model.workflow_detail("buzz-agent@aurelian")
        self.assertEqual([a["id"] for a in row["control"]["actions"]], ["start", "stop", "restart"])
        self.assertEqual(row["control"]["source"], "unavailable")
        daily, _ = self.model.workflow_detail("daily-plan")
        self.assertEqual([a["id"] for a in daily["control"]["actions"]], ["pause", "resume", "run_now", "retry", "stop"])
        self.assertEqual(state.control_actions("paused", "systemd", "agent-runtime")[0],
                         {"id": "start", "enabled": True, "reason": None})
        self.assertEqual(state.control_actions("active", "systemd", "system-workflow")[0]["id"], "pause")
        self.assertEqual(state.RUNTIME_ACTION_IDS, ("start", "stop", "restart"))

    def test_contract_exempt_is_a_declaration_not_a_degraded_source(self):
        item, status = self.model.workflow_detail("spent-kickoff")
        self.assertEqual((item["contractStatus"], item["contractError"]), ("exempt", None))
        self.assertEqual(item["contractExempt"], "spent: its one date fired 2026-08-03; nothing is promised any more")
        self.assertEqual((status["contracts"], status["errors"]["contracts"]), ("available", []))
        self.assertFalse(any(i["id"] == "contract-unavailable:spent-kickoff" for i in self.model.incidents()["items"]))
        self.assertEqual(self.model.list_workflows({"lifecycle": ["all"]})["dataStatus"]["errors"]["contracts"],
                         ["buzz-agent@aurelian: contract not declared"])

    def test_detail_status_describes_this_workflow_not_the_list(self):
        item, status = self.model.workflow_detail("daily-plan")
        self.assertEqual(item["contractExempt"], None)
        self.assertEqual((status["contracts"], status["errors"]["contracts"]), ("available", []))
        self.assertEqual((status["systemd"], status["errors"]["systemd"]), ("available", []))
        (self.receipts / "daily-plan").mkdir(exist_ok=True)
        (self.receipts / "daily-plan" / "bad.json").write_text("{")
        _, status = self.model.workflow_detail("daily-plan")
        self.assertEqual((status["receipts"], [m["path"] for m in status["errors"]["malformedReceipts"]]), ("degraded", ["daily-plan/bad.json"]))
        _, other = self.model.workflow_detail("drift-check")
        self.assertEqual((other["receipts"], other["errors"]["malformedReceipts"]), ("available", []))
        _, aurelian = self.model.workflow_detail("buzz-agent@aurelian")
        self.assertEqual(aurelian["contracts"], "degraded")
        self.assertEqual(aurelian["errors"]["contracts"], ["buzz-agent@aurelian: contract not declared"])
        self.assertEqual(aurelian["systemd"], "degraded")
        self.assertTrue(all(e.startswith("buzz-agent@aurelian: ") for e in aurelian["errors"]["systemd"]), aurelian["errors"]["systemd"])

    def test_missing_contract_and_user_bus_are_visible(self):
        response = self.model.list_workflows({"role": ["all"]})
        aurelian = next(item for item in response["items"] if item["id"] == "buzz-agent@aurelian")
        self.assertEqual(aurelian["contractStatus"], "unavailable")
        self.assertEqual(aurelian["health"], "unknown")
        self.assertEqual(aurelian["triggers"][0]["systemd"]["status"], "unavailable")
        incidents = self.model.incidents()["items"]
        self.assertTrue(any(item["id"] == "contract-unavailable:buzz-agent@aurelian" for item in incidents))

    def test_unavailable_usage_is_null_never_zero(self):
        self.write_receipt(measured=False)
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual(daily["usage"]["status"], "unavailable")
        self.assertIsNone(daily["usage"]["total_tokens"])
        self.assertEqual(daily["cost"]["status"], "unavailable")
        self.assertIsNone(daily["cost"]["amount"])

    def test_measured_usage_aggregates_by_agent(self):
        self.write_receipt(measured=True)
        marcus = next(item for item in self.model.usage()["items"] if item["agent"] == "marcus")
        self.assertEqual(marcus["usage"]["totalTokens"], 17)
        self.assertEqual(marcus["cost"]["amount"], 0.01)

    def test_malformed_receipt_is_an_incident(self):
        target = self.receipts / "daily-plan"
        target.mkdir()
        (target / "bad.json").write_text('{"not":"a receipt"}')
        incidents = self.model.incidents()["items"]
        malformed = next(item for item in incidents if item["failedAssertion"] == "receipt-schema-valid")
        self.assertIn("missing schema_version", malformed["issue"])

    def test_malformed_receipt_ids_are_path_keyed_and_stable(self):  # (::incidents-api-dedup-key)
        target = self.receipts / "daily-plan"
        target.mkdir()
        (target / "a.json").write_text('{"not":"a receipt"}')
        (target / "b.json").write_text('[]')
        first = sorted(item["id"] for item in self.model.incidents()["items"] if item["class"] == "malformed-receipt")
        self.assertEqual(first, ["malformed-receipt:daily-plan/a.json", "malformed-receipt:daily-plan/b.json"])
        (target / "c.json").write_text('{')
        second = sorted(item["id"] for item in self.model.incidents()["items"] if item["class"] == "malformed-receipt")
        self.assertEqual(second[:2], first)
        self.assertEqual(len(second), 3)

    def test_failed_receipt_is_an_incident_even_when_the_timer_is_paused(self):  # (::incidents-api-failed)
        self.write_receipt(outcome="failed")
        paused = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts), systemd=FakeSystemd(paused=True),
            clock=lambda: self.now,
        )
        response = paused.incidents()
        found = [item for item in response["items"] if item["workflowId"] == "daily-plan"]
        self.assertEqual([item["id"] for item in found], ["failed-assertion:daily-plan"])
        item = found[0]
        self.assertEqual((item["class"], item["key"], item["status"]), ("failed-assertion", "failed-assertion:daily-plan", "open"))
        self.assertEqual(item["runId"], "run-1")
        self.assertEqual(item["failedAssertion"], "artifact-exists")
        self.assertIn("daily-plan/run-1.json", item["evidence"])
        for field in ("firstSeen", "lastSeen", "resolvedAt", "notifiedAt", "observations"):
            self.assertIn(field, item)
        self.assertEqual(response["dataStatus"]["incidentState"], "unavailable")

    def test_artifact_and_decline_receipts_yield_no_run_incident(self):  # (::incidents-api-silence)
        self.write_receipt(run="run-1", outcome="artifact")
        self.write_receipt(run="run-2", outcome="decline")
        found = [item for item in self.model.incidents()["items"] if item["workflowId"] == "daily-plan"]
        self.assertEqual(found, [])

    def test_state_file_merges_notified_and_resolved_entries(self):  # (::incidents-api-state-merge)
        self.write_receipt(outcome="failed")
        state_dir = self.runtime / "var" / "incidents"
        state_dir.mkdir(parents=True)
        entry = {"key": "failed-assertion:daily-plan", "class": "failed-assertion", "severity": "high",
                 "workflow_id": "daily-plan", "agent": "marcus", "unit": "daily-plan", "issue": "x",
                 "failed_assertion": "artifact-exists", "required_action": "Review", "run_id": "run-1",
                 "run_ids": ["run-1"], "observations": 3, "evidence": [], "first_seen": "2026-09-09T07:01:00Z",
                 "last_seen": "2026-09-11T07:55:00Z", "resolved_at": None, "notified_at": "2026-09-09T07:05:00Z",
                 "notify_event_id": "e1", "notify_channel": "c1", "send_attempts": 1, "last_send_error": None,
                 "recovery_notified_at": None, "digested_at": None}
        resolved = dict(entry, key="incomplete-run:daily-plan", **{"class": "incomplete-run"},
                        resolved_at="2026-09-10T09:00:00Z", first_seen="2026-09-10T07:00:00Z")
        (state_dir / "state.json").write_text(json.dumps({"schema": 1, "last_digest_at": None, "incidents": {
            entry["key"]: entry, resolved["key"]: resolved}}))
        response = self.model.incidents()
        self.assertEqual(response["dataStatus"]["incidentState"], "available")
        by_id = {item["id"]: item for item in response["items"]}
        live = by_id["failed-assertion:daily-plan"]
        self.assertEqual((live["status"], live["firstSeen"], live["notifiedAt"], live["observations"]),
                         ("open", "2026-09-09T07:01:00Z", "2026-09-09T07:05:00Z", 3))
        self.assertEqual(live["runId"], "run-1")
        gone = by_id["incomplete-run:daily-plan"]
        self.assertEqual((gone["status"], gone["resolvedAt"]), ("resolved", "2026-09-10T09:00:00Z"))
        self.assertEqual([item["status"] for item in response["items"]].count("resolved"), 1)
        self.assertNotIn("incomplete-run:daily-plan", [item["id"] for item in self.model.overview()["needsAttention"]])

    def test_artifact_outcome_requires_evidence(self):
        self.write_receipt()
        path = self.receipts / "daily-plan" / "run-1.json"
        data = json.loads(path.read_text())
        data["artifact"] = None
        path.write_text(json.dumps(data))
        _, malformed, _ = self.model.receipts()
        self.assertIn("artifact outcome has no artifact URI or state-change evidence", malformed[0]["errors"])

    def test_filters_and_unknown_workflow(self):
        items = self.model.list_workflows({"agent": ["marcus"]})["items"]
        self.assertEqual([item["id"] for item in items], ["daily-plan"])
        detail, _ = self.model.workflow_detail("does-not-exist")
        self.assertIsNone(detail)

    def test_control_state_and_next_run(self):  # (::control-room-control-state)
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual(daily["control"]["state"], "active")
        self.assertEqual(daily["control"]["source"], "systemd")
        self.assertEqual(daily["control"]["nextRunAt"], "2026-09-10T09:00:00Z")
        self.assertIs(daily["control"]["nextRunEstimated"], False)
        self.assertEqual(daily["control"]["lastTriggerAt"], "2026-09-10T08:00:00Z")
        self.assertIsNone(daily["control"]["lastAction"])
        actions = {action["id"]: action for action in daily["control"]["actions"]}
        self.assertEqual(sorted(actions), ["pause", "resume", "retry", "run_now", "stop"])
        self.assertTrue(actions["run_now"]["enabled"])
        self.assertTrue(actions["pause"]["enabled"])
        self.assertFalse(actions["resume"]["enabled"])
        self.assertFalse(actions["retry"]["enabled"])
        self.assertIn("idempotent", actions["retry"]["reason"])
        self.assertEqual(daily["triggers"][0]["systemd"]["timer"]["lastTriggerAt"], "2026-09-10T08:00:00Z")
        self.assertEqual(daily["triggers"][0]["systemd"]["timer"]["raw"]["lastTriggerAt"], "Thu 2026-09-10 08:00:00 UTC")
        self.assertEqual(daily["triggers"][0]["systemd"]["timer"]["activeSince"], "2026-09-10T06:00:00Z")
        self.assertEqual(daily["triggers"][0]["systemd"]["timer"]["firedAt"], "2026-09-10T08:00:00Z")
        self.assertEqual(daily["control"]["lastFiredAt"], "2026-09-10T08:00:00Z")

        paused_model = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(paused=True),
            clock=lambda: self.now,
        )
        daily = next(item for item in paused_model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual(daily["health"], "paused")
        self.assertEqual(daily["control"]["state"], "paused")
        self.assertIsNone(daily["control"]["nextRunAt"])
        actions = {action["id"]: action for action in daily["control"]["actions"]}
        self.assertTrue(actions["resume"]["enabled"])
        self.assertFalse(actions["pause"]["enabled"])
        self.assertFalse(actions["stop"]["enabled"])


    def test_a_trigger_read_back_from_the_stamp_on_resume_is_not_a_fire(self):  # (::control-room-stamp-not-a-fire)
        resumed = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(active_since="Thu 2026-09-10 08:00:01 UTC"), clock=lambda: self.now,
        )
        daily = next(item for item in resumed.list_workflows({})["items"] if item["id"] == "daily-plan")
        timer = daily["triggers"][0]["systemd"]["timer"]
        self.assertEqual((timer["lastTriggerAt"], timer["activeSince"]), ("2026-09-10T08:00:00Z", "2026-09-10T08:00:01Z"))
        self.assertIsNone(timer["firedAt"])
        self.assertIsNone(daily["control"]["lastFiredAt"])
        self.assertEqual(daily["control"]["lastTriggerAt"], "2026-09-10T08:00:00Z")

    def test_the_fake_answers_only_properties_the_live_reader_requests(self):  # (::control-room-reader-properties)
        fake = FakeSystemd(user_units={"buzz-agent@aurelian.service": {"ActiveState": "active", "SubState": "running"}})
        answered = set()
        for name, scope in (("daily-plan.timer", "system"), ("daily-plan.service", "system"),
                            ("buzz-agent@aurelian.service", "user")):
            values, error = fake.show(name, scope)
            self.assertIsNone(error)
            answered |= set(values)
        self.assertEqual(answered - set(api.SystemdReader.PROPERTIES), set())

    def test_last_eligible_run_looks_past_a_skip(self):  # (::control-room-last-eligible-run)
        self.write_receipt(run="run-1", outcome="artifact")
        self.write_receipt(run="run-2", outcome="skipped", ended_at="2026-09-11T07:08:28Z")
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual((daily["lastRun"]["id"], daily["lastRun"]["outcome"]), ("run-2", "skipped"))
        self.assertEqual((daily["lastEligibleRun"]["id"], daily["lastEligibleRun"]["outcome"]), ("run-1", "artifact"))
        self.assertEqual(daily["health"], "incomplete")
        self.assertNotIn("missing-artifact", [row["kind"] for row in self.model.exceptions()["items"]
                                              if row["workflowId"] == "daily-plan"])
        self.assertEqual([i["id"] for i in self.model.incidents()["items"] if i["workflowId"] == "daily-plan"], [])
    def run_kinds(self, workflow_id: str) -> list[str]:
        """The run-judging exception kinds on a row; missed-cadence is the fixture timer's own."""
        return sorted(row["kind"] for row in self.model.exceptions()["items"]
                      if row["workflowId"] == workflow_id and row["kind"] in {"failed", "stale-input", "missing-artifact"})

    def test_a_closed_failure_is_looked_past_everywhere(self):  # (::control-room-closed-run)
        self.write_receipt(run="run-1", outcome="failed", ended_at="2026-09-11T07:02:00Z")
        self.write_receipt(run="run-0", outcome="failed", ended_at="2026-09-11T07:01:00Z")
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual((daily["health"], daily["lastEligibleRun"]["id"], daily["eligibleRuns"]), ("failed", "run-1", 2))
        self.assertEqual(self.run_kinds("daily-plan"), ["failed", "missing-artifact"])
        path = self.receipts / "daily-plan" / "run-1.json"
        receipt = json.loads(path.read_text())
        receipt["closed"] = {"at": "2026-09-11T07:30:00Z", "by": "Dave", "reason": "artifact-exists read the wrong path"}
        path.write_text(json.dumps(receipt))
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual((daily["lastRun"]["id"], daily["lastRun"]["outcome"], daily["lastRun"]["closed"]["by"]),
                         ("run-1", "failed", "Dave"))
        self.assertEqual((daily["health"], daily["lastEligibleRun"]["id"], daily["eligibleRuns"]), ("failed", "run-0", 1))
        self.assertEqual([i["runId"] for i in self.model.incidents()["items"] if i["workflowId"] == "daily-plan"], ["run-0"])
        receipt = json.loads((self.receipts / "daily-plan" / "run-0.json").read_text())
        receipt["closed"] = {"at": "2026-09-11T07:30:00Z", "by": "Dave", "reason": "same defect"}
        (self.receipts / "daily-plan" / "run-0.json").write_text(json.dumps(receipt))
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual((daily["health"], daily["lastEligibleRun"], daily["eligibleRuns"], daily["validArtifactRate"]),
                         ("unknown", None, 0, None))
        self.assertEqual(self.run_kinds("daily-plan"), [])
        self.assertEqual([i for i in self.model.incidents()["items"] if i["workflowId"] == "daily-plan"], [])
        by_day = {d["day"]: d for d in self.model.overview()["reliability7d"]["days"]}
        self.assertEqual(by_day["2026-09-11"], {"day": "2026-09-11", "eligible": 0, "valid": 0})
        self.assertEqual(self.model.run_detail("run-1")[0]["closed"]["reason"], "artifact-exists read the wrong path")

    def test_control_reader_hook_fills_last_action_verbatim(self):
        last = {"action": "pause", "actor": "Dave", "result": "applied"}
        model = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(),
            clock=lambda: self.now,
            control_reader=lambda workflow_id: last if workflow_id == "daily-plan" else None,
        )
        items = {item["id"]: item for item in model.list_workflows({})["items"]}
        self.assertEqual(items["daily-plan"]["control"]["lastAction"], last)
        self.assertIsNone(items["augustus-content"]["control"]["lastAction"])

    def test_contract_gains_inputs_decline_and_task_ids(self):
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        contract = daily["contract"]
        self.assertEqual(contract["inputs"], [])
        self.assertEqual(contract["decline_conditions"], "None.")
        self.assertEqual(contract["task_ids"], [])
        self.assertEqual(daily["links"]["contractLocal"], "/api/v1/workflows/daily-plan/contract")
        self.assertTrue(daily["links"]["contractGithub"].endswith("design/contracts/daily-plan.md"))
        self.assertIsNone(daily["lastValidArtifact"])
        self.assertEqual(daily["artifactFreshness"], "unknown")
        self.write_receipt(measured=True)
        daily = next(item for item in self.model.list_workflows({})["items"] if item["id"] == "daily-plan")
        self.assertEqual(daily["lastValidArtifact"]["uri"], "https://notion.so/demo")
        self.assertEqual(daily["lastValidArtifact"]["kind"], "artifact")
        self.assertEqual(daily["lastValidArtifact"]["ageSeconds"], 3540)

    def test_reliability_7d_counts_eligible_and_valid_per_utc_day(self):  # (::control-room-overview-reliability)
        self.write_receipt(run="run-a", outcome="artifact")
        self.write_receipt(run="run-b", outcome="failed")
        self.write_receipt(run="run-c", outcome="skipped")
        self.write_receipt(run="run-d", outcome="decline")
        stale = self.receipts / "daily-plan" / "run-d.json"
        stale.write_text(stale.read_text().replace("2026-09-11T07:0", "2026-09-09T07:0"))
        series = self.model.overview()["reliability7d"]
        self.assertEqual(series["status"], "measured")
        days = series["days"]
        self.assertEqual([d["day"] for d in days], [f"2026-09-{n:02d}" for n in range(5, 12)])
        by_day = {d["day"]: d for d in days}
        self.assertEqual(by_day["2026-09-11"], {"day": "2026-09-11", "eligible": 2, "valid": 1})
        self.assertEqual(by_day["2026-09-09"], {"day": "2026-09-09", "eligible": 1, "valid": 0})
        self.assertEqual(by_day["2026-09-10"], {"day": "2026-09-10", "eligible": 0, "valid": 0})
        for day in days:
            self.assertGreaterEqual(day["eligible"], day["valid"], day)

    def test_reliability_7d_is_unavailable_without_receipts(self):  # (::control-room-overview-reliability)
        model = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.runtime / "no-such-dir"),
            systemd=FakeSystemd(),
            clock=lambda: self.now,
        )
        overview = model.overview()
        self.assertEqual(overview["dataStatus"]["receipts"], "unavailable")
        self.assertEqual(overview["reliability7d"], {"status": "unavailable", "days": []})

    def test_http_routes_are_read_only_and_fail_closed(self):
        server = api.make_server("127.0.0.1", 0, self.model)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        base = f"http://127.0.0.1:{server.server_port}"
        try:
            with urllib.request.urlopen(base + "/api/v1/overview", timeout=3) as response:
                payload = json.load(response)
                self.assertEqual(response.status, 200)
                self.assertEqual(payload["summary"]["workflows"], 3)
                self.assertEqual(payload["summary"]["agents"], {"total": 4, "up": 0, "down": 0, "unknown": 4})
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            with urllib.request.urlopen(base + "/api/v1/agents/aurelian", timeout=3) as response:
                self.assertEqual(json.load(response)["items"]["name"], "aurelian")
            with urllib.request.urlopen(base + "/api/v1/workflows/buzz-agent@aurelian/runs", timeout=3) as response:
                self.assertEqual(json.load(response)["items"], [])
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(base + "/api/v1/agents/nobody", timeout=3)
            self.assertEqual(raised.exception.code, 404)
            self.assertEqual(json.load(raised.exception), {"error": "agent not found"})
            raised.exception.close()
            request = urllib.request.Request(base + "/api/v1/workflows/daily-plan", method="POST", data=b"{}")
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 405)
            raised.exception.close()
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(base + "/api/v1/workflows/%2e%2e", timeout=3)
            self.assertEqual(raised.exception.code, 400)
            raised.exception.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
