#!/usr/bin/env bash
# NUC-46: notion_rest.py's broker transport. The NUC-44 guards are replayed through
# both transports from one shared case table — a guard that holds on HTTPS and not on
# the broker is the entire risk this suite exists to catch, because the broker is the
# path buzz-augustus runs on.
set -euo pipefail
cd "$(dirname "$0")/.."

echo "  (bin/notion_rest.py — stub broker on a temp unix socket, no network, no live Notion)"
exec python3 tests/test_notion_rest_broker.py
