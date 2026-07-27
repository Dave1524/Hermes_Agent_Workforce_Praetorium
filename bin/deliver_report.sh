#!/usr/bin/env bash
# NUC-30: deliver the newest overnight morning report to Dave's Discord channel
# via the model-free `hermes send` primitive (no LLM, no OpenRouter spend, no
# running gateway required for bot-token platforms like Discord).
#
# Wired as ExecStartPost on overnight-morning-report.service so the 06:15 NUC-36
# report delivers its own file. FAIL-SOFT BY DESIGN: any delivery/lookup error is
# logged and this script still exits 0, so a Discord hiccup never marks the report
# unit failed (which would fire the OnFailure alert for a non-event).
#
# NUC-45: the report to deliver is now a parameter (REPORT_DIR / REPORT_GLOB /
# REPORT_SUBJECT, set per-unit in the Environment= lines) so praetorium-daily-plan and
# praetorium-eod-summary reuse this delivery path instead of each growing a copy of it.
# The defaults are the NUC-30 morning report, so the existing unit is unchanged.
set -uo pipefail

REPORT_DIR="${REPORT_DIR:-$HOME/logs/overnight}"
REPORT_GLOB="${REPORT_GLOB:-morning-report-*.md}"
REPORT_SUBJECT="${REPORT_SUBJECT:-[Praetorium] Morning report}"

# Maximum report age before we refuse to deliver it (seconds).
# If the newest report file is older than this, the agent likely
# failed to produce a fresh one — don't spam Dave with stale data.
MAX_REPORT_AGE_SECS=$(( 26 * 3600 ))   # 26 hours — covers one skipped day

log="$HOME/logs/deliver_report.log"
mkdir -p "$HOME/logs" 2>/dev/null || true
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '%s deliver_report: %s\n' "$(now)" "$*" >> "$log" 2>/dev/null || true; }

# Resolve a model-free hermes send entrypoint. Prefer the venv binary (no PATH
# dependency under systemd), then the user shim, then the python module.
hsend() {
  if [ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]; then
    "$HOME/.hermes/hermes-agent/venv/bin/hermes" send "$@"
  elif [ -x "$HOME/.local/bin/hermes" ]; then
    "$HOME/.local/bin/hermes" send "$@"
  elif [ -x "$HOME/.hermes/hermes-agent/venv/bin/python" ]; then
    "$HOME/.hermes/hermes-agent/venv/bin/python" -m hermes_cli.main send "$@"
  else
    note "no hermes entrypoint found — skipping delivery"
    return 1
  fi
}

# Newest report by filename (the timestamped names sort lexically = chronologically).
latest=""
if [ -d "$REPORT_DIR" ]; then
  # REPORT_GLOB must stay unquoted here — quoting it would defeat the glob.
  # shellcheck disable=SC2086
  latest=$(ls -1 $REPORT_DIR/$REPORT_GLOB 2>/dev/null | sort | tail -1)
fi

if [ -z "$latest" ] || [ ! -s "$latest" ]; then
  note "no $REPORT_GLOB found in $REPORT_DIR — nothing to deliver"
  exit 0
fi

# Stale-file guard: only deliver if the report was written within the freshness window.
# This prevents the system from re-delivering the same stale file when the agent
# failed to produce a new one (NUC-37 BLOCKED, missing overrides, etc.).
report_mtime=$(stat -c %Y "$latest" 2>/dev/null || echo 0)
now_epoch=$(date +%s)
age=$(( now_epoch - report_mtime ))
if [ "$age" -gt "$MAX_REPORT_AGE_SECS" ]; then
  note "STALE: $(basename "$latest") is ${age}s old (>${MAX_REPORT_AGE_SECS}s max) — skipping delivery (agent likely did not produce a fresh report)"
  exit 0
fi

if hsend --to discord --subject "$REPORT_SUBJECT" --file "$latest" --quiet; then
  note "delivered $(basename "$latest") to discord"
else
  note "delivery failed for $(basename "$latest") (non-fatal)"
fi

exit 0
