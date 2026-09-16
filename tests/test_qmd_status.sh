#!/usr/bin/env bash
# Test for bin/praetorium-status.sh's qmd MCP daemon section (NUC-16) — mocked
# system commands, no network, no live daemon. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/praetorium-status.sh"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
}

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

exit $fail
