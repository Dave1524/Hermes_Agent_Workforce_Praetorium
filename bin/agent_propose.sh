#!/usr/bin/env bash
# NUC-16 runner: one unattended agent run → one structured proposal in the
# agents/inbox branch, or NO output at all. Never touches canonical files.
#
# Guardrails (NUC-08b): iteration/call ceilings from secrets.env, retry with
# backoff, API failure => no proposal, cost line logged per run — including
# failed and boundary-violation runs, so a runaway failure loop stays visible.
# Write boundary (NUC-15/16): agent may only change _inbox/agents/** inside the
# scoped worktree; any other diff aborts the run and resets the worktree.
# Metrics (NUC-23): each run appends a structured key=value record to cost.log
# and refreshes the scorecard digest (both fail-soft).
# Working memory (NUC-21): the run records one episodic entry to the profile's
# MEMORY.md (agent self-records; runner writes a fail-soft backstop if it didn't).
set -euo pipefail

SECRETS="$HOME/.config/agent-workforce/secrets.env"
WORKTREE="$HOME/agent-worktrees/inbox"
LOG_DIR="$HOME/agent-workforce/logs"
LOCK="${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}"
mkdir -p "$LOG_DIR"
log() { echo "$(date -Is) $*" | tee -a "$LOG_DIR/agent_propose.log"; }

run_started=$(date +%s)
attempt=0
# NUC-23 metrics fields (resolved after secrets are sourced); NUC-21 memory field.
run_profile="unknown"
run_model="unknown"
run_task="standing"
run_proposal="none"
run_outcome="NOPROPOSAL"
mem_status="na"
# NUC-27 real spend: shared-key cumulative USD spend snapshotted before the run.
usage_before="unknown"

key_usage() {
  # NUC-27: real per-run spend tracking. Read-only GET of the shared OpenRouter
  # key's cumulative spend ('usage', USD) via /key — auth pattern reused from
  # bin/llm_smoke_test.sh. The whole fleet shares ONE key under a single ~$25 cap,
  # so (usage_after - usage_before) is this run's real cost. Fail-soft BY CONTRACT:
  # any network / HTTP / parse / missing-key error echoes 'unknown' and returns 0 —
  # a budget probe must NEVER crash or block a run. Key read from the already-sourced
  # env (secrets.env); never logged.
  local base resp usage
  base="${LLM_BASE_URL:-https://openrouter.ai/api/v1}"
  [ -n "${OPENROUTER_API_KEY:-}" ] || { echo "unknown"; return 0; }
  resp=$(curl -sS --max-time 15 "$base/key" \
           -H "Authorization: Bearer $OPENROUTER_API_KEY" 2>/dev/null) \
    || { echo "unknown"; return 0; }
  usage=$(printf '%s' "$resp" | python3 -c 'import json,sys
try:
    u=json.load(sys.stdin)["data"].get("usage")
    print(u if isinstance(u,(int,float)) else "unknown")
except Exception:
    print("unknown")' 2>/dev/null) || usage="unknown"
  [ -n "$usage" ] || usage="unknown"
  echo "$usage"
}

log_cost() {
  # Structured, append-only, key=value (NUC-23). model is the PROFILE's real
  # config.yaml model.name — NOT LLM_MODEL_BUSINESS (which was stale, echoing
  # sonnet-5 while the profile runs haiku-4.5).
  # NUC-27: cost is now REAL, not a flat 'unknown'. usage_before (snapshotted just
  # before the retry loop) and usage_after (read here) are the shared key's
  # cumulative OpenRouter spend in USD; cost_usd_delta = after - before = this run's
  # real cost. Either bound may be 'unknown' when the budget probe fails — the delta
  # is then 'unknown' too and the run still logs cleanly. tokens stay 'unknown':
  # hermes token accounting is broken on OpenAI-compatible endpoints (#4404/#20741).
  # Written on FAIL/VIOLATION too so failure loops stay visible.
  local outcome=$1
  local elapsed=$(( $(date +%s) - run_started ))
  local usage_after delta
  usage_after=$(key_usage)
  delta=$(python3 -c 'import sys
a,b=sys.argv[1],sys.argv[2]
try:
    print(f"{float(a)-float(b):.6f}")
except Exception:
    print("unknown")' "$usage_after" "${usage_before:-unknown}" 2>/dev/null) || delta="unknown"
  [ -n "$delta" ] || delta="unknown"
  printf 'ts=%s schema=3 profile=%s model=%s task=%s outcome=%s proposal=%s run_seconds=%s attempts=%s tokens=unknown usage_before=%s usage_after=%s cost_usd_delta=%s cost_src=openrouter-key-api memory=%s\n' \
    "$(date -Is)" "$run_profile" "$run_model" "$run_task" "$outcome" "$run_proposal" "$elapsed" "$attempt" "${usage_before:-unknown}" "$usage_after" "$delta" "${mem_status:-na}" \
    >> "$LOG_DIR/cost.log"
}

refresh_scorecard() {
  # NUC-23: keep the box-safe digest current after every run (fail-soft; never
  # blocks or fails the run). The deployed scorecard is the runtime copy.
  local sc="$HOME/agent-workforce/bin/scorecard.sh"
  [ -x "$sc" ] || return 0
  "$sc" >>"$LOG_DIR/scorecard.log" 2>&1 || log "scorecard refresh failed (non-fatal)"
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

# ── NUC-23: resolve profile / model / task for the metrics record ──
run_profile="${AGENT_PROFILE:-}"
if [ -z "$run_profile" ]; then
  run_profile=$(printf '%s' "${AGENT_RUNTIME_CMD:-}" | grep -oE -- '-p[[:space:]]+[A-Za-z0-9_-]+' | awk '{print $2}' | tail -1 || true)
fi
run_profile="${run_profile:-unknown}"
run_task="${AGENT_TASK_SLUG:-standing}"
profile_cfg="$HOME/.hermes/profiles/$run_profile/config.yaml"
if [ -r "$profile_cfg" ]; then
  run_model=$(awk '/^model:/{m=1;next} /^[^[:space:]]/{m=0} m && /^[[:space:]]+name:/{sub(/#.*/,"");sub(/^[[:space:]]*name:[[:space:]]*/,"");gsub(/[[:space:]]/,"");print;exit}' "$profile_cfg")
fi
run_model="${run_model:-unknown}"

# ── NUC-21 working memory: snapshot the episodic store BEFORE the run so we can
#    tell afterward whether the agent recorded its own entry (fail-soft glue). ──
MEM_DIR="${RA_MEMORY_DIR:-$HOME/.hermes/profiles/$run_profile/memories}"
MEM_FILE="$MEM_DIR/MEMORY.md"
mem_before="absent"
[ -f "$MEM_FILE" ] && mem_before="$(cksum "$MEM_FILE" 2>/dev/null || echo absent)"

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
# NUC-27: snapshot the shared key's cumulative spend BEFORE any inference so the
# post-run delta in log_cost() captures exactly this run's cost (fail-soft:
# 'unknown' on any probe error — never blocks the run).
usage_before=$(key_usage)
log "cost: usage_before=$usage_before (shared OpenRouter key, USD)"
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
  refresh_scorecard
  exit 1
fi

# ── Write-boundary enforcement: only _inbox/agents/** may change ──
violations=$(git -C "$WORKTREE" status --porcelain | awk '{print $2}' | grep -v "^_inbox/agents/" || true)
if [ -n "$violations" ]; then
  log "FATAL: agent touched files outside _inbox/agents/ — discarding everything: $violations"
  git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  log_cost VIOLATION
  refresh_scorecard
  exit 1
fi

# ── NUC-21 working memory: record/verify the episodic entry (fail-soft) ──
# A proposal is a DATED markdown directly under _inbox/agents/; the metrics digest
# (_inbox/agents/_metrics/, owned by scorecard.sh) must NOT count as one.
proposal_file="$(git -C "$WORKTREE" status --porcelain -- _inbox/agents/ | awk '{print $2}' | grep -E '^_inbox/agents/[0-9]{4}-[0-9]{2}-[0-9]{2}_.*\.md$' | head -1 || true)"
mem_after="absent"; [ -f "$MEM_FILE" ] && mem_after="$(cksum "$MEM_FILE" 2>/dev/null || echo absent)"
if [ ! -d "$MEM_DIR" ]; then
  mem_status="no-store"
  log "MEMORY: no per-profile store at $MEM_DIR — skipping episodic record"
elif [ "$mem_after" != "$mem_before" ]; then
  mem_status="recorded"
  log "MEMORY: agent recorded its own episodic entry"
else
  entry="[run:$(date -Is)] task=standing claudius scheduled run; proposal=${proposal_file:-none}; note=runner auto-record (agent emitted no memory entry this run); findings/decisions/gaps=see agent_run.log / proposal"
  if (
        exec 8>"$MEM_FILE.lock" 2>/dev/null || exit 1
        flock -w 10 8 || exit 1
        if [ -s "$MEM_FILE" ]; then
          printf '%s\n§\n%s' "$(cat "$MEM_FILE")" "$entry" > "$MEM_FILE.tmp.$$" && mv -f "$MEM_FILE.tmp.$$" "$MEM_FILE"
        else
          printf '%s' "$entry" > "$MEM_FILE"
        fi
     ); then
    mem_status="fallback"
    log "MEMORY: agent did not record — wrote runner fallback entry (proposal=${proposal_file:-none})"
  else
    mem_status="record-failed"
    log "MEMORY: fallback record failed (lock/write) — store untouched, continuing"
  fi
fi

# ── Commit + push proposal (or end cleanly if the agent chose not to propose) ──
# A "proposal" is a DATED markdown file directly under _inbox/agents/. The metrics
# digest (_inbox/agents/_metrics/, written + committed separately by scorecard.sh)
# is deliberately EXCLUDED so a metrics refresh is never miscommitted as a proposal
# or miscounted as outcome=PROPOSAL. Only the matched proposal files are staged.
proposal_changes="$(git -C "$WORKTREE" status --porcelain -- _inbox/agents/ | awk '{print $2}' | grep -E '^_inbox/agents/[0-9]{4}-[0-9]{2}-[0-9]{2}_.*\.md$' || true)"
if [ -z "$proposal_changes" ]; then
  log "OK: run completed, agent produced no proposal"
  run_outcome=NOPROPOSAL
else
  run_proposal=$(printf '%s\n' "$proposal_changes" | head -1 | xargs -r -n1 basename | sed -E 's/\.md$//; s/^[0-9]{4}-[0-9]{2}-[0-9]{2}_//')
  run_proposal="${run_proposal:-unknown}"
  printf '%s\n' "$proposal_changes" | xargs -r git -C "$WORKTREE" add --
  git -C "$WORKTREE" commit -q -m "agent proposal $(date +%Y-%m-%d_%H%M)"
  git -C "$WORKTREE" push -q origin agents/inbox
  log "OK: proposal pushed to agents/inbox"
  run_outcome=PROPOSAL
fi

log_cost "$run_outcome"
refresh_scorecard
