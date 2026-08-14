#!/usr/bin/env bash
# The Agent Content Inbox -> Content DB migration: the field mapping, the two refusals
# that stop a bad option being invented or a half-migration starting, body copy, and the
# ledger that makes a partial run reversible.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "  (bin/notion_content_migrate.py — stubbed HTTP, no network, no live Notion writes)"
exec python3 tests/test_notion_content_migrate.py
