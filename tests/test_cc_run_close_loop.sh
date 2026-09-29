#!/usr/bin/env bash
# bin/cc_run.sh hands every scheduled `claude -p` CLAUDE_CLOSE_LOOP_CHECK=off, the one value on
# which the vault's close-loop Stop hook stands down, so its reminder can never become a run's
# `.result` (the why sits at the export). Offline: a fake claude records what it inherited, and
# each runner runs against a fixture HOME whose profiles/ and skills/ are this checkout's own.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

assert 'a found pattern is never reported as a failure' "yes | grep -q y"

WRAP="$REPO_ROOT/bin/cc_run.sh"

# fake claude: records the CLAUDE_CLOSE_LOOP_CHECK it inherited, or <unset>; runs no model.
make_env_recording_claude() {
  local home=$1
  cat > "$home/claude" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\${CLAUDE_CLOSE_LOOP_CHECK-<unset>}" > "$home/close_loop.env"
EOF
  chmod +x "$home/claude"
  echo "$home/claude"
}

seen() { cat "$1/close_loop.env" 2>/dev/null || echo '<claude never ran>'; }

# The HOME a runner derives its task file, skills tree and cwd from.
make_runner_home() {
  local home
  home=$(mktemp -d)
  mkdir -p "$home/agent-workforce" "$home/agent-worktrees/inbox"
  ln -s "$REPO_ROOT/profiles" "$home/agent-workforce/profiles"
  ln -s "$REPO_ROOT/skills" "$home/agent-workforce/skills"
  echo "$home"
}

# `env -i` throughout: the only way the value can reach the fake is through the chain under
# test, never from the shell that runs this suite.
echo "--- cc-run-close-loop-off ---"   # (::cc-run-close-loop-off)
for usage in unset set; do
  for caller in '<unset>' '' on off; do
    h=$(mktemp -d); fake=$(make_env_recording_claude "$h")
    vars=(HOME="$h" PATH="$PATH")
    if [ "$usage" = set ]; then vars+=(AGENT_USAGE_JSON="$h/last-attempt/job.usage.json"); fi
    if [ "$caller" != '<unset>' ]; then vars+=(CLAUDE_CLOSE_LOOP_CHECK="$caller"); fi
    env -i "${vars[@]}" bash "$WRAP" "$fake" -p hi >/dev/null 2>&1 || true
    assert "AGENT_USAGE_JSON $usage, caller's value '$caller': claude inherits exactly 'off'" \
      "[ \"\$(seen '$h')\" = off ]"
  done
done

# The runner list is the job templates', not this file's: every AGENT_RUNTIME_CMD in
# profiles/*.env.example that names a Claude Code runner. Each one is run rather than grepped,
# so a runner that reached claude by any path but the seam fails here by name.
echo "--- cc-run-close-loop-every-runner ---"   # (::cc-run-close-loop-every-runner)
runners=()
for example in "$REPO_ROOT"/profiles/*.env.example; do
  runtime=$(env_value "$example" AGENT_RUNTIME_CMD)
  resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
  case "${resolved%% *}" in "$REPO_ROOT"/bin/run_*_cc.sh) runners+=("${resolved%% *}") ;; esac
done
assert "the job templates wire Claude Code runners (${#runners[@]}); an empty list would assert nothing" \
  "[ ${#runners[@]} -gt 0 ]"
for runner in ${runners[@]+"${runners[@]}"}; do
  for usage in unset set; do
    h=$(make_runner_home); fake=$(make_env_recording_claude "$h")
    vars=(HOME="$h" PATH="$PATH" CLAUDE_BIN="$fake" VAULT_SYNC_GUARD=true AGENT_SESSION_ID=close-loop-test)
    if [ "$usage" = set ]; then vars+=(AGENT_USAGE_JSON="$h/last-attempt/job.usage.json"); fi
    env -i "${vars[@]}" bash "$runner" >"$h/run.log" 2>&1 || true
    assert "${runner#"$REPO_ROOT"/} (AGENT_USAGE_JSON $usage): its claude inherits exactly 'off'" \
      "[ \"\$(seen '$h')\" = off ]"
    [ -e "$h/close_loop.env" ] || sed 's/^/      | /' "$h/run.log" | tail -3
  done
done

exit $fail
