#!/usr/bin/env bash
# NUC-45 shared test fixtures + assertions for the daily-rhythm suites
# (test_vault_sync_guard.sh, test_daily_plan_smoke.sh, test_eod_summary_smoke.sh).
#
# Everything here is offline by contract: throwaway git fixtures and a mock claude
# binary, never ~/vault, never a real remote, never a live Notion write.
#
# Executing this file directly is a deliberate no-op so bin/verify.sh's tests/*.sh
# sweep stays green.
set -euo pipefail

TESTS_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$TESTS_DIR/.." && pwd)"
GUARD="$REPO_ROOT/bin/vault_sync_guard.sh"
# The guard's own "origin was last reachable" stamp: git rewrites FETCH_HEAD even when a
# fetch FAILS, so FETCH_HEAD is not a witness. Path relative to the checkout under test.
STAMP=".git/vault_sync_guard_last_fetch"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
}

commit_at() {
  local repo=$1 when=$2 file=$3 msg=$4
  printf '%s\n' "$msg" >> "$repo/$file"
  git -C "$repo" add -A
  GIT_AUTHOR_DATE="$when" GIT_COMMITTER_DATE="$when" git -C "$repo" commit -q -m "$msg"
}

# state -> a fixture directory whose ./vault is the mirror under test.
make_vault_fixture() {
  local state=$1 root origin work pub base_when
  root=$(mktemp -d); origin="$root/origin.git"; work="$root/vault"; pub="$root/pub"
  # git wants a strict date here, not an approxidate — resolve it with date(1).
  case "$state" in
    stale_behind) base_when=$(date -d '5 days ago' -Is) ;;
    *)            base_when=$(date -d '2 hours ago' -Is) ;;
  esac

  git init -q --bare -b main "$origin"
  git init -q "$work"
  git -C "$work" symbolic-ref HEAD refs/heads/main
  git -C "$work" config user.email test@example.com
  git -C "$work" config user.name test
  printf 'base\n' > "$work/base.md"
  printf 'upstream owns this line\n' > "$work/shared.md"
  git -C "$work" add -A
  GIT_AUTHOR_DATE="$base_when" GIT_COMMITTER_DATE="$base_when" \
    git -C "$work" commit -q -m base
  git -C "$work" remote add origin "$origin"
  git -C "$work" push -q -u origin main

  case "$state" in
    clean_current|untracked) : ;;   # nothing published after the clone
    *)
      git clone -q -b main "$origin" "$pub"
      git -C "$pub" config user.email mac@example.com
      git -C "$pub" config user.name mac
      commit_at "$pub" "$(date -Is)" shared.md "published from the Mac"
      git -C "$pub" push -q origin main
      ;;
  esac

  case "$state" in
    dirty_behind)  printf 'box-side edit that never went through the membrane\n' >> "$work/shared.md" ;;
    # A rewritten upstream: the box still holds commits from the history the Mac's
    # publish_boxsafe.sh --force-with-lease replaced, so origin/main is no longer a
    # fast-forward from HEAD. This is the 2026-07-27 wedge.
    diverged_clean) commit_at "$work" "$(date -Is)" boxhist.md "tip of the pre-rewrite history" ;;
    diverged_dirty) commit_at "$work" "$(date -Is)" boxhist.md "tip of the pre-rewrite history"
                    printf 'box-side edit that never went through the membrane\n' >> "$work/shared.md" ;;
    untracked)     printf 'stray\n' > "$work/local_inference_charter.md" ;;
    offline)       git -C "$work" remote set-url origin "$root/gone.git"
                   touch "$work/$STAMP" ;;
    offline_stale) git -C "$work" remote set-url origin "$root/gone.git"
                   touch -d '3 days ago' "$work/$STAMP" ;;
  esac
  echo "$root"
}

# Stand-in for the headless Claude Code binary: records argv, runs no model.
make_mock_claude() {
  local home=$1
  cat > "$home/claude" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$home/claude_argv.log"
exit 0
EOF
  chmod +x "$home/claude"
  echo "$home/claude"
}

env_value() {
  local file=$1 var=$2
  # shellcheck disable=SC1090
  ( set +u; . "$file" >/dev/null 2>&1 || true; printf '%s' "${!var:-}" )
}

# The shape both daily-rhythm jobs share: an ops-mode override that resolves to a real
# runtime, a verify command that only a THIS-RUN artifact satisfies, and a runner that
# refuses to brief Dave off a stale mirror.
smoke_suite() {
  local job=$1 runner=$2 env_example=$3 receipts=$4 prompt_marker=$5
  local env_file="$REPO_ROOT/$env_example"
  local slug mode runtime verify resolved sandbox started rc root home claude

  echo "--- $job: the env override parses and wires the guarded runner ---"
  assert "$env_example exists" "[ -f '$env_file' ]"
  slug=$(env_value "$env_file" AGENT_TASK_SLUG)
  mode=$(env_value "$env_file" AGENT_RUN_MODE)
  runtime=$(env_value "$env_file" AGENT_RUNTIME_CMD)
  verify=$(env_value "$env_file" AGENT_VERIFY_CMD)
  assert "AGENT_TASK_SLUG=$job" "[ '$slug' = '$job' ]"
  assert "AGENT_RUN_MODE=ops (no inbox worktree, no proposal commit)" "[ '$mode' = ops ]"
  resolved="${runtime/#\~\/agent-workforce/$REPO_ROOT}"
  assert "AGENT_RUNTIME_CMD resolves to an executable script" "[ -x '$resolved' ]"

  echo "--- $job: AGENT_VERIFY_CMD only accepts THIS run's artifact ---"
  assert "AGENT_VERIFY_CMD is set (load-bearing: exit 0 is not evidence)" "[ -n '$verify' ]"
  assert "and is anchored to AGENT_RUN_STARTED_AT" "[[ '$verify' == *AGENT_RUN_STARTED_AT* ]]"
  sandbox=$(mktemp -d); mkdir -p "$sandbox/logs/$receipts"
  started=$(date +%s)
  touch -d '2 hours ago' "$sandbox/logs/$receipts/receipt-2026-07-26.json"
  rc=0
  HOME="$sandbox" AGENT_RUN_STARTED_AT="$started" bash -lc "$verify" >/dev/null 2>&1 || rc=$?
  assert "yesterday's receipt does NOT pass (2026-07-21 stale-redelivery regression)" \
    "[ '$rc' != 0 ]"
  touch "$sandbox/logs/$receipts/receipt-2026-07-27.json"
  rc=0
  HOME="$sandbox" AGENT_RUN_STARTED_AT="$started" bash -lc "$verify" >/dev/null 2>&1 || rc=$?
  assert "a receipt written by this run DOES pass" "[ '$rc' = 0 ]"

  echo "--- $job: refuses to brief off a stale mirror ---"
  root=$(make_vault_fixture stale_behind); home=$(mktemp -d)
  claude=$(make_mock_claude "$home")
  rc=0
  HOME="$home" CLAUDE_BIN="$claude" VAULT_DIR="$root/vault" VAULT_SYNC_GUARD="$GUARD" \
    DAILY_RHYTHM_WORKDIR="$REPO_ROOT" bash "$REPO_ROOT/$runner" >"$home/run.log" 2>&1 || rc=$?
  assert "exits non-zero on a 5-day-stale mirror" "[ '$rc' != 0 ]"
  assert "says REFUSING (so the journal explains the alert)" "grep -q 'REFUSING' '$home/run.log'"
  assert "the agent is never launched on stale data" "[ ! -f '$home/claude_argv.log' ]"

  echo "--- $job: runs on a current mirror ---"
  root=$(make_vault_fixture clean_current); home=$(mktemp -d)
  claude=$(make_mock_claude "$home")
  rc=0
  HOME="$home" CLAUDE_BIN="$claude" VAULT_DIR="$root/vault" VAULT_SYNC_GUARD="$GUARD" \
    DAILY_RHYTHM_WORKDIR="$REPO_ROOT" bash "$REPO_ROOT/$runner" >"$home/run.log" 2>&1 || rc=$?
  assert "exits 0" "[ '$rc' = 0 ]"
  assert "launches the agent with the $job task prompt" \
    "grep -qF '$prompt_marker' '$home/claude_argv.log'"
  assert "no MCP servers (strict, empty config)" \
    "grep -q -- '--strict-mcp-config' '$home/claude_argv.log' && grep -q 'mcpServers' '$home/claude_argv.log'"
  assert "no outward tools in the allowlist (box holds no outward credential)" \
    "! grep -qE 'WebSearch|WebFetch' '$home/claude_argv.log'"
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "  (shared fixture library for the NUC-45 daily-rhythm tests — nothing to run)"
  exit 0
fi
