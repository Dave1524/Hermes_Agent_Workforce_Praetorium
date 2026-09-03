#!/usr/bin/env bash
# check_deploy_drift.sh — is the box running what this repo says it runs?
#
# THE CHECK REPORTS; IT NEVER CONVERGES. No writes to /etc, no bin/deploy, no systemctl, no
# daemon-reload, no deletion in any tree. Its exit code and its output are the whole product.
# /etc/systemd/system is root-owned and `dave` cannot write it without sudo — installing a
# unit stays a human action, exactly as systemd/ttm-pool-drain.service records for its own.
#
# FIVE TREES, NOT THREE. D8 named source systemd/, the staging copy ~/agent-workforce/systemd/
# and live /etc/systemd/system/. It never mentioned ~/.config/systemd/user/, which holds the
# nine --user units the Buzz fleet runs on — including buzz-agent@.service, the fleet's core
# unit. Brief 2 added that fourth tree and adopted those units; it did not adopt the files
# those units READ, so the unit became sourced and its entire configuration did not. The
# fifth tree closes that: ~/.config/buzz-team/ holds the five dispatch-rule files, the
# connector deny-list, the seam that delivers it, the unit's real ExecStart, the MCP bridge,
# the Notion broker and the fleet's own gate — every mechanism S1 (Buzz interactive: DMs,
# channels, forums) runs on. The comparisons that mean something:
#
#   bin/            <-> ~/agent-workforce/bin/      the runtime tree every ExecStart names
#   systemd/        <-> /etc/systemd/system/        DIRECTLY, not via staging
#   systemd/user/   <-> ~/.config/systemd/user/     --user scope, never installed in /etc
#   buzz-team/      <-> ~/.config/buzz-team/        what those --user units read at startup
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
# misclassifies systemd/ttm-pool-drain.service, which is ours and has neither. The buzz-team
# tree fails closed the same way and from its own declaration: buzz-team/MANIFEST.toml names
# every adopted file and every excluded one, an undeclared file in EITHER tree is red, and a
# missing MANIFEST.toml is a refusal to run rather than an empty exclusion set.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"

# Every tree is overridable so the suite can build synthetic ones. A test that pointed at the
# live box would be red for reasons unrelated to the code under test, and everyone would learn
# to ignore it.
RUNTIME_ROOT="${AGENT_WORKFORCE_RUNTIME:-$HOME/agent-workforce}"
SRC_BIN="${DRIFT_SRC_BIN:-$REPO/bin}"
# bin/deploy:17 reads AGENT_WORKFORCE_RUNTIME for its destination. Hardcoding $HOME here
# made a redirected deploy compare against a tree it never wrote and fail its own
# post-condition on every file.
RUNTIME_BIN="${DRIFT_RUNTIME_BIN:-$RUNTIME_ROOT/bin}"
SRC_SYSTEM="${DRIFT_SRC_SYSTEM:-$REPO/systemd}"
ETC="${DRIFT_ETC:-/etc/systemd/system}"
SRC_USER="${DRIFT_SRC_USER:-$REPO/systemd/user}"
USER_TREE="${DRIFT_USER:-$HOME/.config/systemd/user}"
OWNERSHIP="${DRIFT_OWNERSHIP:-$REPO/design/unit-ownership.toml}"
MANIFESTS="${DRIFT_MANIFESTS:-$REPO/design/agents}"
SRC_BUZZ="${DRIFT_SRC_BUZZ:-$REPO/buzz-team}"
BUZZ_TREE="${DRIFT_BUZZ:-$HOME/.config/buzz-team}"
# THIS SCRIPT CANNOT RUN FROM THE DEPLOYED COPY OF ITSELF, and the failure is silent, so it
# is a guard rather than a note. REPO is resolved from $0, so a copy exec'd out of the
# runtime tree sets SRC_BIN to that same tree and compares it with itself — the bin half
# becomes a tautology that reports zero findings whatever the repo contains, and SRC_SYSTEM
# becomes the staging copy this file's own header forbids as a comparison side. That was the
# shipped state of agent-drift-check.service until it was pointed at the source tree.
same_dir() {
  local a b
  a=$(cd "$1" 2>/dev/null && pwd -P) || return 1
  b=$(cd "$2" 2>/dev/null && pwd -P) || return 1
  [ -n "$a" ] && [ "$a" = "$b" ]
}
if same_dir "$SRC_BIN" "$RUNTIME_BIN"; then
  echo "$(basename "$0"): refusing to run — source and runtime resolve to the same tree" >&2
  echo "  ($SRC_BIN). Run it from the source repo, not from $RUNTIME_ROOT." >&2
  exit 2
fi
if same_dir "$SRC_SYSTEM" "$RUNTIME_ROOT/systemd"; then
  echo "$(basename "$0"): refusing to run — the unit source is the STAGING copy" >&2
  echo "  ($SRC_SYSTEM). systemd reads $ETC and never staging, so this comparison" >&2
  echo "  goes green the moment a unit is deployed while /etc stays stale." >&2
  exit 2
fi
if same_dir "$SRC_BUZZ" "$BUZZ_TREE"; then
  echo "$(basename "$0"): refusing to run — the buzz-team source and the live tree" >&2
  echo "  resolve to the same directory ($SRC_BUZZ). Same tautology as the bin half:" >&2
  echo "  a tree compared with itself reports zero findings whatever either contains." >&2
  exit 2
fi

# Scope. bin/deploy owns exactly one of the four trees, so gating its exit status on the
# other three makes a converged deploy return 1 for /etc state only a human with sudo can
# change. `--scope bin` is what a caller passes when its exit code should mean what it can
# actually control.
SCOPE=all
case "${1:-}" in
  --scope) SCOPE="${2:-all}"; shift 2 ;;
  "") ;;
  *) echo "usage: $(basename "$0") [--scope all|bin]" >&2; exit 2 ;;
esac
case "$SCOPE" in all|bin) ;; *) echo "$(basename "$0"): unknown scope: $SCOPE" >&2; exit 2 ;; esac

# Fixture clock. A dated exclusion asserted against `date` is correct only until the date
# passes, at which point the assertion changes meaning with nobody touching it.
NOW="${DRIFT_NOW:-$(date '+%Y-%m-%d %H:%M:%S')}"

findings=0

report() { echo "  DRIFT [$1] $2"; findings=$((findings + 1)); }
info()   { echo "  info: $*"; }

# OFF THE BOX THERE IS NOTHING DEPLOYED TO COMPARE AGAINST, and reporting all 55 units as
# missing would make a hosted runner red for reasons unrelated to the diff — which is how a
# PR gate gets muted. Skip whole, OUT LOUD, in the format tests/box_precondition.sh prints
# and .github/workflows/verify.yml diffs against tests/ci-expected-skips.txt.
#
# The predicate is ALL THREE trees absent, not any one. On this box a deleted runtime tree
# is itself drift and must stay red, and ~/.config/systemd/user and ~/.config/buzz-team
# survive that — so only a checkout with none of them can reach the skip. /etc is not part
# of the predicate: a hosted runner has an /etc/systemd/system full of its own units, so its
# presence proves nothing.
#
# The buzz-team tree JOINS this predicate rather than getting a skip of its own. A second
# skip would be a second thing tests/ci-expected-skips.txt has to know about and a second
# place the gate can shrink; adding a conjunct only makes the existing skip harder to reach,
# which is the safe direction. The printed line gains a third path, so ci-expected-skips.txt
# is updated in the same commit — a skip line that changes silently is what that file exists
# to prevent.
if [ ! -d "$RUNTIME_BIN" ] && [ ! -d "$USER_TREE" ] && [ ! -d "$BUZZ_TREE" ]; then
  printf 'SKIP: %s — %s (absent: %s %s %s)\n' "$(basename "$0")" \
    'the deployed trees this check compares against' \
    "${RUNTIME_BIN/#$HOME/\~}" "${USER_TREE/#$HOME/\~}" "${BUZZ_TREE/#$HOME/\~}"
  exit 0
fi

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
# Absent declarations are a REFUSAL, not an empty exclusion set. With design/ missing, every
# /etc-only unit reports as undeclared drift — measured 2026-09-02 at 11 findings including
# ollama.service and both live campaigns, on a box with no drift at all. A daily alert that
# is wrong every day is worse than no check, and the failure is invisible from the output.
#
# buzz-team/MANIFEST.toml is in the same list and for the same reason, one tree over: with
# it missing, every one of the box's declared-excluded files (TEAM.md, heartbeat.prompt,
# aurelian-calibration.md) reads as undeclared box-only drift, and every adopted file reads
# as an undeclared source-only one. That is a check that is wrong every day about a tree
# with nothing wrong in it.
BUZZ_MANIFEST="${DRIFT_BUZZ_MANIFEST:-$SRC_BUZZ/MANIFEST.toml}"
if [ "$SCOPE" = all ]; then
  for d in "$OWNERSHIP:file" "$MANIFESTS:dir" "$BUZZ_MANIFEST:file"; do
    path=${d%:*}; kind=${d##*:}
    if { [ "$kind" = file ] && [ ! -f "$path" ]; } || { [ "$kind" = dir ] && [ ! -d "$path" ]; }; then
      echo "$(basename "$0"): refusing to run — ownership declarations not found at $path" >&2
      echo "  Without them every /etc-only unit reads as undeclared drift. Run from the" >&2
      echo "  source repo (design/ is not in bin/deploy's PATHS and never reaches runtime)." >&2
      exit 2
    fi
  done
fi

declarations=$(OWNERSHIP="$OWNERSHIP" MANIFESTS="$MANIFESTS" python3 <<'PY'
import os, pathlib, tomllib
own = pathlib.Path(os.environ["OWNERSHIP"])
if own.is_file():
    for row in tomllib.loads(own.read_text()).get("third_party", []):
        print("third_party", row.get("tree", "etc"), row.get("unit", ""))
manifests = pathlib.Path(os.environ["MANIFESTS"])
if manifests.is_dir():
    for m in sorted(manifests.glob("*.toml")):
        for w in tomllib.loads(m.read_text()).get("workflows", []):
            if w.get("status") == "campaign" and w.get("expires"):
                print("campaign", w.get("unit", ""), w["expires"])
PY
)

# The buzz-team declaration, read separately because its shape is different: two lists, not
# one keyed table. Emits `adopted <name>` and `excluded <pattern>`. Read only under
# SCOPE=all — the refusal above is what guarantees the file exists by the time we get here.
buzz_declarations=''
if [ "$SCOPE" = all ]; then
  buzz_declarations=$(BUZZ_MANIFEST="$BUZZ_MANIFEST" python3 <<'PY'
import os, pathlib, tomllib
data = tomllib.loads(pathlib.Path(os.environ["BUZZ_MANIFEST"]).read_text())
for row in data.get("adopted", []):
    if row.get("path"):
        print("adopted", row["path"])
for row in data.get("excluded", []):
    if row.get("path"):
        print("excluded", row["path"])
PY
  )
fi

# Field comparison for the same reason as declared_third_party below: a filename is data.
# `excluded` entries are matched as GLOBS (buzz-team/MANIFEST.toml declares `*.env` as a
# standing refusal rather than a record of a file that once existed), so the case pattern is
# deliberately unquoted on the right — and every other entry is a literal, which a glob
# match treats as itself.
buzz_declared() { # kind, name
  local want=$1 name=$2 kind pat
  while read -r kind pat; do
    [ "$kind" = "$want" ] || continue
    if [ "$want" = excluded ]; then
      # shellcheck disable=SC2254  # glob match is the point; see the comment above
      case "$name" in $pat) return 0 ;; esac
    else
      [ "$pat" = "$name" ] && return 0
    fi
  done <<<"$buzz_declarations"
  return 1
}

# Field comparison, never `grep "^third_party $1"`: a unit name is data, and `.` in a basic
# regex matches any character — dbus-orgXfreedesktop.resolve1.service would match the
# declared dbus-org.freedesktop.resolve1.service and be silenced. Fail-open in a checker
# whose contract is that ownership fails closed.
declared_third_party() { # unit, tree (default etc)
  local want_tree=${2:-etc} kind tree unit
  while read -r kind tree unit; do
    [ "$kind" = third_party ] || continue
    [ "$tree" = "$want_tree" ] && [ "$unit" = "$1" ] && return 0
  done <<<"$declarations"
  return 1
}

# A dated exclusion is consulted only when it is actually silencing a membership difference.
# Its date must then be in the future: an expired entry still doing work is how a list teaches
# everyone to ignore a red. Entries for units with no drift are not checked, because a unit
# present in both trees needs no exclusion at all.
campaign_expiry() { # unit file -> expires, or empty
  local stem=${1%.*} family kind unit rest
  # A templated family is declared ONCE — trajan.toml carries `unit = "praetorium-phaseb-brief@"`
  # for all six instances, deliberately. Keying only on the instance stem
  # (praetorium-phaseb-brief@2) matches nothing, so the exclusion could never fire for the
  # only campaign family in the repo. test_workflow_coverage.py:221 normalises the same
  # registry the same way; two consumers disagreeing on the join key is the defect this
  # checker exists to catch, one level up.
  family=${stem%%@*}
  [ "$family" != "$stem" ] && family="${family}@"
  while read -r kind unit rest; do
    [ "$kind" = campaign ] || continue
    if [ "$unit" = "$stem" ] || [ "$unit" = "$family" ]; then printf '%s\n' "$rest"; return 0; fi
  done <<<"$declarations"
  return 1
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

if [ "$SCOPE" = bin ]; then
  info "scope=bin — the three unit trees are NOT compared by this invocation"
  if [ "$findings" -eq 0 ]; then echo "drift: clean (bin only)"; else echo "drift: $findings finding(s) (bin only)"; fi
  exit $(( findings > 0 ))
fi

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
  # -path '*.d/*.conf' and not just -name: the unit comparison above uses -maxdepth 1 to
  # keep systemd/user/ and systemd/archive/ out, and this scan must exclude them the same
  # way or a systemd/user/<x>.conf becomes `source-only: user/<x>.conf` — a finding no
  # [[third_party]] entry can silence, because ${f%%.d/*} on a path with no `.d/` returns
  # the whole string and matches no declared unit name.
  find "$root" -mindepth 2 -maxdepth 2 -type f -path '*.d/*.conf' -printf '%P\n' 2>/dev/null \
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
  [ -n "$f" ] || continue
  # Same escape hatch as /etc, scoped by the declaration's own `tree`. Without it a --user
  # unit that is genuinely not ours (a distro or app-installed override) is red forever and
  # the only way to clear it is committing someone else's unit into this repo.
  if declared_third_party "$f" user; then
    info "live-only: $f — declared third-party, not ours"
    continue
  fi
  expires=$(campaign_expiry "$f")
  if [ -n "$expires" ]; then
    if [[ "$NOW" > "$expires" ]]; then
      report user "live-only: $f — its campaign exclusion EXPIRED at $expires"
    else
      info "live-only: $f — campaign, excluded until $expires"
    fi
    continue
  fi
  report user "live-only: $f runs on this box with no source here"
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

# --- buzz-team/ <-> ~/.config/buzz-team ------------------------------------------------
# The fifth tree: what the --user units above actually READ. Brief 2 gave the units a source
# and left their entire configuration unsourced, so every design/ reference to this tree was
# a `governed_by` pointer out of the repo.
#
# maxdepth 1 and -type f, so backups/ is never listed — it is declared excluded anyway,
# because an absence cannot be told from a deletion and a converge naming it would then be a
# bug in the tool rather than an undeclared file.
#
# MANIFEST.toml is filtered from the SOURCE side only, and the asymmetry is deliberate: it is
# this repo's declaration ABOUT the tree, not configuration any process on the box reads, so
# bin/deploy_buzz_team.sh never writes it. Filtering it from the box side too would make a
# hand-copied one invisible; leaving it unfiltered there reports it as box-only, which is
# exactly what it would be.
echo "buzz-team: $SRC_BUZZ <-> $BUZZ_TREE"
buzz_src=$(names "$SRC_BUZZ" ! -name 'MANIFEST.toml')
buzz_live=$(names "$BUZZ_TREE")
if [ -z "$buzz_src" ]; then
  report buzz "source tree $SRC_BUZZ matched no files — a clean result here would mean nothing"
fi

# Source-only is one of two different bugs and they need different fixes, so they are two
# reports. A file in the repo that is not on the box means the box is not running what the
# repo says — run bin/deploy_buzz_team.sh, then restart the units.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! buzz_declared adopted "$f"; then
    report buzz "source-only: $f is in $SRC_BUZZ and declared in no MANIFEST.toml [[adopted]] entry"
    continue
  fi
  report buzz "source-only: $f is not on the box — bin/deploy_buzz_team.sh has not run"
done < <(comm -23 <(echo "$buzz_src") <(echo "$buzz_live"))

# Box-only is the other direction: a rebuild from source loses it. Declared exclusions are
# named rather than silently skipped, for the same reason the third-party units are.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if buzz_declared excluded "$f"; then
    info "box-only: $f — declared excluded (prose or runtime state), not adopted"
    continue
  fi
  report buzz "box-only: $f runs on this box with no source here — a rebuild from source loses it"
done < <(comm -13 <(echo "$buzz_src") <(echo "$buzz_live"))

# Present in BOTH trees. The two loops above ask "is this declared?" only about files that
# are missing from one side, so a file hand-copied into both used to fall straight through to
# `cmp`, match, and pass — undeclared, ungoverned by the converge, and reported by nothing.
# The header's "an undeclared file in EITHER tree is red" was true of each direction
# separately and of neither together until 2026-09-03. This is the likeliest shape of the
# bug it describes, because the way an undeclared file gets here is somebody copying it.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if ! buzz_declared adopted "$f"; then
    if buzz_declared excluded "$f"; then
      report buzz "in both trees: $f is declared EXCLUDED, which asserts the box holds it and this repo does not — and this repo does"
    else
      report buzz "in both trees: $f is declared in no MANIFEST.toml entry — bin/deploy_buzz_team.sh neither writes it nor knows it exists"
    fi
    continue
  fi
  cmp -s "$SRC_BUZZ/$f" "$BUZZ_TREE/$f" || report buzz "content differs: $f"
done < <(comm -12 <(echo "$buzz_src") <(echo "$buzz_live"))

# The staging copy, named so the next reader does not add it as a comparison side.
info "staging $RUNTIME_ROOT/systemd/ is inert — systemd reads $ETC, never it"

if [ "$findings" -eq 0 ]; then
  echo "drift: clean"
else
  echo "drift: $findings finding(s)"
fi
exit $(( findings > 0 ))
