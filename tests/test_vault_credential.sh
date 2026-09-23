#!/usr/bin/env bash
# The box pushes to GitHub as the App, from both clones, and nothing else can (T8.5).
#
# Each clone carries the helper pair `''` then github_app_credential.py: the empty line clears
# the global `gh auth git-credential` helper, which would otherwise answer first as Dave1524.
# The canonical vault also keeps its local pre-push guard installed byte-equal to source, and
# the dead SSH alias github-canonical stays refused.
set -uo pipefail

VAULT="${VAULT:-$HOME/dev/Obsidian_AI_Operating_System}"
APP_HELPER='!python3 /home/dave/.local/bin/github_app_credential.py'

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

helpers()        { git -C "$1" config --local --get-all credential.https://github.com.helper 2>/dev/null; }
app_helper_ok()  { [ "$(helpers "$1")" = "$(printf '\n%s' "$APP_HELPER")" ]; }
hook_installed() { cmp -s "$1/.git/hooks/pre-push" "$1/00_system/tools/hooks/pre-push"; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fixture_repo() {
  git init -q "$1"
  local h
  for h in "${@:2}"; do git -C "$1" config --local --add credential.https://github.com.helper "$h"; done
}

echo "--- 0. canaries ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checkers detect each failure on fixtures ---"
fixture_repo "$TMP/good" '' "$APP_HELPER"
fixture_repo "$TMP/no-clear" "$APP_HELPER"
fixture_repo "$TMP/dave" '!/usr/bin/gh auth git-credential'
fixture_repo "$TMP/none"
assert 'the cleared App helper pair passes'                 "app_helper_ok '$TMP/good'"
assert 'the App helper without the clearing line is flagged' "! app_helper_ok '$TMP/no-clear'"
assert 'a clone answering as Dave1524 is flagged'           "! app_helper_ok '$TMP/dave'"
assert 'a clone with no helper is flagged'                  "! app_helper_ok '$TMP/none'"
mkdir -p "$TMP/good/00_system/tools/hooks"
printf '#!/bin/sh\nexit 0\n' > "$TMP/good/00_system/tools/hooks/pre-push"
assert 'a missing pre-push hook is flagged'                 "! hook_installed '$TMP/good'"
cp "$TMP/good/00_system/tools/hooks/pre-push" "$TMP/good/.git/hooks/pre-push"
assert 'a byte-equal installed hook passes'                 "hook_installed '$TMP/good'"
printf '# drifted\n' >> "$TMP/good/.git/hooks/pre-push"
assert 'a drifted installed hook is flagged'                "! hook_installed '$TMP/good'"

echo "--- 2. the live clones ---"
if box_only_with 'the canonical vault clone and its installed hooks' "$VAULT/.git"; then
  assert 'the canonical vault pushes as the App'           "app_helper_ok '$VAULT'"
  assert 'its pre-push guard is installed, byte-equal'     "hook_installed '$VAULT'"
  assert 'this repo pushes as the App'                     "app_helper_ok '$REPO_ROOT'"
  ssh_out=$(timeout 10 ssh -o BatchMode=yes -o ConnectTimeout=8 -T git@github-canonical 2>&1)
  if grep -q 'Permission denied' <<<"$ssh_out"; then
    echo "  ok: the SSH alias github-canonical is refused"
  elif grep -q 'successfully authenticated' <<<"$ssh_out"; then
    echo "  FAIL: the SSH alias github-canonical authenticates — a second push path is live"; fail=1
  else
    echo "  info: github-canonical probe inconclusive (network?): ${ssh_out:0:80}"
  fi
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
