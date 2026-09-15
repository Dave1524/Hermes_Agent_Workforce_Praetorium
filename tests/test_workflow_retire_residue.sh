#!/usr/bin/env bash
# T5.3b — the W19-class residue scanner (source classes, live fail-closed, W19 table, CLI). The
# assertions and their anchors live in tests/test_workflow_retire_residue.py.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
python3 tests/test_workflow_retire_residue.py
