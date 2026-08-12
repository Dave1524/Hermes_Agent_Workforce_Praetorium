#!/usr/bin/env bash
# kanban_run_and_wait.sh — NUC-25
# Runs a Hermes profile via the Kanban dispatcher (already ticking inside
# hermes-gateway.service, dispatch_interval_seconds=60) synchronously, so
# agent_propose.sh's existing retry/write-boundary/cost-log/memory wrapper can
# drop this in as a direct swap for a raw `hermes -z ... -p ...` call — none of
# that hardening lives in the Kanban worker lifecycle, so it must stay owned by
# the outer script. Creates one kanban task (idempotent per key), then blocks
# until it reaches a terminal status or the poll timeout elapses.
set -euo pipefail

HERMES="$HOME/.local/bin/hermes"
TASK_TITLE="${1:?title required}"
TASK_BODY_FILE="${2:?body file required}"
ASSIGNEE="${3:?assignee required}"
WORKSPACE_DIR="${4:?workspace dir required}"
IDEMPOTENCY_KEY="${5:?idempotency key required}"
MAX_RUNTIME="${6:-20m}"
POLL_INTERVAL_SECONDS="${POLL_INTERVAL_SECONDS:-15}"
POLL_TIMEOUT_SECONDS="${POLL_TIMEOUT_SECONDS:-1500}"   # 25min — stays under AGENT_TIMEOUT_MINUTES=30

# NUC-29: prepend a real-date banner to the task body so the agent uses the true system
# date (it otherwise guesses it, misdating proposals + day-count math). Honor the exported
# RUN_DATE from agent_propose.sh; self-compute if this wrapper is run standalone. The
# banner goes at the very top (ahead of the profile task file) and does NOT feed the
# idempotency key (arg 5), so dedup is unperturbed; within a day the banner is stable.
RUN_DATE="${RUN_DATE:-$(date +%Y-%m-%d)}"
DATE_BANNER="TODAY IS ${RUN_DATE} (real system date — use this EXACT date; do NOT guess it or infer it from context). Name any proposal file _inbox/agents/${RUN_DATE}_<slug>.md and base all day-count math on this date."
task_body="$(printf '%s\n\n%s' "$DATE_BANNER" "$(cat "$TASK_BODY_FILE")")"

task_json=$("$HERMES" kanban create "$TASK_TITLE" \
  --body "$task_body" \
  --assignee "$ASSIGNEE" \
  --workspace "dir:$WORKSPACE_DIR" \
  --idempotency-key "$IDEMPOTENCY_KEY" \
  --max-runtime "$MAX_RUNTIME" \
  --max-retries 2 \
  --json)
task_id=$(echo "$task_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "kanban_run_and_wait: task=$task_id created (idempotency-key=$IDEMPOTENCY_KEY)" >&2

# ── NUC-38: idempotent-hit detection ──
# A same-day re-dispatch returns the PRE-EXISTING, already-terminal card (the gateway
# dispatch interval is 60s, so a genuinely fresh card cannot be terminal at t≈0). A
# terminal status on the create response — or on an immediate show — therefore means the
# work already ran under today's key. Signal that distinctly with exit 3 (DEDUP) so the
# outer runner does NOT log a phantom NOPROPOSAL, write a fallback memory entry, or retry.
# NOTE: confirm the real hermes create JSON shape on the box — if it exposes an explicit
# idempotent/created flag or created_at, prefer that (unambiguous vs. a card that legit-
# imately blocks at t≈0). `|| echo unknown` keeps this fail-soft under set -euo pipefail:
# an undeterminable status falls through to the normal poll loop, never a false DEDUP.
DEDUP_EXIT=3
# NUC-44: a `blocked` card is only a benign decline when the AGENT authored the block.
# Hermes also parks a card at `blocked` after its own --max-retries are exhausted by
# runs that crashed, timed out, or gave up — the same terminal status for the opposite
# meaning. Signal that distinctly with exit 4 so the outer runner records CRASHED rather
# than a phantom NOPROPOSAL, and so content_change_dispatch.sh holds its state file.
CRASH_EXIT=4

# True only when at least one run carries outcome=blocked (the agent called kanban_block).
# Everything else on a blocked card — crashed, timed_out, gave_up, or no runs at all — is
# a masked failure. Enumerating the FAILURE outcomes instead would fail OPEN: a new
# outcome string would default to "benign decline", which is the exact bug being fixed
# here, so the check is written to fail CLOSED. An unreadable or unparseable payload is
# likewise treated as not-agent-authored: the expensive direction is certifying a crash
# as a decline, not costing one retry.
block_is_agent_authored() {
  "$HERMES" kanban show "$1" --json 2>/dev/null | python3 -c 'import json,sys
try:
    runs = (json.load(sys.stdin) or {}).get("runs") or []
except Exception:
    sys.exit(1)
sys.exit(0 if any(r.get("outcome") == "blocked" for r in runs) else 1)'
}

# One line per failed run, for the stderr report — the reason the card is parked is on
# the runs, not on the task (there is no block_reason field).
block_run_errors() {
  "$HERMES" kanban show "$1" --json 2>/dev/null | python3 -c 'import json,sys
try:
    runs = (json.load(sys.stdin) or {}).get("runs") or []
except Exception:
    sys.exit(0)
for r in runs:
    err = (r.get("error") or "").strip().replace("\n", " ")
    sys.stdout.write("  run %s: outcome=%s %s\n" % (r.get("id","?"), r.get("outcome"), err[:200]))' || true
}

initial_status=$(printf '%s' "$task_json" | python3 -c 'import json,sys
d=json.load(sys.stdin); t=d.get("task",d); print(t.get("status","unknown"))' 2>/dev/null || echo unknown)
if [ "$initial_status" = unknown ]; then
  initial_status=$("$HERMES" kanban show "$task_id" --json \
    | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])' 2>/dev/null || echo unknown)
fi
case "$initial_status" in
  done|blocked|archived)
    echo "kanban_run_and_wait: task=$task_id already terminal at dispatch (status=$initial_status, key=$IDEMPOTENCY_KEY) — idempotent hit, DEDUP (not a real run)" >&2
    exit "$DEDUP_EXIT"
    ;;
esac

elapsed=0
status="unknown"
while [ "$elapsed" -lt "$POLL_TIMEOUT_SECONDS" ]; do
  status=$("$HERMES" kanban show "$task_id" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')
  case "$status" in
    done)
      echo "kanban_run_and_wait: task=$task_id done" >&2
      exit 0
      ;;
    blocked)
      # NUC-25: an AGENT-AUTHORED block is a benign decline, not a runtime failure.
      # Hermes already exhausts its own --max-retries before ending a task
      # blocked, so the outer runner's 3x retry only repeats the identical block
      # and then marks the whole service failed. The old direct `hermes -z` path
      # counted "agent produced no proposal" as success — mirror that here. The
      # block reason is recorded on the card (hermes kanban show "$task_id").
      #
      # NUC-44: but `blocked` is ALSO where hermes parks a card whose runs all
      # crashed, and treating that as a decline masked 20 consecutive
      # augustus-content failures as outcome=NOPROPOSAL + exit 0. Only a card
      # carrying a real kanban_block still exits 0; a crash-parked card exits
      # CRASH_EXIT so the failure is legible all the way up.
      if block_is_agent_authored "$task_id"; then
        echo "kanban_run_and_wait: task=$task_id ended status=blocked — benign decline, not retried (reason on card: hermes kanban show $task_id)" >&2
        exit 0
      fi
      echo "kanban_run_and_wait: task=$task_id ended status=blocked with NO agent-authored block — every run crashed or was abandoned. This is a FAILURE, not a decline:" >&2
      block_run_errors "$task_id" >&2
      exit "$CRASH_EXIT"
      ;;
    archived)
      echo "kanban_run_and_wait: task=$task_id ended status=archived (cancelled) — no proposal, not a failure" >&2
      exit 0
      ;;
  esac
  sleep "$POLL_INTERVAL_SECONDS"
  elapsed=$((elapsed + POLL_INTERVAL_SECONDS))
done

echo "kanban_run_and_wait: task=$task_id timed out after ${POLL_TIMEOUT_SECONDS}s (status=$status)" >&2
exit 1
