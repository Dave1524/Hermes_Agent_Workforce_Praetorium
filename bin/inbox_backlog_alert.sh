#!/usr/bin/env bash
# NUC-30: alert Dave when the agent-inbox approval backlog ages out.
# Proposals accumulate in ~/agent-worktrees/inbox/_inbox/agents/ awaiting a
# Mac-side promote/reject (the box never decides — see docs/inbox_workflow.md).
# If the OLDEST pending proposal is > 2 days old, hand one line to bin/deliver.sh;
# stay SILENT when the inbox is clear or under threshold.
#
# Silence is the product here. An approvals channel that posts every morning
# whether or not anything is waiting is one nobody reads by the second week, so
# the threshold check stays in this adapter and deliver.sh is only reached on the
# days it has something to say.
#
# Backlog computation reuses bin/agent_inbox_notion_sync.py --count (NUC-45, 2026-08-10):
# a *.md file on disk is not necessarily still pending — the Mac-side promote/reject pass
# that clears a decided file can lag its Notion status update by days, so a raw file count
# overstates the backlog by exactly however many files are decided-but-uncleared. The sync
# script already knows Notion Status per file (it maintains it), so ask it instead of
# recounting locally. Falls back to the old raw count, clearly labeled approximate, if the
# sync script is unavailable (network/token) — this alert must never go silent on that.
# Fail-soft: exits 0 even on delivery error.
set -uo pipefail

DELIVERY_JOB="${DELIVERY_JOB:-inbox-backlog-alert.service}"
# shellcheck source=bin/delivery_common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/delivery_common.sh"

THRESHOLD_DAYS="${INBOX_BACKLOG_THRESHOLD_DAYS:-2}"
SYNC_SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agent_inbox_notion_sync.py"

inbox_dir="$HOME/agent-worktrees/inbox/_inbox/agents"
if [ ! -d "$inbox_dir" ]; then
  note "inbox worktree not present ($inbox_dir) — nothing to check"
  exit 0
fi

approx=0
pend="" oldest_date=""
if [ -r "$SYNC_SCRIPT" ]; then
  count_out=$(timeout 30 python3 "$SYNC_SCRIPT" --count 2>/dev/null) || count_out=""
  pend=$(printf '%s\n' "$count_out" | sed -n 's/^PENDING_COUNT=//p')
  oldest_date=$(printf '%s\n' "$count_out" | sed -n 's/^OLDEST_PENDING_DATE=//p')
fi
if [ -z "$pend" ]; then
  approx=1
  pend=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  oldest_date=""
fi

if [ "${pend:-0}" -eq 0 ]; then
  note "inbox clear (0 pending) — no alert"
  exit 0
fi

if [ -n "$oldest_date" ] && [ "$oldest_date" != none ]; then
  oldest_secs=$(date -d "$oldest_date" +%s 2>/dev/null || echo 0)
else
  # Approximate-mode fallback: oldest raw file mtime (may be a decided-but-uncleared file).
  oldest_line=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' -printf '%T@ %p\n' 2>/dev/null \
                  | sort -n | head -1)
  oldest_epoch=${oldest_line%% *}
  oldest_secs=${oldest_epoch%.*}
fi
now_secs=$(date +%s)
age_days=$(( (now_secs - oldest_secs) / 86400 ))

if [ "$age_days" -le "$THRESHOLD_DAYS" ]; then
  note "backlog under threshold (${pend} pending, oldest ${age_days}d <= ${THRESHOLD_DAYS}d, approx=${approx}) — no alert"
  exit 0
fi

approx_note=""
[ "$approx" -eq 1 ] && approx_note=" (approximate — Notion count unavailable, raw file count may overstate)"
msg="${pend} proposals pending, oldest ${age_days}d (awaiting Mac-side promote/reject)${approx_note}"
note "alerting: ${msg}"
delivery_handoff --subject '[Praetorium] Approvals aging' --message "$msg"

exit 0
