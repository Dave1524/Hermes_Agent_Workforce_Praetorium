#!/usr/bin/env bash
# NUC-44: notion_rest.py only appends to a row at Idea or Picked, and caps how
# many board rows a run is handed. Both guards live in the tool, not in profile prose.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "  (bin/notion_rest.py — stubbed HTTP, no network, no live Notion writes)"
exec python3 tests/test_notion_rest.py
