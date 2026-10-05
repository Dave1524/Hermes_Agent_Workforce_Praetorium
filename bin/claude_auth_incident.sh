#!/usr/bin/env bash
# The one `auth-expired` incident, opened and closed by whoever probes Claude auth.
#
#   claude_auth_incident.sh open "<evidence line>"   declare it; a no-op while one is open
#   claude_auth_incident.sh close                    resolve it; silent when none is open
#
# An expired login takes down every scheduled runner and every Claude Buzz agent at once, and
# 2026-09-30..10-05 surfaced it as one failed receipt per workflow per night — 14 incidents for
# one cause. bin/agent_propose.sh's pre-flight and fleet-turn-check gate 2 both call this, so it
# is one key whoever sees it first, paged once by incident_notify.py, recovered once.
# Fail-soft: incident bookkeeping never changes the caller's outcome.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INCIDENTS="${WORKFLOW_INCIDENTS:-$BIN_DIR/workflow_incidents.py}"
WORKFLOW=claude-auth
KEY="auth-expired:$WORKFLOW:$WORKFLOW"

case "${1:-}" in
  open)
    python3 "$INCIDENTS" declare --class auth-expired --workflow "$WORKFLOW" --id "$WORKFLOW" \
      --issue "${2:-headless claude refused authentication}" \
      --action "Headless Claude cannot authenticate: mint a token with \`claude setup-token\` into ~/.config/agent-workforce/claude_oauth.env, or /login" \
      >/dev/null || echo "claude_auth_incident: could not declare $KEY" >&2
    ;;
  close)
    python3 "$INCIDENTS" resolve --key "$KEY" >/dev/null 2>&1 || true
    ;;
  *) echo "usage: $(basename "$0") open <evidence> | close" >&2; exit 2 ;;
esac
exit 0
