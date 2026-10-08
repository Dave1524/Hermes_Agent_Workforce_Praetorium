#!/usr/bin/env bash
# Dev Plan B3 — driver for the offline behaviour test of bin/notion_research.py.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (bin/notion_research.py — stubbed HTTP, no network, no live Notion writes)"
exec python3 tests/test_notion_research.py
