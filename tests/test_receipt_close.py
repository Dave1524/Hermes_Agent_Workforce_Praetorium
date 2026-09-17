#!/usr/bin/env python3
"""bin/receipt_close.py and the `closed` block of bin/workflow_receipt.py: a reviewed failure
stops being judged without its recorded outcome changing."""

from __future__ import annotations

import datetime as dt
import io
import json
import pathlib
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import receipt_close  # noqa: E402
import workflow_receipt as wr  # noqa: E402

NOW = dt.datetime(2026, 9, 17, 10, 30, tzinfo=dt.timezone.utc)


def receipt(outcome: str = "failed", failed_ids: tuple[str, ...] = (), **extra) -> dict:
    base = {
        "schema_version": wr.SCHEMA_VERSION, "workflow_id": "agent-proposal", "run_id": "run-1",
        "started_at": "2026-09-17T07:57:15Z", "ended_at": "2026-09-17T07:58:20Z",
        "terminal": {"outcome": outcome, "reason": "FAIL: rc=91"},
        "assertions": [{"id": i, "status": "failed"} for i in failed_ids],
        "usage": wr.unavailable_usage(), "cost": wr.unavailable_cost(),
    }
    if outcome == "artifact":
        base["artifact"] = {"uri": "vault://x.md"}
    return {**base, **extra}


class ClosedBlock(unittest.TestCase):  # (::receipt-close-schema)
    def test_a_closure_validates_only_with_author_reason_and_time(self):
        closed = wr.close(receipt(), "Dave", "check defect fixed in 73dea03", NOW)
        self.assertEqual(closed["closed"], {"at": "2026-09-17T10:30:00Z", "by": "Dave",
                                            "reason": "check defect fixed in 73dea03"})
        self.assertEqual(wr.validate(closed), [])
        self.assertEqual(closed["terminal"]["outcome"], "failed")
        for broken in ({"at": "yesterday", "by": "Dave", "reason": "x"},
                       {"at": "2026-09-17T10:30:00Z", "by": " ", "reason": "x"},
                       {"at": "2026-09-17T10:30:00Z", "by": "Dave"},
                       "closed"):
            self.assertTrue(wr.validate(receipt(closed=broken)), broken)

    def test_only_a_failure_can_be_closed(self):
        block = {"at": "2026-09-17T10:30:00Z", "by": "Dave", "reason": "x"}
        self.assertEqual(wr.validate(receipt("decline", ("mirror-was-not-dirty",), closed=block)), [])
        for outcome in ("artifact", "decline", "skipped"):
            self.assertIn("closed on a receipt with nothing failed", wr.validate(receipt(outcome, closed=block)))
            with self.assertRaises(ValueError):
                wr.close(receipt(outcome), "Dave", "x", NOW)

    def test_close_refuses_a_second_closure_and_an_empty_review(self):
        closed = wr.close(receipt(), "Dave", "x", NOW)
        with self.assertRaisesRegex(ValueError, "already closed 2026-09-17T10:30:00Z by Dave"):
            wr.close(closed, "Dave", "again", NOW)
        for by, reason in (("", "x"), ("Dave", "  ")):
            with self.assertRaises(ValueError):
                wr.close(receipt(), by, reason, NOW)


class Judged(unittest.TestCase):  # (::receipt-close-not-judged)
    def test_a_closed_receipt_is_not_a_run_to_judge_and_a_skip_never_was(self):
        self.assertTrue(wr.judged(receipt()))
        self.assertTrue(wr.judged(receipt("artifact")))
        self.assertFalse(wr.judged(receipt("skipped")))
        self.assertFalse(wr.judged(wr.close(receipt(), "Dave", "x", NOW)))
        self.assertFalse(wr.is_closed(receipt()))


class Cli(unittest.TestCase):  # (::receipt-close-cli)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.path = wr.write(receipt(failed_ids=("artifact-is-this-run",)), self.root)

    def tearDown(self):
        self.temp.cleanup()

    def run_cli(self, *args: str) -> tuple[int, str]:
        err = io.StringIO()
        with redirect_stderr(err), redirect_stdout(io.StringIO()):
            code = receipt_close.main(["--root", str(self.root), *args])
        return code, err.getvalue()

    def test_closes_in_place_and_keeps_everything_else(self):
        before = json.loads(self.path.read_text())
        code, err = self.run_cli("agent-proposal", "run-1", "--by", "Dave", "--reason", "skip receipted failed before 73dea03")
        self.assertEqual((code, err), (0, ""))
        after = json.loads(self.path.read_text())
        self.assertEqual({k: v for k, v in after.items() if k != "closed"}, before)
        self.assertEqual((after["closed"]["by"], after["closed"]["reason"]), ("Dave", "skip receipted failed before 73dea03"))
        self.assertEqual(wr.validate(after), [])
        self.assertEqual([p.name for p in self.path.parent.iterdir()], ["run-1.json"])

    def test_refusals_leave_the_receipt_untouched(self):
        before = self.path.read_bytes()
        code, err = self.run_cli("agent-proposal", "run-9", "--by", "Dave", "--reason", "x")
        self.assertEqual(code, 2)
        self.assertIn("no receipt at", err)
        self.assertEqual(self.path.read_bytes(), before)
        self.run_cli("agent-proposal", "run-1", "--by", "Dave", "--reason", "first")
        code, err = self.run_cli("agent-proposal", "run-1", "--by", "Dave", "--reason", "second")
        self.assertEqual(code, 2)
        self.assertIn("already closed", err)
        self.assertEqual(json.loads(self.path.read_text())["closed"]["reason"], "first")
        wr.write(receipt("artifact"), self.root)
        code, err = self.run_cli("agent-proposal", "run-1", "--by", "Dave", "--reason", "x")
        self.assertEqual(code, 2)
        self.assertIn("nothing to close", err)
        self.assertNotIn("closed", json.loads(self.path.read_text()))


if __name__ == "__main__":
    unittest.main()
