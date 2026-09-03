#!/bin/bash
# Reads back one live test: what the relay handed the agent, what the agent ran,
# and whether it actually published.
#
# Two independent sources, because neither alone answers the question:
#   journal   — buzz-acp's dispatch decisions (needs RUST_LOG=buzz_acp=debug)
#   rollout   — Codex's own session record: every tool call and the final answer
# A turn that computes an answer and never calls `buzz messages send` returns
# outcome=ok and looks identical to success from the journal side alone.
set -uo pipefail
export LC_ALL=C

AGENT=${1:-augustus}
SINCE=${2:--15 min}

: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"
export XDG_RUNTIME_DIR

pid=$(systemctl --user show "buzz-agent@$AGENT" -p MainPID --value)
codex_home=$(awk -v k='CODEX_HOME=' 'BEGIN{RS="\0"} index($0,k)==1 {print substr($0,length(k)+1)}' \
  "/proc/$pid/environ" 2>/dev/null)

printf '=== unit ===\n'
printf 'state=%s  mainpid=%s  since=%s\n' \
  "$(systemctl --user is-active "buzz-agent@$AGENT")" "$pid" "$SINCE"

printf '\n=== buzz-acp journal ===\n'
journalctl --user -u "buzz-agent@$AGENT" --since "$SINCE" --no-pager -o cat 2>/dev/null \
  | grep -viE 'presence|typing|token_count' \
  | tail -60

if [ -z "$codex_home" ]; then
  printf '\n(no CODEX_HOME — %s is not on the Codex harness, so there is no rollout)\n' "$AGENT"
  exit 0
fi

printf '\n=== codex rollouts started since "%s" ===\n' "$SINCE"
mapfile -t rollouts < <(find "$codex_home/sessions" -type f -name '*.jsonl' \
  -newermt "$SINCE" -printf '%T@ %p\n' 2>/dev/null | sort -n | cut -d' ' -f2-)

if [ "${#rollouts[@]}" -eq 0 ]; then
  printf 'none — the agent was never prompted in this window.\n'
  printf '\nVERDICT: NO TURN. Either the mention never bound a p-tag, the rules gate\n'
  printf 'rejected it, or the unit never received it. Check the journal above.\n'
  exit 0
fi

for f in "${rollouts[@]}"; do
  printf '\n--- %s ---\n' "${f##*/}"
  python3 - "$f" <<'PY'
import json, sys

# The publish check searches the WHOLE tool input, never a regex over cmd:"..."
# — the model routinely builds its commands in a JS array or a shell loop, and a
# pattern that only sees literal cmd: strings misses those. A missed publish
# reads as "the agent stayed silent", which is the one wrong answer this script
# must never give.
PUBLISH = "buzz messages send"

# A rollout is per *session*, and a session serves many turns — so counts must be
# segmented per turn or two clean one-reply turns aggregate into a false
# "duplicate replies". A turn opens at its user_message.
turns = []


def publishes(body):
    """Occurrences that actually send. `send --help` reads the usage text and is
    the one shape that recurs often enough to matter — an agent orienting itself
    tripped the counter into reporting a duplicate reply on a turn that replied
    once."""
    count = start = 0
    while (i := body.find(PUBLISH, start)) != -1:
        start = i + len(PUBLISH)
        if not body[start:start + 12].lstrip().startswith("--help"):
            count += 1
    return count


def compact(text, width):
    return " ".join(text.split())[:width]


for line in open(sys.argv[1]):
    try:
        payload = json.loads(line).get("payload") or {}
    except json.JSONDecodeError:
        continue
    if not isinstance(payload, dict):
        continue
    kind = payload.get("type")
    if kind == "user_message":
        turns.append({"tools": [], "published": 0, "final": None})
    elif not turns:
        continue
    elif kind == "custom_tool_call":
        body = payload.get("input", "")
        hits = publishes(body)
        turns[-1]["published"] += hits
        turns[-1]["tools"].append((body, hits))
    elif kind == "agent_message" and payload.get("phase") == "final_answer":
        turns[-1]["final"] = payload.get("message", "")

for n, turn in enumerate(turns, 1):
    print(f"  --- turn {n} of {len(turns)} ---")
    for i, (body, hits) in enumerate(turn["tools"], 1):
        marker = f"  <-- PUBLISH x{hits}" if hits else ""
        print(f"    tool[{i}]: {compact(body, 140)}{marker}")
    if turn["final"]:
        print(f"    answered  : {compact(turn['final'], 300)}")
    sent = turn["published"]
    print(f"    tool calls: {len(turn['tools'])}   publishes: {sent}")
    if sent == 0:
        print("    VERDICT: COMPUTED BUT DID NOT PUBLISH — the asker saw silence.")
    elif sent == 1:
        print("    VERDICT: PUBLISHED EXACTLY ONCE.")
    else:
        print(f"    VERDICT: PUBLISHED {sent} TIMES IN ONE TURN — duplicate replies.")
PY
done
