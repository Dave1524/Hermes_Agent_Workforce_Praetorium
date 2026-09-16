#!/usr/bin/env bash
# The Control Room SPA build (T5.3e): the committed bin/control_room_ui/app/ is the build of
# the committed ui/control-room, and nothing else.
#
# TWO HALVES, because the box has no Node and CI has no box. The stamp half runs everywhere:
# BUILD.json carries a sha256 over the source tree (bin/control_room_ui_stamp.sh), so a source
# edit that was not rebuilt is red without a toolchain, and index.html is checked for the
# hygiene the CSP relies on — only /app/assets/ references, no inline script or style, no http.
# The Node half — typecheck, vitest, and a rebuild into a temp outDir that must be
# byte-identical to the committed output — runs where node >= 22 and node_modules exist, and
# prints one SKIP: line otherwise. CI installs both before the gate, so CI runs the whole
# suite and tests/ci-expected-skips.txt carries no line for it; on the box it skips out loud.
#
# The stamp half is the one that proves the check can fail: a copy of the source tree with
# one byte changed must stamp differently. A hash check that cannot go red certifies nothing.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UI="$REPO_ROOT/ui/control-room"
APP="$REPO_ROOT/bin/control_room_ui/app"
STAMP="$REPO_ROOT/bin/control_room_ui_stamp.sh"
NODE_MIN=22

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

echo "--- canary ---"
assert "the pipefail canary passes" 'yes | grep -q y'

echo "--- stamp (::control-room-spa-build) ---"
assert "BUILD.json exists" '[ -f "$APP/BUILD.json" ]'
assert "BUILD.json is schema 1 with a 64-hex source_sha256" \
  '[ -f "$APP/BUILD.json" ] && python3 -c "import json,re,sys; d=json.load(open(sys.argv[1])); sys.exit(0 if d.get(\"schema\")==1 and re.fullmatch(r\"[0-9a-f]{64}\", str(d.get(\"source_sha256\"))) else 1)" "$APP/BUILD.json"'
recorded=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("source_sha256",""))' "$APP/BUILD.json" 2>/dev/null)
live=$("$STAMP" "$REPO_ROOT")
assert "the committed build was built from the committed source (stamp $live)" '[ -n "$live" ] && [ "$recorded" = "$live" ]'

# A hash check has to be shown going red. Copy the checkout's ui tree into a scratch repo,
# change one byte, and the stamp must differ — the checkout itself is never touched.
copy="$tmp/copy"
mkdir -p "$copy"
git -C "$REPO_ROOT" ls-files -z --cached --others --exclude-standard ui/control-room \
  | (cd "$REPO_ROOT" && xargs -0 -I{} cp --parents {} "$copy/")
git -C "$copy" init -q && git -C "$copy" add -A
copied=$("$STAMP" "$copy")
assert "a byte-identical copy stamps the same" '[ "$copied" = "$live" ]'
printf '\n// edited\n' >> "$copy/ui/control-room/src/main.tsx"
edited=$("$STAMP" "$copy")
assert "one edited source byte flips the stamp" '[ "$edited" != "$live" ]'

echo "--- index.html hygiene ---"
index="$APP/index.html"
assert "index.html exists" '[ -f "$index" ]'
assert "every src/href points under /app/assets/" \
  '! grep -oE "(src|href)=\"[^\"]*\"" "$index" | grep -vE "=\"/app/assets/[A-Za-z0-9._-]+\"" >/dev/null'
assert "no inline <script>" '! grep -E "<script[^>]*>[^<]" "$index" >/dev/null && ! grep -E "<script>" "$index" >/dev/null'
assert "no inline <style>" '! grep -E "<style" "$index" >/dev/null'
assert "no http(s) reference" '! grep -E "https?://" "$index" >/dev/null'
assert "the entry script and stylesheet are the fixed names" \
  'grep -F "/app/assets/app.js" "$index" >/dev/null && grep -F "/app/assets/app.css" "$index" >/dev/null'
assert "only css, js and woff2 under assets/" \
  '! find "$APP/assets" -type f ! -name "*.css" ! -name "*.js" ! -name "*.woff2" | grep . >/dev/null'
assert "assets/ is flat" '! find "$APP/assets" -mindepth 1 -type d | grep . >/dev/null'

echo "--- toolchain half ---"
node_ok=0
if command -v node >/dev/null; then
  major=$(node --version | sed -E 's/^v([0-9]+).*/\1/')
  [ "$major" -ge "$NODE_MIN" ] && node_ok=1
fi
if [ "$node_ok" = 1 ] && [ -d "$UI/node_modules" ]; then
  assert "npm run typecheck" '(cd "$UI" && npm run --silent typecheck >"$tmp/typecheck.log" 2>&1) || { cat "$tmp/typecheck.log"; false; }'
  assert "npm test" '(cd "$UI" && npm test --silent >"$tmp/test.log" 2>&1) || { tail -n 40 "$tmp/test.log"; false; }'
  assert "a rebuild is byte-identical to the committed build" \
    '(cd "$UI" && VITE_OUT_DIR="$tmp/out" npm run --silent build >"$tmp/build.log" 2>&1) && { [ ! -f "$APP/BUILD.json" ] || cp "$APP/BUILD.json" "$tmp/out/BUILD.json"; } && diff -r "$tmp/out" "$APP" >"$tmp/diff.log" 2>&1 || { tail -n 40 "$tmp/build.log" "$tmp/diff.log"; false; }'
else
  absent="ui/control-room/node_modules"
  [ "$node_ok" = 1 ] || absent="node>=$NODE_MIN $absent"
  echo "SKIP: test_control_room_spa.sh — the SPA toolchain (absent: $absent)"
  [ "$fail" = 0 ] && exit 77
fi

exit "$fail"
