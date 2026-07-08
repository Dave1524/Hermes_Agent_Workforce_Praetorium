#!/usr/bin/env bash
# NUC-16 runner: one unattended agent run → one structured proposal in the
# agents/inbox branch, or NO output at all. Never touches canonical files.
#
# Guardrails (NUC-08b): iteration/call ceilings from secrets.env, retry with
# backoff, API failure => no proposal, cost line logged per run — including
# failed and boundary-violation runs, so a runaway failure loop stays visible.
# Write boundary (NUC-15/16): agent may only change _inbox/agents/** inside the
# scoped worktree; any other diff aborts the run and resets the worktree.
set -euo pipefail

SECRETS="$HOME/.config/agent-workforce/secrets.env"
WORKTREE="$HOME/agent-worktrees/inbox"
LOG_DIR="$HOME/agent-workforce/logs"
LOCK="${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}"
mkdir -p "$LOG_DIR"
log() { echo "$(date -Is) $*" | tee -a "$LOG_DIR/agent_propose.log"; }

run_started=$(date +%s)
attempt=0
log_cost() {
  local outcome=$1
  local elapsed=$(( $(date +%s) - run_started ))
  echo "$(date -Is) run_seconds=$elapsed attempts=$attempt outcome=$outcome model=${LLM_MODEL_BUSINESS:-unset}" >> "$LOG_DIR/cost.log"
}

exec 9>"$LOCK"
flock -n 9 || { log "SKIP: previous run still active"; exit 0; }

# ── Preflight: every gate must hold, otherwise exit quietly with NO proposal ──
[ -f "$SECRETS" ] || { log "BLOCKED: secrets.env missing"; exit 0; }
# shellcheck disable=SC1090
source "$SECRETS"
[ -n "${OPENROUTER_API_KEY:-}" ] || { log "BLOCKED: no API key — no run (by design)"; exit 0; }
[ -d "$WORKTREE" ] || { log "BLOCKED: inbox worktree missing — run finish_boxsafe_clone.sh"; exit 0; }
[ -n "${AGENT_RUNTIME_CMD:-}" ] || { log "BLOCKED: AGENT_RUNTIME_CMD not set (NUC-14 pending)"; exit 0; }

git -C "$WORKTREE" checkout -q agents/inbox
git -C "$WORKTREE" pull -q --ff-only origin agents/inbox 2>/dev/null || true

# ── Run the profile with retry + backoff (NUC-16) ──
# Turn ceiling is enforced by the profile's own config.yaml `agent.max_turns`,
# which is the single owner of that number. hermes `-z` oneshot has NO
# `--max-turns` CLI flag (verified 2026-07-08, NUC-16): passing one makes hermes
# reject the trailing value as an invalid subcommand and every run fails at
# arg-parse. The earlier `--max-turns $AGENT_MAX_ITERATIONS` here was a phantom
# flag (NUC-08b) that only ever "passed" against the mocked hermes in the smoke
# test; real hermes never accepted it. Do not reintroduce it.
run_cmd="$AGENT_RUNTIME_CMD"
retry_base="${AGENT_RETRY_BASE_SECONDS:-30}"
max_attempts=3; ok=false
while [ $attempt -lt $max_attempts ]; do
  attempt=$((attempt + 1))
  log "run attempt $attempt/$max_attempts: $run_cmd"
  if timeout "${AGENT_TIMEOUT_MINUTES:-30}m" bash -lc "$run_cmd" \
       >>"$LOG_DIR/agent_run.log" 2>&1; then
    ok=true; break
  fi
  sleep $((retry_base * attempt * attempt))   # 30s, 120s backoff by default
done

if ! $ok; then
  log "FAIL: runtime failed after $max_attempts attempts — resetting worktree, NO proposal emitted"
  git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  log_cost FAIL
  exit 1
fi

# ── Write-boundary enforcement: only _inbox/agents/** may change ──
violations=$(git -C "$WORKTREE" status --porcelain | awk '{print $2}' | grep -v "^_inbox/agents/" || true)
if [ -n "$violations" ]; then
  log "FATAL: agent touched files outside _inbox/agents/ — discarding everything: $violations"
  git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  log_cost VIOLATION
  exit 1
fi

# ── Commit + push proposal (or end cleanly if the agent chose not to propose) ──
if [ -z "$(git -C "$WORKTREE" status --porcelain)" ]; then
  log "OK: run completed, agent produced no proposal"
else
  git -C "$WORKTREE" add _inbox/agents/
  git -C "$WORKTREE" commit -q -m "agent proposal $(date +%Y-%m-%d_%H%M)"
  git -C "$WORKTREE" push -q origin agents/inbox
  log "OK: proposal pushed to agents/inbox"
fi

log_cost OK
