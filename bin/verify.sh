#!/usr/bin/env bash
# Verification gate for agent-workforce (Praetorium). Run from repo root.
set -euo pipefail
cd "$(dirname "$0")/.."

fail=0
for f in bin/*.sh; do
  echo "syntax: $f"
  bash -n "$f" || fail=1
done

echo "--- shellcheck (error-severity, must be clean) ---"
shellcheck -S error bin/*.sh || fail=1

echo "--- shellcheck (full, advisory only) ---"
shellcheck bin/*.sh || true

if [ -d tests ]; then
  for t in tests/*.sh; do
    [ -e "$t" ] || continue
    echo "test: $t"
    bash "$t" || fail=1
  done
fi

exit $fail
