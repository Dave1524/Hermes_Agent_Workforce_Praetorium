#!/usr/bin/env bash
# The pointer-skill tree (T3.1). skills/ answers "which skills does this agent have for this
# workflow" — a question this box could not answer at all before it existed, because the only
# skill surface a headless run saw was ~/.claude/skills/, which is user-scope, uncommitted, and
# identical for every agent.
#
# WHY POINTERS AND NOT COPIES. The vault owns the skills; 08_skills/<name>/SKILL.md is the
# canonical text and it changes without this repo being told. A copy here would be a second
# source of truth that goes stale silently — the failure this repo has already paid for in
# AGENTS.md forks and in a runtime tree six days behind. So every SKILL.md under skills/ is a
# few lines naming the canonical path, and `pointer-not-copy` is what keeps it that way.
#
# THE THREE THINGS THAT MAKE THE TREE REACH THE RUNTIME, each of which was measured on
# claude 2.1.267 (2026-09-10) rather than assumed:
#
#   1. --plugin-dir <dir> loads ONLY <dir>/skills/<name>/SKILL.md. A skill directory at the
#      plugin root is not discovered — no warning, no error, it simply is not there. Hence
#      `skills-nested-under-skills`, which asserts the layout the CLI actually reads.
#   2. A --plugin-dir path that does not exist is SILENT: exit 0, no diagnostic, no skills. A
#      runner pointed at a typo would run every night with an empty skill set and nothing
#      anywhere would say so. Hence `runner-skills-guard`: every runner proves the plugin
#      manifest is readable before it execs, so the failure is loud and immediate.
#   3. The runners name a path in the DEPLOYED tree ($HOME/agent-workforce/skills/<owner>),
#      not this repo and not ~/.claude/skills/. What keeps the deployed copy equal to source
#      is bin/deploy shipping skills/ and bin/check_deploy_drift.sh comparing it in both
#      membership directions — `drift-covers-skills` reads that out of both scripts.
#
# SO "THE SKILL LIST THE RUNTIME SEES EQUALS THE REPO'S" IS ASSERTED AS A CHAIN, not as a
# listing. It has to be: `claude plugin details` does not accept --plugin-dir (measured — it
# is an unknown option, despite the not-found message suggesting it), so there is no
# deterministic CLI way to enumerate a session-loaded plugin's skills. The only way to get a
# live listing is to spend model tokens, and no suite in this repo does that. The chain each
# link of which IS checkable: the tree is well-formed, the runner names its owner's tree by
# explicit path, the guard makes a missing tree fatal, and drift keeps deployed == source.
#
# WHAT THIS DOES NOT ASSERT. That a skill is useful, that an agent invokes it, or that the
# vault body behind a pointer says anything in particular — the pointer's target is checked
# for EXISTENCE only, never read (vault content is out of scope for this repo by charter).
# Usage telemetry is T3.3 and the manifest join is T3.2; neither is here.
#
# FIXTURES FIRST, LIVE TREE SECOND. A suite whose only subject is a currently-healthy tree is
# a check that cannot fail. Groups 1-6 prove each lister detects its failure on synthetic
# input and stays silent on a healthy one; groups 7-11 are the verdict on the real tree.
set -uo pipefail

POINTER_MAX_LINES=20            # the longest real pointer is 9 lines; a copy is hundreds

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SKILLS_ROOT="${SKILLS_ROOT:-$REPO_ROOT/skills}"
PROFILES_DIR="${PROFILES_DIR:-$REPO_ROOT/profiles}"
VAULT_SKILLS="${VAULT_SKILLS:-$HOME/vault/08_skills}"

# shellcheck source=tests/box_precondition.sh
. "$REPO_ROOT/tests/box_precondition.sh"

fail=0

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

# --- the listers, one definition each, used on fixtures and on the live tree --------------
# Every lister prints one offender per line, so a failure names its subject and not only a
# count. All of them take the tree root as an argument for exactly that reuse.

owner_dirs() {
  local d
  for d in "$1"/*/; do
    [ -d "$d" ] || continue
    basename "$d"
  done
}

# owner<TAB>skill for every pointer in the place --plugin-dir actually reads.
tree_pairs() {
  local root=$1 owner d
  while read -r owner; do
    for d in "$root/$owner/skills"/*/; do
      [ -f "$d/SKILL.md" ] || continue
      printf '%s\t%s\n' "$owner" "$(basename "$d")"
    done
  done < <(owner_dirs "$root")
}

front_matter_name() {
  sed -n 's/^name: *//p' "$1" | head -1
}

copied_pointers() {
  local root=$1 owner skill f
  while IFS=$'\t' read -r owner skill; do
    f="$root/$owner/skills/$skill/SKILL.md"
    if [ "$(wc -l < "$f")" -gt "$POINTER_MAX_LINES" ] \
       || ! grep -qF "08_skills/$skill/SKILL.md" "$f"; then
      echo "$owner/$skill"
    fi
  done < <(tree_pairs "$root")
}

mismatched_names() {
  local root=$1 owner skill f
  while IFS=$'\t' read -r owner skill; do
    f="$root/$owner/skills/$skill/SKILL.md"
    [ "$(front_matter_name "$f")" = "$skill" ] || echo "$owner/$skill"
  done < <(tree_pairs "$root")
}

bad_plugin_manifests() {
  local root=$1 owner m
  while read -r owner; do
    m="$root/$owner/.claude-plugin/plugin.json"
    if [ ! -f "$m" ] || ! python3 -c '
import json,sys
d=json.load(open(sys.argv[1]))
sys.exit(0 if d.get("name")==f"praetorium-{sys.argv[2]}" else 1)' "$m" "$owner" 2>/dev/null; then
      echo "$owner"
    fi
  done < <(owner_dirs "$root")
}

# A SKILL.md two levels under the root is a skill the CLI silently ignores.
root_level_skills() {
  local root=$1 owner d
  while read -r owner; do
    for d in "$root/$owner"/*/; do
      [ -f "$d/SKILL.md" ] || continue
      echo "$owner/$(basename "$d")"
    done
  done < <(owner_dirs "$root")
}

# owner<TAB>skill from the README allocation table. `none` rows carry no pointer by design.
readme_pairs() {
  awk -F'|' '
    /^\|/ {
      gsub(/^[ \t]+|[ \t]+$/, "", $2); gsub(/^[ \t]+|[ \t]+$/, "", $3)
      if ($2 == "" || $2 == "owner" || $2 ~ /^-+$/) next
      if ($3 == "none") next
      n = split($3, a, ",")
      for (i = 1; i <= n; i++) {
        gsub(/[ \t`]/, "", a[i])
        if (a[i] != "") printf "%s\t%s\n", $2, a[i]
      }
    }' "$1/README.md" 2>/dev/null
}

readme_none_owners() {
  awk -F'|' '
    /^\|/ {
      gsub(/^[ \t]+|[ \t]+$/, "", $2); gsub(/^[ \t]+|[ \t]+$/, "", $3)
      if ($3 == "none" && $2 != "") print $2
    }' "$1/README.md" 2>/dev/null
}

# A pointer that duplicates a task profile owning the same surface. The two named cases are
# the ones the frozen allocation excluded on purpose: profiles/daily_plan_task.md and
# profiles/eod_summary_task.md already own Dave's day on the scheduled surface, so a
# morning-startup or eod-wrap pointer would be a second owner of one job.
profile_collisions() {
  local root=$1 prof=$2 owner skill snake
  while IFS=$'\t' read -r owner skill; do
    snake=${skill//-/_}
    [ -f "$prof/${snake}_task.md" ] && { echo "$owner/$skill"; continue; }
    case "$skill" in
      morning-startup|eod-wrap) echo "$owner/$skill" ;;
    esac
  done < <(tree_pairs "$root")
}

# owner<TAB>runner for every scheduled workflow that names a runner. Read from the manifests
# rather than from a list here, so a tenth scheduled runner joins this check by existing.
scheduled_runners() {
  python3 - "$REPO_ROOT" <<'PY'
import pathlib, sys, tomllib
root = pathlib.Path(sys.argv[1])
for manifest in sorted((root / "design" / "agents").glob("*.toml")):
    data = tomllib.loads(manifest.read_text())
    owner = data.get("name")
    for workflow in data.get("workflows", []):
        if workflow.get("surface") != "scheduled":
            continue
        runner = workflow.get("runner")
        if runner and (root / runner).is_file():
            print(f"{owner}\t{runner}")
PY
}

runners_missing_plugin_dir() {
  local base=$1 owner runner
  while IFS=$'\t' read -r owner runner; do
    if ! grep -qF -- '--plugin-dir' "$base/$runner" 2>/dev/null \
       || ! grep -qF "skills/$owner" "$base/$runner" 2>/dev/null; then
      echo "$runner"
    fi
  done
}

runners_missing_guard() {
  local base=$1 owner runner
  while IFS=$'\t' read -r owner runner; do
    : "$owner"
    grep -qE -- '-r "\$SKILLS_DIR/\.claude-plugin/plugin\.json"' "$base/$runner" 2>/dev/null \
      || echo "$runner"
  done
}

# The reverse direction: a script carrying --plugin-dir that no scheduled workflow names is
# either a runner missing from the manifests or retired residue that should offer nothing.
unjoined_plugin_dir_scripts() {
  local base=$1 joined=$2 f
  for f in "$base"/bin/*.sh; do
    [ -f "$f" ] || continue
    grep -qF -- '--plugin-dir' "$f" || continue
    grep -qxF "bin/$(basename "$f")" "$joined" || echo "bin/$(basename "$f")"
  done
}

count_lines() { grep -c . || true; }

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

make_plugin() {
  mkdir -p "$1/$2/.claude-plugin"
  printf '{"name": "praetorium-%s", "version": "0.1.0"}\n' "${3:-$2}" \
    > "$1/$2/.claude-plugin/plugin.json"
}

make_pointer() {
  local root=$1 owner=$2 skill=$3 declared=${4:-$3} target=${5:-$3}
  mkdir -p "$root/$owner/skills/$skill"
  cat > "$root/$owner/skills/$skill/SKILL.md" <<PTR
---
name: $declared
description: fixture pointer
---

Canonical source: \`08_skills/$target/SKILL.md\` in the vault.
On this box: \`~/vault/08_skills/$target/SKILL.md\`

This file is a pointer, never a copy. Read the canonical file before acting.
PTR
}

echo '--- 0. canary ---'
assert 'a found pattern is never reported as a failure' 'yes | grep -q y'

echo '--- 1. fixtures: a healthy tree trips no lister ---'
HEALTHY="$TMP/healthy"
make_plugin "$HEALTHY" alpha
make_pointer "$HEALTHY" alpha one
make_pointer "$HEALTHY" alpha two
cat > "$HEALTHY/README.md" <<'MD'
| owner | pointers |
|---|---|
| alpha | `one`, `two` |
| beta | none |
MD
assert 'the tree lists both pointers' "[ \"\$(tree_pairs '$HEALTHY' | count_lines)\" = 2 ]"
assert 'no pointer is a copy' "[ -z \"\$(copied_pointers '$HEALTHY')\" ]"
assert 'no name mismatches' "[ -z \"\$(mismatched_names '$HEALTHY')\" ]"
assert 'the plugin manifest is well-formed' "[ -z \"\$(bad_plugin_manifests '$HEALTHY')\" ]"
assert 'no skill sits at the plugin root' "[ -z \"\$(root_level_skills '$HEALTHY')\" ]"
assert 'the README table matches the tree' \
  "[ -z \"\$(comm -3 <(tree_pairs '$HEALTHY' | LC_ALL=C sort) <(readme_pairs '$HEALTHY' | LC_ALL=C sort))\" ]"
assert 'the none-row owner has no directory' \
  "[ ! -d '$HEALTHY/beta' ]"

echo '--- 2. fixtures: a pointer that became a copy, or points nowhere ---'
COPY="$TMP/copy"
make_plugin "$COPY" alpha
make_pointer "$COPY" alpha one
make_pointer "$COPY" alpha two
seq 1 40 >> "$COPY/alpha/skills/one/SKILL.md"
: > "$COPY/alpha/skills/two/SKILL.md"
printf -- '---\nname: two\n---\nno canonical path here\n' > "$COPY/alpha/skills/two/SKILL.md"
copied=$(copied_pointers "$COPY")
assert 'an over-long pointer is named' "grep -qx 'alpha/one' <<<\"\$copied\""
assert 'a pointer naming no canonical path is named' "grep -qx 'alpha/two' <<<\"\$copied\""
assert 'and both are reported, not just the first' "[ \"\$(count_lines <<<\"\$copied\")\" = 2 ]"

echo '--- 3. fixtures: a renamed pointer, and a mis-named plugin ---'
NAMES="$TMP/names"
make_plugin "$NAMES" alpha
make_pointer "$NAMES" alpha one renamed-in-front-matter
make_plugin "$NAMES" gamma gamma
printf 'not json\n' > "$NAMES/gamma/.claude-plugin/plugin.json"
make_pointer "$NAMES" gamma ok
make_plugin "$NAMES" delta wrong-name
make_pointer "$NAMES" delta ok
mkdir -p "$NAMES/epsilon/skills/ok"; cp "$NAMES/delta/skills/ok/SKILL.md" "$NAMES/epsilon/skills/ok/SKILL.md"
assert 'a front-matter name that is not the directory is named' \
  "[ \"\$(mismatched_names '$NAMES')\" = 'alpha/one' ]"
bad=$(bad_plugin_manifests "$NAMES")
assert 'a plugin.json that is not JSON is named' "grep -qx gamma <<<\"\$bad\""
assert 'a plugin.json naming another plugin is named' "grep -qx delta <<<\"\$bad\""
assert 'an owner tree with no plugin.json at all is named' "grep -qx epsilon <<<\"\$bad\""
assert 'and a well-formed one is not' "! grep -qx alpha <<<\"\$bad\""

echo '--- 4. fixtures: a skill at the plugin root, which the CLI never loads ---'
NEST="$TMP/nest"
make_plugin "$NEST" alpha
make_pointer "$NEST" alpha one
mkdir -p "$NEST/alpha/stray"
cp "$NEST/alpha/skills/one/SKILL.md" "$NEST/alpha/stray/SKILL.md"
assert 'a root-level skill directory is named' \
  "[ \"\$(root_level_skills '$NEST')\" = 'alpha/stray' ]"
assert 'and the properly nested one is not, being under skills/' \
  "! grep -q 'alpha/one' <<<\"\$(root_level_skills '$NEST')\""

echo '--- 5. fixtures: the README join, both directions ---'
JOIN="$TMP/join"
make_plugin "$JOIN" alpha
make_pointer "$JOIN" alpha one
make_pointer "$JOIN" alpha undeclared
cat > "$JOIN/README.md" <<'MD'
| owner | pointers |
|---|---|
| alpha | `one`, `documented-but-absent` |
MD
tree_only=$(comm -23 <(tree_pairs "$JOIN" | LC_ALL=C sort) <(readme_pairs "$JOIN" | LC_ALL=C sort))
readme_only=$(comm -13 <(tree_pairs "$JOIN" | LC_ALL=C sort) <(readme_pairs "$JOIN" | LC_ALL=C sort))
assert 'a pointer the table does not declare is named' "grep -q undeclared <<<\"\$tree_only\""
assert 'a table row with no pointer on disk is named' "grep -q documented-but-absent <<<\"\$readme_only\""

echo '--- 6. fixtures: profile collisions, and the runner join ---'
COLL="$TMP/coll"
make_plugin "$COLL" alpha
make_pointer "$COLL" alpha weekly-review
make_pointer "$COLL" alpha eod-wrap
make_pointer "$COLL" alpha harmless
mkdir -p "$TMP/profiles"
: > "$TMP/profiles/weekly_review_task.md"
coll=$(profile_collisions "$COLL" "$TMP/profiles")
assert 'a pointer duplicating a task profile is named' "grep -qx 'alpha/weekly-review' <<<\"\$coll\""
assert 'and the deliberately excluded eod-wrap is named' "grep -qx 'alpha/eod-wrap' <<<\"\$coll\""
assert 'while an unrelated pointer is not' "! grep -q harmless <<<\"\$coll\""

RUN="$TMP/runners"
mkdir -p "$RUN/bin"
cat > "$RUN/bin/good.sh" <<'R'
SKILLS_DIR="${PRAETORIUM_SKILLS_DIR:-$HOME/agent-workforce/skills/alpha}"
[ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || exit 1
exec claude --plugin-dir "$SKILLS_DIR"
R
cat > "$RUN/bin/noflag.sh" <<'R'
exec claude -p hi
R
cat > "$RUN/bin/wrongowner.sh" <<'R'
SKILLS_DIR="$HOME/agent-workforce/skills/beta"
[ -r "$SKILLS_DIR/.claude-plugin/plugin.json" ] || exit 1
exec claude --plugin-dir "$SKILLS_DIR"
R
cat > "$RUN/bin/noguard.sh" <<'R'
SKILLS_DIR="$HOME/agent-workforce/skills/alpha"
exec claude --plugin-dir "$SKILLS_DIR"
R
fixture_pairs=$(printf 'alpha\tbin/good.sh\nalpha\tbin/noflag.sh\nalpha\tbin/wrongowner.sh\nalpha\tbin/noguard.sh\n')
missing_pd=$(runners_missing_plugin_dir "$RUN" <<<"$fixture_pairs")
missing_guard=$(runners_missing_guard "$RUN" <<<"$fixture_pairs")
assert 'a runner with no --plugin-dir is named' "grep -qx 'bin/noflag.sh' <<<\"\$missing_pd\""
assert "a runner offering another owner's tree is named" "grep -qx 'bin/wrongowner.sh' <<<\"\$missing_pd\""
assert 'a runner with the flag and no readability guard is named' \
  "grep -qx 'bin/noguard.sh' <<<\"\$missing_guard\""
assert 'and the correct runner trips neither' \
  "! grep -q 'bin/good.sh' <<<\"\$missing_pd\$missing_guard\""
printf 'bin/good.sh\n' > "$TMP/joined"
assert 'a --plugin-dir script no scheduled workflow names is named' \
  "[ \"\$(unjoined_plugin_dir_scripts '$RUN' '$TMP/joined' | LC_ALL=C sort | tr '\n' ' ')\" = 'bin/noflag.sh bin/noguard.sh bin/wrongowner.sh ' ] || [ -n \"\$(unjoined_plugin_dir_scripts '$RUN' '$TMP/joined')\" ]"

echo "--- 7. the live tree: $SKILLS_ROOT (::pointer-not-copy) ---"
live_pairs=$(tree_pairs "$SKILLS_ROOT" | LC_ALL=C sort)
n_live=$(count_lines <<<"$live_pairs")
assert "the tree carries pointers at all (found $n_live)" "[ '$n_live' -ge 1 ]"
copied=$(copied_pointers "$SKILLS_ROOT")
assert "every pointer is under $POINTER_MAX_LINES lines and names its canonical vault path (${copied:-none} do not)" \
  "[ -z \"\$copied\" ]"

echo '--- 8. names and plugin manifests (::pointer-names-match) (::plugin-manifest-valid) (::skills-nested-under-skills) ---'
mismatched=$(mismatched_names "$SKILLS_ROOT")
assert "every pointer's front-matter name is its directory (${mismatched:-none} differ)" \
  "[ -z \"\$mismatched\" ]"
badplugins=$(bad_plugin_manifests "$SKILLS_ROOT")
assert "every owner tree is a loadable plugin named praetorium-<owner> (${badplugins:-none} are not)" \
  "[ -z \"\$badplugins\" ]"
stray=$(root_level_skills "$SKILLS_ROOT")
assert "no skill sits at a plugin root, where --plugin-dir would silently ignore it (${stray:-none} do)" \
  "[ -z \"\$stray\" ]"

echo '--- 9. the allocation table is joined to the tree (::allocation-matches-readme) (::no-profile-duplicate) ---'
readme_declared=$(readme_pairs "$SKILLS_ROOT" | LC_ALL=C sort)
n_declared=$(count_lines <<<"$readme_declared")
assert "the README table parsed ($n_declared row(s)), so an empty join cannot pass as a clean one" \
  "[ '$n_declared' -ge 1 ]"
tree_only=$(comm -23 <(printf '%s\n' "$live_pairs") <(printf '%s\n' "$readme_declared") | tr '\t' '/' | tr '\n' ' ')
readme_only=$(comm -13 <(printf '%s\n' "$live_pairs") <(printf '%s\n' "$readme_declared") | tr '\t' '/' | tr '\n' ' ')
assert "every pointer on disk is declared by the table (${tree_only:-none} are not)" "[ -z '$tree_only' ]"
assert "every row of the table exists on disk (${readme_only:-none} do not)" "[ -z '$readme_only' ]"
for none_owner in $(readme_none_owners "$SKILLS_ROOT"); do
  assert "$none_owner is declared to have no pointers and has no tree" "[ ! -d '$SKILLS_ROOT/$none_owner' ]"
done
collisions=$(profile_collisions "$SKILLS_ROOT" "$PROFILES_DIR")
assert "no pointer duplicates a task profile that owns the same surface (${collisions:-none} do)" \
  "[ -z \"\$collisions\" ]"

echo '--- 10. the runners offer the deployed tree (::runner-offers-owner-tree) (::runner-skills-guard) (::runner-join-counted) ---'
pairs=$(scheduled_runners | LC_ALL=C sort -u)
n_pairs=$(count_lines <<<"$pairs")
assert "the manifest join reached $n_pairs scheduled runner(s), so a parse that matched nothing cannot pass as clean" \
  "[ '$n_pairs' -ge 1 ]"
missing_pd=$(runners_missing_plugin_dir "$REPO_ROOT" <<<"$pairs" | LC_ALL=C sort -u | tr '\n' ' ')
missing_guard=$(runners_missing_guard "$REPO_ROOT" <<<"$pairs" | LC_ALL=C sort -u | tr '\n' ' ')
assert "every scheduled runner passes --plugin-dir at its own owner's tree (${missing_pd:-none} do not)" \
  "[ -z '$missing_pd' ]"
assert "every scheduled runner proves the plugin manifest is readable first (${missing_guard:-none} do not)" \
  "[ -z '$missing_guard' ]"
cut -f2 <<<"$pairs" | LC_ALL=C sort -u > "$TMP/joined-live"
unjoined=$(unjoined_plugin_dir_scripts "$REPO_ROOT" "$TMP/joined-live" | tr '\n' ' ')
assert "no script offers a skill tree without a scheduled workflow naming it (${unjoined:-none} do)" \
  "[ -z '$unjoined' ]"

echo '--- 11. deploy and drift cover the tree (::drift-covers-skills) ---'
# Read out of both scripts rather than restated here: a literal in this file would assert a
# path the check does not actually compare, which is the exact defect tests/test_deploy_drift.sh
# group 16b records against `systemd`.
deploy_paths=$(sed -n 's/^PATHS=(\(.*\))$/\1/p' "$REPO_ROOT/bin/deploy" | tr ' ' '\n')
content_trees=$(sed -n 's/^CONTENT_TREES="${DRIFT_CONTENT_TREES:-\(.*\)}"$/\1/p' \
  "$REPO_ROOT/bin/check_deploy_drift.sh" | tr ' ' '\n')
assert "bin/deploy's PATHS parsed ($(count_lines <<<"$deploy_paths") entries)" \
  "[ \"\$(count_lines <<<\"\$deploy_paths\")\" -ge 2 ]"
assert "check_deploy_drift.sh's CONTENT_TREES parsed ($(count_lines <<<"$content_trees") entries)" \
  "[ \"\$(count_lines <<<\"\$content_trees\")\" -ge 2 ]"
assert 'bin/deploy ships skills/ to the runtime tree' "grep -qx skills <<<\"\$deploy_paths\""
assert 'and check_deploy_drift.sh compares it as a content tree' "grep -qx skills <<<\"\$content_trees\""

echo '--- 12. every pointer names a vault skill that exists (::pointer-target-exists) ---'
if box_only_with 'the vault the pointer skills name' "$VAULT_SKILLS"; then
  # Existence only. The vault is out of scope for this repo to read; what a pointer promises
  # is that the path resolves, and that is all this checks.
  dangling=$(while IFS=$'\t' read -r _owner skill; do
    [ -f "$VAULT_SKILLS/$skill/SKILL.md" ] || echo "$skill"
  done <<<"$live_pairs" | tr '\n' ' ')
  assert "all $n_live pointer target(s) resolve under $VAULT_SKILLS (${dangling:-none} dangle)" \
    "[ -z '$dangling' ]"
else
  echo "  (skipped — see the SKIP line above)"
fi

exit $fail
