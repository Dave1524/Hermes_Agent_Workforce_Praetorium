#!/usr/bin/env bash
# BD follow-up draft pack (2026-07-30) — the job turns Dave-owed BD next actions into
# copy-paste-ready drafts. Offline by contract: throwaway git fixtures and a mock claude
# binary, never ~/vault, never a real remote, never a live Notion call.
#
# The case that matters is the no-elapsed-time-claim rule: pipeline `Last contact` is
# known-unreliable (outbound email/LinkedIn leaves no trace on this box), so a draft that
# asserts silence is a confident wrong artifact sent to a real client. The mechanism lives
# in the task profile, so the profile is what this test asserts against.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/rhythm_test_lib.sh
. "$TESTS_DIR/rhythm_test_lib.sh"

RUNNER="$REPO_ROOT/bin/run_bd_followup_drafts_cc.sh"
TASK="$REPO_ROOT/profiles/bd_followup_drafts_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/bd_followup_drafts.env.example"
SERVICE="$REPO_ROOT/systemd/bd-followup-drafts.service"
TIMER="$REPO_ROOT/systemd/bd-followup-drafts.timer"

run_drafts() {
  local state=$1 home=$2 root
  root=$(make_vault_fixture "$state")
  local claude; claude=$(make_mock_claude "$home")
  mkdir -p "$home/inbox/_inbox/agents"
  rc=0
  HOME="$home" CLAUDE_BIN="$claude" VAULT_DIR="$root/vault" VAULT_SYNC_GUARD="$GUARD" \
    BD_FOLLOWUP_INBOX="$home/inbox" BD_FOLLOWUP_TASK="$TASK" \
    bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- bd-followup-drafts: the env override parses and wires the CC runner ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert "AGENT_TASK_SLUG=bd-followup-drafts" "[ '$slug' = bd-followup-drafts ]"
assert "AGENT_PROFILE is the Claude Code runtime" "[ '$profile' = claude-opus ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"
assert "and points at run_bd_followup_drafts_cc.sh" "[[ '$runtime' == *run_bd_followup_drafts_cc.sh* ]]"
assert "no hermes/OpenRouter invocation survives" "! grep -qE '^AGENT_RUNTIME_CMD=.*hermes' '$ENV_EXAMPLE'"
assert "AGENT_VERIFY_CMD wires the shared de-silencing helper" \
  "[[ '$verify' == *'proposal_or_decline.sh bd-followup-drafts'* ]]"

echo "--- bd-followup-drafts: refuses to draft off a stale mirror ---"
home=$(mktemp -d)
rc=$(run_drafts stale_behind "$home")
assert "exits non-zero on a 5-day-stale mirror" "[ '$rc' != 0 ]"
assert "says REFUSING (so the journal explains the alert)" "grep -q 'REFUSING' '$home/run.log'"
assert "the agent is never launched on stale data" "[ ! -f '$home/claude_argv.log' ]"

echo "--- bd-followup-drafts: runs on a current mirror ---"
home=$(mktemp -d)
rc=$(run_drafts clean_current "$home")
assert "exits 0" "[ '$rc' = 0 ]"
assert "launches the agent with the bd-followup-drafts task prompt" \
  "grep -qF 'BD Follow-up Draft Pack' '$home/claude_argv.log'"
assert "pins the full Opus 5 model name (an 'opus' alias silently rolls forward)" \
  "grep -qx 'claude-opus-5' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "no web tools in the allowlist (drafts ground in the vault, never the open web)" \
  "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"

echo "--- bd-followup-drafts: the task profile encodes the whole mechanism ---"
assert "task profile exists" "[ -f '$TASK' ]"
assert "input source 1 — the previous night's stall radar pack" \
  "grep -q '_bd-stall-radar.md' '$TASK'"
assert "input source 2 — the Client Pipeline data source, rows whose Next action date passed" \
  "grep -q 'e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e' '$TASK' && grep -q 'Next action date' '$TASK'"
assert "input source 3 — the Task Inbox data source, BD-scoped and due" \
  "grep -q '4dbb4389-6c4a-4f57-b70f-10d899483c21' '$TASK' && grep -q 'Due date' '$TASK'"
assert "the Stage guard names both terminal states" \
  "grep -q 'Closed' '$TASK' && grep -q 'On Hold' '$TASK'"
assert "the suppression guard reads parked/counterparty-owned tracks from current_priorities.md" \
  "grep -q 'current_priorities.md' '$TASK' && grep -qi 'parked' '$TASK'"
assert "no draft may assert silence, non-response or elapsed time" \
  "grep -qi 'elapsed time' '$TASK' && grep -qi 'never assert' '$TASK'"
assert "and names the Last contact unreliability as the reason" \
  "grep -q 'Last contact' '$TASK' && grep -qi 'unreliable' '$TASK'"
assert "the Unverified escape hatch is defined (a loud refusal beats a confident opener)" \
  "grep -q 'Unverified:' '$TASK'"
assert "every draft closes on a concrete ask — a named next step with a date and/or people" \
  "grep -qi 'concrete ask' '$TASK'"
assert "and 'stay in touch' is explicitly rejected" "grep -q 'stay in touch' '$TASK'"
assert "the Locale switch drafts nl rows in Dutch" \
  "grep -q 'Locale' '$TASK' && grep -q 'Dutch' '$TASK'"
# Locale is populated on 1 of 80 pipeline rows (verified 2026-07-30), so the empty case is
# the normal case — an unspecified fallback means English DMs to Dutch operators.
assert "an empty Locale infers from evidence rather than defaulting silently" \
  "grep -qi 'when it is EMPTY' '$TASK' && grep -qi 'never silently default to English' '$TASK'"
assert "and the inference basis is named in the draft block, so Dave can overrule it" \
  "grep -qi 'name the basis' '$TASK'"
assert "channel selection: Email present -> email with a subject line, otherwise LinkedIn" \
  "grep -q 'subject line' '$TASK' && grep -q 'LinkedIn' '$TASK'"
assert "a LinkedIn connection note is budgeted at 300 characters" "grep -q '300 character' '$TASK'"
assert "the pack is capped at 5 drafts" "grep -qi 'at most 5 drafts\|maximum of 5 drafts' '$TASK'"
assert "and nothing dropped by the cap is silently truncated" \
  "grep -qi 'never silently truncate\|no silent truncation' '$TASK'"
assert "ranked by revenue proximity before the cap applies" \
  "grep -qi 'Proposal/Active' '$TASK' && grep -qi 'rank' '$TASK'"
assert "carry-forward de-dup against the previous pack (no daily nag file)" \
  "grep -q 'carried (unchanged from' '$TASK'"
assert "never writes Notion pipeline state" "grep -qi 'never write.*Notion\|NEVER update any Notion' '$TASK'"
assert "never acts outward (the box holds no outward credential)" \
  "grep -qi 'never act outward' '$TASK'"
assert "emits the DECLINE: sentinel when nothing is owed" \
  "grep -q 'DECLINE: no Dave-owed BD next action today' '$TASK'"
assert "Notion is reached over REST only — the MCP is removed box-wide" \
  "grep -q 'api.notion.com/v1/data_sources' '$TASK' && ! grep -qE 'mcp__[A-Za-z_]*[Nn]otion|notion-query-data-sources' '$TASK'"
assert "the pack is send material, never promoted into the vault" \
  "grep -q 'target: none' '$TASK'"

echo "--- bd-followup-drafts: the units wire the shared runner and the delivery path ---"
assert "service exists" "[ -f '$SERVICE' ]"
assert "AGENT_JOB_OVERRIDES points at bd_followup_drafts.env" \
  "grep -q '^Environment=AGENT_JOB_OVERRIDES=.*bd_followup_drafts.env$' '$SERVICE'"
assert "ExecStart is the shared agent_propose.sh runner" \
  "grep -q '^ExecStart=/home/dave/agent-workforce/bin/agent_propose.sh$' '$SERVICE'"
assert "ExecStartPost delivers the pack via the shared reporter" \
  "grep -q '^ExecStartPost=/home/dave/agent-workforce/bin/deliver_report.sh$' '$SERVICE'"
assert "REPORT_GLOB matches this job's pack, not another job's report" \
  "grep -q '^Environment=REPORT_GLOB=\*_bd-followup-drafts.md$' '$SERVICE'"
assert "REPORT_DIR is the inbox agents directory" \
  "grep -q '^Environment=REPORT_DIR=/home/dave/agent-worktrees/inbox/_inbox/agents$' '$SERVICE'"
# systemd splits an unquoted Environment= line on whitespace, so
# `Environment=REPORT_SUBJECT=[Praetorium] BD follow-up drafts` silently becomes
# `[Praetorium]` and drops the rest (caught by systemd-analyze verify, 2026-07-27).
unquoted=$(grep -E '^Environment=[^"]*=[^"]* ' "$SERVICE" || true)
assert "no unquoted multi-word Environment= value" "[ -z '$unquoted' ]"

assert "timer exists" "[ -f '$TIMER' ]"
assert "runs Sun-Thu 23:30, mirroring the radar's cadence one slot later" \
  "grep -q '^OnCalendar=Sun,Mon,Tue,Wed,Thu 23:30$' '$TIMER'"
assert "Persistent (a reboot spanning the slot still catches up)" "grep -q '^Persistent=true' '$TIMER'"
assert "enabled into timers.target" "grep -q '^WantedBy=timers.target' '$TIMER'"

# 23:00 radar -> 23:30 drafts: the pack consumes that night's fresh radar output, and both
# clear the 04:30/05:30/06:00 morning jobs sharing agent_propose.sh's global flock (a
# collision there is a SILENT "SKIP: previous run still active").
radar_at=$(grep -oE 'OnCalendar=.*[0-9]{2}:[0-9]{2}' "$REPO_ROOT/systemd/bd-stall-radar.timer" | grep -oE '[0-9]{2}:[0-9]{2}')
drafts_at=$(grep -oE 'OnCalendar=.*[0-9]{2}:[0-9]{2}' "$TIMER" | grep -oE '[0-9]{2}:[0-9]{2}')
assert "the radar ($radar_at) runs before the draft pack ($drafts_at)" "[[ '$radar_at' < '$drafts_at' ]]"
assert "and the service is ordered after it" "grep -q '^After=.*bd-stall-radar.service' '$SERVICE'"

exit $fail
