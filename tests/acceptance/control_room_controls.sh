#!/usr/bin/env bash
# Hand-run acceptance for the T5.3a workflow controls and the T5.3g runtime controls (Dave, once,
# at land). Runs ON the box and changes no workflow or runtime state: every positive case is a
# preview or a refusal. Not under tests/*.sh, so bin/verify.sh never runs it;
# tests/test_control_room_control.sh only lints it.
#
#   tests/acceptance/control_room_controls.sh [--screen http://100.86.82.16:8787]
#
# Steps 1-4b assert (PASS/FAIL); step 5 prints what to do on the screen from the Mac and asserts
# nothing. The script greps itself first: it must never carry a resume apply, an enable, or a
# confirmed action — a confirmed start would bring a runtime up.
#
# Nothing here assumes a live state. On 2026-09-16 this script carried `pause knowledge-digest`
# and `pause buzz-pr-watch`, expecting state_conflict because both were paused on the day it
# was written; both had since been enabled by hand, so the T5.3g land run paused them. `pause`
# needs no confirm, so its only guard is the state, and a state is not a property of a script.
# broker() therefore refuses to issue an unconfirmed applying verb (pause, run_now) against any
# id the installed allowlist knows as a workflow, and the state-dependent cases accept whichever
# refusal or preview the live state produces.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

SCREEN="http://100.86.82.16:8787"
SOCKET="/run/control-room-broker.sock"
LIB="/usr/local/lib/control-room/control_broker.py"
ALLOWLIST="/etc/control-room/allowlist.json"
RECEIPTS="/var/lib/control-room/receipts"
fail=0

while [ $# -gt 0 ]; do
  case "$1" in
    --screen) SCREEN="$2"; shift 2 ;;
    *) echo "usage: $0 [--screen URL]" >&2; exit 2 ;;
  esac
done

pass() { echo "PASS: $*"; }
flunk() { echo "FAIL: $*"; fail=1; }
check() { # check <description> <command...>: PASS when the command exits 0
  local what="$1"; shift
  if "$@" >/dev/null 2>&1; then pass "$what"; else flunk "$what"; fi
}

# --- self-check: this script previews and refuses, never applies ------------------------------
# The forbidden strings are assembled from halves so the literals never appear in this file and
# a plain grep (tests/test_control_room_control.py) finds nothing either.
forbidden=("--stage ap""ply" "enable --n""ow" 'stage":"ap''ply"' "--con""firm" '"confirm":''true')
for pattern in "${forbidden[@]}"; do
  if grep -q -F -- "$pattern" "$0"; then
    echo "FAIL: this script carries '$pattern' — refusing to run" >&2
    exit 1
  fi
done
pass "self-check: no apply, no enable, no confirm in this script"

GUARD_TRIPPED=$(mktemp)
trap 'rm -f "$GUARD_TRIPPED"' EXIT
is_allowlisted_workflow() { # is_allowlisted_workflow <id>: exit 0 when the installed allowlist knows it, or cannot be read
  python3 - "$ALLOWLIST" "$1" 2>/dev/null <<'PY'
import json, sys
try:
    sys.exit(0 if sys.argv[2] in json.load(open(sys.argv[1]))["workflows"] else 1)
except Exception:
    sys.exit(0)
PY
}
broker() { # broker <verb> <id> [args...]: the root copy through sudo, JSON on stdout
  # Runs inside $(...), so the verdict travels through a file, not $fail.
  case "$1" in
    pause|run_now)
      if is_allowlisted_workflow "$2"; then
        echo "FAIL: refusing to issue '$1 $2' — it applies without confirm when the live state allows" | tee -a "$GUARD_TRIPPED" >&2
        echo '{}'; return 1
      fi ;;
  esac
  sudo /usr/bin/python3 "$LIB" act "$@" 2>/dev/null
}
field() { # field <json> <python expression over d>
  python3 -c 'import json,sys; d=json.loads(sys.argv[1]); print(eval(sys.argv[2]))' "$1" "$2" 2>/dev/null
}
newest_receipt() { # newest_receipt <dir>
  ls -1t "$1"/*.json 2>/dev/null | head -n 1
}

echo "== 1. installed"
check "control-room-broker.socket is enabled" systemctl is-enabled control-room-broker.socket
check "control-room-broker.socket is active" systemctl is-active control-room-broker.socket
check "group control-room exists" getent group control-room
check "root copy exists at $LIB" test -f "$LIB"
check "root copy is root-owned" test "$(stat -c %U "$LIB")" = root
check "allowlist exists at $ALLOWLIST" test -f "$ALLOWLIST"
check "allowlist is root-owned" test "$(stat -c %U "$ALLOWLIST")" = root
check "control_broker_allowlist.py check is clean" python3 bin/control_broker_allowlist.py check --installed "$ALLOWLIST"
check "control-room.service carries SupplementaryGroups=control-room" \
  bash -c 'systemctl show control-room.service -p SupplementaryGroups --value | grep -qw control-room'

echo "== 2. agents cannot connect"
if python3 - "$SOCKET" <<'PY' 2>/dev/null
import socket, sys
s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
try:
    s.connect(sys.argv[1])
except PermissionError:
    sys.exit(0)
sys.exit(1)
PY
then pass "connect as dave raises PermissionError"; else flunk "connect as dave did not raise PermissionError"; fi

echo "== 3. peer gate from this host"
status=$(curl -s -o /tmp/crb-acceptance-peer.json -w '%{http_code}' -X POST "$SCREEN/api/v1/control/actions" \
  -H 'X-Control-Room: 1' -H 'Content-Type: application/json' \
  -d '{"workflow_id":"knowledge-digest","action":"pause","reason":"acceptance peer gate"}')
if [ "$status" = 403 ] && grep -q '"peer_denied"' /tmp/crb-acceptance-peer.json; then
  pass "POST from the box itself -> 403 peer_denied"
else
  flunk "POST from the box itself -> $status (expected 403 peer_denied)"
fi
# The peer gate fires before the allowlist lookup, so the workflow is unresolved and the receipt
# files under _refused/ (requested_workflow_id keeps the id). Find it by the id the response names.
peer_receipt=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["receipt"]["receipt_id"])' /tmp/crb-acceptance-peer.json 2>/dev/null)
if [ -n "$peer_receipt" ] && [ -f "$RECEIPTS/_refused/$peer_receipt.json" ]; then
  pass "its receipt $peer_receipt landed under $RECEIPTS/_refused/"
else flunk "receipt '$peer_receipt' not found under $RECEIPTS/_refused/"; fi

echo "== 4. CLI through the root copy"
# resume --stage preview is the one workflow verb that reads the state and never changes it:
# paused -> previewed (with the catch-up implication), enabled -> refused state_conflict. Which
# one is the live state's business, so both pass and the line says which.
resume_preview() { # resume_preview <workflow>: PASS on previewed or state_conflict, sets $out
  out=$(broker resume "$1" --stage preview --reason acceptance)
  local result; result=$(field "$out" 'd["result"]')
  if [ "$result" = previewed ]; then
    pass "resume $1 --stage preview -> previewed (it is paused)"
    echo "     implication: $(field "$out" 'd["preview"]["implication"]["message"]')"
  elif [ "$result" = refused ] && [ "$(field "$out" 'd["refusal"]["code"]')" = state_conflict ]; then
    pass "resume $1 --stage preview -> refused state_conflict (it is enabled)"
  else flunk "resume $1 --stage preview -> $result / $(field "$out" 'd["refusal"]')"; fi
}
resume_preview knowledge-digest

resume_preview buzz-pr-watch
if [ "$(field "$out" 'any("--machine=dave@.host" in c["argv"] and "--user" in c["argv"] for c in d["receipt"]["commands"])')" = True ]; then
  pass "its receipt's commands carry --user --machine=dave@.host"
else flunk "its receipt's commands do not carry --user --machine=dave@.host"; fi

out=$(broker pause no-such-workflow --reason acceptance)
if [ "$(field "$out" 'd["refusal"]["code"]')" = unknown_workflow ]; then
  pass "pause no-such-workflow -> unknown_workflow"
else flunk "pause no-such-workflow -> $(field "$out" 'd["refusal"]')"; fi
refused_receipt=$(newest_receipt "$RECEIPTS/_refused")
if [ -n "$refused_receipt" ] && [ "$(basename "$refused_receipt" .json)" = "$(field "$out" 'd["receipt"]["receipt_id"]')" ]; then
  pass "its receipt is under _refused/"
else flunk "its receipt is not the newest under _refused/"; fi

out=$(broker stop knowledge-digest --reason x)
if [ "$(field "$out" 'd["refusal"]["code"]')" = confirmation_required ]; then
  pass "stop knowledge-digest unconfirmed -> confirmation_required"
else flunk "stop knowledge-digest unconfirmed -> $(field "$out" 'd["refusal"]')"; fi

# raw-ingest declares no Retry row. Never use a declared workflow here: the CLI bypasses the
# screen's failed-last-run rule and would start it.
out=$(broker retry raw-ingest --reason acceptance)
if [ "$(field "$out" 'd["refusal"]["code"]')" = not_idempotent ]; then
  pass "retry raw-ingest -> not_idempotent"
else flunk "retry raw-ingest -> $(field "$out" 'd["refusal"]')"; fi

echo "== 4b. runtime verbs through the root copy (T5.3g) — refused before any state check"
# Every runtime verb needs confirm, and the confirm flag is forbidden in this file (self-check
# above), so these three refuse whatever the live state of the unit is. No agent starts, stops
# or restarts here.
for verb in start stop restart; do
  out=$(broker "$verb" buzz-agent@marcus --reason acceptance)
  if [ "$(field "$out" 'd["refusal"]["code"]')" = confirmation_required ]; then
    pass "$verb buzz-agent@marcus (unconfirmed) -> confirmation_required"
  else flunk "$verb buzz-agent@marcus (unconfirmed) -> $(field "$out" 'd["result"]') / $(field "$out" 'd["refusal"]')"; fi
  if [ "$(field "$out" 'any(set(c["argv"]) & {"start", "stop", "restart"} for c in d["receipt"]["commands"])')" = False ]; then
    pass "  and its receipt shows no mutating command"
  else flunk "  but its receipt carries a mutating command"; fi
done
runtime_receipt=$(newest_receipt "$RECEIPTS/buzz-agent@marcus")
if [ -n "$runtime_receipt" ] && [ "$(basename "$runtime_receipt" .json)" = "$(field "$out" 'd["receipt"]["receipt_id"]')" ]; then
  pass "its receipt is under $RECEIPTS/buzz-agent@marcus/"
else flunk "its receipt is not the newest under $RECEIPTS/buzz-agent@marcus/"; fi
if [ "$(field "$out" 'd["receipt"]["links"]["agent"]')" = /agents/marcus ]; then
  pass "its receipt links to /agents/marcus"
else flunk "its receipt links.agent = $(field "$out" 'd["receipt"]["links"]["agent"]')"; fi
if [ "$(field "$out" 'any("status" in c["argv"] or any(p.startswith("--property=") and ("ExecStart" in p or "Environment" in p) for p in c["argv"]) for c in d["receipt"]["commands"])')" = False ]; then
  pass "its receipt's commands never ran status or read ExecStart/Environment"
else flunk "its receipt's commands ran status or read ExecStart/Environment"; fi

out=$(broker pause buzz-agent@marcus --reason acceptance)
if [ "$(field "$out" 'd["refusal"]["code"]')" = unknown_action ]; then
  pass "pause buzz-agent@marcus -> unknown_action (workflow verb on a runtime)"
else flunk "pause buzz-agent@marcus -> $(field "$out" 'd["refusal"]')"; fi

echo "== 5. screen (from the Mac; no assertion)"
cat <<EOF
  Open $SCREEN/workflows/knowledge-digest (http://praetorium:8787/workflows/knowledge-digest).
  Expect the verbs the live state allows: paused -> Resume enabled and Pause disabled; enabled
  -> the reverse. Retry disabled with its reason as tooltip; last action = the newest
  non-preview receipt for this workflow (step 4's refused stop, confirmation_required).
  Click the one enabled verb -> the dialog (Resume: the preview states the catch-up
  implication) -> Cancel. Nothing paused or resumed.

  Open $SCREEN/app/agents/marcus.
  Expect the verbs the live state allows: with the unit active, 'Stop agent now' and 'Restart
  agent now' enabled and 'Start agent now' disabled with 'runtime is active, not paused' as
  tooltip; with it inactive, the reverse ('runtime is paused, not active'). boot: <unit file
  state> beside the chip; last action = step 4b's refused restart (confirmation_required).
  Click the one enabled verb -> the dialog states the boot policy (and, for Start, the
  double-hosting risk and check-loaded.sh; for Stop/Restart, the dependents) -> Cancel.
  Nothing started, stopped or restarted.
EOF

if [ -s "$GUARD_TRIPPED" ]; then fail=1; fi
if [ "$fail" -eq 0 ]; then echo "ALL PASS"; else echo "SOME FAIL"; fi
exit "$fail"
