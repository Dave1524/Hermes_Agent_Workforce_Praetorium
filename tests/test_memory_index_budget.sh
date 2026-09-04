#!/usr/bin/env bash
# The shared memory index has a hard load budget, and exceeding it loses memories SILENTLY.
#
# ~/.claude/projects/-home-dave/memory/MEMORY.md is loaded into every session on this box —
# all four buzz-agent@* personas and Dave's own interactive shells share it. When it exceeds
# the loader's budget the loader does not error: it truncates, and the session runs with an
# unknown subset of the index. The writer gets no signal at all. That is a FAIL-OPEN failure,
# so nothing downstream can catch it either — the only tell is a warning in a system reminder
# after the loss has already happened.
#
# MEASURED 2026-09-04, which is why this suite exists. The index had reached 26,081 chars and
# was being truncated on load. 30 of its 60 entries were over the documented one-line limit;
# one had grown to 6,180 chars — 23% of the whole file — because each new finding was appended
# to the INDEX LINE as a dated addendum instead of being edited into the topic file it points
# at. Every one of those addenda was already present, in fuller form, in the topic file: the
# index was carrying pure duplication. Rewriting the 30 entries to a one-line hook returned it
# to ~11,300 chars and lost nothing.
#
# THE UNIT IS CHARACTERS OVER 1024, NOT BYTES. Derived, not guessed: the loader reported that
# file as "25.5KB (limit: 24.4KB)". 26,313 bytes / 1024 = 25.70 and /1000 = 26.31, neither of
# which rounds to 25.5; 26,081 CHARS / 1024 = 25.47 does. So the limit is 24.4 * 1024 = 24,986
# characters. A byte-based check would read ~1% high and would be wrong in the safe direction
# by accident rather than by design.
#
# WHY THE BUDGET IS BELOW THE CLIFF. Failing at 24,986 would fire only once memories are
# already being dropped, which is a report of damage, not a guard against it. BUDGET_CHARS is
# 80% of the limit, so the gate goes red with roughly 5,000 characters of runway left.
#
# THE CHECKER IS APPLIED TO FIXTURES FIRST, AND THAT IS THE POINT. A budget assertion against
# one live file that is currently healthy is a check that cannot fail, and this repo has been
# bitten by exactly that shape (memory `readiness-report-phantom-blockers`). Groups 1 and 2
# prove the two failure modes are detected on synthetic inputs and that a healthy input is
# NOT flagged, so group 3's verdict on the live file means something.
set -uo pipefail

MEMORY_INDEX="${MEMORY_INDEX:-$HOME/.claude/projects/-home-dave/memory/MEMORY.md}"
LOAD_LIMIT_CHARS=24986          # 24.4 * 1024, the loader's own cliff — see header
BUDGET_CHARS=20000              # 80% of it; red while there is still runway
ENTRY_MAX_CHARS=200             # "Keep index entries to one line under ~200 chars"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# --- the checker, one definition, used on fixtures and on the live file -------------------
index_chars()      { wc -m < "$1" | tr -d ' '; }
entries_total()    { grep -c '^- \[' "$1" 2>/dev/null || echo 0; }
entries_over_max() { awk -v m="$ENTRY_MAX_CHARS" '/^- \[/ && length($0) > m {n++} END {print n+0}' "$1"; }
over_budget()      { [ "$(index_chars "$1")" -gt "$BUDGET_CHARS" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- 0. canaries ---"
# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checker detects both failure modes on fixtures ---"
# Over budget by size alone, with every individual entry legal — the two modes are independent
# and a checker that only caught long entries would miss an index bloated by entry COUNT.
big="$TMP/big.md"
: > "$big"
for i in $(seq 1 400); do
  printf -- '- [entry %03d](topic-%03d.md) — %s\n' "$i" "$i" "$(printf 'x%.0s' $(seq 1 60))" >> "$big"
done
assert 'an index over the budget is detected'          "over_budget '$big'"
assert 'and its individual entries are all legal'      "[ \"\$(entries_over_max '$big')\" -eq 0 ]"

# One over-long entry, whole file small — the mode that actually caused the 2026-09-04 overflow.
long="$TMP/long.md"
{ printf -- '- [short](a.md) — a hook\n'
  printf -- '- [bloated](b.md) — %s\n' "$(printf 'y%.0s' $(seq 1 300))"; } > "$long"
assert 'a single over-long entry is detected'          "[ \"\$(entries_over_max '$long')\" -eq 1 ]"
assert 'even while the file is well under budget'      "! over_budget '$long'"

# The boundary, so ENTRY_MAX_CHARS is a limit rather than an approximation.
edge="$TMP/edge.md"
python3 - "$edge" "$ENTRY_MAX_CHARS" <<'PY'
import sys
path, m = sys.argv[1], int(sys.argv[2])
head = "- [x](x.md) — "
sys.stdout = open(path, "w")
print(head + "z" * (m - len(head)))          # exactly m
print(head + "z" * (m - len(head) + 1))      # exactly m+1
PY
assert 'an entry of exactly the limit is not flagged, m+1 is' \
  "[ \"\$(entries_over_max '$edge')\" -eq 1 ]"

echo "--- 2. a healthy index is NOT flagged (the check can pass) ---"
ok="$TMP/ok.md"
{ printf '# Memory index\n\n'
  printf -- '- [a topic](a-topic.md) — a one-line hook that helps a cold session decide whether to open it\n'
  printf -- '- [another](another.md) — likewise\n'; } > "$ok"
assert 'a healthy index is under budget'               "! over_budget '$ok'"
assert 'and has no over-long entries'                  "[ \"\$(entries_over_max '$ok')\" -eq 0 ]"

echo "--- 3. the live shared index ---"
if box_only_with 'the shared memory index every session on this box loads' "$MEMORY_INDEX"; then
  chars=$(index_chars "$MEMORY_INDEX")
  total=$(entries_total "$MEMORY_INDEX")
  overs=$(entries_over_max "$MEMORY_INDEX")
  pct=$(( chars * 100 / LOAD_LIMIT_CHARS ))
  echo "  info: ${chars} chars, ${total} entries, ${pct}% of the ${LOAD_LIMIT_CHARS}-char load limit"
  echo "  info: budget ${BUDGET_CHARS}, headroom $(( BUDGET_CHARS - chars )) chars"
  [ "$chars" -gt "$LOAD_LIMIT_CHARS" ] && \
    echo "  info: OVER THE LOAD LIMIT — memories are being dropped from every session right now"

  assert "the index is within the ${BUDGET_CHARS}-char budget"  "! over_budget '$MEMORY_INDEX'"
  assert "no entry exceeds ${ENTRY_MAX_CHARS} chars (${overs} do)" "[ '$overs' -eq 0 ]"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
