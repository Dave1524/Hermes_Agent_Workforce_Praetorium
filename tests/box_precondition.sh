#!/usr/bin/env bash
# Shared precondition guard for the assertions that read Praetorium itself.
#
# Three suites assert state no checkout carries — the deployed runtime tree, the installed
# /etc units, the fleet's --user settings, the live qmd index. Off the box they fail for a
# reason that has nothing to do with the diff under review, which is exactly what makes a
# PR gate get muted. So they skip instead.
#
# They skip OUT LOUD. Every skip prints one `SKIP: <test> — <reason> (absent: <path>)`
# line, and .github/workflows/verify.yml diffs the collected set against
# tests/ci-expected-skips.txt. A suite that starts skipping for a new reason fails the gate
# rather than quietly shrinking it — the failure mode this file would otherwise introduce.
#
# Paths are printed $HOME-relative so one expectation file holds on any runner.
#
# Executing this file directly is a deliberate no-op, so bin/verify.sh's tests/*.sh sweep
# stays green (same contract as rhythm_test_lib.sh).

# 0 = every path is present, run the assertions. 1 = at least one is missing; the SKIP line
# has been printed and the caller must skip. Never exits: whole-file callers pair it with
# `|| exit 77`, so the decision to abandon the rest stays visible at the call site.
box_only() {
  local reason=$1 p missing=()
  shift
  for p in "$@"; do
    [ -e "$p" ] || missing+=("${p/#$HOME/\~}")
  done
  [ ${#missing[@]} -eq 0 ] && return 0
  printf 'SKIP: %s — %s (absent: %s)\n' \
    "$(basename "${BASH_SOURCE[1]}")" "$reason" "${missing[*]}"
  return 1
}

if [ "${BASH_SOURCE[0]}" = "$0" ]; then
  echo "  (shared precondition guard for the box-reading suites — nothing to run)"
  exit 0
fi
