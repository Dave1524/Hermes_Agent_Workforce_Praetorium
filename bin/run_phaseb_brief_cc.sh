#!/usr/bin/env bash
# Phase-B brief writer — one brief per invocation, id in $1 (systemd passes %i).
#
# Deliberate exception to the "scheduled jobs exec in the deployed tree" norm: the artifact is a
# repo document, so this script runs FROM the deployed copy but operates ON the git source tree
# at ~/dev/agent-workforce. The deployed copy has no .git and could never commit a brief.
#
# Queue and per-brief context: design/phaseb-brief-queue.toml. Method: profiles/phaseb_brief_cc_task.md.
set -euo pipefail

BRIEF_ID="${1:-${PHASEB_BRIEF_ID:-}}"
[ -n "$BRIEF_ID" ] || { echo "phaseb-brief: no brief id given (arg 1 or PHASEB_BRIEF_ID)" >&2; exit 1; }

CLAUDE_BIN="${CLAUDE_BIN:-/home/linuxbrew/.linuxbrew/bin/claude}"
REPO_SRC="${PHASEB_REPO:-$HOME/dev/agent-workforce}"
TASK_FILE="${PHASEB_TASK:-$HOME/agent-workforce/profiles/phaseb_brief_cc_task.md}"
QUEUE="$REPO_SRC/design/phaseb-brief-queue.toml"

[ -r "$TASK_FILE" ] || { echo "phaseb-brief: task file not readable: $TASK_FILE" >&2; exit 1; }
[ -d "$REPO_SRC/.git" ] || { echo "phaseb-brief: not a git source tree: $REPO_SRC" >&2; exit 1; }
[ -r "$QUEUE" ] || { echo "phaseb-brief: queue not readable: $QUEUE" >&2; exit 1; }

slug="$(python3 - "$QUEUE" "$BRIEF_ID" <<'PY'
import sys, tomllib
queue, want = sys.argv[1], int(sys.argv[2])
for b in tomllib.load(open(queue, 'rb'))['brief']:
    if b['id'] == want:
        print(b['slug']); break
else:
    sys.exit(f"no [[brief]] with id {want}")
PY
)"
[ -n "$slug" ] || { echo "phaseb-brief: no slug for id $BRIEF_ID" >&2; exit 1; }

out=".claude/briefs/${slug}.md"
cd "$REPO_SRC"

# STEP 0 idempotency, mirroring the other scheduled jobs: a re-fire must never clobber a brief
# someone has already started reviewing.
if [ -e "$out" ]; then
  echo "phaseb-brief: skip — $out already exists"
  exit 0
fi

echo "phaseb-brief: writing brief $BRIEF_ID ($slug) -> $out"
PHASEB_BRIEF_ID="$BRIEF_ID" "$CLAUDE_BIN" -p "$(cat "$TASK_FILE")" \
  --model claude-opus-5 \
  --permission-mode bypassPermissions \
  --strict-mcp-config \
  --mcp-config '{"mcpServers":{}}' \
  --allowedTools "Bash,Read,Write,Edit,Glob,Grep"

if [ ! -e "$out" ]; then
  echo "phaseb-brief: FAILED — the run produced no $out" >&2
  exit 1
fi

# auto-sync fires every 15 min and commits any dirty tree, so it may have swept the file already;
# that is success, not an error. It does NOT push a clean tree (bin/auto-sync:25), which is why
# the push below is unconditional rather than gated on having made a commit here.
git add -- "$out"
if git diff --cached --quiet; then
  echo "phaseb-brief: already committed (auto-sync got there first)"
else
  git commit -q -m "docs(briefs): Phase-B brief ${BRIEF_ID} — ${slug}"
fi
git push -q origin main
echo "phaseb-brief: done — $out"
