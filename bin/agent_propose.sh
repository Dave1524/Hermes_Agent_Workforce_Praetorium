#!/usr/bin/env bash
# NUC-16 runner: one unattended agent run → one structured proposal in the
# agents/inbox branch, or NO output at all. Never touches canonical files.
#
# Guardrails (NUC-08b): iteration/call ceilings from secrets.env, retry with
# backoff, API failure => no proposal, cost line logged per run.
# Write boundary (NUC-15/16): agent may only change _inbox/agents/** inside the
# scoped worktree; any other diff aborts the run and resets the worktree.
set -euo pipefail

SECRETS="$HOME/.config/agent-workforce/secrets.env"
WORKTREE="$HOME/agent-worktrees/inbox"
LOG_DIR="$HOME/agent-workforce/logs"
LOCK="/tmp/agent_propose.lock"
mkdir -p "$LOG_DIR"
log() { echo "$(date -Is) $*" | tee -a "$LOG_DIR/agent_propose.log"; }

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
run_started=$(date +%s)
attempt=0; max_attempts=3; ok=false
while [ $attempt -lt $max_attempts ]; do
  attempt=$((attempt + 1))
  log "run attempt $attempt/$max_attempts: $AGENT_RUNTIME_CMD"
  if timeout "${AGENT_TIMEOUT_MINUTES:-30}m" bash -lc "$AGENT_RUNTIME_CMD" \
       >>"$LOG_DIR/agent_run.log" 2>&1; then
    ok=true; break
  fi
  sleep $((30 * attempt * attempt))   # 30s, 120s backoff
done

if ! $ok; then
  log "FAIL: runtime failed after $max_attempts attempts — resetting worktree, NO proposal emitted"
  git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  exit 1
fi

# ── Write-boundary enforcement: only _inbox/agents/** may change ──
violations=$(git -C "$WORKTREE" status --porcelain | awk '{print $2}' | grep -v "^_inbox/agents/" || true)
if [ -n "$violations" ]; then
  log "FATAL: agent touched files outside _inbox/agents/ — discarding everything: $violations"
  git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
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

elapsed=$(( $(date +%s) - run_started ))
echo "$(date -Is) run_seconds=$elapsed attempts=$attempt model=${LLM_MODEL_BUSINESS:-unset}" >> "$LOG_DIR/cost.log"
