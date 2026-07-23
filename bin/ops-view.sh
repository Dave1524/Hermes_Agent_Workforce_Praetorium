#!/usr/bin/env bash
# NUC-41: assemble a single-pane, read-only ops snapshot for Praetorium and either
# render it (--dry-run, the safe default) or publish it to a Notion page (--publish,
# gated on OPS_PAGE_ID — Dave's finish). Reuses bin/praetorium-status.sh for fleet
# health and adds what it lacks: Sprint Board Status counts + a recent-errors digest.
# Fail-soft by design (set -uo pipefail, NOT -e): a dead sub-probe degrades to a note.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
STATUS_BIN="${PRAETORIUM_STATUS_BIN:-$REPO_ROOT/bin/praetorium-status.sh}"
BOARD_COUNTS_BIN="${SPRINT_BOARD_COUNTS_BIN:-$REPO_ROOT/bin/sprint_board_counts.py}"
PUBLISH_BIN="${OPS_PAGE_PUBLISH_BIN:-$REPO_ROOT/bin/ops_page_publish.py}"
AGENT_LOG_DIR="${AGENT_LOG_DIR:-$HOME/agent-workforce/logs}"
SECRETS_FILE="${OPS_SECRETS_FILE:-$HOME/.config/agent-workforce/secrets.env}"

fleet_health() {
  if [ -x "$STATUS_BIN" ]; then
    bash "$STATUS_BIN" 2>&1
  else
    echo "(praetorium-status.sh unavailable at $STATUS_BIN)"
  fi
}

sprint_board_section() {
  local line
  if line=$(python3 "$BOARD_COUNTS_BIN" 2>/dev/null); then
    printf '%s\n' "$line"
  else
    echo "unavailable — needs NOTION_API_TOKEN (read-only Sprint Board query)"
  fi
}

failed_units() {
  local sys usr rt="/run/user/$(id -u)"
  sys=$(systemctl --failed --plain --no-legend 2>/dev/null | awk '{print $1}' | grep . || true)
  usr=$(XDG_RUNTIME_DIR="$rt" systemctl --user --failed --plain --no-legend 2>/dev/null \
          | awk '{print $1}' | grep . || true)
  printf '%s\n%s\n' "$sys" "$usr" | grep . || true
}

# Deliberately narrow: match hard error tokens + agent-run outcome=FAIL records,
# not the bare word "fail" (which hits "failed: none" and "expect FAILURE").
log_error_tail() {
  [ -d "$AGENT_LOG_DIR" ] || return 0
  grep -hE '(ERROR|Error|Traceback|Exception|outcome=FAIL)' \
    "$AGENT_LOG_DIR"/*.log 2>/dev/null | tail -n 8 || true
}

recent_errors_section() {
  local units errs
  units=$(failed_units)
  if [ -n "$units" ]; then
    echo "failed units:"
    printf '%s\n' "$units" | sed 's/^/  - /'
  else
    echo "failed units: none"
  fi
  errs=$(log_error_tail)
  if [ -n "$errs" ]; then
    echo "recent log error lines (tail):"
    printf '%s\n' "$errs" | sed 's/^/  /'
  else
    echo "recent log error lines: none"
  fi
}

compose() {
  echo "# Praetorium — Ops Snapshot"
  echo "_$(date -Is) · read-only single-pane ops view (NUC-41)_"
  echo
  echo "## Sprint Board"
  sprint_board_section
  echo
  echo "## Recent errors"
  recent_errors_section
  echo
  echo "## Fleet health (praetorium-status.sh)"
  echo '```'
  fleet_health
  echo '```'
}

resolve_ops_page_id() {
  local id="${OPS_PAGE_ID:-}"
  if [ -z "$id" ] && [ -f "$SECRETS_FILE" ]; then
    id=$(grep -E '^OPS_PAGE_ID=' "$SECRETS_FILE" 2>/dev/null | tail -1 \
           | cut -d= -f2- | tr -d "\"' ")
  fi
  printf '%s' "$id"
}

do_publish() {
  local page_id; page_id=$(resolve_ops_page_id)
  if [ -z "$page_id" ]; then
    echo "REFUSED: OPS_PAGE_ID is unset — cannot publish." >&2
    echo "This is Dave's gated finish: create the Notion ops page, then add" >&2
    echo "OPS_PAGE_ID=<page-id> to $SECRETS_FILE (or export it) and re-run --publish." >&2
    return 3
  fi
  compose | OPS_PAGE_ID="$page_id" python3 "$PUBLISH_BIN"
}

usage() {
  cat <<EOF
Usage: ops-view.sh [--dry-run|--publish]
  --dry-run   (default) compose the ops snapshot and print it to stdout.
              Writes NO Notion page; requires no secret.
  --publish   push the snapshot to the OPS_PAGE_ID Notion page. Refuses when
              OPS_PAGE_ID is unset (Dave's gated finish). Never creates a page.
EOF
}

main() {
  local mode="${1:---dry-run}"
  case "$mode" in
    ""|--dry-run) compose ;;
    --publish)    do_publish ;;
    -h|--help)    usage ;;
    *) echo "unknown argument: $mode" >&2; usage >&2; return 2 ;;
  esac
}

main "$@"
