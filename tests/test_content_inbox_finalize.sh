#!/usr/bin/env bash
# Steps 4 and 5 of the Content DB migration run once, unattended, on Dave's board. The
# guards are the tool: any one of them failing must stop the pass with Notion untouched.
#
# THE NINE RULES design/fleet-suites.toml DECLARES FOR THIS SUITE ARE ANCHORED IN THE .py,
# NOT HERE (W9). This file is a wrapper; the assertions are one exec away, which is why the
# manifest's nine ids matched nothing in the file it names for as long as they did.
# asserts-anchored in tests/test_workflow_coverage.py follows the `exec python3` line below
# to find them, and reads the anchors back in both directions.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "  (bin/content_inbox_finalize.py — stubbed HTTP and shell, no network, no live Notion writes)"
exec python3 tests/test_content_inbox_finalize.py
