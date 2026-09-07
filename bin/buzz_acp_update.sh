#!/usr/bin/env bash
# buzz_acp_update.sh — keep the box's Buzz CLI and ACP harness current with upstream.
#
# THE PROBLEM THIS EXISTS FOR. Between 2026-07-31 and 2026-09-07 this box ran a buzz-acp
# twelve releases behind upstream, and nothing on the box could have said so. Dave updates
# Buzz Desktop on the Mac regularly and reasonably read that as "Buzz is up to date" — it
# is not, and the reason is worth stating once because it is not obvious:
#
#   Desktop (Mac) and the CLI (this box) are TWO INDEPENDENT INSTALLS OF ONE RELEASE
#   STREAM. Every upstream release is tagged desktop-vX.Y.Z; there has never been a
#   CLI-only release line, and there is no standalone `buzz` or `buzz-acp` asset. The CLI
#   ships INSIDE Buzz_X.Y.Z_amd64.deb at usr/bin/, as a byproduct of packaging the app.
#   Desktop carries a Tauri auto-updater (updater-manifest.json is a release asset), which
#   is why the Mac keeps itself current and prompts. This box has no equivalent: the two
#   binaries in ~/.local/bin were extracted from a .deb by hand, once, and nothing looked
#   again. There is no dpkg package to `apt upgrade` — `dpkg -l | grep buzz` finds only
#   libharfbuzz. So the Mac being current says nothing about the box, in either direction.
#
# WHAT IS AUTOMATIC AND WHAT IS NOT. `check` runs daily from agent-buzz-acp-update.timer
# and is the half that fixes the actual defect, which was not knowing. `apply` is one
# supervised command. That split is not caution for its own sake — the binary swap
# restarts every agent in the fleet onto a harness whose flag surface no release note
# promises, and buzz-acp rejects an unknown flag at startup while Restart=on-failure turns
# that into a crash loop rather than a visible stop. So a new release has to be fetched and
# PROBED before anyone can know it is safe, and when the probe fails the right outcome is a
# report, not an install. Making apply unattended is a one-line change to the unit once a
# few releases have gone through cleanly; the probe is what would make that defensible.
#
# THE RECEIPT IS PINNED TO THE BYTES, NOT TRUSTED. Neither binary answers --version and
# neither carries the release version: `strings` finds 0.5.3 in both the July build and the
# September one, because that is a dependency crate, not the release. sha256 is therefore
# the only honest identity an installed binary has. The receipt records tag AND hashes, and
# every command re-hashes the live files before believing the tag. A receipt that describes
# bytes which are no longer there reports UNPINNED and refuses to reason about versions —
# the alternative is a note about the artifact standing in for the artifact, which is the
# same defect as a document count written into prose.
#
#   check     compare installed against upstream latest; stage+probe a new tag once
#   stage     fetch and extract one release, hash it, probe it. Touches nothing live
#   probe     compatibility-check ANY buzz-acp against the flags the unit passes
#   apply     supervised install: backup, canary restart, gate, auto-rollback on failure
#   rollback  restore the previous backup and restart the fleet
#   adopt     write a receipt for what is installed right now, given its tag
#   status    human-readable summary; always exits 0
#
# EXIT CODES. check: 0 current, 10 behind, 1 unpinned or receipt missing. A transient
# network failure exits 0 with a note and only becomes a failure after STALE_CHECK_DAYS,
# because agent-alert@ fires on any non-zero and one blip should not page Dave — while a
# checker that has silently not reached GitHub for a week is exactly what this job exists
# to prevent a second time.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VAR="${BUZZ_UPDATE_VAR:-$HOME/agent-workforce/var}"
RECEIPT="$VAR/buzz-cli-install.json"
STAGE_ROOT="$VAR/buzz-stage"
LOCAL_BIN="${BUZZ_UPDATE_BIN:-$HOME/.local/bin}"
UNIT="${BUZZ_UPDATE_UNIT:-$HOME/.config/systemd/user/buzz-agent@.service}"
API="${BUZZ_UPDATE_API:-https://api.github.com/repos/block/buzz/releases/latest}"
DL_BASE="${BUZZ_UPDATE_DL:-https://github.com/block/buzz/releases/download}"
UA='praetorium-box (agent-workforce buzz_acp_update.sh)'
BINARIES=(buzz buzz-acp)
STALE_CHECK_DAYS="${BUZZ_UPDATE_STALE_DAYS:-7}"
STAGE_WORK=""
trap 'rm -rf "${STAGE_WORK:-}"' EXIT

note() { printf '%s\n' "$*" >&2; }
die()  { note "buzz_acp_update: $*"; exit 1; }

sha_of() { sha256sum "$1" 2>/dev/null | cut -d' ' -f1; }

# The tag carries the version as desktop-vX.Y.Z; the .deb asset spells it X.Y.Z.
version_of_tag() { printf '%s' "${1#desktop-v}"; }

# ---------------------------------------------------------------------------
# probe — the compatibility predicate, and the reason apply is safe to run at all.
#
# One owner: tests/test_buzz_acp_update.sh calls this rather than restating it, so
# the check that gates an install and the check that fails the gate cannot disagree. It
# takes a PATH, not the installed binary, which is what lets a candidate be judged before
# it is anywhere near the fleet.
#
# The control literal is checked first and separately. If strings(1) yields nothing useful
# for a build, every capability below would read as absent — one broken method presenting
# as three missing features.
# ---------------------------------------------------------------------------
WAKE_LITERALS=('buzz:workflow' 'buzz:workflow-owner' 'buzz:workflow-mention')
CONTROL_LITERAL='buzz:config-nudge'

probe() {
  local acp=$1 unit=${2:-$UNIT} findings=0 help unit_flags f
  [ -f "$acp" ] || { echo "  probe: no such binary: $acp"; return 1; }

  if [ "$(strings "$acp" | grep -c -- "$CONTROL_LITERAL")" -eq 0 ]; then
    echo "  FAIL control: strings(1) finds no '$CONTROL_LITERAL' — extraction is broken for"
    echo "                this build, so every absence below would be unreadable. Not a verdict"
    echo "                on the release."
    return 1
  fi
  echo "  ok control: strings reads this binary, so an absence below is a real absence"

  for lit in "${WAKE_LITERALS[@]}"; do
    if [ "$(strings "$acp" | grep -c -- "$lit")" -ge 1 ]; then
      echo "  ok wake: $lit"
    else
      echo "  FAIL wake: $lit absent — a scheduled workflow cannot wake an agent (upstream #6953)"
      findings=$((findings + 1))
    fi
  done

  if [ ! -f "$unit" ]; then
    echo "  FAIL flags: no unit at $unit — cannot tell which flags must survive"
    return 1
  fi
  help=$("$acp" --help 2>&1)
  unit_flags=$(grep -oE '^[[:space:]]+--[a-z-]+' "$unit" | tr -d ' ' | sort -u)
  if [ "$(printf '%s\n' "$unit_flags" | grep -c .)" -lt 5 ]; then
    echo "  FAIL flags: parsed fewer than 5 flags from the unit — the loop below would be vacuous"
    return 1
  fi
  while read -r f; do
    [ -n "$f" ] || continue
    if printf '%s' "$help" | grep -q -- "$f"; then
      echo "  ok flag: $f"
    else
      echo "  FAIL flag: $f is gone from --help — this release would crash-loop the fleet"
      findings=$((findings + 1))
    fi
  done <<< "$unit_flags"

  [ "$findings" -eq 0 ]
}

# ---------------------------------------------------------------------------
# receipt
# ---------------------------------------------------------------------------
receipt_field() {
  [ -f "$RECEIPT" ] || return 1
  python3 -c 'import json,sys
d=json.load(open(sys.argv[1]))
for k in sys.argv[2].split("."):
    d=d[k]
print(d)' "$RECEIPT" "$1" 2>/dev/null
}

write_receipt() {
  local tag=$1 src=$2
  mkdir -p "$VAR"
  local tmp="$RECEIPT.tmp"
  {
    printf '{\n  "tag": "%s",\n  "source_asset": "%s",\n' "$tag" "$src"
    printf '  "installed_utc": "%s",\n  "binaries": {\n' "$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
    local first=1
    for b in "${BINARIES[@]}"; do
      [ $first -eq 1 ] || printf ',\n'
      first=0
      printf '    "%s": {"path": "%s", "sha256": "%s"}' "$b" "$LOCAL_BIN/$b" "$(sha_of "$LOCAL_BIN/$b")"
    done
    printf '\n  }\n}\n'
  } > "$tmp"
  mv "$tmp" "$RECEIPT"
}

# The receipt is only as good as its agreement with the live files. Checked on every path
# that reads a version, never assumed.
receipt_matches_disk() {
  local b recorded live
  for b in "${BINARIES[@]}"; do
    recorded=$(receipt_field "binaries.$b.sha256") || return 1
    live=$(sha_of "$LOCAL_BIN/$b")
    [ -n "$live" ] || { note "  $b: not installed at $LOCAL_BIN/$b"; return 1; }
    [ "$recorded" = "$live" ] || {
      note "  $b: receipt says ${recorded:0:12}, disk is ${live:0:12}"
      return 1
    }
  done
  return 0
}

# ---------------------------------------------------------------------------
# upstream
# ---------------------------------------------------------------------------
# /releases/latest, not a tag list. Upstream carries three tag schemes at once — the
# current desktop-vX.Y.Z, an older bare vX.Y.Z, and rolling names (sprig-latest,
# buzz-desktop-latest) — so "highest tag" and "most recent tag" both pick wrong. This
# endpoint is GitHub's own answer for most-recent non-draft non-prerelease.
latest_tag() {
  curl -sS --max-time 30 -H "User-Agent: $UA" "$API" 2>/dev/null \
    | python3 -c 'import json,sys
try:
    print(json.load(sys.stdin)["tag_name"])
except Exception:
    raise SystemExit(1)' 2>/dev/null
}

stage_dir_for() { printf '%s/%s' "$STAGE_ROOT" "$1"; }

# ---------------------------------------------------------------------------
# stage — fetch one release and extract the two binaries. Touches nothing live.
# ---------------------------------------------------------------------------
# Returns non-zero rather than calling die: check() invokes this, and there a fetch failure
# must not preempt the verdict. A box that is BEHIND and offline reported exit 1 ("this job
# is broken") instead of exit 10 ("you are behind") — the wrong half of a two-part message.
stage() {
  local tag=$1 ver dir deb work
  ver=$(version_of_tag "$tag")
  dir=$(stage_dir_for "$tag")
  deb="Buzz_${ver}_amd64.deb"

  if [ -f "$dir/buzz-acp" ] && [ -f "$dir/buzz" ]; then
    echo "already staged: $dir"
    return 0
  fi

  work=$(mktemp -d) || { note "mktemp failed"; return 1; }
  # NOT a RETURN trap. `trap ... RETURN` set inside a function is global unless functrace
  # is on, so it fires again when the CALLER returns — where $work is out of scope and
  # set -u turns the cleanup into a spurious exit 1, replacing this job's real verdict.
  # Measured: check() reported the correct "behind" result and then exited 1 instead of 10.
  STAGE_WORK="$work"

  echo "fetching $deb ..."
  curl -sSL --max-time 900 -H "User-Agent: $UA" -o "$work/$deb" "$DL_BASE/$tag/$deb" \
    || { note "download failed: $DL_BASE/$tag/$deb"; return 1; }
  [ -s "$work/$deb" ] || { note "downloaded $deb is empty"; return 1; }

  # dpkg-deb -x rather than dpkg -i: this is not a system package install, and never has
  # been. The binaries live in ~/.local/bin as files, so extraction is the whole operation.
  dpkg-deb -x "$work/$deb" "$work/root" || { note "dpkg-deb could not extract $deb"; return 1; }

  mkdir -p "$dir"
  local b
  for b in "${BINARIES[@]}"; do
    [ -f "$work/root/usr/bin/$b" ] || {
      note "$deb contains no usr/bin/$b — upstream changed the layout"; return 1; }
    install -m 0755 "$work/root/usr/bin/$b" "$dir/$b"
  done
  ( cd "$dir" && sha256sum "${BINARIES[@]}" > SHA256SUMS )
  printf '%s\n' "$deb" > "$dir/ASSET"
  echo "staged $tag at $dir"
  cat "$dir/SHA256SUMS"
}

fleet_units() {
  systemctl --user list-units 'buzz-agent@*' --all --no-legend 2>/dev/null \
    | awk '{print $1}' | grep '^buzz-agent@' | sort
}

# ---------------------------------------------------------------------------
# apply — supervised. Backup, canary, gate, rollback.
# ---------------------------------------------------------------------------
backup_dir_for() { printf '%s/buzz-backup-%s-%s' "$LOCAL_BIN" "$(receipt_field tag || echo unknown)" "$(date '+%Y-%m-%d')"; }

restart_and_settle() {
  local unit=$1
  systemctl --user restart "$unit" || return 1
  # buzz-acp connects to the relay before it is doing anything useful, and a rejected flag
  # exits immediately into Restart=on-failure. Give it long enough to fail.
  local i
  for i in 1 2 3 4 5 6 7 8 9 10; do
    /usr/bin/env sleep 1
    [ "$(systemctl --user show "$unit" -p NRestarts --value)" = "0" ] || return 1
  done
  [ "$(systemctl --user is-active "$unit")" = "active" ]
}

apply() {
  local tag=$1 dir backup b
  dir=$(stage_dir_for "$tag")
  [ -f "$dir/buzz-acp" ] || die "$tag is not staged — run: $0 stage $tag"

  echo "--- probing the staged $tag before anything live is touched ---"
  probe "$dir/buzz-acp" || die "$tag fails the compatibility probe; refusing to install it"

  backup=$(backup_dir_for)
  mkdir -p "$backup"
  for b in "${BINARIES[@]}"; do
    cp -p "$LOCAL_BIN/$b" "$backup/$b" || die "could not back up $b"
  done
  ( cd "$backup" && sha256sum "${BINARIES[@]}" > SHA256SUMS )
  echo "backed up the running binaries to $backup"

  for b in "${BINARIES[@]}"; do
    install -m 0755 "$dir/$b" "$LOCAL_BIN/$b" || die "could not install $b"
  done
  echo "installed $tag into $LOCAL_BIN"

  # Canary, then the rest. A bad binary takes down one agent instead of five, and the
  # rollback below runs while four of them are still serving.
  local canary rest u
  canary=$(fleet_units | head -1)
  rest=$(fleet_units | tail -n +2)
  echo "--- canary restart: $canary ---"
  if ! restart_and_settle "$canary"; then
    note "canary $canary did not settle — rolling back"
    rollback_to "$backup"
    return 1
  fi
  for u in $rest; do
    echo "--- restarting $u ---"
    if ! restart_and_settle "$u"; then
      note "$u did not settle — rolling back"
      rollback_to "$backup"
      return 1
    fi
  done

  write_receipt "$tag" "$(cat "$dir/ASSET" 2>/dev/null || echo unknown)"
  echo "receipt updated: $RECEIPT"
  echo "--- fleet gate ---"
  if [ -x "$HOME/.config/buzz-team/verify-fleet.sh" ]; then
    if ! "$HOME/.config/buzz-team/verify-fleet.sh"; then
      note "verify-fleet FAILED after installing $tag — rolling back"
      rollback_to "$backup"
      return 1
    fi
  else
    note "note: verify-fleet.sh not found; the install stands but is ungated"
  fi
  echo "applied $tag"
}

rollback_to() {
  local backup=$1 b u
  [ -d "$backup" ] || die "no backup at $backup"
  for b in "${BINARIES[@]}"; do
    [ -f "$backup/$b" ] || die "backup is missing $b — refusing a partial rollback"
  done
  for b in "${BINARIES[@]}"; do
    install -m 0755 "$backup/$b" "$LOCAL_BIN/$b"
  done
  for u in $(fleet_units); do systemctl --user restart "$u" || true; done
  note "rolled back from $backup; re-run the fleet gate by hand before trusting the fleet"
}

newest_backup() { ls -1d "$LOCAL_BIN"/buzz-backup-* 2>/dev/null | sort | tail -1; }

# ---------------------------------------------------------------------------
# check — the daily job. Non-zero reaches Dave through agent-alert@.
# ---------------------------------------------------------------------------
last_ok_file() { printf '%s/buzz-cli-check-last-ok' "$VAR"; }

check() {
  if [ ! -f "$RECEIPT" ]; then
    note "no install receipt at $RECEIPT."
    note "Nothing here knows which release the running binaries came from, and they carry no"
    note "version string, so this cannot be inferred — only recorded. Fix with:"
    note "    $0 adopt <tag>        e.g. $0 adopt desktop-v0.5.23"
    return 1
  fi
  local installed
  installed=$(receipt_field tag)
  if ! receipt_matches_disk; then
    note "UNPINNED: the receipt says $installed but the binaries on disk are not those bytes."
    note "Something replaced them outside this tool. Re-adopt once you know what is installed:"
    note "    $0 adopt <tag>"
    return 1
  fi

  local latest
  latest=$(latest_tag)
  if [ -z "$latest" ]; then
    # Fail-soft, but not forever. A blip must not page Dave; a week of silence must.
    local last age
    last=$(cat "$(last_ok_file)" 2>/dev/null || echo 0)
    age=$(( ( $(date +%s) - last ) / 86400 ))
    if [ "$last" -gt 0 ] && [ "$age" -lt "$STALE_CHECK_DAYS" ]; then
      echo "could not reach GitHub; last successful check was ${age}d ago (under ${STALE_CHECK_DAYS}d, not reporting)"
      return 0
    fi
    note "could not reach GitHub, and the last successful check was ${age}d ago"
    note "(threshold ${STALE_CHECK_DAYS}d). This job has not known the upstream version for a week."
    return 1
  fi
  date +%s > "$(last_ok_file)"

  if [ "$latest" = "$installed" ]; then
    echo "buzz CLI/ACP is current: $installed"
    return 0
  fi

  note "buzz CLI/ACP is behind: installed $installed, upstream latest $latest"
  # Stage ONCE PER TAG, not once per run. The 24h reminder that keeps this visible must not
  # re-download 117 MB every day it goes unactioned.
  local dir
  dir=$(stage_dir_for "$latest")
  if [ ! -f "$dir/buzz-acp" ]; then
    note "staging $latest so the compatibility verdict below is about the real binary ..."
    stage "$latest" >&2 || { note "staging failed; the verdict below is unavailable"; return 10; }
  fi
  note "--- compatibility of $latest against this box's unit ---"
  if probe "$dir/buzz-acp" >&2; then
    note "$latest passes the probe. Install with:  $0 apply $latest"
  else
    note "$latest FAILS the probe — do not install it unattended. The findings above say what"
    note "changed; the unit's ExecStart is what has to be reconciled first."
  fi
  return 10
}

status() {
  echo "installed receipt: $RECEIPT"
  if [ -f "$RECEIPT" ]; then
    python3 -m json.tool "$RECEIPT"
    if receipt_matches_disk; then echo "  pinned: live binaries match the receipt"
    else echo "  UNPINNED: live binaries do NOT match the receipt"; fi
  else
    echo "  (none — run: $0 adopt <tag>)"
  fi
  echo "upstream latest: $(latest_tag || echo unreachable)"
  echo "staged releases: $(ls -1 "$STAGE_ROOT" 2>/dev/null | tr '\n' ' ' || echo none)"
  echo "backups:         $(ls -1d "$LOCAL_BIN"/buzz-backup-* 2>/dev/null | tr '\n' ' ' || echo none)"
  return 0
}

cmd=${1:-check}
case "$cmd" in
  check)    check ;;
  status)   status ;;
  probe)    [ $# -ge 2 ] || die "usage: $0 probe <path-to-buzz-acp> [unit]"; probe "$2" "${3:-$UNIT}" ;;
  stage)    [ $# -ge 2 ] || die "usage: $0 stage <tag>"; stage "$2" || die "staging $2 failed" ;;
  apply)    [ $# -ge 2 ] || die "usage: $0 apply <tag>"; apply "$2" ;;
  rollback) rollback_to "${2:-$(newest_backup)}" ;;
  adopt)    [ $# -ge 2 ] || die "usage: $0 adopt <tag>"
            write_receipt "$2" "Buzz_$(version_of_tag "$2")_amd64.deb"
            echo "adopted:"; python3 -m json.tool "$RECEIPT" ;;
  *)        die "unknown command: $cmd (check|status|probe|stage|apply|rollback|adopt)" ;;
esac
