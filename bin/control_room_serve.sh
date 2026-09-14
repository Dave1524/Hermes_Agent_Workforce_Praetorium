#!/usr/bin/env bash
# Praetorium Control Room launcher (T5.3, 2026-09-14). Binds bin/control_room_api.py to the
# box's Tailscale IPv4 address only — never 0.0.0.0, never the LAN — and refuses to start when
# Tailscale is down, because a screen that falls back to a wider bind is a screen that leaks.
# CONTROL_ROOM_DRY_RUN=1 prints the resolved command instead of exec'ing it (the test seam).
set -euo pipefail

addr="$(tailscale ip -4 2>/dev/null | head -n 1 || true)"
case "$addr" in
  100.*|fd7a:*) ;;
  *)
    echo "control_room_serve: no Tailscale address from 'tailscale ip -4' (got '${addr}'); refusing to bind" >&2
    exit 1
    ;;
esac

script_dir="$(cd "$(dirname "$0")" && pwd)"
cmd=(python3 "${script_dir}/control_room_api.py" --host "$addr" --port "${CONTROL_ROOM_PORT:-8787}")

if [ "${CONTROL_ROOM_DRY_RUN:-0}" = "1" ]; then
  printf '%s\n' "${cmd[*]}"
  exit 0
fi
exec "${cmd[@]}"
