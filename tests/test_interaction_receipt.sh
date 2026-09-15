#!/usr/bin/env bash
# Interaction receipt fixture suite (T5.2). The assertions and their `::` anchors live in the
# companion .py — asserts-anchored in tests/test_workflow_coverage.py follows the python line
# below — so this wrapper is only the gate's entry point. No box precondition: the transcripts,
# the rollout, the payloads and the heartbeat prompt are all synthetic files in the checkout.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_interaction_receipt.py
