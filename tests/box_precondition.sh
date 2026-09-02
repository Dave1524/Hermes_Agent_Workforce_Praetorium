#!/usr/bin/env bash
# Shared precondition guard for the assertions that only hold on Praetorium.
#
# Two shapes, because the suites need both directions:
#
#   box_only_with     — this box HAS something no checkout carries: the deployed runtime
#                       tree, the installed /etc units, the fleet's --user settings, the
#                       live qmd index.
#   box_only_without  — this box LACKS something a hosted runner has. test_fetch_status's
#                       negative case documents exactly that ("relies on no system chrome
#                       on PATH (true on this box)"), and GitHub's runner image ships one.
#
# Off the box these go red for reasons unrelated to the diff, which is what gets a PR gate
# muted. So they skip — OUT LOUD. Every skip prints one `SKIP: <test> — <reason> (...)`
# line, and .github/workflows/verify.yml diffs the collected set against
# tests/ci-expected-skips.txt. A suite that starts skipping for a new reason, or stops,
# fails the gate rather than quietly shrinking it — the failure mode this file would
# otherwise introduce.
#
# Both detail lists are stable by construction so one expectation file holds on any runner:
# `with` prints its missing paths $HOME-relative, and `without` prints the names it PROBED
# rather than the ones it happened to find (which vary by runner image).
#
# Executing this file directly is a deliberate no-op, so bin/verify.sh's tests/*.sh sweep
# stays green (same contract as rhythm_test_lib.sh).

# BASH_SOURCE[2] is the test that called the predicate that called this.
_box_skip() {
  printf 'SKIP: %s — %s (%s: %s)\n' \
    "$(basename "${BASH_SOURCE[2]}")" "$1" "$2" "$3"
}

# 0 = every path is present, run the assertions. 1 = at least one is missing; the SKIP line
# has been printed and the caller must skip. Never exits: whole-file callers pair it with
# `|| exit 77`, so the decision to abandon the rest stays visible at the call site.
box_only_with() {
  local reason=$1 p missing=()
  shift
  for p in "$@"; do
    [ -e "$p" ] || missing+=("${p/#$HOME/\~}")
  done
  [ ${#missing[@]} -eq 0 ] && return 0
  _box_skip "$reason" absent "${missing[*]}"
  return 1
}

# The mirror: 0 = none of these commands is on PATH, so the absence the assertion depends
# on is real. 1 = at least one exists and the assertion would be measuring the runner.
box_only_without() {
  local reason=$1 c
  shift
  for c in "$@"; do
    if command -v "$c" >/dev/null 2>&1; then
      _box_skip "$reason" probed "$*"
      return 1
    fi
  done
  return 0
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "  (shared precondition guard for the box-reading suites — nothing to run)"
  exit 0
fi
