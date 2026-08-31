#!/usr/bin/env bash
# Driver for the offline unit test of bin/notion_markdown.py.
# bin/verify.sh only executes tests/*.sh, so the python test hangs off this.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (bin/notion_markdown.py — pure converter, no network, no token, no filesystem)"
exec python3 tests/test_notion_markdown.py
