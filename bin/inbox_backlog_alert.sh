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
# Backlog computation mirrors bin/praetorium-status.sh (NUC-26 block): count
# *.md files at depth 1 (the _metrics/ digest dir is excluded by -maxdepth 1)
# and take the oldest mtime. Fail-soft: exits 0 even on delivery error.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DELIVER_BIN="${DELIVER_BIN:-$BIN_DIR/deliver.sh}"

THRESHOLD_DAYS="${INBOX_BACKLOG_THRESHOLD_DAYS:-2}"
ROUTE="${DELIVERY_ROUTE:-unrouted}"

log="$HOME/logs/inbox_backlog_alert.log"
mkdir -p "$HOME/logs" 2>/dev/null || true
note() {
  printf '%s inbox_backlog_alert: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    >> "$log" 2>/dev/null || true
}

inbox_dir="$HOME/agent-worktrees/inbox/_inbox/agents"
if [ ! -d "$inbox_dir" ]; then
  note "inbox worktree not present ($inbox_dir) — nothing to check"
  exit 0
fi

pend=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
if [ "${pend:-0}" -eq 0 ]; then
  note "inbox clear (0 pending) — no alert"
  exit 0
fi

oldest_line=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' -printf '%T@ %p\n' 2>/dev/null \
                | sort -n | head -1)
oldest_epoch=${oldest_line%% *}     # first field: mtime epoch (secs.frac)
oldest_secs=${oldest_epoch%.*}      # strip fractional part
now_secs=$(date +%s)
age_days=$(( (now_secs - oldest_secs) / 86400 ))

if [ "$age_days" -le "$THRESHOLD_DAYS" ]; then
  note "backlog under threshold (${pend} pending, oldest ${age_days}d <= ${THRESHOLD_DAYS}d) — no alert"
  exit 0
fi

msg="${pend} proposals pending, oldest ${age_days}d (awaiting Mac-side promote/reject)"
if "$DELIVER_BIN" \
     --job "${DELIVERY_JOB:-inbox-backlog-alert.service}" \
     --route "$ROUTE" \
     --subject '[Praetorium] Approvals aging' \
     --message "$msg"; then
  note "alerted: ${msg}"
else
  note "alert delivery failed (non-fatal): ${msg}"
fi

exit 0
