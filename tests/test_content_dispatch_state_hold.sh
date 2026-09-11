#!/usr/bin/env bash
# NUC-44 regression: content_change_dispatch.sh must not advance var/content_picked.state
# unless the dispatched run actually reached a terminal success. The rc!=0 guard already
# covers the honest case; this suite pins the DEFENDED case — a runner that reports rc=0
# while the run it just performed recorded outcome=CRASHED in cost.log.
#
# That combination is exactly the 2026-08-12 outage: agent_propose.sh returned 0 on a
# masked crash, the guard never fired, and every Picked row was marked seen without ever
# being drafted — orphaned even after credits were restored. Belt and braces, because the
# expensive failure direction here is silent state advance, not an extra retry.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/content_change_dispatch.sh"

fail=0
# See tests/test_buzz_deliver.sh: conditions must not run under pipefail, or an
# early-exiting reader turns a satisfied assertion into a red one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# ── Sandbox: mirrors tests/test_content_change_dispatch.sh, plus a cost.log the stubbed
#    agent_propose.sh appends to, so the dispatcher sees a real recorded outcome. ──
sandbox() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/bin" "$h/logs" "$h/var"

  cat > "$h/bin/notion_rest.py" <<'PY'
import os, sys
f = os.environ.get("STUB_JSON_FILE", "")
sys.stdout.write(open(f).read() if f and os.path.exists(f) else "[]")
PY

  # Stub runner: records the call, appends a schema-3 cost.log line carrying AP_OUTCOME,
  # and can leave the same receipt-keyed terminal snapshot as the real runner.
  cat > "$h/bin/agent_propose.sh" <<'SH'
#!/usr/bin/env bash
echo "call" >> "$AP_CALLS_FILE"
if [ "${AP_NO_COST:-0}" != 1 ]; then
  printf 'ts=%s schema=3 profile=augustus model=openai/gpt-5.5 task=%s outcome=%s proposal=none run_seconds=215 attempts=1 tokens=unknown usage_before=42.1 usage_after=42.1 cost_usd_delta=0.000000 cost_src=openrouter-key-api memory=fallback\n' \
    "$(date -Is)" "${AP_TASK:-augustus-content}" "${AP_OUTCOME:-OPS}" >> "$AP_COST_LOG"
fi
if [ "${AP_TERMINAL:-none}" != none ]; then
  mkdir -p "$(dirname "$CONTENT_BOARD_SNAPSHOT")"
  printf 'baseline:Picked\nrun_id=%s\nentry_point=picked-change\n' "$(printf 'a%.0s' {1..64})" > "$CONTENT_BOARD_SNAPSHOT"
  case "$AP_TERMINAL" in
    draft) printf 'page=%s from=Picked to=Draft\n' "${AP_DRAFT_PAGE:-id-B}" >> "$CONTENT_BOARD_SNAPSHOT" ;;
    decline) printf 'decline_event=%s\n' "$(printf 'e%.0s' {1..64})" >> "$CONTENT_BOARD_SNAPSHOT" ;;
  esac
fi
exit "${AP_RC:-0}"
SH
  chmod +x "$h/bin/agent_propose.sh"
  echo "$h"
}

state() { echo "$1/var/content_picked.state"; }
mkjson() { local f=$1; shift; local out="[" sep="" id
  for id in "$@"; do out="$out$sep{\"id\":\"$id\",\"angle\":\"a\",\"status\":\"Picked\"}"; sep=","; done
  echo "$out]" > "$f"; }

# Seed a sandbox with a known-stale state file and return its md5 before the run.
run_dispatch() {
  local h=$1 rc_val=$2 outcome=$3 terminal=${4:-none} draft_page=${5:-id-B} no_cost=${6:-0}
  CONTENT_DISPATCH_ROOT="$h" \
  NOTION_REST_BIN="$h/bin/notion_rest.py" \
  AGENT_PROPOSE_BIN="$h/bin/agent_propose.sh" \
  CONTENT_PICKED_STATE="$(state "$h")" \
  LOG_DIR="$h/logs" \
  AGENT_COST_LOG="$h/logs/cost.log" \
  CONTENT_BOARD_SNAPSHOT="$h/var/content_board.snapshot" \
  AUGUSTUS_CONTENT_ENV="$h/augustus-content.env" \
  STUB_JSON_FILE="$h/board.json" \
  AP_CALLS_FILE="$h/ap_calls" \
  AP_COST_LOG="$h/logs/cost.log" \
  AP_RC="$rc_val" \
  AP_OUTCOME="$outcome" \
  AP_NO_COST="$no_cost" \
  AP_TERMINAL="$terminal" \
  AP_DRAFT_PAGE="$draft_page" \
  bash "$SCRIPT" >/dev/null 2>&1
  echo $?
}

echo '--- scenario 1: runner exits 0 but recorded CRASHED -> state HELD ---'
h1=$(sandbox)
mkjson "$h1/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h1")"
before=$(md5sum "$(state "$h1")" | awk '{print $1}')
rc=$(run_dispatch "$h1" 0 CRASHED)
after=$(md5sum "$(state "$h1")" | awk '{print $1}')
assert 'exits 0 (timer-safe)' "[ '$rc' = 0 ]"
assert 'dispatch was attempted' "[ -f '$h1/ap_calls' ]"
assert 'state NOT advanced despite rc=0' "[ '$before' = '$after' ]"
assert 'id-B still absent, so it retries next tick' "! grep -qx id-B '$(state "$h1")'"
assert 'log explains the hold' "grep -q 'CRASHED' '$h1/logs/content_change_dispatch.log'"

echo '--- scenario 2: genuine success -> state ADVANCED (no over-correction) ---'
h2=$(sandbox)
mkjson "$h2/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h2")"
s2=$(state "$h2")
rc=$(run_dispatch "$h2" 0 OPS draft id-B)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'drafted id-B is removed from eligible state' "! grep -qx id-B '$s2'"
assert 'state retains id-A' "grep -qx id-A '$s2'"

echo '--- scenario 3: an evidenced owned decline advances the whole observed set ---'
h3=$(sandbox)
mkjson "$h3/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h3")"
s3=$(state "$h3")
rc=$(run_dispatch "$h3" 0 OPS decline)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'state advanced (a decline is a real, terminal answer)' "grep -qx id-B '$s3'"

echo '--- scenario 4: runner exits non-zero -> state HELD (pre-existing guard) ---'
h4=$(sandbox)
mkjson "$h4/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h4")"
before=$(md5sum "$(state "$h4")" | awk '{print $1}')
rc=$(run_dispatch "$h4" 1 CRASHED)
after=$(md5sum "$(state "$h4")" | awk '{print $1}')
assert 'exits 0 (fail-soft for the timer)' "[ '$rc' = 0 ]"
assert 'state byte-for-byte unchanged' "[ '$before' = '$after' ]"

echo '--- scenario 5: flock SKIP exit 0 with no cost record -> state HELD ---'
h5=$(sandbox)
mkjson "$h5/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h5")"
before=$(md5sum "$(state "$h5")" | awk '{print $1}')
rc=$(run_dispatch "$h5" 0 OPS none id-B 1)
after=$(md5sum "$(state "$h5")" | awk '{print $1}')
assert 'exits 0 (timer-safe)' "[ '$rc' = 0 ]"
assert 'state stays held when the invocation records no run' "[ '$before' = '$after' ]"
assert 'hold names the missing successful OPS record' "grep -q 'no successful augustus-content OPS run' '$h5/logs/content_change_dispatch.log'"

echo '--- scenario 6: OPS without a fresh terminal snapshot -> state HELD ---'
h6=$(sandbox)
mkjson "$h6/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h6")"
before=$(md5sum "$(state "$h6")" | awk '{print $1}')
rc=$(run_dispatch "$h6" 0 OPS none)
after=$(md5sum "$(state "$h6")" | awk '{print $1}')
assert 'exits 0 (timer-safe)' "[ '$rc' = 0 ]"
assert 'state stays held when no terminal evidence was written' "[ '$before' = '$after' ]"
assert 'hold is named in the dispatcher log' "grep -q 'fresh content snapshot\|neither Picked-to-Draft' '$h6/logs/content_change_dispatch.log'"

echo '--- scenario 7: a draft of another page cannot clear this tick’s new row ---'
h7=$(sandbox)
mkjson "$h7/board.json" id-A id-B
printf '%s\n' id-A > "$(state "$h7")"
before=$(md5sum "$(state "$h7")" | awk '{print $1}')
rc=$(run_dispatch "$h7" 0 OPS draft id-A)
after=$(md5sum "$(state "$h7")" | awk '{print $1}')
assert 'exits 0 (timer-safe)' "[ '$rc' = 0 ]"
assert 'state holds id-B when another page was drafted' "[ '$before' = '$after' ]"
assert 'the mismatch names both the run and page' "grep -q 'drafted page=id-A, not one of this tick' '$h7/logs/content_change_dispatch.log'"

exit $fail
