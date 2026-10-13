#!/usr/bin/env bash
# systemd evidence suite. The assertions and their `::` anchors live in the companion .py —
# asserts-anchored in tests/test_workflow_coverage.py follows the python line below — so this
# wrapper is only the gate's entry point. No box precondition: pure functions.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_systemd_evidence.py
