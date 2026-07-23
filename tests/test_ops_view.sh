#!/usr/bin/env bash
# Offline test for bin/ops-view.sh (NUC-41). No network, no secret, no Notion write.
# Stubs praetorium-status.sh, sprint_board_counts.py and ops_page_publish.py so the
# composition + the dry-run/publish gates are proven without touching Notion. Proves:
#   (a) --dry-run composes all sections, embeds fleet health, exits 0, writes nothing
#   (b) no-arg default behaves as --dry-run
#   (c) board-counts failure degrades to an "unavailable" line (still exit 0)
#   (d) --publish REFUSES when OPS_PAGE_ID is unset (exit 3, publisher never called)
#   (e) --publish with OPS_PAGE_ID pipes the composed snapshot into the publisher
# Run via bin/verify.sh.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/ops-view.sh"

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

sandbox() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/bin" "$h/logs"

  cat > "$h/bin/status.sh" <<'SH'
#!/usr/bin/env bash
echo "FLEET-HEALTH-MARKER active=yes"
SH
  chmod +x "$h/bin/status.sh"

  printf 'print("To do=2  In progress=1  Done=5  (total 8)")\n' > "$h/bin/board_ok.py"
  printf 'import sys; sys.exit(1)\n' > "$h/bin/board_fail.py"

  # Publisher stub: record that it ran + capture the piped stdin into a sentinel.
  cat > "$h/bin/publish.py" <<'PY'
import os, sys
open(os.environ["PUBLISH_SENTINEL"], "w").write(sys.stdin.read())
print("stub-published")
PY

  echo "ERROR: boom in nightly job" > "$h/logs/agent.log"
  : > "$h/empty-secrets.env"
  echo "$h"
}

run() {  # $1=home $2=board_bin ...args
  local h=$1 board=$2; shift 2
  PRAETORIUM_STATUS_BIN="$h/bin/status.sh" \
  SPRINT_BOARD_COUNTS_BIN="$h/bin/$board" \
  OPS_PAGE_PUBLISH_BIN="$h/bin/publish.py" \
  AGENT_LOG_DIR="$h/logs" \
  OPS_SECRETS_FILE="$h/empty-secrets.env" \
  PUBLISH_SENTINEL="$h/published" \
  bash "$SCRIPT" "$@"
}

echo '--- (a) --dry-run composes every section, embeds fleet health, writes nothing ---'
ha=$(sandbox); out="$ha/out"
run "$ha" board_ok.py --dry-run > "$out" 2>/dev/null; rc=$?
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'has snapshot title' "grep -q '^# Praetorium — Ops Snapshot' '$out'"
assert 'has Sprint Board section' "grep -q '^## Sprint Board' '$out'"
assert 'shows board counts' "grep -q 'To do=2  In progress=1  Done=5  (total 8)' '$out'"
assert 'has Recent errors section' "grep -q '^## Recent errors' '$out'"
assert 'includes a log error line' "grep -q 'ERROR: boom in nightly job' '$out'"
assert 'embeds fleet health' "grep -q 'FLEET-HEALTH-MARKER' '$out'"
assert 'fleet health is fenced' "grep -q '^\`\`\`' '$out'"
assert 'publisher NOT invoked in dry-run' "[ ! -f '$ha/published' ]"

echo '--- (b) no argument defaults to --dry-run ---'
hb=$(sandbox)
run "$hb" board_ok.py > "$hb/out" 2>/dev/null; rc=$?
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'still renders the snapshot' "grep -q '^# Praetorium — Ops Snapshot' '$hb/out'"
assert 'publisher NOT invoked' "[ ! -f '$hb/published' ]"

echo '--- (c) board-counts failure degrades to unavailable (still exit 0) ---'
hc=$(sandbox)
run "$hc" board_fail.py --dry-run > "$hc/out" 2>/dev/null; rc=$?
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'shows unavailable note' "grep -q 'unavailable — needs NOTION_API_TOKEN' '$hc/out'"

echo '--- (d) --publish REFUSES without OPS_PAGE_ID, never calls publisher ---'
hd=$(sandbox)
env -u OPS_PAGE_ID bash -c "
  PRAETORIUM_STATUS_BIN='$hd/bin/status.sh' \
  SPRINT_BOARD_COUNTS_BIN='$hd/bin/board_ok.py' \
  OPS_PAGE_PUBLISH_BIN='$hd/bin/publish.py' \
  AGENT_LOG_DIR='$hd/logs' OPS_SECRETS_FILE='$hd/empty-secrets.env' \
  PUBLISH_SENTINEL='$hd/published' bash '$SCRIPT' --publish" > "$hd/out" 2>"$hd/err"
rc=$?
assert 'exits 3 (gated)' "[ '$rc' = 3 ]"
assert 'says REFUSED' "grep -q 'REFUSED' '$hd/err'"
assert 'publisher NOT invoked' "[ ! -f '$hd/published' ]"

echo '--- (e) --publish with OPS_PAGE_ID pipes the snapshot into the publisher ---'
he=$(sandbox)
OPS_PAGE_ID="pageXYZ" \
  PRAETORIUM_STATUS_BIN="$he/bin/status.sh" \
  SPRINT_BOARD_COUNTS_BIN="$he/bin/board_ok.py" \
  OPS_PAGE_PUBLISH_BIN="$he/bin/publish.py" \
  AGENT_LOG_DIR="$he/logs" OPS_SECRETS_FILE="$he/empty-secrets.env" \
  PUBLISH_SENTINEL="$he/published" bash "$SCRIPT" --publish > "$he/out" 2>/dev/null
rc=$?
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'publisher WAS invoked' "[ -f '$he/published' ]"
assert 'received the composed snapshot' "grep -q '^# Praetorium — Ops Snapshot' '$he/published'"

exit $fail
