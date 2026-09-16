#!/usr/bin/env bash
# The only rebuild path for the Control Room SPA (T5.3e): ui/control-room → the committed
# bin/control_room_ui/app/. Run it, commit what it prints, then bin/deploy and
# `sudo systemctl restart control-room` as usual.
#
# Order is typecheck, tests, build, stamp: a build from red tests is never written. The
# stamp (BUILD.json) is bin/control_room_ui_stamp.sh over the source tree, which is what
# tests/test_control_room_spa.sh recomputes — so a source edit without a rebuild is red on
# the box and in CI, without Node on the box. Output names are fixed by vite.config.ts, so
# a rebuild never changes the membership of bin/ and never forces bin/deploy --prune.
#
#   --ci    run `npm ci` even when node_modules exists (a lockfile change, a doubt)
set -euo pipefail

repo=$(cd "$(dirname "$0")/.." && pwd)
ui="$repo/ui/control-room"
out="$repo/bin/control_room_ui/app"
NODE_MIN=22

force_ci=0
for arg in "$@"; do
  case "$arg" in
    --ci) force_ci=1 ;;
    *) echo "usage: $0 [--ci]" >&2; exit 2 ;;
  esac
done

command -v node >/dev/null || { echo "control_room_build_ui: node is not on PATH (need >= $NODE_MIN)" >&2; exit 1; }
node_major=$(node --version | sed -E 's/^v([0-9]+).*/\1/')
[ "$node_major" -ge "$NODE_MIN" ] || { echo "control_room_build_ui: node $(node --version) is older than $NODE_MIN" >&2; exit 1; }

cd "$ui"
if [ "$force_ci" = 1 ] || [ ! -d node_modules ]; then
  npm ci
fi
npm run typecheck
npm test
npm run build

stamp=$("$repo/bin/control_room_ui_stamp.sh" "$repo")
printf '{"schema":1,"source_sha256":"%s"}\n' "$stamp" > "$out/BUILD.json"

echo "control_room_build_ui: stamp $stamp"
echo "control_room_build_ui: changed under bin/control_room_ui/app/:"
git -C "$repo" status --short -- bin/control_room_ui/app | sed 's/^/  /'
[ -n "$(git -C "$repo" status --short -- bin/control_room_ui/app)" ] || echo "  (nothing — the committed build already matches)"
