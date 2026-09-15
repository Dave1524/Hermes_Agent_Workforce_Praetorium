#!/usr/bin/env bash
# Fixture smoke test for gamma (both triggers).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
[ -f systemd/gamma.timer ] && [ -f systemd/gamma-dispatch.timer ] || { echo "FAIL: gamma timers missing"; exit 1; }
echo "  ok: gamma timers present"
