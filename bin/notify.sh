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

# shellcheck source=bin/delivery_common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/delivery_common.sh"

usage() {
  note "usage: notify.sh <subject> <message> [--file <path>] [--route <key>]"
  exit 0
}

[ $# -ge 2 ] || usage

subject="$1"
message="$2"
shift 2

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
      DELIVERY_ROUTE="$1"
      shift
      ;;
    *)
      note "unrecognized argument: $1"
      usage
      ;;
  esac
done

args=(--subject "$subject")
if [ ${#file_arg[@]} -gt 0 ]; then
  args+=("${file_arg[@]}")   # file mode: the artifact is the payload; message text is not sent
else
  args+=(--message "$message")
fi

note "handing: $subject"
delivery_handoff "${args[@]}"

exit 0
