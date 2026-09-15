#!/usr/bin/env bash
# Hand-run acceptance for the T5.3a workflow controls (Dave, once, at land). Runs ON the box and
# changes no workflow state: every positive case is a preview or a refusal. Not under tests/*.sh,
# so bin/verify.sh never runs it; tests/test_control_room_control.sh only lints it.
#
#   tests/acceptance/control_room_controls.sh [--screen http://100.86.82.16:8787]
#
# Steps 1-4 assert (PASS/FAIL); step 5 prints what to do on the screen from the Mac and asserts
# nothing. The script greps itself first: it must never carry a resume apply or an enable.
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
forbidden=("--stage ap""ply" "enable --n""ow" 'stage":"ap''ply"')
for pattern in "${forbidden[@]}"; do
  if grep -q -F -- "$pattern" "$0"; then
    echo "FAIL: this script carries '$pattern' — refusing to run" >&2
    exit 1
  fi
done
pass "self-check: no apply, no enable in this script"

broker() { # broker <act args...>: the root copy through sudo, JSON on stdout
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
out=$(broker pause knowledge-digest --reason acceptance)
if [ "$(field "$out" 'd["result"]')" = refused ] && [ "$(field "$out" 'd["refusal"]["code"]')" = state_conflict ]; then
  pass "pause knowledge-digest -> refused state_conflict (already paused)"
else flunk "pause knowledge-digest -> $(field "$out" 'd["result"]') / $(field "$out" 'd["refusal"]')"; fi

out=$(broker resume knowledge-digest --stage preview --reason acceptance)
if [ "$(field "$out" 'd["result"]')" = previewed ]; then
  pass "resume knowledge-digest --stage preview -> previewed"
  echo "     implication: $(field "$out" 'd["preview"]["implication"]["message"]')"
  if [ "$(field "$out" 'd["preview"]["implication"]["catchUp"]')" = True ]; then
    pass "preview reports catchUp: true (Persistent=yes, last Sunday elapse missed)"
  else flunk "preview reports catchUp: $(field "$out" 'd["preview"]["implication"]["catchUp"]') (expected True)"; fi
else flunk "resume knowledge-digest --stage preview -> $(field "$out" 'd["result"]')"; fi

out=$(broker pause buzz-pr-watch --reason acceptance)
if [ "$(field "$out" 'd["refusal"]["code"]')" = state_conflict ]; then
  pass "pause buzz-pr-watch -> refused state_conflict"
else flunk "pause buzz-pr-watch -> $(field "$out" 'd["result"]') / $(field "$out" 'd["refusal"]')"; fi
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
  pass "stop knowledge-digest without --confirm -> confirmation_required"
else flunk "stop knowledge-digest without --confirm -> $(field "$out" 'd["refusal"]')"; fi

# raw-ingest declares no Retry row. Never use a declared workflow here: the CLI bypasses the
# screen's failed-last-run rule and would start it.
out=$(broker retry raw-ingest --reason acceptance)
if [ "$(field "$out" 'd["refusal"]["code"]')" = not_idempotent ]; then
  pass "retry raw-ingest -> not_idempotent"
else flunk "retry raw-ingest -> $(field "$out" 'd["refusal"]')"; fi

echo "== 5. screen (from the Mac; no assertion)"
cat <<EOF
  Open $SCREEN/workflows/knowledge-digest (http://praetorium:8787/workflows/knowledge-digest).
  Expect: Controls shows 'paused'; Resume enabled; Retry disabled with its reason as tooltip;
  last action = the newest non-preview receipt for this workflow (step 4's refused stop,
  confirmation_required).
  Click Resume -> the preview dialog states the catch-up implication -> Cancel.
  Nothing resumed; the fleet is still off.
EOF

if [ "$fail" -eq 0 ]; then echo "ALL PASS"; else echo "SOME FAIL"; fi
exit "$fail"
