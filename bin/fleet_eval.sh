#!/usr/bin/env bash
# fleet_eval.sh — the standing drift check for the fleet's behaviour and grounding.
#
# usage: fleet_eval.sh [--days N] [--skip-probes] [--no-coverage] [--deliver] [--quiet]
#
# Two runners, one scorecard, one history spine:
#   tier1  fleet_eval_behaviour.py  — did deliveries carry the kind/channel/notify the
#                                     route table specifies? (evidence: receipts)
#   tier2  fleet_eval_grounding.py  — does the vault still answer the three questions
#                                     the fleet got wrong? (evidence: qmd)
#
# WHY THIS GATES ON REGRESSION, NOT ON STATE. Two of the three grounding probes fail
# today and are *known* to fail: the vault outranks its own Buzz note on a plainly-worded
# question, and the box cannot fix that — it holds no canonical vault credential. A suite
# that goes red on day one for a condition already accepted gets muted within a week, and
# a muted suite detects nothing. Each probe therefore carries the verdict measured when it
# was added, and only a fall below that verdict is a failure. An improvement is reported
# and the baseline is left alone: bumping it is a deliberate edit to the fixture, never
# something a scheduled job does to its own pass mark.
#
# EXIT CODE IS THE PRODUCT. 0 = no regression. 1 = something moved backwards, and the
# scorecard names it. The timer is not OnFailure-wired to an alerting path, because a
# failing eval is a report to read, not an incident — --deliver posts it to #ops instead,
# and only when there is something to say.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_ROOT="${FLEET_EVAL_LOG_ROOT:-$HOME/logs/fleet-eval}"
HISTORY="$LOG_ROOT/history.psv"
LOCK="${FLEET_EVAL_LOCK:-/tmp/fleet_eval.lock}"
DELIVER="$BIN_DIR/deliver.sh"

DAYS=2
DELIVER_ON_REGRESSION=0
QUIET=0
GROUNDING_ARGS=()
BEHAVIOUR_ARGS=()

while [ $# -gt 0 ]; do
  case "$1" in
    --days)         DAYS="${2:-2}"; shift 2 ;;
    --skip-probes)  GROUNDING_ARGS+=(--skip-probes); shift ;;
    --no-coverage)  BEHAVIOUR_ARGS+=(--no-coverage); shift ;;
    --deliver)      DELIVER_ON_REGRESSION=1; shift ;;
    --quiet)        QUIET=1; shift ;;
    -h|--help)      sed -n '2,20p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "fleet_eval: unrecognized argument: $1" >&2; exit 2 ;;
  esac
done

# Non-blocking, like local_tier_eval.sh: a run that collides with the previous one has
# nothing new to measure, and queueing two embedding passes helps nobody.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "fleet_eval: another run holds $LOCK — skipping" >&2
  exit 0
fi

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
WORKDIR="$LOG_ROOT/$STAMP"
mkdir -p "$WORKDIR"
RESULTS="$WORKDIR/results.psv"
SCORECARD="$WORKDIR/scorecard.md"
# The producers wired through an ExecStartPost adapter anchor their artifact to a run marker
# the unit touches; this one delivers from inside its own ExecStart, so it stamps its own.
# Without it the scorecard travels with anchor=none, and a run that died before writing one
# would ship yesterday's verdict under today's subject line.
MARKER="$WORKDIR/started"
: >"$MARKER"

run_tier() {
  local tier="$1"; shift
  local raw="$WORKDIR/$tier.raw"
  "$@" >"$raw" 2>"$WORKDIR/$tier.err"
  local code=$?
  while IFS= read -r line; do
    [ -n "$line" ] && printf '%s|%s\n' "$tier" "$line" >>"$RESULTS"
  done <"$raw"
  if [ ! -s "$raw" ]; then
    printf '%s|runner|FAIL||produced no output (exit %s): %s\n' \
      "$tier" "$code" "$(tr '\n' ' ' <"$WORKDIR/$tier.err")" >>"$RESULTS"
  fi
  return $code
}

: >"$RESULTS"
run_tier tier1 python3 "$BIN_DIR/fleet_eval_behaviour.py" --days "$DAYS" "${BEHAVIOUR_ARGS[@]}"
run_tier tier2 python3 "$BIN_DIR/fleet_eval_grounding.py" "${GROUNDING_ARGS[@]}"

count_status() { grep -c "^[^|]*|[^|]*|$1|" "$RESULTS" || true; }
FAILS=$(count_status FAIL)
WARNS=$(count_status WARN)
PASSES=$(count_status PASS)

# The history spine is the point of scheduling this: one row per assertion per run, so a
# verdict that has been degrading for a week is visible as a trend rather than as today's
# surprise. Detail is deliberately left out — it is prose, and it belongs in the scorecard.
if [ ! -f "$HISTORY" ]; then
  echo "run_ts|tier|check|status|value" >"$HISTORY"
fi
while IFS='|' read -r tier check status value _detail; do
  printf '%s|%s|%s|%s|%s\n' "$RUN_TS" "$tier" "$check" "$status" "$value" >>"$HISTORY"
done <"$RESULTS"

verdict="no regression"
[ "$FAILS" -gt 0 ] && verdict="REGRESSION"

{
  echo "# Fleet eval — $RUN_TS"
  echo
  echo "**$verdict** — $PASSES pass, $WARNS warn, $FAILS fail."
  echo
  echo "| tier | check | status | value | detail |"
  echo "|---|---|---|---|---|"
  while IFS='|' read -r tier check status value detail; do
    printf '| %s | %s | %s | %s | %s |\n' "$tier" "$check" "$status" "$value" "${detail//|/\\|}"
  done <"$RESULTS"
  echo
  echo "tier1 = delivery conformance against \`bin/buzz_routes.env\`, measured on receipts."
  echo "tier2 = vault grounding against \`bin/fleet_eval_probes.json\`, measured on qmd."
  echo
  echo "A probe verdict is scored against the baseline recorded in the fixture, so FAIL here"
  echo "means *worse than when the probe was added* — not that the fleet answers wrongly."
  echo "The instruction layer in TEAM.md carries the questions retrieval ranks wrong, and its"
  echo "own assertions are hard gates in tier2."
  echo
  echo "History: \`$HISTORY\` — full run: \`$WORKDIR\`"
} >"$SCORECARD"

[ "$QUIET" -eq 1 ] || cat "$SCORECARD"

if [ "$DELIVER_ON_REGRESSION" -eq 1 ] && [ "$FAILS" -gt 0 ]; then
  "$DELIVER" --job fleet-eval.service --route ops \
    --subject "[Praetorium] Fleet eval — regression ($FAILS)" \
    --file "$SCORECARD" --run-marker "$MARKER" --runtime none --artifact-type report \
    --target none --operation none --risk-tier review \
    --acceptance-check "every FAIL row is either fixed or its fixture baseline is deliberately re-recorded"
fi

[ "$FAILS" -gt 0 ] && exit 1
exit 0
