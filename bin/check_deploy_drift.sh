#!/usr/bin/env bash
# check_deploy_drift.sh — is the box running what this repo says it runs?
#
# THE CHECK REPORTS; IT NEVER CONVERGES. No writes to /etc, no bin/deploy, no systemctl, no
# daemon-reload, no deletion in any tree. Its exit code and its output are the whole product.
# /etc/systemd/system is root-owned and `dave` cannot write it without sudo — installing a
# unit stays a human action, exactly as systemd/ttm-pool-drain.service records for its own.
#
# FOUR TREES, NOT THREE. D8 named source systemd/, the staging copy ~/agent-workforce/systemd/
# and live /etc/systemd/system/. It never mentioned ~/.config/systemd/user/, which holds the
# nine --user units the Buzz fleet runs on — including buzz-agent@.service, the fleet's core
# unit. The comparisons that mean something:
#
#   bin/            <-> ~/agent-workforce/bin/      the runtime tree every ExecStart names
#   systemd/        <-> /etc/systemd/system/        DIRECTLY, not via staging
#   systemd/user/   <-> ~/.config/systemd/user/     --user scope, never installed in /etc
#
# THE STAGING COPY ~/agent-workforce/systemd/ IS NOT A SIDE OF ANY COMPARISON, deliberately.
# systemd reads /etc and never reads it — proof: content-inbox-finalize.{service,timer} sit in
# the staging tree today and `systemctl list-unit-files` does not know them. bin/deploy rsyncs
# systemd/ into staging and never writes /etc (its PATHS array at bin/deploy:20 has no /etc
# entry), so comparing source against staging goes GREEN the moment a unit is deployed while
# /etc stays stale — a false green in exactly the direction that matters, and it is live right
# now: staging is byte-identical to source for all 55 units. Do not add it back.
#
# MEMBERSHIP IS COMPARED IN BOTH DIRECTIONS. A unit present in one tree and absent from the
# other is invisible to a byte-comparison of the units that exist in both, which is all the
# 2026-09-01 deploy checked. Both directions are red: /etc-only (a rebuild from source loses
# it) and source-only (the box is not running what the repo says).
#
# OWNERSHIP FAILS CLOSED. An installed unit with no source counterpart is RED unless a
# declaration in this repo explains it — design/unit-ownership.toml for permanent third-party
# and never-commit entries, and the owning manifest's status = "campaign" + expires for the
# dated ones. Never a heuristic over unit contents: "references /home/dave" or "User=dave"
# misclassifies systemd/ttm-pool-drain.service, which is ours and has neither.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"

# Every tree is overridable so the suite can build synthetic ones. A test that pointed at the
# live box would be red for reasons unrelated to the code under test, and everyone would learn
# to ignore it.
SRC_BIN="${DRIFT_SRC_BIN:-$REPO/bin}"
RUNTIME_BIN="${DRIFT_RUNTIME_BIN:-$HOME/agent-workforce/bin}"
SRC_SYSTEM="${DRIFT_SRC_SYSTEM:-$REPO/systemd}"
ETC="${DRIFT_ETC:-/etc/systemd/system}"
SRC_USER="${DRIFT_SRC_USER:-$REPO/systemd/user}"
USER_TREE="${DRIFT_USER:-$HOME/.config/systemd/user}"
OWNERSHIP="${DRIFT_OWNERSHIP:-$REPO/design/unit-ownership.toml}"
MANIFESTS="${DRIFT_MANIFESTS:-$REPO/design/agents}"
# Fixture clock. A dated exclusion asserted against `date` is correct only until the date
# passes, at which point the assertion changes meaning with nobody touching it.
NOW="${DRIFT_NOW:-$(date '+%Y-%m-%d %H:%M:%S')}"

findings=0

report() { echo "  DRIFT [$1] $2"; findings=$((findings + 1)); }
info()   { echo "  info: $*"; }

# LC_ALL=C on every sort feeding comm. comm compares bytes; sort collates by locale, and on
# this tree they disagree over '@' (praetorium-phaseb-brief@2.timer), so a locale sort makes
# comm emit "not in sorted order" on stderr and SKIP LINES — the diff then fails toward
# "nothing new", which is the one direction a drift check must never fail in.
names() { # dir, then find-args; prints basenames, byte-sorted
  local dir=$1; shift
  [ -d "$dir" ] || return 0
  find "$dir" -maxdepth 1 -type f "$@" -printf '%f\n' 2>/dev/null | LC_ALL=C sort
}

# --- the declarations ------------------------------------------------------------------
# Read once, in python, because the sources are TOML. Emits one line per declared exclusion:
#   third_party <unit>
#   campaign <unit-stem> <expires>            (from the owning manifest, not re-keyed here)
declarations=$(OWNERSHIP="$OWNERSHIP" MANIFESTS="$MANIFESTS" python3 <<'PY'
import os, pathlib, tomllib
own = pathlib.Path(os.environ["OWNERSHIP"])
if own.is_file():
    for row in tomllib.loads(own.read_text()).get("third_party", []):
        print("third_party", row.get("unit", ""))
manifests = pathlib.Path(os.environ["MANIFESTS"])
if manifests.is_dir():
    for m in sorted(manifests.glob("*.toml")):
        for w in tomllib.loads(m.read_text()).get("workflows", []):
            if w.get("status") == "campaign" and w.get("expires"):
                print("campaign", w.get("unit", ""), w["expires"])
PY
)

declared_third_party() { grep -qx "third_party $1" <<<"$declarations"; }

# A dated exclusion is consulted only when it is actually silencing a membership difference.
# Its date must then be in the future: an expired entry still doing work is how a list teaches
# everyone to ignore a red. Entries for units with no drift are not checked, because a unit
# present in both trees needs no exclusion at all.
campaign_expiry() { # unit file -> expires, or empty
  local stem=${1%.*} line
  line=$(grep -m1 "^campaign ${stem} " <<<"$declarations") || return 1
  cut -d' ' -f3- <<<"$line"
}

# --- bin/ <-> runtime ------------------------------------------------------------------
# Ignores __pycache__/ and *.bak*, both live in the runtime tree today (seven *.bak-* scripts
# and one __pycache__), and both are runtime debris rather than deployed content.
echo "bin: $SRC_BIN <-> $RUNTIME_BIN"
bin_src=$(names "$SRC_BIN" ! -name '*.bak*')
bin_run=$(names "$RUNTIME_BIN" ! -name '*.bak*')
if [ -z "$bin_src" ]; then
  report bin "source tree $SRC_BIN matched no files — a clean result here would mean nothing"
fi
while IFS= read -r f; do [ -n "$f" ] && report bin "source-only: $f is not deployed"; done \
  < <(comm -23 <(echo "$bin_src") <(echo "$bin_run"))
while IFS= read -r f; do [ -n "$f" ] && report bin "runtime-only: $f has no source"; done \
  < <(comm -13 <(echo "$bin_src") <(echo "$bin_run"))
while IFS= read -r f; do
  [ -n "$f" ] || continue
  cmp -s "$SRC_BIN/$f" "$RUNTIME_BIN/$f" || report bin "content differs: $f"
done < <(comm -12 <(echo "$bin_src") <(echo "$bin_run"))

# --- systemd/ <-> /etc -----------------------------------------------------------------
# maxdepth 1 and -type f: systemd/user/ and systemd/archive/ are NOT part of this comparison,
# and neither are the eight OS alias symlinks in /etc. Both exclusions are stated rather than
# inherited from a glob, because both are load-bearing — sweeping systemd/user/ in here would
# demand that a --user unit appear in /etc, and sweeping systemd/archive/ in would report six
# deliberately-retired units as source-only.
echo "system units: $SRC_SYSTEM <-> $ETC"
sys_src=$(names "$SRC_SYSTEM" \( -name '*.service' -o -name '*.timer' \))
sys_etc=$(names "$ETC" \( -name '*.service' -o -name '*.timer' \))
if [ -z "$sys_src" ]; then
  report system "source tree $SRC_SYSTEM matched no units — a clean result here would mean nothing"
fi
while IFS= read -r f; do
  [ -n "$f" ] || continue
  expires=$(campaign_expiry "$f")
  if [ -n "$expires" ]; then
    if [[ "$NOW" > "$expires" ]]; then
      report system "source-only: $f — its campaign exclusion EXPIRED at $expires"
    else
      info "source-only: $f — campaign, excluded until $expires"
    fi
  else
    report system "source-only: $f is in this repo and not installed in $ETC"
  fi
done < <(comm -23 <(echo "$sys_src") <(echo "$sys_etc"))

while IFS= read -r f; do
  [ -n "$f" ] || continue
  if declared_third_party "$f"; then
    info "etc-only: $f — declared third-party, not ours"
    continue
  fi
  expires=$(campaign_expiry "$f")
  if [ -n "$expires" ]; then
    if [[ "$NOW" > "$expires" ]]; then
      report system "etc-only: $f — its campaign exclusion EXPIRED at $expires"
    else
      info "etc-only: $f — campaign, excluded until $expires"
    fi
    continue
  fi
  report system "etc-only: $f is installed with no source here — a rebuild from source loses it"
done < <(comm -13 <(echo "$sys_src") <(echo "$sys_etc"))

while IFS= read -r f; do
  [ -n "$f" ] || continue
  cmp -s "$SRC_SYSTEM/$f" "$ETC/$f" || report system "content differs: $f"
done < <(comm -12 <(echo "$sys_src") <(echo "$sys_etc"))

# --- system drop-ins -------------------------------------------------------------------
# A drop-in silently overrides its unit, so an unnoticed one is worse than an unnoticed unit.
# Compared by <unit>.d/<file>.conf relative path. /etc-side .d directories belonging to a
# declared third-party unit are skipped: ollama.service.d is the installer's, like its unit.
echo "system drop-ins: $SRC_SYSTEM/*.d <-> $ETC/*.d"
dropins() {
  local root=$1
  [ -d "$root" ] || return 0
  find "$root" -mindepth 2 -maxdepth 2 -type f -name '*.conf' -printf '%P\n' 2>/dev/null \
    | LC_ALL=C sort
}
di_src=$(dropins "$SRC_SYSTEM")
di_etc=$(dropins "$ETC")
while IFS= read -r f; do
  [ -n "$f" ] || continue
  # ${f%%.d/*} on "ollama.service.d/vulkan.conf" is already "ollama.service" — appending
  # .service again asks the declaration about "ollama.service.service" and never matches.
  declared_third_party "${f%%.d/*}" && continue
  report dropin "etc-only: $f has no source here"
done < <(comm -13 <(echo "$di_src") <(echo "$di_etc"))
while IFS= read -r f; do
  [ -n "$f" ] && report dropin "source-only: $f is not installed"
done < <(comm -23 <(echo "$di_src") <(echo "$di_etc"))
while IFS= read -r f; do
  [ -n "$f" ] || continue
  cmp -s "$SRC_SYSTEM/$f" "$ETC/$f" || report dropin "content differs: $f"
done < <(comm -12 <(echo "$di_src") <(echo "$di_etc"))

# --- systemd/user/ <-> ~/.config/systemd/user ------------------------------------------
echo "user units: $SRC_USER <-> $USER_TREE"
usr_src=$(names "$SRC_USER" \( -name '*.service' -o -name '*.timer' \))
usr_live=$(names "$USER_TREE" \( -name '*.service' -o -name '*.timer' \))
while IFS= read -r f; do
  [ -n "$f" ] && report user "live-only: $f runs on this box with no source here"
done < <(comm -13 <(echo "$usr_src") <(echo "$usr_live"))
while IFS= read -r f; do
  [ -n "$f" ] && report user "source-only: $f is in this repo and not installed"
done < <(comm -23 <(echo "$usr_src") <(echo "$usr_live"))
while IFS= read -r f; do
  [ -n "$f" ] || continue
  cmp -s "$SRC_USER/$f" "$USER_TREE/$f" || report user "content differs: $f"
done < <(comm -12 <(echo "$usr_src") <(echo "$usr_live"))

# User-tree drop-ins are OUT OF SCOPE for this comparison and are counted out loud rather
# than skipped, so the gap is visible in every run instead of being rediscovered. Three of
# them carry BUZZ_AUTH_TAG and must never enter this repo (design/unit-ownership.toml
# [[never_commit]]); the rest are per-agent model and harness overrides that this brief did
# not adopt. Giving them a source home is a change of its own.
if [ -d "$USER_TREE" ]; then
  n=$(find "$USER_TREE" -mindepth 2 -name '*.conf' 2>/dev/null | wc -l)
  [ "$n" -gt 0 ] && info "user drop-ins: $n *.conf files NOT compared (see design/unit-ownership.toml)"
fi

# The staging copy, named so the next reader does not add it as a comparison side.
info "staging ${AGENT_WORKFORCE_RUNTIME:-$HOME/agent-workforce}/systemd/ is inert — systemd reads $ETC, never it"

if [ "$findings" -eq 0 ]; then
  echo "drift: clean"
else
  echo "drift: $findings finding(s)"
fi
exit $(( findings > 0 ))
