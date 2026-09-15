#!/usr/bin/env bash
# Fixture smoke test for beta.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
[ -f systemd/beta.timer ] || { echo "FAIL: beta.timer missing"; exit 1; }
echo "  ok: beta present"
