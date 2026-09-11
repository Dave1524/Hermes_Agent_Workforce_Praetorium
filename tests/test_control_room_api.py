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
    def show(self, name: str, scope: str):
        if scope == "user":
            return {}, "user bus unavailable in fixture"
        if name.endswith(".timer"):
            return {
                "ActiveState": "active",
                "SubState": "waiting",
                "UnitFileState": "enabled",
                "LastTriggerUSec": "Thu 2026-09-10 08:00:00 CEST",
                "NextElapseUSecRealtime": "Thu 2026-09-10 09:00:00 CEST",
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
            '[[workflows]]\nunit="content-change-dispatch"\nlogical_workflow="augustus-content"\n'
            'surface="buzz_dispatch"\ntrigger="every 15 min"\nstatus="standing"\ncontract="design/contracts/augustus-content.md"\n'
        )
        (self.repo / "design" / "agents" / "aurelian.toml").write_text(
            'name="aurelian"\n[[workflows]]\nunit="buzz-agent@aurelian"\nsurface="interactive"\nscope="user"\n'
            'kind="service"\ntrigger="event-driven"\nstatus="standing"\n'
        )
        (self.repo / "design" / "contracts" / "daily-plan.md").write_text(CONTRACT.format(unit="daily-plan", owner="marcus"))
        (self.repo / "design" / "contracts" / "augustus-content.md").write_text(CONTRACT.format(unit="augustus-content", owner="augustus"))
        self.now = dt.datetime(2026, 9, 11, 8, 0, tzinfo=dt.timezone.utc)
        self.model = api.ControlRoomReadModel(
            api.SourcePaths(self.repo, self.runtime, self.receipts),
            systemd=FakeSystemd(),
            clock=lambda: self.now,
        )

    def tearDown(self):
        self.temp.cleanup()

    def write_receipt(self, workflow="daily-plan", run="run-1", outcome="artifact", measured=False):
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
            "ended_at": "2026-09-11T07:01:00Z",
            "terminal": {"outcome": outcome, "reason": None},
            "artifact": {"uri": "https://notion.so/demo", "title": "Daily plan"} if outcome == "artifact" else None,
            "state_change": None,
            "assertions": [{"id": "artifact-exists", "status": "passed", "message": "ok"}],
            "usage": usage,
            "cost": cost,
            "next_action": {"actor": "Dave", "action": "Review", "due_at": None},
            "parent_run_id": None,
            "handoff": None,
        }
        (target / f"{run}.json").write_text(json.dumps(body))

    def test_reconciles_two_triggers_to_one_logical_workflow(self):
        response = self.model.list_workflows({})
        ids = [item["id"] for item in response["items"]]
        self.assertEqual(ids, ["augustus-content", "buzz-agent@aurelian", "daily-plan"])
        content = response["items"][0]
        self.assertEqual([trigger["unit"] for trigger in content["triggers"]], ["augustus-content", "content-change-dispatch"])

    def test_missing_contract_and_user_bus_are_visible(self):
        response = self.model.list_workflows({})
        aurelian = next(item for item in response["items"] if item["id"] == "buzz-agent@aurelian")
        self.assertEqual(aurelian["contractStatus"], "unavailable")
        self.assertEqual(aurelian["health"], "unknown")
        self.assertEqual(aurelian["triggers"][0]["systemd"]["status"], "unavailable")
        incidents = self.model.incidents()["items"]
        self.assertTrue(any(item["id"] == "contract-buzz-agent@aurelian" for item in incidents))

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
                self.assertEqual(response.headers["Cache-Control"], "no-store")
            request = urllib.request.Request(base + "/api/v1/workflows/daily-plan", method="POST", data=b"{}")
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(request, timeout=3)
            self.assertEqual(raised.exception.code, 405)
            with self.assertRaises(urllib.error.HTTPError) as raised:
                urllib.request.urlopen(base + "/api/v1/workflows/%2e%2e", timeout=3)
            self.assertEqual(raised.exception.code, 400)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


if __name__ == "__main__":
    unittest.main()
