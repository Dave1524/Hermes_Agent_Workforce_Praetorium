#!/usr/bin/env bash
# The two instruction files every session loads are bounded, and carry no stale live-state counts.
#
# A ceiling per file, in bytes: measured size + 256 when it was last cut. It only goes down —
# a PR that shrinks a file lowers its ceiling in the same commit (T8.5). A trap paragraph
# leaves the prose by becoming an assertion somewhere; this suite is what stops it coming back.
#
# Count literals ("five agents", "529 documents") are live state written as prose and went
# stale every time (fleet five read as four for weeks). A count may appear only on a line
# that says MEASURED, the marker the file itself prescribes.
set -uo pipefail

REPO_MAX=13063
MACHINE_MAX=36570
REPO_FILE="${REPO_FILE:-$(cd "$(dirname "$0")/.." && pwd)/CLAUDE.md}"
MACHINE_FILE="${MACHINE_FILE:-$HOME/CLAUDE.md}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

COUNT_LITERAL='\b(two|three|four|five|six|seven|eight|nine|ten|[0-9]+) (agents|units|documents)\b'

bytes()          { wc -c < "$1" | tr -d ' '; }
within()         { [ "$(bytes "$1")" -le "$2" ]; }
count_literals() { grep -nE "$COUNT_LITERAL" "$1" | grep -v 'MEASURED' || true; }
no_literals()    { [ -z "$(count_literals "$1")" ]; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- 0. canaries ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checker detects both failure modes on fixtures (::instruction-size-checker) ---"
head -c 1001 /dev/zero | tr '\0' x > "$TMP/big.md"
head -c 1000 /dev/zero | tr '\0' x > "$TMP/edge.md"
assert 'a file one byte over its ceiling is flagged'     "! within '$TMP/big.md' 1000"
assert 'a file at exactly its ceiling is not'            "within '$TMP/edge.md' 1000"
printf 'Check the fleet: all four agents answer.\n' > "$TMP/fleet.md"
printf 'The index holds 529 documents.\n' > "$TMP/docs.md"
printf 'Five units active running (MEASURED 2026-09-05).\n' > "$TMP/measured.md"
printf 'Enumerate the units; never count them in prose.\n' > "$TMP/clean.md"
assert 'a fleet count in prose is flagged'               "! no_literals '$TMP/fleet.md'"
assert 'a document count in prose is flagged'            "! no_literals '$TMP/docs.md'"
assert 'a count on a MEASURED line is not'               "no_literals '$TMP/measured.md'"
assert 'prose with no count is not'                      "no_literals '$TMP/clean.md'"

report() {
  local f=$1 max=$2
  echo "  info: $f $(bytes "$f") B, ceiling $max B"
  assert "$(basename "$f") is within its ${max}-byte ceiling"  "within '$f' $max"
  assert "$(basename "$f") carries no unmeasured count literal: $(count_literals "$f" | tr '\n' ' ')" \
    "no_literals '$f'"
}

echo "--- 2. this repo's CLAUDE.md (::instruction-size-repo) ---"
report "$REPO_FILE" "$REPO_MAX"

echo "--- 3. the box-root ~/CLAUDE.md (::instruction-size-machine) ---"
if box_only_with 'the box-root instruction file every session on this box loads' "$MACHINE_FILE"; then
  report "$MACHINE_FILE" "$MACHINE_MAX"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
