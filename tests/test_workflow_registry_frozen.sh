#!/usr/bin/env bash
# design/workflow-registry.md is the D1 decision record: which workflows existed on 2026-09-01
# and who Dave made accountable for each. It was, for three days, the only place that answer
# lived. Then D2 moved the answer into design/agents/*.toml, two suites joined the manifests to
# the box (tests/test_workflow_coverage.py, tests/test_fleet_ownership.sh), and the registry
# was joined to nothing at all.
#
# WHY A JOIN FOR A FROZEN FILE. A registry nobody joins against is prose, and prose does not
# get retired. W19 (design/open-decisions.md) measured the consequence on 2026-09-04: the two
# campaign units were deleted in a commit that touched exactly the two files a test forced it
# to touch, and the registry's rows for them still read `keep` with live triggers, because no
# check compared the registry to anything. T6.4 (docs/dev-plan-2026-09.md) froze the file with
# a header that says it is history and points at where the live answer lives. This suite is
# the one join the file can honestly carry: it does not assert the prose is TRUE — the prose
# is dated history and stays as written — it asserts the file cannot drift back into
# presenting itself as current.
#
# THE FOUR INVARIANTS. 1, 2 and 4 look at the header — the lines above the file's first `---`
# rule, which is where the header ends; 3 looks at every heading in the file:
#
#   1. The header is present: a `FROZEN RECORD` marker, and `design/agents/` named as where
#      workflows are declared now. The bare word FROZEN discriminates nothing — the pre-freeze
#      header already read `FROZEN 2026-09-01` while calling itself the single source of truth.
#   2. Every backticked repo path in the header resolves on disk. A pointer at a moved or
#      renamed file is the defect the header exists to prevent, so a stale one goes red by
#      name. Globs resolve as globs (design/agents/*.toml); a trailing slash is a directory.
#      A line reference (`file.md:77-78`) is checked by its path half, suffix stripped, so a
#      renamed file hides behind no line number. Only a token containing `/` is taken as a
#      repo path: a `~` home path, a URL and a root-level file such as `CLAUDE.md` are not
#      checked — stated so a green run is not read as covering them. The dedup is `LC_ALL=C`:
#      under this box's en_US.UTF-8, `sort -u` collapses two paths that differ only in
#      punctuation, so a dead pointer beside its live twin was never resolved (measured
#      2026-09-08; `tests/test_buzz_interactive_harness.sh` pins the same).
#   3. No heading anywhere in the file, at any level, claims liveness — `(live`, `(proposed`,
#      "must resolve", "required from", case-insensitively. Those were the five headings that
#      made the frozen file read as an open worklist; a heading is the cheapest place the
#      claim can come back, and the H1 is a heading like any other.
#   4. The header ends at a `---` rule inside HEADER_MAX lines. Without one there is no header,
#      only a window someone chose, and 1 and 2 are then judged over a guess.
#
# WHY THE RULE AND NOT A LINE COUNT. This suite read `head -30` until 2026-09-09, over a header
# whose last pointer sat on line 24 and whose rule sat on line 28: two lines of growth would
# have pushed a pointer out of scope with no signal at all — the checker would have gone on
# passing over a region that no longer contained what it was written to check. The rule moves
# with the prose, so the window cannot fall behind it. HEADER_MAX only bounds the damage when
# the rule is missing entirely, which invariant 4 reports rather than absorbs.
#
# WHY NOT compgen -G. Measured 2026-09-08 on bash 5.3: `compgen -G "design/nope/"` reports a
# match for a directory that does not exist — a fail-open on exactly the trailing-slash case
# invariant 2 most needs. A nullglob expansion followed by -e is correct on every shape tried.
#
# WHAT THIS DOES NOT ASSERT. Whether any table row is right, whether an owner is still the
# owner, whether a trigger is the declared OnCalendar. All of that lives in the manifests and
# is asserted there; a green run here says the registry still says so, nothing more.
#
# FIXTURES FIRST, LIVE FILE SECOND. Group 1 proves each checker names its offender on
# synthetic input and stays silent on a healthy one; group 2 is the verdict on the real file.
# No box precondition: every checkout carries both inputs, so this suite never prints SKIP.
set -uo pipefail

HEADER_MAX=60

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REGISTRY="$REPO_ROOT/design/workflow-registry.md"

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

# --- the checkers, one definition each, used on fixtures and on the live file --------------
# Each prints one offender per line, so a failure names its subject instead of only its count.

header_of() {                 # $1 file — the lines above the first `---` rule, HEADER_MAX at most
  awk -v max="$HEADER_MAX" 'NR>max || /^---$/ {exit} {print}' "$1"
}

header_unbounded() {          # $1 file — a header no rule closes is a window, not a header
  head -n "$HEADER_MAX" "$1" | grep -q '^---$' \
    || echo "no --- rule in the first $HEADER_MAX lines"
}

header_missing() {            # $1 file
  local hdr
  hdr=$(header_of "$1")
  grep -q 'FROZEN RECORD' <<<"$hdr"   || echo 'no FROZEN RECORD marker'
  grep -q 'design/agents/' <<<"$hdr"  || echo 'no design/agents/ pointer'
}

live_headings() {             # $1 file — any level, either paren spelling, either case
  grep -inE '^#{1,6} .*(\(live|\(proposed|must resolve|required from)' "$1"
  return 0
}

resolves_glob() {             # $1 pattern, relative to the cwd
  local -a m
  shopt -s nullglob
  # shellcheck disable=SC2206  # word-splitting IS the glob expansion under test
  m=($1)
  shopt -u nullglob
  [ ${#m[@]} -gt 0 ] && [ -e "${m[0]}" ]
}

unresolved_pointers() {       # $1 file, $2 root the pointers resolve against
  local f=$1 root=$2 p
  # shellcheck disable=SC2016  # the backticks are the markdown delimiters being matched, not a command
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    ( cd "$root" && resolves_glob "$p" ) || echo "$p"
  done < <(header_of "$f" | grep -oE '`[A-Za-z0-9_./*@:-]+`' | tr -d '`' \
             | sed -E 's/:[0-9-]+$//' | grep '/' | grep -v '://' | LC_ALL=C sort -u)
}

echo "--- 0. canary ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. fixtures: each failure mode is caught, a healthy file is not ---"
fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT

cat >"$fx/no-header.md" <<'EOF'
# Workflow registry — ownership freeze (D1)

**Status: FROZEN 2026-09-01** — all eight decisions in §7 are closed (Dave's ALL-CAPS
answers to §7.1–7.5/§7.8 in commit `ed568f8`; §7.6 and §7.7 discussed and closed the
same day). Every action below is executed, not proposed. D2 starts from this table.

## 2. Scheduled persona workflows (live)
EOF

cat >"$fx/live-heading.md" <<'EOF'
# Workflow registry — the D1 record (FROZEN)

**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml`.

## 3. Scheduled platform jobs (live, deterministic)
## 7. Decisions required from Dave
EOF

cat >"$fx/dead-pointer.md" <<'EOF'
# Workflow registry — the D1 record (FROZEN)

**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml`, the unit list in
`config/fleet-units.tsv`, and `design/fixture-path-that-must-not-exist.md:14`, plus
`design/fixture-dir-that-must-not-exist/`. The suite `tests/test_workflow_coverage.sh` exists;
its punctuation twin `tests/test-workflow-coverage.sh` does not.

## 2. Scheduled persona workflows (as recorded 2026-09-01)
EOF

cat >"$fx/healthy.md" <<'EOF'
# Workflow registry — the D1 record (FROZEN)

**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml` (D2, `design/agent-model.md`),
the unit list in `config/fleet-units.tsv`, contracts under `design/contracts/`. A line reference
like `design/workflow-registry.md:77-78` is checked by its path; a home path like `~/agent-workforce/bin`
and a URL like `https://github.com/block/buzz` are not.

---

## 2. Scheduled persona workflows (as recorded 2026-09-01)
## 7. Decisions taken by Dave (2026-09-01)
EOF

# A header that outgrew the old fixed 30-line window: the dead pointer sits on line 34, above
# the `---` on line 38. Checked against a window bounded by the rule; missed by a fixed head -30.
{
  echo '# Workflow registry — the D1 record (FROZEN)'
  echo
  echo '**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml`.'
  for i in $(seq 1 28); do echo "Paragraph line $i of a header that grew."; done
  echo 'One more pointer, added last: `design/fixture-grown-header-pointer.md`.'
  echo
  echo '---'
  echo
  echo '## 2. Scheduled persona workflows (as recorded 2026-09-01)'
} >"$fx/long-header.md"

# No rule at all: the header has no end, so the window is a guess. Named rather than assumed.
cat >"$fx/no-rule.md" <<'EOF'
# Workflow registry — the D1 record (FROZEN)

**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml`.

## 2. Scheduled persona workflows (as recorded 2026-09-01)
EOF

# The three liveness spellings the first regex let through: an H1, a lowercase-insensitive
# match, and `(proposed` without its closing paren.
cat >"$fx/heading-variants.md" <<'EOF'
# Workflow registry (live)

**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml`.

---

## 3. Scheduled platform jobs (LIVE, deterministic)
### 7.1 Decisions (proposed, pending Dave)
EOF

assert 'a file with no header is named for the marker AND the pointer' \
  "[ \"\$(header_missing '$fx/no-header.md' | wc -l)\" = 2 ]"
assert 'a heading that claims liveness is reported by line' \
  "[ \"\$(live_headings '$fx/no-header.md' | wc -l)\" = 1 ]"
assert 'a headed file with two live headings reports both' \
  "[ \"\$(live_headings '$fx/live-heading.md' | wc -l)\" = 2 ]"
assert 'a headed file with live headings still passes the header check' \
  "[ -z \"\$(header_missing '$fx/live-heading.md')\" ]"
assert 'a dead file, a dead directory and a dead punctuation twin are each named' \
  "[ \"\$(unresolved_pointers '$fx/dead-pointer.md' '$REPO_ROOT' | wc -l)\" = 3 ]"
assert 'a dead pointer differing from a live one only in punctuation is still named' \
  "unresolved_pointers '$fx/dead-pointer.md' '$REPO_ROOT' | grep -q tests/test-workflow-coverage.sh"
assert 'the dead-pointer fixture names the missing file, not the real ones beside it' \
  "unresolved_pointers '$fx/dead-pointer.md' '$REPO_ROOT' | grep -q fixture-path-that-must-not-exist"
assert 'a healthy file has its header'                "[ -z \"\$(header_missing '$fx/healthy.md')\" ]"
assert 'and every header pointer resolves'            "[ -z \"\$(unresolved_pointers '$fx/healthy.md' '$REPO_ROOT')\" ]"
assert 'and no live heading'                          "[ -z \"\$(live_headings '$fx/healthy.md')\" ]"
assert 'and its header is bounded by a rule'          "[ -z \"\$(header_unbounded '$fx/healthy.md')\" ]"
assert 'a dead pointer past line 30 but above the rule is still named' \
  "unresolved_pointers '$fx/long-header.md' '$REPO_ROOT' | grep -q fixture-grown-header-pointer"
assert 'a file whose header is closed by no rule is named' \
  "header_unbounded '$fx/no-rule.md' | grep -q 'no --- rule'"
assert 'an H1, an upper-case (LIVE) and a bare (proposed are each reported' \
  "[ \"\$(live_headings '$fx/heading-variants.md' | wc -l)\" = 3 ]"

echo "--- 2. the live registry: $REGISTRY ---"
missing=$(header_missing "$REGISTRY")
dead=$(unresolved_pointers "$REGISTRY" "$REPO_ROOT")
live=$(live_headings "$REGISTRY")
unbounded=$(header_unbounded "$REGISTRY")
hdr_lines=$(header_of "$REGISTRY" | wc -l)

assert "the header ends at a --- rule, so the checked window is the header (${unbounded:-$hdr_lines lines})" \
  "[ -z \"\$unbounded\" ]"
assert "those $hdr_lines lines carry the FROZEN header naming design/agents/ (${missing:-complete})" \
  "[ -z \"\$missing\" ]"
assert "every repo path in the header resolves on disk (${dead:-all resolve})" \
  "[ -z \"\$dead\" ]"
assert "no heading presents the record as live (${live:-none})" \
  "[ -z \"\$live\" ]"

exit $fail
