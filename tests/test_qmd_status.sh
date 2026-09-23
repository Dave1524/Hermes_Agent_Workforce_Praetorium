#!/usr/bin/env bash
# Test for bin/praetorium-status.sh's qmd MCP daemon section (NUC-16) — mocked
# system commands, no network, no live daemon. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/praetorium-status.sh"
# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0
assert() {
  local desc=$1 cond=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# ── Sandbox: scratch $HOME + stub PATH so the script never touches the real
# systemd units, qmd index, tailscale, or the live qmd daemon on :8765 ──
sandbox() {
  local home; home=$(mktemp -d)
  local stubs; stubs=$(mktemp -d)

  cat > "$stubs/systemctl" <<'EOF'
#!/usr/bin/env bash
case "$1" in
  is-active) echo inactive; exit 3 ;;
  is-enabled) echo disabled; exit 1 ;;
  list-timers) echo "NEXT LEFT LAST PASSED UNIT ACTIVATES"; exit 0 ;;
  *) exit 0 ;;
esac
EOF
  cat > "$stubs/curl" <<'EOF'
#!/usr/bin/env bash
exit "${QMD_HEALTH_RC:-0}"
EOF
  cat > "$stubs/ss" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
  for c in qmd tailscale git npx; do
    printf '#!/usr/bin/env bash\nexit 0\n' > "$stubs/$c"
  done
  cat > "$stubs/free" <<'EOF'
#!/usr/bin/env bash
echo "              total        used        free"
echo "Mem:            1Gi         2Gi         3Gi"
EOF
  cat > "$stubs/uptime" <<'EOF'
#!/usr/bin/env bash
echo " 12:00:00 up 1 day,  0 users,  load average: 0.00, 0.00, 0.00"
EOF
  cat > "$stubs/df" <<'EOF'
#!/usr/bin/env bash
echo "Filesystem      Size  Used Avail Use% Mounted on"
echo "/dev/sda1        20G    5G   15G  25% /"
EOF
  chmod +x "$stubs"/*
  mkdir -p "$home/agent-workforce/logs"
  echo "$home:$stubs"
}

run_scenario() {
  local home=$1 stubs=$2 rc_health=$3
  local out; out=$(mktemp)
  local rc=0
  HOME="$home" PATH="$stubs:$PATH" QMD_HEALTH_RC="$rc_health" env -u BRAVE_API_KEY bash "$SCRIPT" >"$out" 2>&1 || rc=$?
  echo "$rc:$out"
}

echo "--- scenario A: daemon healthy ---"
IFS=: read -r hA sA <<<"$(sandbox)"
IFS=: read -r rcA outA <<<"$(run_scenario "$hA" "$sA" 0)"
assert "exits 0" "[ '$rcA' = 0 ]"
assert "prints qmd MCP daemon section" "grep -q -- '── qmd MCP daemon (agent transport, NUC-16)' '$outA'"
assert "endpoint reachable" "grep -q -- 'endpoint : http://127.0.0.1:8765/mcp (reachable)' '$outA'"
assert "no profile line (T6.1: the hermes profile probe is retired)" "! grep -q -- 'claudius qmd' '$outA'"

echo "--- scenario B: daemon unreachable ---"
IFS=: read -r hB sB <<<"$(sandbox)"
IFS=: read -r rcB outB <<<"$(run_scenario "$hB" "$sB" 7)"
assert "exits 0" "[ '$rcB' = 0 ]"
assert "endpoint unreachable" "grep -q -- 'endpoint : http://127.0.0.1:8765/mcp (unreachable)' '$outB'"
assert "no profile line" "! grep -q -- 'claudius qmd' '$outB'"

# qmd-mcp reads index.yml only at start, and its instruction blurb is rendered then too; a
# config newer than the process means every MCP consumer is told the old posture (T8.5).
started_after() { [ "$1" -ge "$2" ]; }

echo "--- the reload check detects a config newer than the process ---"
assert "a process started after the edit is current" "started_after 200 100"
assert "a config edited after start is flagged"      "! started_after 100 200"

echo "--- live: qmd-mcp has loaded the current index.yml ---"
if box_only_with 'the live qmd-mcp unit and its config' \
     "$HOME/.config/qmd/index.yml" /etc/systemd/system/qmd-mcp.service; then
  start_s=$(date -d "$(systemctl show qmd-mcp -p ExecMainStartTimestamp --value)" +%s 2>/dev/null || echo 0)
  cfg_s=$(stat -c %Y "$HOME/.config/qmd/index.yml")
  echo "  info: qmd-mcp started $start_s, index.yml mtime $cfg_s"
  assert "qmd-mcp started after the last index.yml edit (else: sudo systemctl restart qmd-mcp)" \
    "started_after '$start_s' '$cfg_s'"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
