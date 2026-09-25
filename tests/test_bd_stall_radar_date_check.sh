#!/usr/bin/env bash
# The bd-stall-radar contract's `kernel-date-matched-the-run`, lifted from the contract and
# run the way contract_exec.py runs it.
#
# On 2026-09-21 the run wrote the right file (2026-09-21_bd-stall-radar.md) and was recorded
# as failed: the check took the LAST proposal path in Claudius's reply for the kernel's
# write, and his reply ended by pointing at last week's unactioned 2026-09-17 proposal. The
# check now reads the date from the kernel's own summary line, which no reply can paraphrase.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CONTRACT="$REPO_ROOT/design/contracts/bd-stall-radar.md"

fail=0
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/bddate.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

sed -n '/^   ```check id=kernel-date-matched-the-run/,/^   ```$/p' "$CONTRACT" | sed '1d;$d' >"$WORK/check.sh"
assert 'the contract carries the check' "[ -s '$WORK/check.sh' ]"

SUMMARY_DIR="$WORK/home/agent-workforce/var/bd-stall-radar"
mkdir -p "$SUMMARY_DIR"
REPLY="$WORK/attempt.log"
cat >"$REPLY" <<'EOF'
56 genuine stalls flagged. Wrote `_inbox/agents/2026-09-21_bd-stall-radar.md`.
One note: the 2026-09-17 proposal is still sitting unactioned in `_inbox/agents/2026-09-17_bd-stall-radar.md`.
EOF

run_check() {  # run_check <run-date> <run-started-at>
  env -i PATH="$PATH" HOME="$WORK/home" UNIT=bd-stall-radar RUN_DATE="$1" \
    AGENT_RUN_STARTED_AT="$2" AGENT_ATTEMPT_LOG="$REPLY" bash "$WORK/check.sh" >"$WORK/out" 2>&1
}
summary() {  # summary <date> — the kernel's own line, written now
  printf 'bd-stall-radar (deterministic) %s — 88 deals, 57 Prospect&unworked, 56 flagged (8 warm, 11 aging, 37 never contacted)\n' "$1" \
    >"$SUMMARY_DIR/last-run.log"
}
started=$(( $(date +%s) - 60 ))

summary 2026-09-21
run_check 2026-09-21 "$started"; rc=$?
assert 'the 2026-09-21 case: a reply that names an older proposal last still passes' "[ $rc -eq 0 ]"

summary 2026-09-22
run_check 2026-09-21 "$started"; rc=$?
assert 'a kernel that dated its run differently fails' "[ $rc -eq 1 ]"
assert 'and names both dates' "grep -q \"dated its run '2026-09-22' while this run is dated 2026-09-21\" '$WORK/out'"

summary 2026-09-21
run_check 2026-09-21 "$(( $(date +%s) + 3600 ))"; rc=$?
assert 'a summary older than this run is n/a here (kernel-actually-ran owns that failure)' "[ $rc -eq 77 ]"

rm -f "$SUMMARY_DIR/last-run.log"
run_check 2026-09-21 "$started"; rc=$?
assert 'no summary at all is n/a here too' "[ $rc -eq 77 ]"

assert 'the check never reads the agent'"'"'s reply' "! grep -q 'AGENT_ATTEMPT_LOG' '$WORK/check.sh'"

if [ "$fail" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "all kernel-date assertions passed"
