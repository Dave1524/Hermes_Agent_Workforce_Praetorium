#!/usr/bin/env bash
# m1-signal-scan on the Claude Code runtime (NUC-32 variant). W6: this workflow carried
# status = "standing" with neither `suite` nor `suite_exempt` from D6 until 2026-09-03.
#
# Offline by contract: a fixture HOME and a mock claude binary, never OpenRouter, never the
# real inbox worktree. The runner reads INBOX and TASK_FILE from $HOME with no env override,
# which sounds untestable and is the opposite — pointing HOME at a fixture relocates both.
#
# WHAT THIS JOB DOES THAT ITS SIBLINGS DO NOT: it runs with WebSearch and WebFetch in the
# allowlist. rhythm_test_lib.sh's shared smoke_suite() asserts their ABSENCE, so the obvious
# reuse is actively wrong for this file and would fail a correct runner. The distinction is
# inbound vs outbound: reading a public page is not an outward action, and the box's hard gate
# is outward ACTION — no email, no social, no messaging — backed by the fact that it holds no
# outward credential at all. A market scan that cannot read the market is not a scan. Pinned
# below so the next reader does not "fix" it into uselessness.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in the shared assert(): `yes` is
# still writing when `grep -q` exits, so this fails if and only if a condition is evaluated
# under pipefail. It lives in every caller because the assert it guards is shared — a single
# copy in the lib could not tell which suite had reintroduced the setting.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_m1_signal_scan_cc.sh"
TASK="$REPO_ROOT/profiles/m1_signal_scan_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/m1_signal_scan.env.example"

# The lib's make_mock_claude records argv only. This job's cwd is load-bearing: the task
# profile writes `_inbox/agents/<today>_m1-signal-scan.md` as a RELATIVE path, so a runner
# that launched the agent from the wrong directory would write the proposal somewhere the
# inbox tooling never looks, with no error anywhere.
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

# state -> fixture HOME. "complete" builds both paths the runner needs; each other state
# removes exactly one, so the two preconditions are proven separately.
make_m1_home() {
  local state=$1 home
  home=$(mktemp -d)
  [ "$state" = no_task ]  || { mkdir -p "$home/agent-workforce/profiles"
                               cp "$TASK" "$home/agent-workforce/profiles/m1_signal_scan_cc_task.md"; }
  [ "$state" = no_inbox ] || mkdir -p "$home/agent-worktrees/inbox/_inbox/agents"
  # `-r`, not `-f`: a present-but-unreadable profile (a bad chmod, a half-copied deploy)
  # feeds cat(1) the same failure and the agent the same empty prompt as an absent one, so
  # the guard is proven against both. `||` form, not `&&`: under `set -e` a trailing-false
  # `&&` list would abort the builder for every other state.
  [ "$state" != unreadable ] || chmod 000 "$home/agent-workforce/profiles/m1_signal_scan_cc_task.md"
  echo "$home"
}

run_m1() { # home -> rc
  local home=$1 claude rc=0
  claude=$(mock_claude_recording_pwd "$home")
  HOME="$home" CLAUDE_BIN="$claude" bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- m1-signal-scan: the env override parses and wires the CC runner ---"
assert 'env.example exists' "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
owner=$(env_value "$ENV_EXAMPLE" AGENT_OWNER)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
mode=$(env_value "$ENV_EXAMPLE" AGENT_RUN_MODE)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert 'AGENT_TASK_SLUG=m1-signal-scan' "[ '$slug' = m1-signal-scan ]"
assert 'AGENT_OWNER=claudius, matching design/agents/claudius.toml' "[ '$owner' = claudius ]"
assert 'AGENT_PROFILE names the RUNTIME (claude-sonnet), not the owner persona (W1)' \
  "[ '$profile' = claude-sonnet ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert 'AGENT_RUNTIME_CMD resolves to an executable script' "[ -x '$resolved' ]"
assert 'and points at the CC runner, not the retired hermes/OpenRouter line' \
  "[[ '$runtime' == *run_m1_signal_scan_cc.sh* ]] && [[ '$runtime' != *hermes* ]]"
# NOT ops mode, and the distinction is this job's entire delivery path. ops mode skips the
# inbox worktree and the proposal commit; a proposal file is m1's only output, so an ops-mode
# override would run it "successfully" and commit nothing, every Monday and Wednesday.
assert 'AGENT_RUN_MODE is NOT ops — the proposal path is this job entire output' \
  "[ '$mode' != ops ]"

echo "--- m1-signal-scan: AGENT_VERIFY_CMD closes the second layer of W15 ---"
# Layer two of the W15 fail-open, wired 2026-09-03. With no AGENT_VERIFY_CMD,
# bin/agent_propose.sh:331 skips the artifact check entirely and a run that produced nothing
# lands on line 440 as `OK: run completed, agent produced no proposal` — exit 0, and no
# operator can tell it from a genuine "no signals at quality". The three research siblings
# have carried this wiring since 2026-07-30; m1 never had one.
verify_resolved="${verify/#\~\/agent-workforce/$REPO_ROOT}"
assert 'AGENT_VERIFY_CMD wires the shared de-silencing helper, under this job own slug' \
  "[[ '$verify' == *'proposal_or_decline.sh m1-signal-scan'* ]]"
assert 'and resolves to an executable script' "[ -x '${verify_resolved%% *}' ]"
# Behaviour, not wording: the two halves of the fix are ONE change, so this runs the real
# helper the way agent_propose.sh does (bash -lc) against both decline shapes. The profile's
# sentinel must pass and the wording it REPLACED must fail — wiring the verify command while
# the profile still said "print one line saying why" would have turned every legitimate
# no-signal Monday and Wednesday into a hard FAIL.
sandbox=$(mktemp -d)
mkdir -p "$sandbox/agent-worktrees/inbox/_inbox/agents" "$sandbox/agent-workforce/logs"
run_verify() { # log-tail -> rc, or 127 when nothing is wired
  local rc=0
  # An empty AGENT_VERIFY_CMD makes `bash -lc ""` exit 0, which would let an UNWIRED job pass
  # the accept-a-DECLINE assertion below — a check that cannot fail. Fail closed instead.
  [ -n "$verify_resolved" ] || { echo 127; return 0; }
  printf 'an earlier line from the run\n%s\n' "$1" > "$sandbox/agent-workforce/logs/agent_run.log"
  HOME="$sandbox" RUN_DATE="$(date +%F)" AGENT_RUN_STARTED_AT="$(date +%s)" \
    bash -lc "$verify_resolved" >/dev/null 2>&1 || rc=$?
  echo "$rc"
}
rc=$(run_verify 'DECLINE: no second-order signals at quality today')
assert 'the DECLINE: sentinel the task profile now prints is accepted' "[ '$rc' = 0 ]"
rc=$(run_verify 'No second-order signals at quality today.')
assert 'and the prose decline it replaced is NOT — the two halves land together or not at all' \
  "[ '$rc' != 0 ]"

echo "--- m1-signal-scan: refuses when it has nowhere to write ---"
home=$(make_m1_home no_inbox)
rc=$(run_m1 "$home")
assert 'a missing inbox worktree exits non-zero' "[ '$rc' != 0 ]"
assert 'and the agent is never launched with nowhere to write' "[ ! -f '$home/claude_argv.log' ]"

echo "--- m1-signal-scan: refuses when it has no mission to run ---"
# W15, fixed 2026-09-03 — these three assertions pinned the DEFECT until this branch and now
# pin the refusal. What they used to certify: `exec claude -p "$(cat "$TASK_FILE")"` puts the
# failing `cat` inside a command substitution used as an ARGUMENT, and `set -e` does not
# propagate that, so the substitution yielded the empty string, the agent was launched with an
# EMPTY PROMPT, and the runner exited 0.
#
# It was a two-layer fail-open and the second layer is why it stayed silent: this job set no
# AGENT_VERIFY_CMD, so bin/agent_propose.sh:331 skipped the artifact check entirely and an
# empty-prompt run landed on line 440 as `OK: run completed, agent produced no proposal` —
# NOPROPOSAL, exit 0, indistinguishable from a real "nothing to report". That is verbatim the
# class the same file's line 278 comment says cost 20 consecutive runs.
#
# The fix is bin/run_m1_signal_scan_cc.sh:23 — an explicit `[ -r "$TASK_FILE" ]` BEFORE the
# substitution, the shape bin/run_overnight_morning_report_cc.sh:30 has always had. Layer two
# is wired in profiles/m1_signal_scan.env.example and asserted in the env group above; it
# reaches the runtime only when Dave installs the live .env, so the guard below is the half a
# deploy can deliver on its own.
home=$(make_m1_home no_task)
rc=$(run_m1 "$home")
assert 'a missing task file exits non-zero — no empty prompt, no NOPROPOSAL' "[ '$rc' != 0 ]"
assert 'names the path in the journal (an alert with no path is a second search)' \
  "grep -q 'm1-signal-scan: task file not readable' '$home/run.log'"
assert 'and the agent is never launched without its mission' "[ ! -f '$home/claude_argv.log' ]"

home=$(make_m1_home unreadable)
rc=$(run_m1 "$home")
assert 'a PRESENT but unreadable task file also refuses (-r, not -f)' "[ '$rc' != 0 ]"
assert 'and the agent is never launched' "[ ! -f '$home/claude_argv.log' ]"

echo "--- m1-signal-scan: a complete fixture launches the agent correctly ---"
home=$(make_m1_home complete)
rc=$(run_m1 "$home")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the prompt is the task file, not an empty string (the W15 positive control)' \
  "[ \"\$(sed -n 1p '$home/claude_argv.log')\" = '-p' ] && [ -n \"\$(sed -n 2p '$home/claude_argv.log')\" ]"
assert 'launches the agent with the M1 mission prompt' \
  "grep -qF 'Standing task: M1 — Market Signal Scan' '$home/claude_argv.log'"
assert 'on sonnet, the model design/agents/claudius.toml declares' \
  "grep -qx -- '--model' '$home/claude_argv.log' && grep -qx 'sonnet' '$home/claude_argv.log'"
assert 'no MCP servers (strict, empty config)' \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
# cwd, not a flag: the profile writes `_inbox/agents/<today>_m1-signal-scan.md` relative.
assert 'and from the inbox worktree, which is what makes the relative write land' \
  "[ \"\$(cat '$home/claude_pwd.log')\" = \"\$(cd '$home/agent-worktrees/inbox' && pwd -P)\" ]"

echo "--- m1-signal-scan: web READS are allowed here, and that is not a leak ---"
# The inverse of rhythm_test_lib.sh's smoke_suite(). Read this file's header before changing it.
assert 'WebSearch and WebFetch ARE in the allowlist — a scan that cannot read is not a scan' \
  "grep -qx 'Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch' '$home/claude_argv.log'"
assert 'and the profile still forbids outward ACTION, which is the gate that matters' \
  "grep -qF 'no Notion sharing, no outbound' '$TASK'"

echo "--- m1-signal-scan: the task profile keeps its write boundary and idempotency ---"
assert 'task profile exists' "[ -f '$TASK' ]"
# The guard is a SAME-DAY retry check and deliberately not a weekly skip: the job moved to
# twice weekly (Mon+Wed), so a 7-day guard would silently drop every Wednesday run while
# reporting success. Both halves asserted — the presence of one and the exclusion of the other.
assert 'the idempotency guard is same-day' \
  "grep -q 'STEP 0 — Idempotency' '$TASK' && grep -qF 'date +%F' '$TASK'"
assert 'and explicitly NOT a weekly skip (Wednesday would vanish silently)' \
  "grep -qF 'NOT a weekly-skip' '$TASK'"
assert 'it writes exactly ONE proposal, under _inbox/agents/' \
  "grep -qF 'Write exactly ONE proposal file' '$TASK'"
# The wording half of W15. The siblings have always been explicit —
# profiles/standing_research_cc_task.md:41, raw_ingest_cc_task.md:24,
# bd_followup_drafts_cc_task.md:120 — while this profile said only "print one line saying
# why", which decline_sentinel() cannot match. Asserted as a literal because the string IS
# the contract with bin/proposal_or_decline.sh, not a stylistic preference.
assert 'and declines with the literal DECLINE: sentinel, not prose (W15)' \
  "grep -qF 'print exactly \`DECLINE: <short reason>\`' '$TASK'"
assert 'and is told to touch nothing outside that directory' \
  "grep -qF 'Do NOT touch any file outside' '$TASK'"

exit $fail
