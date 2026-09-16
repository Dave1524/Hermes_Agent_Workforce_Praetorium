#!/usr/bin/env python3
"""Receipt coverage (T5.2): every standing row has exactly one receipt producer.

Four producers write the one shape in bin/workflow_receipt.py, and which one a row gets is
decided by what systemd execs for it, never by a list kept here: `agent_propose.sh` rows
receipt themselves through bin/propose_receipt.py; `content_change_dispatch.sh` calls the
executor for its tick; `receipt_sweep.py` receipts itself and sweeps every other standing
timer from systemd's record; the `buzz-agent@*` services are receipted per turn by
bin/interaction_receipt.py, from the Claude Code Stop hook (claude-agent-acp) or codex
`notify` (codex-acp). A row the chain leaves with zero producers, or two, is the finding.
The producible workflow_ids — what each producer would write as `workflow_id` — must equal
the logical set the Control Room lists, so no row can be visible on the screen and
unreceiptable. The tallies are MEASURED 2026-09-16 (T6.1 retired memory-consolidation),
pinned the way tests/test_control_room_views.py pins its 32/31. Anchors are the `::` comments;
tests/test_receipt_coverage.sh is the gate entry point.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "design" / "agents"
TSV = ROOT / "config" / "fleet-units.tsv"
SETTINGS = ROOT / "buzz-team" / "agent-settings.json"
EXEC_START = re.compile(r"^ExecStart=(\S+)", re.MULTILINE)

SELF_RECEIPTING = {"agent_propose.sh": "scheduled", "content_change_dispatch.sh": "dispatch",
                   "receipt_sweep.py": "sweep-self"}
EXPECTED_TALLY = {"scheduled": 11, "dispatch": 1, "sweep": 14, "sweep-self": 1, "interaction": 5}
LOGICAL_WORKFLOWS = 31


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


contract_exec = load("contract_exec")
receipt_sweep = load("receipt_sweep")


def standing_rows() -> list[dict[str, str]]:
    rows = []
    for line in TSV.read_text().splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        unit, scope, status, owner, kind = (c.strip() for c in line.split("\t")[:5])
        if status == "standing":
            rows.append({"unit": unit, "scope": scope, "owner": owner, "kind": kind})
    return rows


def exec_start(row: dict[str, str]) -> str | None:
    unit_dir = ROOT / "systemd" / "user" if row["scope"] == "user" else ROOT / "systemd"
    path = unit_dir / f"{row['unit']}.service"
    if not path.is_file():
        return None
    match = EXEC_START.search(path.read_text())
    return pathlib.Path(match.group(1)).name if match else None


def producer_classes(row: dict[str, str], swept: set[str]) -> set[str]:
    classes = set()
    if row["kind"] == "service" and row["unit"].startswith("buzz-agent@"):
        classes.add("interaction")
    program = exec_start(row)
    if program in SELF_RECEIPTING:
        classes.add(SELF_RECEIPTING[program])
    if row["kind"] == "timer" and row["unit"] in swept and program not in SELF_RECEIPTING:
        classes.add("sweep")
    return classes


def workflow_id(row: dict[str, str]) -> str:
    manifest, _agent = contract_exec.manifest_row(MANIFESTS, row["unit"])
    return str(manifest.get("logical_workflow") or row["unit"])


def logical_set() -> set[str]:
    ids = set()
    for path in sorted(MANIFESTS.glob("*.toml")):
        for entry in tomllib.loads(path.read_text()).get("workflows", []):
            if entry.get("status") == "standing":
                ids.add(str(entry.get("logical_workflow") or entry["unit"]))
    return ids


def harness_of(unit: str) -> str:
    agent = unit.partition("@")[2]
    return str(tomllib.loads((MANIFESTS / f"{agent}.toml").read_text()).get("harness"))


class EveryStandingRow(unittest.TestCase):
    def setUp(self):
        self.rows = standing_rows()
        self.swept = {unit for unit, _scope in receipt_sweep.standing_timers(TSV)}
        self.classes = {row["unit"]: producer_classes(row, self.swept) for row in self.rows}

    def test_exactly_one_producer_each(self):
        # (::receipt-coverage-every-standing-row)
        wrong = {unit: sorted(classes) for unit, classes in self.classes.items() if len(classes) != 1}
        self.assertEqual(wrong, {}, "rows with zero or several producers")
        tally = {}
        for classes in self.classes.values():
            tally[next(iter(classes))] = tally.get(next(iter(classes)), 0) + 1
        self.assertEqual(tally, EXPECTED_TALLY)

    def test_producible_ids_are_the_logical_set(self):
        # (::receipt-coverage-every-standing-row) — the sweep and the self-receipting rows write
        # the manifest's logical id (contract_exec.build_receipt); the hook writes the unit
        producible = set()
        for row in self.rows:
            producible.add(row["unit"] if self.classes[row["unit"]] == {"interaction"} else workflow_id(row))
        self.assertEqual(producible, logical_set())
        self.assertEqual(len(producible), LOGICAL_WORKFLOWS)

    def test_swept_rows_are_executable_at_sweep_vantage(self):
        # (::receipt-coverage-every-standing-row) — a swept row the executor would refuse (no
        # manifest row, no contract, kind=service) is a receipt the sweep logs as `refused`
        # every morning and never writes
        for row in self.rows:
            if self.classes[row["unit"]] != {"sweep"}:
                continue
            with self.subTest(row["unit"]):
                manifest, _agent = contract_exec.manifest_row(MANIFESTS, row["unit"])
                contract = contract_exec.contract_of(manifest, row["unit"], ROOT)
                self.assertTrue(contract.is_file(), contract)

    def test_interaction_rows_are_hooked(self):
        # (::receipt-coverage-every-standing-row) — claude-agent-acp agents run the Stop hook
        # agent-settings.json declares; the codex-acp agent's `notify` lives in his own
        # config.toml outside the repo, so only the CLI half is assertable here
        stop_hooks = json.loads(SETTINGS.read_text()).get("hooks", {}).get("Stop", [])
        commands = [hook.get("command", "") for group in stop_hooks for hook in group.get("hooks", [])]
        self.assertTrue(any("interaction_receipt.py" in c for c in commands), commands)
        self.assertIn("--codex-notify", (ROOT / "bin" / "interaction_receipt.py").read_text())
        for row in self.rows:
            if self.classes[row["unit"]] != {"interaction"}:
                continue
            with self.subTest(row["unit"]):
                self.assertIn(harness_of(row["unit"]), {"claude-agent-acp", "codex-acp"})

    def test_self_receipting_producers_name_the_writer(self):
        # (::receipt-coverage-every-standing-row) — the ExecStart basename is the claim; the
        # script naming the writer is the evidence
        self.assertIn("propose_receipt.py", (ROOT / "bin" / "agent_propose.sh").read_text())
        self.assertIn("contract_exec.py", (ROOT / "bin" / "content_change_dispatch.sh").read_text())
        self.assertIn("receipt_self", (ROOT / "bin" / "receipt_sweep.py").read_text())
        self.assertTrue((ROOT / "bin" / "propose_receipt.py").is_file())


if __name__ == "__main__":
    unittest.main()
