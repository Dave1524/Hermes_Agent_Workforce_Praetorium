#!/usr/bin/env python3
"""Fixture tests for bin/control_room_lineage.py — six research stages, Unknown when a source is absent."""

from __future__ import annotations

import pathlib
import sys
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from control_room_fixture import build_model  # noqa: E402

import control_room_lineage as lineage  # noqa: E402


def fixture_item(workflow_id):
    items, _ = build_model().workflows()
    return next(item for item in items if item["id"] == workflow_id)


def latest_receipt(workflow_id):
    receipts, _, _ = build_model().receipts()
    return next((r for r in receipts if r["workflow_id"] == workflow_id), None)


def flat(value):
    return " ".join(value) if isinstance(value, list) else (value or "")


class LineageSixStages(unittest.TestCase):  # (::lineage-six-stages)
    def setUp(self):
        self.stages = {s["stage"]: s for s in lineage.lineage(fixture_item("agent-proposal"), latest_receipt("agent-proposal"))}

    def test_stage_order_and_shape(self):
        stages = lineage.lineage(fixture_item("agent-proposal"), latest_receipt("agent-proposal"))
        self.assertEqual([s["stage"] for s in stages], list(lineage.STAGES))
        self.assertEqual(lineage.STAGES, ("source", "selection", "trigger", "agent", "output", "human_action"))
        for stage in stages:
            self.assertEqual(set(stage), {"stage", "value", "source"})
            self.assertIn(stage["source"], {"contract", "manifest", "receipt", "systemd", None})

    def test_source_names_the_contract_inputs(self):
        source = self.stages["source"]
        self.assertEqual(source["source"], "contract")
        self.assertIsInstance(source["value"], list)
        self.assertTrue(any("04_operations/box_brief/queue.md" in v for v in source["value"]))

    def test_selection_carries_the_rule_and_the_decline_reason(self):
        selection = self.stages["selection"]
        self.assertEqual(selection["source"], "contract")
        self.assertIn("DECLINE: no open queue item", flat(selection["value"]))
        self.assertIn("legitimate decline", flat(selection["value"]))

    def test_trigger_is_manifest_text_plus_control_state(self):
        trigger = self.stages["trigger"]
        self.assertEqual(trigger["source"], "manifest")
        self.assertIn("Mon..Fri 04:30", flat(trigger["value"]))
        self.assertIn("paused", flat(trigger["value"]))

    def test_agent_is_owner_plus_receipt_model(self):
        agent = self.stages["agent"]
        self.assertEqual(agent["source"], "receipt")
        self.assertIn("claudius", flat(agent["value"]))
        self.assertIn("claude-opus-5", flat(agent["value"]))

    def test_output_is_unknown_when_no_valid_artifact(self):
        self.assertIsNone(self.stages["output"]["value"])
        self.assertIsNone(self.stages["output"]["source"])

    def test_output_labels_notion_by_host(self):
        stages = {s["stage"]: s for s in lineage.lineage(fixture_item("praetorium-daily-plan"),
                                                          latest_receipt("praetorium-daily-plan"))}
        self.assertEqual(stages["output"]["source"], "receipt")
        self.assertTrue(flat(stages["output"]["value"]).startswith("Notion"))
        self.assertIn("https://www.notion.so/", flat(stages["output"]["value"]))

    def test_human_action_is_contract_next_actor_and_action(self):
        human = self.stages["human_action"]
        self.assertEqual(human["source"], "contract")
        self.assertIn("Dave", flat(human["value"]))
        self.assertIn("promote", flat(human["value"]))

    def test_human_action_appends_receipt_due_date(self):
        stages = {s["stage"]: s for s in lineage.lineage(fixture_item("overnight-morning-report"),
                                                          latest_receipt("overnight-morning-report"))}
        self.assertIn("2026-09-12T08:00:00Z", flat(stages["human_action"]["value"]))

    def test_output_label_by_scheme_for_non_notion(self):
        self.assertEqual(lineage.output_label("https://www.notion.so/x"), "Notion")
        self.assertEqual(lineage.output_label("https://acme.notion.site/x"), "Notion")
        self.assertEqual(lineage.output_label("file:///home/dave/x.md"), "file")
        self.assertEqual(lineage.output_label("https://example.com/x"), "https")


class LineageUnknownStage(unittest.TestCase):  # (::lineage-unknown-stage)
    def test_no_contract_and_no_receipt_is_six_unknowns(self):
        item = {"id": "x", "owner": None, "contract": None, "triggers": [], "control": {"state": "unknown"},
                "lastValidArtifact": None}
        stages = lineage.lineage(item, None)
        self.assertEqual(len(stages), 6)
        for stage in stages:
            with self.subTest(stage=stage["stage"]):
                self.assertIsNone(stage["value"])
                self.assertIsNone(stage["source"])

    def test_fixture_items_carry_lineage(self):
        item = fixture_item("agent-proposal")
        self.assertEqual([s["stage"] for s in item["lineage"]], list(lineage.STAGES))


if __name__ == "__main__":
    unittest.main()
