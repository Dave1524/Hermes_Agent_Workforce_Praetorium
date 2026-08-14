#!/usr/bin/env bash
# Steps 4 and 5 of the Content DB migration run once, unattended, on Dave's board. The
# guards are the tool: any one of them failing must stop the pass with Notion untouched.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "  (bin/content_inbox_finalize.py — stubbed HTTP and shell, no network, no live Notion writes)"
exec python3 tests/test_content_inbox_finalize.py
