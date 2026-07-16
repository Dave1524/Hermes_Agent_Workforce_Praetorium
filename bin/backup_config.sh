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
units=()
for u in "$REPO_ROOT"/systemd/*.service "$REPO_ROOT"/systemd/*.timer; do
  [ -e "$u" ] || continue
  b="$(basename "$u")"
  [ -e "/etc/systemd/system/$b" ] && units+=("etc/systemd/system/$b")
done

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
  -C / "${units[@]}"

echo "backup written: $OUT ($(du -h "$OUT" | cut -f1))"
echo "  systemd units captured: ${#units[@]}"
echo "contains NO secrets (by design). Copy off-box from the Mac with:"
echo "  scp praetorium:$OUT ~/backups/"
