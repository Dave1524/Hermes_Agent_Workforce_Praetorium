#!/usr/bin/env bash
# Test for bin/praetorium-status.sh's Brave MCP section (NUC-21) — mocked system
# commands, no network, no real key, no live search. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/praetorium-status.sh"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then
    echo "  ok: $desc"
  else
    echo "  FAIL: $desc"
    fail=1
  fi
}

# ── Sandbox: scratch $HOME + a stub PATH so the script never touches real
# systemd units, qmd index/daemon, tailscale, or the real ~/.hermes/.env ──
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

  cat > "$stubs/qmd" <<'EOF'
#!/usr/bin/env bash
echo "index: 0 docs (stub)"
exit 0
EOF

  cat > "$stubs/tailscale" <<'EOF'
#!/usr/bin/env bash
echo "100.0.0.1  stub-node  stub@  linux  -"
exit 0
EOF

  cat > "$stubs/git" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

  cat > "$stubs/npx" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

  # curl stub: keeps the qmd /health probe network-free (NUC-16 added a curl call).
  cat > "$stubs/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

  # ss stub: keeps the Brave :8766 endpoint probe network-free (prints nothing ->
  # endpoint resolves to 'down' in-sandbox).
  cat > "$stubs/ss" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

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
  mkdir -p "$home/.hermes" "$home/agent-workforce/logs"

  echo "$home:$stubs"
}

run_scenario() {
  local home=$1 stubs=$2
  local out; out=$(mktemp)
  local rc=0
  HOME="$home" PATH="$stubs:$PATH" env -u BRAVE_API_KEY bash "$SCRIPT" >"$out" 2>&1 || rc=$?
  echo "$rc:$out"
}

echo "--- scenario 1: BRAVE_API_KEY set (via ~/.hermes/.env) ---"
IFS=: read -r h1 s1 <<<"$(sandbox)"
echo "BRAVE_API_KEY=test-key-not-real" > "$h1/.hermes/.env"
IFS=: read -r rc1 out1 <<<"$(run_scenario "$h1" "$s1")"
assert "exits 0" "[ '$rc1' = 0 ]"
assert "prints Brave section" "grep -q -- '── Research MCP (Brave)' '$out1'"
assert "reports key=set" "grep -q -- 'key      : set' '$out1'"
assert "reports server=resolvable" "grep -q -- 'server   : resolvable' '$out1'"
assert "prints brave service line" "grep -q -- 'service  :' '$out1'"
assert "prints brave endpoint line (down in sandbox)" "grep -q -- 'endpoint : down (127.0.0.1:8766/mcp)' '$out1'"

echo "--- scenario 2: BRAVE_API_KEY absent ---"
IFS=: read -r h2 s2 <<<"$(sandbox)"
: > "$h2/.hermes/.env"
IFS=: read -r rc2 out2 <<<"$(run_scenario "$h2" "$s2")"
assert "exits 0" "[ '$rc2' = 0 ]"
assert "prints Brave section" "grep -q -- '── Research MCP (Brave)' '$out2'"
assert "reports key=MISSING" "grep -q -- 'key      : MISSING' '$out2'"

exit $fail
