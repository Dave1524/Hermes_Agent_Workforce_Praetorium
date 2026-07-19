#!/usr/bin/env bash
# Test for bin/praetorium-status.sh's Working memory section (NUC-21) — mocked
# system commands, no network, no real profiles. Run via bin/verify.sh or directly.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/praetorium-status.sh"
DELIM=$'\n§\n'

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

  cat > "$stubs/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF

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

echo "--- scenario 1: multiple profiles, mixed populated/empty ---"
IFS=: read -r h1 s1 <<<"$(sandbox)"
mkdir -p "$h1/.hermes/profiles/claudius/memories" "$h1/.hermes/profiles/augustus/memories" \
         "$h1/.hermes/profiles/marcus/memories"
printf 'entry-01%sentry-02%sentry-03' "$DELIM" "$DELIM" > "$h1/.hermes/profiles/claudius/memories/MEMORY.md"
printf 'entry-01' > "$h1/.hermes/profiles/augustus/memories/MEMORY.md"
# marcus left with no MEMORY.md at all (never run yet)
IFS=: read -r rc1 out1 <<<"$(run_scenario "$h1" "$s1")"
assert "exits 0" "[ '$rc1' = 0 ]"
assert "prints Working memory section" "grep -q -- '── Working memory (all profiles, NUC-21)' '$out1'"
assert "reports claudius entry count" "grep -q -- 'claudius   entries: 3' '$out1'"
assert "reports augustus entry count" "grep -q -- 'augustus   entries: 1' '$out1'"
assert "reports marcus store empty" "grep -q -- 'marcus     store empty' '$out1'"

echo "--- scenario 2: no profile directories at all ---"
IFS=: read -r h2 s2 <<<"$(sandbox)"
IFS=: read -r rc2 out2 <<<"$(run_scenario "$h2" "$s2")"
assert "exits 0" "[ '$rc2' = 0 ]"
assert "reports no profile memory directories found" "grep -q -- 'no profile memory directories found' '$out2'"

exit $fail
