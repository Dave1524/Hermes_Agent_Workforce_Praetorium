#!/usr/bin/env bash
# NUC-35: change-triggered content dispatch, at the shell layer.
#
# A deterministic, MODEL-FREE poll: every tick it asks Notion for the current
# "Picked" content-board page IDs, diffs them against a state file, and dispatches
# the existing Augustus draft run (bin/agent_propose.sh, same wiring the nightly
# augustus-content.timer uses) ONLY when a Picked ID appears that we have not seen
# before. On a quiet tick it spends nothing — no agent_propose.sh call, so no LLM,
# no cost.log line, no agent_run.log entry. This cuts Picked->Draft latency from
# the ~24h nightly cadence to ~15 min while keeping per-tick cost at zero.
#
# Fail-soft BY CONTRACT (matches notion_rest.py / key_usage): on ANY error querying
# or parsing Notion, log it and exit 0 WITHOUT touching STATE — a transient Notion
# outage must never corrupt state, drop a pending Picked row, or crash the timer.
# STATE is only advanced after a successful board read (empty diff) or after a
# dispatched run returns. The flock inside agent_propose.sh (/tmp/agent_propose.lock)
# makes an overlap with the 01:30 nightly run a clean SKIP — no double-draft.
set -euo pipefail

ROOT="${CONTENT_DISPATCH_ROOT:-$HOME/agent-workforce}"
NOTION_REST="${NOTION_REST_BIN:-$ROOT/bin/notion_rest.py}"
AGENT_PROPOSE="${AGENT_PROPOSE_BIN:-$ROOT/bin/agent_propose.sh}"
STATE="${CONTENT_PICKED_STATE:-$ROOT/var/content_picked.state}"
LOG_DIR="${LOG_DIR:-$ROOT/logs}"
AUGUSTUS_OVERRIDES="${AUGUSTUS_CONTENT_ENV:-$HOME/.config/agent-workforce/augustus-content.env}"

mkdir -p "$(dirname "$STATE")" 2>/dev/null || true
mkdir -p "$LOG_DIR" 2>/dev/null || true
log() { echo "$(date -Is) content_change_dispatch: $*" | tee -a "$LOG_DIR/content_change_dispatch.log"; }

# ── 1. Read current Picked page IDs (deterministic, model-free) ──
# board --status Picked --json prints a JSON array of {id, angle, status, url};
# extract ids, one sorted id per line. notion_rest.py exits non-zero on API error.
# --max-rows 0 (NUC-44): the tool's default cap of 2 is for the agent that has to draft
# them. This diff must see EVERY Picked row — a capped read would write a truncated set
# to STATE and mark the rows it never saw as seen, which is the bug this file guards.
current=""
if ! current=$(python3 "$NOTION_REST" board --status Picked --json --max-rows 0 2>>"$LOG_DIR/content_change_dispatch.log" \
    | python3 -c 'import json,sys
try:
    rows = json.load(sys.stdin)
except Exception as e:
    sys.stderr.write("parse error: %s\n" % e); sys.exit(1)
ids = sorted(r.get("id","") for r in rows if r.get("id"))
sys.stdout.write("\n".join(ids))
'); then
  # Any non-zero (Notion API error, network, or parse failure) => fail-soft.
  # STATE is left byte-for-byte untouched; a real Picked row is picked up next tick.
  log "FAIL-SOFT: could not read/parse Picked rows from Notion — exiting 0, state unchanged"
  exit 0
fi

# Normalize to a clean, sorted, newline-separated id list (may be empty).
current=$(printf '%s\n' "$current" | grep -v '^[[:space:]]*$' | sort -u || true)

# ── 2. Diff against stored state ──
# new IDs = current-set MINUS stored-set. grep -Fxv treats each stored id as a
# fixed whole-line pattern; anything in `current` not matched is new.
new_ids=""
if [ -f "$STATE" ]; then
  if [ -n "$current" ]; then
    new_ids=$(printf '%s\n' "$current" | grep -Fxv -f "$STATE" || true)
  fi
else
  # No state yet (first run / fresh deploy): treat every current Picked as new.
  new_ids="$current"
fi

# ── 3a. Empty diff => refresh state, spend nothing ──
if [ -z "$(printf '%s' "$new_ids" | tr -d '[:space:]')" ]; then
  log "no new Picked rows ($(printf '%s\n' "$current" | grep -c . || true) currently Picked) — refreshing state, no dispatch"
  printf '%s\n' "$current" | grep -v '^[[:space:]]*$' > "$STATE" || true
  exit 0
fi

# ── 3b. New Picked row(s) => dispatch the existing Augustus draft run ──
count=$(printf '%s\n' "$new_ids" | grep -c . || true)
log "detected $count new Picked row(s) — dispatching Augustus draft run via agent_propose.sh"

# Reuse the nightly wiring: agent_propose.sh sources secrets.env + this override
# itself and drafts up to 2 Picked rows. We do NOT source the override here.
export AGENT_JOB_OVERRIDES="$AUGUSTUS_OVERRIDES"
# NUC-44: mark where cost.log ends BEFORE dispatching, so the outcome check below reads
# only the record this dispatch produced and never an older one.
COST_LOG="${AGENT_COST_LOG:-$LOG_DIR/cost.log}"
cost_lines_before=$(wc -l < "$COST_LOG" 2>/dev/null || echo 0)
rc=0
"$AGENT_PROPOSE" || rc=$?
if [ "$rc" -ne 0 ]; then
  # agent_propose.sh is itself fail-soft (records its own cost.log/blocked outcome);
  # a non-zero here (e.g. flock SKIP returns 0, but a real failure) means we did NOT
  # confirm the Picked rows were drafted. Leave STATE untouched so the next tick
  # retries them rather than silently swallowing an undrafted Picked row.
  log "agent_propose.sh returned $rc — leaving state unchanged so new rows retry next tick"
  exit 0
fi

# ── 3c. Belt and braces: rc=0 is a CLAIM of success, the cost.log record is evidence ──
# The 2026-08-12 outage ran entirely through the rc=0 path: agent_propose.sh returned 0 on
# a run whose every hermes attempt had crashed, the guard above never fired, and 20 nights
# of Picked rows were marked seen without ever being drafted. Criterion (1)/(2) stop the
# false zero at its source; this check keeps state safe if a future runner regresses to it.
# awk (not `tail | grep`) so nothing in this pipeline can exit early — see CLAUDE.md.
crashed=$(awk -v skip="$cost_lines_before" \
  'NR > skip && /outcome=CRASHED/ { n++ } END { print n+0 }' "$COST_LOG" 2>/dev/null || echo 0)
if [ "${crashed:-0}" -gt 0 ]; then
  log "agent_propose.sh exited 0 but recorded outcome=CRASHED — leaving state unchanged so new rows retry next tick"
  exit 0
fi

# ── 4. Only after a successful dispatch, commit the new state ──
printf '%s\n' "$current" | grep -v '^[[:space:]]*$' > "$STATE" || true
log "dispatch complete — state advanced to current Picked set ($(printf '%s\n' "$current" | grep -c . || true) rows)"
exit 0
