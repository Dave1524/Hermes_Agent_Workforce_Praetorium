#!/usr/bin/env bash
# notify.sh — model-free notification dispatch to Discord via hermes send.
#
# A single, tested entrypoint for all box-side notifications (alert
# handlers, service completion notices, ad-hoc messages). Wraps the
# `hermes send --to discord` pattern duplicated in deliver_report.sh
# and inbox_backlog_alert.sh.
#
# Usage:
#   notify.sh <subject> <message>              # text-mode notification
#   notify.sh <subject> --file <path>          # file-content notification
#
# Behaviour:
#   - Resolves the hermes CLI entrypoint (venv → .local → python -m)
#   - Calls `hermes send --to discord --subject <subject>` with the
#     provided message text or file content
#   - Logs outcome to $HOME/logs/notify.log
#   - FAIL-SOFT: always exits 0 so a Discord hiccup never causes a
#     caller (systemd ExecStartPost, OnFailure handler, etc.) to fail
set -uo pipefail

readonly log="$HOME/logs/notify.log"
mkdir -p "$HOME/logs" 2>/dev/null || true
now() { date -u +%Y-%m-%dT%H:%M:%SZ; }
note() { printf '%s notify: %s\n' "$(now)" "$*" >> "$log" 2>/dev/null || true; }

# Resolve a model-free hermes send entrypoint (same resolution as
# deliver_report.sh and inbox_backlog_alert.sh).
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

usage() {
  note "usage: notify.sh <subject> <message> [--file <path>]"
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
      [ -n "${1:-}" ] && file_arg=(--file "$1") || usage
      shift
      ;;
    *)
      note "unrecognized argument: $1"
      usage
      ;;
  esac
done

if [ ${#file_arg[@]} -gt 0 ]; then
  # File mode — send file content, ignore message text
  if hsend --to discord --subject "$subject" "${file_arg[@]}" --quiet; then
    note "delivered (file): $subject"
  else
    note "delivery failed (non-fatal): $subject"
  fi
else
  # Text mode — send subject + message body
  if hsend --to discord --subject "$subject" "$message" --quiet; then
    note "delivered: $subject — $message"
  else
    note "delivery failed (non-fatal): $subject — $message"
  fi
fi

exit 0
