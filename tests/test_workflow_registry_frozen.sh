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
# THE THREE INVARIANTS, each on the first HEADER_LINES lines because that is what a reader
# and the land gate look at:
#
#   1. The header is present: a `FROZEN RECORD` marker, and `design/agents/` named as where
#      workflows are declared now. The bare word FROZEN discriminates nothing — the pre-freeze
#      header already read `FROZEN 2026-09-01` while calling itself the single source of truth.
#   2. Every backticked repo path in the header resolves on disk. A pointer at a moved or
#      renamed file is the defect the header exists to prevent, so a stale one goes red by
#      name. Globs resolve as globs (design/agents/*.toml); a trailing slash is a directory.
#      A line reference (`file.md:77-78`) is checked by its path half, suffix stripped, so a
#      renamed file hides behind no line number. A `~` home path and a URL are not repo paths
#      and are not checked — stated so a green run is not read as covering them.
#   3. No `##` heading anywhere in the file claims liveness — `(live`, `(proposed)`,
#      "must resolve", "required from". Those were the five headings that made the frozen
#      file read as an open worklist; a heading is the cheapest place the claim can come back.
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

HEADER_LINES=30

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

header_missing() {            # $1 file
  local hdr
  hdr=$(head -n "$HEADER_LINES" "$1")
  grep -q 'FROZEN RECORD' <<<"$hdr"   || echo 'no FROZEN RECORD marker'
  grep -q 'design/agents/' <<<"$hdr"  || echo 'no design/agents/ pointer'
}

live_headings() {             # $1 file
  grep -nE '^##.*(\(live|\(proposed\)|must resolve|required from)' "$1"
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
  done < <(head -n "$HEADER_LINES" "$f" | grep -oE '`[A-Za-z0-9_./*@:-]+`' | tr -d '`' \
             | sed -E 's/:[0-9-]+$//' | grep '/' | grep -v '://' | sort -u)
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
`design/fixture-dir-that-must-not-exist/`.

## 2. Scheduled persona workflows (as recorded 2026-09-01)
EOF

cat >"$fx/healthy.md" <<'EOF'
# Workflow registry — the D1 record (FROZEN)

**Status: FROZEN RECORD.** Live declarations: `design/agents/*.toml` (D2, `design/agent-model.md`),
the unit list in `config/fleet-units.tsv`, contracts under `design/contracts/`. A line reference
like `design/workflow-registry.md:77-78` is checked by its path; a home path like `~/agent-workforce/bin`
and a URL like `https://github.com/block/buzz` are not.

## 2. Scheduled persona workflows (as recorded 2026-09-01)
## 7. Decisions taken by Dave (2026-09-01)
EOF

assert 'a file with no header is named for the marker AND the pointer' \
  "[ \"\$(header_missing '$fx/no-header.md' | wc -l)\" = 2 ]"
assert 'a heading that claims liveness is reported by line' \
  "[ \"\$(live_headings '$fx/no-header.md' | wc -l)\" = 1 ]"
assert 'a headed file with two live headings reports both' \
  "[ \"\$(live_headings '$fx/live-heading.md' | wc -l)\" = 2 ]"
assert 'a headed file with live headings still passes the header check' \
  "[ -z \"\$(header_missing '$fx/live-heading.md')\" ]"
assert 'a dead file pointer and a dead directory pointer are each named' \
  "[ \"\$(unresolved_pointers '$fx/dead-pointer.md' '$REPO_ROOT' | wc -l)\" = 2 ]"
assert 'the dead-pointer fixture names the missing file, not the real ones beside it' \
  "unresolved_pointers '$fx/dead-pointer.md' '$REPO_ROOT' | grep -q fixture-path-that-must-not-exist"
assert 'a healthy file has its header'                "[ -z \"\$(header_missing '$fx/healthy.md')\" ]"
assert 'and every header pointer resolves'            "[ -z \"\$(unresolved_pointers '$fx/healthy.md' '$REPO_ROOT')\" ]"
assert 'and no live heading'                          "[ -z \"\$(live_headings '$fx/healthy.md')\" ]"

echo "--- 2. the live registry: $REGISTRY ---"
missing=$(header_missing "$REGISTRY")
dead=$(unresolved_pointers "$REGISTRY" "$REPO_ROOT")
live=$(live_headings "$REGISTRY")

assert "the first $HEADER_LINES lines carry the FROZEN header naming design/agents/ (${missing:-complete})" \
  "[ -z \"\$missing\" ]"
assert "every repo path in the header resolves on disk (${dead:-all resolve})" \
  "[ -z \"\$dead\" ]"
assert "no heading presents the record as live (${live:-none})" \
  "[ -z \"\$live\" ]"

exit $fail
