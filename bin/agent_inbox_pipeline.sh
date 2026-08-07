#!/usr/bin/env bash
# agent_inbox_pipeline.sh — deterministic Notion<->agent-inbox reconcile.
#
# Replaces the glm-5.2 `agent-inbox-sync` LLM cron (jobs.json 98e6eb41f553), which was
# needlessly running an LLM to execute a fully-specified algorithm and failing on the
# exhausted OpenRouter budget. This pipeline is model-free and budget-independent:
#   1. sync  (box -> Notion): create a row for every new _inbox/agents/*.md proposal;
#            reflect Mac-side promote/reject outcomes (approvals.tsv) back into Notion.
#   2. apply (Notion -> box): auto-execute REJECTED within the box-safe membrane
#            (archive + remove + push agents/inbox); surface APPROVED as a Mac hand-off
#            (canonical promotion stays a Mac judgment write, by the vault boundary).
#
# The run's output is also written to the runtime log tree, because ExecStopPost cannot
# see ExecStart's stdout and the journal is not a delivery surface. It goes to
# ~/agent-workforce/logs and never beside this script: the source checkout is swept into
# git by the auto-sync timer every 15 minutes.
set -uo pipefail
BIN="$(cd "$(dirname "$0")" && pwd)"
OUT="${AGENT_INBOX_OUTPUT:-$HOME/agent-workforce/logs/agent_inbox_pipeline.last}"

reconcile() {
  echo "== agent-inbox pipeline $(date -u +%FT%TZ) =="
  local rc=0
  python3 "$BIN/agent_inbox_notion_sync.py"      || { echo "sync failed"; rc=1; }
  python3 "$BIN/agent_inbox_apply.py" --apply    || { echo "apply failed"; rc=1; }
  return "$rc"
}

mkdir -p "$(dirname "$OUT")"
reconcile 2>&1 | tee "$OUT"
exit "${PIPESTATUS[0]}"
