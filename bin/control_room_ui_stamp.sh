#!/usr/bin/env bash
# Prints the source stamp of the Control Room SPA (T5.3e): sha256 over every tracked or
# untracked-but-not-ignored file under ui/control-room, path and bytes, in sorted order.
#
# One owner for writer and reader: bin/control_room_build_ui.sh writes it into
# bin/control_room_ui/app/BUILD.json and tests/test_control_room_spa.sh recomputes it. No
# timestamps and no Node version — the stamp says which SOURCE the committed build came
# from, so the same tree always stamps the same and a build from an edited tree is red
# without needing Node to say so. node_modules and the build output are git-ignored, so
# --others --exclude-standard sees neither.
#
# Usage: control_room_ui_stamp.sh [<repo-root>]   (default: the checkout this script is in)
set -euo pipefail

repo=${1:-$(cd "$(dirname "$0")/.." && pwd)}
cd "$repo"

git ls-files -z --cached --others --exclude-standard ui/control-room \
  | LC_ALL=C sort -z \
  | while IFS= read -r -d '' f; do
      [ -f "$f" ] || continue
      printf '%s\0' "$f"
      cat "$f"
    done \
  | sha256sum \
  | cut -d' ' -f1
