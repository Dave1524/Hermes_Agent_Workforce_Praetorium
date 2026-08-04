#!/usr/bin/env bash
# The three input adapters — deliver_report.sh, notify.sh, inbox_backlog_alert.sh —
# after the Buzz migration. Each one owns its caller interface and its "should this
# send at all?" decision, then makes AT MOST ONE bin/deliver.sh call.
#
# What is being pinned here is the split. Before the migration each adapter carried a
# private copy of hermes resolution and its own idea of freshness; three copies of a
# transport is three places for a delivery to go quietly missing. deliver.sh is stubbed
# throughout: these cases assert the handoff, not the transport.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

sandbox() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/logs" "$h/overnight"
  cat > "$h/deliver-stub.sh" <<'SH'
#!/usr/bin/env bash
printf '%s\n' "$*" >> "$HOME/deliver-calls.log"
exit "${STUB_RC:-0}"
SH
  chmod +x "$h/deliver-stub.sh"
  echo "$h"
}

run_adapter() {  # run_adapter <sandbox> <script> [args...]
  local h=$1 script=$2; shift 2
  HOME="$h" DELIVER_BIN="$h/deliver-stub.sh" bash "$REPO_ROOT/bin/$script" "$@" \
    >/dev/null 2>&1
  echo $?
}
calls() { [ -f "$1/deliver-calls.log" ] && grep -c . "$1/deliver-calls.log" || echo 0; }
argv()  { cat "$1/deliver-calls.log" 2>/dev/null; }

echo '--- deliver_report.sh: artifact lookup stays here, transport does not ---'
h=$(sandbox)
printf 'older\n' > "$h/overnight/morning-report-2026-08-01.md"
printf 'newer\n' > "$h/overnight/morning-report-2026-08-04.md"
rc=$(REPORT_DIR="$h/overnight" DELIVERY_ROUTE=ops DELIVERY_JOB=overnight-morning-report.service \
     run_adapter "$h" deliver_report.sh)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'exactly one deliver.sh call' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'newest report selected' "argv '$h' | grep -q -- '--file $h/overnight/morning-report-2026-08-04.md'"
assert 'route passed through' "argv '$h' | grep -q -- '--route ops'"
assert 'job passed through' "argv '$h' | grep -q -- '--job overnight-morning-report.service'"
assert 'age budget still handed to the transport' "argv '$h' | grep -q -- '--max-age-secs 93600'"
assert 'the adapter no longer resolves a transport of its own' \
  "! grep -qE 'hermes|hsend' '$REPO_ROOT/bin/deliver_report.sh'"

echo '--- deliver_report.sh: a run marker supersedes the age budget ---'
h=$(sandbox)
printf 'body\n' > "$h/overnight/morning-report-2026-08-04.md"
: > "$h/marker"
rc=$(REPORT_DIR="$h/overnight" DELIVERY_ROUTE=ops DELIVERY_RUN_MARKER="$h/marker" \
     run_adapter "$h" deliver_report.sh)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'run marker forwarded' "argv '$h' | grep -q -- '--run-marker $h/marker'"

echo '--- deliver_report.sh: nothing to deliver stays silent ---'
h=$(sandbox)
rc=$(REPORT_DIR="$h/overnight" DELIVERY_ROUTE=ops run_adapter "$h" deliver_report.sh)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'no transport call for an absent artifact' "[ \"\$(calls '$h')\" -eq 0 ]"

h=$(sandbox)
: > "$h/overnight/morning-report-2026-08-04.md"
rc=$(REPORT_DIR="$h/overnight" DELIVERY_ROUTE=ops run_adapter "$h" deliver_report.sh)
assert 'no transport call for an empty artifact' "[ \"\$(calls '$h')\" -eq 0 ]"

echo '--- an unrouted caller keeps its Discord behaviour and stays visible as a gap ---'
h=$(sandbox)
printf 'body\n' > "$h/overnight/morning-report-2026-08-04.md"
rc=$(REPORT_DIR="$h/overnight" run_adapter "$h" deliver_report.sh)
assert 'still delivers' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'route is unrouted, never silently ops' "argv '$h' | grep -q -- '--route unrouted'"

echo '--- deliver_report.sh is fail-soft when the transport itself fails ---'
h=$(sandbox)
printf 'body\n' > "$h/overnight/morning-report-2026-08-04.md"
rc=$(STUB_RC=1 REPORT_DIR="$h/overnight" DELIVERY_ROUTE=ops run_adapter "$h" deliver_report.sh)
assert 'exits 0 despite a failing transport' "[ '$rc' = 0 ]"

echo '--- notify.sh keeps its positional interface ---'
h=$(sandbox)
rc=$(DELIVERY_ROUTE=ops DELIVERY_JOB=agent-alert@raw-ingest.service \
     run_adapter "$h" notify.sh '[Praetorium] Unit failed' 'raw-ingest exited 1')
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'one call' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'subject forwarded' "argv '$h' | grep -q -- \"--subject \[Praetorium\] Unit failed\""
assert 'message forwarded' "argv '$h' | grep -q -- '--message raw-ingest exited 1'"
assert 'route forwarded' "argv '$h' | grep -q -- '--route ops'"

echo '--- notify.sh file mode attaches instead of inlining ---'
h=$(sandbox)
printf 'summary\n' > "$h/report.md"
rc=$(DELIVERY_ROUTE=research run_adapter "$h" notify.sh 'subj' 'ignored' --file "$h/report.md")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'file forwarded' "argv '$h' | grep -q -- '--file $h/report.md'"
assert 'message text dropped in file mode' "! argv '$h' | grep -q -- '--message ignored'"

echo '--- notify.sh with too few arguments sends nothing and never fails a unit ---'
h=$(sandbox)
rc=$(run_adapter "$h" notify.sh 'only-a-subject')
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'no transport call' "[ \"\$(calls '$h')\" -eq 0 ]"

echo '--- notify.sh has no route of its own: an unset route is not ops ---'
h=$(sandbox)
rc=$(run_adapter "$h" notify.sh 'subj' 'body')
assert 'route is unrouted' "argv '$h' | grep -q -- '--route unrouted'"

echo '--- inbox_backlog_alert.sh: silence is the normal case ---'
h=$(sandbox)
rc=$(run_adapter "$h" inbox_backlog_alert.sh)
assert 'no inbox worktree => exits 0 silently' "[ '$rc' = 0 ] && [ \"\$(calls '$h')\" -eq 0 ]"

h=$(sandbox)
mkdir -p "$h/agent-worktrees/inbox/_inbox/agents"
rc=$(run_adapter "$h" inbox_backlog_alert.sh)
assert 'empty inbox => no alert' "[ \"\$(calls '$h')\" -eq 0 ]"

h=$(sandbox)
mkdir -p "$h/agent-worktrees/inbox/_inbox/agents"
: > "$h/agent-worktrees/inbox/_inbox/agents/fresh.md"
rc=$(run_adapter "$h" inbox_backlog_alert.sh)
assert 'fresh proposal is under threshold => no alert' "[ \"\$(calls '$h')\" -eq 0 ]"

echo '--- inbox_backlog_alert.sh alerts once when the backlog ages out ---'
h=$(sandbox)
mkdir -p "$h/agent-worktrees/inbox/_inbox/agents"
: > "$h/agent-worktrees/inbox/_inbox/agents/old.md"
: > "$h/agent-worktrees/inbox/_inbox/agents/old2.md"
touch -d '5 days ago' "$h/agent-worktrees/inbox/_inbox/agents/old.md"
rc=$(DELIVERY_ROUTE=approvals DELIVERY_JOB=inbox-backlog-alert.service \
     run_adapter "$h" inbox_backlog_alert.sh)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'exactly one alert' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'routed to approvals' "argv '$h' | grep -q -- '--route approvals'"
assert 'counts reported' "argv '$h' | grep -q '2 proposals pending, oldest 5d'"
assert 'no artifact attached to a status alert' "! argv '$h' | grep -q -- '--file'"

echo '--- the threshold is still configurable ---'
h=$(sandbox)
mkdir -p "$h/agent-worktrees/inbox/_inbox/agents"
: > "$h/agent-worktrees/inbox/_inbox/agents/old.md"
touch -d '3 days ago' "$h/agent-worktrees/inbox/_inbox/agents/old.md"
rc=$(INBOX_BACKLOG_THRESHOLD_DAYS=7 run_adapter "$h" inbox_backlog_alert.sh)
assert 'raised threshold suppresses the alert' "[ \"\$(calls '$h')\" -eq 0 ]"

exit $fail
