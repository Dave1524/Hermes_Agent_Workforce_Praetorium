#!/usr/bin/env bash
# Hermes residue gate (T6.1). The assertions and their `::` anchors live in the companion
# .py — asserts-anchored in tests/test_workflow_coverage.py follows the python line below —
# so this wrapper is only the gate's entry point. No box precondition: it scans the checkout.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_hermes_residue.py
