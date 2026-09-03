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

# One parse, reused. Emits: owner<TAB>unit<TAB>scope<TAB>status<TAB>kind<TAB>where<TAB>profile
#
# `kind` defaults to "timer" for the same reason `scope` defaults to "system": that is what
# every entry was before the column existed, so an unstated value must mean the old value or
# the default silently reclassifies 30 units. It is stated explicitly on the five
# buzz-agent@* entries, which are the ones it is false for.
manifest_rows() {
  python3 - "$AGENTS" <<'PY'
import tomllib, glob, os, sys
for f in sorted(glob.glob(os.path.join(sys.argv[1], '*.toml'))):
    with open(f, 'rb') as fh:
        d = tomllib.load(fh)
    owner = d['name']
    for w in d.get('workflows', []):
        print('\t'.join([owner, w['unit'], w.get('scope', 'system'),
                         w['status'], w.get('kind', 'timer'),
                         'repo' if w.get('profile_in_repo', True) else 'external',
                         w.get('profile', '')]))
PY
}

fleet_rows() { grep -v '^#' "$FLEET" | grep -v '^[[:space:]]*$'; }

echo '--- the list itself is well-formed ---'
assert 'config/fleet-units.tsv exists' "[ -f '$FLEET' ]"
assert 'design/agents/ exists' "[ -d '$AGENTS' ]"
assert 'every row has five tab-separated columns' \
  "[ \"\$(fleet_rows | awk -F'\t' 'NF!=5' | wc -l)\" -eq 0 ]"
assert 'no duplicate units' \
  "[ \"\$(fleet_rows | cut -f1 | sort | uniq -d | wc -l)\" -eq 0 ]"
assert 'scope is only system or user' \
  "[ \"\$(fleet_rows | awk -F'\t' '\$2!=\"system\" && \$2!=\"user\"' | wc -l)\" -eq 0 ]"
# The vocabulary is closed for the same reason scope's is: a consumer branches on the value,
# so a third spelling is not a new category, it is a row that every branch skips.
assert 'kind is only timer or service' \
  "[ \"\$(fleet_rows | awk -F'\t' '\$5!=\"timer\" && \$5!=\"service\"' | wc -l)\" -eq 0 ]"
assert 'at least one row of each kind, or the column is asserting nothing' \
  "[ \"\$(fleet_rows | awk -F'\t' '\$5==\"timer\"' | wc -l)\" -gt 0 ] && [ \"\$(fleet_rows | awk -F'\t' '\$5==\"service\"' | wc -l)\" -gt 0 ]"
assert 'the list is not empty (a silently empty list is the defect it replaced)' \
  "[ \"\$(fleet_rows | wc -l)\" -gt 0 ]"

echo '--- and kind is joined against the unit files, not merely spelled correctly ---'
# A closed vocabulary stops a THIRD spelling; it does not stop the WRONG one of the two. The
# column exists so the three reporting jobs never render an always-on agent as a timer that
# has never fired — and a row typed `timer` for a unit that has no timer reproduces exactly
# that defect, silently, past every assertion above.
#
# So the value is checked against the repo's own unit files. Evidence, one direction: if a
# `.timer` exists for the unit it is a timer; if only a `.service` exists it is a service.
# Templates are resolved both ways — `praetorium-phaseb-brief@` is instantiated as
# `…@2.timer`, while `buzz-agent@marcus` is served by the template `buzz-agent@.service`.
#
# A unit with NO file in this repo is /etc-only and cannot be judged here — that is the
# campaign case, and it is NAMED rather than skipped. An unexplained empty evidence set is
# how this check would stop checking.
kind_join=$(FLEET="$FLEET" REPO_ROOT="$REPO_ROOT" python3 <<'PY'
import os, pathlib
root = pathlib.Path(os.environ["REPO_ROOT"])

def evidence(d, unit):
    names = {f"{unit}.timer", f"{unit}.service"}
    if unit.endswith("@"):
        names |= {p.name for p in d.glob(f"{unit}*.timer")}
        names |= {p.name for p in d.glob(f"{unit}*.service")}
    elif "@" in unit:
        base = unit.split("@")[0] + "@"
        names |= {f"{base}.timer", f"{base}.service"}
    present = {n for n in names if (d / n).is_file()}
    return (any(n.endswith(".timer") for n in present),
            any(n.endswith(".service") for n in present))

unjudgeable = []
judged = 0
for line in pathlib.Path(os.environ["FLEET"]).read_text().splitlines():
    if line.startswith("#") or not line.strip():
        continue
    cols = line.split("\t")
    if len(cols) < 5:
        continue
    unit, scope, status, _owner, kind = cols[0], cols[1], cols[2], cols[3], cols[4]
    d = root / ("systemd/user" if scope == "user" else "systemd")
    has_timer, has_service = evidence(d, unit)
    if has_timer:
        expected = "timer"
    elif has_service:
        expected = "service"
    else:
        unjudgeable.append(f"{unit} ({status})")
        continue
    judged += 1
    if expected != kind:
        print(f"{unit}: declared kind={kind}, {d} says {expected}")
# A join that reached nothing passes every comparison it never made. Pointed at the wrong
# root — the failure mode this block had itself, reading an unexported REPO_ROOT and falling
# back to cwd — every unit lands in `unjudgeable` and the check reports clean.
if judged == 0:
    print(f"the kind join judged ZERO rows against {root}/systemd — it is looking in the wrong place, not finding agreement")
if unjudgeable:
    print("NOTE no unit file in this repo, so kind is unjudged here:", ", ".join(sorted(unjudgeable)))
PY
)
assert 'no row declares a kind its unit files contradict' \
  "[ -z \"\$(printf '%s\n' \"\$kind_join\" | grep -v '^NOTE' | grep -v '^\$')\" ] || { printf '      %s\n' \"\$kind_join\"; false; }"
# Printed unconditionally: the units this join cannot reach are the ones a future mistake
# would hide in.
printf '%s\n' "$kind_join" | grep '^NOTE' | sed 's/^/  info: /'

echo '--- the list equals the manifests, in BOTH directions ---'
# LC_ALL=C on BOTH sorts, because `comm` compares bytes and `sort` does not. Under
# en_US.UTF-8 punctuation is weighted differently in the first pass, so a locale-sorted
# input makes comm walk past lines it should have matched — and it reports that as a
# difference in whichever direction it drifted, never as an error. The five buzz-agent@*
# rows put an `@` in the key for the first time, which is exactly the character class that
# makes the two collations disagree.
mrows=$(manifest_rows | awk -F'\t' '{print $2"\t"$3"\t"$4"\t"$1"\t"$5}' | LC_ALL=C sort)
frows=$(fleet_rows | LC_ALL=C sort)
assert 'every manifest workflow appears in the list with the same scope/status/owner/kind' \
  "[ -z \"\$(comm -23 <(printf '%s\n' \"\$mrows\") <(printf '%s\n' \"\$frows\"))\" ]"
assert 'the list declares no unit the manifests do not' \
  "[ -z \"\$(comm -13 <(printf '%s\n' \"\$mrows\") <(printf '%s\n' \"\$frows\"))\" ]"

echo '--- every profile-carrying workflow names its owner on line 1 ---'
while IFS=$'\t' read -r owner unit scope status kind where profile; do
  [ -n "$profile" ] || continue
  # `Owner: <persona>` on line 1 is a convention of the profiles THIS REPO OWNS. The five
  # S1 charters live at ~/.config/buzz-agents/<name>.prompt, which is deny-listed — this
  # repo cannot read them, so it cannot assert a header in them and must not pretend to.
  #
  # The escape is DECLARED, never inferred. `profile_in_repo = false` in the manifest is
  # what routes an entry here; a heuristic on the path's shape would also swallow a typo'd
  # repo path and turn a real missing profile into a silent pass. What is asserted instead
  # is that the declaration is honest: an external profile must not resolve inside the repo.
  if [ "$where" = external ]; then
    # $profile reaches assert(), which evals its argument. Interpolating a manifest value
    # into a single-quoted test expression makes a value containing a quote — say
    # `dave's.prompt` — terminate the quoting and run as code. Every other field in this
    # loop is treated as data; this one goes through a function so it stays data too.
    _outside_repo() { [ ! -e "$REPO_ROOT/$1" ]; }
    assert "$unit: profile declared external and is in fact outside this repo" \
      "_outside_repo \"\$profile\""
    echo "  ok: $unit: owner header not assertable (external profile: $profile)"
    continue
  fi
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

echo '--- W4: the job-override examples have exactly one home ---'
# The invariant is a filesystem fact, not a prose fact. config/job-overrides/ holds a README
# and archive/ only; the live templates are profiles/*.env.example. Asserted this way round
# because the failure mode was an INSTRUCTION that stayed authoritative-looking after its
# target moved: docs/runbook.md carried `install -m 600 config/job-overrides/augustus-content.env.example`
# for a path that had existed only under archive/ since 2026-09-01.
assert 'config/job-overrides/ holds no top-level *.env.example' \
  "[ \"\$(find '$REPO_ROOT/config/job-overrides' -maxdepth 1 -name '*.env.example' | wc -l)\" -eq 0 ]"
assert 'the live examples are in profiles/ (at least the nine live jobs)' \
  "[ \"\$(find '$REPO_ROOT/profiles' -maxdepth 1 -name '*.env.example' | wc -l)\" -ge 9 ]"
# Commands, not prose. A sentence explaining where templates USED to live is a correct
# record; an `install` line pointing there is a broken instruction. Only the latter fails.
assert 'no install command sources a template from config/job-overrides/' \
  "! grep -rhE '^[[:space:]]*install[[:space:]].*config/job-overrides/' '$REPO_ROOT/docs' '$REPO_ROOT/config' | grep -q ."
# Every install command in the docs must name a path that exists, or a <job> placeholder.
while IFS= read -r line; do
  src=$(printf '%s' "$line" | awk '{for(i=1;i<=NF;i++) if ($i ~ /\.env\.example$/) {print $i; exit}}')
  [ -n "$src" ] || continue
  case "$src" in *"<job>"*) continue ;; esac
  assert "install command names an existing template: $src" "[ -f '$REPO_ROOT/'\"$src\" ]"
done < <(grep -rhE '^[[:space:]]*install[[:space:]]' "$REPO_ROOT/docs" "$REPO_ROOT/config" 2>/dev/null)

exit $fail
