#!/usr/bin/env bash
# NUC-45 — driver for the offline behaviour test of bin/notion_daily.py.
# bin/verify.sh only executes tests/*.sh, so the python test hangs off this.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (bin/notion_daily.py — stubbed HTTP, no network, no live Notion writes)"
exec python3 tests/test_notion_daily.py
