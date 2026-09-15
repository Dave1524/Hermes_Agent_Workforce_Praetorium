#!/usr/bin/env bash
# T5.3b — schedule changes and retirements as reviewed PRs: worker, records, HTTP seam.
# The assertions and their anchors live in tests/test_control_room_proposals.py
# (including the grep-level pass over bin/control_room_ui/proposals.js); this wrapper also
# lints the hand-run acceptance script, a shell artefact the Python suite cannot shellcheck.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

fail=0
if [ -f tests/acceptance/control_room_proposals.sh ]; then
  bash -n tests/acceptance/control_room_proposals.sh || fail=1
  if command -v shellcheck >/dev/null 2>&1; then
    shellcheck -S error tests/acceptance/control_room_proposals.sh || fail=1
  fi
fi
python3 tests/test_control_room_proposals.py || fail=1
exit $fail
