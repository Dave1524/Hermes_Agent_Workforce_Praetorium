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
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

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
printf 'AGENT_RECEIPT_UNIT=%s\nAGENT_RUN_ID=%s\nAGENT_PARENT_RUN_ID=%s\n' "${AGENT_RECEIPT_UNIT:-UNSET}" \
  "${AGENT_RUN_ID:-UNSET}" "${AGENT_PARENT_RUN_ID:-UNSET}" > "${AP_RECEIPT_ENV_FILE:-/dev/null}"
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

# ── T5.2: two receipts per dispatched tick, none for a quiet or fail-soft one ──
# The stubbed agent_propose.sh records the receipt identity it inherited (the child's
# unit, run id and parent), and CONTRACT_EXEC points the tick's own executor call at a
# recording stub. Scenario (r3) runs the real executor over the LIVE augustus-content
# contract so the tick receipt on disk is proven valid and folded under augustus-content/.
make_exec_stub() {
  local h=$1
  cat > "$h/bin/stub_exec.py" <<'PY'
#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_OUT"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
print("contract_exec: stub")
PY
  chmod +x "$h/bin/stub_exec.py"
  echo "$h/bin/stub_exec.py"
}
run_receipted() {   # $1=home $2=json $3=stubfail $4=AP_RC $5=exec override (default: recording stub)
  local h=$1 jsonfile=$2 stubfail=$3 ap_rc=${4:-0} exec_bin=${5:-}
  [ -n "$exec_bin" ] || exec_bin=$(make_exec_stub "$h")
  CONTENT_DISPATCH_ROOT="$h" NOTION_REST_BIN="$h/bin/notion_rest.py" \
  AGENT_PROPOSE_BIN="$h/bin/agent_propose.sh" CONTENT_PICKED_STATE="$h/var/content_picked.state" \
  LOG_DIR="$h/logs" AGENT_COST_LOG="$h/logs/cost.log" CONTENT_BOARD_SNAPSHOT="$h/var/content_board.snapshot" \
  AUGUSTUS_CONTENT_ENV="$h/augustus-content.env" STUB_JSON_FILE="$jsonfile" STUB_FAIL="$stubfail" \
  AP_CALLS_FILE="$h/ap_calls" AP_OVERRIDES_FILE="$h/ap_overrides" AP_ENTRY_POINT_FILE="$h/ap_entry_point" \
  AP_RECEIPT_ENV_FILE="$h/ap_receipt_env" AP_RC="$ap_rc" \
  INVOCATION_ID=tick0001 CONTRACT_EXEC="$exec_bin" STUB_OUT="$h/exec.jsonl" \
  CONTROL_ROOM_RECEIPT_ROOT="$h/receipts" HOME="$h" \
  bash "$SCRIPT" >/dev/null 2>&1
  echo $?
}
exec_calls() { if [ -f "$1/exec.jsonl" ]; then grep -c . "$1/exec.jsonl"; else echo 0; fi; }
exec_has() {
  python3 - "$1/exec.jsonl" "$2" "$3" <<'PY'
import json, sys
call = json.loads(open(sys.argv[1]).read().splitlines()[-1])
flag, value = sys.argv[2], sys.argv[3]
sys.exit(0 if flag in call and call[call.index(flag) + 1] == value else 1)
PY
}

echo '--- scenario (r1): a dispatched tick gives the child its ids and writes its own receipt (::dispatch-parent-child-ids) ---'
hr=$(sandbox); jr="$hr/board.json"
mkjson "$jr" id-A id-B
printf '%s\n' id-A > "$(state "$hr")"
rc=$(run_receipted "$hr" "$jr" "")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the child inherits AGENT_RECEIPT_UNIT=augustus-content' "grep -qx 'AGENT_RECEIPT_UNIT=augustus-content' '$hr/ap_receipt_env'"
assert 'the child run id is <tick>-draft' "grep -qx 'AGENT_RUN_ID=tick0001-draft' '$hr/ap_receipt_env'"
assert 'the child parent id is the tick' "grep -qx 'AGENT_PARENT_RUN_ID=tick0001' '$hr/ap_receipt_env'"
assert 'the tick calls the executor exactly once' "[ \"\$(exec_calls '$hr')\" = 1 ]"
assert 'for content-change-dispatch at vantage run' "grep -q '\"content-change-dispatch\", \"--vantage\", \"run\"' '$hr/exec.jsonl'"
assert 'with the tick as its run id' "exec_has '$hr' --run-id tick0001"
assert 'a state change naming the drafted page' "exec_has '$hr' --state-change 'content_picked.state advanced: draft page=id-B'"
assert 'and a handoff to the child run' "exec_has '$hr' --handoff-event tick0001-draft && exec_has '$hr' --handoff-recipient augustus"
assert 'never --failed on success' "! grep -q -- '--failed' '$hr/exec.jsonl'"

echo '--- scenario (r2): quiet and fail-soft ticks write nothing (::dispatch-quiet-tick-no-receipt) ---'
hq=$(sandbox); jq_="$hq/board.json"
mkjson "$jq_" id-A id-B
printf '%s\n' id-A id-B > "$(state "$hq")"
rc=$(run_receipted "$hq" "$jq_" "")
assert 'quiet tick exits 0' "[ '$rc' = 0 ]"
assert 'quiet tick: no executor call' "[ \"\$(exec_calls '$hq')\" = 0 ]"
assert 'quiet tick: no child dispatched' "[ \"\$(ncalls '$hq')\" -eq 0 ]"
hf=$(sandbox); jf="$hf/board.json"
mkjson "$jf" id-A id-B
rc=$(run_receipted "$hf" "$jf" 1)
assert 'fail-soft tick exits 0' "[ '$rc' = 0 ]"
assert 'fail-soft tick: no executor call' "[ \"\$(exec_calls '$hf')\" = 0 ]"

echo '--- scenario (r2b): a held tick still receipts, as failed, with the reason (::dispatch-parent-child-ids) ---'
hh=$(sandbox); jh="$hh/board.json"
mkjson "$jh" id-A id-B
printf '%s\n' id-A > "$(state "$hh")"
rc=$(run_receipted "$hh" "$jh" "" 3)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'one executor call' "[ \"\$(exec_calls '$hh')\" = 1 ]"
assert '--failed carries the hold reason' "exec_has '$hh' --failed 'agent_propose.sh returned 3 — state held so new rows retry next tick'"
assert 'the handoff is still recorded' "exec_has '$hh' --handoff-event tick0001-draft"

echo '--- scenario (r3): the real executor folds the tick receipt under augustus-content/ and it validates (::receipt-reads-back-valid) ---'
hv=$(sandbox); jv="$hv/board.json"
mkjson "$jv" id-A id-B
printf '%s\n' id-A > "$(state "$hv")"
cat > "$hv/bin/real_exec.sh" <<EOF
#!/usr/bin/env bash
exec python3 "$REPO_ROOT/bin/contract_exec.py" "\$@" --repo-root "$REPO_ROOT" --home "$hv"
EOF
chmod +x "$hv/bin/real_exec.sh"
rc=$(run_receipted "$hv" "$jv" "" 0 "$hv/bin/real_exec.sh")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'receipt at receipts/augustus-content/tick0001.json (logical fold)' "[ -s '$hv/receipts/augustus-content/tick0001.json' ]"
assert 'the receipt validates, is artifact, unit content-change-dispatch, handoff to the child' "python3 - '$hv/receipts/augustus-content/tick0001.json' '$REPO_ROOT/bin/workflow_receipt.py' <<'PY'
import importlib.util, json, sys
spec = importlib.util.spec_from_file_location('wr', sys.argv[2]); m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
r = json.load(open(sys.argv[1]))
ok = (not m.validate(r) and r['terminal']['outcome'] == 'artifact' and r['unit'] == 'content-change-dispatch'
      and r['workflow_id'] == 'augustus-content' and r['handoff']['event'] == 'tick0001-draft'
      and all(a['status'] == 'not_applicable' for a in r['assertions']))
sys.exit(0 if ok else 1)
PY"

exit $fail
