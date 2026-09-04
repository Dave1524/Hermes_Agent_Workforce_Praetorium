#!/usr/bin/env bash
# Research pipeline brief (2026-07-30) — standing research on headless Claude Code,
# pinned to Opus 5, replacing hermes/claudius on OpenRouter. The case that matters: the
# standing run was hard-down for ten days on OpenRouter 402s while agent_propose.sh logged
# a clean NOPROPOSAL, because the 402 landed in the hermes profile's own errors.log, never
# in the attempt's stdout where PROVIDER_ERROR_RE could see it. Offline by contract: mock
# claude, never a real inbox worktree, never OpenRouter.
#
# SR (2026-09-04) added the refusal groups. Until then this suite exercised exactly ONE runner
# path — the happy one — so the unguarded `$(cat "$TASK_FILE")` in the runner's exec line was
# green here for five weeks: an empty prompt still launches the agent and still exits 0, which
# every assertion in the launch group below passes unchanged. A suite with no negative case
# cannot see a fail-open, and that is why the positive control and the refusals landed together.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=tests/rhythm_test_lib.sh
. "$TESTS_DIR/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in assert(): `yes` is guaranteed
# to still be writing when `grep -q` exits, so this fails if and only if a condition is
# evaluated under pipefail. It lives in every caller because the assert it guards is shared —
# a single copy in the lib could not tell which suite had reintroduced the setting.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

RUNNER="$REPO_ROOT/bin/run_standing_research_cc.sh"
TASK="$REPO_ROOT/profiles/standing_research_cc_task.md"
ENV_EXAMPLE="$REPO_ROOT/profiles/standing_research.env.example"

# state -> a fixture root holding the inbox checkout and the task profile. This runner honours
# STANDING_RESEARCH_INBOX and STANDING_RESEARCH_TASK (bin/run_standing_research_cc.sh:16-17),
# so both preconditions relocate with two env vars and nothing here needs to move HOME — the
# opposite of tests/test_m1_signal_scan_smoke.sh, which relocates HOME precisely because m1
# hardcodes both paths off it. Each broken state removes exactly ONE precondition so the two
# are proven separately; `both_missing` exists only to pin the ORDER of the two checks.
make_sr_fixture() {
  local state=$1 home
  home=$(mktemp -d)
  [ "$state" = no_inbox ] || [ "$state" = both_missing ] || mkdir -p "$home/inbox"
  case "$state" in
    no_task|both_missing) : ;;   # TASK_FILE points into the fixture at a path never created
    # `-r`, not `-f`: a present-but-unreadable profile (a bad chmod, a half-copied deploy)
    # feeds cat(1) the same failure and the agent the same empty prompt as an absent one.
    # NOTE: this fixture is only a real test of `-r` for a non-root user — under uid 0 mode
    # 000 is still readable and the assertion would pass for the wrong reason. Verified as
    # uid 1000 (dave) on 2026-09-04; the suite runs unprivileged from bin/verify.sh.
    unreadable) cp "$TASK" "$home/task.md"; chmod 000 "$home/task.md" ;;
    *)          cp "$TASK" "$home/task.md" ;;
  esac
  echo "$home"
}

run_sr() { # fixture-root -> rc
  local home=$1 claude rc=0
  claude=$(make_mock_claude "$home")
  HOME="$home" CLAUDE_BIN="$claude" STANDING_RESEARCH_INBOX="$home/inbox" \
    STANDING_RESEARCH_TASK="$home/task.md" bash "$RUNNER" >"$home/run.log" 2>&1 || rc=$?
  echo "$rc"
}

# "the agent was never launched" is an ABSENCE claim, and an absence is only evidence once its
# subject is shown to exist: a mock that failed to install would leave the same missing
# claude_argv.log and certify nothing. So every refusal asserts the launcher IS present and
# executable in the same breath. The complementary proof is the positive control at the bottom,
# where the identical mock DOES write the log.
assert_never_launched() {
  local home=$1 desc=$2
  assert "$desc" "[ -x '$home/claude' ] && [ ! -f '$home/claude_argv.log' ]"
}

echo "--- standing-research: the env override parses and wires the CC runner ---"
assert "env.example exists" "[ -f '$ENV_EXAMPLE' ]"
slug=$(env_value "$ENV_EXAMPLE" AGENT_TASK_SLUG)
runtime=$(env_value "$ENV_EXAMPLE" AGENT_RUNTIME_CMD)
profile=$(env_value "$ENV_EXAMPLE" AGENT_PROFILE)
verify=$(env_value "$ENV_EXAMPLE" AGENT_VERIFY_CMD)
assert "AGENT_TASK_SLUG=standing-research" "[ '$slug' = standing-research ]"
assert "AGENT_PROFILE is the Claude Code runtime, not claudius/OpenRouter" "[ '$profile' = claude-opus ]"
resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"
assert "and points at the CC runner (the 402 fix)" "[[ '$runtime' == *run_standing_research_cc.sh* ]]"
assert "no hermes/OpenRouter invocation survives in the active wiring" \
  "! grep -qE '^AGENT_RUNTIME_CMD=.*hermes' '$ENV_EXAMPLE'"
assert "AGENT_VERIFY_CMD wires the shared de-silencing helper" \
  "[[ '$verify' == *'proposal_or_decline.sh standing-research'* ]]"

echo "--- standing-research: refuses when it has nowhere to write ---"
# Not in scope for SR on its own — it is the control that makes the ordering assertion below
# an ordering assertion. A missing inbox fails at `cd "$INBOX"` and says so; if it produced the
# task-file message too, `both_missing` could not tell the two checks apart.
home=$(make_sr_fixture no_inbox)
rc=$(run_sr "$home")
assert 'a missing inbox worktree exits non-zero' "[ '$rc' != 0 ]"
# `-s` first, and it is load-bearing: `! grep -q X missing-file` is TRUE, so an absence claim
# whose subject was never created certifies nothing. Prove the log was written, then prove
# what it does not say.
assert 'and does NOT claim the task file is at fault' \
  "[ -s '$home/run.log' ] && ! grep -qF 'task file not readable' '$home/run.log'"
assert_never_launched "$home" 'and the agent is never launched with nowhere to write'

echo "--- standing-research: refuses when it has no mission to run ---"
# SR, 2026-09-04. This runner was the LAST of the ten CC runners still reaching
# `exec claude -p "$(cat "$TASK_FILE")"` unguarded. The failing cat sits in a command
# substitution used as an ARGUMENT and `set -e` does not propagate that: the substitution
# yields the empty string, the agent is launched with an EMPTY PROMPT, and the runner exits 0.
# Identical mechanism to W15 (bin/run_m1_signal_scan_cc.sh:23, fixed 2026-09-03).
#
# THE HARM PROFILE IS NOT W15's, and that is why the fix here is one line rather than three.
# m1 wired no AGENT_VERIFY_CMD, so its empty-prompt run landed as NOPROPOSAL exit 0 and was
# genuinely silent. This job already carries both halves of that second layer — the env group
# above asserts `proposal_or_decline.sh standing-research`, and the profile group below asserts
# the literal DECLINE: sentinel — so an empty-prompt run produces neither artifact and FAILS
# LOUD on its own. What the guard buys is the NAMED PATH in the journal instead of a bare
# verify failure pointing at the wrong layer. Do not "complete" this by touching the env
# template or the profile; both were checked on 2026-09-04 and are already correct.
home=$(make_sr_fixture no_task)
rc=$(run_sr "$home")
assert 'a missing task file exits non-zero — no empty prompt, no silent success' "[ '$rc' != 0 ]"
# The PATH, not just the phrase: an alert that says "task file not readable" without saying
# which one starts a second search at 04:30.
assert 'names the unreadable path in the journal' \
  "grep -qF 'standing-research: task file not readable: $home/task.md' '$home/run.log'"
assert_never_launched "$home" 'and the agent is never launched without its mission'

home=$(make_sr_fixture unreadable)
rc=$(run_sr "$home")
assert 'a PRESENT but unreadable task file also refuses (-r, not -f)' "[ '$rc' != 0 ]"
assert_never_launched "$home" 'and the agent is never launched'

# Order, not just presence. The guard has to sit ahead of `cd "$INBOX"`, so with BOTH
# preconditions broken the mission failure is the one reported. Placed after the cd it would
# report a directory error instead and send the reader to the wrong repair.
home=$(make_sr_fixture both_missing)
rc=$(run_sr "$home")
assert 'with both preconditions broken it still refuses' "[ '$rc' != 0 ]"
assert 'and the task-file guard is the one that fires — it precedes the cd' \
  "grep -qF 'standing-research: task file not readable' '$home/run.log'"
assert_never_launched "$home" 'and the agent is never launched'

echo "--- standing-research: the runner launches Opus 5 with no MCP servers ---"
home=$(make_sr_fixture complete)
rc=$(run_sr "$home")
assert "exits 0" "[ '$rc' = 0 ]"
# The positive control for the three refusals above. Without it they are shape-only: a runner
# that refused EVERYTHING would satisfy every one of them. argv is recorded one element per
# line, so line 1 is the flag and line 2 the prompt's first line — an empty prompt leaves line
# 2 blank, which is exactly the defect this branch closes.
assert "the prompt is the task file, not an empty string (the SR positive control)" \
  "[ \"\$(sed -n 1p '$home/claude_argv.log')\" = '-p' ] && [ -n \"\$(sed -n 2p '$home/claude_argv.log')\" ]"
assert "pins the full Opus 5 model name, not the opus alias" \
  "grep -qx 'claude-opus-5' '$home/claude_argv.log' && ! grep -qx 'opus' '$home/claude_argv.log'"
assert "no MCP servers (strict, empty config)" \
  "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
assert "keeps WebSearch/WebFetch (this job does public web research)" \
  "grep -qE 'WebSearch' '$home/claude_argv.log' && grep -qE 'WebFetch' '$home/claude_argv.log'"
assert "launches with the standing-research task prompt" \
  "grep -qF 'headless Claude Code (Opus 5)' '$home/claude_argv.log'"

echo "--- standing-research: task profile carries over the load-bearing claudius instructions ---"
assert "task profile exists" "[ -f '$TASK' ]"
assert "keeps the published_corpus.py duplicate-title gate" "grep -q 'published_corpus.py' '$TASK'"
assert "keeps FACT vs INFERENCE labelling" "grep -qi 'FACT' '$TASK' && grep -qi 'INFERENCE' '$TASK'"
assert "keeps the queue.md soonest-Deadline priority order" "grep -q 'queue.md' '$TASK'"
assert "adds the Mechanism A Contradictions section" "grep -q '## Contradictions' '$TASK'"
assert "emits the DECLINE: sentinel contract" "grep -q 'DECLINE:' '$TASK'"
assert "never acts outward" "grep -qi 'never act outward' '$TASK'"
assert "no hermes memory tool call survives (STEP 5 dropped)" "! grep -q 'action=add' '$TASK'"
assert "substitutes ls _inbox/agents for the removed hermes MEMORY store" \
  "grep -q 'ls -1 _inbox/agents' '$TASK'"
assert "reads approvals.tsv for what was already proposed" "grep -q 'approvals.tsv' '$TASK'"

exit $fail
