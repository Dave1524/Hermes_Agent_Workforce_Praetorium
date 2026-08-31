#!/usr/bin/env bash
# Driver for the offline behaviour test of the proposal-body sync in
# bin/agent_inbox_notion_sync.py. bin/verify.sh only executes tests/*.sh.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (bin/agent_inbox_notion_sync.py bodies — stubbed HTTP, no network, no Notion writes)"
exec python3 tests/test_agent_inbox_body_sync.py
