#!/usr/bin/env bash
# Finish-step suite. The assertions and their `::` anchors live in the companion .py —
# asserts-anchored in tests/test_workflow_coverage.py follows the python line below — so this
# wrapper is only the gate's entry point. No box precondition: the fake systemctl, a fixture
# platform contract and a sandboxed receipt root, with the real executor and sweep.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_receipt_finish.py
