#!/usr/bin/env bash
# Test for bin/praetorium-status.sh's fetch-backend section (NUC-22) — mocked
# system commands, no network, no real browser. Run via bin/verify.sh or directly.
# Positive case is fully HOME-sandboxed (~/.cache/ms-playwright glob); negative
# case relies on no system chrome on PATH (true on this box).
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/praetorium-status.sh"

fail=0
assert() {
  local desc=$1 cond=$2
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
}

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
  for c in curl ss qmd tailscale git npx; do
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
  mkdir -p "$home/.hermes" "$home/agent-workforce/logs"
  : > "$home/.hermes/.env"
  echo "$home:$stubs"
}

run_scenario() {
  local home=$1 stubs=$2
  local out; out=$(mktemp)
  local rc=0
  HOME="$home" PATH="$stubs:$PATH" env -u BRAVE_API_KEY -u AGENT_BROWSER_EXECUTABLE_PATH \
    bash "$SCRIPT" >"$out" 2>&1 || rc=$?
  echo "$rc:$out"
}

echo "--- scenario 1: Chromium present (HOME-sandboxed agent-browser install) ---"
IFS=: read -r h1 s1 <<<"$(sandbox)"
mkdir -p "$h1/.agent-browser/browsers/chrome-150.0.7871.49"
: > "$h1/.agent-browser/browsers/chrome-150.0.7871.49/chrome"
IFS=: read -r rc1 out1 <<<"$(run_scenario "$h1" "$s1")"
assert "exits 0" "[ '$rc1' = 0 ]"
assert "prints fetch backend section" "grep -q -- '── Fetch backend (browser' '$out1'"
assert "mode local-headless-chromium" "grep -q -- 'mode    : local-headless-chromium' '$out1'"
assert "chromium installed" "grep -q -- 'chromium: installed' '$out1'"
assert "runner npx-fallback" "grep -q -- 'runner  : npx-fallback' '$out1'"

echo "--- scenario 2: Chromium absent ---"
IFS=: read -r h2 s2 <<<"$(sandbox)"
IFS=: read -r rc2 out2 <<<"$(run_scenario "$h2" "$s2")"
assert "exits 0" "[ '$rc2' = 0 ]"
assert "chromium MISSING" "grep -q -- 'chromium: MISSING' '$out2'"
assert "runner npx-fallback" "grep -q -- 'runner  : npx-fallback' '$out2'"

exit $fail
