#!/usr/bin/env bash
# Verification gate for agent-workforce (Praetorium). Run from repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

# Collect every shell script in bin/: *.sh plus extension-less executables whose
# shebang is bash/sh (e.g. bin/auto-sync, bin/opencode-observe). Python helpers
# (#!/usr/bin/env python3) are excluded so bash -n / shellcheck never see them.
bash_shebang='^#!.*(bash|/sh( |$)|env sh( |$))'
scripts=()
for f in bin/*; do
  [ -f "$f" ] || continue
  case "$f" in
    *.sh) scripts+=("$f") ;;
    *) # Matched without a pipe: `grep -q` exits on the match, SIGPIPEs head, and under
       # pipefail the script is then silently dropped from the gate it just qualified for.
       shebang=''
       read -r shebang < "$f" || true
       if [[ $shebang =~ $bash_shebang ]]; then
         scripts+=("$f")
       fi ;;
  esac
done

for f in "${scripts[@]}"; do
  echo "syntax: $f"
  bash -n "$f" || fail=1
done

echo "--- shellcheck (error-severity, must be clean) ---"
shellcheck -S error "${scripts[@]}" || fail=1

echo "--- shellcheck (full, advisory only) ---"
shellcheck "${scripts[@]}" || true

# Source-vs-deployed drift (D8). A hard fail: a green gate that says nothing about what is
# RUNNING has already produced two live outages (eval-spec.md 7.3). Note the ordering this
# imposes — see docs/runbook.md § Deploy ordering: adding a bin/ script makes this red until
# bin/deploy runs, so the loop is edit -> deploy -> verify -> commit, not the usual order.
echo "--- deploy drift (source vs deployed) ---"
bash bin/check_deploy_drift.sh || fail=1

if [ -d tests ]; then
  # Most tests mktemp fixtures without a cleanup trap. Owning one temp root here
  # beats 30 traps a new test can forget: on 2026-08-13 the accumulated leak hit
  # /tmp's 1,048,576-inode ceiling with 13G of blocks still free, so `df -h` read
  # healthy while mktemp, git commit and the gate itself failed with ENOSPC.
  run_tmp=$(mktemp -d)
  trap 'rm -rf "$run_tmp"' EXIT
  export TMPDIR="$run_tmp"

  # Buffered rather than streamed so the SKIP lines can be collected. A suite that opts out
  # of a box precondition (tests/box_precondition.sh) has to be counted somewhere; the
  # alternative is a gate that shrinks silently off the box. 77 is the whole-file skip
  # convention, so it is not a failure — anything else non-zero is.
  gate_out="$run_tmp/.verify-current"
  skips=()
  for t in tests/*.sh; do
    [ -e "$t" ] || continue
    echo "test: $t"
    rc=0
    bash "$t" >"$gate_out" 2>&1 || rc=$?
    cat "$gate_out"
    [ "$rc" = 0 ] || [ "$rc" = 77 ] || fail=1
    while IFS= read -r line; do skips+=("$line"); done < <(grep '^SKIP: ' "$gate_out")
  done

  # Printed unconditionally when non-empty: the CI gate diffs this set against
  # tests/ci-expected-skips.txt, which is what stops a skip from becoming invisible.
  if [ ${#skips[@]} -gt 0 ]; then
    echo "--- skipped (${#skips[@]}) ---"
    printf '%s\n' "${skips[@]}"
  fi
fi

exit $fail
