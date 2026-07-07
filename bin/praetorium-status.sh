#!/usr/bin/env bash
# NUC-18: one command to see the health of everything on Praetorium.
set -uo pipefail

echo "══ Praetorium status $(date -Is) ══"
echo; echo "── Services"
for svc in qmd-mcp.service qmd-refresh.timer agent-proposal.timer; do
  state=$(systemctl is-active "$svc" 2>/dev/null || true)
  enabled=$(systemctl is-enabled "$svc" 2>/dev/null || true)
  printf "  %-28s active=%-10s enabled=%s\n" "$svc" "$state" "$enabled"
done
echo; echo "── Timers (next runs)"
systemctl list-timers qmd-refresh.timer agent-proposal.timer --no-pager 2>/dev/null | head -5
echo; echo "── qmd index"
qmd status 2>/dev/null | head -8 || echo "  qmd index not built yet (finish_boxsafe_clone.sh)"
echo; echo "── Research MCP (Brave)"
brave_key="MISSING"
if grep -qE '^BRAVE_API_KEY=.+' "$HOME/.hermes/.env" 2>/dev/null || [ -n "${BRAVE_API_KEY:-}" ]; then
  brave_key="set"
fi
brave_server="npx-missing"
command -v npx >/dev/null 2>&1 && brave_server="resolvable"
printf "  key    : %s\n" "$brave_key"
printf "  server : %s\n" "$brave_server"
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
echo; echo "── System"
uptime | sed 's/^/  /'
df -h / | tail -1 | awk '{print "  disk / : "$3" used of "$2" ("$5")"}'
free -h | awk 'NR==2{print "  memory : "$3" used of "$2}'
echo; echo "── Tailscale"
tailscale status 2>/dev/null | head -3 | sed 's/^/  /'
echo; echo "── Log inspection: journalctl -u qmd-mcp -e | journalctl -u agent-proposal -e"
