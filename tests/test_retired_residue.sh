#!/usr/bin/env bash
# Retired runtimes stay retired on the box, not only in the tree (T8.5).
#
# test_hermes_residue.sh scans the checkout. This suite covers what a checkout cannot carry:
# the Hermes install and the Ollama binary (removed 2026-09-18), discord-bot.service (staged,
# never installed), and references to ~/dev/vault-boxsafe (deleted 2026-08-12) in source or in
# the installed units.
set -uo pipefail

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

# Each lister prints one offender per line; empty output is clean.
present_paths()  { local p; for p in "$@"; do [ -e "$p" ] && echo "$p"; done; return 0; }
units_named()    { local d; for d in "${@:2}"; do [ -e "$d/$1" ] && echo "$d/$1"; done; return 0; }
stale_mirror()   { grep -rl 'vault-boxsafe' "$@" 2>/dev/null || true; }
on_path()        { PATH="$1" command -v "$2" || true; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- 0. canaries ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checkers detect residue on fixtures (::retired-residue-checker) ---"
mkdir -p "$TMP/home/.hermes" "$TMP/units" "$TMP/clean-units" "$TMP/bin" "$TMP/src"
: > "$TMP/units/discord-bot.service"
printf '#!/bin/sh\n' > "$TMP/bin/ollama" && chmod +x "$TMP/bin/ollama"
printf 'WorkingDirectory=/home/dave/dev/vault-boxsafe\n' > "$TMP/src/x.service"
assert 'a leftover ~/.hermes is named'           "[ -n \"\$(present_paths '$TMP/home/.hermes')\" ]"
assert 'an installed discord-bot.service is named' \
  "[ -n \"\$(units_named discord-bot.service '$TMP/units' '$TMP/clean-units')\" ]"
assert 'an ollama on PATH is found'              "[ -n \"\$(on_path '$TMP/bin' ollama)\" ]"
assert 'a vault-boxsafe reference is named'      "[ -n \"\$(stale_mirror '$TMP/src')\" ]"
assert 'clean inputs name nothing' \
  "[ -z \"\$(present_paths '$TMP/home/.nothing')\$(units_named discord-bot.service '$TMP/clean-units')\$(stale_mirror '$TMP/clean-units')\" ]"

echo "--- 2. the checkout (::retired-residue-checkout) ---"
refs=$(cd "$REPO_ROOT" && stale_mirror bin systemd buzz-team config)
assert "no source references ~/dev/vault-boxsafe (${refs:-none})" "[ -z '$refs' ]"

echo "--- 3. the live box (::retired-residue-live) ---"
if box_only_with 'the installed units and home tree a checkout cannot carry' \
     "$HOME/agent-workforce/bin" "$HOME/.config/systemd/user"; then
  left=$(present_paths "$HOME/.hermes" "$HOME/.local/bin/hermes")
  ollama=$(on_path "$PATH:/usr/local/bin:/usr/bin" ollama)
  discord=$(units_named discord-bot.service /etc/systemd/system "$HOME/.config/systemd/user")
  live_refs=$(stale_mirror /etc/systemd/system "$HOME/.config/systemd/user")
  assert "no Hermes install (${left:-none})"                  "[ -z '$left' ]"
  assert "no ollama binary (${ollama:-none})"                 "[ -z '$ollama' ]"
  assert "discord-bot.service installed nowhere (${discord:-none})" "[ -z '$discord' ]"
  assert "no installed unit references vault-boxsafe (${live_refs:-none})" "[ -z '$live_refs' ]"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
