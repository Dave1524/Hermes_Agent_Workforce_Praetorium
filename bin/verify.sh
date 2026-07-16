#!/usr/bin/env bash
# Verification gate for agent-workforce (Praetorium). Run from repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0

# Collect every shell script in bin/: *.sh plus extension-less executables whose
# shebang is bash/sh (e.g. bin/auto-sync, bin/opencode-observe). Python helpers
# (#!/usr/bin/env python3) are excluded so bash -n / shellcheck never see them.
scripts=()
for f in bin/*; do
  [ -f "$f" ] || continue
  case "$f" in
    *.sh) scripts+=("$f") ;;
    *) if head -n1 "$f" | grep -Eq '^#!.*(bash|/sh( |$)|env sh( |$))'; then
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
  for t in tests/*.sh; do
    [ -e "$t" ] || continue
    echo "test: $t"
    bash "$t" || fail=1
  done
fi

exit $fail
