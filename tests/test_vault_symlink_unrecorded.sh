#!/usr/bin/env bash
# ~/vault is a symlink that cutover repoints; nothing that must survive cutover records it (T8.5).
#
# Unit files, the qmd collection config and worktree gitdir pointers carry the resolved mirror
# path instead, so a cutover is a deliberate edit of each, never a silent follow of the link.
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

SYMLINK_REF='(/home/dave|%h|~|\$HOME|\$\{HOME\})/vault([/"'"'"'[:space:]]|$)'

# One offending file:line per line; comment lines are prose, not configuration.
symlink_refs() {
  grep -HnE "$SYMLINK_REF" "$@" 2>/dev/null | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | cut -d: -f1,2 || true
}

installed_units() {
  local u d
  for u in "$REPO_ROOT"/systemd/*.service "$REPO_ROOT"/systemd/*.timer; do
    [ -e /etc/systemd/system/"$(basename "$u")" ] && echo /etc/systemd/system/"$(basename "$u")"
  done
  for u in "$REPO_ROOT"/systemd/user/*; do
    d="$HOME/.config/systemd/user/$(basename "$u")"
    [ -f "$d" ] && echo "$d"
  done
  return 0
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- 0. canaries ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checker names every spelling of the symlink, and nothing else (::vault-symlink-checker) ---"
printf 'ConditionPathExists=/home/dave/vault/.git\n' > "$TMP/abs.service"
printf 'WorkingDirectory=%%h/vault\n'                 > "$TMP/spec.service"
printf '    path: /home/dave/vault\n'                  > "$TMP/index.yml"
printf 'gitdir: ~/vault/.git/worktrees/inbox\n'        > "$TMP/gitdir"
printf '# ~/vault is the symlink\nConditionPathExists=/home/dave/dev/obsidian-ai-os-boxsafe/.git\nX=/home/dave/vaultish\n' > "$TMP/clean"
for f in abs.service spec.service index.yml gitdir; do
  assert "a symlink reference in $f is named" "[ -n \"\$(symlink_refs '$TMP/$f')\" ]"
done
assert 'a resolved path, a comment and a longer name are not' "[ -z \"\$(symlink_refs '$TMP/clean')\" ]"

echo "--- 2. unit sources in this checkout (::vault-symlink-source) ---"
src=$(symlink_refs "$REPO_ROOT"/systemd/* "$REPO_ROOT"/systemd/*/* | sed "s|$REPO_ROOT/||" | tr '\n' ' ')
assert "no unit source records ~/vault (${src:-none})" "[ -z '$src' ]"

echo "--- 3. installed units, the qmd collection, worktree gitdirs (::vault-symlink-live) ---"
if box_only_with 'the installed units, qmd config and vault worktrees' \
     "$HOME/.config/qmd/index.yml" "$HOME/agent-worktrees"; then
  mapfile -t units < <(installed_units)
  gitdirs=("$HOME"/agent-worktrees/*/.git)
  live=$(symlink_refs "${units[@]}" "$HOME/.config/qmd/index.yml" "${gitdirs[@]}" | tr '\n' ' ')
  echo "  info: scanned ${#units[@]} installed units, the qmd config, ${#gitdirs[@]} worktree pointers"
  assert "nothing live records ~/vault (${live:-none})" "[ -z '$live' ]"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
