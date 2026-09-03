#!/usr/bin/env bash
# overnight-morning-report (NUC-36), Claude Code runtime variant. W6: this workflow carried
# status = "standing" with neither `suite` nor `suite_exempt` from D6 until 2026-09-03.
#
# Offline by contract: fixture HOMEs, a mock claude, and a stub systemctl on PATH. Nothing
# here queries the live box, and nothing writes ~/logs/overnight.
#
# THE HIGHEST-VALUE HALF IS AT THE BOTTOM. This job's task profile embeds a bash block that
# enumerates the fleet from config/fleet-units.tsv, and that block is PROSE — markdown in a
# file, executed by an agent at 06:20 and by nothing else, ever. It is the repaired version of
# the defect that left eight standing units invisible to six different reports. The group
# "the timer-enumeration block is executable, and executed" extracts it and RUNS it against
# fixtures, because a repair nobody can run is a repair nobody can check.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in the shared assert(): `yes` is
# still writing when `grep -q` exits, so this fails if and only if a condition is evaluated
# under pipefail. It lives in every caller because the assert it guards is shared.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_overnight_morning_report_cc.sh"
TASK="$REPO_ROOT/profiles/overnight_morning_report_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/overnight_morning_report.env.example"

# Mock claude that records argv, cwd, AND writes a file — the umask assertion below needs a
# real artifact, because `umask 077` is inherited across exec and is otherwise unobservable.
mock_claude_writing_artifact() {
  local home=$1
  cat > "$home/claude" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$home/claude_argv.log"
pwd > "$home/claude_pwd.log"
printf 'report\n' > "$home/logs/overnight/morning-report-fixture.md"
exit 0
EOF
  chmod +x "$home/claude"
  echo "$home/claude"
}

# state -> fixture HOME holding the task file at the path the runner derives from WORKDIR.
make_mr_home() {
  local state=$1 home
  home=$(mktemp -d)
  mkdir -p "$home/agent-workforce/profiles"
  case "$state" in
    no_task)   : ;;
    unreadable) cp "$TASK" "$home/agent-workforce/profiles/overnight_morning_report_cc_task.md"
                chmod 000 "$home/agent-workforce/profiles/overnight_morning_report_cc_task.md" ;;
    *)         cp "$TASK" "$home/agent-workforce/profiles/overnight_morning_report_cc_task.md" ;;
  esac
  echo "$home"
}

run_mr() { # home [extra env assignments...] -> rc
  local home=$1; shift
  local claude rc=0
  claude=$(mock_claude_writing_artifact "$home")
  env HOME="$home" CLAUDE_BIN="$claude" "$@" bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- overnight-morning-report: the env override parses and wires the CC runner ---"
assert 'env.example exists' "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
owner=$(env_value "$ENV_EXAMPLE" AGENT_OWNER)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
mode=$(env_value "$ENV_EXAMPLE" AGENT_RUN_MODE)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert 'AGENT_TASK_SLUG=overnight-morning-report' "[ '$slug' = overnight-morning-report ]"
assert 'AGENT_OWNER=marcus, matching design/agents/marcus.toml' "[ '$owner' = marcus ]"
assert 'AGENT_PROFILE names the RUNTIME (claude-sonnet), not the owner persona (W1)' \
  "[ '$profile' = claude-sonnet ]"
# ops mode is correct HERE and wrong for m1: this job's artifact is the report file itself,
# so there is no inbox worktree to check out and no proposal to commit.
assert 'AGENT_RUN_MODE=ops — the artifact is the report file, not a proposal' "[ '$mode' = ops ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert 'AGENT_RUNTIME_CMD resolves to an executable script' "[ -x '$resolved' ]"
assert 'and points at the CC runner, not the retired hermes/OpenRouter line' \
  "[[ '$runtime' == *run_overnight_morning_report_cc.sh* ]] && [[ '$runtime' != *hermes* ]]"

echo "--- overnight-morning-report: AGENT_VERIFY_CMD only accepts THIS run's artifact ---"
# Without it, exit 0 is the whole evidence — and the runtime exits 0 when a provider error
# becomes the agent's final response. deliver_report.sh would then re-post yesterday's file
# for up to 26h with nothing anywhere recording that today's was never written.
assert 'AGENT_VERIFY_CMD is set (exit 0 is not evidence)' "[ -n '$verify' ]"
assert 'and is anchored to AGENT_RUN_STARTED_AT, not to mere existence' \
  "[[ '$verify' == *AGENT_RUN_STARTED_AT* ]]"
sandbox=$(mktemp -d); mkdir -p "$sandbox/logs/overnight"
started=$(date +%s)
touch -d '2 hours ago' "$sandbox/logs/overnight/morning-report-2026-09-02.md"
rc=0
HOME="$sandbox" AGENT_RUN_STARTED_AT="$started" bash -lc "$verify" >/dev/null 2>&1 || rc=$?
assert "yesterday's surviving report does NOT pass" "[ '$rc' != 0 ]"
touch "$sandbox/logs/overnight/morning-report-2026-09-03.md"
rc=0
HOME="$sandbox" AGENT_RUN_STARTED_AT="$started" bash -lc "$verify" >/dev/null 2>&1 || rc=$?
assert 'a report written by this run DOES pass' "[ '$rc' = 0 ]"
# The seam, asserted rather than assumed. This AGENT_VERIFY_CMD ends in `find ... | grep -q .`
# — an early-exiting reader, the exact construct that returns 141 under pipefail and inverts
# the verdict. It is safe ONLY because bin/agent_propose.sh:331 runs it through `bash -lc`, a
# fresh non-interactive shell that does not inherit the caller's shell options. Setting
# pipefail here and getting 0 back proves the insulation is real and not a coincidence of how
# the tests happen to be invoked.
rc=0
( set -o pipefail
  HOME="$sandbox" AGENT_RUN_STARTED_AT="$started" bash -lc "$verify" >/dev/null 2>&1 ) || rc=$?
assert 'and still passes with pipefail set in the CALLER (bash -lc is a fresh shell)' \
  "[ '$rc' = 0 ]"

echo "--- overnight-morning-report: an unusable task file refuses, and says so ---"
# This guard is the shape m1-signal-scan copied when W15 was fixed (2026-09-03) — it had none
# until then and launched an empty prompt instead; see W15 in open-decisions.md and the matching
# group in tests/test_m1_signal_scan_smoke.sh. The check is an explicit `[ -r ]` BEFORE the
# command substitution, so both shapes refuse instead of launching an empty prompt.
home=$(make_mr_home no_task)
rc=$(run_mr "$home")
assert 'a missing task file exits non-zero' "[ '$rc' != 0 ]"
assert 'names the path in the journal (an alert with no path is a second search)' \
  "grep -q 'task file not readable' '$home/run.log'"
assert 'and the agent is never launched without its mission' "[ ! -f '$home/claude_argv.log' ]"

home=$(make_mr_home unreadable)
rc=$(run_mr "$home")
assert 'a PRESENT but unreadable task file also refuses (-r, not -f)' "[ '$rc' != 0 ]"
assert 'and the agent is never launched' "[ ! -f '$home/claude_argv.log' ]"

echo "--- overnight-morning-report: a complete fixture launches the agent correctly ---"
home=$(make_mr_home complete)
rc=$(run_mr "$home")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the prompt is the task file, not an empty string' \
  "[ \"\$(sed -n 1p '$home/claude_argv.log')\" = '-p' ] && [ -n \"\$(sed -n 2p '$home/claude_argv.log')\" ]"
assert 'launches the agent with the morning-report mission prompt' \
  "grep -qF 'pre-snapshot' '$home/claude_argv.log'"
assert 'no MCP servers (strict, empty config)' \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert 'no outward tools in the allowlist (the box holds no outward credential)' \
  "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"
# cwd is the workforce tree, NOT a vault or inbox checkout — the job reads the inbox by
# absolute path. A cwd change here would silently relocate every relative Read in the profile.
assert 'runs from the workforce tree, not a vault checkout' \
  "[ \"\$(cat '$home/claude_pwd.log')\" = \"\$(cd '$home/agent-workforce' && pwd -P)\" ]"

echo "--- overnight-morning-report: umask 077 survives the exec ---"
# Asserted from the artifact, not from grepping the source for `umask`. Claude Code writes
# with the inherited umask (0002 under systemd here), which would silently widen every report
# to 664 — a box-wide-readable file holding the night's operational detail. umask is inherited
# across exec, so a mock that writes a file is a genuine end-to-end check of the one line.
assert 'the report the agent writes is mode 600, not 664' \
  "[ \"\$(stat -c %a '$home/logs/overnight/morning-report-fixture.md')\" = 600 ]"
assert 'and the directory the runner creates is 700' \
  "[ \"\$(stat -c %a '$home/logs/overnight')\" = 700 ]"

echo "--- overnight-morning-report: the two runtime overrides are honoured ---"
# MORNING_REPORT_MODEL is what lets this suite exercise the runner without naming the model
# production uses; MORNING_REPORT_WORKDIR is what lets it run outside ~/agent-workforce. Both
# exist for testability, so a suite that never used them would leave them unproven.
home=$(make_mr_home complete)
rc=$(run_mr "$home")
assert 'the model defaults to sonnet' \
  "grep -qx -- '--model' '$home/claude_argv.log' && grep -qx 'sonnet' '$home/claude_argv.log'"
home=$(make_mr_home complete)
rc=$(run_mr "$home" MORNING_REPORT_MODEL=haiku)
assert 'MORNING_REPORT_MODEL overrides it' "grep -qx 'haiku' '$home/claude_argv.log'"
alt=$(mktemp -d); mkdir -p "$alt/profiles"
cp "$TASK" "$alt/profiles/overnight_morning_report_cc_task.md"
home=$(make_mr_home no_task)
rc=$(run_mr "$home" MORNING_REPORT_WORKDIR="$alt")
assert 'MORNING_REPORT_WORKDIR relocates the task file and the cwd' \
  "[ '$rc' = 0 ] && [ \"\$(cat '$home/claude_pwd.log')\" = \"\$(cd '$alt' && pwd -P)\" ]"

echo "--- overnight-morning-report: NO vault freshness gate, deliberately ---"
# The inverse of run_daily_rhythm_cc.sh, and the assertion exists because the copy-paste is
# tempting. This report reads systemd, journals, logs and the inbox worktree — never the vault
# mirror — so a stale mirror is not a reason to withhold it. Adding a gate would invent a new
# way to lose the report on a morning when nothing was wrong with the report.
assert 'the runner consults no vault guard' \
  "! grep -qE 'vault_sync_guard|VAULT_DIR|VAULT_SYNC_GUARD' '$RUNNER'"
assert 'and says why, so the absence reads as a decision rather than an omission' \
  "grep -qF 'No vault freshness gate here' '$RUNNER'"

echo "--- overnight-morning-report: the timer-enumeration block is executable, and executed ---"
# Extracted from the profile and RUN. Six hand-written copies of this list disagreed six ways
# and left eight standing units invisible to every report; this is the repaired version, and
# until now nothing could tell whether the repair worked, because a bash block inside a
# markdown file is executed by an agent once a day and by no test ever.
block=$(mktemp); sed -n '/^  ```bash$/,/^  ```$/p' "$TASK" | sed '1d;$d;s/^  //' > "$block"
assert 'a bash block was extracted from the profile' "[ -s '$block' ]"
assert 'and it is syntactically valid bash' "bash -n '$block'"

# Stub systemctl on PATH: records every invocation with the XDG_RUNTIME_DIR it saw. Without
# this the block would query the live box, and the 4-column case below could not prove the
# thing that matters — that systemctl is never reached at all.
stub=$(mktemp -d)
cat > "$stub/systemctl" <<EOF
#!/usr/bin/env bash
printf 'xdg=%s argv=%s\n' "\${XDG_RUNTIME_DIR:-UNSET}" "\$*" >> "$stub/calls.log"
exit 0
EOF
chmod +x "$stub/systemctl"

# Output goes to a FILE, never to a variable the assertion interpolates. The block's refusal
# is multi-line, and a multi-line value spliced into a `grep <<<"..."` herestring splits into
# arguments: grep reads the first line as a pattern and the rest as filenames, then fails with
# ENOENT on a message that is present and correct. That inverts the verdict — the refusal
# under test renders as the refusal not happening.
run_block() { # tsv-content -> writes $stub/out.log, resets $stub/calls.log
  local content=$1 home
  home=$(mktemp -d); mkdir -p "$home/agent-workforce/config"
  printf '%s' "$content" > "$home/agent-workforce/config/fleet-units.tsv"
  : > "$stub/calls.log"
  HOME="$home" PATH="$stub:$PATH" bash "$block" > "$stub/out.log" 2>&1
}

# The real file, verbatim: the block must work against its actual owner, not a hand-written
# imitation of it. A fixture that only ever sees a fixture proves the fixture.
run_block "$(cat "$REPO_ROOT/config/fleet-units.tsv")"
assert 'against the real config/fleet-units.tsv it does not refuse' \
  "! grep -q FATAL '$stub/out.log'"
assert 'it asks the system manager for a NON-EMPTY explicit timer list' \
  "grep -qE '^xdg=.* argv=list-timers .*\.timer' '$stub/calls.log'"
assert 'it asks the USER manager separately, and carries XDG_RUNTIME_DIR (no session bus)' \
  "grep -E 'argv=--user list-timers' '$stub/calls.log' | grep -qv 'xdg=UNSET'"
assert 'and asks about kind=service rows with is-active, not by appending .timer' \
  "grep -E 'argv=--user is-active .*\.service' '$stub/calls.log' | grep -qv 'xdg=UNSET'"
assert 'no call ever names a buzz-agent timer, which does not exist' \
  "! grep -q 'buzz-agent@[a-z]*\.timer' '$stub/calls.log'"

# The regression the guard exists for. `NF>=5` matches nothing in a 4-column file, and
# `systemctl list-timers` with an empty argument array lists EVERY timer on the box — 44,
# measured 2026-09-03 — so a silently empty list renders as a full, confident report derived
# from nothing. Worse than the glob it replaced, which at least matched a prefix.
four_col=$(awk -F'\t' 'BEGIN{OFS="\t"} !/^#/ && NF>=5 {print $1,$2,$3,$4}' "$REPO_ROOT/config/fleet-units.tsv")
run_block "$four_col"
assert 'a 4-column (pre-2026-09-03) file REFUSES rather than reporting' \
  "grep -q FATAL '$stub/out.log'"
assert 'and says coverage is UNKNOWN, not that nothing is scheduled' \
  "grep -q 'Unit coverage is UNKNOWN' '$stub/out.log'"
assert 'the kind=service half refuses independently (unaccounted for, not absent)' \
  "grep -q 'unaccounted for, not absent' '$stub/out.log'"
assert 'and systemctl is NEVER reached, so no 44-timer listing can be produced' \
  "[ ! -s '$stub/calls.log' ]"

run_block ""
assert 'an empty file refuses too (missing and empty are the same failure)' \
  "grep -q FATAL '$stub/out.log' && [ ! -s '$stub/calls.log' ]"

echo "--- overnight-morning-report: the alert log is DATED, never bare-tailed (W17) ---"
# The producer's `## Alerts (last 10)` section now prints `newest entry: <ts> (N days ago) —
# FRESH|STALE` (bin/overnight_pre_snapshot.sh, tests/test_overnight_pre_snapshot.sh). But this
# consumer reads ~/logs/agent-alert.log DIRECTLY as well, so fixing only the producer would have
# left the defect intact on the path Dave actually reads every morning. Both ends of one concept,
# asserted from both suites.
#
# Keyed on the AGE, not on a timestamp: every line bin/agent_alert.sh writes already carries
# `failed at <ISO>Z`, so an eight-day-dead log has always been full of dates and has always read
# as live. Stating the mtime is the minimum; being told to CALL IT STALE is the fix.
assert 'the profile dates the alert log before reading it' \
  "grep -qF 'alert log newest entry' '$TASK'"
assert 'and no longer asks for an undated tail of it' \
  "! grep -qE '^- .tail -[0-9]+ ~/logs/agent-alert\\.log' '$TASK'"
assert 'it is pointed at the pre-snapshot marker by its exact rendered shape' \
  "grep -qF 'newest entry: <ts> (N days ago)' '$TASK'"
assert 'and told to report a stale log as history rather than as last night' \
  "grep -qF 'never present an old alert as last' '$TASK'"
assert 'an UNKNOWN age is unverified, not fresh — the blank that reads as freshness' \
  "grep -qF 'report it as unverified, not as fresh' '$TASK'"
# The instruction needs somewhere to land. The report template had no alert slot at all, so
# "say so in the report" was a rule with no output field — and a field the agent has to invent
# is a field it will omit on the morning the log is stale.
# `--` is load-bearing: the pattern starts with `-`, and grep reads a leading dash as an option
# cluster even inside quotes — it exits 2 with "invalid option", which an assert reads as the
# text being absent. A true assertion failing for a quoting reason is the worst kind of red.
assert 'and the report template carries an alert-log line demanding the age' \
  "grep -qF -- '- Alert log: <newest entry + its age' '$TASK'"
# The block below is extracted by line-anchored fences. A SECOND 2-space-indented fenced block
# anywhere in the profile splices into that sed range and leaves stray fence lines mid-script,
# so the alert instruction above is deliberately inline code rather than a fence. Counted here
# because the failure it causes surfaces as "the enumeration block is not valid bash", which
# names the wrong file.
fence_count=$(grep -c '^  ```bash$' "$TASK" || true)
assert 'the profile still carries exactly one 2-space-indented bash fence to extract' \
  "[ '$fence_count' = 1 ]"

echo "--- overnight-morning-report: the profile keeps its retired-surface exclusions ---"
# S3 was retired 2026-09-02 (D7) and the pre-snapshot stopped capturing kanban and gateway in
# the same commit. A report that flags their absence as a fault manufactures a blocker every
# single morning, which is the readiness-report phantom-blocker shape.
assert 'kanban/gateway absence is explicitly not a fault' \
  "grep -qF 'do not report their absence as a fault' '$TASK'"
assert 'and hermes cron is demoted, not treated as the schedule source' \
  "grep -qF 'Do **not** treat' '$TASK'"

exit $fail
