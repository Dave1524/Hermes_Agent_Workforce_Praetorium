#!/usr/bin/env bash
# Driver for the offline behaviour test of bin/notion_publish_doc.py.
# bin/verify.sh only executes tests/*.sh, so the python test hangs off this.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (bin/notion_publish_doc.py — stubbed HTTP, no network, no live Notion writes)"
exec python3 tests/test_notion_publish_doc.py
