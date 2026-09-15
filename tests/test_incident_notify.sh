#!/usr/bin/env bash
# Incident notifier suite (T5.3c). The assertions and their `::` anchors live in the companion
# .py — asserts-anchored in tests/test_workflow_coverage.py follows the python line below — so
# this wrapper is only the gate's entry point. No box precondition: the fake transport and the
# fake systemctl live under tests/fixtures/incidents/.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_incident_notify.py
