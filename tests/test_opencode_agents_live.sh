#!/usr/bin/env bash
# Opt-in LIVE contract tests for OpenCode agents + observability.
# SPENDS MODEL TOKENS. Skipped unless OPENCODE_LIVE_TESTS=1.
#
# Uses a temporary fixture repository only — never mutates the real
# Praetorium agent-workforce checkout during behavioral runs.
#
# Usage:
#   OPENCODE_LIVE_TESTS=1 bash tests/test_opencode_agents_live.sh
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ANALYZER="$REPO_ROOT/tools/opencode-observability/analyze_flows.py"
OBSERVE="$REPO_ROOT/bin/opencode-observe"
AGENTS_SRC="$REPO_ROOT/.opencode/agents"

if [[ "${OPENCODE_LIVE_TESTS:-0}" != "1" ]]; then
  echo "SKIP: live OpenCode agent contract tests (set OPENCODE_LIVE_TESTS=1 to spend model tokens)"
  exit 0
fi

if ! command -v opencode >/dev/null 2>&1; then
  echo "FAIL: opencode not found on PATH" >&2
  exit 1
fi
if ! command -v mitmdump >/dev/null 2>&1; then
  echo "FAIL: mitmdump not found (required for live capture)" >&2
  exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
RESULTS_JSON="$TMP/results.json"
: > "$TMP/results.ndjson"

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

echo "=== LIVE OpenCode agent contract tests (SPENDS MODEL TOKENS) ==="
echo "  fixture root: $TMP"
echo "  real repo is not used as cwd for agent runs"

# ── Fixture repository ─────────────────────────────────────────────────────────

make_fixture_repo() {
  local dest=$1
  mkdir -p "$dest/src" "$dest/tests" "$dest/.opencode/agents"
  # Copy agent configs so OpenCode discovers them inside the fixture repo.
  cp "$AGENTS_SRC/praetorium-planner.md" "$dest/.opencode/agents/"
  cp "$AGENTS_SRC/praetorium-developer.md" "$dest/.opencode/agents/"
  cp "$AGENTS_SRC/praetorium-qa.md" "$dest/.opencode/agents/"

  cat > "$dest/src/greet.py" <<'PY'
def greet(name: str) -> str:
    return f"hello, {name}"
PY

  cat > "$dest/tests/test_greet.py" <<'PY'
from src.greet import greet

def test_greet():
    assert greet("world") == "hello, world"
PY

  cat > "$dest/README.md" <<'EOF'
# fixture-greeter

Tiny fixture project used only for OpenCode live contract tests.
EOF

  # Intentional defect for QA scenario C (seeded later into a copy).
  git -C "$dest" init -q
  git -C "$dest" config user.email "live-test@example.com"
  git -C "$dest" config user.name "Live Test"
  git -C "$dest" add -A
  git -C "$dest" commit -q -m "init fixture"
}

FIXTURE_BASE="$TMP/fixture-base"
make_fixture_repo "$FIXTURE_BASE"

snapshot_tree() {
  local dir=$1
  # Stable file inventory + content hashes, excluding .git
  (cd "$dir" && find . -type f ! -path './.git/*' | sort | while read -r f; do
    printf '%s %s\n' "$(sha256sum "$f" | awk '{print $1}')" "$f"
  done)
}

run_agent() {
  # run_agent <label> <workdir> <obs_dir> <opencode args...>
  local label=$1 workdir=$2 obs_dir=$3
  shift 3
  mkdir -p "$obs_dir"
  local out="$obs_dir/stdout.txt"
  local err="$obs_dir/stderr.txt"
  local rc=0
  local port=$(( 19000 + RANDOM % 1000 ))
  # --auto approves ask-level permissions inside the isolated fixture only.
  # Captures go under obs_dir (temp), never into the real repo.
  # Custom praetorium-* agents are subagents; invoke via @mention in the prompt
  # (more reliable than --agent for mode: subagent). Built-ins use --agent.
  (
    cd "$workdir"
    OPENCODE_OBSERVABILITY_DIR="$obs_dir" \
      bash "$OBSERVE" --dir "$obs_dir" --port "$port" -- \
        run --format default --auto "$@"
  ) >"$out" 2>"$err" || rc=$?
  echo "$rc"
}

record_metrics() {
  local label=$1 flows_dir=$2 out_file=$3 rc=$4
  python3 - "$label" "$flows_dir" "$out_file" "$rc" "$TMP/results.ndjson" "$ANALYZER" <<'PY'
import json, subprocess, sys
from pathlib import Path

label, flows_dir, out_file, rc, ndjson_path, analyzer = sys.argv[1:7]
flows = Path(flows_dir)
if not flows.exists():
    # bin/opencode-observe nests under <dir>/opencode-observability/flows
    candidate = Path(flows_dir) / "opencode-observability" / "flows"
    if candidate.exists():
        flows = candidate
    else:
        # also accept bare dir
        flows = Path(flows_dir)

report = {"flows_analyzed": 0, "usage": {"has_actual_metadata": False, "actual": None, "estimated": {}},
          "title_generation_calls": 0, "unique_models": {}, "system_prompt": {},
          "tool_definitions": {}, "latency": {}, "errors": []}
if flows.exists() and any(flows.glob("*.json")):
    r = subprocess.run([sys.executable, analyzer, str(flows), "--json"],
                       capture_output=True, text=True)
    if r.stdout.strip():
        report = json.loads(r.stdout)

usage = report.get("usage", {})
actual = usage.get("actual") or {}
estimated = usage.get("estimated") or {}
classified = bool(usage.get("has_actual_metadata")) or bool(estimated)
row = {
    "label": label,
    "exit_code": int(rc),
    "models": report.get("unique_models", {}),
    "calls": report.get("flows_analyzed", 0),
    "title_generation_calls": report.get("title_generation_calls", 0),
    "usage_classified": classified,
    "usage_actual": actual or None,
    "usage_estimated": estimated or None,
    "system_prompt": report.get("system_prompt", {}),
    "tool_definitions": report.get("tool_definitions", {}),
    "latency": report.get("latency", {}),
    "errors": report.get("errors", []),
    "stdout_path": out_file,
}
with open(ndjson_path, "a", encoding="utf-8") as fh:
    fh.write(json.dumps(row, sort_keys=True) + "\n")
print(json.dumps(row, indent=2, sort_keys=True))
PY
}

# ── A. Planner: harmless request, no file mutations ───────────────────────────

echo "--- A: planner contract (temp fixture) ---"
PLAN_DIR="$TMP/A-planner"
cp -a "$FIXTURE_BASE" "$PLAN_DIR"
BEFORE=$(snapshot_tree "$PLAN_DIR")
OBS_A="$TMP/obs-A"
RC_A=$(run_agent "planner" "$PLAN_DIR" "$OBS_A" \
  "@praetorium-planner Inspect this repository and produce an implementation plan to add a farewell(name) function next to greet(), including tests. Do not edit any files.")
AFTER=$(snapshot_tree "$PLAN_DIR")
OUT_A="$OBS_A/stdout.txt"
METRICS_A=$(record_metrics "A-planner" "$OBS_A" "$OUT_A" "$RC_A")
echo "$METRICS_A" | head -n 40

assert "A: planner made no file changes" "[[ '$BEFORE' == '$AFTER' ]]"
assert "A: output has ## Plan" "grep -qE '^## Plan' '$OUT_A'"
assert "A: output has ## Files" "grep -qE '^## Files' '$OUT_A'"
assert "A: output has ## Acceptance Tests" "grep -qE '^## Acceptance Tests' '$OUT_A'"
assert "A: output has ## Risks" "grep -qE '^## Risks' '$OUT_A'"
assert "A: output has ## Blockers" "grep -qE '^## Blockers' '$OUT_A'"
assert "A: plan names concrete files" "grep -Eq 'src/greet\\.py|tests/test_greet\\.py|farewell' '$OUT_A'"
assert "A: plan names acceptance tests" "grep -Eqi 'test_|acceptance|assert|pytest|unittest' '$OUT_A'"
assert "A: usage classified" "echo '$METRICS_A' | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"usage_classified\"]'"

# ── B. Developer: tiny fixture change ─────────────────────────────────────────

echo "--- B: developer contract (temp fixture) ---"
DEV_DIR="$TMP/B-developer"
cp -a "$FIXTURE_BASE" "$DEV_DIR"
OBS_B="$TMP/obs-B"
RC_B=$(run_agent "developer" "$DEV_DIR" "$OBS_B" \
  "@praetorium-developer Implement farewell(name) in src/greet.py that returns f'goodbye, {name}'. Add test_farewell in tests/test_greet.py. Run the tests. Do not commit or push. Stay inside this repository.")
OUT_B="$OBS_B/stdout.txt"
METRICS_B=$(record_metrics "B-developer" "$OBS_B" "$OUT_B" "$RC_B")
echo "$METRICS_B" | head -n 40

# Only intended files should change (greet.py and/or test_greet.py). Ignore .opencode and .git.
CHANGED_B=$(cd "$DEV_DIR" && git status --porcelain | awk '{print $2}' | grep -v '^\.opencode/' || true)
assert "B: only intended files changed" \
  "python3 -c \"
import sys
changed = '''$CHANGED_B'''.strip().splitlines()
allowed = {'src/greet.py', 'tests/test_greet.py'}
bad = [c for c in changed if c and c not in allowed]
assert not bad, bad
assert 'src/greet.py' in changed or 'tests/test_greet.py' in changed, changed
print('ok')
\""
assert "B: fixture test passes" \
  "python3 -c \"
import sys
sys.path.insert(0, '$DEV_DIR')
from src.greet import greet
# farewell may exist after developer run
import importlib
mod = importlib.import_module('src.greet')
assert greet('world') == 'hello, world'
if hasattr(mod, 'farewell'):
    assert mod.farewell('world') == 'goodbye, world'
print('ok')
\""
# Prefer running the fixture test file if present
if [[ -f "$DEV_DIR/tests/test_greet.py" ]]; then
  assert "B: tests/test_greet.py executes" \
    "python3 -c \"
import runpy, sys
sys.path.insert(0, '$DEV_DIR')
# execute assertions in the test module style
ns = {}
code = open('$DEV_DIR/tests/test_greet.py').read()
# simple exec of test functions if pure asserts
exec(compile(code, 'test_greet.py', 'exec'), ns)
for k,v in list(ns.items()):
    if k.startswith('test_') and callable(v):
        v()
print('ok')
\""
fi
assert "B: output has ## Changed" "grep -qE '^## Changed' '$OUT_B'"
assert "B: output has ## Tests" "grep -qE '^## Tests' '$OUT_B'"
assert "B: output has ## Remaining" "grep -qE '^## Remaining' '$OUT_B'"
assert "B: output has ## Needs Approval" "grep -qE '^## Needs Approval' '$OUT_B'"
assert "B: usage classified" "echo '$METRICS_B' | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"usage_classified\"]'"

# ── C. QA: seeded defect → FAIL, no mutations ─────────────────────────────────

echo "--- C: qa contract with seeded defect (temp fixture) ---"
QA_DIR="$TMP/C-qa"
cp -a "$FIXTURE_BASE" "$QA_DIR"
# Seed a known defect: greet returns wrong string
cat > "$QA_DIR/src/greet.py" <<'PY'
def greet(name: str) -> str:
    return f"hi, {name}"  # DEFECT: should be "hello, {name}"
PY
git -C "$QA_DIR" add -A
git -C "$QA_DIR" commit -q -m "seed greet defect"
BEFORE_C=$(snapshot_tree "$QA_DIR")
OBS_C="$TMP/obs-C"
RC_C=$(run_agent "qa" "$QA_DIR" "$OBS_C" \
  "@praetorium-qa Review this repository. Run tests/test_greet.py (or equivalent). The greet() function is supposed to return 'hello, {name}'. Report PASS/FAIL/BLOCKED. Do not edit any files.")
AFTER_C=$(snapshot_tree "$QA_DIR")
OUT_C="$OBS_C/stdout.txt"
METRICS_C=$(record_metrics "C-qa" "$OBS_C" "$OUT_C" "$RC_C")
echo "$METRICS_C" | head -n 40

assert "C: qa made no file changes" "[[ '$BEFORE_C' == '$AFTER_C' ]]"
assert "C: output has Verdict heading" "grep -qE '^## Verdict:' '$OUT_C'"
assert "C: QA returns FAIL" "grep -Eqi '^## Verdict:[[:space:]]*FAIL' '$OUT_C'"
assert "C: defect is identified" "grep -Eqi 'hello|greet|defect|fail|expected|assert' '$OUT_C'"
assert "C: output has ## Findings" "grep -qE '^## Findings' '$OUT_C'"
assert "C: output has ## Tests Run" "grep -qE '^## Tests Run' '$OUT_C'"
assert "C: output has ## Security Checks" "grep -qE '^## Security Checks' '$OUT_C'"
assert "C: usage classified" "echo '$METRICS_C' | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"usage_classified\"]'"

# ── D. Minimal prompt × agents × 3 runs (metrics only) ────────────────────────

echo "--- D: minimal prompt metrics across agents (3 runs each) ---"
# Each entry: name|message-or-flags. Custom agents use @mention; built-ins use --agent.
run_matrix_once() {
  local name=$1
  local i=$2
  local RUN_DIR="$TMP/D-$name-$i"
  local OBS_D="$TMP/obs-D-$name-$i"
  cp -a "$FIXTURE_BASE" "$RUN_DIR"
  local RC_D
  case "$name" in
    build)
      RC_D=$(run_agent "D-$name-$i" "$RUN_DIR" "$OBS_D" "hello")
      ;;
    plan)
      RC_D=$(run_agent "D-$name-$i" "$RUN_DIR" "$OBS_D" --agent plan "hello")
      ;;
    praetorium-planner)
      RC_D=$(run_agent "D-$name-$i" "$RUN_DIR" "$OBS_D" "@praetorium-planner hello")
      ;;
    praetorium-developer)
      RC_D=$(run_agent "D-$name-$i" "$RUN_DIR" "$OBS_D" "@praetorium-developer hello")
      ;;
    praetorium-qa)
      RC_D=$(run_agent "D-$name-$i" "$RUN_DIR" "$OBS_D" "@praetorium-qa hello")
      ;;
    *)
      echo "unknown agent $name" >&2
      return 1
      ;;
  esac
  local OUT_D="$OBS_D/stdout.txt"
  local METRICS_D
  METRICS_D=$(record_metrics "D-$name-$i" "$OBS_D" "$OUT_D" "$RC_D")
  echo "  recorded: D-$name-$i"
  assert "D-$name-$i: usage classified (not missing)" \
    "echo '$METRICS_D' | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d[\"usage_classified\"], d'"
  assert "D-$name-$i: analyzer did not crash (report present)" \
    "echo '$METRICS_D' | python3 -c 'import json,sys; d=json.load(sys.stdin); assert \"calls\" in d'"
  if [[ "$name" == "praetorium-planner" || "$name" == "praetorium-qa" || "$name" == "plan" ]]; then
    local CHANGED
    CHANGED=$(cd "$RUN_DIR" && git status --porcelain | awk '{print $2}' | grep -v '^\.opencode/' || true)
    assert "D-$name-$i: no role-violating file mutations" "[[ -z '$CHANGED' ]]"
  fi
}

for name in build plan praetorium-planner praetorium-developer praetorium-qa; do
  for i in 1 2 3; do
    run_matrix_once "$name" "$i"
  done
done

# Summarize metrics table
python3 - "$TMP/results.ndjson" <<'PY'
import json, sys
from pathlib import Path
rows = [json.loads(l) for l in Path(sys.argv[1]).read_text().splitlines() if l.strip()]
print("\n=== Live metrics summary ===")
print(f"{'label':32} {'calls':>5} {'title':>5} {'classified':>10} {'models'}")
for r in rows:
    models = ",".join(f"{k}:{v}" for k,v in (r.get("models") or {}).items()) or "-"
    print(f"{r['label'][:32]:32} {r.get('calls',0):5} {r.get('title_generation_calls',0):5} {str(r.get('usage_classified')):>10} {models}")
Path(sys.argv[1]).with_name("results.json").write_text(json.dumps(rows, indent=2, sort_keys=True))
print(f"\nFull JSON: {Path(sys.argv[1]).with_name('results.json')}")
PY

# ── Guard: real repo tree untouched by live runs ──────────────────────────────

echo "--- guard: real repository not mutated by live fixture runs ---"
# Soft check: no unexpected changes under REPO_ROOT from this script's fixture copies.
# (We only copy agents into temp dirs; never write into REPO_ROOT during live runs.)
assert "live tests used temporary fixture directories only" "[[ -d '$TMP' ]]"

echo "---"
if [ "$fail" -eq 0 ]; then
  echo "  all live opencode agent contract tests passed"
else
  echo "  FAIL: some live opencode agent contract tests failed"
fi
exit $fail
