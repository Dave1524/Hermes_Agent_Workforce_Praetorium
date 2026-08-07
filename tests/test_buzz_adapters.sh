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
  # A payload argument may itself be multi-line, so invocations are counted by the
  # CALL marker rather than by line — otherwise a two-line summary reads as two calls.
  cat > "$h/deliver-stub.sh" <<'SH'
#!/usr/bin/env bash
printf 'CALL %s\n' "$*" >> "$HOME/deliver-calls.log"
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
calls() {
  local n
  n=$(grep -c '^CALL ' "$1/deliver-calls.log" 2>/dev/null)
  echo "${n:-0}"
}
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

echo '--- deliver_scorecard.sh: an unchanged week still reports ---'
# scorecard.sh does not rewrite a byte-identical digest, so mtime says nothing about
# whether the rollup ran. Silence policy for this producer is `never`.
h=$(sandbox)
cat > "$h/scorecard.md" <<'MD'
# Scorecard
| Metric | Value |
| --- | --- |
| Agent runs (all-time) | 129 |
| Proposal rate | 46% |
| Error runs (last 7d) | 0 (0 fail / 0 violation) |
| Approval rate | 71% |
| Record window | 2026-06-01 → 2026-08-07 |
MD
touch -d '30 days ago' "$h/scorecard.md"
rc=$(SCORECARD_DIGEST="$h/scorecard.md" DELIVERY_ROUTE=ops DELIVERY_JOB=scorecard.service \
     run_adapter "$h" deliver_scorecard.sh)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'a month-old digest still delivers' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'routed to ops' "argv '$h' | grep -q -- '--route ops'"
assert 'headline rows summarised' "argv '$h' | grep -q 'Proposal rate: 46%'"
assert 'the record window is carried' "argv '$h' | grep -q 'Record window: 2026-06-01'"
assert 'the digest itself is never attached' "! argv '$h' | grep -q -- '--file'"

echo '--- deliver_scorecard.sh: a missing digest is reported, not swallowed ---'
h=$(sandbox)
rc=$(SCORECARD_DIGEST="$h/absent.md" DELIVERY_ROUTE=ops run_adapter "$h" deliver_scorecard.sh)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'still delivers one line' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'says the rollup produced nothing' "argv '$h' | grep -q 'no digest'"

echo '--- deliver_proposal.sh reports the run record, not the agent prose ---'
# agent_run.log is a raw concatenation of attempt stdout with no run boundary in it, so
# only cost.log can say what THIS run did. The ten-day OpenRouter outage logged as a
# clean NOPROPOSAL, which is why an absent record has to be louder than a decline.
proposal_sandbox() {  # <sandbox> <ts> <outcome> <proposal>
  local h=$1
  printf 'ts=%s schema=3 profile=claude-opus model=unknown task=raw-ingest outcome=%s proposal=%s run_seconds=23 attempts=1\n' \
    "$2" "$3" "$4" > "$h/cost.log"
  touch -d '1 hour ago' "$h/marker"
}
run_proposal() {  # <sandbox> [extra env assignments are the caller's]
  local h=$1
  DELIVERY_TASK=raw-ingest DELIVERY_ROUTE=research DELIVERY_JOB=raw-ingest.service \
  DELIVERY_RUN_MARKER="$h/marker" AGENT_COST_LOG="$h/cost.log" \
  AGENT_RUN_LOG="$h/agent_run.log" run_adapter "$h" deliver_proposal.sh
}

h=$(sandbox)
proposal_sandbox "$h" "$(date -Is)" PROPOSAL raw-ingest
rc=$(run_proposal "$h")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'exactly one call' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'routed to research' "argv '$h' | grep -q -- '--route research'"
assert 'the proposal path is named' \
  "argv '$h' | grep -q \"proposed _inbox/agents/\$(date +%F)_raw-ingest.md\""
assert 'a status payload attaches nothing' "! argv '$h' | grep -q -- '--file'"

h=$(sandbox)
proposal_sandbox "$h" "$(date -Is)" NOPROPOSAL none
printf 'noise\nDECLINE: no unprocessed sources in 05_knowledge/raw/\n' > "$h/agent_run.log"
rc=$(run_proposal "$h")
assert 'a decline still delivers' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'the decline reason is quoted' "argv '$h' | grep -q 'NOPROPOSAL — no unprocessed sources'"

h=$(sandbox)
proposal_sandbox "$h" "$(date -Is)" NOPROPOSAL none
printf 'DECLINE: from a run that ended before this one started\n' > "$h/agent_run.log"
touch -d '2 hours ago' "$h/agent_run.log"
rc=$(run_proposal "$h")
assert 'a decline reason older than the marker is not attributed to this run' \
  "! argv '$h' | grep -q 'before this one started'"
assert 'and the outcome is still reported' "argv '$h' | grep -q 'NOPROPOSAL'"

echo '--- deliver_proposal.sh is loudest when the run wrote no record at all ---'
h=$(sandbox)
proposal_sandbox "$h" "$(date -Is -d '3 hours ago')" PROPOSAL raw-ingest
rc=$(run_proposal "$h")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'a record predating the marker is not read as this run' \
  "! argv '$h' | grep -q 'proposed _inbox'"
assert 'the gap is delivered, never swallowed' "argv '$h' | grep -q 'this run wrote no record'"

h=$(sandbox)
: > "$h/cost.log"
touch -d '1 hour ago' "$h/marker"
rc=$(run_proposal "$h")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'an absent record still delivers' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'it says the run ended before writing one' "argv '$h' | grep -q 'no run record for task raw-ingest'"

h=$(sandbox)
printf 'ts=%s schema=3 task=standing-research outcome=PROPOSAL proposal=standing-research run_seconds=9 attempts=1\n' \
  "$(date -Is)" > "$h/cost.log"
touch -d '1 hour ago' "$h/marker"
rc=$(run_proposal "$h")
assert "another job's record is never claimed as this task's" \
  "argv '$h' | grep -q 'no run record for task raw-ingest'"

echo '--- the content route always states what the duplicate-title gate was reading ---'
# published_corpus.py falls back to the last known ref when origin is unreachable, so a
# delivered draft proves nothing about whether the collision check could see the site.
# Both content adapters are stubbed off the network here; what is pinned is that the
# corpus and board lines reach the message at all.
probes() {  # probes <sandbox> <fetched:true|false> <board-json>
  local h=$1 d="$1/probes"
  mkdir -p "$d"
  cat > "$d/published_corpus.py" <<PY
print('{"freshness": {"fetched": $2, "ref_age_hours": 12.5}, "articles": []}')
PY
  printf '%s' "$3" > "$d/board.json"
  cat > "$d/notion_rest.py" <<'PY'
import os, sys
sys.stdout.write(open(os.path.join(os.path.dirname(__file__), "board.json")).read())
PY
  echo "$d"
}
board_rows() {  # board_rows <iso-stamp>
  printf '[{"id":"p1","angle":"Why cold-store grid capacity is the constraint","status":"Drafted","last_edited":"%s"}]' "$1"
}
run_content() {  # run_content <sandbox> <probe-dir>
  local h=$1 d=$2
  DELIVERY_TASK=augustus-content DELIVERY_ROUTE=content \
  DELIVERY_JOB=augustus-content.service DELIVERY_RUN_MARKER="$h/marker" \
  AGENT_COST_LOG="$h/cost.log" CONTENT_PROBE_DIR="$d" run_adapter "$h" deliver_content.sh
}

h=$(sandbox); d=$(probes "$h" true "$(board_rows "$(date -u -Is -d '10 minutes ago' | sed 's/+00:00/Z/')")")
printf 'ts=%s schema=3 task=augustus-content outcome=NOPROPOSAL proposal=none run_seconds=231 attempts=1\n' \
  "$(date -Is)" > "$h/cost.log"
touch -d '1 hour ago' "$h/marker"
rc=$(run_content "$h" "$d")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'exactly one call' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'routed to content' "argv '$h' | grep -q -- '--route content'"
assert 'corpus freshness is stated' "argv '$h' | grep -q 'corpus: fetched, tip age 12.5h'"
assert 'the changed board row is named' "argv '$h' | grep -q 'board: 1 row(s) changed'"
assert 'the run outcome rides along' "argv '$h' | grep -q 'run: NOPROPOSAL in 231s'"
assert 'no artifact is invented for a board-only job' "! argv '$h' | grep -q -- '--file'"

h=$(sandbox); d=$(probes "$h" false '[]')
printf 'ts=%s schema=3 task=augustus-content outcome=NOPROPOSAL proposal=none run_seconds=200 attempts=1\n' \
  "$(date -Is)" > "$h/cost.log"
touch -d '1 hour ago' "$h/marker"
rc=$(run_content "$h" "$d")
assert 'an offline corpus is reported as stale, never as fetched' \
  "argv '$h' | grep -q 'corpus: stale'"
assert 'a run that changed nothing says so' "argv '$h' | grep -q 'board: no rows changed'"

h=$(sandbox); d=$(probes "$h" true '[]')
printf 'ts=%s schema=3 task=augustus-content outcome=NOPROPOSAL proposal=none run_seconds=200 attempts=1\n' \
  "$(date -Is -d '3 hours ago')" > "$h/cost.log"
touch -d '1 hour ago' "$h/marker"
rc=$(run_content "$h" "$d")
assert 'a record predating the marker is reported as no record' "argv '$h' | grep -q 'run: NO RECORD'"
assert 'and the board and corpus are still reported' \
  "argv '$h' | grep -q 'board:' && argv '$h' | grep -q 'corpus:'"

h=$(sandbox); d=$(probes "$h" true '[]')
rm -f "$d/published_corpus.py"
: > "$h/cost.log"; touch -d '1 hour ago' "$h/marker"
rc=$(run_content "$h" "$d")
assert 'exits 0 when a probe itself is broken' "[ '$rc' = 0 ]"
assert 'a broken corpus probe is named, not silently omitted' \
  "argv '$h' | grep -q 'corpus: UNAVAILABLE'"

echo '--- content-change-dispatch: a quiet poll stays silent, every decision delivers ---'
# 96 ticks a day, almost all no-ops. A channel that reports each one stops being read,
# and the two ticks that mattered go with it.
run_dispatch() {  # run_dispatch <sandbox> <probe-dir>
  local h=$1 d=$2
  DELIVERY_ROUTE=content DELIVERY_JOB=content-change-dispatch.service \
  DELIVERY_RUN_MARKER="$h/marker" DISPATCH_LOG="$h/dispatch.log" \
  CONTENT_PROBE_DIR="$d" run_adapter "$h" deliver_dispatch.sh
}
dispatch_log() {  # dispatch_log <sandbox> <message>
  printf '%s content_change_dispatch: %s\n' "$(date -Is)" "$2" >> "$1/dispatch.log"
}

h=$(sandbox); d=$(probes "$h" true '[]')
touch -d '1 minute ago' "$h/marker"
dispatch_log "$h" 'no new Picked rows (0 currently Picked) — refreshing state, no dispatch'
rc=$(run_dispatch "$h" "$d")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'a quiet tick sends nothing' "[ \"\$(calls '$h')\" -eq 0 ]"

h=$(sandbox); d=$(probes "$h" true "$(board_rows "$(date -u -Is | sed 's/+00:00/Z/')")")
touch -d '1 minute ago' "$h/marker"
dispatch_log "$h" 'detected 1 new Picked row(s) — dispatching Augustus draft run via agent_propose.sh'
dispatch_log "$h" 'dispatch complete — state advanced to current Picked set (1 rows)'
rc=$(run_dispatch "$h" "$d")
assert 'a dispatch delivers exactly once' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'the decision is quoted' "argv '$h' | grep -q 'dispatch complete'"
assert 'the affected board row is named' "argv '$h' | grep -q 'board: 1 row(s) changed'"
assert 'corpus state rides along' "argv '$h' | grep -q 'corpus: fetched'"

h=$(sandbox); d=$(probes "$h" true '[]')
touch -d '1 minute ago' "$h/marker"
dispatch_log "$h" 'FAIL-SOFT: could not read/parse Picked rows from Notion — exiting 0, state unchanged'
rc=$(run_dispatch "$h" "$d")
assert 'a fail-soft Notion read is never mistaken for a quiet tick' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'and it says what failed' "argv '$h' | grep -q 'FAIL-SOFT'"

h=$(sandbox); d=$(probes "$h" true '[]')
touch -d '1 minute ago' "$h/marker"
printf '%s content_change_dispatch: no new Picked rows (0 currently Picked) — refreshing state, no dispatch\n' \
  "$(date -Is -d '20 minutes ago')" > "$h/dispatch.log"
rc=$(run_dispatch "$h" "$d")
assert 'a previous tick line is not read as this run' "[ \"\$(calls '$h')\" -eq 1 ]"
assert 'a poll that reached no decision is delivered, not swallowed' \
  "argv '$h' | grep -q 'never reached a decision'"

echo '--- the threshold is still configurable ---'
h=$(sandbox)
mkdir -p "$h/agent-worktrees/inbox/_inbox/agents"
: > "$h/agent-worktrees/inbox/_inbox/agents/old.md"
touch -d '3 days ago' "$h/agent-worktrees/inbox/_inbox/agents/old.md"
rc=$(INBOX_BACKLOG_THRESHOLD_DAYS=7 run_adapter "$h" inbox_backlog_alert.sh)
assert 'raised threshold suppresses the alert' "[ \"\$(calls '$h')\" -eq 0 ]"

exit $fail
