#!/usr/bin/env bash
# deploy_buzz_team.sh — converge buzz-team/ into ~/.config/buzz-team/.
#
# Source   ~/dev/agent-workforce/buzz-team   (git, this repo)
# Dest     ~/.config/buzz-team               (what buzz-agent@*.service actually reads)
#
# WHY THIS IS NOT bin/deploy. That script has ONE $DEST, guarded by three refusals that are
# all about the agent-workforce runtime tree: bin/agent_propose.sh must be present, .git must
# be absent, the directory must exist (bin/deploy:36-48). A config directory satisfies none
# of them, and loosening those guards to admit a second destination weakens the guard that
# protects the first. So this carries its own destination guard instead — it refuses unless
# the target already holds the five dispatch-rule files, which is the one shape only the live
# buzz-team tree has.
#
# IT DOES NOT RESTART ANYTHING, AND IT SAYS SO ON EXIT. buzz-acp loads --config rules at
# STARTUP and filter compilation is EAGER, so two things are true at once: a converge is
# inert until a restart, and a bad converge is a five-agent crash loop rather than a quiet
# dispatch failure. That is the machine CLAUDE.md's first debugging trap ("a config edit is
# inert until the process reloads it") applied to the one tree where it costs the whole
# fleet. This prints the restart command; a human runs it, and then re-runs
# ~/.config/buzz-team/verify-fleet.sh, whose gate 7 already checks config freshness against
# ExecMainStartTimestamp. Do not add a systemctl call here.
#
# ADDITIVE, NEVER DESTRUCTIVE. It writes the files buzz-team/MANIFEST.toml declares
# [[adopted]] and touches nothing else — not the declared exclusions (TEAM.md,
# heartbeat.prompt, aurelian-calibration.md), not backups/, not a credential. There is no
# --prune: deleting a box-side file is what the drift check reports and a human decides.
set -uo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
SRC="${BUZZ_TEAM_SRC:-$REPO/buzz-team}"
DEST="${BUZZ_TEAM_DEST:-$HOME/.config/buzz-team}"
MANIFEST="$SRC/MANIFEST.toml"

# The five rule files are the destination guard. Every other file in the tree exists
# somewhere else on this box under some name; this set does not.
GUARD_FILES=(marcus.toml claudius.toml augustus.toml trajan.toml aurelian.toml)

DRY_RUN=0
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "deploy_buzz_team: unknown argument '$arg'" >&2; exit 2 ;;
  esac
done

die() { echo "deploy_buzz_team: $*" >&2; exit 1; }

[ -d "$SRC" ]      || die "source tree '$SRC' does not exist. Refusing."
[ -f "$MANIFEST" ] || die "no MANIFEST.toml at '$MANIFEST' — the adopted set is undeclared. Refusing."

# Destination guard. Same shape as bin/deploy's, keyed on this tree's own contents rather
# than on the runtime tree's.
[ -d "$DEST" ] || die "destination '$DEST' does not exist. This script converges an EXISTING live tree; it does not create one. Refusing."
for g in "${GUARD_FILES[@]}"; do
  [ -f "$DEST/$g" ] || die "'$DEST' does not look like the live buzz-team tree (expected $g). Refusing."
done
if [ -d "$DEST/.git" ] || [ -f "$DEST/.git" ]; then
  die "'$DEST' is a git tree — that is a source, not the live config. Refusing."
fi
if [ "$(cd "$SRC" && pwd -P)" = "$(cd "$DEST" && pwd -P)" ]; then
  die "source and destination resolve to the same directory. Refusing."
fi

# The adopted set comes from the manifest, never from a glob of the source tree. A glob would
# ship whatever happened to be sitting there — including a file someone dropped in to test
# with — and the whole point of the declaration is that what converges is a declared list.
adopted=$(MANIFEST="$MANIFEST" python3 <<'PY'
import os, pathlib, tomllib
data = tomllib.loads(pathlib.Path(os.environ["MANIFEST"]).read_text())
for row in data.get("adopted", []):
    if row.get("path"):
        print(row["path"])
PY
) || die "MANIFEST.toml does not parse. Refusing."

[ -n "$adopted" ] || die "MANIFEST.toml declares no [[adopted]] files — a converge that would write nothing is a broken declaration, not a no-op. Refusing."

# Every declared path must be a PLAIN FILENAME. `path` is a manifest string that reaches
# `cp -p "$SRC/$f" "$DEST/$f"` unvalidated, so a value carrying a directory component writes
# outside the tree the destination guard above just proved — `../.ssh/authorized_keys` is one
# `cp` away, and it is not hypothetical the way a traversal usually is, because this script's
# whole job is to write files a declaration named. It is also invisible afterwards:
# bin/check_deploy_drift.sh enumerates with `find -maxdepth 1 -type f -printf '%f\n'`, so a
# written-through path is absent from BOTH membership directions and the drift check reports
# a clean tree. Validated as a set, before anything is written, so a bad manifest refuses
# rather than half-converging.
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in
    */*|.|..)
      die "MANIFEST.toml declares path '$f', which is not a plain filename. A path component escapes '$DEST' and is invisible to bin/check_deploy_drift.sh. Fix the manifest. Refusing." ;;
  esac
done <<<"$adopted"

echo "deploy_buzz_team: $SRC -> $DEST"
echo "deploy_buzz_team: source at $(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
[ "$DRY_RUN" -eq 1 ] && echo "deploy_buzz_team: DRY RUN — no changes written"

changed=0
missing=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  if [ ! -f "$SRC/$f" ]; then
    echo "  MISSING  $f — declared [[adopted]] and not in $SRC"
    missing=$((missing + 1))
    continue
  fi
  if cmp -s "$SRC/$f" "$DEST/$f"; then
    continue
  fi
  if [ -e "$DEST/$f" ]; then verb=update; else verb=create; fi
  echo "  $verb   $f"
  changed=$((changed + 1))
  [ "$DRY_RUN" -eq 1 ] && continue
  # -p preserves the mode: three of these are executables the unit execs directly, and a
  # copy that lands 644 makes buzz-agent@.service fail with a permission error that looks
  # nothing like a config problem.
  cp -p "$SRC/$f" "$DEST/$f" || die "failed to write $DEST/$f"
done <<<"$adopted"

if [ "$missing" -gt 0 ]; then
  echo "deploy_buzz_team: $missing declared file(s) absent from source — REFUSING to report a converge." >&2
  exit 1
fi

if [ "$changed" -eq 0 ]; then
  echo "deploy_buzz_team: live tree already current. Nothing to do."
  exit 0
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "deploy_buzz_team: $changed file(s) WOULD change. Re-run without --dry-run to write them."
  exit 0
fi

echo "deploy_buzz_team: $changed file(s) written."
cat <<'EOF'

deploy_buzz_team: NOTHING WAS RESTARTED, and the fleet is still running the old config.
  buzz-acp reads --config rules at startup and compiles every filter eagerly, so this
  converge is inert until a restart — and a malformed rule crash-loops the unit rather
  than failing quietly at dispatch. Five live agents. Run it yourself, one at a time:

    systemctl --user restart buzz-agent@marcus
    systemctl --user status  buzz-agent@marcus     # confirm it stayed up before the next

  Then re-run the fleet gate, whose gate 7 checks the config each process ACTUALLY loaded
  against its ExecMainStartTimestamp:

    ~/.config/buzz-team/verify-fleet.sh
EOF
