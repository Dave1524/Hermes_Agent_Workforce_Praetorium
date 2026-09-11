#!/usr/bin/env bash
# Driver for the offline rules test of bin/bd_stall_radar_kernel.py.
# bin/verify.sh only executes tests/*.sh, so the python test hangs off this.
set -euo pipefail
cd "$(dirname "$0")/.."
echo "  (bin/bd_stall_radar_kernel.py — pure rules, no Notion, no qmd)"
exec python3 tests/test_bd_stall_radar_kernel.py
