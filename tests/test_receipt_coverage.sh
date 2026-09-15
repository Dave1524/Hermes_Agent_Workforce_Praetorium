#!/usr/bin/env bash
# Receipt coverage suite (T5.2). The assertions and their `::` anchors live in the companion
# .py — asserts-anchored in tests/test_workflow_coverage.py follows the python line below — so
# this wrapper is only the gate's entry point. No box precondition: it joins the checked-in
# manifests, config/fleet-units.tsv, the unit sources and buzz-team/agent-settings.json.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_receipt_coverage.py
