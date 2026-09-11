#!/usr/bin/env bash
# Model-free smoke test for bin/content_change_dispatch.sh (NUC-35). No network, no LLM.
# Stubs notion_rest.py (canned Picked JSON / forced failure) and agent_propose.sh
# (records that it was called + the AGENT_JOB_OVERRIDES it saw). Proves:
#   (a) empty diff  => agent_propose stub NOT called, state refreshed
#   (b) new Picked  => stub called exactly once, AGENT_JOB_OVERRIDES exported, state advanced
#   (c) Notion fail => script exits 0 and the state file is byte-for-byte unchanged
# Run via verify.sh.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/content_change_dispatch.sh"

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

# ── Sandbox: scratch root with stubbed notion_rest.py + agent_propose.sh ──
sandbox() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/bin" "$h/logs" "$h/var"

  # Stub notion_rest.py: STUB_FAIL=1 -> exit 1 (simulate Notion API/network error);
  # otherwise emit the JSON array from STUB_JSON_FILE (canned board --status Picked --json).
  cat > "$h/bin/notion_rest.py" <<'PY'
import os, sys
if os.environ.get("STUB_FAIL") == "1":
    sys.stderr.write("stub notion_rest: forced API failure\n")
    sys.exit(1)
f = os.environ.get("STUB_JSON_FILE", "")
sys.stdout.write(open(f).read() if f and os.path.exists(f) else "[]")
PY

  # Stub agent_propose.sh: record one call + the AGENT_JOB_OVERRIDES it inherited,
  # then leave the same receipt-keyed terminal evidence the real runtime must leave.
  cat > "$h/bin/agent_propose.sh" <<'SH'
#!/usr/bin/env bash
echo "call" >> "$AP_CALLS_FILE"
printf '%s\n' "${AGENT_JOB_OVERRIDES:-UNSET}" >> "$AP_OVERRIDES_FILE"
printf '%s\n' "${CONTENT_ENTRY_POINT:-UNSET}" >> "$AP_ENTRY_POINT_FILE"
printf 'ts=%s schema=3 profile=augustus model=openai/gpt-5.5 task=augustus-content outcome=%s proposal=none\n' \
  "$(date -Is)" "${AP_OUTCOME:-OPS}" >> "$AGENT_COST_LOG"
mkdir -p "$(dirname "$CONTENT_BOARD_SNAPSHOT")"
printf 'baseline:Picked\nrun_id=%s\nentry_point=picked-change\n' "$(printf 'a%.0s' {1..64})" > "$CONTENT_BOARD_SNAPSHOT"
case "${AP_TERMINAL:-draft}" in
  draft) printf 'page=%s from=Picked to=Draft\n' "${AP_DRAFT_PAGE:-id-B}" >> "$CONTENT_BOARD_SNAPSHOT" ;;
  decline) printf 'decline_event=%s\n' "$(printf 'e%.0s' {1..64})" >> "$CONTENT_BOARD_SNAPSHOT" ;;
esac
exit "${AP_RC:-0}"
SH
  chmod +x "$h/bin/agent_propose.sh"
  echo "$h"
}

# Run the script under test against a sandbox, with all paths overridden.
run() {
  local h=$1 jsonfile=$2 stubfail=$3 draft_page=${4:-id-B}
  CONTENT_DISPATCH_ROOT="$h" \
  NOTION_REST_BIN="$h/bin/notion_rest.py" \
  AGENT_PROPOSE_BIN="$h/bin/agent_propose.sh" \
  CONTENT_PICKED_STATE="$h/var/content_picked.state" \
  LOG_DIR="$h/logs" \
  AGENT_COST_LOG="$h/logs/cost.log" \
  CONTENT_BOARD_SNAPSHOT="$h/var/content_board.snapshot" \
  AUGUSTUS_CONTENT_ENV="$h/augustus-content.env" \
  STUB_JSON_FILE="$jsonfile" \
  STUB_FAIL="$stubfail" \
  AP_CALLS_FILE="$h/ap_calls" \
  AP_OVERRIDES_FILE="$h/ap_overrides" \
  AP_ENTRY_POINT_FILE="$h/ap_entry_point" \
  AP_DRAFT_PAGE="$draft_page" \
  bash "$SCRIPT" >/dev/null 2>&1
  echo $?
}
state()   { echo "$1/var/content_picked.state"; }
ncalls()  { [ -f "$1/ap_calls" ] && grep -c . "$1/ap_calls" || echo 0; }
mkjson()  { # $1=file, rest=ids -> JSON array of {id,status}
  local f=$1; shift; local out="[" sep="" id
  for id in "$@"; do out="$out$sep{\"id\":\"$id\",\"angle\":\"a\",\"status\":\"Picked\"}"; sep=","; done
  echo "$out]" > "$f"
}

echo '--- scenario (a): empty diff -> agent_propose NOT called, state refreshed ---'
ha=$(sandbox); ja="$ha/board.json"
mkjson "$ja" id-A id-B
printf '%s\n' id-A id-B > "$(state "$ha")"   # state already == current Picked
rc=$(run "$ha" "$ja" "")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'agent_propose NOT called' "[ \"\$(ncalls '$ha')\" -eq 0 ]"
assert 'no cost/agent_run signal (stub never ran)' "[ ! -f '$ha/ap_overrides' ]"
assert 'state still has id-A and id-B' "grep -qx id-A '$(state "$ha")' && grep -qx id-B '$(state "$ha")'"
assert 'log records no-new-Picked' "grep -q 'no new Picked rows' '$ha/logs/content_change_dispatch.log'"

echo '--- scenario (b): new Picked ID -> stub called once, override exported, state advanced ---'
hb=$(sandbox); jb="$hb/board.json"
mkjson "$jb" id-A id-B                        # id-B is new
printf '%s\n' id-A > "$(state "$hb")"         # state only knows id-A
rc=$(run "$hb" "$jb" "")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'agent_propose called exactly once' "[ \"\$(ncalls '$hb')\" -eq 1 ]"
assert 'AGENT_JOB_OVERRIDES pointed at augustus-content.env' "grep -qx '$hb/augustus-content.env' '$hb/ap_overrides'"
assert 'the dispatched run records its picked-change entry point' "grep -qx picked-change '$hb/ap_entry_point'"
assert 'drafted id-B is removed from the eligible Picked state' "! grep -qx id-B '$(state "$hb")'"
assert 'state still includes id-A' "grep -qx id-A '$(state "$hb")'"

echo '--- scenario (b2): first run, no state file -> all Picked new -> dispatch ---'
hb2=$(sandbox); jb2="$hb2/board.json"
mkjson "$jb2" id-X
rc=$(run "$hb2" "$jb2" "" id-X)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'agent_propose called once on first run' "[ \"\$(ncalls '$hb2')\" -eq 1 ]"
assert 'drafted id-X is not retained as eligible' "[ ! -s '$(state "$hb2")' ]"

echo '--- scenario (c): Notion failure -> exit 0, state byte-unchanged, no dispatch ---'
hc=$(sandbox); jc="$hc/board.json"
mkjson "$jc" id-A id-B
printf '%s\n' id-A > "$(state "$hc")"
before=$(md5sum "$(state "$hc")" | awk '{print $1}')
rc=$(run "$hc" "$jc" 1)                        # STUB_FAIL=1
after=$(md5sum "$(state "$hc")" | awk '{print $1}')
assert 'fail-soft exits 0' "[ '$rc' = 0 ]"
assert 'state byte-for-byte unchanged' "[ '$before' = '$after' ]"
assert 'agent_propose NOT called on failure' "[ \"\$(ncalls '$hc')\" -eq 0 ]"
assert 'log records fail-soft' "grep -q 'FAIL-SOFT' '$hc/logs/content_change_dispatch.log'"

echo '--- scenario (d): agent_propose non-zero -> state NOT advanced (rows retry) ---'
hd=$(sandbox); jd="$hd/board.json"
mkjson "$jd" id-A id-B
printf '%s\n' id-A > "$(state "$hd")"
before=$(md5sum "$(state "$hd")" | awk '{print $1}')
CONTENT_DISPATCH_ROOT="$hd" NOTION_REST_BIN="$hd/bin/notion_rest.py" \
  AGENT_PROPOSE_BIN="$hd/bin/agent_propose.sh" CONTENT_PICKED_STATE="$(state "$hd")" \
  LOG_DIR="$hd/logs" AUGUSTUS_CONTENT_ENV="$hd/augustus-content.env" \
  AGENT_COST_LOG="$hd/logs/cost.log" CONTENT_BOARD_SNAPSHOT="$hd/var/content_board.snapshot" \
  STUB_JSON_FILE="$jd" STUB_FAIL="" AP_CALLS_FILE="$hd/ap_calls" \
  AP_OVERRIDES_FILE="$hd/ap_overrides" AP_RC=3 bash "$SCRIPT" >/dev/null 2>&1
rc=$?
after=$(md5sum "$(state "$hd")" | awk '{print $1}')
assert 'exits 0 even when dispatch failed' "[ '$rc' = 0 ]"
assert 'dispatch attempted (stub called)' "[ \"\$(ncalls '$hd')\" -eq 1 ]"
assert 'state NOT advanced after failed dispatch' "[ '$before' = '$after' ]"

exit $fail
