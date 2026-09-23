#!/usr/bin/env bash
# Brief shape (T8.6). /plan-feature's template lives in ~/.claude/commands/plan-feature.md —
# user scope, under no git repo, off CI — so nothing versioned notices if it is reverted (a
# Mac-side re-copy, a repo override without the sections). What IS versioned is every brief it
# writes. Every dated brief on or after BRIEF_SHAPE_SINCE carries `## Order of work` and
# `## Risks`, each with at least one non-blank line before the next `## `.
#
# A file without `**Date:**` is not a template brief and is not judged. Presence and
# non-emptiness only: whether a risk is a good one is the reviewer's call, not a grep's.
#
# FIXTURES FIRST: group 1 proves the checker flags each failure on synthetic briefs and stays
# silent on a filled one; group 2 is the verdict on the real briefs.
set -uo pipefail

BRIEF_SHAPE_SINCE=2026-09-23
REQUIRED_SECTIONS=("Order of work" "Risks")

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BRIEFS_DIR="${BRIEFS_DIR:-$REPO_ROOT/.claude/briefs}"

fail=0

# pipefail has no place inside a boolean condition: `grep -q` exits on its first match and
# SIGPIPEs its producer, so a found pattern would report 141.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

brief_date() {
  sed -n 's/^\*\*Date:\*\* *\([0-9-]\{10\}\).*/\1/p' "$1" | head -n1
}

# Prints the first line of body under `## <heading>`, empty when absent or empty.
section_body() {
  awk -v h="## $2" '
    $0 == h { inside = 1; next }
    inside && /^## / { exit }
    inside && NF { print; exit }
  ' "$1"
}

# One offender per line: `<file>: <missing-or-empty section>`.
misshapen_briefs() {
  local f d s
  for f in "$1"/*.md "$1"/archive/*.md; do
    [ -f "$f" ] || continue
    d=$(brief_date "$f")
    [ -n "$d" ] || continue
    [[ "$d" < "$BRIEF_SHAPE_SINCE" ]] && continue
    for s in "${REQUIRED_SECTIONS[@]}"; do
      [ -n "$(section_body "$f" "$s")" ] || echo "$f: ## $s"
    done
  done
}

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

write_brief() {  # <dir> <name> <date|-> <body sections...>
  local dir=$1 name=$2 date=$3; shift 3
  mkdir -p "$dir"
  {
    echo "# Brief: fixture"
    [ "$date" = - ] || echo "**Date:** $date   **Verify:** none"
    printf '%s\n' "$@"
  } > "$dir/$name.md"
}

echo "0. the assert helper itself"
assert "a found pattern is never reported as a failure" "yes | grep -q y"

echo "1. the checker, on fixtures"   # (::brief-shape-checker)
FILLED=("## Order of work" "1. test, then change" "" "## Risks" "- none: fixture" "" "## Notes" "- x")
write_brief "$TMP/filled" ok 2026-09-23 "${FILLED[@]}"
assert "a brief with both sections filled passes" "[ -z \"\$(misshapen_briefs '$TMP/filled')\" ]"

write_brief "$TMP/no-risks" b 2026-09-24 "## Order of work" "1. x"
assert "a brief missing ## Risks is flagged, naming the section" \
       "[ \"\$(misshapen_briefs '$TMP/no-risks')\" = '$TMP/no-risks/b.md: ## Risks' ]"

write_brief "$TMP/empty" b 2026-09-24 "## Order of work" "" "## Risks" "" "## Notes" "- x"
assert "a brief whose ## Order of work is empty is flagged" \
       "misshapen_briefs '$TMP/empty' | grep -qx '$TMP/empty/b.md: ## Order of work'"
assert "and its empty ## Risks too — blank lines are not a body" \
       "misshapen_briefs '$TMP/empty' | grep -qx '$TMP/empty/b.md: ## Risks'"

write_brief "$TMP/archived" b 2026-09-24 "## Risks" "- none: x"
mkdir -p "$TMP/archived/archive" && mv "$TMP/archived/b.md" "$TMP/archived/archive/"
assert "archive/ is judged too" \
       "[ \"\$(misshapen_briefs '$TMP/archived')\" = '$TMP/archived/archive/b.md: ## Order of work' ]"

write_brief "$TMP/undated" b - "# no sections at all"
assert "a file without **Date:** is not a template brief and is ignored" \
       "[ -z \"\$(misshapen_briefs '$TMP/undated')\" ]"

write_brief "$TMP/old" b 2026-09-01 "## Acceptance criteria" "- x"
assert "a brief dated before $BRIEF_SHAPE_SINCE is exempt" "[ -z \"\$(misshapen_briefs '$TMP/old')\" ]"

echo "2. the real briefs"   # (::brief-shape-live)
anchors=$(ls "$BRIEFS_DIR"/*t8-6-brief-template-order-risks.md "$BRIEFS_DIR"/archive/*t8-6-brief-template-order-risks.md 2>/dev/null)
assert "the T8.6 brief (the shape's first instance) is present to be judged" "[ -n \"\$anchors\" ]"
bad=$(misshapen_briefs "$BRIEFS_DIR")
assert "every brief dated >= $BRIEF_SHAPE_SINCE carries both sections, filled" "[ -z \"\$bad\" ]"
[ -z "$bad" ] || printf '%s\n' "$bad" | sed 's/^/    /'

exit $fail
