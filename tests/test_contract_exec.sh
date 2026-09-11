#!/usr/bin/env bash
# Contract executor fixture suite (T5.1). The assertions and their `::` anchors live in the
# companion .py — asserts-anchored in tests/test_workflow_coverage.py follows the python line
# below — so this wrapper is only the gate's entry point. No box precondition: every checkout
# carries the live knowledge-digest contract, the schema doc and the fixtures the suite needs.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_contract_exec.py
