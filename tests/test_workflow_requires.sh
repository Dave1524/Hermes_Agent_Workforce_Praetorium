#!/usr/bin/env bash
# `requires` — one resolver for the screen's rows and the executor pre-flights (T5.3f).
# Static rules over the live manifests and mutated copies; `check` against a fake systemctl.
# Anchors live in tests/test_workflow_requires.py: (::workflow-requires-resolves)
# (::workflow-requires-fold-agrees) (::workflow-requires-unit-file)
# (::workflow-requires-buzz-handoff) (::workflow-requires-check)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

echo "--- canary ---"
assert "the pipefail canary passes" 'yes | grep -q y'

echo "--- units this box depends on that no repo unit file describes (EXTERNAL_UNITS) ---"
python3 - <<'PY'
import sys
sys.path.insert(0, "bin")
import workflow_requires
for key, description in workflow_requires.EXTERNAL_UNITS.items():
    print(f"  {key}\t{description}")
PY

echo "--- tests/test_workflow_requires.py ---"
assert "the requires suite is green" 'python3 tests/test_workflow_requires.py'

echo "--- executor pre-flights (::workflow-requires-preflight) ---"
# The two executors call the CLI before the run and honour exit 1. agent_propose.sh's half
# is driven end-to-end by tests/test_agent_propose_smoke.sh scenario 40; local_tier_eval.sh
# is driven here with a stub for the CLI, an empty out dir and its own lock, so Ollama and
# hermes are never reached — the stub's verdict is the only thing on trial.
assert "agent_propose.sh calls workflow_requires.py check on the unit systemd is running" \
  'grep -q "WORKFLOW_REQUIRES:-\$BIN_DIR/workflow_requires.py}\" check \"\$requires_unit\"" bin/agent_propose.sh'
assert "and a refusal is a BLOCKED exit" \
  'grep -A6 "workflow_requires.py}\" check" bin/agent_propose.sh | grep -q "block_exit"'
assert "local_tier_eval.sh calls workflow_requires.py check local-tier-eval" \
  'grep -q "WORKFLOW_REQUIRES:-\$REPO_BIN/workflow_requires.py}\" check local-tier-eval" bin/local_tier_eval.sh'
tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT
cat > "$tmp/down.sh" <<'EOF'
#!/usr/bin/env bash
echo "$*" >> "${0%/*}/argv.log"
echo "requires ollama.service: inactive"
exit 1
EOF
chmod +x "$tmp/down.sh"
rc=0
out=$(LOCAL_EVAL_OUT="$tmp/out" AGENT_PROPOSE_LOCK="$tmp/lock" WORKFLOW_REQUIRES="$tmp/down.sh" \
  HERMES_BIN=/bin/false bash bin/local_tier_eval.sh 2>&1) || rc=$?
assert "local_tier_eval.sh: a requirement down skips with exit 0" "[ '$rc' = 0 ]"
assert "  it asked about local-tier-eval" "grep -qx 'check local-tier-eval' '$tmp/argv.log'"
assert "  the CLI's line and the skip are in the log" \
  "printf '%s' \"\$out\" | grep -q 'requires ollama.service: inactive' && printf '%s' \"\$out\" | grep -q 'a requirement is down — skipping'"
assert "  and no scorecard was written" "! ls '$tmp'/out/*/scorecard.md >/dev/null 2>&1"
# Unknown is not a refusal, and that is the CLI's exit 0 (asserted above); the runner skips
# on the exit status alone, never on the words. main reads the live bus, so it is not run.
assert "local_tier_eval.sh: the skip is conditioned on the CLI's exit status only" \
  'grep -q "if \[ \"\$requires_rc\" -ne 0 \]; then" bin/local_tier_eval.sh && ! grep -q "requires_out.*inactive\|requires_out.*failed" bin/local_tier_eval.sh'
exit $fail
