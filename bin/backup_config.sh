#!/usr/bin/env bash
# NUC-19: back up everything needed to rebuild Praetorium EXCEPT secrets
# (secrets are re-issued at providers, never restored from backup — see
# ~/.config/agent-workforce/README.md).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
DEST="${1:-$HOME/agent-workforce/backups}"
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d_%H%M)
OUT="$DEST/praetorium_config_$STAMP.tar.gz"

# Back up EVERY deployed unit family — not a hand-picked five. Derive the unit
# names from this repo's systemd/ source of truth and include each one that is
# actually installed under /etc/systemd/system (skips any not yet deployed).
#
# TWO TREES, because enumerating only this one made the adoption in D8 cosmetic: a unit
# with no source here is not backed up AT ALL, and a --user unit is never under /etc, so
# it could never match no matter how long the loop ran. That is the chain that put the
# whole Buzz fleet outside every tarball — no source => not enumerated => not in the
# backup => the rebuild checklist restores /etc from the tarball and the unit is simply
# gone, with nothing anywhere reporting its absence.
units=()
for u in "$REPO_ROOT"/systemd/*.service "$REPO_ROOT"/systemd/*.timer; do
  [ -e "$u" ] || continue
  b="$(basename "$u")"
  [ -e "/etc/systemd/system/$b" ] && units+=("etc/systemd/system/$b")
done

# --user scope. Same rule — sourced here AND installed there — but a different pair of
# trees, and the tar entry is $HOME-relative rather than /-relative.
user_units=()
for u in "$REPO_ROOT"/systemd/user/*.service "$REPO_ROOT"/systemd/user/*.timer; do
  [ -e "$u" ] || continue
  b="$(basename "$u")"
  [ -e "$HOME/.config/systemd/user/$b" ] && user_units+=(".config/systemd/user/$b")
done

# The drop-in *.conf files under ~/.config/systemd/user are DELIBERATELY not captured.
# Three of them carry BUZZ_AUTH_TAG (design/unit-ownership.toml [[never_commit]]) and this
# tarball is the no-secrets one — the inventory at docs/runbook.md already distinguishes
# assets that are never backed up, and credentials are that class. Restoring them is
# re-issuing them, exactly as ~/.config/agent-workforce/README.md says for every secret.

tar czf "$OUT" \
  --exclude="agent-workforce/backups" \
  --exclude="agent-workforce/logs" \
  --exclude=".config/agent-workforce/secrets.env" \
  --exclude=".config/agent-workforce/keys" \
  -C "$HOME" \
  agent-workforce \
  .config/agent-workforce/.env.example \
  .config/agent-workforce/README.md \
  .config/qmd/index.yml \
  "${user_units[@]}" \
  -C / "${units[@]}"

echo "backup written: $OUT ($(du -h "$OUT" | cut -f1))"
echo "  systemd units captured: ${#units[@]} system, ${#user_units[@]} user"
echo "contains NO secrets (by design). Copy off-box from the Mac with:"
echo "  scp praetorium:$OUT ~/backups/"
