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

if [ -d tests ]; then
  # Most tests mktemp fixtures without a cleanup trap. Owning one temp root here
  # beats 30 traps a new test can forget: on 2026-08-13 the accumulated leak hit
  # /tmp's 1,048,576-inode ceiling with 13G of blocks still free, so `df -h` read
  # healthy while mktemp, git commit and the gate itself failed with ENOSPC.
  run_tmp=$(mktemp -d)
  trap 'rm -rf "$run_tmp"' EXIT
  export TMPDIR="$run_tmp"

  for t in tests/*.sh; do
    [ -e "$t" ] || continue
    echo "test: $t"
    bash "$t" || fail=1
  done
fi

exit $fail
