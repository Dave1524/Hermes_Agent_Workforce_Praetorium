#!/usr/bin/env bash
# Driver for the offline behaviour test of the branch-row body mode in
# bin/agent_inbox_notion_sync.py. bin/verify.sh only executes tests/*.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (branch-shaped Agent Inbox rows — stubbed HTTP, temp git repo, no network)"
exec python3 tests/test_agent_inbox_branch_rows.py
