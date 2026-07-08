#!/usr/bin/env bash
# NUC-21 working memory: nightly, mechanical consolidation/prune of the
# research_analyst Hermes-native episodic memory (MEMORY.md). NO LLM, NO network.
#
# On-disk contract (hermes tools/memory_tool.py MemoryStore): entries are
# separated by a line that is exactly § (U+00A7, bytes C2 A7); joined by \n§\n;
# there is NO trailing newline; each entry is stored stripped.
#
# Guarantees: bounded (<= caps), idempotent (a 2nd run is byte-identical), and
# fail-soft — on ANY problem the ORIGINAL store is left byte-for-byte untouched
# and we still exit 0. Never empties or corrupts the store.
set -uo pipefail   # deliberately NOT -e: every exit is controlled, for fail-soft

MEM_DIR="${MEM_DIR:-$HOME/.hermes/profiles/research_analyst/memories}"
MEM_FILE="${MEM_FILE:-$MEM_DIR/MEMORY.md}"
MEM_LOCK="${MEM_LOCK:-$MEM_FILE.lock}"
MEM_MAX_ENTRIES="${MEM_MAX_ENTRIES:-12}"
MEM_MAX_CHARS="${MEM_MAX_CHARS:-7000}"
MEM_BACKUP_KEEP="${MEM_BACKUP_KEEP:-5}"
LOG_DIR="${LOG_DIR:-$HOME/agent-workforce/logs}"
DELIM=$'\n§\n'   # literal newline, U+00A7, newline — MUST match memory_tool.py

mkdir -p "$LOG_DIR" 2>/dev/null || true
log() { echo "$(date -Is) consolidate_memory: $*" >>"$LOG_DIR/consolidate_memory.log" 2>/dev/null || true; }

# ── No-op: absent or whitespace-only store ──
[ -f "$MEM_FILE" ] || { log "no-op: store absent ($MEM_FILE)"; exit 0; }
if [ ! -s "$MEM_FILE" ] || ! grep -q '[^[:space:]]' "$MEM_FILE" 2>/dev/null; then
  log "no-op: store empty"; exit 0
fi

# ── Serialize against live memory-tool writes via the SAME lock file it uses ──
exec 9>"$MEM_LOCK" 2>/dev/null || { log "no-op: cannot open lock"; exit 0; }
flock -w 30 9 || { log "no-op: lock busy — skip this cycle"; exit 0; }

# ── Parse entries: a boundary is a line that is exactly § ──
entries=(); cur=""; have=0
while IFS= read -r line || [ -n "$line" ]; do
  if [ "$line" = "§" ]; then
    entries+=("$cur"); cur=""; have=0
  elif [ "$have" -eq 0 ]; then
    cur="$line"; have=1
  else
    cur="$cur"$'\n'"$line"
  fi
done < "$MEM_FILE"
entries+=("$cur")

# ── Strip each entry (match MemoryStore .strip()); drop empties ──
strip() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"; printf '%s' "$s"; }
clean=()
for e in "${entries[@]}"; do
  s="$(strip "$e")"
  [ -n "$s" ] && clean+=("$s")
done
n=${#clean[@]}
[ "$n" -eq 0 ] && { log "no-op: no parseable entries"; exit 0; }

# ── Keep newest MEM_MAX_ENTRIES ──
start=0
[ "$n" -gt "$MEM_MAX_ENTRIES" ] && start=$(( n - MEM_MAX_ENTRIES ))
kept=( "${clean[@]:$start}" )

joined() {
  local out="" i
  for i in "${!kept[@]}"; do
    [ "$i" -gt 0 ] && out+="$DELIM"
    out+="${kept[$i]}"
  done
  printf '%s' "$out"
}
size() { joined | wc -c | tr -d ' '; }

# ── Trim oldest kept until byte size <= cap (never below 1 entry) ──
while [ "${#kept[@]}" -gt 1 ] && [ "$(size)" -gt "$MEM_MAX_CHARS" ]; do
  kept=( "${kept[@]:1}" )
done

# ── Fail-soft: a single remaining entry alone over cap — refuse to split/corrupt ──
if [ "$(size)" -gt "$MEM_MAX_CHARS" ]; then
  log "fail-soft: newest entry alone > ${MEM_MAX_CHARS} bytes — store preserved unchanged"
  exit 0
fi

new_content="$(joined)"

# ── Idempotency: nothing to change ──
if [ "$new_content" = "$(cat "$MEM_FILE")" ]; then
  log "no-op: already bounded (${#kept[@]} entries, $(size) bytes)"
  exit 0
fi

# ── Backup, then atomic VALIDATED replace ──
ts=$(date +%s)
cp "$MEM_FILE" "$MEM_FILE.bak.consolidate.$ts" 2>/dev/null || { log "fail-soft: backup failed — store preserved"; exit 0; }
tmp="$(mktemp "$MEM_DIR/.mem_consolidate.XXXXXX")" || { log "fail-soft: mktemp failed — store preserved"; exit 0; }
printf '%s' "$new_content" > "$tmp" || { rm -f "$tmp"; log "fail-soft: temp write failed — store preserved"; exit 0; }
d=$(grep -c '^§$' "$tmp" 2>/dev/null); tmp_count=$(( d + 1 ))
if [ ! -s "$tmp" ] || [ "$tmp_count" -ne "${#kept[@]}" ]; then
  rm -f "$tmp"; log "fail-soft: validation failed (parsed $tmp_count != ${#kept[@]}) — store preserved"; exit 0
fi
mv -f "$tmp" "$MEM_FILE" || { rm -f "$tmp"; log "fail-soft: atomic replace failed — store preserved"; exit 0; }
log "consolidated: $n -> ${#kept[@]} entries, $(size) bytes (cap ${MEM_MAX_ENTRIES}/${MEM_MAX_CHARS})"

# ── Bound the backups too (keep newest MEM_BACKUP_KEEP) ──
# shellcheck disable=SC2012
ls -1t "$MEM_FILE".bak.consolidate.* 2>/dev/null | tail -n +"$(( MEM_BACKUP_KEEP + 1 ))" | xargs -r rm -f 2>/dev/null || true
exit 0
