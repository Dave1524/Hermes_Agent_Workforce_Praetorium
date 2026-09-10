#!/usr/bin/env bash
# bd-stall-radar on the Claude Code runtime (T2.3). Offline by contract: a fixture HOME
# and a mock claude binary, never Notion, never the real inbox worktree, never OpenRouter.
#
# The kernel (bin/bd_stall_radar_kernel.py) is the stall detector; this suite asserts the
# harness around it — env wiring, the runner's refusal/launch shape, the task's guards,
# and the unit files. It does not run the kernel and does not talk to the live box.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_bd_stall_radar_cc.sh"
TASK="$REPO_ROOT/profiles/bd_stall_radar_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/bd_stall_radar.env.example"
KERNEL="$REPO_ROOT/bin/bd_stall_radar_kernel.py"
SERVICE="$REPO_ROOT/systemd/bd-stall-radar.service"
TIMER="$REPO_ROOT/systemd/bd-stall-radar.timer"

mock_claude_recording_pwd() {
  local home=$1
  cat > "$home/claude" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$home/claude_argv.log"
pwd > "$home/claude_pwd.log"
exit 0
EOF
  chmod +x "$home/claude"
  echo "$home/claude"
}

make_radar_home() {
  local state=$1 home
  home=$(mktemp -d)
  [ "$state" = no_task ]  || { mkdir -p "$home/agent-workforce/profiles"
                               cp "$TASK" "$home/agent-workforce/profiles/bd_stall_radar_task.md"; }
  [ "$state" = no_inbox ] || mkdir -p "$home/agent-worktrees/inbox/_inbox/agents"
  make_skills_fixture "$home" claudius >/dev/null
  [ "$state" != unreadable ] || chmod 000 "$home/agent-workforce/profiles/bd_stall_radar_task.md"
  echo "$home"
}

run_radar() {
  local home=$1 claude rc=0
  claude=$(mock_claude_recording_pwd "$home")
  HOME="$home" CLAUDE_BIN="$claude" bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- bd-stall-radar: the env override parses and wires the CC runner ---"
assert 'env.example exists' "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
owner=$(env_value "$ENV_EXAMPLE" AGENT_OWNER)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
mcp_deps=$(env_value "$ENV_EXAMPLE" AGENT_MCP_DEPS)
assert 'AGENT_TASK_SLUG=bd-stall-radar' "[ '$slug' = bd-stall-radar ]"
assert 'AGENT_OWNER=claudius, matching design/agents/claudius.toml' "[ '$owner' = claudius ]"
assert 'AGENT_PROFILE names the RUNTIME (claude-sonnet), not the owner persona (W1)' \
  "[ '$profile' = claude-sonnet ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert 'AGENT_RUNTIME_CMD resolves to an executable script' "[ -x '$resolved' ]"
assert 'and points at the CC runner, not the kernel or hermes' \
  "[[ '$runtime' == *run_bd_stall_radar_cc.sh* ]] && [[ '$runtime' != *hermes* ]] && [[ '$runtime' != *bd_stall_radar_kernel.py* ]]"
assert 'AGENT_MCP_DEPS=none' "[ '$mcp_deps' = none ]"

echo "--- bd-stall-radar: AGENT_VERIFY_CMD closes the W15 silent-NOPROPOSAL hole ---"
verify_resolved="${verify/#\~\/agent-workforce/$REPO_ROOT}"
assert 'AGENT_VERIFY_CMD wires the shared de-silencing helper, under this job own slug' \
  "[[ '$verify' == *'proposal_or_decline.sh bd-stall-radar'* ]]"
assert 'and resolves to an executable script' "[ -x '${verify_resolved%% *}' ]"
sandbox=$(mktemp -d)
mkdir -p "$sandbox/agent-worktrees/inbox/_inbox/agents" "$sandbox/agent-workforce/logs"
run_verify() {
  local rc=0
  [ -n "$verify_resolved" ] || { echo 127; return 0; }
  # T7.1: the sentinel is read from THIS run's own output, at the per-task path
  # agent_propose.sh writes — never from the shared agent_run.log, where any job's decline
  # used to satisfy every other job's check. Left unexported on purpose so the slug-derived
  # default is what gets exercised, since that is what a hand invocation resolves.
  local slug started log
  slug=${verify_resolved##* }
  started=$(date +%s)
  log="$sandbox/agent-workforce/logs/last-attempt/$slug.log"
  mkdir -p "$(dirname "$log")"
  printf 'an earlier line from the run\n%s\n' "$1" > "$log"
  touch -d "@$((started + 1))" "$log"
  HOME="$sandbox" RUN_DATE="$(date +%F)" AGENT_RUN_STARTED_AT="$started" \
    bash -lc "$verify_resolved" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
rc=$(run_verify 'DECLINE: no genuine new stalls, no proposal written')
assert 'the DECLINE: sentinel the kernel prints is accepted' "[ '$rc' = 0 ]"
rc=$(run_verify '=> clean decline: no genuine new stalls, no proposal written')
assert 'and the prose decline it replaced is NOT' "[ '$rc' != 0 ]"

echo "--- bd-stall-radar: refuses when it has nowhere to write ---"
home=$(make_radar_home no_inbox)
rc=$(run_radar "$home")
assert 'a missing inbox worktree exits non-zero' "[ '$rc' != 0 ]"
assert 'and the agent is never launched with nowhere to write' "[ ! -f '$home/claude_argv.log' ]"

echo "--- bd-stall-radar: refuses when it has no mission to run ---"
home=$(make_radar_home no_task)
rc=$(run_radar "$home")
assert 'a missing task file exits non-zero — no empty prompt, no NOPROPOSAL' "[ '$rc' != 0 ]"
assert 'names the path in the journal (an alert with no path is a second search)' \
  "grep -q 'bd-stall-radar: task file not readable' '$home/run.log'"
assert 'and the agent is never launched without its mission' "[ ! -f '$home/claude_argv.log' ]"

home=$(make_radar_home unreadable)
rc=$(run_radar "$home")
assert 'a PRESENT but unreadable task file also refuses (-r, not -f)' "[ '$rc' != 0 ]"
assert 'and the agent is never launched' "[ ! -f '$home/claude_argv.log' ]"

echo "--- bd-stall-radar: a complete fixture launches the agent correctly ---"
home=$(make_radar_home complete)
rc=$(run_radar "$home")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the prompt is the task file, not an empty string (the W15 positive control)' \
  "[ \"\$(sed -n 1p '$home/claude_argv.log')\" = '-p' ] && [ -n \"\$(sed -n 2p '$home/claude_argv.log')\" ]"
assert 'launches the agent with the radar mission prompt' \
  "grep -qF 'Standing task: BD Pipeline Stall Radar' '$home/claude_argv.log'"
assert 'on claude-sonnet-5, the model design/agents/claudius.toml declares' \
  "grep -qx -- '--model' '$home/claude_argv.log' && grep -qx 'claude-sonnet-5' '$home/claude_argv.log'"
assert 'permission-mode is dontAsk (T2.2), not bypass' \
  "grep -qx -- '--permission-mode' '$home/claude_argv.log' && grep -qx 'dontAsk' '$home/claude_argv.log' && ! grep -q bypassPermissions '$home/claude_argv.log'"
assert 'no MCP servers (strict, empty config)' \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert 'no web tools in the allowlist (radar flags inward; kernel does Notion REST)' \
  "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"
assert 'and from the inbox worktree, which is what makes the relative write land' \
  "[ \"\$(cat '$home/claude_pwd.log')\" = \"\$(cd '$home/agent-worktrees/inbox' && pwd -P)\" ]"
assert "offers claudius's pointer-skill tree by explicit path, not ~/.claude/skills (T3.1)" \
  "grep -qx -- '--plugin-dir' '$home/claude_argv.log' && grep -qx '$home/agent-workforce/skills/claudius' '$home/claude_argv.log'"

echo "--- bd-stall-radar: the task points at the kernel and keeps its guards ---"
assert 'task profile exists' "[ -f '$TASK' ]"
assert 'kernel exists' "[ -f '$KERNEL' ]"
assert 'the task names the kernel rather than reimplementing stall rules' \
  "grep -q 'bd_stall_radar_kernel.py' '$TASK'"
assert 'qmd MCP is not the priorities path — disk read of current_priorities.md is named' \
  "grep -q 'current_priorities.md' '$TASK' && grep -q '~/vault/04_operations/current_priorities.md' '$TASK' && ! grep -q 'use the qmd tool' '$TASK'"
assert 'the Stage guard names both terminal states' \
  "grep -q 'Closed' '$TASK' && grep -q 'On Hold' '$TASK'"
assert 'never writes Notion pipeline state' \
  "grep -qi 'Do NOT update any Notion' '$TASK'"
assert 'never acts outward' \
  "grep -qi 'Never act outward' '$TASK'"
assert 'declines with the literal DECLINE: sentinel, not prose (W15)' \
  "grep -qF 'DECLINE:' '$TASK'"
assert 'and does not call the Hermes memory tool (missing under CC / dontAsk)' \
  "! grep -qE 'memory tool|action=add' '$TASK'"

echo "--- bd-stall-radar: the kernel prints the sentinel proposal_or_decline.sh accepts ---"
assert 'kernel prints ^DECLINE: on a clean decline' \
  "grep -qF 'print(\"DECLINE:' '$KERNEL'"

echo "--- bd-stall-radar: the units wire the shared runner and stay a file-level claim ---"
assert 'service exists' "[ -f '$SERVICE' ]"
assert 'AGENT_JOB_OVERRIDES points at bd_stall_radar.env' \
  "grep -q '^Environment=AGENT_JOB_OVERRIDES=.*bd_stall_radar.env$' '$SERVICE'"
assert 'ExecStart is the shared agent_propose.sh runner' \
  "grep -q '^ExecStart=/home/dave/agent-workforce/bin/agent_propose.sh$' '$SERVICE'"
assert 'OnFailure is wired' "grep -q '^OnFailure=agent-alert@%n.service$' '$SERVICE'"
unquoted=$(grep -E '^Environment=[^"]*=[^"]* ' "$SERVICE" || true)
assert 'no unquoted multi-word Environment= value' "[ -z '$unquoted' ]"
assert 'timer exists' "[ -f '$TIMER' ]"
assert 'runs Sun-Thu 23:00' "grep -q '^OnCalendar=Sun,Mon,Tue,Wed,Thu 23:00$' '$TIMER'"
assert 'Persistent (a reboot spanning the slot still catches up)' "grep -q '^Persistent=true' '$TIMER'"
assert 'enabled into timers.target' "grep -q '^WantedBy=timers.target' '$TIMER'"

exit $fail
