#!/usr/bin/env bash
# NUC-45 — evening job entrypoint, wired as AGENT_RUNTIME_CMD in
# ~/.config/agent-workforce/eod_summary.env. run_daily_rhythm_cc.sh owns the vault
# freshness gate and the headless Claude Code invocation for both daily jobs.
set -euo pipefail
exec "$(cd "$(dirname "$0")" && pwd)/run_daily_rhythm_cc.sh" eod-summary
