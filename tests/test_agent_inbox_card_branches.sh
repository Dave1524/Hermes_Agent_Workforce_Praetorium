#!/usr/bin/env bash
# Driver for the card-branch skip in bin/agent_inbox_branch_rows.py. bin/verify.sh only
# executes tests/*.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
exec python3 tests/test_agent_inbox_card_branches.py
