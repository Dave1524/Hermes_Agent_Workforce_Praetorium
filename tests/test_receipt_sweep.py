#!/usr/bin/env python3
"""bin/receipt_sweep.py: one receipt per finished timer invocation, from systemd's record.

Driven as a subprocess over the fake systemctl in tests/fixtures/receipt-wiring/bin/ (copied
into a sandbox with its sweep-state.tsv), the seven-row fleet-units.tsv fixture and the fixture
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
SELF_ID = "5e" * 16
SELF_STARTED = 1789460000
EXECUTOR = ROOT / "bin" / "contract_exec.py"


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

    def self_receipt(self, *extra: str) -> dict:
        """The run-vantage receipt self-receipting writes for itself, through the real executor."""
        log = self.home / "agent-workforce" / "logs" / "last-attempt" / "self-receipting.log"
        log.parent.mkdir(parents=True, exist_ok=True)
        log.write_text("ran\n")
        cmd = [sys.executable, str(EXECUTOR), "self-receipting", "--vantage", "run", "--run-id", SELF_ID,
               "--artifact", "file:///self/artifact", "--repo-root", str(ROOT), "--manifest-dir", str(FIX / "agents"),
               "--receipt-root", str(self.receipts), "--home", str(self.home),
               "--run-started-at", str(SELF_STARTED), "--now", "2026-09-15T08:15:00Z", *extra]
        done = subprocess.run(cmd, env={"PATH": os.environ["PATH"], "HOME": str(self.home)},
                              capture_output=True, text=True, cwd=str(ROOT))
        assert done.returncode == 0, done.stdout + done.stderr
        return self.read(f"self-receipting/{SELF_ID}.json")

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
                          f"self-receipting/{SELF_ID}.json", "workflow-receipt-sweep/sweep-1.json"])
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
        self.assertIn(f"already receipted: logical-child — logical-parent/{LOGICAL_ID}.json (written by the sweep)",
                      self.box.log_text())
        self.assertEqual(self.box.read("workflow-receipt-sweep/sweep-2.json")["state_change"]["evidence"],
                         "swept 5: 0 written, 0 amended, 1 paused, 1 refused, 3 skipped")

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
        self.assertEqual(own["state_change"]["evidence"], "swept 5: 3 written, 0 amended, 1 paused, 1 refused, 0 skipped")
        self.assertEqual({a["id"]: a["status"] for a in own["assertions"]},
                         {"swept-this-run": "passed", "timer-fired-within-window": "not_applicable"})
        self.assertRegex(self.box.log_text(), r"\n\S+ swept 5: 3 written, 0 amended, 1 paused, 1 refused, 0 skipped\n")

    def test_amends_a_self_receipted_run(self):
        # (::sweep-amends-self-receipted-run) — a unit that receipted its own run recorded its
        # sweep checks n/a; the sweep decides them in place, once, and its own receipt says so
        before = self.box.self_receipt()
        self.assertEqual({a["id"]: a["status"] for a in before["assertions"]},
                         {"attempt-log-exists": "passed", "delivered-after-the-run": "not_applicable",
                          "timer-is-loaded": "not_applicable"})
        done = self.box.sweep("sweep-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"amended: self-receipting — self-receipting/{SELF_ID}.json (decided)", self.box.log_text())
        after = self.box.read(f"self-receipting/{SELF_ID}.json")
        self.assertEqual(receipt.validate(after), [])
        self.assertEqual(after["vantage"], "run")
        self.assertEqual({a["id"]: a["status"] for a in after["assertions"]},
                         {"attempt-log-exists": "passed", "delivered-after-the-run": "passed", "timer-is-loaded": "passed"})
        self.assertEqual(self.assertion(after, "delivered-after-the-run")["output"],
                         f"delivered for the run started @{SELF_STARTED}")
        self.assertEqual(after["terminal"], before["terminal"])
        self.assertEqual(after["artifact"], {"uri": "file:///self/artifact"})
        self.assertEqual(after["swept"]["sweep_run_id"], "sweep-1")
        self.assertEqual(self.box.read("workflow-receipt-sweep/sweep-1.json")["state_change"]["evidence"],
                         "swept 5: 2 written, 1 amended, 1 paused, 1 refused, 0 skipped")
        # the next sweep leaves it alone
        stamp = (self.box.receipts / "self-receipting" / f"{SELF_ID}.json").read_bytes()
        done = self.box.sweep("sweep-2")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"already receipted: self-receipting — self-receipting/{SELF_ID}.json (swept {after['swept']['at']})",
                      self.box.log_text())
        self.assertEqual((self.box.receipts / "self-receipting" / f"{SELF_ID}.json").read_bytes(), stamp)

    def test_a_failed_sweep_check_turns_the_run_receipt_failed(self):
        # (::sweep-amends-self-receipted-run) — the gate T7.3 names: the run receipt exists,
        # a sweep check would fail, and the receipt is `failed` afterwards
        before = self.box.self_receipt()
        self.assertEqual(before["terminal"]["outcome"], "artifact")
        (self.box.home / "delivery-failed").write_text("")
        done = self.box.sweep("sweep-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"amended: self-receipting — self-receipting/{SELF_ID}.json (failed)", self.box.log_text())
        after = self.box.read(f"self-receipting/{SELF_ID}.json")
        self.assertEqual(receipt.validate(after), [])
        self.assertEqual(after["terminal"], {"outcome": "failed",
                                             "reason": "failed sweep checks: delivered-after-the-run; run outcome was artifact"})
        self.assertEqual(self.assertion(after, "delivered-after-the-run")["status"], "failed")
        self.assertEqual(self.assertion(after, "attempt-log-exists"), self.assertion(before, "attempt-log-exists"))
        self.assertEqual(after["artifact"], before["artifact"])
        self.assertTrue(receipt.has_failure(after))
        self.assertFalse(receipt.judged(receipt.close(after, "Dave", "delivery fixed")))
        # a skipped run receipt is not a run, so nothing is swept and nothing is written
        skipped = self.box.self_receipt("--skipped", "previous run still active (flock)")
        self.assertEqual(skipped["assertions"], [])
        done = self.box.sweep("sweep-2")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn(f"already receipted: self-receipting — self-receipting/{SELF_ID}.json (a skip is not a run)",
                      self.box.log_text())
        self.assertNotIn("swept", self.box.read(f"self-receipting/{SELF_ID}.json"))

    @staticmethod
    def assertion(written: dict, ident: str) -> dict:
        return next(a for a in written["assertions"] if a["id"] == ident)

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
