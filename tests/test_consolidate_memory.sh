#!/usr/bin/env bash
# Smoke test for bin/consolidate_memory.sh (NUC-21). Scratch $HOME, no network.
# Proves the consolidation is bounded, idempotent, and fail-soft. Run via verify.sh.
set -uo pipefail   # NOT -e: grep -c exits 1 on no-match, which is expected here

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/consolidate_memory.sh"
DELIM=$'\n§\n'

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

sandbox() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/.hermes/profiles/claudius/memories" "$h/agent-workforce/logs"
  echo "$h"
}
memf() { echo "$1/.hermes/profiles/claudius/memories/MEMORY.md"; }
sandbox_profiles() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/agent-workforce/logs"
  local p
  for p in "$@"; do mkdir -p "$h/.hermes/profiles/$p/memories"; done
  echo "$h"
}
memf_profile() { echo "$1/.hermes/profiles/$2/memories/MEMORY.md"; }
run() { HOME="$1" MEM_MAX_ENTRIES="$2" MEM_MAX_CHARS="$3" bash "$SCRIPT" >/dev/null 2>&1; echo $?; }
bakglob() { echo "$(dirname "$1")"/MEMORY.md.bak.consolidate.*; }
count_entries() { local f=$1 d; [ -s "$f" ] || { echo 0; return; }; d=$(grep -c '^§$' "$f"); echo $(( d + 1 )); }
mk_store() {
  local f=$1 count=$2 pad=$3 i content="" body e
  body=$(head -c "$pad" < /dev/zero | tr '\0' 'x')
  for i in $(seq 1 "$count"); do
    e=$(printf 'entry-%02d %s' "$i" "$body")
    if [ -z "$content" ]; then content="$e"; else content="$content$DELIM$e"; fi
  done
  printf '%s' "$content" > "$f"
}

echo '--- scenario 1: over cap -> bounded + idempotent, newest kept ---'
h1=$(sandbox); f1=$(memf "$h1"); mk_store "$f1" 20 150
rc=$(run "$h1" 8 900)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'entry count bounded <=8' "[ \"\$(count_entries '$f1')\" -le 8 ]"
assert 'byte size <= 900' "[ \"\$(wc -c < '$f1')\" -le 900 ]"
assert 'store not emptied' "[ -s '$f1' ]"
assert 'newest entry-20 kept' "grep -q 'entry-20' '$f1'"
assert 'oldest entry-01 dropped' "! grep -q 'entry-01' '$f1'"
assert 'backup written' "ls $(bakglob "$f1") >/dev/null 2>&1"
sa=$(md5sum "$f1" | awk '{print $1}'); rc2=$(run "$h1" 8 900); sb=$(md5sum "$f1" | awk '{print $1}')
assert 'second run exits 0' "[ '$rc2' = 0 ]"
assert 'idempotent (byte-identical)' "[ '$sa' = '$sb' ]"

echo '--- scenario 2: empty/absent store -> no-op exit 0 ---'
h2=$(sandbox); f2=$(memf "$h2")
rc=$(run "$h2" 8 900)
assert 'absent store exits 0' "[ '$rc' = 0 ]"
assert 'absent store not created' "[ ! -e '$f2' ]"
: > "$f2"
rc=$(run "$h2" 8 900)
assert 'empty store exits 0' "[ '$rc' = 0 ]"
assert 'empty store not deleted, not filled' "[ ! -s '$f2' ]"

echo '--- scenario 3: oversized newest entry -> fail-soft, store preserved ---'
h3=$(sandbox); f3=$(memf "$h3")
big=$(printf 'entry-99 %s' "$(head -c 2000 < /dev/zero | tr '\0' 'y')")
printf 'entry-01 small%sentry-02 small%s%s' "$DELIM" "$DELIM" "$big" > "$f3"
before=$(md5sum "$f3" | awk '{print $1}')
rc=$(run "$h3" 8 900)
after=$(md5sum "$f3" | awk '{print $1}')
assert 'fail-soft exits 0' "[ '$rc' = 0 ]"
assert 'store preserved byte-for-byte' "[ '$before' = '$after' ]"
assert 'no backup on preserve path' "! ls $(bakglob "$f3") >/dev/null 2>&1"

echo '--- scenario 4: exact duplicates -> deduped (newest kept), idempotent ---'
h4=$(sandbox); f4=$(memf "$h4")
# unique1, DUP, unique2, DUP, unique3 (DUP appears twice, byte-identical)
printf 'unique-1%sdupe-entry payload%sunique-2%sdupe-entry payload%sunique-3' \
  "$DELIM" "$DELIM" "$DELIM" "$DELIM" > "$f4"
rc=$(run "$h4" 8 900)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'duplicate collapsed to one occurrence' "[ \"\$(grep -c 'dupe-entry payload' '$f4')\" = 1 ]"
assert 'entry count is 4 (5 - 1 dupe)' "[ \"\$(count_entries '$f4')\" = 4 ]"
assert 'all three uniques kept' "grep -q 'unique-1' '$f4' && grep -q 'unique-2' '$f4' && grep -q 'unique-3' '$f4'"
sc=$(md5sum "$f4" | awk '{print $1}'); rc2=$(run "$h4" 8 900); sd=$(md5sum "$f4" | awk '{print $1}')
assert 'second run exits 0' "[ '$rc2' = 0 ]"
assert 'idempotent after dedup' "[ '$sc' = '$sd' ]"

echo '--- scenario 5: multiple profiles consolidated independently in one run ---'
h5=$(sandbox_profiles alpha beta)
fa=$(memf_profile "$h5" alpha); mk_store "$fa" 20 150
fb=$(memf_profile "$h5" beta)
bigb=$(printf 'entry-99 %s' "$(head -c 2000 < /dev/zero | tr '\0' 'y')")
printf 'entry-01 small%sentry-02 small%s%s' "$DELIM" "$DELIM" "$bigb" > "$fb"
before_b=$(md5sum "$fb" | awk '{print $1}')
rc=$(run "$h5" 8 900)
assert 'multi-profile run exits 0' "[ '$rc' = 0 ]"
assert 'profile alpha bounded <=8' "[ \"\$(count_entries '$fa')\" -le 8 ]"
assert 'profile alpha newest kept' "grep -q 'entry-20' '$fa'"
assert 'profile alpha backup written' "ls $(bakglob "$fa") >/dev/null 2>&1"
assert 'profile beta preserved (fail-soft), unaffected by profile alpha' "[ '$(md5sum "$fb" | awk '{print $1}')' = '$before_b' ]"
assert 'profile beta no backup on preserve path' "! ls $(bakglob "$fb") >/dev/null 2>&1"

echo '--- scenario 6: no profile directories at all -> no-op exit 0 ---'
h6=$(mktemp -d); mkdir -p "$h6/agent-workforce/logs"
rc=$(run "$h6" 8 900)
assert 'no profiles present exits 0' "[ '$rc' = 0 ]"

exit $fail
