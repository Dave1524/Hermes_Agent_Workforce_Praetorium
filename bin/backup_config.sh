#!/usr/bin/env bash
# NUC-19: back up everything needed to rebuild Praetorium EXCEPT secrets
# (secrets are re-issued at providers, never restored from backup — see
# ~/.config/agent-workforce/README.md).
set -euo pipefail

DEST="${1:-$HOME/agent-workforce/backups}"
mkdir -p "$DEST"
STAMP=$(date +%Y%m%d_%H%M)
OUT="$DEST/praetorium_config_$STAMP.tar.gz"

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
  -C / etc/systemd/system/qmd-mcp.service \
     etc/systemd/system/qmd-refresh.service \
     etc/systemd/system/qmd-refresh.timer \
     etc/systemd/system/agent-proposal.service \
     etc/systemd/system/agent-proposal.timer

echo "backup written: $OUT ($(du -h "$OUT" | cut -f1))"
echo "contains NO secrets (by design). Copy off-box from the Mac with:"
echo "  scp praetorium:$OUT ~/backups/"
