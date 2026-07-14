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
set -uo pipefail
BIN="$(cd "$(dirname "$0")" && pwd)"
echo "== agent-inbox pipeline $(date -u +%FT%TZ) =="
rc=0
python3 "$BIN/agent_inbox_notion_sync.py"      || { echo "sync failed"; rc=1; }
python3 "$BIN/agent_inbox_apply.py" --apply    || { echo "apply failed"; rc=1; }
exit "$rc"
