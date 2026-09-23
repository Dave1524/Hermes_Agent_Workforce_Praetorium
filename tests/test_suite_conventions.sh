#!/usr/bin/env bash
# Two conventions CLAUDE.md used to state and nothing held (T8.5):
#
#   1. Every tests/*.sh that defines assert() scopes pipefail off inside it and carries the
#      `yes | grep -q y` canary. Under pipefail an early-exiting reader SIGPIPEs its producer,
#      so a true assertion fails and a negated one passes unread. Nine suites broke this while
#      the prose said every suite complied.
#   2. Every journalctl call in buzz-team/*.sh passes --utc. buzz-acp logs UTC and journalctl
#      renders local time; an unnormalised timeline once inverted cause and effect.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

assert_body()      { awk '/^assert\(\)/{on=1} on{print} on && /}[[:space:]]*;?[[:space:]]*$/{exit}' "$1"; }
defines_assert()   { grep -q '^assert()' "$1"; }
scopes_pipefail()  { assert_body "$1" | grep 'set +o pipefail' >/dev/null; }
has_canary()       { grep -qF 'yes | grep -q y' "$1"; }

# One offending path per line.
unconventional() {
  local f
  for f in "$@"; do
    defines_assert "$f" || continue
    if ! scopes_pipefail "$f" || ! has_canary "$f"; then echo "$f"; fi
  done
  return 0
}

local_time_journalctl() {
  grep -HnE '(^|[^-[:alnum:]_])journalctl[[:space:]]' "$@" 2>/dev/null \
    | grep -vE '^[^:]+:[0-9]+:[[:space:]]*#' | grep -v -- '--utc' || true
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

echo "--- 0. canaries ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checkers detect both conventions broken on fixtures (::conventions-checker) ---"
cat > "$TMP/bare.sh" <<'SH'
assert() { local d=$1 c=$2; if eval "$c"; then echo ok; else fail=1; fi; }
assert 'canary' "yes | grep -q y"
SH
cat > "$TMP/no-canary.sh" <<'SH'
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo ok; else fail=1; fi
  eval "$pf"
}
SH
{ cat "$TMP/no-canary.sh"; echo "assert 'canary' \"yes | grep -q y\""; } > "$TMP/good.sh"
printf 'no assert here\n' > "$TMP/plain.sh"
assert 'an assert() that leaves pipefail on is flagged'    "[ \"\$(unconventional '$TMP/bare.sh')\" = '$TMP/bare.sh' ]"
assert 'a scoped assert() with no canary is flagged'       "[ \"\$(unconventional '$TMP/no-canary.sh')\" = '$TMP/no-canary.sh' ]"
assert 'a scoped assert() with the canary is not'          "[ -z \"\$(unconventional '$TMP/good.sh')\" ]"
assert 'a file defining no assert() is not'                "[ -z \"\$(unconventional '$TMP/plain.sh')\" ]"

printf 'journalctl --user -u x --since "$w" -o cat\n' > "$TMP/local.sh"
printf 'journalctl --utc --user -u x -o cat\n# journalctl in a comment\nprintf journalctl-free\n' > "$TMP/utc.sh"
assert 'a journalctl call without --utc is flagged'        "[ -n \"\$(local_time_journalctl '$TMP/local.sh')\" ]"
assert 'with --utc, in a comment, or as a substring it is not' "[ -z \"\$(local_time_journalctl '$TMP/utc.sh')\" ]"

echo "--- 2. this checkout (::conventions-checkout) ---"
bad=$(unconventional "$REPO_ROOT"/tests/*.sh | sed "s|$REPO_ROOT/||" | tr '\n' ' ')
assert "every tests/*.sh assert() scopes pipefail and carries the canary (${bad:-none} do not)" "[ -z '$bad' ]"
local_calls=$(local_time_journalctl "$REPO_ROOT"/buzz-team/*.sh | sed "s|$REPO_ROOT/||" | cut -d: -f1,2 | tr '\n' ' ')
assert "every journalctl in buzz-team/*.sh passes --utc (${local_calls:-none} do not)" "[ -z '$local_calls' ]"

exit $fail
