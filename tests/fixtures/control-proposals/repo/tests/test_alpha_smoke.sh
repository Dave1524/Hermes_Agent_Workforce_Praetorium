#!/usr/bin/env bash
# Fixture smoke test pinning alpha's schedule.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
grep -q "^OnCalendar=Sun 09:00$" systemd/alpha.timer || { echo "FAIL: alpha.timer must fire Sun 09:00"; exit 1; }
echo "  ok: alpha fires Sun 09:00"
