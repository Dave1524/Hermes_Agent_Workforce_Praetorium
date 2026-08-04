#!/usr/bin/env bash
# notify.sh — text/file notification adapter over bin/deliver.sh.
#
# The positional interface is unchanged from the Discord-only version, because
# agent-alert@.service and the ExecStartPost hooks call it that way:
#
#   notify.sh <subject> <message>               # text-mode notification
#   notify.sh <subject> <message> --file <path> # attach a file instead
#
# The destination is NOT decided here. There is deliberately no default route: a
# caller that has not been given DELIVERY_ROUTE (or --route) delivers to Discord
# exactly as before and leaves a config_error receipt behind. Hardcoding a fallback
# would quietly file research and content output into the ops channel, and the audit
# would still show a clean dual-run.
#
# FAIL-SOFT: always exits 0, so an OnFailure handler or ExecStartPost can never
# itself fail the unit it is reporting on.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVER_BIN="${DELIVER_BIN:-$BIN_DIR/deliver.sh}"

log="$HOME/logs/notify.log"
mkdir -p "$HOME/logs" 2>/dev/null || true
note() {
  printf '%s notify: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" >> "$log" 2>/dev/null || true
}

usage() {
  note "usage: notify.sh <subject> <message> [--file <path>] [--route <key>]"
  exit 0
}

[ $# -ge 2 ] || usage

subject="$1"
message="$2"
shift 2

route="${DELIVERY_ROUTE:-unrouted}"
file_arg=()
while [ $# -gt 0 ]; do
  case "$1" in
    --file)
      shift
      [ -n "${1:-}" ] || usage
      file_arg=(--file "$1")
      shift
      ;;
    --route)
      shift
      [ -n "${1:-}" ] || usage
      route="$1"
      shift
      ;;
    *)
      note "unrecognized argument: $1"
      usage
      ;;
  esac
done

args=(--job "${DELIVERY_JOB:-notify.sh}" --route "$route" --subject "$subject"
      --runtime "${DELIVERY_RUNTIME:-${AGENT_PROFILE:-unknown}}")
if [ ${#file_arg[@]} -gt 0 ]; then
  args+=("${file_arg[@]}")   # file mode: the artifact is the payload; message text is not sent
else
  args+=(--message "$message")
fi

if "$DELIVER_BIN" "${args[@]}"; then
  note "handed to deliver.sh (route=$route): $subject"
else
  note "deliver.sh returned non-zero (non-fatal): $subject"
fi

exit 0
