#!/usr/bin/env bash
# Local-tier capability eval: bounded, mechanical tasks with machine-checked
# ground truth, run against the on-box Ollama models. $0 — no OpenRouter egress.
#
# Each task isolates ONE failure mode observed on 2026-07-21 while trying to run
# the morning report locally, so the result says WHICH capability is missing
# rather than just "it didn't work":
#   t1 extraction   — structured output + hallucinated units (run 3x: also determinism)
#   t2 classify     — the charter's named mechanical use case
#   t3 format       — qwen emitted a markdown table despite an explicit prohibition
#   t4 artifact     — qwen replied as if done without writing the file
#   t5 summarise    — constrained compression with fact retention
#   t6 filter       — emit only the matching subset, invent nothing
#   t7 count        — arithmetic over a list, into one strict JSON object
#   t8 abstention   — say NOT FOUND when the answer is absent (no invented time)
#   t9 sort/dedup   — deterministic ordering + duplicate removal
#   t10 redaction   — mask emails and $ amounts, touch nothing else
#   t11 lookup      — copy one unit's next-time exactly, no padding
#
# Read-only against the box: every write lands in the run's own workdir.
# Takes the agent_propose lock so it can never overlap a real scheduled job.
set -uo pipefail

REPO_BIN="$(cd "$(dirname "$0")" && pwd)"
PROMPTS="$REPO_BIN/../profiles/local_eval"
SCORER="$REPO_BIN/local_tier_eval_score.py"
HERMES="${HERMES_BIN:-$HOME/.local/bin/hermes}"
LOCK="${AGENT_PROPOSE_LOCK:-/tmp/agent_propose.lock}"
OUT_DIR="${LOCAL_EVAL_OUT:-$HOME/logs/local-tier-eval}"
MODELS="${LOCAL_EVAL_MODELS:-local}"
TIMEOUT_MIN="${LOCAL_EVAL_TIMEOUT_MIN:-6}"
# Small prompts, so a task needing tools is the exception (t4 only).
TOOLSET_DEFAULT="${LOCAL_EVAL_TOOLSET:-terminal,file}"

# Per-run dir (minute resolution): the schedule fires several times a day, so a
# per-DAY dir would let each run overwrite the last. history.psv is the long-term
# spine that survives across runs.
run_stamp=$(date +%Y-%m-%dT%H%M)
work="$OUT_DIR/$run_stamp"
mkdir -p "$work"
card="$work/scorecard.md"
history="$OUT_DIR/history.psv"

log() { echo "$(date -Is) $*"; }

# ── Capture inputs ONCE so every model sees byte-identical data and the scorer
#    grades against exactly what was asked, not against live state. ──
capture_inputs() {
  # Keep the header row: NEXT and LAST are both timestamps, so without column
  # names the task is unanswerable and the model is graded on a coin flip.
  # W3 (2026-09-02): the timer set comes from config/fleet-units.tsv, not the five-prefix
  # glob that stood here. Two consequences, both deliberate.
  #   1. t1's denominator moves from 7 units to every system-scope standing unit (21 today).
  #      That is a DIFFICULTY CHANGE, not a model change: history.psv scores either side of
  #      the deploy that ships this are not comparable. t1's detail string carries the
  #      denominator ("7/7 units" -> "21/21 units"), so the discontinuity is visible in the
  #      scorecard itself rather than needing to be remembered.
  #   2. The set now grows when the fleet grows. That is the point — a model that can
  #      transcribe the box's real timer list is what this measures — but it does mean a
  #      future unit addition moves the score. Read a t1 drop against the denominator first.
  # The services list below is deliberately NOT derived: it mixes workflow units with
  # daemons (ollama, qmd-mcp) that are declared in no manifest, and it is test data rather
  # than fleet coverage.
  mapfile -t _fleet_timers < <(
    awk -F'\t' '!/^#/ && NF>=3 && $2=="system" && $3=="standing" {print $1".timer"}' \
      "$REPO_BIN/../config/fleet-units.tsv" 2>/dev/null)
  if [ ${#_fleet_timers[@]} -eq 0 ]; then
    log "FATAL: config/fleet-units.tsv unreadable or empty — refusing to grade on a fixture"
    return 1
  fi
  systemctl list-timers "${_fleet_timers[@]}" \
    --no-pager 2>/dev/null | grep -E '^NEXT|\.timer' > "$work/timers.txt" || true

  : > "$work/services.txt"
  : > "$work/services_raw.txt"
  for u in ollama.service agent-inbox-sync.timer overnight-morning-report.service \
           bd-stall-radar.service augustus-content.service agent-proposal.service \
           qmd-mcp.service ttm-pool-drain.timer weekly-pre-assembly.service \
           agent-workforce-auto-sync.timer; do
    state=$(systemctl is-active "$u" 2>/dev/null || true)
    [ -n "$state" ] || state=unknown
    printf '%s\t%s\n' "$u" "$state" >> "$work/services.txt"
    printf '%s: %s\n' "$u" "$state" >> "$work/services_raw.txt"
  done

  cp "$work/timers.txt" "$work/jobs.txt"

  local newest
  newest=$(ls -1 "$HOME/logs/overnight"/morning-report-*.md 2>/dev/null | sort | tail -1)
  if [ -n "$newest" ]; then cp "$newest" "$work/report.txt"; else : > "$work/report.txt"; fi

  # t9 input: unit names reversed with two duplicates appended — exercises dedup
  # and ordering. Ground truth (sorted-unique) is recomputed from services.txt.
  awk -F'\t' '{print $1}' "$work/services.txt" | tac > "$work/names_dup.txt"
  awk -F'\t' 'NR<=2{print $1}' "$work/services.txt" >> "$work/names_dup.txt"

  # t10 input: fixed, fake, box-safe text carrying emails and $ amounts to mask.
  cat > "$work/pii_sample.txt" <<'PII'
Contact ops at alerts@praetorium.local about the 06:15 run.
Overnight spend was $0.02; last week it was $1.45 total.
Ping dave@example.com if qmd-mcp.service starts flapping again.
No sensitive tokens on this line — just uptime 3218s and 62% disk.
PII
}

# Substitute the captured input into a prompt template.
build_prompt() {
  local template=$1 input_file=$2 outpath=${3:-}
  python3 - "$template" "$input_file" "$outpath" <<'PY'
import sys, pathlib
tpl, inp, outpath = sys.argv[1], sys.argv[2], sys.argv[3]
text = pathlib.Path(tpl).read_text()
text = text.replace("{{INPUT}}", pathlib.Path(inp).read_text() if inp != "-" else "")
text = text.replace("{{OUTPATH}}", outpath)
sys.stdout.write(text)
PY
}

run_one() {
  local task=$1 model=$2 prompt=$3 toolset=$4
  local tag="${task}__${model}"
  local outfile="$work/$tag.out"
  local started ended
  started=$(date +%s)
  timeout "${TIMEOUT_MIN}m" "$HERMES" -t "$toolset" -z "$prompt" \
    -p marcus -m "$model" >"$outfile" 2>"$work/$tag.err"
  ended=$(date +%s)
  local verdict
  verdict=$(python3 "$SCORER" "$task" "$outfile" "$work")
  printf '%s|%s|%s|%ss\n' "$task" "$model" "$verdict" "$((ended - started))" >> "$work/results.psv"
  log "  $tag -> $verdict ($((ended - started))s)"
}

main() {
  log "local-tier eval starting; workdir=$work"
  capture_inputs
  : > "$work/results.psv"

  for model in $MODELS; do
    log "model: $model"
    # t1 three times: same prompt, so identical outputs also prove temperature 0
    # survives the provider path (temp 1 produced a wrong answer 1-in-3 on 07-21).
    for i in 1 2 3; do
      run_one "t1_run$i" "$model" "$(build_prompt "$PROMPTS/t1_extract.md" "$work/timers.txt")" "$TOOLSET_DEFAULT"
    done
    run_one t2 "$model" "$(build_prompt "$PROMPTS/t2_classify.md" "$work/services_raw.txt")" "$TOOLSET_DEFAULT"
    run_one t3 "$model" "$(build_prompt "$PROMPTS/t3_format.md" "$work/jobs.txt")" "$TOOLSET_DEFAULT"
    rm -f "$work/t4_artifact.txt"
    run_one t4 "$model" "$(build_prompt "$PROMPTS/t4_artifact.md" - "$work/t4_artifact.txt")" "$TOOLSET_DEFAULT"
    run_one t5 "$model" "$(build_prompt "$PROMPTS/t5_summarise.md" "$work/report.txt")" "$TOOLSET_DEFAULT"
    run_one t6 "$model" "$(build_prompt "$PROMPTS/t6_filter.md" "$work/services_raw.txt")" "$TOOLSET_DEFAULT"
    run_one t7 "$model" "$(build_prompt "$PROMPTS/t7_count.md" "$work/services_raw.txt")" "$TOOLSET_DEFAULT"
    run_one t8 "$model" "$(build_prompt "$PROMPTS/t8_abstain.md" "$work/timers.txt")" "$TOOLSET_DEFAULT"
    run_one t9 "$model" "$(build_prompt "$PROMPTS/t9_sort.md" "$work/names_dup.txt")" "$TOOLSET_DEFAULT"
    run_one t10 "$model" "$(build_prompt "$PROMPTS/t10_redact.md" "$work/pii_sample.txt")" "$TOOLSET_DEFAULT"
    run_one t11 "$model" "$(build_prompt "$PROMPTS/t11_lookup.md" "$work/timers.txt")" "$TOOLSET_DEFAULT"
  done

  python3 "$REPO_BIN/local_tier_eval_report.py" "$work" > "$card"
  log "scorecard: $card"
  cat "$card"

  # Append this run's per-task verdicts to the cumulative history so trend can
  # track pass-rate over time and across the day. Columns: run_ts task model
  # status score secs. results.psv verdict field is "STATUS score detail".
  [ -f "$history" ] || echo "run_ts|task|model|status|score|secs" > "$history"
  awk -F'|' -v ts="$run_stamp" '{split($3, v, " "); print ts"|"$1"|"$2"|"v[1]"|"v[2]"|"$4}' \
    "$work/results.psv" >> "$history"
  log "history: appended $(wc -l < "$work/results.psv") rows to $history"
}

# Serialise against real scheduled jobs; skip rather than queue if one is running.
exec 9>"$LOCK"
if ! flock -n 9; then
  log "another agent job holds $LOCK — skipping this eval run"
  exit 0
fi
main
