#!/usr/bin/env bash
# agent_config_eval.sh — after an agent-config change, do the skills still FIRE?
#
# usage: agent_config_eval.sh [--owner <name>]... [--runs N] [--changed-since <ref>]
#                            [--dry-run] [--record] [--self-check] [--deliver] [--quiet]
#
# THE GAP THIS FILLS. Every other gate in this repo is deterministic, and
# tests/test_pointer_skills.sh:29-34 says so out loud: "no suite in this repo spends model
# tokens", so the pointer tree is asserted as a CHAIN — the tree is well-formed, each runner
# names its owner's tree by explicit path, the guard makes a missing tree fatal, drift keeps
# deployed equal to source. Every link is checkable and the thing the chain exists to produce
# is not. T3.3 then measured the consequence: 48 runs, skills_offered= three per owner every
# time, invoked ZERO times, for three days after the cause (paraphrased descriptions that
# dropped the vault's "Use when …" triggers) had already been fixed. Nothing here could have
# said so. This runner is the one suite that spends model tokens, and that is its whole point.
#
# REGRESSION, NOT ABSOLUTE — the same rationale as bin/fleet_eval.sh:13-20. A score is only
# meaningful against the score measured when the case was added. An absolute pass mark on a
# model's behaviour goes red for reasons nobody chose (a model rollout, a harness change) and
# a suite that goes red for reasons nobody chose gets muted within a week.
#
# THREE THINGS MEASURED RATHER THAN ASSUMED, all on 2026-09-22, claude 2.1.278:
#
#   1. --ablation none IS REQUIRED FOR A SCORE. Under the default `with-without`, graders
#      marked with-only — and `tool_used: Skill` is one — become a plugin-fired INDICATOR and
#      are not part of the score ("withOnly": true, "scored": false in the JSON). The whole
#      verdict here is a tool_used grader, so the default mode would score nothing. It also
#      halves the cost: one arm, not two.
#   2. THE EVAL RUNS ON A COPY, OUTSIDE $HOME. The tool writes <plugin>/evals/results/, and
#      agent-workforce-auto-sync.timer would commit that into origin/main within 15 minutes.
#      And the eval child's cwd is the scaffold's: under $HOME it loads ~/CLAUDE.md (46 KB)
#      and the shared memory pool into EVERY run, so the eval would measure Dave's machine
#      instructions instead of the pointer descriptions under test — expensively, and while
#      reporting a number that looks the same either way.
#   3. THE MODEL IS PINNED TO A FULL NAME. `opus` silently rolls forward on the next model
#      release and takes the baseline with it (the standing-research convention,
#      bin/run_standing_research_cc.sh:36). claude-opus-5 is what 7 of the 9 scheduled
#      runners run, including every job that loads claudius's tree.
#
# EXIT CODE IS THE PRODUCT, like fleet_eval: 0 = no regression, 1 = something moved backwards
# and the scorecard names it, 2 = this runner could not run at all (bad flag, no credential,
# a temp root inside $HOME). 2 is never a verdict about the fleet.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$BIN_DIR/.." && pwd)"
# Source checkout when run from one, the deployed tree under the timer. Both carry skills/
# and config/ (bin/deploy:20 ships both), which is why --self-check works in either.
SKILLS_ROOT="${AGENT_CONFIG_EVAL_SKILLS:-$ROOT/skills}"
BASELINE="${AGENT_CONFIG_EVAL_BASELINE:-$SKILLS_ROOT/evals-baseline.json}"
MODEL="${AGENT_CONFIG_EVAL_MODEL:-claude-opus-5}"
CONCURRENCY="${AGENT_CONFIG_EVAL_CONCURRENCY:-4}"
# Only used to answer --changed-since, so a scratch repo can be pointed at it in a test.
REPO="${AGENT_CONFIG_EVAL_REPO:-$ROOT}"
LOG_ROOT="${AGENT_CONFIG_EVAL_LOG_ROOT:-$HOME/logs/agent-config-eval}"
LOCK="${AGENT_CONFIG_EVAL_LOCK:-/tmp/agent_config_eval.lock}"
COMPARE="$BIN_DIR/agent_config_eval_compare.py"
DELIVER="$BIN_DIR/deliver.sh"

OWNERS=()
RUNS=""
CHANGED_SINCE=""
DRY_RUN=0
RECORD=0
SELF_CHECK=0
DELIVER_ON_REGRESSION=0
QUIET=0

while [ $# -gt 0 ]; do
  case "$1" in
    --owner)          OWNERS+=("${2:-}"); shift 2 ;;
    --runs)           RUNS="${2:-}"; shift 2 ;;
    --changed-since)  CHANGED_SINCE="${2:-}"; shift 2 ;;
    --dry-run)        DRY_RUN=1; shift ;;
    --record)         RECORD=1; shift ;;
    --self-check)     SELF_CHECK=1; shift ;;
    --deliver)        DELIVER_ON_REGRESSION=1; shift ;;
    --quiet)          QUIET=1; shift ;;
    -h|--help)        sed -n '2,6p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "agent_config_eval: unrecognized argument: $1" >&2; exit 2 ;;
  esac
done

say() { [ "$QUIET" -eq 1 ] || echo "$@"; }

# --- the change gate -------------------------------------------------------------------
# THE WATCHED SET IS THE AGENT'S CONFIG, not the repo. A change to any of these can stop a
# skill firing without changing a line of the skill: the pointer descriptions themselves
# (skills/), the instruction layer every session loads (CLAUDE.md), what the harness is
# allowed to do (.claude/settings.json, .claude/hooks/) and the user-scope skill surface
# (.claude/skills/). .claude/briefs/ is deliberately NOT watched — a brief is prose about
# work, and watching it would spend a model run on every planning commit.
watched_changed() {
  local ref=$1 f
  while IFS= read -r f; do
    case "$f" in
      skills/*|CLAUDE.md|.claude/settings.json|.claude/hooks/*|.claude/skills/*) echo "$f" ;;
    esac
  done < <(git -C "$REPO" diff --name-only "$ref...HEAD" 2>/dev/null)
}

if [ -n "$CHANGED_SINCE" ]; then
  hits="$(watched_changed "$CHANGED_SINCE")"
  if [ -z "$hits" ]; then
    echo "no watched path changed"
    exit 0
  fi
  say "watched paths changed since $CHANGED_SINCE:"
  say "$hits" | sed 's/^/  /'
  # A CHANGE UNDER ONE OWNER'S TREE IS SCORED AGAINST THAT OWNER. Every other watched path —
  # CLAUDE.md, the settings deny, the hooks, the user skill surface — is shared by all of
  # them, so any hit outside skills/<owner>/ widens it back to the whole tree. This is the
  # difference between a ~$1 gate and a ~$4 one on a branch that touched one pointer, and it
  # narrows only what a run MEASURES: the comparator scopes MISSING to the owners present in
  # the results, so a partial run is honest rather than quiet. An explicit --owner wins.
  if [ ${#OWNERS[@]} -eq 0 ]; then
    changed_owners="$(printf '%s\n' "$hits" | sed -n 's|^skills/\([^/]*\)/.*|\1|p' | sort -u)"
    if [ -n "$changed_owners" ] && [ "$(printf '%s\n' "$hits" | grep -cv '^skills/')" -eq 0 ]; then
      mapfile -t OWNERS < <(printf '%s\n' "$changed_owners")
      say "scoped to the owners whose trees changed: ${OWNERS[*]}"
    fi
  fi
fi

# --- preconditions ---------------------------------------------------------------------
command -v claude >/dev/null 2>&1 || {
  echo "agent_config_eval: claude is not on PATH — nothing to evaluate" >&2; exit 2; }
[ -f "$COMPARE" ] || {
  echo "agent_config_eval: comparator missing: $COMPARE" >&2; exit 2; }
[ -d "$SKILLS_ROOT" ] || {
  echo "agent_config_eval: no skills tree at $SKILLS_ROOT" >&2; exit 2; }

# owner<newline> for every owner that actually carries a case. An owner with none is not an
# omission — aurelian has a plugin manifest and no pointers by allocation.
owners_with_cases() {
  local f
  for f in "$SKILLS_ROOT"/*/evals/*/case.yaml; do
    [ -f "$f" ] || continue
    basename "$(dirname "$(dirname "$(dirname "$f")")")"
  done | sort -u
}

if [ ${#OWNERS[@]} -eq 0 ]; then
  mapfile -t OWNERS < <(owners_with_cases)
fi
if [ ${#OWNERS[@]} -eq 0 ]; then
  echo "agent_config_eval: no eval cases under $SKILLS_ROOT/*/evals/" >&2
  exit 2
fi

if [ "$DRY_RUN" -eq 1 ]; then
  echo "would evaluate: ${OWNERS[*]}"
  exit 0
fi

# Non-blocking, like fleet_eval: every case run is a full `claude` child on the same login as
# five Buzz agents and nine runners, so two overlapping suites are a rate-limit collision and
# not extra information.
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "agent_config_eval: another run holds $LOCK — skipping" >&2
  exit 0
fi

TMPROOT="$(mktemp -d "${TMPDIR:-/tmp}/agent-config-eval.XXXXXX")" || exit 2
# See note 2 in the header. This is the check that keeps the measurement honest, so it is a
# refusal and not a warning — a run under $HOME produces a number, and the number is wrong.
case "$(readlink -f "$TMPROOT")/" in
  "$HOME"/*)
    echo "agent_config_eval: temp root $TMPROOT is inside \$HOME — every eval child would" >&2
    echo "                   load ~/CLAUDE.md and the shared memory pool. Unset TMPDIR." >&2
    rm -rf "$TMPROOT"; exit 2 ;;
esac
trap 'rm -rf "$TMPROOT"' EXIT

STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
RUN_TS="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
WORKDIR="$LOG_ROOT/$STAMP"
mkdir -p "$WORKDIR"
SCORECARD="$WORKDIR/scorecard.md"
# Delivered from inside this ExecStart rather than through an ExecStartPost adapter, so it
# stamps its own run marker — without one the scorecard travels anchor=none and a run that
# died before writing would ship the previous verdict under today's subject line
# (bin/fleet_eval.sh:66-70).
MARKER="$WORKDIR/started"
: >"$MARKER"

# --- one owner, one eval, one result file -----------------------------------------------
# $1 = owner, $2 = plugin source dir, $3 = label used for the result filename, $4 = optional
# case-name glob, which the negative control uses to buy its red with one case instead of all.
eval_tree() {
  local owner=$1 src=$2 label=$3 only=${4:-} work="$TMPROOT/$3" out="$TMPROOT/$3.json"
  cp -r "$src" "$work" || return 2
  rm -rf "$work/evals/results"
  # -j 4 and not 8: every run is a full `claude` child on the same claude.ai login the five
  # buzz-agent@* units and the nine scheduled runners share, so the ceiling here is that rate
  # limit rather than this box. Results and the report keep case order whatever it is set to.
  local args=(. --trust-plugin --no-publish --ablation none --threshold 0 -j "$CONCURRENCY"
              --model "$MODEL" --json "$out")
  [ -n "$RUNS" ] && args+=(--runs "$RUNS")
  [ -n "$only" ] && args+=(--case "$only")
  ( cd "$work" && claude plugin eval "${args[@]}" ) >"$TMPROOT/$label.log" 2>&1
  if [ ! -s "$out" ]; then
    echo "agent_config_eval: $owner produced no result JSON:" >&2
    tail -5 "$TMPROOT/$label.log" >&2
    return 2
  fi
  echo "$out"
}

RESULTS=()
for owner in "${OWNERS[@]}"; do
  [ -d "$SKILLS_ROOT/$owner" ] || { echo "agent_config_eval: no such owner: $owner" >&2; exit 2; }
  say "evaluating $owner …"
  out="$(eval_tree "$owner" "$SKILLS_ROOT/$owner" "$owner")" || exit 2
  RESULTS+=("$out")
  # The raw JSON outlives TMPROOT here or nowhere: it carries costUsd, turns and the trace
  # path per run, which is everything a red row cannot tell you and the one moment they can
  # still be read. The scorecard's `Full run:` line points at this directory.
  cp "$out" "$WORKDIR/$owner.json" 2>/dev/null || true
done

compare_args=(--baseline "$BASELINE")
[ "$RECORD" -eq 1 ] && compare_args+=(--record)
python3 "$COMPARE" "${RESULTS[@]}" "${compare_args[@]}" >"$WORKDIR/results.psv" 2>"$WORKDIR/compare.err"
COMPARE_CODE=$?
if [ ! -s "$WORKDIR/results.psv" ]; then
  echo "agent_config_eval: comparator produced no rows (exit $COMPARE_CODE):" >&2
  cat "$WORKDIR/compare.err" >&2
  exit 2
fi

# --- the negative control ----------------------------------------------------------------
# A behavioural gate that has never been seen to fail has proven nothing. --self-check
# re-runs the first owner with every skill directory moved from <plugin>/skills/<name>/ to
# <plugin>/<name>/ and requires the suite to go RED.
#
# THAT MUTATION IS NOT ARBITRARY — it is the exact trap tests/test_pointer_skills.sh:17-19
# measured on claude 2.1.267: a skill directory at a plugin root is not discovered, with no
# warning and no error, and the plugin-dir flag pointed at a path that does not exist is
# silent too (exit 0, no diagnostic, no skills). Every file is still present and readable;
# the loader simply does not see them.
#
# That flag is named in words and never written as a literal anywhere in this file, and this
# sentence is why. tests/test_pointer_skills.sh:223-230 greps every bin/*.sh for it and calls
# any match that no scheduled workflow claims either a runner missing from the manifests or
# retired residue — it reads comments too, so a prose mention turns this script into a false
# positive. This runner EVALUATES a skill tree; it never offers one to a model. Same class of
# editing trap as the parenthesised assert ids in design/fleet-suites.toml, resolved the same
# way. It is the failure mode on this box that a deterministic gate can only reach
# by proxy, so it is the right thing for the one suite that spends model tokens to prove it
# can catch.
#
# WHAT WAS TRIED FIRST, AND WHY IT IS NOT THE CONTROL. The brief specified the real T3.3
# incident — claudius's meeting-prep pointer carrying its pre-400e7ef description, "Prepare
# for a meeting from what the vault already knows.", with the vault's "Use when Dave says
# 'prep for meeting with [company/person]'" triggers dropped. MEASURED 2026-09-22 on
# claude-opus-5, it does not reproduce: the paraphrased description scored 1.000 over three
# runs, and a second prompt written to avoid the word "meeting" ("I've got a call with … on
# Thursday. Get me ready for it.") scored 1.000 over two runs against BOTH descriptions. For
# a skill whose NAME already matches the request, the description is not what decides. See
# skills/README.md for what that does and does not say about T3.3.
#
# IT BUYS ITS RED WITH ONE CASE, NOT ONE OWNER. The control is the same whichever `-fires`
# case carries it, and every owner now holds four or five, so running the whole tree broken
# would spend four times the runs for the same one-bit answer. It is compared against a
# baseline filtered to exactly the case it ran: against the whole file, the owner's other
# baselined cases come back MISSING and the run is red for a reason that is not the one this
# control exists to prove — a broken tree that still fired would pass on the MISSING rows
# alone. Filtered, the only thing that can make it red is the score.
SELF_CHECK_STATUS=""
if [ "$SELF_CHECK" -eq 1 ]; then
  sc_owner="${OWNERS[0]}"
  sc_case="$(ls -d "$SKILLS_ROOT/$sc_owner"/evals/*-fires 2>/dev/null | head -1)"
  sc_case="$(basename "${sc_case:-}")"
  [ -n "$sc_case" ] && [ "$sc_case" != "." ] || {
    echo "agent_config_eval: $sc_owner has no *-fires case to run the control on" >&2; exit 2; }
  say "self-check: evaluating $sc_owner/$sc_case with its skills where the loader cannot see them …"
  cp -r "$SKILLS_ROOT/$sc_owner" "$TMPROOT/broken-src" || exit 2
  rm -rf "$TMPROOT/broken-src/evals/results"
  for d in "$TMPROOT/broken-src/skills"/*/; do
    [ -d "$d" ] || continue
    mv "$d" "$TMPROOT/broken-src/$(basename "$d")" || exit 2
  done
  broken="$(eval_tree "$sc_owner" "$TMPROOT/broken-src" broken "$sc_case")" || exit 2
  cp "$broken" "$WORKDIR/self-check.json" 2>/dev/null || true
  sc_baseline="$TMPROOT/self-check-baseline.json"
  python3 - "$BASELINE" "$sc_owner/$sc_case" >"$sc_baseline" <<'PY' || exit 2
import json, pathlib, sys
b = json.loads(pathlib.Path(sys.argv[1]).read_text())
b["cases"] = {k: v for k, v in (b.get("cases") or {}).items() if k == sys.argv[2]}
json.dump(b, sys.stdout)
PY
  if python3 "$COMPARE" "$broken" --baseline "$sc_baseline" >"$WORKDIR/self-check.psv" 2>&1; then
    SELF_CHECK_STATUS="FAIL"
    echo "agent_config_eval: SELF-CHECK FAILED — $sc_owner/$sc_case scored clean with no skill" >&2
    echo "                   the loader can reach, so this suite cannot see a silent empty tree." >&2
    cat "$WORKDIR/self-check.psv" >&2
  elif ! grep -q "^case/$sc_owner/$sc_case|FAIL" "$WORKDIR/self-check.psv"; then
    SELF_CHECK_STATUS="FAIL"
    echo "agent_config_eval: SELF-CHECK FAILED — red, but not on $sc_owner/$sc_case." >&2
    cat "$WORKDIR/self-check.psv" >&2
  else
    SELF_CHECK_STATUS="PASS"
    say "self-check: an unreachable skill tree turns the suite red, as designed."
  fi
fi

count_status() { grep -c "^[^|]*|$1|" "$WORKDIR/results.psv" || true; }
FAILS=$(count_status FAIL)
WARNS=$(count_status WARN)
PASSES=$(count_status PASS)
[ "$SELF_CHECK_STATUS" = "FAIL" ] && FAILS=$((FAILS + 1))

verdict="no regression"
[ "$FAILS" -gt 0 ] && verdict="REGRESSION"

{
  echo "# Agent-config eval — $RUN_TS"
  echo
  echo "**$verdict** — $PASSES pass, $WARNS warn, $FAILS fail."
  echo
  echo "Owners: ${OWNERS[*]} · model \`$MODEL\` · baseline \`$BASELINE\`"
  [ -n "$SELF_CHECK_STATUS" ] && echo "Negative control (skills where the loader cannot see them): **$SELF_CHECK_STATUS**"
  echo
  echo "| check | status | value | detail |"
  echo "|---|---|---|---|"
  while IFS='|' read -r check status value detail; do
    printf '| %s | %s | %s | %s |\n' "$check" "$status" "$value" "${detail//|/\\|}"
  done <"$WORKDIR/results.psv"
  echo
  echo "A case verdict is scored against the baseline recorded in \`skills/evals-baseline.json\`,"
  echo "so FAIL means *worse than when the case was added* — not that the score is below some"
  echo "absolute mark. An IMPROVED row leaves the baseline alone: re-recording it is a"
  echo "deliberate commit, never something a scheduled job does to its own pass mark."
  echo
  echo "Full run: \`$WORKDIR\`"
} >"$SCORECARD"

[ "$QUIET" -eq 1 ] || cat "$SCORECARD"

if [ "$DELIVER_ON_REGRESSION" -eq 1 ] && [ "$FAILS" -gt 0 ]; then
  "$DELIVER" --job agent-config-eval.service --route ops \
    --subject "[Praetorium] Agent-config eval — regression ($FAILS)" \
    --file "$SCORECARD" --run-marker "$MARKER" --runtime none --artifact-type report \
    --target none --operation none --risk-tier review \
    --acceptance-check "every FAIL row is either fixed or its baseline score is deliberately re-recorded"
fi

[ "$FAILS" -gt 0 ] && exit 1
exit 0
