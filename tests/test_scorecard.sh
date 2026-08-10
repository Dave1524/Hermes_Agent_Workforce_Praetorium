#!/usr/bin/env bash
# Test for bin/scorecard.sh (NUC-23) — mocked rollup, no git side effects, no network.
# All scenarios set SCORECARD_PUSH=0 and a nonexistent worktree so nothing is pushed.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/scorecard.sh"
TD="$(mktemp -d)"

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

sc() {
  local cost=$1 approvals=$2 digest=$3
  SCORECARD_PUSH=0 SCORECARD_WORKTREE="$TD/nonexistent" SCORECARD_LOCK="$TD/lock" \
    SCORECARD_COST_LOG="$cost" SCORECARD_APPROVALS="$approvals" \
    SCORECARD_METRICS_DIR="$(dirname "$digest")" SCORECARD_DIGEST="$digest" \
    bash "$SCRIPT" >/dev/null 2>&1
  echo $?
}

# Fixture: 5 schema=2 records (2 PROPOSAL, 1 NOPROPOSAL, 1 FAIL, 1 VIOLATION) +
# 1 legacy outcome=OK line + 1 pure-garbage line + 1 malformed run_seconds line.
c1="$TD/cost1.log"; d1="$TD/digest1.md"
cat > "$c1" <<'EOF'
ts=2026-07-08T10:00:00+00:00 schema=2 profile=claudius model=anthropic/claude-haiku-4.5 task=standing outcome=PROPOSAL proposal=alpha run_seconds=300 attempts=1 tokens=unknown cost_usd=unknown cost_src=openrouter-dashboard memory=recorded
ts=2026-07-08T10:05:00+00:00 schema=2 profile=claudius model=anthropic/claude-haiku-4.5 task=standing outcome=PROPOSAL proposal=beta run_seconds=200 attempts=1 tokens=unknown cost_usd=unknown cost_src=openrouter-dashboard memory=recorded
ts=2026-07-08T10:10:00+00:00 schema=2 profile=claudius model=x task=standing outcome=NOPROPOSAL proposal=none run_seconds=100 attempts=1 tokens=unknown cost_usd=unknown cost_src=openrouter-dashboard memory=fallback
ts=2026-07-08T10:15:00+00:00 schema=2 profile=claudius model=x task=standing outcome=FAIL proposal=none run_seconds=60 attempts=3 tokens=unknown cost_usd=unknown cost_src=openrouter-dashboard memory=na
ts=2026-07-08T10:20:00+00:00 schema=2 profile=claudius model=x task=standing outcome=VIOLATION proposal=none run_seconds=40 attempts=1 tokens=unknown cost_usd=unknown cost_src=openrouter-dashboard memory=na
2026-07-06T09:00:00+00:00 run_seconds=380 attempts=1 outcome=OK model=anthropic/claude-sonnet-5
this is pure garbage not a record at all
ts=2026-07-08T11:00:00+00:00 schema=2 profile=claudius model=x task=standing outcome=PROPOSAL proposal=gamma run_seconds=notanumber attempts=1
EOF

echo "--- scenario 1: rollup math ---"
rc=$(sc "$c1" "$TD/none.tsv" "$d1")
assert "exits 0" "[ '$rc' = 0 ]"
assert "all-time runs = 6" "grep -q '| Agent runs (all-time) | 6 |' '$d1'"
assert "proposals = 2" "grep -q '| Proposals produced | 2 |' '$d1'"
assert "proposal rate 33% (2/6)" "grep -q 'Proposal rate | 33% (2/6)' '$d1'"
assert "error runs 2 (1 fail / 1 violation)" "grep -q 'Error runs (fail/violation) | 2 (1 fail / 1 violation)' '$d1'"
assert "no-proposal = 1" "grep -q '| No-proposal runs | 1 |' '$d1'"
assert "avg duration 180s" "grep -q '| Avg run duration | 180s |' '$d1'"
assert "inference 100% remote" "grep -q '0% local / 100% remote' '$d1'"
assert "cost best-effort unknown" "grep -q 'best-effort: unknown' '$d1'"
assert "approvals pending" "grep -q 'pending (awaiting Mac sync)' '$d1'"
assert "legacy note" "grep -q '1 pre-NUC-23 record' '$d1'"

echo "--- scenario 2: empty cost.log ---"
c2="$TD/cost2.log"; d2="$TD/digest2.md"; : > "$c2"
rc=$(sc "$c2" "$TD/none.tsv" "$d2")
assert "exits 0" "[ '$rc' = 0 ]"
assert "digest exists" "[ -f '$d2' ]"
assert "runs = 0" "grep -q '| Agent runs (all-time) | 0 |' '$d2'"
assert "proposal rate n/a" "grep -q '| Proposal rate | n/a |' '$d2'"

echo "--- scenario 3: all-garbage input ---"
c3="$TD/cost3.log"; d3="$TD/digest3.md"
printf 'garbage line one\nnot a record either\n' > "$c3"
rc=$(sc "$c3" "$TD/none.tsv" "$d3")
assert "exits 0 (no crash)" "[ '$rc' = 0 ]"
assert "runs = 0" "grep -q '| Agent runs (all-time) | 0 |' '$d3'"

echo "--- scenario 4: approvals present (incl. an edited decision) ---"
# NUC-23 bug fix (2026-08-10): 'Approval rate' used to compute promoted/decisions, which
# silently treated decision=edited (a used proposal, applied with Mac-side changes) as if
# it were a rejection. This fixture pins that: with 2 promoted / 1 rejected / 1 edited,
# clean-promote is 50% (2/4) but acceptance — what was actually used — is 75% (3/4). A
# regression that reverts to the old single-field formula fails this scenario, not just
# scenario 4's old 0-edited case which the buggy formula also happened to get "right".
c4="$TD/cost4.log"; d4="$TD/digest4.md"; a4="$TD/appr4.tsv"
cp "$c1" "$c4"
cat > "$a4" <<'EOF'
ts=2026-07-08T12:00:00+00:00 slug=alpha decision=promoted
ts=2026-07-08T12:01:00+00:00 slug=beta decision=promoted
ts=2026-07-08T12:02:00+00:00 slug=gamma decision=rejected
ts=2026-07-08T12:03:00+00:00 slug=delta decision=edited
EOF
rc=$(sc "$c4" "$a4" "$d4")
assert "exits 0" "[ '$rc' = 0 ]"
assert "approvals cell 2 / 1 / 1" "grep -q 'Approvals promoted / rejected / edited | 2 / 1 / 1' '$d4'"
assert "acceptance rate 75% (promoted+edited)" "grep -q 'Acceptance rate (promoted+edited / decisions) | 75%' '$d4'"
assert "clean-promote rate 50% (promoted only)" "grep -q 'Clean-promote rate (promoted / decisions) | 50%' '$d4'"

echo "--- scenario 5: idempotency ---"
d5a="$TD/digest5a.md"; d5b="$TD/digest5b.md"
sc "$c1" "$TD/none.tsv" "$d5a" >/dev/null
sc "$c1" "$TD/none.tsv" "$d5b" >/dev/null
assert "two runs byte-identical" "cmp -s '$d5a' '$d5b'"

echo "--- scenario 6: 7-day window ---"
c6="$TD/cost6.log"; d6="$TD/digest6.md"
now=$(date -Is); old=$(date -Is -d '30 days ago')
{
  echo "ts=$now schema=2 profile=claudius model=x task=standing outcome=PROPOSAL proposal=r1 run_seconds=100 attempts=1"
  echo "ts=$now schema=2 profile=claudius model=x task=standing outcome=NOPROPOSAL proposal=none run_seconds=50 attempts=1"
  echo "ts=$old schema=2 profile=claudius model=x task=standing outcome=PROPOSAL proposal=r0 run_seconds=70 attempts=1"
} > "$c6"
rc=$(sc "$c6" "$TD/none.tsv" "$d6")
assert "exits 0" "[ '$rc' = 0 ]"
assert "last 7d = 2" "grep -q '| Agent runs (last 7d) | 2 |' '$d6'"
assert "all-time = 3" "grep -q '| Agent runs (all-time) | 3 |' '$d6'"

echo "--- scenario 7: BLOCKED/DEDUP excluded from runs, own rows (NUC-37/38) ---"
c7="$TD/cost7.log"; d7="$TD/digest7.md"
cat > "$c7" <<'EOF'
ts=2026-07-13T10:00:00+00:00 schema=3 profile=claudius model=x task=standing outcome=PROPOSAL proposal=a run_seconds=100 attempts=1
ts=2026-07-13T10:05:00+00:00 schema=3 profile=claudius model=x task=standing outcome=NOPROPOSAL proposal=none run_seconds=80 attempts=1
ts=2026-07-13T10:10:00+00:00 schema=3 profile=unknown model=unknown task=standing outcome=BLOCKED proposal=none run_seconds=0 attempts=0
ts=2026-07-13T10:11:00+00:00 schema=3 profile=claudius model=x task=standing outcome=BLOCKED proposal=none run_seconds=0 attempts=0
ts=2026-07-13T10:12:00+00:00 schema=3 profile=claudius model=x task=standing outcome=DEDUP proposal=none run_seconds=1 attempts=1
EOF
rc=$(sc "$c7" "$TD/none.tsv" "$d7")
assert "exits 0" "[ '$rc' = 0 ]"
assert "runs = 2 (BLOCKED/DEDUP excluded)" "grep -q '| Agent runs (all-time) | 2 |' '$d7'"
assert "proposals = 1" "grep -q '| Proposals produced | 1 |' '$d7'"
assert "proposal rate 50% (1/2), denominator excludes blocked/dedup" "grep -q 'Proposal rate | 50% (1/2)' '$d7'"
assert "blocked runs row = 2" "grep -q '| Blocked runs (preflight/health gate) | 2 |' '$d7'"
assert "dedup dispatches row = 1" "grep -q '| Deduplicated dispatches (idempotent) | 1 |' '$d7'"
assert "avg duration 90s (blocked/dedup seconds excluded)" "grep -q '| Avg run duration | 90s |' '$d7'"

echo "--- scenario 8: OPS runs counted, excluded from proposal rate (NUC-36) ---"
c8="$TD/cost8.log"; d8="$TD/digest8.md"
cat > "$c8" <<'EOF'
ts=2026-07-13T10:00:00+00:00 schema=3 profile=claudius model=x task=standing outcome=PROPOSAL proposal=a run_seconds=100 attempts=1
ts=2026-07-13T10:05:00+00:00 schema=3 profile=claudius model=x task=overnight-morning-report outcome=OPS proposal=none run_seconds=50 attempts=1
ts=2026-07-13T10:06:00+00:00 schema=3 profile=claudius model=x task=overnight-morning-report outcome=OPS proposal=none run_seconds=40 attempts=1
EOF
rc=$(sc "$c8" "$TD/none.tsv" "$d8")
assert "exits 0" "[ '$rc' = 0 ]"
assert "runs = 3 (OPS included in all-time)" "grep -q '| Agent runs (all-time) | 3 |' '$d8'"
assert "ops runs row = 2" "grep -q '| Ops runs (non-proposal, NUC-36) | 2 |' '$d8'"
assert "proposal rate 100% (1/1), OPS excluded from denom" "grep -q 'Proposal rate | 100% (1/1)' '$d8'"
assert "avg duration 63s (includes OPS seconds)" "grep -q '| Avg run duration | 63s |' '$d8'"

exit $fail
