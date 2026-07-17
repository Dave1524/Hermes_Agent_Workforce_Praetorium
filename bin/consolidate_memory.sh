#!/usr/bin/env bash
# NUC-21 working memory: nightly, mechanical consolidation/prune of every
# Hermes-native episodic memory store (MEMORY.md) under every agent profile.
# NO LLM, NO network.
#
# On-disk contract (hermes tools/memory_tool.py MemoryStore): entries are
# separated by a line that is exactly § (U+00A7, bytes C2 A7); joined by \n§\n;
# there is NO trailing newline; each entry is stored stripped.
#
# Policy: exact-duplicate dedup (drop byte-identical entries, keep the newest)
# then a FIFO cap (keep the newest MEM_MAX_ENTRIES within MEM_MAX_CHARS bytes).
# NOT summarization — that would need an LLM, which this script deliberately avoids.
# Guarantees, PER PROFILE: bounded (<= caps), idempotent (a 2nd run is
# byte-identical), and fail-soft — on ANY problem that profile's store is left
# byte-for-byte untouched and the script moves on to the next profile. Never
# empties or corrupts a store. The script itself always exits 0 (a systemd
# oneshot must never surface as failed because one profile had a bad day).
set -uo pipefail   # deliberately NOT -e: every exit is controlled, for fail-soft

PROFILES_ROOT="${PROFILES_ROOT:-$HOME/.hermes/profiles}"
MEM_MAX_ENTRIES="${MEM_MAX_ENTRIES:-12}"
MEM_MAX_CHARS="${MEM_MAX_CHARS:-7000}"
MEM_BACKUP_KEEP="${MEM_BACKUP_KEEP:-5}"
LOG_DIR="${LOG_DIR:-$HOME/agent-workforce/logs}"
DELIM=$'\n§\n'   # literal newline, U+00A7, newline — MUST match memory_tool.py

mkdir -p "$LOG_DIR" 2>/dev/null || true
log() { echo "$(date -Is) consolidate_memory: [${CURRENT_PROFILE:-?}] $*" >>"$LOG_DIR/consolidate_memory.log" 2>/dev/null || true; }

# ── Strip a string (match MemoryStore .strip()) ──
strip() { local s="$1"; s="${s#"${s%%[![:space:]]*}"}"; s="${s%"${s##*[![:space:]]}"}"; printf '%s' "$s"; }

# ── Consolidate one profile's MEMORY.md. Every early-out is a `return`, never
#    an `exit`, so the caller always moves on to the next profile. The
#    lock+parse+rewrite body runs in a subshell so the lock fd is released on
#    every exit path without needing an explicit close on each branch. ──
consolidate_profile() {
  local mem_dir="$1" mem_file="$1/MEMORY.md" mem_lock="$1/MEMORY.md.lock"

  [ -f "$mem_file" ] || { log "no-op: store absent ($mem_file)"; return 0; }
  if [ ! -s "$mem_file" ] || ! grep -q '[^[:space:]]' "$mem_file" 2>/dev/null; then
    log "no-op: store empty"; return 0
  fi

  # ── Serialize against live memory-tool writes via the SAME lock file it uses ──
  (
    exec 9>"$mem_lock" 2>/dev/null || { log "no-op: cannot open lock"; exit 0; }
    flock -w 30 9 || { log "no-op: lock busy — skip this cycle"; exit 0; }

    # ── Parse entries: a boundary is a line that is exactly § ──
    local entries=() cur="" have=0 line
    while IFS= read -r line || [ -n "$line" ]; do
      if [ "$line" = "§" ]; then
        entries+=("$cur"); cur=""; have=0
      elif [ "$have" -eq 0 ]; then
        cur="$line"; have=1
      else
        cur="$cur"$'\n'"$line"
      fi
    done < "$mem_file"
    entries+=("$cur")

    # ── Drop empties after stripping ──
    local clean=() e s
    for e in "${entries[@]}"; do
      s="$(strip "$e")"
      [ -n "$s" ] && clean+=("$s")
    done
    local n=${#clean[@]}
    [ "$n" -eq 0 ] && { log "no-op: no parseable entries"; exit 0; }

    # ── Exact-duplicate dedup (mechanical, no-LLM/no-network): drop byte-identical
    #    stripped entries, keeping the NEWEST occurrence. Runs BEFORE the FIFO cap
    #    so duplicates don't consume the entry budget. Preserves chronological order. ──
    local -A seen=()
    local dedup=() i
    for (( i = n - 1; i >= 0; i-- )); do
      e="${clean[$i]}"
      [ -n "${seen[$e]+x}" ] && continue   # already kept a newer identical entry
      seen["$e"]=1
      dedup+=("$e")
    done
    clean=()   # rebuild oldest→newest
    for (( i = ${#dedup[@]} - 1; i >= 0; i-- )); do clean+=("${dedup[$i]}"); done
    [ "$n" -ne "${#clean[@]}" ] && log "dedup: $n -> ${#clean[@]} entries (exact duplicates dropped)"
    n=${#clean[@]}

    # ── Keep newest MEM_MAX_ENTRIES ──
    local start=0
    [ "$n" -gt "$MEM_MAX_ENTRIES" ] && start=$(( n - MEM_MAX_ENTRIES ))
    local kept=( "${clean[@]:$start}" )

    joined() {
      local out="" j
      for j in "${!kept[@]}"; do
        [ "$j" -gt 0 ] && out+="$DELIM"
        out+="${kept[$j]}"
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

    local new_content; new_content="$(joined)"

    # ── Idempotency: nothing to change ──
    if [ "$new_content" = "$(cat "$mem_file")" ]; then
      log "no-op: already bounded (${#kept[@]} entries, $(size) bytes)"
      exit 0
    fi

    # ── Backup, then atomic VALIDATED replace ──
    local ts tmp d tmp_count
    ts=$(date +%s)
    cp "$mem_file" "$mem_file.bak.consolidate.$ts" 2>/dev/null || { log "fail-soft: backup failed — store preserved"; exit 0; }
    tmp="$(mktemp "$mem_dir/.mem_consolidate.XXXXXX")" || { log "fail-soft: mktemp failed — store preserved"; exit 0; }
    printf '%s' "$new_content" > "$tmp" || { rm -f "$tmp"; log "fail-soft: temp write failed — store preserved"; exit 0; }
    d=$(grep -c '^§$' "$tmp" 2>/dev/null); tmp_count=$(( d + 1 ))
    if [ ! -s "$tmp" ] || [ "$tmp_count" -ne "${#kept[@]}" ]; then
      rm -f "$tmp"; log "fail-soft: validation failed (parsed $tmp_count != ${#kept[@]}) — store preserved"; exit 0
    fi
    mv -f "$tmp" "$mem_file" || { rm -f "$tmp"; log "fail-soft: atomic replace failed — store preserved"; exit 0; }
    log "consolidated: $n -> ${#kept[@]} entries, $(size) bytes (cap ${MEM_MAX_ENTRIES}/${MEM_MAX_CHARS})"

    # ── Bound the backups too (keep newest MEM_BACKUP_KEEP) ──
    # shellcheck disable=SC2012
    ls -1t "$mem_file".bak.consolidate.* 2>/dev/null | tail -n +"$(( MEM_BACKUP_KEEP + 1 ))" | xargs -r rm -f 2>/dev/null || true
  )
  return 0
}

# ── Discover profiles: explicit MEM_DIR overrides discovery (single-profile
#    test/back-compat mode); otherwise every */memories under PROFILES_ROOT,
#    so a newly added profile is picked up with no script or unit change. ──
profile_dirs=()
if [ -n "${MEM_DIR:-}" ]; then
  profile_dirs=("$MEM_DIR")
else
  for d in "$PROFILES_ROOT"/*/memories; do
    [ -d "$d" ] && profile_dirs+=("$d")
  done
fi

if [ "${#profile_dirs[@]}" -eq 0 ]; then
  CURRENT_PROFILE="-"
  log "no-op: no profile memory directories found under $PROFILES_ROOT"
  exit 0
fi

for dir in "${profile_dirs[@]}"; do
  CURRENT_PROFILE="$(basename "$(dirname "$dir")")"
  consolidate_profile "$dir"
done

exit 0
