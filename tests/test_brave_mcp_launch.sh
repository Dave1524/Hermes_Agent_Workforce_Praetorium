#!/usr/bin/env bash
# bin/brave_mcp_launch.sh (T6.1): the launcher moved into the repo from ~/.hermes/bin. A fake
# server on BRAVE_MCP_SERVER records its argv and env; nothing here runs npx or a live unit.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LAUNCHER="$REPO_ROOT/bin/brave_mcp_launch.sh"
UNIT="$REPO_ROOT/systemd/brave-mcp.service"

fail=0
assert() {
  local desc=$1 cond=$2 pf
  pf=$(set +o | grep pipefail); set +o pipefail
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
cat > "$work/fake-server" <<'EOF'
#!/usr/bin/env bash
printf '%s\n' "$@" > "$FAKE_ARGV"
printf '%s\n' "${BRAVE_API_KEY:-<unset>}" > "$FAKE_ENV"
exit 0
EOF
chmod +x "$work/fake-server"

echo "== launcher: key present =="  # (::brave-launcher-logs-and-execs)
FAKE_ARGV="$work/argv1" FAKE_ENV="$work/env1" BRAVE_MCP_LOG="$work/launch.log" \
  BRAVE_MCP_SERVER="$work/fake-server" BRAVE_API_KEY=abcde \
  bash "$LAUNCHER" --transport http --port 8766 --host 127.0.0.1
assert 'launcher is executable in source' "[ -x '$LAUNCHER' ]"
assert 'one launch line, key=set(len=5)' "[ \"\$(grep -c 'launch pid=' '$work/launch.log')\" = 1 ] && grep -q 'key=set(len=5)' '$work/launch.log'"
assert 'argv passes through verbatim' "[ \"\$(tr '\n' ' ' < '$work/argv1')\" = '-y @brave/brave-search-mcp-server --transport http --port 8766 --host 127.0.0.1 ' ]"
assert 'the key reaches the server env' "[ \"\$(cat '$work/env1')\" = abcde ]"
assert 'the key value never reaches the log' "! grep -q abcde '$work/launch.log'"

echo "== launcher: key missing =="
FAKE_ARGV="$work/argv2" FAKE_ENV="$work/env2" BRAVE_MCP_LOG="$work/launch.log" \
  BRAVE_MCP_SERVER="$work/fake-server" bash "$LAUNCHER" --transport http
assert 'second launch logs key=MISSING' "[ \"\$(grep -c 'launch pid=' '$work/launch.log')\" = 2 ] && tail -1 '$work/launch.log' | grep -q 'key=MISSING'"

echo "== unit execs the repo launcher =="  # (::brave-unit-execs-repo-launcher)
assert 'ExecStart names the deployed repo path' "grep -qE '^ExecStart=/home/dave/agent-workforce/bin/brave_mcp_launch.sh --transport http --port 8766 --host 127.0.0.1$' '$UNIT'"
assert 'no ~/.hermes path anywhere in the unit' "! grep -q '/.hermes/' '$UNIT'"

[ "$fail" = 0 ] && echo "PASS: brave_mcp_launch" || { echo "FAIL: brave_mcp_launch"; exit 1; }
