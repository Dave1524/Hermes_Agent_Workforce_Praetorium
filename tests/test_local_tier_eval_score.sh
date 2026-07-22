#!/usr/bin/env bash
# Test for bin/local_tier_eval_score.py — each scorer graded against a fixed
# captured input, so ground truth is deterministic and offline (no model, no net).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCORER="$REPO_ROOT/bin/local_tier_eval_score.py"
TD="$(mktemp -d)"
trap 'rm -rf "$TD"' EXIT

fail=0

# check <task> <output-text> <verdict-regex>
check() {
  local task=$1 text=$2 pat=$3
  local out="$TD/out"
  printf '%s' "$text" > "$out"
  local got
  got=$(python3 "$SCORER" "$task" "$out" "$TD")
  if echo "$got" | grep -Eq "$pat"; then
    echo "  ok: $task -> $got"
  else
    echo "  FAIL: $task expected /$pat/, got: $got"
    fail=1
  fi
}

# ── Fixtures: 5 units (3 active, 2 inactive), 2 timers with known NEXT times ──
printf 'ollama.service\tactive\n'            > "$TD/services.txt"
printf 'agent-inbox-sync.timer\tactive\n'   >> "$TD/services.txt"
printf 'qmd-mcp.service\tactive\n'          >> "$TD/services.txt"
printf 'bd-stall-radar.service\tinactive\n' >> "$TD/services.txt"
printf 'augustus-content.service\tinactive\n' >> "$TD/services.txt"

{
  echo 'NEXT                         LEFT  LAST                         PASSED   UNIT                            ACTIVATES'
  echo 'Wed 2026-07-22 08:01:30 CEST 24min Wed 2026-07-22 07:30:44 CEST 6min ago agent-inbox-sync.timer          agent-inbox-sync.service'
  echo 'Wed 2026-07-22 07:45:25 CEST 8min  Wed 2026-07-22 07:31:34 CEST 5min ago agent-workforce-auto-sync.timer agent-workforce-auto-sync.service'
} > "$TD/timers.txt"

printf '7 promoted, 3 rejected, 3 pending, 1 ready. Spend $0.02 overnight.\n' > "$TD/report.txt"
printf 'Email foo@bar.com and $1.23 here.\nPlain line.\n' > "$TD/pii_sample.txt"

echo "--- t1 extraction ---"
check t1 '[{"unit":"agent-inbox-sync.timer","next":"Wed 2026-07-22 08:01:30 CEST"},{"unit":"agent-workforce-auto-sync.timer","next":"Wed 2026-07-22 07:45:25 CEST"}]' '^PASS 1.00'
check t1 '[{"unit":"ghost.timer","next":"Wed 2026-07-22 00:00:00 CEST"}]' '^FAIL 0.00 .*hallucinated'

echo "--- t2 classify ---"
check t2 $'ollama.service = active\nagent-inbox-sync.timer = active\nqmd-mcp.service = active\nbd-stall-radar.service = inactive\naugustus-content.service = inactive\n' '^PASS 1.00 5/5'

echo "--- t3 format ---"
check t3 $'```\njob    status\nfoo    ok\n```\n' '^PASS 1.00 clean'
check t3 $'| job | status |\n|-----|--------|\n| foo | ok |\n' '^FAIL 0.00 .*markdown table'

echo "--- t4 artifact ---"
printf 'READYOK' > "$TD/t4_artifact.txt"
check t4 'DONE' '^PASS 1.00 file correct'
rm -f "$TD/t4_artifact.txt"
check t4 'DONE' '^FAIL 0.00 no file written but replied DONE'
printf 'READYOK' > "$TD/t4_artifact.txt"  # restore for any re-runs

echo "--- t5 summarise ---"
check t5 '7 promoted, 3 rejected/pending, 1 ready, $0.02 spend.' '^PASS 1.00'
check t5 "$(head -c 700 < /dev/zero | tr '\0' 'x')" '^FAIL 0.00 .*> 600'

echo "--- t6 filter ---"
check t6 $'ollama.service\nagent-inbox-sync.timer\nqmd-mcp.service\n' '^PASS 1.00 3/3'
check t6 $'ollama.service\nbd-stall-radar.service\n' '^FAIL 0.00 .*wrong'

echo "--- t7 count -> JSON ---"
check t7 '{"total": 5, "active": 3, "inactive": 2}' '^PASS 1.00 3/3'
check t7 '{"total": 5, "active": 4, "inactive": 2}' '^FAIL 0.67'
check t7 'total is 5 units' '^FAIL 0.00 not a JSON object'

echo "--- t8 abstention ---"
check t8 'NOT FOUND' '^PASS 1.00 correctly abstained'
check t8 'Wed 2026-07-22 08:01:30 CEST' '^FAIL 0.00 hallucinated a time'

echo "--- t9 sort + dedup ---"
check t9 $'agent-inbox-sync.timer\naugustus-content.service\nbd-stall-radar.service\nollama.service\nqmd-mcp.service\n' '^PASS 1.00'
check t9 $'qmd-mcp.service\nollama.service\nbd-stall-radar.service\naugustus-content.service\nagent-inbox-sync.timer\n' '^FAIL 0.50 correct set, wrong order'

echo "--- t10 redaction ---"
check t10 $'Email [REDACTED] and [REDACTED] here.\nPlain line.\n' '^PASS 1.00 redacted exactly'
check t10 $'Email foo@bar.com and [REDACTED] here.\nPlain line.\n' '^FAIL 0.00 1 PII'

echo "--- t11 targeted lookup ---"
check t11 'Wed 2026-07-22 07:45:25 CEST' '^PASS 1.00 exact'
check t11 'The next run is Wed 2026-07-22 07:45:25 CEST' '^FAIL 0.50 correct but padded'

echo "--- empty output ---"
: > "$TD/empty"
got=$(python3 "$SCORER" t7 "$TD/empty" "$TD")
if echo "$got" | grep -Eq '^FAIL 0.00 empty output'; then echo "  ok: empty -> $got"; else echo "  FAIL: empty got: $got"; fail=1; fi

exit $fail
