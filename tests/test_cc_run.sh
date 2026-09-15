#!/usr/bin/env bash
# bin/cc_run.sh + bin/cc_envelope.py (T5.2 step 2). Offline: a fake claude script stands in
# for the binary and answers from tests/fixtures/receipt-wiring/. Proves the wrapper is
# invisible with AGENT_USAGE_JSON unset, and with it set splits the JSON envelope into the
# `.result` text every existing reader parses and the usage side file the receipt reads.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO_ROOT=$(pwd)
FIX="$REPO_ROOT/tests/fixtures/receipt-wiring"
WRAP="$REPO_ROOT/bin/cc_run.sh"

fail=0
assert() {
  local desc=$1 cond=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# fake claude: records argv; with --output-format json prints $FAKE_BODY, else prints "text mode";
# exits $FAKE_RC.
make_fake() {
  local home=$1
  cat > "$home/claude" <<EOF
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$home/argv.log"
if printf '%s\n' "\$@" | grep -qx -- '--output-format'; then cat "\$FAKE_BODY"; else echo "text mode"; fi
echo "to stderr" >&2
exit "\${FAKE_RC:-0}"
EOF
  chmod +x "$home/claude"
  echo "$home/claude"
}

echo "--- cc-run-unset-is-exec ---"   # (::cc-run-unset-is-exec)
h=$(mktemp -d); fake=$(make_fake "$h")
rc=0; out=$(env -u AGENT_USAGE_JSON FAKE_BODY="$FIX/claude-envelope.json" bash "$WRAP" "$fake" -p "hi" --model m 2>"$h/err") || rc=$?
assert 'exits with claude'"'"'s status' "[ '$rc' = 0 ]"
assert 'argv is byte-identical (no --output-format)' "[ \"\$(cat '$h/argv.log')\" = \$'-p\nhi\n--model\nm' ]"
assert 'stdout is claude'"'"'s own text' "[ '$out' = 'text mode' ]"
assert 'stderr passes through' "grep -q 'to stderr' '$h/err'"
assert 'no side file appears' "[ -z \"\$(ls '$h' | grep -v -e claude -e argv.log -e err)\" ]"
rc=0; FAKE_RC=3 env -u AGENT_USAGE_JSON FAKE_BODY="$FIX/claude-envelope.json" bash "$WRAP" "$fake" -p hi >/dev/null 2>&1 || rc=$?
assert 'a non-zero status passes through unchanged' "[ '$rc' = 3 ]"

echo "--- cc-run-result-passthrough ---"   # (::cc-run-result-passthrough)
h=$(mktemp -d); fake=$(make_fake "$h"); usage="$h/last-attempt/job.usage.json"
rc=0; out=$(AGENT_USAGE_JSON="$usage" FAKE_BODY="$FIX/claude-envelope.json" bash "$WRAP" "$fake" -p "hi" --model m 2>"$h/err") || rc=$?
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'claude was asked for the JSON envelope' "grep -qx -- '--output-format' '$h/argv.log' && grep -qx json '$h/argv.log'"
assert 'the original flags are still there, first' "[ \"\$(head -4 '$h/argv.log' | tr '\n' ' ')\" = '-p hi --model m ' ]"
assert 'stdout is the .result text, newline-terminated' "[ \"\$out\" = 'OK' ]"
assert 'stderr passes through' "grep -q 'to stderr' '$h/err'"
rc=0; out=$(AGENT_USAGE_JSON="$usage" FAKE_BODY="$FIX/claude-envelope-error.json" FAKE_RC=1 bash "$WRAP" "$fake" -p hi 2>/dev/null) || rc=$?
assert 'is_error: claude'"'"'s exit 1 is preserved' "[ '$rc' = 1 ]"
assert 'is_error: the error text still reaches stdout for PROVIDER_ERROR_RE' "[ \"\$out\" = 'API Error: 529 overloaded_error' ]"

echo "--- cc-run-envelope-captured ---"   # (::cc-run-envelope-captured)
h=$(mktemp -d); fake=$(make_fake "$h"); usage="$h/last-attempt/job.usage.json"
AGENT_USAGE_JSON="$usage" FAKE_BODY="$FIX/claude-envelope.json" bash "$WRAP" "$fake" -p hi >/dev/null 2>&1
assert 'the envelope lands at AGENT_USAGE_JSON' "[ -s '$usage' ]"
assert 'and is the whole envelope, unchanged' "cmp -s '$usage' '$FIX/claude-envelope.json'"
assert 'no temp file is left beside it' "[ \"\$(ls '$h/last-attempt' | wc -l)\" = 1 ]"
AGENT_USAGE_JSON="$usage" FAKE_BODY="$FIX/claude-envelope-error.json" FAKE_RC=1 bash "$WRAP" "$fake" -p hi >/dev/null 2>&1
assert 'an is_error envelope is captured too (its usage is real spend)' "cmp -s '$usage' '$FIX/claude-envelope-error.json'"

echo "--- cc-run-garbage-is-unavailable ---"   # (::cc-run-garbage-is-unavailable)
h=$(mktemp -d); fake=$(make_fake "$h"); usage="$h/last-attempt/job.usage.json"
mkdir -p "$h/last-attempt"; echo '{"stale": true}' > "$usage"
rc=0; out=$(AGENT_USAGE_JSON="$usage" FAKE_BODY="$FIX/claude-garbage.txt" FAKE_RC=1 bash "$WRAP" "$fake" -p hi 2>/dev/null) || rc=$?
assert 'claude'"'"'s status is preserved' "[ '$rc' = 1 ]"
assert 'the raw bytes reach stdout so readers see what claude said' "[ \"\$out\" = \"\$(cat '$FIX/claude-garbage.txt')\" ]"
assert 'a DECLINE: line inside garbage is still greppable' "printf '%s\n' \"\$out\" | grep -q '^DECLINE:'"
assert 'the stale side file is removed, never left to be read as this run'"'"'s' "[ ! -e '$usage' ]"
assert 'no temp file is left' "[ \"\$(ls '$h/last-attempt' | wc -l)\" = 0 ]"
rc=0; out=$(AGENT_USAGE_JSON="$usage" FAKE_BODY=/dev/null bash "$WRAP" "$fake" -p hi 2>/dev/null) || rc=$?
assert 'empty output: exit code preserved, stdout empty, no side file' "[ '$rc' = 0 ] && [ -z \"\$out\" ] && [ ! -e '$usage' ]"

[ "$fail" = 0 ] && echo "PASS: cc_run" || { echo "FAIL: cc_run"; exit 1; }
