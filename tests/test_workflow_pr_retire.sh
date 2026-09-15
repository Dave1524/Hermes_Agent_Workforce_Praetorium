#!/usr/bin/env bash
# T5.3b — the retirement plan: removal across joins, retention, refusals, count literals, the PR
# body, and the fail-closed residue check. Anchors live in tests/test_workflow_pr_retire.py.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
python3 tests/test_workflow_pr_retire.py
