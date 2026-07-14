#!/usr/bin/env bash
# NUC-18: one command to see the health of everything on Praetorium.
set -uo pipefail

echo "══ Praetorium status $(date -Is) ══"
echo; echo "── Services"
for svc in qmd-mcp.service brave-mcp.service qmd-refresh.timer agent-proposal.timer \
           memory-consolidation.timer scorecard.timer; do
  state=$(systemctl is-active "$svc" 2>/dev/null || true)
  enabled=$(systemctl is-enabled "$svc" 2>/dev/null || true)
  printf "  %-28s active=%-10s enabled=%s\n" "$svc" "$state" "$enabled"
done
echo; echo "── Timers (next runs)"
systemctl list-timers qmd-refresh.timer agent-proposal.timer memory-consolidation.timer \
  scorecard.timer --no-pager 2>/dev/null | head -7
echo; echo "── qmd index"
qmd status 2>/dev/null | head -8 || echo "  qmd index not built yet (finish_boxsafe_clone.sh)"
echo; echo "── qmd MCP daemon (agent transport, NUC-16)"
qmd_daemon="unreachable"
if command -v curl >/dev/null 2>&1 && curl -sf --max-time 2 http://127.0.0.1:8765/health >/dev/null 2>&1; then
  qmd_daemon="reachable"
fi
qmd_profile="unknown"
prof="$HOME/.hermes/profiles/claudius/config.yaml"
if [ -f "$prof" ]; then
  qmd_block=$(awk '/^  qmd:/{f=1;next} f&&/^  [A-Za-z]/{f=0} f' "$prof")
  if printf '%s\n' "$qmd_block" | grep -qE '^[[:space:]]*url:'; then
    qmd_profile="daemon (http)"
  elif printf '%s\n' "$qmd_block" | grep -qE '^[[:space:]]*command:'; then
    qmd_profile="cold-spawn (stdio) — NUC-16 regression"
  fi
fi
printf "  endpoint : http://127.0.0.1:8765/mcp (%s)\n" "$qmd_daemon"
printf "  profile  : claudius qmd = %s\n" "$qmd_profile"
echo; echo "── Research MCP (Brave)"
brave_key="MISSING"
if grep -qE '^BRAVE_API_KEY=.+' "$HOME/.hermes/.env" 2>/dev/null || [ -n "${BRAVE_API_KEY:-}" ]; then
  brave_key="set"
fi
brave_server="npx-missing"
command -v npx >/dev/null 2>&1 && brave_server="resolvable"
brave_svc=$(systemctl is-active brave-mcp.service 2>/dev/null || true)
brave_ep="down"
if ss -ltn 2>/dev/null | grep -q ':8766'; then brave_ep="up"; fi
brave_last=$(tail -1 "$HOME/agent-workforce/logs/brave_mcp.log" 2>/dev/null || true)
printf "  key      : %s\n" "$brave_key"
printf "  server   : %s\n" "$brave_server"
printf "  service  : %s\n" "${brave_svc:-unknown}"
printf "  endpoint : %s (127.0.0.1:8766/mcp)\n" "$brave_ep"
[ -n "$brave_last" ] && printf "  last start: %s\n" "$brave_last"
echo; echo "── Fetch backend (browser, NUC-22)"
# Local headless Chromium via agent-browser (credential-free; no Browserbase key).
# Quota-free reachability — mirrors tools/browser_tool.py::_chromium_installed().
fetch_chromium="MISSING"
if [ -n "${AGENT_BROWSER_EXECUTABLE_PATH:-}" ] && [ -x "${AGENT_BROWSER_EXECUTABLE_PATH:-}" ]; then
  fetch_chromium="installed"
elif command -v google-chrome >/dev/null 2>&1 || command -v chromium >/dev/null 2>&1 \
    || command -v chromium-browser >/dev/null 2>&1 || command -v chrome >/dev/null 2>&1; then
  fetch_chromium="installed"
else
  shopt -s nullglob
  # Playwright cache (hermes _chromium_installed method 3) OR agent-browser's own
  # Chrome-for-testing dir (agent-browser 0.31.1 installs here; NUC-22).
  _pw=( "$HOME"/.cache/ms-playwright/chromium-* "$HOME"/.cache/ms-playwright/chromium_headless_shell-* \
        "$HOME"/.agent-browser/browsers/chrome-*/chrome "$HOME"/.agent-browser/browsers/chromium-*/chrome )
  shopt -u nullglob
  [ "${#_pw[@]}" -gt 0 ] && fetch_chromium="installed"
fi
fetch_runner="MISSING"
if command -v agent-browser >/dev/null 2>&1; then
  fetch_runner="agent-browser"
elif [ -x "$HOME/.hermes/hermes-agent/node_modules/.bin/agent-browser" ]; then
  fetch_runner="agent-browser (hermes-local)"   # what hermes actually resolves + uses
elif command -v npx >/dev/null 2>&1; then
  fetch_runner="npx-fallback"
fi
printf "  mode    : %s\n" "local-headless-chromium"
printf "  chromium: %s\n" "$fetch_chromium"
printf "  runner  : %s\n" "$fetch_runner"
echo; echo "── Working memory (claudius, NUC-21)"
ra_mem="$HOME/.hermes/profiles/claudius/memories/MEMORY.md"
if [ -s "$ra_mem" ]; then
  e=$(grep -c '^§$' "$ra_mem" 2>/dev/null); entries=$(( e + 1 ))
  printf "  entries: %s   bytes: %s\n" "$entries" "$(wc -c < "$ra_mem" | tr -d ' ')"
else
  echo "  store empty (no runs recorded yet)"
fi
echo; echo "── Vault clone"
if [ -d "$HOME/vault/.git" ]; then
  echo "  $(git -C "$HOME/vault" log -1 --format='last pull: %h %cd' --date=relative 2>/dev/null)"
else
  echo "  not cloned yet (deploy key gate)"
fi
echo; echo "── Last agent runs"
tail -3 "$HOME/agent-workforce/logs/agent_propose.log" 2>/dev/null || echo "  no runs yet"
echo; echo "── Cost log"
tail -3 "$HOME/agent-workforce/logs/cost.log" 2>/dev/null || echo "  no cost entries yet"
# ── NUC-26: surface the pending approval backlog (surfacing ONLY — promote/reject is a
#    Mac-side human gate via agent_inbox.py against the canonical vault; the box never decides).
#    Counts proposal files in _inbox/agents/ (excludes the _metrics/ digest dir) + oldest age.
echo; echo "── Agent inbox backlog (pending proposals, NUC-26)"
inbox_dir="$HOME/agent-worktrees/inbox/_inbox/agents"
if [ -d "$inbox_dir" ]; then
  pend=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  if [ "${pend:-0}" -gt 0 ]; then
    oldest_line=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' -printf '%T@ %p\n' 2>/dev/null \
                    | sort -n | head -1)
    oldest_epoch=${oldest_line%% *}          # first field: mtime epoch (secs.frac)
    oldest_secs=${oldest_epoch%.*}           # strip fractional part
    oldest_file=$(basename "${oldest_line#* }")
    now_secs=$(date +%s)
    age_days=$(( (now_secs - oldest_secs) / 86400 ))
    printf "  pending  : %s awaiting Mac-side promote/reject (agent_inbox.py)\n" "$pend"
    printf "  oldest   : %s (%sd old)\n" "$oldest_file" "$age_days"
  else
    echo "  pending  : 0 (inbox clear)"
  fi
else
  echo "  inbox worktree not present ($inbox_dir)"
fi
# ── NUC-27: shared OpenRouter budget (whole fleet shares ONE key + a ~$25 cap) ──
# Read-only GET of /key. Runs in a SUBSHELL so the key never leaks into this
# script's env and is never printed. Fail-soft: any error prints a soft note and
# never breaks the status run (this script is set -uo pipefail, NOT -e). Key is
# taken from env if present, else grepped from secrets.env (same convention this
# script already uses for the Brave key — no full source, no side effects).
echo; echo "── OpenRouter budget (NUC-27)"
(
  base="${LLM_BASE_URL:-https://openrouter.ai/api/v1}"
  secrets="$HOME/.config/agent-workforce/secrets.env"
  key="${OPENROUTER_API_KEY:-}"
  if [ -z "$key" ] && [ -f "$secrets" ]; then
    key=$(grep -E '^OPENROUTER_API_KEY=' "$secrets" | tail -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
  fi
  if [ -z "$key" ]; then echo "  key: MISSING — cannot check budget"; exit 0; fi
  resp=$(curl -sS --max-time 15 "$base/key" -H "Authorization: Bearer $key" 2>/dev/null) \
    || { echo "  budget: key endpoint unreachable (GET failed)"; exit 0; }
  printf '%s' "$resp" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)["data"]
except Exception:
    print("  budget: unparseable response"); sys.exit(0)
def m(x): return "$%.2f" % x if isinstance(x,(int,float)) else "n/a"
usage=d.get("usage"); limit=d.get("limit"); rem=d.get("limit_remaining")
lim = m(limit) if limit is not None else "none"
print("  usage: %s   limit: %s   remaining: %s" % (m(usage), lim, m(rem)))
if isinstance(rem,(int,float)) and rem < 2:
    print("  WARNING: OpenRouter budget nearly exhausted (%s left of shared ~$25 cap) -- fleet may stop completing; top up / raise the cap" % m(rem))'
) || true
echo; echo "── System"
uptime | sed 's/^/  /'
df -h / | tail -1 | awk '{print "  disk / : "$3" used of "$2" ("$5")"}'
free -h | awk 'NR==2{print "  memory : "$3" used of "$2}'
echo; echo "── Tailscale"
tailscale status 2>/dev/null | head -3 | sed 's/^/  /'
echo; echo "── Log inspection: journalctl -u qmd-mcp -e | journalctl -u brave-mcp -e | journalctl -u agent-proposal -e"
