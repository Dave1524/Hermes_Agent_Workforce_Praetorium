#!/usr/bin/env python3
"""bin/receipt_finish.py: a platform timer's receipt the moment its run ends, when the outcome moved.

Driven as a subprocess, with the environment systemd hands ExecStopPost, over the fake systemctl
in tests/fixtures/receipt-wiring/bin/ and a fixture platform contract
(tests/fixtures/contract-exec/contracts/platform-job.md). The real executor runs, so every
receipt on disk is the real shape. The end-to-end case runs the real bin/receipt_sweep.py over
what the finish step wrote. Anchors are the `::` comments; tests/test_receipt_finish.sh is the
gate entry point.
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
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "receipt-wiring"
FINISH = ROOT / "bin" / "receipt_finish.py"
SWEEP = ROOT / "bin" / "receipt_sweep.py"
CLOSE = ROOT / "bin" / "receipt_close.py"
UNIT = "platform-job"
STATE_HEADER = "# unit\ttimer_active\tinvocation_id\texec_main_start\texec_main_exit\tresult\texec_main_status\tlast_trigger\tservice_active\n"
MANIFEST = f"""name = "platform"

[[workflows]]
unit     = "{UNIT}"
surface  = "platform"
trigger  = "fixture"
contract = "tests/fixtures/contract-exec/contracts/platform-job.md"
status   = "standing"

[[workflows]]
unit     = "user-job"
surface  = "platform"
trigger  = "fixture"
scope    = "user"
contract = "tests/fixtures/contract-exec/contracts/platform-job.md"
status   = "standing"
"""


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receipt = load("workflow_receipt")


def run_id(n: int) -> str:
    return f"{n:02x}" * 16


class Sandbox:
    def __init__(self, tmp: pathlib.Path) -> None:
        self.home, self.fakebin, self.receipts, self.agents = (tmp / d for d in ("home", "fakebin", "receipts", "agents"))
        for path in (self.home, self.fakebin, self.receipts, self.agents):
            path.mkdir(parents=True)
        shutil.copy(FIX / "bin" / "systemctl", self.fakebin / "systemctl")
        shutil.copy(FIX / "agents" / "trajan.toml", self.agents / "trajan.toml")
        (self.agents / "platform.toml").write_text(MANIFEST)
        self.tsv = tmp / "fleet-units.tsv"
        self.tsv.write_text(f"{UNIT}\tsystem\tstanding\tfixture\ttimer\n")
        self.state(run_id(1), "success", "0")

    def state(self, invocation: str, result: str, status: str) -> None:
        row = [UNIT, "active", invocation, "@1789452600", "@1789452660", result, status, "@1789452600", "inactive"]
        user = ["user-job", "active", invocation, "@1789452600", "@1789452660", result, status, "@1789452600", "inactive"]
        (self.fakebin / "sweep-state.tsv").write_text(STATE_HEADER + "\t".join(row) + "\n" + "\t".join(user) + "\n")

    def env(self, **extra: str) -> dict[str, str]:
        return {"PATH": f"{self.fakebin}:{os.environ['PATH']}", "HOME": str(self.home), **extra}

    def finish(self, invocation: str | None, result: str, status: str | None = "0", code: str | None = "exited",
               *args: str, unit: str = UNIT, **env: str) -> subprocess.CompletedProcess:
        stop_post = {"SERVICE_RESULT": result, **env}
        if code is not None:
            stop_post.update(EXIT_CODE=code, EXIT_STATUS=status or "")
        if invocation is not None:
            stop_post["INVOCATION_ID"] = invocation
        cmd = [sys.executable, str(FINISH), "--receipt-root", str(self.receipts), "--manifest-dir", str(self.agents),
               "--repo-root", str(ROOT), *args, unit]
        return subprocess.run(cmd, env=self.env(**stop_post), capture_output=True, text=True, cwd=str(ROOT), timeout=60)

    def sweep(self) -> subprocess.CompletedProcess:
        return subprocess.run([sys.executable, str(SWEEP), "--tsv", str(self.tsv), "--manifest-dir", str(self.agents),
                               "--repo-root", str(ROOT), "--receipt-root", str(self.receipts)],
                              env=self.env(INVOCATION_ID="5e" * 16), capture_output=True, text=True, cwd=str(ROOT))

    def files(self) -> list[str]:
        return sorted(str(p.relative_to(self.receipts)) for p in self.receipts.rglob("*.json"))

    def read(self, invocation: str) -> dict:
        return json.loads((self.receipts / UNIT / f"{invocation}.json").read_text())


class FinishStep(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="receipt-finish-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.box = Sandbox(self.tmp)

    def assertLine(self, done: subprocess.CompletedProcess, prefix: str) -> None:
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        lines = done.stdout.splitlines()
        self.assertEqual(len(lines), 1, done.stdout)
        self.assertTrue(lines[0].startswith(prefix), lines[0])

    def test_first_run_is_recorded(self):
        # (::finish-writes-on-change)
        done = self.box.finish(run_id(1), "success")
        self.assertLine(done, f"receipt: written {UNIT}/{run_id(1)}.json (none -> artifact)")
        got = self.box.read(run_id(1))
        self.assertEqual(receipt.validate(got), [])
        self.assertEqual(got["vantage"], "run")
        self.assertEqual(got["terminal"]["outcome"], "artifact")
        self.assertIn(f"systemd: {UNIT}.service {run_id(1)} Result=success ExecMainStatus=0 exited 2026-09-15T06:11:00Z",
                      got["state_change"]["evidence"])
        self.assertEqual(got["started_at"], "2026-09-15T06:10:00Z")
        self.assertEqual({a["id"]: (a["status"], a.get("reason")) for a in got["assertions"]},
                         {"failure-alerted": ("not_applicable", "vantage"), "timer-is-loaded": ("not_applicable", "vantage")})

    def test_an_unchanged_outcome_is_left_to_the_sweep(self):
        # (::finish-skips-unchanged)
        self.box.finish(run_id(1), "success")
        done = self.box.finish(run_id(2), "success")
        self.assertLine(done, "receipt: unchanged (artifact), left to the sweep")
        self.assertEqual(self.box.files(), [f"{UNIT}/{run_id(1)}.json"])
        self.box.finish(run_id(3), "exit-code", "1")
        done = self.box.finish(run_id(4), "exit-code", "1")
        self.assertLine(done, "receipt: unchanged (failed), left to the sweep")

    def test_every_flip_is_recorded_with_its_reason(self):
        # (::finish-writes-on-change)
        self.box.finish(run_id(1), "success")
        done = self.box.finish(run_id(2), "exit-code", "3")
        self.assertLine(done, f"receipt: written {UNIT}/{run_id(2)}.json (artifact -> failed)")
        self.assertEqual(self.box.read(run_id(2))["terminal"]["reason"], "Result=exit-code ExecMainStatus=3")
        done = self.box.finish(run_id(3), "success")
        self.assertLine(done, f"receipt: written {UNIT}/{run_id(3)}.json (failed -> artifact)")

    def test_a_closed_failure_is_not_the_outcome_compared(self):
        # (::finish-compares-judged) — the incident reads lastEligibleRun, so the finish step does too
        self.box.finish(run_id(1), "success")
        self.box.finish(run_id(2), "exit-code", "1")
        closed = subprocess.run([sys.executable, str(CLOSE), UNIT, run_id(2), "--by", "suite", "--reason", "fixture",
                                 "--root", str(self.box.receipts)], capture_output=True, text=True)
        self.assertEqual(closed.returncode, 0, closed.stdout + closed.stderr)
        self.assertLine(self.box.finish(run_id(3), "success"), "receipt: unchanged (artifact)")
        self.assertLine(self.box.finish(run_id(4), "exit-code", "1"),
                        f"receipt: written {UNIT}/{run_id(4)}.json (artifact -> failed)")

    def test_a_failed_sweep_check_is_not_undone_by_the_next_clean_run(self):
        # (::finish-compares-systemd-verdict) — the run exited 0 and its alert check failed at
        # 05:50; only the sweep can clear that, or the incident flaps resolved/reopened daily
        (self.box.home / "alert-missing").write_text("")
        self.box.finish(run_id(1), "success")
        self.box.sweep()
        self.assertEqual(self.box.read(run_id(1))["terminal"]["outcome"], "failed")
        self.assertLine(self.box.finish(run_id(2), "success"), "receipt: unchanged (artifact)")
        self.assertLine(self.box.finish(run_id(3), "exit-code", "1"),
                        f"receipt: written {UNIT}/{run_id(3)}.json (artifact -> failed)")

    def test_newest_is_by_end_time_not_by_run_id(self):
        # (::finish-compares-judged) — systemd's invocation ids are random, so their order is not time
        self.box.finish(run_id(0xf0), "success")
        self.box.finish(run_id(0x01), "exit-code", "1")
        self.assertLine(self.box.finish(run_id(0x80), "success"),
                        f"receipt: written {UNIT}/{run_id(0x80)}.json (failed -> artifact)")

    def test_a_malformed_receipt_is_not_the_one_compared(self):
        # (::finish-compares-judged) — the Control Room drops what does not validate, so does this
        self.box.finish(run_id(1), "success")
        bad = self.box.read(run_id(1))
        bad.update(run_id=None, ended_at="2099-01-01T00:00:00Z", terminal={"outcome": "failed", "reason": "x"},
                   state_change={"evidence": f"systemd: {UNIT}.service x Result=exit-code ExecMainStatus=1"})
        (self.box.receipts / UNIT / "malformed.json").write_text(json.dumps(bad))
        self.assertLine(self.box.finish(run_id(2), "success"), "receipt: unchanged (artifact)")

    def test_a_failed_start_pre_still_gets_systemd_numbers(self):
        # (::finish-same-evidence-as-sweep) — EXIT_CODE/EXIT_STATUS are unset when ExecStartPre=
        # failed; the sweep would read ExecMainStatus from systemctl, so the finish step does too
        self.box.state(run_id(1), "exit-code", "0")
        done = self.box.finish(run_id(1), "exit-code", None, None)
        self.assertLine(done, "receipt: written")
        self.assertEqual(self.box.read(run_id(1))["terminal"]["reason"], "Result=exit-code ExecMainStatus=0")

    def test_a_signal_is_recorded_as_systemctl_numbers_it(self):
        # (::finish-same-evidence-as-sweep)
        done = self.box.finish(run_id(1), "signal", "TERM", "killed")
        self.assertLine(done, "receipt: written")
        self.assertEqual(self.box.read(run_id(1))["terminal"]["reason"], "Result=signal ExecMainStatus=15")

    def test_a_user_unit_asks_the_user_manager(self):
        # (::finish-same-evidence-as-sweep)
        done = self.box.finish(run_id(1), "success", "0", "exited", "--user", unit="user-job")
        self.assertLine(done, "receipt: written user-job/")
        self.assertIn("user show user-job.service", (self.box.fakebin / "calls.log").read_text())

    def test_no_invocation_id_writes_nothing(self):
        # (::finish-never-fails-the-job)
        done = self.box.finish(None, "success")
        self.assertLine(done, "receipt: errored no INVOCATION_ID")
        self.assertEqual(self.box.files(), [])

    def test_an_unknown_unit_is_errored_not_raised(self):
        # (::finish-never-fails-the-job)
        done = self.box.finish(run_id(1), "success", unit="not-in-any-manifest")
        self.assertLine(done, "receipt: errored")
        self.assertEqual(self.box.files(), [])

    def test_an_executor_refusal_is_errored(self):
        # (::finish-never-fails-the-job)
        stub = self.box.fakebin / "refuse"
        stub.write_text("#!/bin/sh\necho 'refused: fixture' >&2\nexit 2\n")
        stub.chmod(0o755)
        done = self.box.finish(run_id(1), "success", "0", "exited", "--executor", str(stub))
        self.assertLine(done, "receipt: errored executor exit 2")
        self.assertEqual(self.box.files(), [])

    def test_a_hung_executor_is_cut_off(self):
        # (::finish-never-fails-the-job) — stop-post time counts against the unit's TimeoutStopSec
        stub = self.box.fakebin / "hang"
        stub.write_text("#!/bin/sh\nexec sleep 30\n")
        stub.chmod(0o755)
        started = time.monotonic()
        done = self.box.finish(run_id(1), "success", "0", "exited", "--executor", str(stub), "--timeout", "1")
        self.assertLess(time.monotonic() - started, 15)
        self.assertLine(done, "receipt: errored executor timed out after 1s")

    def test_the_sweep_amends_what_the_finish_step_wrote(self):
        # (::finish-then-sweep-amends) — one file, the sweep checks decided in place
        self.box.state(run_id(5), "exit-code", "1")
        (self.box.home / "alert-missing").write_text("")
        self.assertLine(self.box.finish(run_id(5), "exit-code", "1"), "receipt: written")
        swept = self.box.sweep()
        log = (self.box.home / "agent-workforce" / "logs" / "receipt_sweep.log").read_text()
        self.assertIn(f"amended: {UNIT} — {UNIT}/{run_id(5)}.json", log, swept.stdout + swept.stderr)
        got = self.box.read(run_id(5))
        self.assertEqual(got["vantage"], "run")
        self.assertIn("swept", got)
        self.assertEqual({a["id"]: a["status"] for a in got["assertions"]},
                         {"failure-alerted": "failed", "timer-is-loaded": "passed"})
        self.assertEqual([f for f in self.box.files() if f.startswith(UNIT)], [f"{UNIT}/{run_id(5)}.json"])


if __name__ == "__main__":
    unittest.main(verbosity=1)
