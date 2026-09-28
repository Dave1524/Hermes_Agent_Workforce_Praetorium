#!/usr/bin/env python3
"""Exercise the unchanged-gate wrapper with real child shells, including silent failures."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "bin"))
import ship_verify


class Verify(unittest.TestCase):
    def fixture(self, drift: bool, other: bool):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            (root / "bin").mkdir()
            (root / "bin/check_deploy_drift.sh").write_text(
                "echo '  DRIFT [bin] content differs: example.sh'\nexit 1\n" if drift else "exit 0\n")
            (root / "bin/verify.sh").write_text(
                'set -euo pipefail\ncd "$(dirname "$0")/.."\ntrap ":" EXIT\nfail=0\n'
                'bash -c \'test -z "${BASH_XTRACEFD+x}"\' || fail=1\n'
                'bash bin/check_deploy_drift.sh || fail=1\n'
                + ('false || fail=1\n' if other else '') + 'exit $fail\n')
            return ship_verify.run(root, root / "gate.log")

    def test_drift_preserves_raw_failure(self):
        # (::ship-verify-drift)
        result = self.fixture(True, False)
        self.assertEqual(result, {"verifyExit": 1, "otherChecksExit": 0,
                                  "allRed": ["  DRIFT [bin] content differs: example.sh"]})
        self.assertEqual(self.fixture(False, False), {"verifyExit": 0, "otherChecksExit": 0, "allRed": []})

    def test_failure_without_red_line_remains_fatal(self):
        # (::ship-verify-other-failures)
        for drift in (True, False):
            result = self.fixture(drift, True)
            self.assertEqual(result["verifyExit"], 1)
            self.assertEqual(result["otherChecksExit"], 1)

    def test_incomplete_trace_fails_closed(self):
        # (::ship-verify-trace)
        for trace, code in (("", 0), ("+ fail=0\n", 1), ("+ fail=0\n+ exit 1\n", 1),
                            ("+ fail=0\n+ exit 2\n", 2)):
            self.assertEqual(ship_verify.other_checks_exit(trace, code), 1)


if __name__ == "__main__":
    unittest.main()
