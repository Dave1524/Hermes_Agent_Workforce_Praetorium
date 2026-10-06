#!/usr/bin/env bash
# The agent_propose time budget (brief agent-propose-timeout-budget, 2026-10-06).
#
#   A. bin/propose_budget.py audit: every unit that runs the runner fits the committed example
#      its AGENT_JOB_OVERRIDES names, and an edit to either side goes red.
#   B. bin/agent_propose.sh at run time, from the values it loaded: only a fast failure is
#      retried, a retry that cannot finish is not started, every timeout is named in the log,
#      cost.log and the receipt, a misfit is declared as an incident, and a systemd kill
#      (SIGTERM) still leaves one cost.log row and a receipt.
# Stub runtime, stub contract executor, sandboxed $HOME: no model, relay or systemctl.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/agent_propose.sh"
BUDGET="$REPO_ROOT/bin/propose_budget.py"

fail=0
assert() {
  local desc=$1 cond=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$cond"; then
    echo "  ok: $desc"
  else
    echo "  FAIL: $desc"
    fail=1
  fi
  eval "$pf"
}

assert "a found pattern is never reported as a failure" "yes | grep -q y"

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

audit_copy() {
  local dir=$1
  rm -rf "$dir"; mkdir -p "$dir"
  cp -r "$REPO_ROOT/systemd" "$dir/systemd"
  cp -r "$REPO_ROOT/profiles" "$dir/profiles"
}
audit_rc() {
  local rc=0
  python3 "$BUDGET" audit "$1/systemd" "$1/profiles" >"$1/audit.out" 2>&1 || rc=$?
  echo "$rc"
}

echo "--- A1. the committed units and examples fit (::budget-audit-green) ---"
rc=0; python3 "$BUDGET" audit "$REPO_ROOT/systemd" "$REPO_ROOT/profiles" >"$TMP/audit.out" 2>&1 || rc=$?
assert "audit exits 0 over the repo" "[ '$rc' = 0 ]"
assert "every runner unit is audited (twelve today, enumerated not counted)" \
  "[ \"\$(grep -c '^ok: ' '$TMP/audit.out')\" = \"\$(grep -lE '^ExecStart=.*(agent_propose|content_change_dispatch)\\.sh' '$REPO_ROOT'/systemd/*.service | wc -l)\" ]"
assert "both augustus-content units read the one example" \
  "[ \"\$(grep -c 'augustus-content.env.example' '$TMP/audit.out')\" = 2 ]"

echo "--- A2. an edit to either side goes red (::budget-audit-red) ---"
a="$TMP/a"
audit_copy "$a"; sed -i 's/^TimeoutStartSec=.*/TimeoutStartSec=20min/' "$a/systemd/praetorium-daily-plan.service"
assert "a unit shrunk below its worst case is red" "[ \"\$(audit_rc '$a')\" = 1 ] && grep -q 'FAIL: praetorium-daily-plan.service: worst case' '$a/audit.out'"
audit_copy "$a"; sed -i 's/^AGENT_TIMEOUT_MINUTES=.*/AGENT_TIMEOUT_MINUTES=30/' "$a/profiles/daily_plan.env.example"
assert "a per-attempt limit raised past the unit is red" "[ \"\$(audit_rc '$a')\" = 1 ] && grep -q 'FAIL: praetorium-daily-plan.service' '$a/audit.out'"
audit_copy "$a"; sed -i '/^AGENT_RETRY_WITHIN_SECONDS=/d' "$a/profiles/raw_ingest.env.example"
assert "an example missing a knob is red (the audit never assumes the script's defaults)" \
  "[ \"\$(audit_rc '$a')\" = 1 ] && grep -q 'raw_ingest.env.example does not set AGENT_RETRY_WITHIN_SECONDS' '$a/audit.out'"
audit_copy "$a"; sed -i 's/^AGENT_MAX_ATTEMPTS=.*/AGENT_MAX_ATTEMPTS=3/' "$a/profiles/augustus-content.env.example"
sed -i 's/^TimeoutStartSec=.*/TimeoutStartSec=30min/' "$a/systemd/content-change-dispatch.service"
assert "a shared example is checked against every unit that reads it" \
  "[ \"\$(audit_rc '$a')\" = 1 ] && grep -q 'FAIL: content-change-dispatch.service' '$a/audit.out'"
audit_copy "$a"; printf '[Service]\nExecStart=/home/dave/agent-workforce/bin/agent_propose.sh\nTimeoutStartSec=45min\n' >"$a/systemd/new-job.service"
assert "a new runner unit without AGENT_JOB_OVERRIDES is red" "[ \"\$(audit_rc '$a')\" = 1 ] && grep -q 'FAIL: new-job.service: .*sets no AGENT_JOB_OVERRIDES' '$a/audit.out'"
audit_copy "$a"; printf '[Service]\nEnvironment=AGENT_JOB_OVERRIDES=/x/brand_new.env\nExecStart=/home/dave/agent-workforce/bin/agent_propose.sh\nTimeoutStartSec=45min\n' >"$a/systemd/new-job.service"
assert "a new runner unit with no committed example is red" "[ \"\$(audit_rc '$a')\" = 1 ] && grep -q 'no committed example brand_new.env.example' '$a/audit.out'"

echo "--- A3. the arithmetic (::budget-arithmetic) ---"
check() { PROPOSE_BUDGET_LIMIT=$1 PROPOSE_BUDGET_REMAINING="" python3 "$BUDGET" check --attempts 2 --timeout-min 15 --retry-base 30 --retry-within 300 --reserve 180; }
assert "2 x 15m, fast retry within 300s, 180s reserve: worst 1410s" "check 1500 | grep -q 'budget=fit worst=1410 limit=1500'"
assert "the 60s margin is part of fitting" "check 1440 | grep -q 'budget=misfit worst=1410'"
assert "no limit is unknown, never misfit" "PROPOSE_BUDGET_LIMIT='' PROPOSE_BUDGET_REMAINING='' python3 '$BUDGET' check --attempts 9 --timeout-min 99 --retry-base 30 --retry-within 300 --reserve 180 | grep -q 'budget=unknown'"
assert "systemd spans parse" "python3 -c 'import sys; sys.path.insert(0, \"$REPO_ROOT/bin\"); import propose_budget as b; assert b.parse_span(\"1h 30min\") == 5400 and b.parse_span(\"90\") == 90 and b.parse_span(\"infinity\") is None'"

# ── B. the runner ────────────────────────────────────────────────────────────
sandbox() {
  local home; home=$(mktemp -d "$TMP/home.XXXX")
  mkdir -p "$home/.config/agent-workforce" "$home/agent-workforce/logs" "$home/mockbin"
  cat >"$home/runtime.sh" <<EOF
#!/usr/bin/env bash
echo attempt >> "$home/attempts"
sleep "\${MOCK_SLEEP:-0}"
exit "\${MOCK_EXIT:-0}"
EOF
  cat >"$home/exec_stub.py" <<'EOF'
#!/usr/bin/env python3
import json, os, sys
with open(os.environ["STUB_OUT"], "a") as fh:
    fh.write(json.dumps(sys.argv[1:]) + "\n")
EOF
  printf '#!/usr/bin/env bash\nexit 0\n' >"$home/requires_stub"
  chmod +x "$home/runtime.sh" "$home/exec_stub.py" "$home/requires_stub"
  cat >"$home/.config/agent-workforce/secrets.env" <<EOF
OPENROUTER_API_KEY=test-key-not-real
AGENT_RUNTIME_CMD=$home/runtime.sh
AGENT_PROFILE=claude-sonnet
AGENT_TASK_SLUG=budget-fixture
AGENT_RUN_MODE=ops
AGENT_MAX_ATTEMPTS=2
AGENT_TIMEOUT_MINUTES=1
AGENT_RETRY_BASE_SECONDS=0
AGENT_BUDGET_RESERVE_SECONDS=0
EOF
  echo "$home"
}
# Every scenario names its unit, so the receipt and the incident have an owner; the budget's
# limit and remaining come from PROPOSE_BUDGET_* (set per scenario), never from systemctl.
runner_env() {
  local home=$1
  echo HOME="$home" AGENT_PROPOSE_LOCK="$home/lock" QMD_HEALTH_POLICY=off BRAVE_HEALTH_POLICY=off \
    DELIVERY_JOB=budget-fixture.service WORKFLOW_REQUIRES="$home/requires_stub" \
    CONTRACT_EXEC="$home/exec_stub.py" STUB_OUT="$home/receipts.jsonl"
}
run_runner() {
  local home=$1; shift
  local rc=0
  env $(runner_env "$home") "$@" bash "$SCRIPT" >"$home/stdout.log" 2>&1 || rc=$?
  echo "$rc"
}
cost() { cat "$1/agent-workforce/logs/cost.log"; }
plog() { cat "$1/agent-workforce/logs/agent_propose.log"; }
attempts() { wc -l <"$1/attempts" | tr -d ' '; }
failed_reason() { python3 -c 'import json,sys; c=[json.loads(l) for l in open(sys.argv[1])][-1]; print(c[c.index("--failed")+1])' "$1/receipts.jsonl"; }

echo "--- B1. a fast failure is retried (::budget-fast-fail-retried) ---"
h=$(sandbox)
rc=$(run_runner "$h" MOCK_EXIT=1 PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=10000)
assert "exits 1" "[ '$rc' = 1 ]"
assert "both attempts ran" "[ \"\$(attempts '$h')\" = 2 ]"
assert "cost.log: FAIL, no timeout, budget fit" "cost '$h' | grep -q 'outcome=FAIL .*attempts=2 .*timeout=none budget=fit'"

echo "--- B2. a slow failure is not retried (::budget-slow-fail-not-retried) ---"
h=$(sandbox)
rc=$(run_runner "$h" MOCK_EXIT=1 MOCK_SLEEP=2 AGENT_RETRY_WITHIN_SECONDS=1 PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=10000)
assert "exits 1" "[ '$rc' = 1 ]"
assert "one attempt only" "[ \"\$(attempts '$h')\" = 1 ]"
assert "the log says why there was no retry" "plog '$h' | grep -q 'no retry: attempt 1 failed (rc 1) after [0-9]*s, slower than AGENT_RETRY_WITHIN_SECONDS=1'"
assert "the FAIL line does not claim attempts that never ran" "plog '$h' | grep -q 'FAIL: runtime failed after 1 of 2 attempts (no retry)'"

echo "--- B3. an attempt that hits its limit is named everywhere (::budget-attempt-timeout-named) ---"
h=$(sandbox)
rc=$(run_runner "$h" MOCK_SLEEP=20 PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=3)
assert "exits 1" "[ '$rc' = 1 ]"
assert "the attempt was clamped to the unit's deadline" "plog '$h' | grep -q 'attempt 1 clamped to [0-9]*s by the unit.s deadline'"
assert "TIMEOUT line names the limit and the elapsed seconds" "plog '$h' | grep -qE 'TIMEOUT: attempt 1/2 hit the [0-9]+s limit after [0-9]+s'"
assert "a timed-out attempt is not retried" "[ \"\$(attempts '$h')\" = 1 ]"
assert "cost.log: one FAIL row with timeout=attempt" "[ \"\$(cost '$h' | grep -c 'outcome=FAIL .*timeout=attempt')\" = 1 ]"
assert "the receipt's failed reason names the timeout" "failed_reason '$h' | grep -qE '^FAIL: rc=124 timeout=attempt: attempt 1/2 hit the [0-9]+s limit'"

echo "--- B4. a retry that cannot finish is not started (::budget-retry-deadline) ---"
h=$(sandbox)
rc=$(run_runner "$h" MOCK_EXIT=1 PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=30)
assert "exits 1" "[ '$rc' = 1 ]"
assert "one attempt only" "[ \"\$(attempts '$h')\" = 1 ]"
assert "TIMEOUT line says there was no room" "plog '$h' | grep -q 'TIMEOUT: no room for attempt 2/2: it needs 0s backoff + 60s'"
assert "cost.log: timeout=deadline" "cost '$h' | grep -q 'outcome=FAIL .*timeout=deadline'"
assert "the receipt names it" "failed_reason '$h' | grep -q 'timeout=deadline: no room for attempt 2/2'"

echo "--- B5. a misfit is loud and declared; a later fit resolves it (::budget-misfit-declared) ---"
h=$(sandbox)
rc=$(run_runner "$h" PROPOSE_BUDGET_LIMIT=100 PROPOSE_BUDGET_REMAINING=100)
incident="$h/agent-workforce/var/incidents/declared/failed-assertion_budget-fixture_budget-misfit.json"
assert "the run still succeeds" "[ '$rc' = 0 ] && cost '$h' | grep -q 'outcome=OPS'"
assert "BUDGET MISFIT is logged" "plog '$h' | grep -q 'BUDGET MISFIT: 2 x 1m .* cannot fit budget-fixture.service'"
assert "cost.log carries budget=misfit" "cost '$h' | grep -q 'budget=misfit'"
assert "a failed-assertion incident is declared for the unit" "python3 -c 'import json,sys; d=json.load(open(sys.argv[1])); assert d[\"class\"]==\"failed-assertion\" and d[\"resolved_at\"] is None' '$incident'"
rc=$(run_runner "$h" PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=10000)
assert "a fitting run resolves it" "python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))[\"resolved_at\"]' '$incident'"
h=$(sandbox)
rc=$(run_runner "$h" DELIVERY_JOB="")
assert "a hand run (no unit) is budget=unknown and unclamped" "cost '$h' | grep -q 'outcome=OPS .*budget=unknown' && ! plog '$h' | grep -q clamped"
h=$(sandbox)
rc=$(run_runner "$h" AGENT_RETRY_WITHIN_SECONDS=1.5 PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=10000)
assert "a non-integer knob is BLOCKED, recorded, never crashes unrecorded" "[ '$rc' = 0 ] && cost '$h' | grep -q 'outcome=BLOCKED' && plog '$h' | grep -q 'retry_within must be a whole number'"

echo "--- B6. a systemd kill still leaves one row and a receipt (::budget-unit-kill-recorded) ---"
h=$(sandbox)
env $(runner_env "$h") MOCK_SLEEP=30 PROPOSE_BUDGET_LIMIT=10000 PROPOSE_BUDGET_REMAINING=10000 \
  bash "$SCRIPT" >"$h/stdout.log" 2>&1 &
pid=$!
for _ in $(seq 50); do [ -s "$h/attempts" ] && break; sleep 0.1; done
# systemd signals the whole cgroup; the runner, then its child `timeout`, is the same here.
kill -TERM "$pid"; pkill -TERM -P "$pid" || true
rc=0; wait "$pid" || rc=$?
pkill -f "$h/runtime.sh" || true
assert "exits 143" "[ '$rc' = 143 ]"
assert "TIMEOUT line names the systemd kill" "plog '$h' | grep -q 'TIMEOUT: systemd terminated the run after [0-9]*s, during attempt 1/2'"
assert "exactly one cost.log row, FAIL timeout=unit" "[ \"\$(wc -l <'$h/agent-workforce/logs/cost.log')\" = 1 ] && cost '$h' | grep -q 'outcome=FAIL .*timeout=unit'"
assert "a receipt names it" "failed_reason '$h' | grep -q '^FAIL: rc=143 timeout=unit: systemd terminated the run'"

echo
if [ "$fail" -eq 0 ]; then echo "PASS: propose budget"; else echo "FAILED: propose budget"; fi
exit "$fail"
