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
#
# NUC-36: AGENT_RUN_MODE=proposal|ops (default proposal).
#   proposal — inbox worktree, write-boundary, commit/push, memory fallback.
#   ops      — lock/preflight/cost/scorecard only; no inbox checkout, no
#              write-boundary, no proposal commit, no memory fallback. For
#              overnight reports and other non-proposal LLM jobs folded off
#              Hermes cron onto this guarded runner.
set -euo pipefail

SECRETS="$HOME/.config/agent-workforce/secrets.env"
WORKTREE="$HOME/agent-worktrees/inbox"
LOG_DIR="$HOME/agent-workforce/logs"
LOCK="${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}"
mkdir -p "$LOG_DIR"
log() { echo "$(date -Is) $*" | tee -a "$LOG_DIR/agent_propose.log"; }

run_started=$(date +%s)
# Exported so AGENT_VERIFY_CMD can assert "the artifact is newer than THIS run"
# exactly (-newermt "@$AGENT_RUN_STARTED_AT") instead of guessing a freshness
# window that silently breaks the day someone changes AGENT_TIMEOUT_MINUTES.
export AGENT_RUN_STARTED_AT="$run_started"
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
  # NUC-37: on a BLOCKED early-exit usage_before was never snapshotted (still
  # 'unknown'), so the delta is 'unknown' regardless — skip the live OpenRouter GET.
  if [ "${usage_before:-unknown}" = unknown ]; then
    usage_after=unknown
  else
    usage_after=$(key_usage)
  fi
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
  # NUC-37: never let scorecard.sh's `mkdir -p $METRICS_DIR` recreate a MISSING inbox
  # worktree as a plain dir — that would silently defeat the [ -d "$WORKTREE" ] gate
  # on the next run. Skip the refresh when the worktree isn't a real git checkout.
  [ -e "$WORKTREE/.git" ] || { log "scorecard skip: inbox worktree absent"; return 0; }
  "$sc" >>"$LOG_DIR/scorecard.log" 2>&1 || log "scorecard refresh failed (non-fatal)"
}

block_exit() {
  # NUC-37: a preflight gate failed -> this run is BLOCKED, not "nothing to propose".
  # Record it (visible in cost.log + the scorecard) then exit 0 — blocked is not a
  # crash; the timer simply retries next cycle. log_cost/refresh_scorecard are
  # fail-soft. On the earliest gate (before secrets are sourced) key_usage() short-
  # circuits to 'unknown' with no network call and the record carries profile=unknown.
  log "BLOCKED: $1"
  log_cost BLOCKED
  refresh_scorecard
  exit 0
}

# NUC-31: fail-soft MCP daemon health probes (reuse the exact patterns in
# praetorium-status.sh — qmd :8765/health, brave :8766). A missing probe tool returns
# "healthy" so a box without curl/ss never blocks; curl is bounded by --max-time 2 so a
# hung daemon can't stall the run.
qmd_healthy() {
  command -v curl >/dev/null 2>&1 || return 0
  curl -sf --max-time 2 http://127.0.0.1:8765/health >/dev/null 2>&1
}
brave_healthy() {
  command -v ss >/dev/null 2>&1 || return 0
  # NOT `grep -q` (CLAUDE.md § Verification): -q exits on the first match, SIGPIPEs ss, and
  # under this script's `pipefail` the pipeline returns 141 — reporting the daemon DOWN while
  # it is up. Latent with a short socket table, live on a busy box.
  ss -ltn 2>/dev/null | grep ':8766' >/dev/null
}

exec 9>"$LOCK"
flock -n 9 || { log "SKIP: previous run still active"; exit 0; }

# ── Preflight: every gate must hold, else BLOCKED (recorded) with NO proposal (NUC-37) ──
# NOTE: the "previous run still active" SKIP at the flock above stays a SILENT exit —
# the lock is NOT held there (flock just failed), it is healthy timer overlap (the
# active run records its own outcome), and a cost.log append there is the one place it
# could race the live run's append. Do not convert that SKIP to a BLOCKED record.
[ -f "$SECRETS" ] || block_exit "secrets.env missing"
# shellcheck disable=SC1090
source "$SECRETS"
# NUC-24: optional per-job override (non-secret AGENT_TASK_SLUG/AGENT_RUNTIME_CMD only)
# so new job types (bd-stall-radar, weekly-pre-assembly, augustus-content) reuse this
# hardened runner (locking, retry, write-boundary enforcement, metrics, memory) without
# duplicating API keys across multiple secrets files. Sourced AFTER the canonical secrets,
# so it can only override task wiring, never credentials. (Reconciled into git from the
# deployed runtime; the missing-file gate now records BLOCKED via NUC-37's block_exit.)
if [ -n "${AGENT_JOB_OVERRIDES:-}" ]; then
  [ -f "$AGENT_JOB_OVERRIDES" ] || block_exit "AGENT_JOB_OVERRIDES set but file missing: $AGENT_JOB_OVERRIDES"
  # shellcheck disable=SC1090
  source "$AGENT_JOB_OVERRIDES"
fi
# NUC-36: default proposal; ops skips inbox/write-boundary/memory (see header).
run_mode="${AGENT_RUN_MODE:-proposal}"
case "$run_mode" in
  proposal|ops) ;;
  *) block_exit "AGENT_RUN_MODE must be proposal or ops (got: $run_mode)" ;;
esac
[ -n "${OPENROUTER_API_KEY:-}" ] || block_exit "no API key — no run (by design)"
if [ "$run_mode" = proposal ]; then
  [ -d "$WORKTREE" ] || block_exit "inbox worktree missing — run finish_boxsafe_clone.sh"
fi
[ -n "${AGENT_RUNTIME_CMD:-}" ] || block_exit "AGENT_RUNTIME_CMD not set (NUC-14 pending)"

# ── NUC-23: resolve profile / model / task for the metrics record ──
run_profile="${AGENT_PROFILE:-}"
if [ -z "$run_profile" ]; then
  run_profile=$(printf '%s' "${AGENT_RUNTIME_CMD:-}" | grep -oE -- '-p[[:space:]]+[A-Za-z0-9_-]+' | awk '{print $2}' | tail -1 || true)
fi
run_profile="${run_profile:-unknown}"
run_task="${AGENT_TASK_SLUG:-standing}"
profile_cfg="$HOME/.hermes/profiles/$run_profile/config.yaml"
if [ -r "$profile_cfg" ]; then
  # Every profile on the box (marcus/trajan/augustus/claudius) keys its model as
  # `default:` under `model:`, not `name:` — this parser looked for `name:` only and
  # silently resolved model=unknown on every one of them. Accept either key.
  run_model=$(awk '/^model:/{m=1;next} /^[^[:space:]]/{m=0} m && /^[[:space:]]+(name|default):/{sub(/#.*/,"");sub(/^[[:space:]]+(name|default):[[:space:]]*/,"");gsub(/[[:space:]]/,"");print;exit}' "$profile_cfg")
fi
run_model="${run_model:-unknown}"
log "mode: AGENT_RUN_MODE=$run_mode task=$run_task profile=$run_profile"

# ── NUC-31: preflight MCP tool-health gate (advisory by default) ──
# Placed AFTER profile/model resolution so a warn/block record carries the real
# profile+model, and BEFORE the git checkout/run loop so the agent never launches when
# blocked. Per-daemon policy: warn (log + proceed) | block (log BLOCKED via NUC-37 + no
# run) | off (skip the probe). Defaults are warn-only for BOTH daemons — a daemon outage
# is visible in the run log but never blocks a run; flip to block with a one-word change.
# Per-job opt-out: eight of the eleven runners exec with `--strict-mcp-config
# --mcp-config '{"mcpServers":{}}'` and so reach NO MCP daemon at all. Probing qmd/brave
# for those jobs logs a WARN naming a dependency the job does not have, which is how they
# came to be read as "hard-blocked on the qmd daemon" in review. AGENT_MCP_DEPS=none, set
# in the job's override env, opts a job out of both probes. It supplies a DEFAULT only —
# an explicit QMD_HEALTH_POLICY/BRAVE_HEALTH_POLICY in that same env still wins, so this
# can never silently downgrade a policy someone set deliberately. Unset = unchanged.
AGENT_MCP_DEPS="${AGENT_MCP_DEPS:-}"
if [ "$AGENT_MCP_DEPS" = none ]; then
  QMD_HEALTH_POLICY="${QMD_HEALTH_POLICY:-off}"
  BRAVE_HEALTH_POLICY="${BRAVE_HEALTH_POLICY:-off}"
  log "MCP probes: skipped (AGENT_MCP_DEPS=none — job declares no MCP dependency)"
elif [ -n "$AGENT_MCP_DEPS" ]; then
  # Fail OPEN on a typo, but say so: an unrecognised value probes as normal rather than
  # silently opting out. 'none' is the only value that skips.
  log "WARN: AGENT_MCP_DEPS='$AGENT_MCP_DEPS' unrecognised (only 'none' skips) — probing as normal"
fi
QMD_HEALTH_POLICY="${QMD_HEALTH_POLICY:-warn}"     # warn | block | off
BRAVE_HEALTH_POLICY="${BRAVE_HEALTH_POLICY:-warn}" # warn | block | off
if [ "$QMD_HEALTH_POLICY" != off ] && ! qmd_healthy; then
  if [ "$QMD_HEALTH_POLICY" = block ]; then
    block_exit "qmd MCP daemon down (http://127.0.0.1:8765/health) — no vault retrieval"
  else
    log "WARN: qmd MCP daemon down (policy=warn) — proceeding without vault retrieval"
  fi
fi
if [ "$BRAVE_HEALTH_POLICY" != off ] && ! brave_healthy; then
  if [ "$BRAVE_HEALTH_POLICY" = block ]; then
    block_exit "brave MCP endpoint down (127.0.0.1:8766) — no web search"
  else
    log "WARN: brave MCP endpoint down (policy=warn) — proceeding without web search"
  fi
fi

# ── NUC-21 working memory: snapshot the episodic store BEFORE the run so we can
#    tell afterward whether the agent recorded its own entry (fail-soft glue).
#    NUC-36 ops mode skips memory entirely (mem_status stays na). ──
MEM_DIR="${RA_MEMORY_DIR:-$HOME/.hermes/profiles/$run_profile/memories}"
MEM_FILE="$MEM_DIR/MEMORY.md"
mem_before="absent"
if [ "$run_mode" = proposal ]; then
  [ -f "$MEM_FILE" ] && mem_before="$(cksum "$MEM_FILE" 2>/dev/null || echo absent)"
  git -C "$WORKTREE" checkout -q agents/inbox
  git -C "$WORKTREE" pull -q --ff-only origin agents/inbox 2>/dev/null || true
fi

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
# No runtime produces exit 3 since the kanban path was retired (2026-09-02, D7). The
# bucket stays because ~/agent-workforce/logs/cost.log holds one historical outcome=DEDUP
# row (2026-08-13T01:33:57+02:00) that bin/scorecard.sh:51-56 must keep classifying.
DEDUP_EXIT=3
# NUC-44: the live producer is bin/run_content_via_buzz.sh (:40,48 — `crash()`), which
# exits 4 when the dispatch itself failed rather than the agent declining. Re-attributed
# 2026-09-02: this said kanban_run_and_wait.sh, which no longer exists, and a boundary
# credited to a deleted script is the §2/§6.1 defect D3 found. The vocab is the point —
# recorded as NOPROPOSAL a crash read as "the agent had nothing to say" for 20 consecutive
# augustus-content nights, and a generic FAIL is indistinguishable from a transport fault.
CRASH_EXIT=4
max_attempts="${AGENT_MAX_ATTEMPTS:-3}"
ok=false; is_dedup=false; is_crash=false; rc=0
# ── Silent-failure detection: a zero exit is NOT evidence the work happened ──
# hermes exits 0 when the agent's FINAL RESPONSE is itself a provider error. The
# error is caught inside the agent loop and emitted as response text, so
# hermes_cli/oneshot.py sees "a response was produced" and returns 0. HARD failures
# (unknown provider, context-floor rejection) do exit non-zero and were always
# handled correctly — these are the ones that slipped through.
# Observed 2026-07-21: an HTTP 400 model-ID error and an ollama empty-stream error
# each logged "OK: ops run completed" having produced no report at all. Because
# deliver_report.sh then re-posts the newest surviving artifact, one silent failure
# re-delivers a stale report for up to 26h (see the 4x repeat of 07-17 in
# ~/logs/deliver_report.log). Two independent checks, either of which fails the run:
#   1. did the run END on a provider error   (catches the observed cases)
#   2. did the job's own artifact appear     (AGENT_VERIFY_CMD — catches the class)
PROVIDER_ERROR_RE='^(HTTP [45][0-9]{2}:|API call failed after [0-9]+ retries:|Provider returned an empty stream)'
# Tail-only: a fatal provider error is the last thing hermes emits, whereas an agent
# REPORT may legitimately quote such a string out of a journal it was summarising.
run_ended_on_provider_error() {
  tail -n "${AGENT_ERROR_TAIL_LINES:-5}" "$1" 2>/dev/null | grep -qE "$PROVIDER_ERROR_RE"
}
# NUC-29: stamp the real date once, exported so the kanban wrapper (and any future
# direct hermes -z path) share ONE value — no midnight-rollover mismatch between the two
# scripts. RUN_DATE feeds the proposal filename + day-count math; TODAY is the human form.
export RUN_DATE="${RUN_DATE:-$(date +%Y-%m-%d)}"
export TODAY="${TODAY:-$(date '+%A, %-d %B %Y')}"
log "date: RUN_DATE=$RUN_DATE"
# NUC-27: snapshot the shared key's cumulative spend BEFORE any inference so the
# post-run delta in log_cost() captures exactly this run's cost (fail-soft:
# 'unknown' on any probe error — never blocks the run).
usage_before=$(key_usage)
log "cost: usage_before=$usage_before (shared OpenRouter key, USD)"
while [ "$attempt" -lt "$max_attempts" ]; do
  attempt=$((attempt + 1))
  rc=0
  log "run attempt $attempt/$max_attempts: $run_cmd"
  # Captured per-attempt (then appended to the shared log as before) so the
  # silent-failure scan sees THIS attempt's tail, not the whole history.
  attempt_out=$(mktemp "${TMPDIR:-/tmp}/agent_propose_out.XXXXXX")
  timeout "${AGENT_TIMEOUT_MINUTES:-30}m" bash -lc "$run_cmd" \
    >"$attempt_out" 2>&1 || rc=$?
  cat "$attempt_out" >>"$LOG_DIR/agent_run.log"
  if [ "$rc" -eq 0 ] && run_ended_on_provider_error "$attempt_out"; then
    rc=90
    log "SILENT-FAIL: exit 0 but the run ended on a provider error — recording FAIL"
  fi
  if [ "$rc" -eq 0 ] && [ -n "${AGENT_VERIFY_CMD:-}" ] && ! bash -lc "$AGENT_VERIFY_CMD"; then
    rc=91
    log "SILENT-FAIL: exit 0 but AGENT_VERIFY_CMD found no artifact — recording FAIL"
  fi
  rm -f "$attempt_out"
  if [ "$rc" -eq 0 ]; then ok=true; break; fi
  # NUC-38: a distinct DEDUP exit (idempotent kanban hit — the card already ran under
  # today's key) is not a failure and must not be retried.
  if [ "$rc" -eq "$DEDUP_EXIT" ]; then is_dedup=true; break; fi
  # NUC-44: a crash-parked card is a failure, but a diagnosed one — record it as such and
  # stop, rather than re-running work hermes has already retried into the ground.
  if [ "$rc" -eq "$CRASH_EXIT" ]; then is_crash=true; break; fi
  # Only back off when another attempt will actually follow — never hold the
  # flock sleeping after the FINAL failed attempt (dead 270s/30s wait).
  [ "$attempt" -lt "$max_attempts" ] && sleep $((retry_base * attempt * attempt))   # 30s, 120s backoff by default
done

# ── NUC-38: idempotent hit — not a real run. No proposal, no memory fallback, no retry,
#    and no worktree reset (the wrapper only queried the API; any prior same-key run
#    already committed its own proposal). Record outcome=DEDUP and exit clean. Must come
#    BEFORE the FAIL branch: is_dedup sets ok=false but is not a failure. ──
if $is_dedup; then
  log "DEDUP: kanban idempotent hit — card already terminal for today's key; no run recorded"
  run_outcome=DEDUP; run_proposal=none; mem_status=na
  log_cost DEDUP
  refresh_scorecard
  exit 0
fi

if ! $ok; then
  # NUC-44: same handling as any failure (non-zero exit, worktree reset), but a crash the
  # runtime already diagnosed gets its own outcome so cost.log, the scorecard and the
  # morning report can tell "it broke" from "it failed for an unknown reason".
  if $is_crash; then
    fail_outcome=CRASHED
    fail_reason="CRASHED: runtime reported a crashed run (exit $CRASH_EXIT) — see the wrapper's run errors above"
  else
    fail_outcome=FAIL
    fail_reason="FAIL: runtime failed after $max_attempts attempts"
  fi
  if [ "$run_mode" = proposal ]; then
    log "$fail_reason — resetting worktree, NO proposal emitted"
    git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  else
    log "$fail_reason (ops mode — no worktree reset)"
  fi
  log_cost "$fail_outcome"
  refresh_scorecard
  exit 1
fi

# ── NUC-36 ops mode: runtime succeeded; no inbox write-boundary / commit / memory ──
if [ "$run_mode" = ops ]; then
  log "OK: ops run completed (no proposal path)"
  run_outcome=OPS
  run_proposal=none
  mem_status=na
  log_cost OPS
  refresh_scorecard
  exit 0
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
