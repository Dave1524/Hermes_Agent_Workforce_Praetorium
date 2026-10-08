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
# Working memory (NUC-21) was a per-profile MEMORY.md the runner backstopped; retired
# at T6.1 (2026-09-16) — the receipt (T5.2) is the per-run record, memory=na on every row.
#
# NUC-36: AGENT_RUN_MODE=proposal|ops (default proposal).
#   proposal — inbox worktree, write-boundary, commit/push.
#   ops      — lock/preflight/cost/scorecard only; no inbox checkout, no
#              write-boundary, no proposal commit. For
#              overnight reports and other non-proposal LLM jobs folded off
#              Hermes cron onto this guarded runner.
#   board    — ops-style, plus a card: the pick (AGENT_BOARD_PICK) is required and a quiet
#              tick is a receipted skip before any model. The run's one output is
#              $AGENT_CARD_DIR/brief.out.md, which the wrapper records as the card's `brief`
#              event after the model exits (design: agent-board-refinement §3.6.3).
set -euo pipefail

SECRETS="$HOME/.config/agent-workforce/secrets.env"
WORKTREE="$HOME/agent-worktrees/inbox"
LOG_DIR="$HOME/agent-workforce/logs"
LOCK="${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}"
mkdir -p "$LOG_DIR"
# The graft Claude Code hooks (~/.claude/settings.json, user scope, since 2026-09-11) write
# their index and per-session telemetry into the session's cwd — this worktree — and the Stop
# hook does it from a detached process that outlives the run, so the write boundary below saw
# `graft/` and discarded the first resumed run (2026-09-15). GRAFT_DIR moves every graft write
# out of the worktree; the kill switches stop it indexing the vault or touching the root
# .gitignore/.ignore. Runtime state, so under var/ and never deployed over.
export GRAFT_DIR="$HOME/agent-workforce/var/graft"
export GRAFT_NO_SEED=1 GRAFT_NO_REFRESH=1 GRAFT_NO_GITIGNORE=1 GRAFT_NO_IGNORE=1
log() { echo "$(date -Is) $*" | tee -a "$LOG_DIR/agent_propose.log"; }

run_started=$(date +%s)
# Exported so AGENT_VERIFY_CMD can assert "the artifact is newer than THIS run"
# exactly (-newermt "@$AGENT_RUN_STARTED_AT") instead of guessing a freshness
# window that silently breaks the day someone changes AGENT_TIMEOUT_MINUTES.
export AGENT_RUN_STARTED_AT="$run_started"
# One run id, resolved before any pre-flight so a card's `picked` event and the receipt name the
# same run: propose_receipt.py already prefers AGENT_RUN_ID over INVOCATION_ID.
export AGENT_RUN_ID="${AGENT_RUN_ID:-${INVOCATION_ID:-hand-$run_started}}"
attempt=0
# NUC-23 metrics fields (resolved after secrets are sourced); NUC-21 memory field.
run_profile="unknown"
run_owner="unknown"
run_model="unknown"
run_task="standing"
run_proposal="none"
run_outcome="NOPROPOSAL"
mem_status="na"
# Which limit, if any, ended the run (none|attempt|deadline|unit), and whether the loaded budget
# fits the unit's TimeoutStartSec (fit|misfit|unknown) — bin/propose_budget.py owns the sum.
run_timeout="none"
budget_state="unknown"
cost_logged=false
# T6.1 (2026-09-16): the shared OpenRouter key probe is retired. The Hermes runtime was its
# only spender and its delta read 0.000000 on 344 of 353 rows; usage is measured per run in
# the receipt (T5.2). cost.log keeps the keys with `unknown`.
usage_before="unknown"

new_session_id() {
  # T3.3: one Claude Code session id per ATTEMPT, so the transcript log_cost reads is the
  # one this attempt wrote and a retry never inherits its predecessor's evidence.
  uuidgen 2>/dev/null || python3 -c 'import uuid; print(uuid.uuid4())'
}

skill_telemetry() {
  # T3.3: which pointer skills this attempt was offered / invoked / read, from its Claude
  # Code transcript located BY SESSION ID (never mtime): the Claude runners pass
  # AGENT_SESSION_ID as --session-id and the CLI persists <id>.jsonl under
  # ~/.claude/projects/<cwd-slug>/ — the glob across projects/*/ is what makes the lookup
  # owner-agnostic. Sets tel_skills / tel_offered / tel_src. Fail-soft by contract: no
  # session (BLOCKED), no transcript (hermes, codex-acp, a claude that never started) or
  # an extractor error all record unknown/unknown/none and say why.
  # The extractor is resolved as a SIBLING of this script, not the deployed copy
  # refresh_scorecard() uses, so the smoke test's sandboxed $HOME still reaches it.
  tel_skills=unknown tel_offered=unknown tel_src=none
  [ -n "${AGENT_SESSION_ID:-}" ] || return 0
  local extractor transcripts out rc=0 err
  extractor="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skill_telemetry.py"
  transcripts=("$HOME"/.claude/projects/*/"$AGENT_SESSION_ID".jsonl)
  [ -f "${transcripts[0]}" ] || { log "skills: no transcript for session $AGENT_SESSION_ID — recording unknown"; return 0; }
  err="$LOG_DIR/skill_telemetry.err"
  out=$(python3 "$extractor" "${transcripts[0]}" 2>"$err") || rc=$?
  if [ "$rc" -ne 0 ]; then
    log "skills: telemetry failed (extractor exit $rc: $(head -c 200 "$err" 2>/dev/null | tr -d '\n')) — recording unknown"
    return 0
  fi
  local offered=unknown invoked=unknown read=unknown t
  for t in $out; do
    case "$t" in
      offered=*) offered=${t#*=} ;;
      invoked=*) invoked=${t#*=} ;;
      read=*)    read=${t#*=} ;;
    esac
  done
  if [ "$offered" = unknown ] || [ "$invoked" = unknown ] || [ "$read" = unknown ]; then
    log "skills: telemetry failed (unparseable extractor output: $out) — recording unknown"
    return 0
  fi
  tel_offered=$offered
  tel_skills=$(printf '%s,%s\n' "$invoked" "$read" | tr ',' '\n' | awk 'NF && $0 != "none"' | sort -u | paste -sd, -)
  [ -n "$tel_skills" ] || tel_skills=none
  tel_src=transcript
  log "skills: offered=$offered invoked=$invoked read=$read src=$tel_src"
}

log_cost() {
  # Structured, append-only, key=value (NUC-23). model is the PROFILE's real
  # config.yaml model.name — NOT LLM_MODEL_BUSINESS (which was stale, echoing
  # sonnet-5 while the profile runs haiku-4.5).
  # usage_before / usage_after / cost_usd_delta are `unknown` on every row since T6.1:
  # the shared-key probe (NUC-27) measured a spend nothing on this runtime makes. The
  # keys stay so every reader (scorecard.sh, run_record.sh) keeps parsing; the receipt
  # (T5.2) carries measured usage. tokens stay 'unknown' for the same reason.
  # Written on FAIL/VIOLATION too so failure loops stay visible.
  local outcome=$1
  local elapsed=$(( $(date +%s) - run_started ))
  local usage_after delta
  usage_after=unknown
  delta=$(python3 -c 'import sys
a,b=sys.argv[1],sys.argv[2]
try:
    print(f"{float(a)-float(b):.6f}")
except Exception:
    print("unknown")' "$usage_after" "${usage_before:-unknown}" 2>/dev/null) || delta="unknown"
  [ -n "$delta" ] || delta="unknown"
  # T3.3: three more keys, schema unchanged — every reader is key-based (scorecard.sh,
  # deliver_proposal.sh `field`) and nothing branches on the schema value.
  #   skills=<csv|none|unknown>          invoked ∪ read, sorted
  #   skills_offered=<csv|none|unknown>  the skill_listing, namespace-filtered
  #   skills_src=transcript|none         none <=> unknown <=> no transcript for the session
  skill_telemetry
  printf 'ts=%s schema=3 profile=%s model=%s task=%s outcome=%s proposal=%s run_seconds=%s attempts=%s tokens=unknown usage_before=%s usage_after=%s cost_usd_delta=%s cost_src=openrouter-key-api memory=%s skills=%s skills_offered=%s skills_src=%s timeout=%s budget=%s\n' \
    "$(date -Is)" "$run_profile" "$run_model" "$run_task" "$outcome" "$run_proposal" "$elapsed" "$attempt" "${usage_before:-unknown}" "$usage_after" "$delta" "${mem_status:-na}" "$tel_skills" "$tel_offered" "$tel_src" "$run_timeout" "$budget_state" \
    >> "$LOG_DIR/cost.log"
  cost_logged=true
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

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
write_receipt() {
  # T5.2: one receipt per run, on every exit path, through bin/propose_receipt.py -> the
  # contract executor. Fail-soft by construction: the receipt is evidence about the run and
  # must never become the run's outcome, so this function returns 0 whatever the adapter
  # does, and the exit that follows it is the one the script would have taken anyway. The
  # adapter's own stdout is the executor's check table, kept in agent_propose.log.
  local outcome=$1; shift
  local rc=0 out
  out="$(AGENT_CARD_BRIEF_HASH="${card_brief_hash:-}" python3 "$BIN_DIR/propose_receipt.py" "$outcome" "$@" 2>&1)" || rc=$?
  printf '%s\n' "$out" | tee -a "$LOG_DIR/agent_propose.log"
  # The executor exits 1 for a written receipt whose checks failed, so its status alone
  # cannot tell a failed verdict from a broken adapter; the `receipt: <path>` line it
  # prints on every write can.
  if [ "$rc" -ne 0 ]; then
    if [ -n "$(printf '%s\n' "$out" | grep '^receipt: /')" ]; then
      log "receipt: written, verdict failed (exit $rc) — the run's own outcome stands"
    else
      log "receipt: not written (propose_receipt.py exit $rc) — the run's own outcome stands"
    fi
  fi
  return 0
}

block_exit() {
  # NUC-37: a preflight gate failed -> this run is BLOCKED, not "nothing to propose".
  # Record it (visible in cost.log + the scorecard) then exit 0 — blocked is not a
  # crash; the timer simply retries next cycle. log_cost/refresh_scorecard are
  # fail-soft. On the earliest gate (before secrets are sourced) the record carries
  # profile=unknown.
  log "BLOCKED: $1"
  log_cost BLOCKED
  write_receipt BLOCKED --reason "$1"
  refresh_scorecard
  exit 0
}

auth_down_exit() {
  # A run that cannot authenticate never started: skipped, not failed, and the cause is the
  # shared auth-expired incident rather than one alarm per workflow. BLOCKED in cost.log, the
  # vocabulary scorecard.sh already excludes from the proposal rate.
  log "SKIP: $1"
  log_cost BLOCKED
  write_receipt AUTHDOWN --reason "$1"
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
flock -n 9 || { log "SKIP: previous run still active"; write_receipt SKIP; exit 0; }

unit_terminated() {
  # systemd's TimeoutStartSec kill sends SIGTERM to the whole cgroup. Before 2026-10-06 that
  # left no cost.log row and no receipt, so the run was invisible to the scorecard. Record it
  # here unless the run already recorded itself, in which case let that record finish.
  $cost_logged && return 0
  run_timeout=unit
  local why="systemd terminated the run after $(( $(date +%s) - run_started ))s, during attempt $attempt/${max_attempts:-?}"
  log "TIMEOUT: $why"
  log_cost FAIL
  write_receipt FAIL --rc 143 --reason "timeout=unit: $why"
  exit 143
}
trap unit_terminated TERM

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
  proposal|ops|board) ;;
  *) block_exit "AGENT_RUN_MODE must be proposal, ops or board (got: $run_mode)" ;;
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
# T7.1 (2026-09-10): the run boundary needs a name. agent_run.log is one stream shared by
# every job, so a DECLINE: line in it belongs to nobody in particular — on 2026-09-09
# bd-followup-drafts passed its AGENT_VERIFY_CMD on a decline bd-stall-radar had written
# 27 minutes earlier, having produced nothing itself. This attempt's own output, at a path
# keyed by task, is the only thing that can answer "did THIS run of THIS job decline?".
# ExecStartPost inherits no export from the run, so the path must be derivable from the
# task slug rather than merely passed down.
export AGENT_ATTEMPT_LOG="${AGENT_ATTEMPT_LOG:-$LOG_DIR/last-attempt/$run_task.log}"
# T5.2: where bin/cc_run.sh leaves the Claude Code JSON envelope for the receipt's usage and
# cost. Per attempt like the log above; a hermes runtime writes nothing here and the receipt
# says `unavailable`, never a number from cost.log's shared-key delta.
export AGENT_USAGE_JSON="${AGENT_USAGE_JSON:-$LOG_DIR/last-attempt/$run_task.usage.json}"
# W1 (2026-09-02): the owner is the OWNING PERSONA (design/agents/<owner>.toml); the cost
# record keys on the RUNTIME. They were one variable once, and AGENT_PROFILE has been
# model-named (claude-opus / claude-sonnet) since the 2026-07-30 migration. Do NOT merge
# them back: `profile=` in cost.log is what makes a model regression visible, and
# bin/run_record.sh:37 reads it back as the runtime. The fallback is the runtime name.
run_owner="${AGENT_OWNER:-$run_profile}"
# model= is `unknown` since T6.1 (2026-09-16): it was resolved from a hermes profile config,
# which no live job runs — augustus-content rows logged openai/gpt-5.5 from a profile the
# buzz-agent runtime never used. The receipt (T5.2) carries the measured model.
run_model=unknown
verify_state=unset
[ -n "${AGENT_VERIFY_CMD:-}" ] && verify_state=set
log "mode: AGENT_RUN_MODE=$run_mode task=$run_task profile=$run_profile owner=$run_owner verify=$verify_state"
# verify= is the only place a job's AGENT_VERIFY_CMD wiring is visible from outside the
# deny-listed env tree: the command itself prints nothing on success, so an unset one
# (D2, m1_signal_scan.env) was indistinguishable from a passing one.

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

# T5.3f: the requires pre-flight. The unit systemd is running is the manifest entry whose
# `requires` applies — the identity bin/propose_receipt.py::unit_name resolves — and the
# verdict is bin/workflow_requires.py's: exit 1 names the first requirement known down and
# this run is BLOCKED like any other failed gate; unknown is not a refusal. A hand run with
# no unit skips it out loud. WORKFLOW_REQUIRES overrides the CLI for fixtures.
requires_unit="${AGENT_RECEIPT_UNIT:-${DELIVERY_JOB:-}}"; requires_unit="${requires_unit%.service}"
if [ -z "$requires_unit" ]; then
  log "requires pre-flight skipped: no unit (AGENT_RECEIPT_UNIT and DELIVERY_JOB unset)"
else
  requires_rc=0
  requires_out=$("${WORKFLOW_REQUIRES:-$BIN_DIR/workflow_requires.py}" check "$requires_unit" 2>&1) || requires_rc=$?
  while IFS= read -r requires_line; do
    [ -n "$requires_line" ] && log "$requires_line"
  done <<<"$requires_out"
  if [ "$requires_rc" -ne 0 ]; then
    block_exit "${requires_out##*$'\n'}"
  fi
fi

# The board pick (Dev Plan B2). Opt-in by AGENT_BOARD_PICK, e.g. "--owner claudius --kind research
# --column backlog"; the override env's variables never reach the model, so the three exports
# below are the whole card-side environment a profile may name. Board mode requires a card;
# elsewhere AGENT_BOARD_REQUIRED=1 asks for the same. No card is a receipted skip, never a
# model run. The workflow is the unit the receipt is filed under, because that is the path
# board.py joins a pick to its outcome by.
BOARD_PY="${BOARD_PY:-$BIN_DIR/board.py}"
card_events_file() { echo "$BOARD_ROOT/cards/$AGENT_CARD/events.jsonl"; }
card_ledger_lines() { if [ -f "$(card_events_file)" ]; then wc -l < "$(card_events_file)"; else echo 0; fi; }
pick_card() {
  [ "$run_mode" = board ] && [ -z "${AGENT_BOARD_PICK:-}" ] && block_exit "AGENT_RUN_MODE=board needs AGENT_BOARD_PICK"
  [ -n "${AGENT_BOARD_PICK:-}" ] || return 0
  local picked rc=0 workflow
  workflow="${requires_unit:-$run_task}"
  export BOARD_ROOT="${BOARD_ROOT:-${CONTROL_ROOM_BOARD_ROOT:-/var/lib/control-room-board}}"
  # shellcheck disable=SC2086  # AGENT_BOARD_PICK is a flag list by contract
  picked=$(python3 "$BOARD_PY" pick $AGENT_BOARD_PICK --run-id "$AGENT_RUN_ID" --workflow "$workflow") || rc=$?
  [ "$rc" -eq 0 ] || block_exit "board pick failed (exit $rc)"
  if [ -z "$picked" ]; then
    if [ "$run_mode" = board ] || [ "${AGENT_BOARD_REQUIRED:-0}" = 1 ]; then
      log "SKIP: no card for: $AGENT_BOARD_PICK"
      write_receipt SKIP --reason "no card for: $AGENT_BOARD_PICK"
      exit 0
    fi
    log "board: no card — proceeding card-less"
    return 0
  fi
  export AGENT_CARD="$picked" AGENT_CARD_DIR="$BOARD_ROOT/runs/$AGENT_RUN_ID"
  card_brief_hash=$(card_field brief_hash)
  mkdir -p "$AGENT_CARD_DIR"
  printf '{"card": "%s", "run_id": "%s", "brief_hash": "%s"}\n' "$AGENT_CARD" "$AGENT_RUN_ID" "$card_brief_hash" \
    > "$AGENT_CARD_DIR/pick.json"
  log "board: picked card $AGENT_CARD for run $AGENT_RUN_ID (brief ${card_brief_hash:-none})"
}
# One field of the picked card's view (`board.py show --json`); empty when the verb or the field is absent.
card_field() {  # card_field <brief_hash|title>
  python3 "$BOARD_PY" show "$AGENT_CARD" --json 2>/dev/null | python3 -c '
import json, sys
try:
    view = json.load(sys.stdin)
except ValueError:
    sys.exit(0)
key = sys.argv[1]
print(view.get(key) or (view.get("fields") or {}).get(key) or "")' "$1" || true
}
card_brief_hash=""
pick_card
# A card picked in proposal mode is a research run: the model works in the card's directory, the
# wrapper publishes its one file as the card's page, and the inbox is never checked out or written.
card_run=false
if [ "$run_mode" = proposal ] && [ -n "${AGENT_CARD:-}" ]; then card_run=true; fi
NOTION_RESEARCH_PY="${NOTION_RESEARCH_PY:-$BIN_DIR/notion_research.py}"

# The claude-auth pre-flight (2026-10-05). An expired login fails every Claude Code runner at
# once, and each run used to retry into it three times and receipt its own `failed`: 14
# incidents for one cause between 09-30 and 10-05. A refusal is now a skipped run naming the
# dependency plus the one shared auth-expired incident; a pass closes that incident; unknown
# (timeout, network) proceeds, because a blip must not read as an expired login. Only runtimes
# that are Claude Code runners are probed. CLAUDE_AUTH_PROBE overrides the probe for fixtures.
case "$AGENT_RUNTIME_CMD" in
  *_cc.sh*)
    auth_rc=0
    auth_out=$("${CLAUDE_AUTH_PROBE:-$BIN_DIR/claude_auth_probe.sh}" 2>&1) || auth_rc=$?
    log "${auth_out:-claude-auth: probe printed nothing (exit $auth_rc)}"
    case $auth_rc in
      0) "$BIN_DIR/claude_auth_incident.sh" close ;;
      3) "$BIN_DIR/claude_auth_incident.sh" open "$auth_out"; auth_down_exit "$auth_out" ;;
    esac
    ;;
esac

# The NUC-21 episodic store (~/.hermes/profiles/<owner>/memories) is retired (T6.1);
# mem_status stays na on every run.
if [ "$run_mode" = proposal ] && ! $card_run; then
  git -C "$WORKTREE" checkout -q agents/inbox
  git -C "$WORKTREE" pull -q --ff-only origin agents/inbox 2>/dev/null || true
fi

# After a request for changes the page already exists, Dave's edits in it: the model revises that
# rather than starting over. --if-exists makes a first run (no page yet) write nothing; a Notion
# failure is the run's failure, never a silent first draft over Dave's edits.
if $card_run; then
  export_rc=0
  python3 "$NOTION_RESEARCH_PY" export --card "$AGENT_CARD" --out "$AGENT_CARD_DIR/research.prev.md" --if-exists \
    >/dev/null 2>>"$LOG_DIR/agent_propose.log" || export_rc=$?
  if [ "$export_rc" -ne 0 ]; then
    log "FAIL: notion_research.py export refused for card $AGENT_CARD (exit $export_rc)"
    log_cost FAIL
    write_receipt FAIL --rc "$export_rc" --reason "notion_research.py export refused the page for card $AGENT_CARD"
    refresh_scorecard
    exit 1
  fi
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
# Produced by AGENT_VERIFY_CMD (bin/proposal_or_decline.sh) since 2026-09-17 when the
# profile's own `skip: today's … already exists` line ends the run: the run already
# happened, so this is not a failure and must not be retried. No runtime has produced it
# since the kanban path was retired (2026-09-02, D7); ~/agent-workforce/logs/cost.log holds
# one historical outcome=DEDUP row (2026-08-13T01:33:57+02:00) that bin/scorecard.sh:51-56
# must keep classifying.
DEDUP_EXIT=3
# NUC-44: the live producer is bin/run_content_via_buzz.sh (:40,48 — `crash()`), which
# exits 4 when the dispatch itself failed rather than the agent declining. Re-attributed
# 2026-09-02: this said kanban_run_and_wait.sh, which no longer exists, and a boundary
# credited to a deleted script is the §2/§6.1 defect D3 found. The vocab is the point —
# recorded as NOPROPOSAL a crash read as "the agent had nothing to say" for 20 consecutive
# augustus-content nights, and a generic FAIL is indistinguishable from a transport fault.
CRASH_EXIT=4
max_attempts="${AGENT_MAX_ATTEMPTS:-3}"
timeout_minutes="${AGENT_TIMEOUT_MINUTES:-30}"
# Only a failure this fast is retried. A slow failure is an upstream stall the retry rarely
# beats (2026-10-06: attempt 1 hung on a 196s call, attempt 2 saw 126s ones), and its retry is
# what used to outrun the unit's TimeoutStartSec.
retry_within="${AGENT_RETRY_WITHIN_SECONDS:-300}"
# Kept back from the unit's limit for preflight and the ExecStartPost delivery.
budget_reserve="${AGENT_BUDGET_RESERVE_SECONDS:-180}"
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
for knob in max_attempts timeout_minutes retry_base retry_within budget_reserve; do
  [[ "${!knob}" =~ ^[0-9]+$ ]] || block_exit "time budget: $knob must be a whole number (got: ${!knob})"
done
deadline=""
check_budget() {
  # From the values this run actually loaded: the live overrides are deny-listed to every
  # agent, so a budget that cannot fit its unit is only ever visible here. A misfit runs, but
  # clamped to the unit's deadline so the run records its own end instead of being killed.
  local out rc=0 field remaining=unknown
  out=$(python3 "$BIN_DIR/propose_budget.py" check --attempts "$max_attempts" \
    --timeout-min "$timeout_minutes" --retry-base "$retry_base" --retry-within "$retry_within" \
    --reserve "$budget_reserve" --unit "${DELIVERY_JOB:-}" 2>&1) || rc=$?
  if [ "$rc" -ne 0 ]; then
    log "BUDGET: check failed (exit $rc: ${out##*$'\n'}) — running unclamped"
    return 0
  fi
  for field in $out; do
    case "$field" in
      budget=*)    budget_state=${field#*=} ;;
      remaining=*) remaining=${field#*=} ;;
    esac
  done
  log "BUDGET: $out"
  [ "$remaining" = unknown ] || deadline=$(( $(date +%s) + remaining - budget_reserve ))
  case "$budget_state" in
    misfit)
      log "BUDGET MISFIT: $max_attempts x ${timeout_minutes}m (retry within ${retry_within}s, backoff base ${retry_base}s) cannot fit ${DELIVERY_JOB:-the unit}'s TimeoutStartSec — attempts are clamped to its deadline"
      budget_incident declare "$out" ;;
    fit) budget_incident resolve ;;
  esac
}
budget_incident() {
  # Fail-soft, like claude_auth_incident.sh: bookkeeping never changes the run's outcome.
  local workflow="${DELIVERY_JOB%.service}"
  [ -n "$workflow" ] || return 0
  if [ "$1" = declare ]; then
    python3 "$BIN_DIR/workflow_incidents.py" declare --class failed-assertion --workflow "$workflow" \
      --id budget-misfit --issue "time budget misfit: $2" \
      --action "Set this job's AGENT_MAX_ATTEMPTS / AGENT_TIMEOUT_MINUTES / AGENT_RETRY_WITHIN_SECONDS in ~/.config/agent-workforce to the committed example (profiles/*.env.example), or grow the unit; bin/propose_budget.py check shows the sum" \
      >/dev/null 2>&1 || log "BUDGET: could not declare the budget-misfit incident"
  else
    python3 "$BIN_DIR/workflow_incidents.py" resolve --key "failed-assertion:$workflow:budget-misfit" >/dev/null 2>&1 || true
  fi
}
attempt_limit_seconds() {
  local limit=$((timeout_minutes * 60)) left
  [ -n "$deadline" ] || { echo "$limit"; return 0; }
  left=$(( deadline - $(date +%s) ))
  [ "$left" -ge 1 ] || left=1
  echo $(( left < limit ? left : limit ))
}
retry_fits() {
  [ -z "$deadline" ] || [ $(( $(date +%s) + $1 + timeout_minutes * 60 )) -le "$deadline" ]
}

# NUC-29: stamp the real date once, exported so this script and whatever it execs share ONE
# value — no midnight-rollover mismatch between them. Written for the kanban wrapper, which
# is gone (D7, 2026-09-02); it still matters because the AGENT_VERIFY_CMD and four task
# profiles read it: proposal_or_decline.sh:25 builds the filename it asserts from RUN_DATE,
# and daily_plan / eod_summary / both standing_research profiles take it with a `date`
# fallback. So an unexported RUN_DATE does not fail — it silently disagrees across midnight.
# TODAY is the human form and is read only here.
export RUN_DATE="${RUN_DATE:-$(date +%Y-%m-%d)}"
export TODAY="${TODAY:-$(date '+%A, %-d %B %Y')}"
log "date: RUN_DATE=$RUN_DATE"
check_budget
ledger_before=0
[ -z "${AGENT_CARD:-}" ] || ledger_before=$(card_ledger_lines)
ledger_grew() {
  # The model never writes the ledger: growth during the model phase is the same VIOLATION as a
  # write outside the boundary. The offending lines are moved aside, not deleted, so the
  # incident can name what was attempted.
  [ -n "${AGENT_CARD:-}" ] || return 1
  local file now
  file=$(card_events_file); now=$(card_ledger_lines)
  [ "$now" -gt "$ledger_before" ] || return 1
  mkdir -p "$AGENT_CARD_DIR"
  tail -n +$((ledger_before + 1)) "$file" >> "$AGENT_CARD_DIR/rejected-events.jsonl"
  head -n "$ledger_before" "$file" > "$file.keep" && mv "$file.keep" "$file"
  log "FATAL: the model wrote $((now - ledger_before)) event(s) to card $AGENT_CARD's ledger — moved to rejected-events.jsonl"
  return 0
}
while [ "$attempt" -lt "$max_attempts" ]; do
  attempt=$((attempt + 1))
  rc=0
  attempt_limit=$(attempt_limit_seconds)
  [ "$attempt_limit" -ge $((timeout_minutes * 60)) ] || log "attempt $attempt clamped to ${attempt_limit}s by the unit's deadline"
  # T3.3: exported so the runner's `--session-id` and log_cost's transcript lookup agree on
  # ONE id, minted per attempt so a retry's record carries the attempt whose outcome it is.
  AGENT_SESSION_ID="$(new_session_id)"
  export AGENT_SESSION_ID
  log "run attempt $attempt/$max_attempts session=$AGENT_SESSION_ID: $run_cmd"
  # Captured per-attempt (then appended to the shared log as before) so the
  # silent-failure scan sees THIS attempt's tail, not the whole history. Kept after the
  # run rather than removed: AGENT_VERIFY_CMD reads it in-process and deliver_proposal.sh
  # reads it from ExecStartPost, long after a mktemp file would have been gone.
  attempt_out="$AGENT_ATTEMPT_LOG"
  mkdir -p "$(dirname "$attempt_out")"
  : > "$attempt_out"
  rm -f "$AGENT_USAGE_JSON"
  [ "$run_mode" != board ] || rm -f "$AGENT_CARD_DIR/brief.out.md"
  ! $card_run || rm -f "$AGENT_CARD_DIR/research.md"
  attempt_started=$(date +%s)
  timeout --kill-after=30 "${attempt_limit}s" bash -lc "$run_cmd" \
    >"$attempt_out" 2>&1 || rc=$?
  attempt_seconds=$(( $(date +%s) - attempt_started ))
  cat "$attempt_out" >>"$LOG_DIR/agent_run.log"
  if ledger_grew; then
    log_cost VIOLATION
    write_receipt VIOLATION --reason "wrote the card ledger during the model phase"
    refresh_scorecard
    exit 1
  fi
  if { [ "$rc" -eq 124 ] || [ "$rc" -eq 137 ]; } && [ "$attempt_seconds" -ge "$attempt_limit" ]; then
    run_timeout=attempt
    timeout_detail="attempt $attempt/$max_attempts hit the ${attempt_limit}s limit after ${attempt_seconds}s"
    log "TIMEOUT: $timeout_detail"
    break
  fi
  if [ "$rc" -eq 0 ] && run_ended_on_provider_error "$attempt_out"; then
    rc=90
    log "SILENT-FAIL: exit 0 but the run ended on a provider error — recording FAIL"
  fi
  if [ "$rc" -eq 0 ] && [ -n "${AGENT_VERIFY_CMD:-}" ]; then
    verify_rc=0
    bash -lc "$AGENT_VERIFY_CMD" || verify_rc=$?
    if [ "$verify_rc" -eq "$DEDUP_EXIT" ]; then
      rc=$DEDUP_EXIT
      log "DEDUP: AGENT_VERIFY_CMD found this run's idempotent skip — today's artifact already exists"
    elif [ "$verify_rc" -ne 0 ]; then
      rc=91
      log "SILENT-FAIL: exit 0 but AGENT_VERIFY_CMD found no artifact — recording FAIL"
    fi
  fi
  if [ "$rc" -eq 0 ]; then ok=true; break; fi
  # NUC-38: a distinct DEDUP exit (the run already happened under today's key) is not a
  # failure and must not be retried.
  if [ "$rc" -eq "$DEDUP_EXIT" ]; then is_dedup=true; break; fi
  # NUC-44: a crash-parked card is a failure, but a diagnosed one — record it as such and
  # stop, rather than re-running work hermes has already retried into the ground.
  if [ "$rc" -eq "$CRASH_EXIT" ]; then is_crash=true; break; fi
  [ "$attempt" -lt "$max_attempts" ] || break
  if [ "$attempt_seconds" -gt "$retry_within" ]; then
    log "no retry: attempt $attempt failed (rc $rc) after ${attempt_seconds}s, slower than AGENT_RETRY_WITHIN_SECONDS=$retry_within"
    break
  fi
  backoff=$((retry_base * attempt * attempt))   # 30s, 120s by default
  if ! retry_fits "$backoff"; then
    run_timeout=deadline
    timeout_detail="no room for attempt $((attempt + 1))/$max_attempts: it needs ${backoff}s backoff + $((timeout_minutes * 60))s, $(( deadline - $(date +%s) ))s left before the unit's deadline"
    log "TIMEOUT: $timeout_detail"
    break
  fi
  # Only back off when another attempt will actually follow — never hold the
  # flock sleeping after the FINAL failed attempt (dead 270s/30s wait).
  sleep "$backoff"
done

# ── NUC-38: idempotent hit — not a real run. No proposal, no memory fallback, no retry,
#    and no worktree reset (the wrapper only queried the API; any prior same-key run
#    already committed its own proposal). Record outcome=DEDUP and exit clean. Must come
#    BEFORE the FAIL branch: is_dedup sets ok=false but is not a failure. ──
if $is_dedup; then
  log "DEDUP: idempotent hit — today's artifact already exists; no run recorded"
  run_outcome=DEDUP; run_proposal=none; mem_status=na
  log_cost DEDUP
  write_receipt DEDUP
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
  elif [ "$run_timeout" != none ]; then
    fail_outcome=FAIL
    fail_reason="FAIL: timeout — $timeout_detail"
  else
    fail_outcome=FAIL
    fail_reason="FAIL: runtime failed after $max_attempts attempts"
    [ "$attempt" -eq "$max_attempts" ] || fail_reason="FAIL: runtime failed after $attempt of $max_attempts attempts (no retry)"
  fi
  if [ "$run_mode" = proposal ]; then
    log "$fail_reason — resetting worktree, NO proposal emitted"
    git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  else
    log "$fail_reason (ops mode — no worktree reset)"
  fi
  log_cost "$fail_outcome"
  if [ "$run_timeout" != none ]; then
    write_receipt "$fail_outcome" --rc "$rc" --reason "timeout=$run_timeout: $timeout_detail"
  else
    write_receipt "$fail_outcome" --rc "$rc"
  fi
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
  write_receipt OPS
  refresh_scorecard
  exit 0
fi

# ── board mode: the run's one output is the card's brief; the wrapper, not the model, records it ──
if [ "$run_mode" = board ]; then
  brief_file="$AGENT_CARD_DIR/brief.out.md"
  if [ -f "$brief_file" ] && [ -n "$(find "$AGENT_CARD_DIR" -maxdepth 1 -name brief.out.md -newermt "@$AGENT_RUN_STARTED_AT")" ]; then
    brief_rc=0
    brief_hash=$(python3 "$BOARD_PY" brief "$AGENT_CARD" --from-file "$brief_file" --actor "run:$AGENT_RUN_ID") || brief_rc=$?
    if [ "$brief_rc" -ne 0 ]; then
      log "FAIL: board.py refused the brief for $AGENT_CARD (exit $brief_rc)"
      log_cost FAIL
      write_receipt FAIL --rc "$brief_rc" --reason "board.py brief refused the text for card $AGENT_CARD"
      refresh_scorecard
      exit 1
    fi
    log "OK: board run recorded brief ${brief_hash} for card $AGENT_CARD"
    run_outcome=BOARD
    run_proposal="$AGENT_CARD"
    log_cost BOARD
    write_receipt BOARD --brief-hash "$brief_hash"
  else
    log "OK: board run declined card $AGENT_CARD"
    run_outcome=NOPROPOSAL
    log_cost NOPROPOSAL
    write_receipt NOPROPOSAL
  fi
  refresh_scorecard
  exit 0
fi

# ── card run: the run's one output is research.md; the wrapper, not the model, publishes it ──
if $card_run; then
  dirty=$(git -C "$WORKTREE" status --porcelain)
  if [ -n "$dirty" ]; then
    log "FATAL: a card run touched the inbox mirror — discarding everything: $dirty"
    git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
    log_cost VIOLATION
    write_receipt VIOLATION --reason "a card run wrote to the inbox mirror"
    refresh_scorecard
    exit 1
  fi
  research_file="$AGENT_CARD_DIR/research.md"
  if [ -f "$research_file" ] && [ -n "$(find "$AGENT_CARD_DIR" -maxdepth 1 -name research.md -newermt "@$AGENT_RUN_STARTED_AT")" ]; then
    publish_rc=0
    published=$(python3 "$NOTION_RESEARCH_PY" publish --card "$AGENT_CARD" --from-file "$research_file" \
      --title "$(card_field title)" --run-id "$AGENT_RUN_ID" 2>>"$LOG_DIR/agent_propose.log") || publish_rc=$?
    if [ "$publish_rc" -ne 0 ]; then
      log "FAIL: notion_research.py publish refused the page for card $AGENT_CARD (exit $publish_rc)"
      log_cost FAIL
      write_receipt FAIL --rc "$publish_rc" --reason "notion_research.py publish refused the page for card $AGENT_CARD"
      refresh_scorecard
      exit 1
    fi
    page=$(printf '%s' "$published" | python3 -c 'import json,sys; print(json.load(sys.stdin)["page"])')
    page_hash=$(printf '%s' "$published" | python3 -c 'import json,sys; print(json.load(sys.stdin)["page_hash"])')
    printf '{"card": "%s", "run_id": "%s", "page": "%s", "page_hash": "%s", "brief_hash": "%s"}\n' \
      "$AGENT_CARD" "$AGENT_RUN_ID" "$page" "$page_hash" "$(card_field brief_hash)" > "$AGENT_CARD_DIR/published.json"
    log "OK: card run published page $page (${page_hash}) for card $AGENT_CARD"
    run_outcome=CARD
    run_proposal="$AGENT_CARD"
    log_cost CARD
    write_receipt CARD --page "$page" --page-hash "$page_hash"
  else
    log "OK: card run declined card $AGENT_CARD"
    run_outcome=NOPROPOSAL
    log_cost NOPROPOSAL
    write_receipt NOPROPOSAL
  fi
  refresh_scorecard
  exit 0
fi

# ── Write-boundary enforcement: only _inbox/agents/** may change ──
violations=$(git -C "$WORKTREE" status --porcelain | awk '{print $2}' | grep -v "^_inbox/agents/" || true)
if [ -n "$violations" ]; then
  log "FATAL: agent touched files outside _inbox/agents/ — discarding everything: $violations"
  git -C "$WORKTREE" reset --hard -q && git -C "$WORKTREE" clean -fdq
  log_cost VIOLATION
  write_receipt VIOLATION
  refresh_scorecard
  exit 1
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
if [ "$run_outcome" = PROPOSAL ]; then
  write_receipt PROPOSAL --proposal "$(printf '%s\n' "$proposal_changes" | head -1)"
else
  write_receipt NOPROPOSAL
fi
refresh_scorecard
