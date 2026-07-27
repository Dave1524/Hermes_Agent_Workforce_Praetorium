#!/usr/bin/env bash
# NUC-45: the one owner of "is the vault mirror actually current?".
#
# Replaces the inline `git pull --ff-only || echo "... (offline?)"` in
# qmd-refresh.service, which masked a REJECTED pull as an offline blip: the unit
# exited 0, systemd logged Finished, no OnFailure fired, and qmd re-indexed a
# frozen tree for four days (2026-07-23 → 07-27) while every health check read
# green. A pull the remote refused and a pull the network prevented are different
# events and must exit differently.
#
#   sync   fetch + fast-forward. Offline => soft (exit 0, tree untouched).
#          Rejected merge => HARD FAIL (exit 1) naming the files that block it.
#   check  read-only freshness gate for the daily-rhythm jobs. Refuses (exit 1)
#          on a dirty tree or a mirror lagging origin by more than the max, so a
#          06:00 briefing is never generated from stale content.
#
# Untracked files are reported but never block: they cannot make a briefing wrong
# and cannot stop a fast-forward. Tracked modifications do both.
set -euo pipefail

VAULT_DIR="${VAULT_DIR:-$HOME/vault}"
MAX_LAG_HOURS="${VAULT_MAX_LAG_HOURS:-24}"

note() { printf '%s vault_sync_guard[%s]: %s\n' "$(date -Is)" "$mode" "$*"; }
git_v() { git -C "$VAULT_DIR" "$@"; }

usage() {
  echo "usage: $(basename "$0") sync|check [--path DIR] [--max-lag-hours N]" >&2
  exit 2
}

tracked_changes() { git_v status --porcelain --untracked-files=no; }
untracked_files() { git_v ls-files --others --exclude-standard; }

upstream_ref() {
  git_v rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' 2>/dev/null && return 0
  echo "origin/$(git_v rev-parse --abbrev-ref HEAD)"
}

commit_epoch() { git_v log -1 --format=%ct "$1"; }

# "Last time origin was actually reachable." git rewrites FETCH_HEAD even when the
# fetch FAILS, so its mtime says nothing — the guard keeps its own stamp instead.
stamp_path() {
  local p
  [ -z "${VAULT_SYNC_STAMP:-}" ] || { echo "$VAULT_SYNC_STAMP"; return 0; }
  p=$(git_v rev-parse --git-path vault_sync_guard_last_fetch)
  case "$p" in /*) ;; *) p="$VAULT_DIR/$p" ;; esac
  echo "$p"
}

fetch_origin() {
  git_v fetch --quiet origin 2>/dev/null || return 1
  : > "$(stamp_path)" 2>/dev/null || true
}

report_untracked() {
  local stray; stray=$(untracked_files || true)
  [ -n "$stray" ] || return 0
  note "note: untracked (not blocking, still unrouted):"
  printf '  %s\n' "$stray"
}

cmd_sync() {
  local up head
  if ! fetch_origin; then
    note "SOFT: cannot reach origin (offline?) — tree left at $(git_v rev-parse --short HEAD)"
    return 0
  fi
  up=$(upstream_ref)
  head=$(git_v rev-parse HEAD)
  if [ "$head" = "$(git_v rev-parse "$up")" ]; then
    note "OK: already current with $up — nothing to pull"
    return 0
  fi
  if git_v merge --ff-only --quiet "$up" 2>/dev/null; then
    note "OK: fast-forwarded to $(git_v rev-parse --short HEAD) ($up)"
    return 0
  fi
  note "FAIL: fast-forward onto $up was REJECTED — the mirror is frozen until this is routed"
  printf '  %s\n' "$(tracked_changes)"
  return 1
}

lag_verdict() {
  local lag_seconds=$1 label=$2 max_seconds=$(( MAX_LAG_HOURS * 3600 ))
  if [ "$lag_seconds" -gt "$max_seconds" ]; then
    note "REFUSE: $label ($(( lag_seconds / 3600 ))h > ${MAX_LAG_HOURS}h) — a briefing off this tree would be confidently wrong"
    return 1
  fi
  note "OK: $label ($(( lag_seconds / 3600 ))h, within ${MAX_LAG_HOURS}h)"
  return 0
}

check_against_origin() {
  local up head_ts up_ts
  up=$(upstream_ref)
  if [ "$(git_v rev-parse HEAD)" = "$(git_v rev-parse "$up")" ]; then
    note "OK: in sync with $up at $(git_v rev-parse --short HEAD)"
    return 0
  fi
  head_ts=$(commit_epoch HEAD)
  up_ts=$(commit_epoch "$up")
  lag_verdict "$(( up_ts - head_ts ))" "mirror is behind $up"
}

check_offline() {
  local last_ts now_ts
  last_ts=$(stat -c %Y "$(stamp_path)" 2>/dev/null || echo 0)
  now_ts=$(date +%s)
  note "WARN: cannot reach origin — falling back to last confirmed sync"
  lag_verdict "$(( now_ts - last_ts ))" "last confirmed sync with origin"
}

cmd_check() {
  local dirty
  dirty=$(tracked_changes)
  if [ -n "$dirty" ]; then
    note "REFUSE: $VAULT_DIR has uncommitted tracked changes — the mirror cannot fast-forward:"
    printf '  %s\n' "$dirty"
    return 1
  fi
  report_untracked
  if fetch_origin; then
    check_against_origin
  else
    check_offline
  fi
}

mode=""
while [ $# -gt 0 ]; do
  case "$1" in
    sync|check) mode="$1"; shift ;;
    --path) VAULT_DIR="${2:-}"; shift 2 ;;
    --max-lag-hours) MAX_LAG_HOURS="${2:-}"; shift 2 ;;
    *) usage ;;
  esac
done
[ -n "$mode" ] || usage
[ -e "$VAULT_DIR/.git" ] || { note "FAIL: $VAULT_DIR is not a git checkout"; exit 1; }

case "$mode" in
  sync) cmd_sync ;;
  check) cmd_check ;;
esac
