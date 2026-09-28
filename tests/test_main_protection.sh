#!/usr/bin/env bash
# Offline negative cases everywhere; effective GitHub rules only on Praetorium.
set -euo pipefail
cd "$(dirname "$0")/.."
python3 tests/test_main_protection.py
# shellcheck source=tests/box_precondition.sh
. tests/box_precondition.sh
box_only_with 'the installed GitHub App helper for the live protection check' \
  "$HOME/.local/bin/github_app_credential.py" || exit 77
python3 bin/main_protection.py --live
