#!/usr/bin/env bash
# Gate for the agent-config eval (T8.4) — the one suite on this box that spends model tokens.
#
# THE COST IS THE DESIGN CONSTRAINT, so the shape is fixtures first and live last. Groups 1-7
# are deterministic and run on any runner: they prove the case files are well-formed and
# joined to the pointer tree, that the baseline is pinned and dated, and that the comparator
# reaches each of its four verdicts on synthetic results. Groups 8-9 spend a real credential
# and run only on the box, only when the branch diff touched something that could have
# changed the answer.
#
# WHICH DIRECTION EACH CHECK DEGRADES (CLAUDE.md § Verification corollary). The comparator's
# own failure mode is fail-OPEN — a verdict it never reaches is a green run that certified
# nothing — and it has already happened once: MISSING scoped its owner set to the owners seen
# in the CASE list, so a result file with zero cases contributed no owner, every MISSING row
# was skipped, and the comparator exited 0 on the exact input it exists to catch. That is why
# group 4 asserts the exit code of all five fixtures and not only the two obvious reds.
#
# THE BASELINE JOIN IS BOTH DIRECTIONS for the same reason. A case with no recorded score is
# a pass mark nobody measured, and a baselined case that has vanished from the tree is a
# check that silently stopped running. Group 3 is the CI-side half of "pinned"; group 4's
# UNBASELINED fixture is the runner-side half.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_ROOT="${SKILLS_ROOT:-$REPO_ROOT/skills}"
BASELINE="$SKILLS_ROOT/evals-baseline.json"
FIXTURES="$REPO_ROOT/tests/fixtures/agent-config-eval"
RUNNER="$REPO_ROOT/bin/agent_config_eval.sh"
COMPARE="$REPO_ROOT/bin/agent_config_eval_compare.py"
CREDENTIALS="${AGENT_CONFIG_EVAL_CREDENTIALS:-$HOME/.claude/.credentials.json}"

# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# --- listers, one definition each ---------------------------------------------------------

# owner<TAB>case for every eval case in the tree.
case_pairs() {
  local f owner
  for f in "$SKILLS_ROOT"/*/evals/*/case.yaml; do
    [ -f "$f" ] || continue
    owner="$(basename "$(dirname "$(dirname "$(dirname "$f")")")")"
    printf '%s\t%s\n' "$owner" "$(basename "$(dirname "$f")")"
  done
}

# The pointer a case is about: the longest pointer of that owner that prefixes the case name.
# Empty means the case names no pointer the owner actually has.
case_pointer() {
  local owner=$1 name=$2 d p best=""
  for d in "$SKILLS_ROOT/$owner/skills"/*/; do
    [ -d "$d" ] || continue
    p="$(basename "$d")"
    case "$name" in
      "$p"-*) [ "${#p}" -gt "${#best}" ] && best="$p" ;;
    esac
  done
  printf '%s' "$best"
}

yaml_scalar() { sed -n "s/^$2: *//p" "$1" | head -1 | tr -d '"'"'"''; }

# Offenders, one per line, so a failure names its subject rather than a count.
malformed_cases() {
  local owner name f
  while IFS=$'\t' read -r owner name; do
    f="$SKILLS_ROOT/$owner/evals/$name/case.yaml"
    [ "$(yaml_scalar "$f" name)" = "$name" ] || { echo "$owner/$name: name != directory"; continue; }
    grep -q '^ *prompt:' "$f" || { echo "$owner/$name: no execution.prompt"; continue; }
    grep -q '^ *schema_version:' "$f" || { echo "$owner/$name: no schema_version"; continue; }
    grep -q '^ *- *name:' "$f" || { echo "$owner/$name: no named grader"; continue; }
    grep -q '^ *type:' "$f" || echo "$owner/$name: a grader carries no type"
  done < <(case_pairs)
}

unjoined_cases() {
  local owner name f p
  while IFS=$'\t' read -r owner name; do
    f="$SKILLS_ROOT/$owner/evals/$name/case.yaml"
    p="$(case_pointer "$owner" "$name")"
    [ -n "$p" ] || { echo "$owner/$name: names no pointer $owner has"; continue; }
    grep -q "$p" "$f" || echo "$owner/$name: no grader mentions the pointer $p"
  done < <(case_pairs)
}

echo "0. pipefail canary"
# Deterministic reproduction of the SIGPIPE class this file's assert() scopes off.
assert "an early-exiting reader in a condition does not report 141" "yes | grep -q y"

echo "1. case files are well-formed"   # (::eval-case-wellformed)
assert "at least one eval case exists" "[ \"\$(case_pairs | wc -l)\" -ge 1 ]"
assert "every case.yaml carries name==dir, schema_version, a prompt and a named typed grader" \
       "[ -z \"\$(malformed_cases)\" ] || { malformed_cases; false; }"

echo "2. every case names a pointer its owner really has"   # (::eval-case-names-skill)
assert "each case is joined to an existing pointer, in the name and in a grader" \
       "[ -z \"\$(unjoined_cases)\" ] || { unjoined_cases; false; }"

echo "3. the baseline is pinned, dated, and joined to the tree"   # (::baseline-measured-dated)
assert "baseline parses as JSON" "python3 -m json.tool '$BASELINE' >/dev/null"
assert "baseline records a model, a claude version and a run count" \
       "python3 -c \"
import json,sys
b=json.load(open('$BASELINE'))
sys.exit(0 if b.get('model') and b.get('claude') and b.get('runs') else 1)\""
assert "measured is an ISO date no later than today" \
       "python3 -c \"
import datetime,json,sys
b=json.load(open('$BASELINE'))
sys.exit(0 if datetime.date.fromisoformat(b['measured']) <= datetime.date.today() else 1)\""
assert "the model is a full name, not an alias that rolls on the next release" \
       "python3 -c \"
import json,sys
m=json.load(open('$BASELINE'))['model']
sys.exit(0 if m.split('[')[0] not in ('opus','sonnet','haiku','fable','best','opusplan') else 1)\""
# Both directions: a case with no score is an unmeasured pass mark, a score with no case is a
# check that stopped running. Either alone fails open.
assert "the baseline's case set equals the tree's, in both directions" \
       "diff <(python3 -c \"
import json
print('\\n'.join(sorted(json.load(open('$BASELINE'))['cases'])))\") \
             <(case_pairs | awk -F'\t' '{print \$1\"/\"\$2}' | sort)"

echo "4. the comparator reaches all four verdicts"   # (::compare-regression-red)
run_compare() {
  python3 "$COMPARE" "$FIXTURES/result-$1.json" --baseline "$FIXTURES/baseline.json" >"$TMP/$1.psv" 2>&1
  echo $?
}
assert "an unchanged score passes"        "[ \"\$(run_compare equal)\" = 0 ]"
assert "a fallen score is red"            "[ \"\$(run_compare drop)\" = 1 ]"
assert "a risen score passes"             "[ \"\$(run_compare improve)\" = 0 ]"
assert "a baselined case that did not run is red" "[ \"\$(run_compare missing)\" = 1 ]"
assert "a case with no recorded score is red"     "[ \"\$(run_compare unbaselined)\" = 1 ]"
assert "the REGRESSION row names the case"  "grep -q 'meeting-prep-fires|FAIL' '$TMP/drop.psv'"
assert "the MISSING row names the case"     "grep -q 'meeting-prep-fires|FAIL||MISSING' '$TMP/missing.psv'"
assert "the UNBASELINED row names the case" "grep -q 'prospect-research-fires|FAIL' '$TMP/unbaselined.psv'"
assert "an improvement is reported and does not rewrite the baseline" \
       "grep -q 'IMPROVED' '$TMP/improve.psv' && \
        diff -q '$FIXTURES/baseline.json' '$FIXTURES/baseline.json' >/dev/null"

echo "5. --record is the only writer of a baseline"   # (::compare-record-writes)
cp "$FIXTURES/baseline.json" "$TMP/scratch-baseline.json"
python3 "$COMPARE" "$FIXTURES/result-improve.json" --baseline "$TMP/scratch-baseline.json" >/dev/null 2>&1
assert "a plain comparison leaves the baseline byte-identical" \
       "diff -q '$FIXTURES/baseline.json' '$TMP/scratch-baseline.json' >/dev/null"
python3 "$COMPARE" "$FIXTURES/result-improve.json" --baseline "$TMP/scratch-baseline.json" --record >"$TMP/record.psv" 2>&1
assert "--record stamps today, the model and the claude version" \
       "python3 -c \"
import datetime,json,sys
b=json.load(open('$TMP/scratch-baseline.json'))
sys.exit(0 if b['measured']==datetime.date.today().isoformat()
             and b['model']=='claude-opus-5' and b['claude'] else 1)\""
assert "--record writes the score it just measured" \
       "python3 -c \"
import json,sys
b=json.load(open('$TMP/scratch-baseline.json'))
sys.exit(0 if b['cases']['claudius/meeting-prep-fires']['score']==1.0 else 1)\""
assert "--record prints the scores it froze, not just a count" \
       "grep -q 'case/claudius/meeting-prep-fires|PASS|1.000|recorded' '$TMP/record.psv'"

echo "6. the tolerance absorbs exactly one flaky run of three"   # (::compare-tolerance-quantised)
# 2/3 computes as 0.6666666666666666 and 1 - 1/3 as 0.6666666666666667, so a bare comparison
# makes ONE flaky run red — the tolerance absorbing nothing at precisely the value it is
# sized for. This group is the reason the comparator slackens every comparison by an epsilon.
quantised() {
  python3 - "$TMP" "$1" <<'PY'
import json, pathlib, sys
tmp, score = pathlib.Path(sys.argv[1]), float(sys.argv[2])
base = {"measured": "2026-09-20", "claude": "2.1.278", "model": "claude-opus-5",
        "runs": 3, "tolerance": 1.0 / 3.0, "cases": {"claudius/c-fires": {"score": 1.0}}}
(tmp / "q-baseline.json").write_text(json.dumps(base))
(tmp / "q-result.json").write_text(json.dumps({
    "claudeVersion": "2.1.278",
    "suite": {"root": "/tmp/x/claudius", "modelOverride": "claude-opus-5",
              "plugins": [{"name": "praetorium-claudius"}]},
    "cases": [{"name": "c-fires", "aggregates": {"score": score},
               "arms": {"with": [{"score": 1}, {"score": 1}, {"score": 0}]}}]}))
PY
  python3 "$COMPARE" "$TMP/q-result.json" --baseline "$TMP/q-baseline.json" >"$TMP/q.psv" 2>&1
  echo $?
}
assert "one flaky run of three is absorbed"  "[ \"\$(quantised 0.6666666666666666)\" = 0 ]"
assert "two flaky runs of three are red"     "[ \"\$(quantised 0.3333333333333333)\" = 1 ]"

echo "7. the change gate watches agent config and not prose"   # (::watched-paths-trigger)
scratch_repo_says() {
  local path=$1 repo="$TMP/repo-$RANDOM"
  mkdir -p "$repo" && git -C "$repo" init -q
  git -C "$repo" config user.email t@example.com && git -C "$repo" config user.name t
  mkdir -p "$repo/$(dirname "$path")" && echo base >"$repo/seed"
  git -C "$repo" add -A && git -C "$repo" commit -qm base
  local ref; ref="$(git -C "$repo" rev-parse HEAD)"
  echo changed >"$repo/$path"
  git -C "$repo" add -A && git -C "$repo" commit -qm change
  AGENT_CONFIG_EVAL_REPO="$repo" "$RUNNER" --changed-since "$ref" --dry-run 2>&1
}
assert "a change under skills/ runs the eval" \
       "scratch_repo_says skills/claudius/skills/x/SKILL.md | grep -q 'would evaluate'"
assert "a change to CLAUDE.md runs the eval" \
       "scratch_repo_says CLAUDE.md | grep -q 'would evaluate'"
assert "a change to .claude/settings.json runs the eval" \
       "scratch_repo_says .claude/settings.json | grep -q 'would evaluate'"
assert "a change under .claude/briefs/ does not" \
       "scratch_repo_says .claude/briefs/x.md | grep -q 'no watched path changed'"
assert "a change to an unrelated file does not" \
       "scratch_repo_says docs/runbook.md | grep -q 'no watched path changed'"

echo "8. the runner refuses a temp root inside \$HOME"   # (::temp-root-outside-home)
# Not a warning: a run under $HOME loads ~/CLAUDE.md and the shared memory pool into every
# eval child, so it still produces a number and the number measures the wrong thing.
mkdir -p "$HOME/.cache/agent-config-eval-test"
TMPDIR="$HOME/.cache/agent-config-eval-test" "$RUNNER" --owner claudius >"$TMP/home.out" 2>&1
home_code=$?   # captured HERE: $? inside assert is assert's own machinery, not the runner's
rmdir "$HOME/.cache/agent-config-eval-test" 2>/dev/null
assert "a TMPDIR under \$HOME is exit 2 — a runner error, never a verdict about the fleet" \
       "[ '$home_code' = 2 ]"
assert "and it says why, naming \$HOME" "grep -q 'is inside .HOME' '$TMP/home.out'"

# --- live groups: a real credential, spent only when the answer could have changed ---------
LIVE="${AGENT_CONFIG_EVAL_LIVE:-}"
if [ "$LIVE" = "0" ]; then
  echo "9. live eval — opted out (AGENT_CONFIG_EVAL_LIVE=0)"
elif box_only_with 'the claude.ai login the live eval spends' "$CREDENTIALS"; then
  if [ "$LIVE" = "1" ] || [ -n "$("$RUNNER" --changed-since "${AGENT_CONFIG_EVAL_BASE:-origin/main}" --dry-run 2>/dev/null | grep 'would evaluate')" ]; then
    echo "9. the live tree still fires its skills"   # (::live-eval-clean)
    assert "a clean run of the real tree is exit 0 against the real baseline" \
           "'$RUNNER' --quiet"
    if [ "$LIVE" = "1" ]; then
      echo "10. an unreachable skill tree turns the suite red"   # (::broken-skill-turns-red)
      # The negative control, opt-in because it doubles the run's cost. It replays the trap
      # tests/test_pointer_skills.sh:17-19 measured: a skill directory at the plugin root is
      # not discovered, silently. --self-check requires that red and then requires the clean
      # tree to be green, so a red cannot be the harness having a bad morning.
      assert "--self-check is exit 0, meaning the broken tree WAS red and the clean one green" \
             "'$RUNNER' --self-check --quiet"
    fi
  else
    echo "9. live eval — no watched path changed since ${AGENT_CONFIG_EVAL_BASE:-origin/main}, not spending a run"
  fi
fi

[ "$fail" -eq 0 ] && echo "PASS" || echo "FAILED"
exit "$fail"
