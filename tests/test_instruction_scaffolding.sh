#!/usr/bin/env bash
# The instruction files are the only thing standing between an agent and a wrong action, and
# until this suite they were the least-checked artifacts on the box: nothing joined them to
# each other, and nothing joined them to the machine they describe.
#
# WHY A JOIN AND NOT A REVIEW. Eight instruction-file defects were measured 2026-09-04 and every
# one of them had survived for weeks. They did not survive because they were hard to see — most
# are a single wrong sentence — but because no artifact anywhere compared these files to
# anything, so a wrong one and a right one are indistinguishable until an agent acts on it. Two
# of the eight are mechanisable cheaply and are the two this suite asserts. The other six are
# prose, and no cheap check covers them; see WHAT THIS DOES NOT ASSERT below rather than reading
# a green run as coverage it does not have.
#
# THE TWO INVARIANTS.
#
#   1. Coverage, both directions. Claude Code reads CLAUDE.md and Codex reads AGENTS.md; a rule
#      written to one is invisible to the other. So a project with a CLAUDE.md and no AGENTS.md
#      runs Codex with NO project instructions at all — which is exactly what ~/dev/energy-ledger
#      did until 2026-09-05, silently, while the box convention claimed every project had both.
#      The mirror direction (an AGENTS.md with no sibling) is asserted too: it is the shape a
#      renamed or half-deleted project leaves behind.
#
#   2. The thin-pointer invariant. Every AGENTS.md on this box is a pointer at its sibling
#      CLAUDE.md by design (see ~/.codex/AGENTS.md). They were full forks until 2026-08-03 and
#      drift had eaten them: AI_Trading_Bot/AGENTS.md was a copy of its CLAUDE.md that had lost
#      BOTH HARD safety sections plus the verification gate while still calling Polymarket an
#      active track. A pointer is checked two ways — it must name its sibling, and it must be
#      materially smaller than it.
#
# WHERE POINTER_MAX_PCT COMES FROM. Measured, not guessed. On 2026-09-05 the four pointers on
# this box sit at 12% (AI_Trading_Bot, 2,692 B against 20,832 B), 20% (agent-workforce, 2,743 B
# against 13,625 B), 59% (energy-ledger, 1,810 B against 3,066 B) and 62%
# (Obsidian_AI_Operating_System, 4,963 B against 7,925 B). 62% is the binding value and the
# ceiling is set above it with headroom, not at the comfortable end of the range — a threshold
# tuned to the two small files would go red on the other two for being themselves.
#
# The spread is not sloppiness, it is structural: the ratio saturates as a CLAUDE.md gets small.
# energy-ledger's is 3 KB, so a pointer that does its job at all is a large fraction of it. The
# first draft of that file summarised its sibling's sections instead of naming them and landed at
# 74%, one point under this ceiling — which is the tell that summarising IS the fork, not merely
# that the file was long. Rewritten to name the sections and defer, it is 59%.
#
# AND WHAT THE RATIO CANNOT CATCH, stated plainly because the number invites over-reading: it
# catches a pointer that has grown back into a COPY (~100%), which is what AI_Trading_Bot was.
# It would NOT have caught the other 2026-08-03 fork — agent-workforce/AGENTS.md was 1.4 KB
# against an 11 KB CLAUDE.md, 13%, comfortably "thin" while restating project rules in its own
# words and drifting three weeks stale. Size is evidence of a copy, never evidence of agreement.
#
# WHAT THIS DOES NOT ASSERT. Freshness of prose; whether a document count in prose is still
# true; whether a mechanism a file describes at length is actually configured. Those are the
# other six 2026-09-04 rows — a four-agent fleet that is five, a qmd document count that has
# been four different numbers, an MCP surface list, a Codex permission profile the doc describes
# as verified and which no config enables. Each is a claim about the live machine, and checking
# it means reproducing the machine. Also out of reach by choice: the box-root pair ~/CLAUDE.md
# and ~/.codex/AGENTS.md. Neither is in any repo, and they are not siblings — ~/AGENTS.md is a
# symlink into ~/.codex/ precisely because a plain ~/AGENTS.md loads only when the workspace IS
# /home/dave. They need their own check, not this one bent to fit.
#
# FIXTURES FIRST, LIVE TREE SECOND. Group 3's verdict on the real ~/dev is worth nothing unless
# the checker is known to detect the failures it looks for, and a suite whose only subject is a
# currently-healthy tree is a check that cannot fail — the shape this repo has been bitten by
# before (memory `readiness-report-phantom-blockers`). Groups 1 and 2 prove each failure mode is
# caught on synthetic input and that a healthy tree is NOT flagged.
set -uo pipefail

POINTER_MAX_PCT=75              # measured max is 62% — see header
DEV_ROOT="${DEV_ROOT:-$HOME/dev}"

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# --- the checker, one definition, used on fixtures and on the live tree -------------------
# Each lister prints one offending project name per line, so a failure names its subject
# instead of only its count. A directory carrying NEITHER file is silent by design: this
# asserts that the pair is complete, not that every directory under DEV_ROOT is a project.
unpaired_claude() {
  local d
  for d in "$1"/*/; do
    [ -d "$d" ] || continue
    [ -f "$d/CLAUDE.md" ] || continue
    [ -f "$d/AGENTS.md" ] || basename "$d"
  done
}

orphan_agents() {
  local d
  for d in "$1"/*/; do
    [ -d "$d" ] || continue
    [ -f "$d/AGENTS.md" ] || continue
    [ -f "$d/CLAUDE.md" ] || basename "$d"
  done
}

pointer_pct() {
  local a c
  a=$(wc -c < "$1/AGENTS.md")
  c=$(wc -c < "$1/CLAUDE.md")
  [ "$c" -gt 0 ] && echo $(( a * 100 / c )) || echo 100
}

# Read straight from the file: no pipe, so no early-exiting reader to SIGPIPE.
names_sibling() { grep -qF 'CLAUDE.md' "$1/AGENTS.md"; }

# A pointer that has grown back into a copy, or that never points at all.
forked_pointers() {
  local d
  for d in "$1"/*/; do
    [ -d "$d" ] || continue
    [ -f "$d/AGENTS.md" ] && [ -f "$d/CLAUDE.md" ] || continue
    if [ "$(pointer_pct "$d")" -gt "$POINTER_MAX_PCT" ] || ! names_sibling "$d"; then
      basename "$d"
    fi
  done
}

count_lines() { grep -c . || true; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# A CLAUDE.md of a given byte size, so the ratio fixtures are exact rather than approximate.
make_pair() {
  local dir=$1 claude_bytes=$2 agents_bytes=$3
  mkdir -p "$dir"
  python3 - "$dir" "$claude_bytes" "$agents_bytes" <<'PY'
import sys
d, cb, ab = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
head = "# AGENTS.md\n\nRead CLAUDE.md in this repo root first.\n"
open(f"{d}/CLAUDE.md", "w").write("# CLAUDE.md\n" + "c" * (cb - len("# CLAUDE.md\n")))
open(f"{d}/AGENTS.md", "w").write(head + "a" * (ab - len(head)))
PY
}

echo "--- 0. canaries ---"
# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. the checker detects every failure mode on fixtures ---"
gap="$TMP/gap"
make_pair "$gap/paired" 4000 800
mkdir -p "$gap/claude-only" && echo '# CLAUDE.md' > "$gap/claude-only/CLAUDE.md"
mkdir -p "$gap/agents-only" && echo '# AGENTS.md — see CLAUDE.md' > "$gap/agents-only/AGENTS.md"
mkdir -p "$gap/neither" && echo 'not a project' > "$gap/neither/README.md"

assert 'a CLAUDE.md with no sibling AGENTS.md is named' \
  "[ \"\$(unpaired_claude '$gap')\" = 'claude-only' ]"
assert 'an AGENTS.md with no sibling CLAUDE.md is named' \
  "[ \"\$(orphan_agents '$gap')\" = 'agents-only' ]"
assert 'a directory carrying neither is not an offender in either direction' \
  "[ \"\$(unpaired_claude '$gap' | count_lines)\" -eq 1 ] && [ \"\$(orphan_agents '$gap' | count_lines)\" -eq 1 ]"

# The fork this would have caught: a pointer that is a copy of its sibling.
fork="$TMP/fork"
mkdir -p "$fork/copied"
printf '# CLAUDE.md\n%s\n' "$(printf 'rule %.0s' $(seq 1 400))" > "$fork/copied/CLAUDE.md"
cp "$fork/copied/CLAUDE.md" "$fork/copied/AGENTS.md"
assert 'an AGENTS.md that is a byte copy of its CLAUDE.md is flagged' \
  "[ \"\$(forked_pointers '$fork')\" = 'copied' ]"
assert 'and it is flagged on size, not on the missing pointer text' \
  "[ \"\$(pointer_pct '$fork/copied')\" -gt $POINTER_MAX_PCT ]"

# The other half of the invariant: thin, but pointing nowhere.
silent="$TMP/silent"
make_pair "$silent/mute" 4000 400
python3 -c "open('$silent/mute/AGENTS.md','w').write('# AGENTS.md\n\nCodex mechanics only.\n')"
assert 'a thin AGENTS.md that never names its sibling is flagged' \
  "[ \"\$(forked_pointers '$silent')\" = 'mute' ]"
assert 'even though its size is well under the ceiling' \
  "[ \"\$(pointer_pct '$silent/mute')\" -lt $POINTER_MAX_PCT ]"

# The boundary, so POINTER_MAX_PCT is a limit rather than an approximation.
edge="$TMP/edge"
make_pair "$edge/at-ceiling" 1000 750     # exactly 75%
make_pair "$edge/over-ceiling" 1000 760   # 76%
assert "a pointer at exactly ${POINTER_MAX_PCT}% is not flagged, one point over is" \
  "[ \"\$(forked_pointers '$edge')\" = 'over-ceiling' ]"

echo "--- 2. a healthy tree is NOT flagged (the check can pass) ---"
ok="$TMP/ok"
make_pair "$ok/alpha" 13625 2743          # the agent-workforce shape, 20%
make_pair "$ok/beta" 7925 4963            # the vault shape, 62% — the binding measured value
assert 'a healthy tree has no unpaired CLAUDE.md' "[ -z \"\$(unpaired_claude '$ok')\" ]"
assert 'no orphan AGENTS.md'                      "[ -z \"\$(orphan_agents '$ok')\" ]"
assert 'and no forked pointer'                    "[ -z \"\$(forked_pointers '$ok')\" ]"

echo "--- 3. the live ~/dev project tree ---"
if box_only_with 'the box'"'"'s ~/dev project tree, which no checkout carries' "$DEV_ROOT"; then
  for d in "$DEV_ROOT"/*/; do
    [ -d "$d" ] || continue
    [ -f "$d/AGENTS.md" ] && [ -f "$d/CLAUDE.md" ] || continue
    printf '  info: %-32s pointer %s%% of its CLAUDE.md\n' "$(basename "$d")" "$(pointer_pct "$d")"
  done

  missing=$(unpaired_claude "$DEV_ROOT")
  orphans=$(orphan_agents "$DEV_ROOT")
  forks=$(forked_pointers "$DEV_ROOT")

  assert "every CLAUDE.md under $DEV_ROOT has a sibling AGENTS.md (${missing:-none} missing it)" \
    "[ -z '$missing' ]"
  assert "every AGENTS.md has a sibling CLAUDE.md (${orphans:-none} without one)" \
    "[ -z '$orphans' ]"
  assert "every AGENTS.md names its sibling and stays under ${POINTER_MAX_PCT}% of it (${forks:-none} do not)" \
    "[ -z '$forks' ]"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
