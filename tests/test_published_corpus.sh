#!/usr/bin/env bash
# Driver for the offline test of bin/published_corpus.py + bin/brief_collision_check.py.
# bin/verify.sh only executes tests/*.sh, so the python test hangs off this.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (published corpus — fixture blog.ts, no network, no git)"
exec python3 tests/test_published_corpus.py
