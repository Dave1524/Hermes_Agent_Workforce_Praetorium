#!/usr/bin/env python3
"""bin/propose_receipt.py: an agent_propose.sh outcome -> the executor's argv -> one receipt.

Driven as a subprocess with CONTRACT_EXEC pointed at a recording stub (argv assertions) and,
for the read-back test, at a wrapper around the real executor over T5.1's fixture manifest.
Anchors are the `::` comments; tests/test_propose_receipt.sh is the gate entry point.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "receipt-wiring"
EXEC_FIX = ROOT / "tests" / "fixtures" / "contract-exec"
ADAPTER = ROOT / "bin" / "propose_receipt.py"
EXECUTOR = ROOT / "bin" / "contract_exec.py"

STUB = """#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_OUT"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\\n")
print("stub-executor-stdout")
sys.exit(int(os.environ.get("STUB_RC", "0")))
"""

REAL = """#!/usr/bin/env bash
exec python3 "{executor}" "$@" --repo-root "{root}" --manifest-dir "{manifest}" \\
  --receipt-root "$CONTROL_ROOM_RECEIPT_ROOT" --home "$HOME"
"""


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receipt = load("workflow_receipt")
api = load("control_room_api")


def executable(path: pathlib.Path, text: str) -> pathlib.Path:
    path.write_text(text)
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return path


class ProposeReceiptTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.tmp = pathlib.Path(self.temp.name)
        self.home = self.tmp / "home"
        self.logs = self.home / "agent-workforce" / "logs" / "last-attempt"
        self.logs.mkdir(parents=True)
        self.receipts = self.tmp / "receipts"
        self.stub_out = self.tmp / "stub.jsonl"
        self.stub = executable(self.tmp / "stub_exec.py", STUB)
        self.started = int(time.time()) - 120
        self.attempt_log = self.logs / "knowledge-digest.log"
        self.attempt_log.write_text("vault_sync_guard[check]: OK: mirror clean and current\nran\n")

    def tearDown(self):
        self.temp.cleanup()

    def base_env(self, **extra):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
               "CONTRACT_EXEC": str(self.stub), "STUB_OUT": str(self.stub_out),
               "CONTROL_ROOM_RECEIPT_ROOT": str(self.receipts),
               "DELIVERY_JOB": "knowledge-digest.service", "AGENT_TASK_SLUG": "knowledge-digest",
               "AGENT_ATTEMPT_LOG": str(self.attempt_log), "AGENT_RUN_STARTED_AT": str(self.started),
               "RUN_DATE": "2026-09-14", "INBOX_WORKTREE": str(self.home / "agent-worktrees" / "inbox"),
               "INVOCATION_ID": "inv0001"}
        env.update({k: v for k, v in extra.items() if v is not None})
        for key, value in extra.items():
            if value is None:
                env.pop(key, None)
        return env

    def run_adapter(self, *args, env=None):
        done = subprocess.run([sys.executable, str(ADAPTER), *args], capture_output=True, text=True,
                              env=env or self.base_env())
        calls = [json.loads(line) for line in self.stub_out.read_text().splitlines()] if self.stub_out.exists() else []
        return done, calls

    def test_every_exit(self):  # (::propose-receipt-every-exit)
        cases = {
            ("SKIP",): ["--skipped", "previous run still active (flock)"],
            ("DEDUP",): ["--skipped", "dedup: today's proposal already exists"],
            ("BLOCKED", "--reason", "secrets.env missing"): ["--failed", "BLOCKED: secrets.env missing"],
            ("FAIL", "--rc", "1"): ["--failed", "FAIL: rc=1 ran"],
            ("CRASHED", "--rc", "4"): ["--failed", "CRASHED: rc=4 ran"],
            ("VIOLATION",): ["--failed", "VIOLATION: wrote outside _inbox/agents"],
            ("NOPROPOSAL",): [],
            ("PROPOSAL", "--proposal", "_inbox/agents/2026-09-14_knowledge-digest.md"):
                ["--artifact", f"file://{self.home}/agent-worktrees/inbox/_inbox/agents/2026-09-14_knowledge-digest.md"],
        }
        for argv, expected in cases.items():
            self.stub_out.unlink(missing_ok=True)
            done, calls = self.run_adapter(*argv)
            self.assertEqual(done.returncode, 0, (argv, done.stdout, done.stderr))
            self.assertEqual(len(calls), 1, argv)
            call = calls[0]
            self.assertEqual(call[:3], ["knowledge-digest", "--vantage", "run"], argv)
            for flag, value in zip(expected[::2], expected[1::2]):
                self.assertIn(flag, call, argv)
                self.assertEqual(call[call.index(flag) + 1], value, argv)
            for flag in ("--skipped", "--failed", "--artifact", "--state-change", "--decline"):
                if flag not in expected:
                    self.assertNotIn(flag, call, (argv, flag))
            self.assertEqual(call[call.index("--run-id") + 1], "inv0001", argv)
            self.assertNotIn("--parent-run-id", call, argv)
            self.assertNotIn("--usage-json", call, argv)
            self.assertIn("stub-executor-stdout", done.stdout, argv)

        self.attempt_log.write_text("started\nDECLINE: nothing\n")
        self.stub_out.unlink(missing_ok=True)
        done, calls = self.run_adapter("FAIL", "--rc", "91")
        self.assertEqual(calls[0][calls[0].index("--failed") + 1], "FAIL: rc=91 started")

        report_dir = self.tmp / "reports"
        report_dir.mkdir()
        old = report_dir / "daily-plan-2026-09-13.md"
        old.write_text("old\n")
        os.utime(old, (self.started - 100, self.started - 100))
        self.stub_out.unlink(missing_ok=True)
        done, calls = self.run_adapter("OPS", env=self.base_env(REPORT_DIR=str(report_dir), REPORT_GLOB="daily-plan-*.md"))
        self.assertNotIn("--artifact", calls[0], "a report older than the run is not this run's artifact")
        new = report_dir / "daily-plan-2026-09-14.md"
        new.write_text("new\n")
        self.stub_out.unlink(missing_ok=True)
        done, calls = self.run_adapter("OPS", env=self.base_env(REPORT_DIR=str(report_dir), REPORT_GLOB="daily-plan-*.md"))
        self.assertEqual(calls[0][calls[0].index("--artifact") + 1], f"file://{new}")

        for log, expected in (("attempt-content-draft.log",
                               ["--state-change", "page=0a0a0a0a-0a0a-4a0a-8a0a-0a0a0a0a0a0a from=Picked to=Draft",
                                "--handoff-actor", "praetorium", "--handoff-recipient", "augustus",
                                "--handoff-event", "e0" * 32]),
                              ("attempt-content-decline.log",
                               ["--decline", f"augustus declined: decline_event={'d2' * 32}",
                                "--handoff-event", "e1" * 32]),
                              ("attempt-content-neither.log", ["--handoff-event", "e2" * 32])):
            self.stub_out.unlink(missing_ok=True)
            done, calls = self.run_adapter("OPS", env=self.base_env(
                DELIVERY_JOB="augustus-content.service", AGENT_TASK_SLUG="augustus-content",
                AGENT_ATTEMPT_LOG=str(FIX / log), AGENT_RUN_ID="inv0001-draft", AGENT_PARENT_RUN_ID="inv0001"))
            call = calls[0]
            self.assertEqual(call[0], "augustus-content", log)
            for flag, value in zip(expected[::2], expected[1::2]):
                self.assertEqual(call[call.index(flag) + 1], value, (log, flag))
            for flag in ("--state-change", "--decline", "--artifact"):
                if flag not in expected:
                    self.assertNotIn(flag, call, (log, flag))
            self.assertEqual(call[call.index("--run-id") + 1], "inv0001-draft")
            self.assertEqual(call[call.index("--parent-run-id") + 1], "inv0001")

        self.stub_out.unlink(missing_ok=True)
        done, calls = self.run_adapter("NOPROPOSAL", env=self.base_env(STUB_RC="1"))
        self.assertEqual(done.returncode, 1, "the executor's status is the adapter's")
        done, calls = self.run_adapter("NOPROPOSAL", env=self.base_env(AGENT_RECEIPT_UNIT="raw-ingest"))
        self.assertEqual(calls[-1][0], "raw-ingest", "AGENT_RECEIPT_UNIT wins over DELIVERY_JOB")

    def test_usage_from_envelope(self):  # (::propose-receipt-usage-from-envelope)
        usage = self.logs / "knowledge-digest.usage.json"
        done, calls = self.run_adapter("NOPROPOSAL", env=self.base_env(AGENT_USAGE_JSON=str(usage)))
        self.assertNotIn("--usage-json", calls[0], "a missing envelope is not passed")
        usage.write_bytes((FIX / "claude-envelope.json").read_bytes())
        self.stub_out.unlink()
        done, calls = self.run_adapter("NOPROPOSAL", env=self.base_env(AGENT_USAGE_JSON=str(usage)))
        self.assertEqual(calls[0][calls[0].index("--usage-json") + 1], str(usage))

        real = executable(self.tmp / "real_exec.sh",
                          REAL.format(executor=EXECUTOR, root=ROOT, manifest=EXEC_FIX / "agents"))
        env = self.base_env(CONTRACT_EXEC=str(real), AGENT_USAGE_JSON=str(usage),
                            DELIVERY_JOB="logical-child.service", AGENT_TASK_SLUG="logical-child")
        done = subprocess.run([sys.executable, str(ADAPTER), "PROPOSAL", "--proposal", "_inbox/agents/x.md"],
                              capture_output=True, text=True, env=env)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        written = json.loads((self.receipts / "logical-parent" / "inv0001.json").read_text())
        self.assertEqual(written["usage"]["status"], "measured")
        self.assertEqual(written["usage"]["input_tokens"], 10)
        self.assertEqual(written["usage"]["output_tokens"], 92)
        self.assertEqual(written["cost"]["status"], "measured")
        self.assertEqual(written["cost"]["amount"], 0.0555477)
        self.assertEqual(written["model"], "claude-opus-5")
        usage.unlink()
        env["INVOCATION_ID"] = "inv0002"
        done = subprocess.run([sys.executable, str(ADAPTER), "PROPOSAL", "--proposal", "_inbox/agents/x.md"],
                              capture_output=True, text=True, env=env)
        written = json.loads((self.receipts / "logical-parent" / "inv0002.json").read_text())
        self.assertEqual(written["usage"], receipt.unavailable_usage())
        self.assertEqual(written["cost"], receipt.unavailable_cost())

    def test_no_unit_no_receipt(self):  # (::propose-receipt-no-unit-no-receipt)
        done, calls = self.run_adapter("NOPROPOSAL", env=self.base_env(DELIVERY_JOB=None))
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(calls, [])
        self.assertIn("no unit known — no receipt", done.stdout + done.stderr)

    def test_reads_back_valid(self):  # (::receipt-reads-back-valid)
        real = executable(self.tmp / "real_exec.sh",
                          REAL.format(executor=EXECUTOR, root=ROOT, manifest=EXEC_FIX / "agents"))
        env = self.base_env(CONTRACT_EXEC=str(real), DELIVERY_JOB="logical-child.service",
                            AGENT_TASK_SLUG="logical-child")
        for outcome, argv, expected in (("PROPOSAL", ["--proposal", "_inbox/agents/x.md"], "artifact"),
                                        ("SKIP", [], "skipped"),
                                        ("FAIL", ["--rc", "1"], "failed")):
            env["INVOCATION_ID"] = f"inv-{outcome}"
            done = subprocess.run([sys.executable, str(ADAPTER), outcome, *argv],
                                  capture_output=True, text=True, env=env)
            written = json.loads((self.receipts / "logical-parent" / f"inv-{outcome}.json").read_text())
            self.assertEqual(written["terminal"]["outcome"], expected, (outcome, done.stdout, done.stderr))
            self.assertEqual(receipt.validate(written), [], outcome)
            self.assertEqual(done.returncode, 1 if expected == "failed" else 0, outcome)
        model = api.ControlRoomReadModel(api.SourcePaths(ROOT, self.tmp, self.receipts))
        valid, malformed, errors = model.receipts()
        self.assertEqual((malformed, errors), ([], []))
        self.assertEqual({v["run_id"] for v in valid}, {"inv-PROPOSAL", "inv-SKIP", "inv-FAIL"})
        runs, status = model.list_runs("logical-parent")
        self.assertEqual({r["id"] for r in runs}, {"inv-PROPOSAL", "inv-SKIP", "inv-FAIL"})
        self.assertEqual(status["errors"]["malformedReceipts"], [])


if __name__ == "__main__":
    unittest.main()
