#!/usr/bin/env bash
# Ownership gate for W2 (owner headers) and W3 (the fleet unit list).
#
# Two facts about every workflow are declared in design/agents/<persona>.toml and
# materialised somewhere a deployed process can read:
#
#   * WHO OWNS IT.  Each [[workflows]] entry carrying a `profile` names a prompt file
#     whose first line must read `Owner: <persona>`, where <persona> is the manifest that
#     DECLARES the entry. The direction is the whole point. Deriving an owner from prompt
#     prose gets profiles/weekly_pre_assembly_cc_task.md wrong — it says "NOT
#     hermes/claudius on OpenRouter" while design/agents/marcus.toml declares it — and the
#     two files either side of it in the same directory make the same mistake look right.
#
#   * WHICH UNITS THE REPORTING JOBS COVER.  config/fleet-units.tsv is the manifests'
#     projection into a tree bin/deploy actually ships. design/ is NOT deployed, so a
#     runtime read of the manifests works in the repo and silently empties in
#     ~/agent-workforce/. This suite is what keeps the projection honest, in both
#     directions: neither the manifests nor the list may drift alone.
#
# The denominator is DERIVED here, never written down. "9 of 19" was recorded on
# 2026-09-01 and could not be reproduced a day later, because 19 never named its set.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FLEET="$REPO_ROOT/config/fleet-units.tsv"
AGENTS="$REPO_ROOT/design/agents"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match,
# so whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that
# was found — failing a true assertion, and silently passing a negated one. It is scoped
# off here rather than per-condition so a later `| grep -q` cannot reintroduce it.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

if ! python3 -c 'import tomllib' 2>/dev/null; then
  echo "SKIP: tomllib unavailable (needs Python 3.11+)"
  exit 77
fi

# One parse, reused. Emits: owner<TAB>unit<TAB>scope<TAB>status<TAB>profile
manifest_rows() {
  python3 - "$AGENTS" <<'PY'
import tomllib, glob, os, sys
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.toml'))):
    with open(f, 'rb') as fh:
        d = tomllib.load(fh)
    owner = d['name']
    for w in d.get('workflows', []):
        print('\t'.join([owner, w['unit'], w.get('scope', 'system'),
                         w['status'], w.get('profile', '')]))
PY
}

fleet_rows() { grep -v '^#' "$FLEET" | grep -v '^[[:space:]]*$'; }

echo '--- the list itself is well-formed ---'
assert 'config/fleet-units.tsv exists' "[ -f '$FLEET' ]"
assert 'design/agents/ exists' "[ -d '$AGENTS' ]"
assert 'every row has four tab-separated columns' \
  "[ \"\$(fleet_rows | awk -F'\t' 'NF!=4' | wc -l)\" -eq 0 ]"
assert 'no duplicate units' \
  "[ \"\$(fleet_rows | cut -f1 | sort | uniq -d | wc -l)\" -eq 0 ]"
assert 'scope is only system or user' \
  "[ \"\$(fleet_rows | awk -F'\t' '\$2!=\"system\" && \$2!=\"user\"' | wc -l)\" -eq 0 ]"
assert 'the list is not empty (a silently empty list is the defect it replaced)' \
  "[ \"\$(fleet_rows | wc -l)\" -gt 0 ]"

echo '--- the list equals the manifests, in BOTH directions ---'
mrows=$(manifest_rows | awk -F'\t' '{print $2"\t"$3"\t"$4"\t"$1}' | sort)
frows=$(fleet_rows | sort)
assert 'every manifest workflow appears in the list with the same scope/status/owner' \
  "[ -z \"\$(comm -23 <(printf '%s\n' \"\$mrows\") <(printf '%s\n' \"\$frows\"))\" ]"
assert 'the list declares no unit the manifests do not' \
  "[ -z \"\$(comm -13 <(printf '%s\n' \"\$mrows\") <(printf '%s\n' \"\$frows\"))\" ]"

echo '--- every profile-carrying workflow names its owner on line 1 ---'
while IFS=$'\t' read -r owner unit scope status profile; do
  [ -n "$profile" ] || continue
  f="$REPO_ROOT/$profile"
  assert "$unit: profile exists ($profile)" "[ -f '$f' ]"
  [ -f "$f" ] || continue
  assert "$unit: line 1 declares Owner: $owner" \
    "[ \"\$(head -1 '$f' | sed -n 's/^Owner: \\([A-Za-z0-9_-]*\\).*/\\1/p')\" = '$owner' ]"
  # The owner header is canonical, but the prose below it is what a reader sees first.
  # A "You are <persona>" naming anyone else is drift that the header alone cannot catch.
  others=$(ls "$AGENTS" | sed 's/\.toml$//' | grep -vx "$owner" || true)
  for p in $others; do
    assert "$unit: no prose claims 'You are ${p^}'" \
      "! grep -qiE 'You are (the )?${p}\b' '$f'"
  done
done < <(manifest_rows)

echo '--- the reporting consumers read the list rather than a glob of their own ---'
for c in bin/praetorium-status.sh bin/overnight_pre_snapshot.sh bin/local_tier_eval.sh \
         profiles/daily_plan_task.md profiles/eod_summary_task.md \
         profiles/overnight_morning_report_cc_task.md; do
  assert "$c names config/fleet-units.tsv" \
    "grep -q 'fleet-units.tsv' '$REPO_ROOT/$c'"
done

echo '--- the artifact lives where bin/deploy can ship it ---'
# design/ is not in bin/deploy's list, so a consumer reading the manifests directly works
# in the repo and empties in the runtime. This is the assertion that stops that regression.
assert 'bin/deploy ships the config/ tree' \
  "grep -qE '^[^#]*\bconfig\b' '$REPO_ROOT/bin/deploy'"
assert 'bin/deploy does NOT ship design/ (so nothing may read it at run time)' \
  "! grep -qE '^[^#]*DEPLOY_PATHS=.*\bdesign\b' '$REPO_ROOT/bin/deploy'"

exit $fail
