#!/usr/bin/env bash
# T5.3b — the schedule plan: exact diff, timezone/catch-up description, the check bundle's
# schedule half. The assertions and their (::id) anchors live in tests/test_workflow_pr_schedule.py.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
python3 tests/test_workflow_pr_schedule.py
