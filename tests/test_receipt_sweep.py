#!/usr/bin/env python3
"""bin/receipt_sweep.py: one receipt per finished timer invocation, from systemd's record.

Driven as a subprocess over the fake systemctl in tests/fixtures/receipt-wiring/bin/ (copied
into a sandbox with its sweep-state.tsv), the six-row fleet-units.tsv fixture and the fixture
manifests under tests/fixtures/receipt-wiring/agents/ — the real executor runs, so every
receipt on disk is the real shape and the sweep's own receipt exercises the LIVE contract.
Anchors are the `::` comments; tests/test_receipt_sweep.sh is the gate entry point.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "receipt-wiring"
SWEEP = ROOT / "bin" / "receipt_sweep.py"

ENV_PROBE_ID = "e5" * 16
LOGICAL_ID = "1c" * 16


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receipt = load("workflow_receipt")


class Sandbox:
    def __init__(self, tmp: pathlib.Path) -> None:
        self.home = tmp / "home"
        self.fakebin = tmp / "fakebin"
        self.receipts = tmp / "receipts"
        self.log = self.home / "agent-workforce" / "logs" / "receipt_sweep.log"
        for path in (self.home, self.fakebin, self.receipts):
            path.mkdir(parents=True)
        shutil.copy(FIX / "bin" / "systemctl", self.fakebin / "systemctl")
        shutil.copy(FIX / "sweep-state.tsv", self.fakebin / "sweep-state.tsv")
        self.calls = self.fakebin / "calls.log"

    def sweep(self, invocation: str, *extra: str) -> subprocess.CompletedProcess:
        env = {"PATH": f"{self.fakebin}:{os.environ['PATH']}", "HOME": str(self.home),
               "INVOCATION_ID": invocation, "CONTROL_ROOM_RECEIPT_ROOT": str(self.receipts)}
        return subprocess.run([sys.executable, str(SWEEP), "--tsv", str(FIX / "fleet-units.tsv"),
                               "--manifest-dir", str(FIX / "agents"), "--repo-root", str(ROOT), *extra],
                              env=env, capture_output=True, text=True, cwd=str(ROOT))

    def set_state(self, unit: str, column: int, value: str) -> None:
        rows = (self.fakebin / "sweep-state.tsv").read_text().splitlines()
        out = []
        for row in rows:
            cells = row.split("\t")
            if not row.startswith("#") and cells[0] == unit:
                cells[column - 1] = value
                row = "\t".join(cells)
            out.append(row)
        (self.fakebin / "sweep-state.tsv").write_text("\n".join(out) + "\n")

    def receipt_files(self) -> list[str]:
        return sorted(str(p.relative_to(self.receipts)) for p in self.receipts.rglob("*.json"))

    def read(self, relative: str) -> dict:
        return json.loads((self.receipts / relative).read_text())

    def log_text(self) -> str:
        return self.log.read_text() if self.log.exists() else ""


class ReceiptSweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="receipt-sweep-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.box = Sandbox(self.tmp)

    def test_one_receipt_per_finished_invocation(self):
        # (::sweep-one-receipt-per-invocation)
        done = self.box.sweep("sweep-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(self.box.receipt_files(),
                         [f"env-probe/{ENV_PROBE_ID}.json", f"logical-parent/{LOGICAL_ID}.json",
                          "workflow-receipt-sweep/sweep-1.json"])
        probe = self.box.read(f"env-probe/{ENV_PROBE_ID}.json")
        self.assertEqual(receipt.validate(probe), [])
        self.assertEqual(probe["vantage"], "sweep")
        self.assertEqual(probe["unit"], "env-probe")
        self.assertEqual(probe["run_id"], ENV_PROBE_ID)
        self.assertEqual(probe["terminal"]["outcome"], "artifact")
        self.assertIn("Result=success", probe["state_change"]["evidence"])
        self.assertIn(ENV_PROBE_ID, probe["state_change"]["evidence"])
        self.assertEqual(probe["started_at"], "2026-09-15T06:10:00Z")
        self.assertEqual({a["id"]: a["status"] for a in probe["assertions"]},
                         {"secret-probe": "not_applicable", "env-dump": "not_applicable", "sweep-only": "passed"})
        self.assertEqual(probe["usage"]["status"], "unavailable")
        self.assertIn("user show env-probe.timer -p ActiveState --value", self.box.calls.read_text())
        # systemd's Result decides: a run that exited non-zero is receipted as failed
        failed = self.box.read(f"logical-parent/{LOGICAL_ID}.json")
        self.assertEqual(receipt.validate(failed), [])
        self.assertEqual(failed["unit"], "logical-child")
        self.assertEqual(failed["terminal"]["outcome"], "failed")
        self.assertIn("Result=exit-code", failed["terminal"]["reason"])
        self.assertIn("ExecMainStatus=1", failed["terminal"]["reason"])
        # the executor refused the service-kind row: logged, skipped, no receipt, sweep still 0
        self.assertIn("refused: always-on", self.box.log_text())
        self.assertFalse((self.box.receipts / "always-on").exists())
        # a spent row is filtered before systemd is asked anything about it
        self.assertNotIn("spent-job", self.box.calls.read_text())
        self.assertNotIn("spent-job", self.box.log_text())

    def test_paused_timer_writes_nothing(self):
        # (::sweep-paused-writes-nothing)
        done = self.box.sweep("sweep-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("paused: knowledge-digest", self.box.log_text())
        self.assertFalse((self.box.receipts / "knowledge-digest").exists())
        self.assertNotIn("show knowledge-digest.service", self.box.calls.read_text())
        # a service still running at sweep time has no finished run to receipt
        self.box.set_state("env-probe", 9, "active")
        done = self.box.sweep("sweep-2")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("running: env-probe", self.box.log_text())
        # a timer that is active but whose service has not run since boot has no invocation
        self.box.set_state("env-probe", 9, "inactive")
        self.box.set_state("env-probe", 3, "")
        shutil.rmtree(self.box.receipts / "env-probe")
        done = self.box.sweep("sweep-3")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("never ran: env-probe", self.box.log_text())
        self.assertFalse((self.box.receipts / "env-probe").exists())

    def test_never_overwrites(self):
        # (::sweep-never-overwrites)
        self.box.sweep("sweep-1")
        probe = self.box.receipts / "env-probe" / f"{ENV_PROBE_ID}.json"
        marker = json.dumps({"marker": "left by the first sweep"})
        probe.write_text(marker)
        before = self.box.receipt_files()
        done = self.box.sweep("sweep-2")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(probe.read_text(), marker)
        self.assertEqual(self.box.receipt_files(), before + ["workflow-receipt-sweep/sweep-2.json"])
        self.assertIn("already receipted: env-probe", self.box.log_text())
        self.assertIn("already receipted: logical-child", self.box.log_text())
        self.assertEqual(self.box.read("workflow-receipt-sweep/sweep-2.json")["state_change"]["evidence"],
                         "swept 4: 0 written, 1 paused, 1 refused, 2 skipped")

    def test_self_receipt(self):
        # (::sweep-self-receipt)
        done = self.box.sweep("sweep-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        own = self.box.read("workflow-receipt-sweep/sweep-1.json")
        self.assertEqual(receipt.validate(own), [])
        self.assertEqual(own["vantage"], "run")
        self.assertEqual(own["unit"], "workflow-receipt-sweep")
        self.assertEqual(own["agent"], "trajan")
        self.assertEqual(own["terminal"]["outcome"], "artifact")
        self.assertEqual(own["state_change"]["evidence"], "swept 4: 2 written, 1 paused, 1 refused, 0 skipped")
        self.assertEqual({a["id"]: a["status"] for a in own["assertions"]},
                         {"swept-this-run": "passed", "timer-fired-within-window": "not_applicable"})
        self.assertRegex(self.box.log_text(), r"\n\S+ swept 4: 2 written, 1 paused, 1 refused, 0 skipped\n")

    def test_executor_crash_is_the_sweeps_failure(self):
        # (::sweep-self-receipt) — a broken executor cannot write receipts at all, and the sweep says so
        done = self.box.sweep("sweep-1", "--executor", "/bin/false")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(self.box.receipt_files(), [])
        self.assertIn("errored: env-probe", self.box.log_text())

    def test_unit_ships_disabled(self):
        # (::sweep-unit-ships-disabled)
        timer = (ROOT / "systemd" / "workflow-receipt-sweep.timer").read_text()
        self.assertIn("[Install]", timer)
        self.assertIn("WantedBy=timers.target", timer)
        self.assertIn("OnCalendar=*-*-* 05:50", timer)
        service = (ROOT / "systemd" / "workflow-receipt-sweep.service").read_text()
        self.assertIn("ExecStart=/home/dave/agent-workforce/bin/receipt_sweep.py", service)
        self.assertIn("OnFailure=agent-alert@%n.service", service)
        pattern = "enable.*" + "workflow-receipt" + "-sweep"   # split so this line is not a hit
        grep = subprocess.run(["grep", "-rlE", "--exclude-dir=__pycache__", pattern,
                               "bin", "tests", "systemd", "buzz-team"],
                              cwd=str(ROOT), capture_output=True, text=True)
        self.assertEqual(grep.stdout.strip(), "", f"something enables the sweep timer: {grep.stdout}")
        self.assertIn("workflow-receipt-sweep\tsystem\tstanding\ttrajan\ttimer",
                      (ROOT / "config" / "fleet-units.tsv").read_text())


if __name__ == "__main__":
    unittest.main()
