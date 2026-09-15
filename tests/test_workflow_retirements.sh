#!/usr/bin/env bash
# T5.3b — the retired-workflows registry consumer. Group 1 (every checkout): each [[retired]]
# entry is well-formed and clean in source; the synthetic half-retired entry is named. Group 2
# (box only): every entry is clean live, or FAILS naming the pending residue and the clear
# command. Anchors (::id) live in tests/test_workflow_retirements.py.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
# shellcheck source=tests/box_precondition.sh
. tests/box_precondition.sh

fail=0
python3 tests/test_workflow_retirements.py || fail=1

box_only_with 'the deployed trees a live residue scan reads' \
  "$HOME/agent-workforce/bin" "$HOME/agent-workforce/systemd" || exit "$fail"
RETIREMENTS_LIVE=1 python3 tests/test_workflow_retirements.py RegistryLive.test_registry_entries_are_clean_live || fail=1
exit "$fail"
