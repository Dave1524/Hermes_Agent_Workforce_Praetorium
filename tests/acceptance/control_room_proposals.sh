#!/usr/bin/env bash
# Hand-run acceptance for the T5.3b schedule/retirement PR worker (Dave, once, at land). Runs ON
# the box and creates no branch and no pull request: every positive case is a preview or a
# refusal. Not under tests/*.sh, so bin/verify.sh never runs it; tests/test_control_room_proposals.sh
# only lints it.
#
#   tests/acceptance/control_room_proposals.sh [--screen http://100.86.82.16:8787]
#
# Steps 1-3 assert (PASS/FAIL); step 4 prints what to do on the screen from the Mac and asserts
# nothing. The script greps itself first: it must never carry a submit, a PR call or a remote write.
set -uo pipefail
cd "$(dirname "$0")/../.." || exit 1

SCREEN="http://100.86.82.16:8787"
STATE="/var/lib/control-room-proposals"
DROPIN="/etc/systemd/system/control-room.service.d/proposals.conf"
WORKER="$HOME/agent-workforce/bin/workflow_pr.py"
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

# --- self-check: this script previews and refuses, never opens anything -----------------------
# The forbidden strings are assembled from halves so the literals never appear in this file and
# a plain grep (tests/test_control_room_proposals.py) finds nothing either.
forbidden=("--sub""mit" 'stage":"sub''mit"' "gh p""r" "pu""sh")
for pattern in "${forbidden[@]}"; do
  if grep -q -F -- "$pattern" "$0"; then
    echo "FAIL: this script carries '$pattern' — refusing to run" >&2
    exit 1
  fi
done
pass "self-check: no submit, no PR call, no remote write in this script"

worker() { # worker <args...>: the deployed CLI against the live state root, preview only
  CONTROL_ROOM_PROPOSALS_ROOT="$STATE" python3 "$WORKER" "$@"
}
post() { # post <json>: POST to the screen's proposals endpoint; prints "<status> <body>"
  curl -s -o /tmp/crp-acceptance.body -w '%{http_code}' -X POST "$SCREEN/api/v1/control/proposals" \
    -H 'Content-Type: application/json' -H 'X-Control-Room: 1' --data "$1"
  echo " $(cat /tmp/crp-acceptance.body)"
}

echo "== 1. installed"
check "drop-in installed at $DROPIN" test -f "$DROPIN"
check "control-room.service carries StateDirectory=control-room-proposals" \
  bash -c 'systemctl show control-room.service -p StateDirectory --value | grep -qw control-room-proposals'
check "bare clone present at $STATE/repo.git" test -d "$STATE/repo.git"
if worker doctor > /tmp/crp-acceptance.doctor 2>&1 && ! grep -q '^fail:' /tmp/crp-acceptance.doctor; then
  pass "doctor is all ok"
else
  flunk "doctor reports a fail"; cat /tmp/crp-acceptance.doctor
fi

echo "== 2. peer gate from this host"
records_before=$(find "$STATE/proposals" -name '*.json' 2>/dev/null | wc -l)
answer=$(post '{"workflow_id":"knowledge-digest","kind":"schedule","stage":"preview","reason":"acceptance","proposed":{"on_calendar":["Sun 07:00"]}}')
case "$answer" in
  403*peer_denied*) pass "a POST from the box itself is 403 peer_denied" ;;
  *) flunk "expected 403 peer_denied from this host, got: $answer" ;;
esac
records_after=$(find "$STATE/proposals" -name '*.json' 2>/dev/null | wc -l)
check "the refusal wrote a proposal record" test "$records_after" -gt "$records_before"

echo "== 3. CLI previews (state root $STATE; nothing leaves the box)"
if worker schedule knowledge-digest --on-calendar "Sun 07:00" --reason acceptance --preview > /tmp/crp-acceptance.schedule 2>&1; then
  pass "schedule knowledge-digest Sun 07:00 previews"
  check "the diff names the timer, the manifest and the contract" \
    bash -c 'grep -q "systemd/knowledge-digest.timer" /tmp/crp-acceptance.schedule && grep -q "design/agents/claudius.toml" /tmp/crp-acceptance.schedule && grep -q "design/contracts/knowledge-digest.md" /tmp/crp-acceptance.schedule'
  check "the timezone block carries CEST/CET and UTC elapses" \
    bash -c 'grep -Eq "CES?T" /tmp/crp-acceptance.schedule && grep -q "UTC" /tmp/crp-acceptance.schedule'
  check "the catch-up sentence names resume" grep -q "resume" /tmp/crp-acceptance.schedule
  check "manifest-joins pass" grep -Eq "^ *pass +manifest-joins" /tmp/crp-acceptance.schedule
  check "drift-preview lists the timer as introduced" grep -q "knowledge-digest.timer" /tmp/crp-acceptance.schedule
else
  flunk "schedule knowledge-digest preview failed"; tail -20 /tmp/crp-acceptance.schedule
fi
worker schedule qmd-refresh --on-calendar hourly --reason acceptance --preview > /tmp/crp-acceptance.refresh 2>&1
check "schedule qmd-refresh → not_calendar_timer" grep -q not_calendar_timer /tmp/crp-acceptance.refresh
worker schedule buzz-agent@marcus --on-calendar "Sun 07:00" --reason acceptance --preview > /tmp/crp-acceptance.marcus 2>&1
check "schedule buzz-agent@marcus → not_a_timer" grep -q not_a_timer /tmp/crp-acceptance.marcus
if worker retire knowledge-digest --reason acceptance-preview-only --receipts keep --notion keep --inbox keep --note acceptance --preview \
     > /tmp/crp-acceptance.retire 2>&1; then
  pass "retire knowledge-digest previews"
  check "the residue tables render (source and live)" \
    bash -c 'grep -c "has a check?" /tmp/crp-acceptance.retire | grep -qx 2 || grep -q "residue_verdict" /tmp/crp-acceptance.retire'
  check "the dave-only env line is reported unverifiable" grep -q "unverifiable from an agent" /tmp/crp-acceptance.retire
  check "the removal table names the timer" grep -q "systemd/knowledge-digest.timer" /tmp/crp-acceptance.retire
  check "deploy-preview ran" grep -Eq "deploy-preview" /tmp/crp-acceptance.retire
else
  flunk "retire knowledge-digest preview failed"; tail -20 /tmp/crp-acceptance.retire
fi
worker retire knowledge-digest --reason acceptance-preview-only --receipts keep --notion keep --inbox keep --note "" --preview \
  > /tmp/crp-acceptance.retention 2>&1
check "retire without a note → retention_required or bad_request" grep -Eq "retention_required|bad_request" /tmp/crp-acceptance.retention
check "no control-room/* branch reached origin" \
  bash -c 'test -z "$(git -C "$HOME/dev/agent-workforce" ls-remote --heads origin "control-room/*" 2>/dev/null)"'

echo "== 4. screen (from the Mac; nothing asserted here)"
cat <<EOF
  open $SCREEN/workflows/knowledge-digest
  - Controls row 2 shows "Change schedule…" and "Retire…"
  - click Change schedule… → the dialog is prefilled with the current OnCalendar → set "Sun 07:00",
    a reason → Preview → the same diff and checks as step 3 → Cancel
  - no PR exists: on the Mac, list the open pull requests with gh — none from control-room/
EOF

rm -f /tmp/crp-acceptance.*
echo
[ "$fail" -eq 0 ] && echo "all acceptance steps passed"
exit "$fail"
