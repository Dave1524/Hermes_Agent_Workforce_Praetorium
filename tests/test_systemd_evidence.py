#!/usr/bin/env python3
"""bin/systemd_evidence.py: systemd's verdict on one run, as executor evidence.

Two producers write it for the same run: bin/receipt_sweep.py from `systemctl show`, and
bin/receipt_finish.py from ExecStopPost's environment. One builder keeps their receipts one
string; the signal case is where the two sources disagree (a name in EXIT_STATUS, a number in
ExecMainStatus). Anchors are the `::` comments; tests/test_systemd_evidence.sh is the gate
entry point.
"""

from __future__ import annotations

import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


evidence = load("systemd_evidence")
RECORD = {"InvocationID": "ab" * 16, "ExecMainExitTimestamp": "@1789452660"}


class EvidenceFlags(unittest.TestCase):
    # (::systemd-evidence-one-shape)
    def test_success_is_a_state_change_only(self):
        flags = evidence.evidence_flags("unit-a", {**RECORD, "Result": "success", "ExecMainStatus": "0"})
        self.assertEqual(flags, ["--state-change", f"systemd: unit-a.service {'ab' * 16} Result=success "
                                                   "ExecMainStatus=0 exited 2026-09-15T06:11:00Z"])

    def test_anything_else_failed_with_the_reason(self):
        flags = evidence.evidence_flags("unit-a", {**RECORD, "Result": "exit-code", "ExecMainStatus": "3"})
        self.assertEqual(flags[:2], ["--failed", "Result=exit-code ExecMainStatus=3"])
        self.assertEqual(flags[2], "--state-change")

    def test_an_unknown_exit_time_says_so(self):
        flags = evidence.evidence_flags("unit-a", {"InvocationID": "x", "Result": "success", "ExecMainStatus": "0"})
        self.assertTrue(flags[1].endswith("exited unknown time"), flags)

    def test_epoch_of_reads_only_the_unix_form(self):
        self.assertEqual(evidence.epoch_of("@1789452600"), 1789452600)
        self.assertIsNone(evidence.epoch_of("Tue 2026-09-15 06:10:00 UTC"))
        self.assertIsNone(evidence.epoch_of(""))


class ExitStatusNumber(unittest.TestCase):
    # (::systemd-evidence-signal-number)
    def test_a_signal_name_becomes_the_number_systemctl_reports(self):
        self.assertEqual(evidence.exit_status_number("killed", "TERM"), "15")
        self.assertEqual(evidence.exit_status_number("dumped", "SEGV"), "11")

    def test_an_exit_code_passes_through(self):
        self.assertEqual(evidence.exit_status_number("exited", "3"), "3")
        self.assertEqual(evidence.exit_status_number("killed", "9"), "9")

    def test_an_unknown_name_is_kept_rather_than_guessed(self):
        self.assertEqual(evidence.exit_status_number("killed", "NOPE"), "NOPE")
        self.assertEqual(evidence.exit_status_number("", ""), "")


if __name__ == "__main__":
    unittest.main(verbosity=1)
