#!/usr/bin/env bash
# SDLC measurements fixture suite (T8.7). The assertions and their `::` anchors live in the
# companion .py — asserts-anchored in tests/test_workflow_coverage.py follows the python line
# below — so this wrapper is only the gate's entry point. No box precondition: the fixture
# git history is built in a tempdir and the run records are in the checkout.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_sdlc_measurements.py
