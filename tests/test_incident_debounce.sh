#!/usr/bin/env bash
# Incident debounce suite (criterion 15). The assertions and their `::` anchors live in the
# companion .py, so this wrapper is only the gate's entry point. No box precondition: the CLI
# half reuses the notifier suite's fake transport under tests/fixtures/incidents/.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

python3 tests/test_incident_debounce.py
