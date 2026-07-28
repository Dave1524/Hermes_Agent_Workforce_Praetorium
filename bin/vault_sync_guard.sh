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
#          Local tracked edits => HARD FAIL (exit 1) naming the files that block it.
#          Rewritten upstream => resync (exit 0), see below.
#
# The mirror is a GENERATED ARTIFACT and the box authors none of it: the Mac's
# publish_boxsafe.sh rebuilds it and pushes with --force-with-lease by design ("rebuild
# overwrites stray main", 2026-07-08 open-bubble design). So origin/main legitimately
# rewrites history, and --ff-only alone can never converge afterwards: it rejects every
# run forever. That is the 2026-07-27 wedge — origin/main took a forced-update at 18:43,
# and qmd-refresh then failed every 30 minutes while qmd re-indexed a 2026-07-25 tree.
# A rewritten upstream is therefore a RESYNC (hard reset to origin), not a failure —
# but only from a clean tree. Local tracked changes still hard-fail, because those are
# the one thing on this box that upstream does not already have.
#   check  read-only freshness gate for the daily-rhythm jobs. Refuses (exit 1)
#          on a dirty tree or a mirror lagging origin by more than the max, so a
#          06:00 briefing is never generated from stale content.
#
# Untracked files are reported but never block: they cannot make a briefing wrong
# and cannot stop a fast-forward. Tracked modifications do both.
set -euo pipefail

VAULT_DIR="${VAULT_DIR:-$HOME/vault}"
MAX_LAG_HOURS="${VAULT_MAX_LAG_HOURS:-24}"
# Where the pre-resync tip is parked so a discard is recoverable, not silent.
RECOVERY_REF="refs/vault-sync-guard/pre-resync"

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

is_fast_forward() { git_v merge-base --is-ancestor HEAD "$1"; }

reject_dirty() {
  note "FAIL: sync onto $1 REJECTED — local tracked changes, the mirror is frozen until this is routed"
  printf '  %s\n' "$(tracked_changes)"
}

fast_forward_to() {
  git_v merge --ff-only --quiet "$1" 2>/dev/null || {
    note "FAIL: fast-forward onto $1 was REJECTED from a clean tree — an untracked file is in the way:"
    printf '  %s\n' "$(untracked_files)"
    return 1
  }
  note "OK: fast-forwarded to $(git_v rev-parse --short HEAD) ($1)"
}

resync_to() {
  local was; was=$(git_v rev-parse --short HEAD)
  git_v update-ref "$RECOVERY_REF" HEAD
  git_v reset --hard --quiet "$1"
  note "RESYNC: $1 was rewritten and no longer contains $was — mirror reset to $(git_v rev-parse --short HEAD)"
  note "  the old tip is parked at $RECOVERY_REF (git -C $VAULT_DIR reset --hard $RECOVERY_REF to undo)"
}

cmd_sync() {
  local up
  if ! fetch_origin; then
    note "SOFT: cannot reach origin (offline?) — tree left at $(git_v rev-parse --short HEAD)"
    return 0
  fi
  up=$(upstream_ref)
  if [ "$(git_v rev-parse HEAD)" = "$(git_v rev-parse "$up")" ]; then
    note "OK: already current with $up — nothing to pull"
    return 0
  fi
  if [ -n "$(tracked_changes)" ]; then
    reject_dirty "$up"
    return 1
  fi
  if is_fast_forward "$up"; then
    fast_forward_to "$up"
    return
  fi
  resync_to "$up"
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
  is_fast_forward "$up" || note "note: $up has diverged (rewritten upstream) — the next sync resyncs the mirror"
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
