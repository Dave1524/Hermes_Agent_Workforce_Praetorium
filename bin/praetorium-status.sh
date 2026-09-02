#!/usr/bin/env bash
# NUC-18: one command to see the health of everything on Praetorium.
set -uo pipefail

echo "══ Praetorium status $(date -Is) ══"

# ── W3 (2026-09-02): the unit list comes from config/fleet-units.tsv, not from a literal
#    here. This block used to carry 12 hand-picked units; eight standing units existed that
#    it — and the other five copies of the same list — never named. Resolved relative to the
#    script so it works from the repo and from ~/agent-workforce/ alike; design/ is NOT
#    deployed, so reading the manifests directly would empty this silently in the runtime.
FLEET_UNITS="$(dirname "$0")/../config/fleet-units.tsv"
# Fail LOUD, not empty. A missing list must not render as a clean short report — that is the
# whitelist defect in its worst form, where the check reports nothing wrong because it
# checked nothing.
if [ ! -r "$FLEET_UNITS" ]; then
  echo "  FATAL: cannot read $FLEET_UNITS — unit coverage unknown, not 'fine'"
  exit 1
fi
fleet_units() {  # $1 = scope
  awk -F'\t' -v want="$1" '!/^#/ && NF>=3 && $2==want && $3=="standing" {print $1}' "$FLEET_UNITS"
}

echo; echo "── Services"
# The two MCP daemons are not workflows and are declared in no manifest, so they stay named
# here on purpose; everything below them is derived.
for svc in qmd-mcp.service brave-mcp.service; do
  state=$(systemctl is-active "$svc" 2>/dev/null || true)
  enabled=$(systemctl is-enabled "$svc" 2>/dev/null || true)
  printf "  %-32s active=%-10s enabled=%s\n" "$svc" "$state" "$enabled"
done
while read -r u; do
  [ -n "$u" ] || continue
  state=$(systemctl is-active "$u.timer" 2>/dev/null || true)
  enabled=$(systemctl is-enabled "$u.timer" 2>/dev/null || true)
  printf "  %-32s active=%-10s enabled=%s\n" "$u.timer" "$state" "$enabled"
done < <(fleet_units system)

echo; echo "── Timers (next runs)"
mapfile -t _sys < <(fleet_units system)
systemctl list-timers "${_sys[@]/%/.timer}" --no-pager 2>/dev/null | head -30

# User-scope standing units are invisible to the system manager above. Reported separately
# rather than merged, because "not-found" from the wrong manager is indistinguishable from
# a unit that is genuinely gone.
echo; echo "── User timers (scope=user, next runs)"
mapfile -t _usr < <(fleet_units user)
if [ ${#_usr[@]} -eq 0 ]; then
  echo "  none declared"
else
  XDG_RUNTIME_DIR="/run/user/$(id -u)" \
    systemctl --user list-timers "${_usr[@]/%/.timer}" --no-pager 2>/dev/null | head -10 \
    || echo "  UNKNOWN — could not reach the user manager"
fi
# ── User services: fleet units run in the --user manager, so their state is invisible
#    to system-scope systemctl. Ask the user manager what is WRONG rather than asking a
#    hand-maintained list whether it is fine — a whitelist cannot report a unit nobody
#    thought to add, which is how an 8-day failure went unnamed twice a day.
#    Fail-soft (|| true); set -uo pipefail contract preserved (no -e).
echo; echo "── User services (failed units)"
rt="/run/user/$(id -u)"
# `|| true` on the assignment alone would print "none" when the USER BUS is unreachable,
# which is the same false green this block replaced. Keep the rc.
user_rc=0
user_failed=$(XDG_RUNTIME_DIR="$rt" systemctl --user --failed --no-legend --no-pager 2>/dev/null) || user_rc=$?
if [ "$user_rc" -ne 0 ]; then
  echo "  UNKNOWN — could not reach the user manager (rc=$user_rc); this is not 'nothing failed'"
elif [ -n "$user_failed" ]; then
  printf '%s\n' "$user_failed" | sed 's/^/  /'
else
  echo "  none"
fi
# The hermes-gateway and hermes-cron blocks that stood here were removed 2026-09-02 with
# the S3 retirement (open-decisions.md D7). Both would now report a retired surface on
# every run — `active=inactive enabled=disabled` forever, and a cron count against a host
# that no longer exists — and a status view that reports a retired surface every run
# trains its reader to skip it. The gateway unit is still on disk for one review cycle;
# if it is ever restarted it will appear above by failing, not by being whitelisted here.
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
echo; echo "── Working memory (all profiles, NUC-21)"
mem_profile_dirs=()
for d in "$HOME"/.hermes/profiles/*/memories; do
  [ -d "$d" ] && mem_profile_dirs+=("$d")
done
if [ "${#mem_profile_dirs[@]}" -eq 0 ]; then
  echo "  no profile memory directories found"
else
  for d in "${mem_profile_dirs[@]}"; do
    profile=$(basename "$(dirname "$d")")
    mem_file="$d/MEMORY.md"
    if [ -s "$mem_file" ]; then
      e=$(grep -c '^§$' "$mem_file" 2>/dev/null); entries=$(( e + 1 ))
      printf "  %-10s entries: %s   bytes: %s\n" "$profile" "$entries" "$(wc -c < "$mem_file" | tr -d ' ')"
    else
      printf "  %-10s store empty (no runs recorded yet)\n" "$profile"
    fi
  done
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
# ── NUC-26/45: surface the pending approval backlog (surfacing ONLY — promote/reject is a
#    Mac-side human gate via agent_inbox.py against the canonical vault; the box never decides).
#    Pending count comes from agent_inbox_notion_sync.py --count, which knows Notion Status
#    per file — a raw *.md count on disk overstates the backlog by however many files are
#    already decided but not yet cleared by the Mac-side promote pass (NUC-45, 2026-08-10:
#    40 raw files vs 25 genuinely pending on 2026-08-10). Raw disk count is still shown, as
#    context, never as "pending".
echo; echo "── Agent inbox backlog (pending proposals, NUC-26/45)"
inbox_dir="$HOME/agent-worktrees/inbox/_inbox/agents"
if [ -d "$inbox_dir" ]; then
  disk_count=$(find "$inbox_dir" -maxdepth 1 -type f -name '*.md' 2>/dev/null | wc -l | tr -d ' ')
  pend="" oldest_date=""
  count_out=$(timeout 30 python3 "$HOME/agent-workforce/bin/agent_inbox_notion_sync.py" --count 2>/dev/null) || count_out=""
  pend=$(printf '%s\n' "$count_out" | sed -n 's/^PENDING_COUNT=//p')
  oldest_date=$(printf '%s\n' "$count_out" | sed -n 's/^OLDEST_PENDING_DATE=//p')
  if [ -n "$pend" ]; then
    if [ "$pend" -gt 0 ] && [ -n "$oldest_date" ] && [ "$oldest_date" != none ]; then
      now_secs=$(date +%s)
      oldest_secs=$(date -d "$oldest_date" +%s 2>/dev/null || echo "$now_secs")
      age_days=$(( (now_secs - oldest_secs) / 86400 ))
      printf "  pending  : %s awaiting Mac-side promote/reject (agent_inbox.py, Notion-verified)\n" "$pend"
      printf "  oldest   : %s (%sd old)\n" "$oldest_date" "$age_days"
    else
      echo "  pending  : 0 (inbox clear, Notion-verified)"
    fi
    if [ "$disk_count" -gt "${pend:-0}" ]; then
      printf "  on disk  : %s files (%s already decided in Notion, not yet cleared)\n" \
        "$disk_count" "$(( disk_count - pend ))"
    fi
  else
    echo "  pending  : UNKNOWN — agent_inbox_notion_sync.py --count unavailable (network/token)"
    printf "  on disk  : %s files (raw count — includes any already-decided, uncleared)\n" "$disk_count"
  fi
else
  echo "  inbox worktree not present ($inbox_dir)"
fi
# ── NUC-40 verified NUC-27 key-cap/budget coverage below already exists — no re-add. ──
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
echo; echo "── Overnight logs (NUC-36)"
ls -t "$HOME/logs/overnight"/pre-snapshot-*.log 2>/dev/null | head -1 | sed 's/^/  last pre-snapshot: /' \
  || echo "  last pre-snapshot: none"
ls -t "$HOME/logs/overnight"/morning-report-*.md 2>/dev/null | head -1 | sed 's/^/  last morning report: /' \
  || echo "  last morning report: none"
echo; echo "── Log inspection: journalctl -u qmd-mcp -e | journalctl -u brave-mcp -e | journalctl -u agent-proposal -e | journalctl -u overnight-morning-report -e"
