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

task_json=$("$HERMES" kanban create "$TASK_TITLE" \
  --body "$(cat "$TASK_BODY_FILE")" \
  --assignee "$ASSIGNEE" \
  --workspace "dir:$WORKSPACE_DIR" \
  --idempotency-key "$IDEMPOTENCY_KEY" \
  --max-runtime "$MAX_RUNTIME" \
  --max-retries 2 \
  --json)
task_id=$(echo "$task_json" | python3 -c 'import json,sys; print(json.load(sys.stdin)["id"])')
echo "kanban_run_and_wait: task=$task_id created (idempotency-key=$IDEMPOTENCY_KEY)" >&2

elapsed=0
status="unknown"
while [ "$elapsed" -lt "$POLL_TIMEOUT_SECONDS" ]; do
  status=$("$HERMES" kanban show "$task_id" --json | python3 -c 'import json,sys; print(json.load(sys.stdin)["task"]["status"])')
  case "$status" in
    done)
      echo "kanban_run_and_wait: task=$task_id done" >&2
      exit 0
      ;;
    blocked|archived)
      echo "kanban_run_and_wait: task=$task_id ended status=$status" >&2
      exit 1
      ;;
  esac
  sleep "$POLL_INTERVAL_SECONDS"
  elapsed=$((elapsed + POLL_INTERVAL_SECONDS))
done

echo "kanban_run_and_wait: task=$task_id timed out after ${POLL_TIMEOUT_SECONDS}s (status=$status)" >&2
exit 1
