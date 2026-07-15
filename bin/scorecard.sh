#!/usr/bin/env bash
# NUC-23 agent-run scorecard: roll the append-only cost.log into an aggregate,
# de-identified digest published to the box-safe repo (same channel as proposals).
#
# Fail-soft (never hard-fails, never blocks a run), idempotent (identical input ->
# byte-identical digest, zero git churn), box-safe (aggregate counts only — no
# proposal slugs, no client-identifiable strings, no _confidential content).
# Cost truth is the OpenRouter dashboard; hermes token/$ accounting is unreliable
# (#4404/#20741) so tokens/cost are best-effort 'unknown' here — never fabricated.
set -uo pipefail   # NOT -e: every failure is swallowed so a run is never blocked

LOG_DIR="${SCORECARD_LOG_DIR:-$HOME/agent-workforce/logs}"
COST_LOG="${SCORECARD_COST_LOG:-$LOG_DIR/cost.log}"
WORKTREE="${SCORECARD_WORKTREE:-$HOME/agent-worktrees/inbox}"
METRICS_DIR="${SCORECARD_METRICS_DIR:-$WORKTREE/_inbox/agents/_metrics}"
DIGEST="${SCORECARD_DIGEST:-$METRICS_DIR/scorecard.md}"
APPROVALS="${SCORECARD_APPROVALS:-$METRICS_DIR/approvals.tsv}"
PUSH="${SCORECARD_PUSH:-1}"
LOCK="${SCORECARD_LOCK:-/tmp/scorecard.lock}"
BRANCH="${SCORECARD_BRANCH:-agents/inbox}"

# ── Own lock (fd 8 — separate from agent_propose's fd 9); skip if busy/unavailable ──
if command -v flock >/dev/null 2>&1; then
  exec 8>"$LOCK" 2>/dev/null || { echo "scorecard: cannot open lock — skip"; exit 0; }
  flock -n 8 || { echo "scorecard: another rollup running — skip"; exit 0; }
fi

# ── Roll up the append-only run log ──
cutoff=$(date -d '7 days ago' +%s 2>/dev/null || echo 0)
runs=0 runs7d=0 sum_seconds=0
proposals=0 noproposals=0 fails=0 violations=0 legacy=0 blocked=0 dedup=0 ops=0
first_ts="" last_ts=""

if [ -r "$COST_LOG" ]; then
  while IFS= read -r line || [ -n "$line" ]; do
    [ -n "$line" ] || continue
    declare -A kv=()
    bare_ts=""
    read -ra toks <<< "$line"
    for t in "${toks[@]}"; do
      case "$t" in
        *=*) kv["${t%%=*}"]="${t#*=}" ;;
        *)   [ -z "$bare_ts" ] && bare_ts="$t" ;;
      esac
    done
    # A line is a run record ONLY if run_seconds is all-digits (skips noise + malformed).
    rs="${kv[run_seconds]:-}"
    case "$rs" in
      ''|*[!0-9]*) unset kv; continue ;;
    esac
    # NUC-37/38: BLOCKED (preflight/health gate) and DEDUP (idempotent kanban hit) are
    # NOT real agent runs — no inference happened. Count them in their own buckets and
    # exclude from runs / proposal-rate / avg-duration / the 7-day window.
    case "${kv[outcome]:-}" in
      BLOCKED) blocked=$(( blocked + 1 )); unset kv; continue ;;
      DEDUP)   dedup=$(( dedup + 1 ));     unset kv; continue ;;
    esac
    # NUC-36: OPS (non-proposal guarded runs) are real inference but not proposal
    # jobs — count duration/window, keep a separate bucket, exclude from proposal rate.
    if [ "${kv[outcome]:-}" = OPS ]; then
      ops=$(( ops + 1 ))
      runs=$(( runs + 1 ))
      sum_seconds=$(( sum_seconds + rs ))
      ts="${kv[ts]:-$bare_ts}"
      [ -z "$first_ts" ] && first_ts="$ts"
      last_ts="$ts"
      if [ -n "$ts" ]; then
        ep=$(date -d "$ts" +%s 2>/dev/null || echo 0)
        [ "$ep" -ge "$cutoff" ] && runs7d=$(( runs7d + 1 ))
      fi
      unset kv
      continue
    fi
    runs=$(( runs + 1 ))
    sum_seconds=$(( sum_seconds + rs ))
    ts="${kv[ts]:-$bare_ts}"
    [ -z "$first_ts" ] && first_ts="$ts"
    last_ts="$ts"
    if [ -n "$ts" ]; then
      ep=$(date -d "$ts" +%s 2>/dev/null || echo 0)
      [ "$ep" -ge "$cutoff" ] && runs7d=$(( runs7d + 1 ))
    fi
    case "${kv[outcome]:-}" in
      PROPOSAL)   proposals=$(( proposals + 1 )) ;;
      NOPROPOSAL) noproposals=$(( noproposals + 1 )) ;;
      FAIL)       fails=$(( fails + 1 )) ;;
      VIOLATION)  violations=$(( violations + 1 )) ;;
      *)          legacy=$(( legacy + 1 )) ;;
    esac
    unset kv
  done < "$COST_LOG"
fi
errors=$(( fails + violations ))
# Proposal rate denominator excludes OPS (and already excludes BLOCKED/DEDUP).
proposal_denom=$(( proposals + noproposals + fails + violations + legacy ))

# ── Approval outcomes (AC2 feed; Mac-written approvals.tsv, box reads it) ──
promoted=0 rejected=0 edited=0 approvals_present=0
if [ -r "$APPROVALS" ]; then
  approvals_present=1
  # grep -c prints exactly one number (0 on no match); no `|| echo 0` — that would
  # double to "0\n0" on no-match (grep prints 0 AND exits 1) and break the arithmetic.
  promoted=$(grep -c 'decision=promoted' "$APPROVALS" 2>/dev/null); promoted=${promoted:-0}
  rejected=$(grep -c 'decision=rejected' "$APPROVALS" 2>/dev/null); rejected=${rejected:-0}
  edited=$(grep -c 'decision=edited' "$APPROVALS" 2>/dev/null); edited=${edited:-0}
fi
decisions=$(( promoted + rejected + edited ))

pct() { if [ "${2:-0}" -le 0 ]; then echo "n/a"; else echo "$(( $1 * 100 / $2 ))%"; fi; }

proposal_rate="n/a"
[ "$proposal_denom" -gt 0 ] && proposal_rate="$(pct "$proposals" "$proposal_denom") ($proposals/$proposal_denom)"
if [ "$approvals_present" -eq 1 ] && [ "$decisions" -gt 0 ]; then
  approval_rate="$(pct "$promoted" "$decisions")"
  approvals_cell="$promoted / $rejected / $edited"
else
  approval_rate="pending (awaiting Mac sync)"
  approvals_cell="pending (awaiting Mac sync)"
fi
avg_dur="n/a"
[ "$runs" -gt 0 ] && avg_dur="$(( sum_seconds / runs ))s"
# NOTE: box uptime is deliberately NOT embedded as a live value — a wall-clock field
# would break the idempotent/zero-churn contract (identical cost.log -> byte-identical
# digest). Infra health (incl. uptime) lives in praetorium-status.sh (NUC-18) — link,
# don't duplicate (per the NUC-23 brief's out-of-scope note).
[ -n "$first_ts" ] || first_ts="(none)"
[ -n "$last_ts" ] || last_ts="(none)"

# ── Write the digest (data-derived header => idempotent) ──
mkdir -p "$METRICS_DIR" 2>/dev/null || { echo "scorecard: cannot create $METRICS_DIR — skip"; exit 0; }
tmp="$(mktemp "${TMPDIR:-/tmp}/scorecard.XXXXXX")" || { echo "scorecard: mktemp failed — skip"; exit 0; }
{
  echo "# Agent Run Scorecard — Praetorium"
  echo
  echo "_As of last recorded run: ${last_ts}_"
  echo
  echo "> De-identified, box-safe aggregate — no proposal contents, no client-identifiable"
  echo "> data. Actual \$ spend: **OpenRouter dashboard is the source of truth** (hermes token"
  echo "> accounting is unreliable, #4404/#20741). Infra health: see \`praetorium-status.sh\` (NUC-18)."
  echo
  echo "| Signal | Value |"
  echo "|---|---|"
  echo "| Agent runs (last 7d) | ${runs7d} |"
  echo "| Agent runs (all-time) | ${runs} |"
  echo "| Proposals produced | ${proposals} |"
  echo "| Proposal rate | ${proposal_rate} |"
  echo "| No-proposal runs | ${noproposals} |"
  echo "| Ops runs (non-proposal, NUC-36) | ${ops} |"
  echo "| Blocked runs (preflight/health gate) | ${blocked} |"
  echo "| Deduplicated dispatches (idempotent) | ${dedup} |"
  echo "| Error runs (fail/violation) | ${errors} (${fails} fail / ${violations} violation) |"
  echo "| Approvals promoted / rejected / edited | ${approvals_cell} |"
  echo "| Approval rate | ${approval_rate} |"
  echo "| Inference served | 0% local / 100% remote |"
  echo "| Cost per run | best-effort: unknown (see OpenRouter dashboard) |"
  echo "| Avg run duration | ${avg_dur} |"
  echo "| Box uptime | see praetorium-status.sh (NUC-18) |"
  echo "| Record window | ${first_ts} → ${last_ts} |"
  if [ "$legacy" -gt 0 ]; then
    echo
    echo "_Note: ${legacy} pre-NUC-23 record(s) counted as runs with unknown proposal status (legacy \`outcome=OK\`)._"
  fi
} > "$tmp" 2>/dev/null || { rm -f "$tmp"; echo "scorecard: digest write failed — skip"; exit 0; }

if [ -f "$DIGEST" ] && cmp -s "$tmp" "$DIGEST"; then
  rm -f "$tmp"
else
  mv -f "$tmp" "$DIGEST" 2>/dev/null || { rm -f "$tmp"; echo "scorecard: install failed — skip"; exit 0; }
fi

# ── Publish to the box-safe repo (fail-soft; timeouts so a run never hangs) ──
# Use -e not -d: the inbox is a git WORKTREE whose ".git" is a FILE (gitdir
# pointer), not a directory — [ -d ] would be false and silently skip the push.
if [ "$PUSH" = "1" ] && [ -e "$WORKTREE/.git" ]; then
  timeout 60 git -C "$WORKTREE" pull -q --ff-only origin "$BRANCH" 2>/dev/null || true
  git -C "$WORKTREE" add "$DIGEST" 2>/dev/null || true
  if ! git -C "$WORKTREE" diff --cached --quiet 2>/dev/null; then
    git -C "$WORKTREE" commit -q -m "metrics: scorecard $(date +%Y-%m-%d)" 2>/dev/null || true
    timeout 60 git -C "$WORKTREE" push -q origin "$BRANCH" 2>/dev/null || true
  fi
fi
exit 0
