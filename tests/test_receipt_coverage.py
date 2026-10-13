#!/usr/bin/env python3
"""Receipt coverage (T5.2): every standing row has exactly one receipt producer.

Five producers write the one shape in bin/workflow_receipt.py, and which one a row gets is
decided by what systemd execs for it, never by a list kept here: `agent_propose.sh` rows
receipt themselves through bin/propose_receipt.py; `content_change_dispatch.sh` calls the
executor for its tick; every other standing timer ends on `ExecStopPost=-…/receipt_finish.py`,
which records a change of outcome when the run ends (2026-10-13); `receipt_sweep.py` receipts
itself and backfills those timers daily from systemd's record, so a timer without the finish
step is `sweep` and is the finding; the `buzz-agent@*` services are receipted per turn by
bin/interaction_receipt.py, from the Claude Code Stop hook (claude-agent-acp) or codex
`notify` (codex-acp). A row the chain leaves with zero producers, or two, is the finding.
The producible workflow_ids — what each producer would write as `workflow_id` — must equal
the logical set the Control Room lists, so no row can be visible on the screen and
unreceiptable. The tallies are MEASURED 2026-09-22 (T8.4 added agent-config-eval, a swept timer),
pinned the way tests/test_control_room_views.py pins its 32/31. Anchors are the `::` comments;
tests/test_receipt_coverage.sh is the gate entry point.
"""

from __future__ import annotations

import importlib.util
import json
import pathlib
import re
import tempfile
import tomllib
import unittest
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFESTS = ROOT / "design" / "agents"
TSV = ROOT / "config" / "fleet-units.tsv"
SETTINGS = ROOT / "buzz-team" / "agent-settings.json"
EXEC_START = re.compile(r"^ExecStart=(\S+)", re.MULTILINE)
EXEC_STOP_POST = re.compile(r"^ExecStopPost=(.*)$", re.MULTILINE)
FINISH_STEP = "-/home/dave/agent-workforce/bin/receipt_finish.py"

SELF_RECEIPTING = {"agent_propose.sh": "scheduled", "content_change_dispatch.sh": "dispatch",
                   "receipt_sweep.py": "sweep-self"}
EXPECTED_TALLY = {"scheduled": 12, "dispatch": 1, "finish": 12, "sweep-self": 1, "interaction": 5}
LOGICAL_WORKFLOWS = 30


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


def unit_file(row: dict[str, str]) -> pathlib.Path:
    unit_dir = ROOT / "systemd" / "user" if row["scope"] == "user" else ROOT / "systemd"
    return unit_dir / f"{row['unit']}.service"


def exec_start(row: dict[str, str]) -> str | None:
    path = unit_file(row)
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
        classes.add("finish" if last_stop_post(row) == finish_step(row) else "sweep")
    return classes


def last_stop_post(row: dict[str, str]) -> str | None:
    path = unit_file(row)
    lines = EXEC_STOP_POST.findall(path.read_text()) if path.is_file() else []
    return lines[-1].strip() if lines else None


def finish_step(row: dict[str, str]) -> str:
    return f"{FINISH_STEP} --user %N" if row["scope"] == "user" else f"{FINISH_STEP} %N"


def workflow_id(row: dict[str, str]) -> str:
    manifest, _agent = contract_exec.manifest_row(MANIFESTS, row["unit"])
    return str(manifest.get("logical_workflow") or row["unit"])


def platform_units() -> set[str]:
    """Standing platform workflows the finish step must cover: all but the sweep, which receipts itself."""
    units = set()
    for path in sorted(MANIFESTS.glob("*.toml")):
        for entry in tomllib.loads(path.read_text()).get("workflows", []):
            if entry.get("status") == "standing" and entry.get("surface") == "platform":
                units.add(str(entry["unit"]))
    return units - {receipt_sweep.SELF_UNIT}


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
            if self.classes[row["unit"]] not in ({"finish"}, {"sweep"}):
                continue
            with self.subTest(row["unit"]):
                manifest, _agent = contract_exec.manifest_row(MANIFESTS, row["unit"])
                contract = contract_exec.contract_of(manifest, row["unit"], ROOT)
                self.assertTrue(contract.is_file(), contract)

    def test_every_platform_timer_ends_on_the_finish_step(self):
        # (::receipt-coverage-finish-step) — a platform timer without it reaches the Control Room
        # only through the 05:50 sweep, a day late (2026-10-11); `-` and last, so it can never
        # change the job's result or be skipped by an earlier stop-post line that failed
        timers = {row["unit"]: row for row in self.rows if row["kind"] == "timer"}
        platform = sorted(platform_units() & timers.keys())
        self.assertEqual(len(platform), 12, platform)
        for unit in platform:
            with self.subTest(unit):
                self.assertEqual(last_stop_post(timers[unit]), finish_step(timers[unit]))

    def test_the_classifier_tells_finish_from_sweep_on_fixture_units(self):
        # (::receipt-coverage-finish-step) — on fixture unit files, so a classifier that always
        # answered `finish` could not pass on the real tree alone
        step = "ExecStopPost=-/home/dave/agent-workforce/bin/receipt_finish.py"
        cases = {
            "no stop-post": ("system", "ExecStart=/bin/true\n", "sweep"),
            "finish last": ("system", f"ExecStart=/bin/true\n{step} %N\n", "finish"),
            "finish, then another": ("system", f"ExecStart=/bin/true\n{step} %N\nExecStopPost=/bin/true\n", "sweep"),
            "no dash": ("system", "ExecStopPost=/home/dave/agent-workforce/bin/receipt_finish.py %N\n", "sweep"),
            "user unit without --user": ("user", f"{step} %N\n", "sweep"),
            "user unit with --user": ("user", f"{step} --user %N\n", "finish"),
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, (scope, body, want) in cases.items():
                with self.subTest(name):
                    path = pathlib.Path(tmp) / "fixture-job.service"
                    path.write_text(f"[Service]\nType=oneshot\n{body}")
                    row = {"unit": "fixture-job", "scope": scope, "owner": "fixture", "kind": "timer"}
                    with mock.patch(f"{__name__}.unit_file", return_value=path):
                        self.assertEqual(producer_classes(row, {"fixture-job"}), {want})

    def test_no_self_receipting_unit_carries_the_finish_step(self):
        # (::receipt-coverage-finish-step) — it would be a second producer for the same run id
        for row in self.rows:
            if exec_start(row) not in SELF_RECEIPTING:
                continue
            with self.subTest(row["unit"]):
                self.assertNotIn("receipt_finish.py", unit_file(row).read_text())

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
