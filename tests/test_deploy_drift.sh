#!/usr/bin/env bash
# Suite for bin/check_deploy_drift.sh — one assertion per drift class, each proven by
# CONSTRUCTING that class in a fixture.
#
# THE SUITE TESTS THE CHECKER, NOT THE BOX. Every tree is built under $TMPDIR and the script
# is pointed at it with DRIFT_* overrides. A suite that asserted "the live box is clean"
# would be red for reasons having nothing to do with the code under test, and every future
# implementer would learn to ignore it — and it could not run in CI at all, where no runtime
# tree, no /etc units and no --user tree exist. The live verdict is what the verify.sh and
# bin/deploy callers produce on a real run: reported, not manufactured.
#
# Corollary, and it is a rule rather than a convenience: a drift class is never proven by
# damaging the live box. No unit is removed from /etc, no live unit edited, no timer stopped,
# no source unit `git rm`ed "to watch it go red".
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO="$(pwd)"
CHECK="$REPO/bin/check_deploy_drift.sh"

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one. Scoped off here
# rather than per-condition so a later `| grep -q` cannot reintroduce it.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

fail=0

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# --- fixture plumbing ------------------------------------------------------------------

fixture() {
  root=$(mktemp -d)
  mkdir -p "$root"/{src_bin,run_bin,src_sys,etc,src_user,user,src_buzz,buzz}
  # Every comparison needs a non-empty source side, or the checker reports the empty glob
  # instead of the class under test. D1's first measurement globbed a path that did not
  # exist and returned a clean 0 for every connector; the checker refuses to repeat it.
  echo 'shared' > "$root/src_bin/keep.sh"
  echo 'shared' > "$root/run_bin/keep.sh"
  echo '[Unit]' > "$root/src_sys/shared.service"
  echo '[Unit]' > "$root/etc/shared.service"
  printf '' > "$root/ownership.toml"
  mkdir -p "$root/manifests"
  printf '' > "$root/manifests/none.toml"
  # The fifth tree gets a synthetic pair like every other. Leaving it unset would point the
  # buzz comparison at the REAL repo tree and the REAL ~/.config/buzz-team — the live box,
  # which this suite's header forbids as a comparison side and which would make every
  # `clean` assertion below depend on fleet state.
  echo 'rules' > "$root/src_buzz/shared.toml"
  echo 'rules' > "$root/buzz/shared.toml"
  # The seven content trees bin/deploy ships. Every existing assertion in this suite calls
  # clean(), so leaving these pointed at the real repo would make every one of them depend on
  # the live runtime's prune backlog — the exact fleet-state dependency this fixture exists to
  # avoid. Two trees and one single-file tree is enough to exercise all three directions.
  mkdir -p "$root/src_content/profiles" "$root/run_content/profiles" \
           "$root/src_content/config/job-overrides" "$root/run_content/config/job-overrides"
  echo 'task' > "$root/src_content/profiles/live_task.md"
  echo 'task' > "$root/run_content/profiles/live_task.md"
  # A NESTED file, on both sides. It is also what keeps config/ non-empty: the checker
  # refuses a source tree that matched no files, so an empty fixture tree is a finding in
  # every scenario rather than a neutral background.
  echo 'env' > "$root/src_content/config/job-overrides/live.env.example"
  echo 'env' > "$root/run_content/config/job-overrides/live.env.example"
  echo 'note' > "$root/src_content/NOTE.md"
  echo 'note' > "$root/run_content/NOTE.md"
  # systemd/ is a content tree TOO, and that is the whole of W17. It has two destinations:
  # /etc (compared above, by the unit half) and $RUNTIME_ROOT/systemd/, the staging copy
  # bin/deploy actually writes. Pointed at the real repo this pair would depend on the live
  # prune backlog like the others; built here it does not.
  mkdir -p "$root/src_content/systemd" "$root/run_content/systemd"
  echo '[Unit]' > "$root/src_content/systemd/staged.service"
  echo '[Unit]' > "$root/run_content/systemd/staged.service"
  : > "$root/exclusions.toml"
  # ONE owner for the content-tree half of the fixture env. Four call sites need it — drift()
  # and the three inline invocations that each override a single other var — and it was four
  # copies of the same literal until W17, which is the shape this suite exists to catch one
  # tree over. Passed through `env` because an expanded array word is a command word, not an
  # assignment: bash recognises `NAME=value` prefixes at parse time, before expansion.
  CONTENT_ENV=(
    "DRIFT_SRC_ROOT=$root/src_content"
    "AGENT_WORKFORCE_RUNTIME=$root/run_content"
    'DRIFT_CONTENT_TREES=profiles config NOTE.md systemd'
    "DRIFT_EXCLUSIONS=$root/exclusions.toml"
  )
  cat > "$root/src_buzz/MANIFEST.toml" <<'TOML'
[[adopted]]
path = "shared.toml"
why  = "fixture"
[[excluded]]
path = "PROSE.md"
why  = "fixture prose"
TOML
}

drift() { # runs the checker against the current fixture; extra env comes from the caller
  DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
  DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
  DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
  DRIFT_SRC_BUZZ="$root/src_buzz" DRIFT_BUZZ="$root/buzz" \
  DRIFT_BUZZ_MANIFEST="$root/src_buzz/MANIFEST.toml" \
  DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
  env "${CONTENT_ENV[@]}" \
  DRIFT_NOW="${NOW_FIXTURE:-2026-09-02 12:00:00}" \
  bash "$CHECK" 2>&1
}

# `drift` exits non-zero by design, so its status must never reach a pipeline the assert
# then reads. Captured into a variable first, every time.
out=''
capture() { out=$(drift); }
saw()     { grep -q "$1" <<<"$out"; }
clean()   { ! grep -q '^  DRIFT' <<<"$out"; }

echo "--- 1. content drift, both trees ---"
fixture
echo 'changed' > "$root/run_bin/keep.sh"
echo '[Unit]x' > "$root/etc/shared.service"
capture
assert 'a bin/ file whose bytes differ is named' "saw 'DRIFT \[bin\] content differs: keep.sh'"
assert 'a unit whose bytes differ is named' "saw 'DRIFT \[system\] content differs: shared.service'"
rm -rf "$root"

echo "--- 2. source-only: the repo says it runs, the box does not have it ---"
fixture
echo '[Unit]' > "$root/src_sys/only-in-repo.timer"
capture
assert 'a source-only unit is red' "saw 'DRIFT \[system\] source-only: only-in-repo.timer'"
rm -rf "$root"

echo "--- 3. etc-only and OURS: the class that loses fleet-turn-check ---"
fixture
echo '[Unit]' > "$root/etc/hand-installed.timer"
capture
assert 'an /etc unit with no source is red — a rebuild from source loses it' \
  "saw 'DRIFT \[system\] etc-only: hand-installed.timer'"
rm -rf "$root"

echo "--- 4. etc-only and third-party: declared, therefore silent ---"
fixture
echo '[Unit]' > "$root/etc/ollama.service"
cat > "$root/ownership.toml" <<'TOML'
[[third_party]]
unit = "ollama.service"
why  = "installer-owned"
TOML
capture
assert 'a declared third-party unit produces no finding' "clean"
assert 'and is still reported by name, not silently skipped' "saw 'declared third-party'"
rm -rf "$root"

echo "--- 5. etc-only and UNDECLARED: fails closed ---"
fixture
echo '[Unit]' > "$root/etc/mystery.service"
cat > "$root/ownership.toml" <<'TOML'
[[third_party]]
unit = "something-else.service"
why  = "not this one"
TOML
capture
assert 'an undeclared /etc unit is red, never ignored' \
  "saw 'DRIFT \[system\] etc-only: mystery.service'"
rm -rf "$root"

echo "--- 6. dated exclusion: live silences, EXPIRED does not ---"
fixture
echo '[Unit]' > "$root/etc/campaign-job.timer"
cat > "$root/manifests/augustus.toml" <<'TOML'
[[workflows]]
unit    = "campaign-job"
status  = "campaign"
expires = "2026-09-04 01:30"
TOML
NOW_FIXTURE='2026-09-02 12:00:00' capture
assert 'a campaign exclusion whose date is ahead silences the difference' "clean"
assert 'and names the date it is relying on' "saw 'excluded until 2026-09-04 01:30'"
NOW_FIXTURE='2026-09-05 00:00:00' capture
assert 'the SAME exclusion one day past its date is red' \
  "saw 'DRIFT \[system\] etc-only: campaign-job.timer — its campaign exclusion EXPIRED'"
rm -rf "$root"

echo "--- 7. the user tree ---"
fixture
echo '[Unit]' > "$root/user/buzz-agent@.service"
capture
assert 'a --user unit with no source here is red' \
  "saw 'DRIFT \[user\] live-only: buzz-agent@.service'"
echo '[Unit]' > "$root/src_user/buzz-agent@.service"
capture
assert 'giving it a source clears the finding' "clean"
echo '[Unit]edited' > "$root/user/buzz-agent@.service"
capture
assert 'and an edit to the live copy is then caught' \
  "saw 'DRIFT \[user\] content differs: buzz-agent@.service'"
rm -rf "$root"

echo "--- 7b. the credential drop-ins are declared, and absent from git ---"
# Three PATHS, two FILES: nekovri-subsidy-watchdog.service.d/auth.conf is a symlink to
# buzz-agent@trajan.service.d/auth.conf. `grep -rl` does not follow symlinks during
# recursion and reports two, so any scan that enumerates these must dereference or it
# certifies a path it never read.
tracked=$(git -C "$REPO" ls-files)
declared=$(python3 - <<'PY'
import pathlib, tomllib
rows = tomllib.loads(pathlib.Path("design/unit-ownership.toml").read_text())
for r in rows.get("never_commit", []):
    print(r["path"])
PY
)
assert 'all three credential paths are declared never-commit' \
  "[ \"\$(wc -l <<<\"\$declared\")\" -eq 3 ]"
not_tracked() {
  local p
  while IFS= read -r p; do
    [ -n "$p" ] || continue
    grep -qxF "${p#\~/}" <<<"$tracked" && return 1
    grep -qF "$(basename "$(dirname "$p")")/$(basename "$p")" <<<"$tracked" && return 1
  done <<<"$declared"
  return 0
}
assert 'none of them is tracked by git' "not_tracked"
assert 'and no auth.conf reached this repo by any path' \
  "! git -C '$REPO' ls-files | grep -q 'auth\.conf$'"

echo "--- 8. drop-in *.d/*.conf ---"
fixture
mkdir -p "$root/src_sys/qmd-mcp.service.d" "$root/etc/qmd-mcp.service.d"
echo 'a' > "$root/src_sys/qmd-mcp.service.d/gpu.conf"
echo 'b' > "$root/etc/qmd-mcp.service.d/gpu.conf"
capture
assert 'a drop-in whose bytes differ is red — it silently overrides its unit' \
  "saw 'DRIFT \[dropin\] content differs: qmd-mcp.service.d/gpu.conf'"
echo 'a' > "$root/etc/qmd-mcp.service.d/gpu.conf"
mkdir -p "$root/etc/ollama.service.d"
echo 'x' > "$root/etc/ollama.service.d/vulkan.conf"
cat > "$root/ownership.toml" <<'TOML'
[[third_party]]
unit = "ollama.service"
why  = "installer-owned"
TOML
capture
assert "a third-party unit's drop-in dir is covered by its declaration" "clean"
rm -rf "$root"

echo "--- 9. ignored classes stay ignored ---"
fixture
echo 'junk' > "$root/run_bin/agent_propose.sh.bak-20260901"
mkdir -p "$root/run_bin/__pycache__"
echo 'junk' > "$root/run_bin/__pycache__/mod.cpython-312.pyc"
capture
assert '*.bak-* in the runtime tree is not drift' "clean"
assert '__pycache__ is not drift' "! saw '__pycache__'"
rm -rf "$root"

echo "--- 9b. an empty source glob is refused, not reported clean ---"
fixture
rm -f "$root/src_bin/keep.sh"
capture
assert 'a source tree that matched nothing cannot yield a clean verdict' \
  "saw 'matched no files'"
rm -rf "$root"

echo "--- 10. the three callers are wired ---"
assert 'bin/verify.sh calls the drift check' \
  "grep -q 'check_deploy_drift.sh' '$REPO/bin/verify.sh'"
assert 'bin/deploy calls it as a post-condition' \
  "grep -q 'check_deploy_drift.sh' '$REPO/bin/deploy'"
assert 'the timer unit exists in systemd/' \
  "[ -f '$REPO/systemd/agent-drift-check.timer' ]"
assert 'the service unit exists in systemd/' \
  "[ -f '$REPO/systemd/agent-drift-check.service' ]"
# The ExecStart is resolved against the SOURCE tree, not the runtime one. Asserting the
# runtime copy would make this suite depend on whether bin/deploy has run — box state, which
# CI does not have — and runtime existence is already the drift check's own job: it reports
# an undeployed script as `source-only`, which is the correct owner of that question.
# The SOURCE repo, not the runtime tree — this is the one job that must not run from the
# deployed copy of itself (see the unit's header and group 11).
execstart=$(sed -n 's|^ExecStart=/home/dave/dev/agent-workforce/||p' "$REPO/systemd/agent-drift-check.service")
assert 'the timer runs the checker from the SOURCE repo, never the runtime copy' \
  "! grep -q '^ExecStart=/home/dave/agent-workforce/' '$REPO/systemd/agent-drift-check.service'"
assert 'its ExecStart names a script that exists in this repo' \
  "[ -n '$execstart' ] && [ -f '$REPO/$execstart' ]"
# RETARGETED 2026-09-02 (W3), not relaxed. The invariant is unchanged — this timer must be
# visible to the reports, because a drift checker nothing reports on is a checker that can
# die unnoticed. What moved is where visibility is decided: it used to be six hand-written
# lists and globs, so this asserted against two of them by name; it is now one declared list.
# Asserting the old shape after the shape changed is how a check starts certifying nothing.
assert 'the timer is in the fleet unit list, or no report can see it' \
  "awk -F'\t' '!/^#/ && \$1==\"agent-drift-check\" && \$2==\"system\" && \$3==\"standing\"' '$REPO/config/fleet-units.tsv' | grep -q ."
# Two consumption sites in praetorium-status.sh, not one, and the distinction is the point:
# the is-active loop is the only one that can report a timer as ABSENT, while list-timers
# cannot — it never prints a unit systemd has not loaded. Both must be fed by the list.
# That the OTHER five consumers read the list is asserted once, in tests/test_fleet_ownership.sh;
# re-asserting it here would be a second copy of the fact this list exists to remove.
# RESPELLED 2026-09-03 (brief 7), not relaxed. The accessor gained a `kind` argument and a
# refusing wrapper, so `fleet_units system` no longer appears anywhere and the old assertion
# went red on a correct script — the same failure mode the W3 note above describes, one
# paragraph later. The invariant is unchanged: BOTH system-timer sites read the derived list.
assert 'praetorium-status.sh feeds the derived list to BOTH of its system-timer sites' \
  "[ \"\$(grep -c 'fleet_or_die system timer' '$REPO/bin/praetorium-status.sh')\" -eq 2 ]"
# And the wrapper is the ONLY accessor a consumer may call. fleet_units returns empty for a
# missing, empty or still-4-column TSV, and empty is what lets a report say "nothing
# scheduled" about a list it could not read; fleet_or_die turns that into a refusal. A site
# that calls the raw accessor has opted out of the refusal without saying so.
assert 'and every consumption site goes through the refusing wrapper' \
  "[ \"\$(grep -c 'fleet_or_die ' '$REPO/bin/praetorium-status.sh')\" -eq 4 ] && [ \"\$(grep -cE '[(]fleet_units ' '$REPO/bin/praetorium-status.sh')\" -eq 1 ]"

registered=$(python3 - <<'PY'
import pathlib, tomllib
for m in sorted(pathlib.Path("design/agents").glob("*.toml")):
    for w in tomllib.loads(m.read_text()).get("workflows", []):
        if w.get("unit") == "agent-drift-check":
            print(" ".join(w.get("suite", [])))
PY
)
assert 'it has a [[workflows]] entry whose suite names this file' \
  "grep -q 'tests/test_deploy_drift.sh' <<<'$registered'"

echo "--- 11. the checker refuses the shapes that make it lie ---"
fixture
# Source==runtime: REPO is resolved from $0, so the deployed copy of this script compares a
# tree with itself and reports zero findings whatever the repo contains.
out=$(DRIFT_SRC_BIN="$root/run_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
      DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
      DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
      DRIFT_SRC_BUZZ="$root/src_buzz" DRIFT_BUZZ="$root/buzz" \
      DRIFT_BUZZ_MANIFEST="$root/src_buzz/MANIFEST.toml" \
      DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
  env "${CONTENT_ENV[@]}" \
      bash "$CHECK" 2>&1); rc=$?
assert 'source and runtime resolving to one tree is refused, not reported clean' "[ $rc -eq 2 ]"
assert 'and says which tree collapsed' "saw 'same tree'"

# design/ is not in bin/deploy's PATHS, so the runtime tree has none. Reading that as "no
# exclusions" turned a clean box into 11 findings including ollama.service.
out=$(DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
      DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
      DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
      DRIFT_SRC_BUZZ="$root/src_buzz" DRIFT_BUZZ="$root/buzz" \
      DRIFT_BUZZ_MANIFEST="$root/src_buzz/MANIFEST.toml" \
      DRIFT_OWNERSHIP="$root/nope.toml" DRIFT_MANIFESTS="$root/manifests" \
      bash "$CHECK" 2>&1); rc=$?
assert 'absent ownership declarations are refused, never an empty exclusion set' "[ $rc -eq 2 ]"
assert 'and the refusal explains what would have gone wrong' "saw 'undeclared drift'"
rm -rf "$root"

echo "--- 12. a TEMPLATED campaign family is declared once and excludes every instance ---"
fixture
echo '[Unit]' > "$root/etc/praetorium-phaseb-brief@2.timer"
cat > "$root/manifests/trajan.toml" <<'TOML'
[[workflows]]
unit    = "praetorium-phaseb-brief@"
status  = "campaign"
expires = "2026-12-31 00:00"
TOML
capture
# The manifest declares the family; the instance stem is praetorium-phaseb-brief@2. Keying
# on the stem alone matched nothing, so the only campaign family in the repo could never be
# excluded — and group 6 above never noticed, because its fixture name has no `@`.
assert 'the family entry silences an instance' "saw 'praetorium-phaseb-brief@2.timer — campaign'"
assert 'and nothing is reported' "clean"
rm -rf "$root"

echo "--- 13. scope: deploy owns one tree and its exit code says only that ---"
fixture
echo '[Unit]' > "$root/etc/hand-installed.timer"
out=$(DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
      DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
      DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
      DRIFT_SRC_BUZZ="$root/src_buzz" DRIFT_BUZZ="$root/buzz" \
      DRIFT_BUZZ_MANIFEST="$root/src_buzz/MANIFEST.toml" \
      DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
  env "${CONTENT_ENV[@]}" \
      bash "$CHECK" --scope bin 2>&1); rc=$?
assert '--scope bin ignores an /etc-only unit deploy cannot install' "[ $rc -eq 0 ]"
assert 'and says so rather than implying the units were checked' "saw 'NOT compared'"
assert 'an unknown scope is refused' \
  "bash '$CHECK' --scope sideways >/dev/null 2>&1; [ \$? -eq 2 ]"
rm -rf "$root"

echo "--- 14. the user tree has the same escape hatch as /etc ---"
fixture
echo '[Unit]' > "$root/user/not-ours.service"
cat > "$root/ownership.toml" <<'TOML'
[[third_party]]
unit = "not-ours.service"
tree = "user"
why  = "app-installed --user override"
TOML
capture
assert 'a declared user-tree unit produces no finding' "clean"
assert 'and is named rather than silently skipped' "saw 'live-only: not-ours.service — declared'"
# tree is read, not decorative: the same declaration scoped to etc must NOT silence a user
# unit, or one list would silence two trees and the field would mean nothing.
sed -i 's/tree = "user"/tree = "etc"/' "$root/ownership.toml"
capture
assert 'the same entry scoped to etc does NOT silence it' \
  "saw 'DRIFT \[user\] live-only: not-ours.service'"
rm -rf "$root"

echo "--- 14b. the fifth tree: buzz-team/ <-> ~/.config/buzz-team ---"
# S1's mechanism tree. Brief 2 sourced the --user units and left everything those units READ
# unsourced, so the fleet's core unit was in the repo and its entire configuration was not.
# The two membership directions are DIFFERENT BUGS WITH DIFFERENT FIXES and are proven
# separately: source-only means the box is not running what the repo says (run
# bin/deploy_buzz_team.sh, then restart); box-only means a rebuild from source loses the file
# (adopt it, or declare it excluded).
fixture
echo 'rules' > "$root/src_buzz/marcus.toml"
capture
assert 'a repo-side file the box does not have is red, and it is UNDECLARED that is reported' \
  "saw 'DRIFT \[buzz\] source-only: marcus.toml is in .* declared in no MANIFEST.toml'"
cat >> "$root/src_buzz/MANIFEST.toml" <<'TOML'
[[adopted]]
path = "marcus.toml"
why  = "declared, so the finding must change from undeclared to undeployed"
TOML
capture
assert 'declaring it changes the finding to "not on the box" — a converge, not an adoption' \
  "saw 'DRIFT \[buzz\] source-only: marcus.toml is not on the box'"
echo 'rules' > "$root/buzz/marcus.toml"
capture
assert 'converging it clears the finding' "clean"
echo 'edited-on-the-box' > "$root/buzz/marcus.toml"
capture
assert 'and a hand-edit to the live copy is then caught' \
  "saw 'DRIFT \[buzz\] content differs: marcus.toml'"
rm -rf "$root"

fixture
echo 'prose' > "$root/buzz/PROSE.md"
capture
assert 'a DECLARED box-only exclusion is not drift — prose stays machine-level by design' "clean"
assert 'and is named, because an absence cannot be told from a deletion' \
  "saw 'box-only: PROSE.md — declared excluded'"
echo 'prose' > "$root/buzz/UNDECLARED.md"
capture
assert 'an UNDECLARED box-only file is red — a rebuild from source loses it' \
  "saw 'DRIFT \[buzz\] box-only: UNDECLARED.md'"
rm -rf "$root"

echo "--- 14b-iii. buzz-team: present in BOTH trees, declared in neither list ---"
# The third membership case, and the one the two above cannot reach: present in BOTH trees.
# Until 2026-09-03 an undeclared file here fell through to `cmp`, matched, and passed — so
# the header's "an undeclared file in EITHER tree is red" held for each direction separately
# and for neither together. It is also the likeliest shape of the bug, because the way an
# undeclared file arrives in both trees is somebody copying it into both.
fixture
echo 'hand-copied' > "$root/src_buzz/SIDECAR.toml"
echo 'hand-copied' > "$root/buzz/SIDECAR.toml"
capture
assert 'a byte-identical file in both trees, declared nowhere, is red' \
  "saw 'DRIFT \[buzz\] in both trees: SIDECAR.toml is declared in no MANIFEST.toml entry'"
cat >> "$root/src_buzz/MANIFEST.toml" <<'TOML'
[[adopted]]
path = "SIDECAR.toml"
why  = "declaring it is the fix, and the finding must then clear"
TOML
capture
assert 'declaring it adopted clears the finding' "clean"
rm -rf "$root"

# The mirror case: an `excluded` entry asserts the box holds the file and this repo does not.
# A source copy falsifies that, and reporting it as merely "excluded, skipping" would let a
# stale exclusion hide a real adoption.
fixture
echo 'prose' > "$root/buzz/PROSE.md"
echo 'prose' > "$root/src_buzz/PROSE.md"
capture
assert 'an EXCLUDED file that has grown a source copy is red, not silently skipped' \
  "saw 'DRIFT \[buzz\] in both trees: PROSE.md is declared EXCLUDED'"
rm -rf "$root"

fixture
rm -f "$root/src_buzz/MANIFEST.toml"
out=$(drift); rc=$?
assert 'a missing buzz-team MANIFEST.toml is a refusal to run, not an empty exclusion set' \
  "[ $rc -eq 2 ]"
assert 'and the refusal names the declaration it could not find' "saw 'MANIFEST.toml'"
rm -rf "$root"

fixture
# Same tautology as the bin half, one tree over: a tree compared with itself reports zero
# findings whatever either side contains.
out=$(DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
      DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
      DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
      DRIFT_SRC_BUZZ="$root/buzz" DRIFT_BUZZ="$root/buzz" \
      DRIFT_BUZZ_MANIFEST="$root/src_buzz/MANIFEST.toml" \
      DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
  env "${CONTENT_ENV[@]}" \
      bash "$CHECK" 2>&1); rc=$?
assert 'buzz source and live resolving to one tree is refused, not reported clean' "[ $rc -eq 2 ]"
assert 'and says which tree collapsed' "saw 'same directory'"
rm -rf "$root"

echo "--- 14c. the converge path is a separate script, and it restarts nothing ---"
# Criterion 8-10. bin/deploy owns ONE $DEST behind three refusals that are all about the
# agent-workforce runtime tree; a config directory satisfies none of them, and loosening them
# to fit a second destination weakens the guard protecting the first.
CONVERGE="$REPO/bin/deploy_buzz_team.sh"
assert 'bin/deploy_buzz_team.sh exists and is executable' "[ -x '$CONVERGE' ]"
assert 'bin/deploy still ships exactly its eight paths — buzz-team is NOT one of them' \
  "! grep -qE '^PATHS=.*buzz-team' '$REPO/bin/deploy'"
assert 'it says out loud that the fleet is still on the old config' \
  "grep -q 'NOTHING WAS RESTARTED' '$CONVERGE'"
assert '--dry-run is a documented mode' "grep -q -- '--dry-run' '$CONVERGE'"

# Proven by RUNNING it under a systemctl stub, not by grepping for the word. The script
# PRINTS `systemctl --user restart buzz-agent@marcus` inside a quoted heredoc, so a grep
# cannot tell the instruction it hands a human from a call it makes itself — and it is
# precisely that distinction the assertion is about. Five live agents: a converge that
# restarted them would take the fleet down on a malformed filter, because buzz-acp compiles
# every filter eagerly at startup.
guard_root=$(mktemp -d)
mkdir -p "$guard_root/stub" "$guard_root/dest" "$guard_root/notbuzz"
cat > "$guard_root/stub/systemctl" <<STUB
#!/bin/sh
echo "\$@" >> "$guard_root/systemctl-was-called"
STUB
chmod +x "$guard_root/stub/systemctl"
for f in marcus claudius augustus trajan aurelian; do
  cp "$REPO/buzz-team/$f.toml" "$guard_root/dest/$f.toml"
done
echo 'stale' > "$guard_root/dest/marcus.toml"
converge_out=$(PATH="$guard_root/stub:$PATH" BUZZ_TEAM_DEST="$guard_root/dest" \
               bash "$CONVERGE" 2>&1); converge_rc=$?
assert 'a real converge writes the drifted file and exits 0' \
  "[ $converge_rc -eq 0 ] && cmp -s '$REPO/buzz-team/marcus.toml' '$guard_root/dest/marcus.toml'"
assert 'and it invoked systemctl exactly never — the fleet is still on the old config' \
  "[ ! -e '$guard_root/systemctl-was-called' ]"
assert 'while telling the human which command to run' \
  "grep -q 'systemctl --user restart buzz-agent@' <<<\"\$converge_out\""

# Its destination guard, proven by pointing it at a directory that is not the live tree.
assert 'it refuses a destination that lacks the five rule files' \
  "! BUZZ_TEAM_DEST='$guard_root/notbuzz' bash '$CONVERGE' --dry-run >/dev/null 2>&1"
assert 'it refuses a destination that does not exist' \
  "! BUZZ_TEAM_DEST='$guard_root/absent' bash '$CONVERGE' --dry-run >/dev/null 2>&1"
# --dry-run is the documented first step, so it must not write. Asserted by re-drifting the
# destination and checking the file is still wrong afterwards.
echo 'stale-again' > "$guard_root/dest/marcus.toml"
PATH="$guard_root/stub:$PATH" BUZZ_TEAM_DEST="$guard_root/dest" \
  bash "$CONVERGE" --dry-run >/dev/null 2>&1
assert '--dry-run reports the change and writes nothing' \
  "[ \"\$(cat '$guard_root/dest/marcus.toml')\" = 'stale-again' ]"

# The manifest is a WRITE DESTINATION, not just a selector. `path` reaches
# `cp -p "$SRC/$f" "$DEST/$f"` with no validation, and the destination guard above proves
# things about $DEST that a `../` in $f walks straight out of. The escape is also silent
# afterwards: bin/check_deploy_drift.sh enumerates both trees with
# `find -maxdepth 1 -type f -printf '%f\n'`, so a file written through a path component is
# absent from both membership directions and the drift check reports clean.
#
# Asserted by running the real thing, with the escape target PRESENT in the source — the
# pre-existing "declared file absent from source" refusal already covers the absent case, and
# a test that only covered that would pass with the guard deleted. Measured 2026-09-03 on a
# guard-stripped copy: `create   ../payload.toml`, `1 file(s) written.`, exit 0 — reported as
# a clean converge.
trav="$guard_root/trav"
mkdir -p "$trav/src" "$trav/live/dest"
for f in marcus claudius augustus trajan aurelian; do
  cp "$REPO/buzz-team/$f.toml" "$trav/src/$f.toml"
  cp "$REPO/buzz-team/$f.toml" "$trav/live/dest/$f.toml"
done
# $SRC/../payload.toml resolves to $trav/payload.toml and EXISTS, so the pre-existing
# "declared file absent from source" refusal cannot be what stops this. $DEST/../payload.toml
# resolves to $trav/live/payload.toml — a different directory, which is why the fixture nests
# the destination one level deeper than the source.
printf 'PAYLOAD\n' > "$trav/payload.toml"
# The legitimate entry is left DRIFTED so the half-converge assertion below can fail. With
# dest already matching source there is nothing to write and the check passes vacuously.
printf 'stale-trav\n' > "$trav/live/dest/marcus.toml"
cat > "$trav/src/MANIFEST.toml" <<'TRAVMAN'
[[adopted]]
path = "marcus.toml"
[[adopted]]
path = "../payload.toml"
TRAVMAN
trav_out=$(PATH="$guard_root/stub:$PATH" BUZZ_TEAM_SRC="$trav/src" BUZZ_TEAM_DEST="$trav/live/dest" \
           bash "$CONVERGE" 2>&1); trav_rc=$?
assert 'a manifest path with a directory component is refused, not written' "[ $trav_rc -ne 0 ]"
assert 'and it names the offending path rather than failing generically' \
  "grep -q -- '../payload.toml' <<<\"\$trav_out\""
assert 'nothing escaped the destination' "[ ! -e '$trav/live/payload.toml' ]"
# The refusal is a SET check, before any write — a half-converge that refuses on the second
# entry has already shipped the first, and the operator sees a failure over a changed tree.
assert 'and the legitimate entry ahead of it was not written either' \
  "[ \"\$(cat '$trav/live/dest/marcus.toml')\" = 'stale-trav' ]"
rm -rf "$guard_root"

echo "--- 15. a .conf outside a *.d directory is not a drop-in ---"
fixture
mkdir -p "$root/src_sys/user"
echo 'x' > "$root/src_sys/user/model.conf"
capture
# systemd/user/ and systemd/archive/ are excluded from the UNIT comparison by -maxdepth 1;
# the drop-in scan must exclude them the same way or it emits a finding no declaration can
# silence.
assert 'systemd/user/*.conf is not reported as an uninstalled drop-in' "! saw 'user/model.conf'"
rm -rf "$root"

echo "--- 16. the six content trees bin/deploy ships (W7) ---"
# Until 2026-09-03 this check compared 2 of the 8 paths bin/deploy ships. The four unit
# groups above cover `bin` and the three unit trees; these cover the rest, and profiles/ is
# the one that matters most — it holds the agents' actual instructions, so a profile fixed in
# source and never deployed is a fleet running prose this repo has already corrected.
fixture
echo 'edited' > "$root/run_content/profiles/live_task.md"
capture
assert 'a profile whose bytes differ is named' \
  "saw 'DRIFT \[content\] content differs: profiles/live_task.md'"
rm -rf "$root"

fixture
echo 'new' > "$root/src_content/profiles/added_task.md"
capture
assert 'a profile in source and not deployed is red' \
  "saw 'DRIFT \[content\] source-only: profiles/added_task.md is not deployed'"
rm -rf "$root"

# The direction bin/deploy cannot fix. It is additive, so deleting a file from source leaves
# the deployed copy in place until --prune runs — and --prune is a human decision against a
# live runtime. Undeclared, that is drift.
fixture
echo 'orphan' > "$root/run_content/profiles/disowned_task.md"
capture
assert 'a runtime file the source tree disowned is red when nothing declares it' \
  "saw 'DRIFT \[content\] runtime-only: profiles/disowned_task.md has no source and is declared in no exclusion'"

cat > "$root/exclusions.toml" <<'TOML'
[[runtime_only]]
path  = "disowned_task.md"
tree  = "profiles"
since = "2026-09-01"
why   = "fixture"
TOML
capture
assert 'declaring it in design/deploy-exclusions.toml clears the finding' "clean"
assert 'and it is still printed by name, never silently skipped' \
  "saw 'info: runtime-only: profiles/disowned_task.md'"
assert 'the info line names the action that resolves it' "saw 'pending bin/deploy --prune'"
rm -rf "$root"

# The self-clearing half, and the reason the exclusions carry no expiry date. A prune removes
# the file; the entry that silenced it must then go, or the list carries a permanent silence
# for something that no longer exists. An exclusion outliving its subject is the same defect
# as a missing one, pointing the other way.
fixture
cat > "$root/exclusions.toml" <<'TOML'
[[runtime_only]]
path  = "already_pruned.md"
tree  = "profiles"
since = "2026-09-01"
why   = "fixture: the prune has run"
TOML
capture
assert 'an exclusion whose subject is gone is red, so the list cannot rot' \
  "saw 'stale exclusion: design/deploy-exclusions.toml names profiles/already_pruned.md'"
assert 'and it says the prune happened rather than reporting a missing file' \
  "saw 'the prune has happened; delete the entry'"
rm -rf "$root"

# Single-file trees (CLAUDE.md, AGENTS.md, README.md). `find` over a file path yields the
# file with an EMPTY %P, which would compare "$src/" against "$live/" — two directories that
# do not exist — and pass silently. Both are exercised because the bug is invisible from the
# passing side.
fixture
echo 'changed' > "$root/run_content/NOTE.md"
capture
assert 'a single-file tree whose bytes differ is caught, not collapsed to an empty path' \
  "saw 'DRIFT \[content\] content differs: NOTE.md'"
rm -rf "$root"

fixture
rm "$root/run_content/NOTE.md"
capture
assert 'and an undeployed single-file tree is red' \
  "saw 'DRIFT \[content\] source-only: NOTE.md is not deployed'"
rm -rf "$root"

# Nesting is why these trees need %P and not %f. config/job-overrides/ and profiles/archive/
# both nest, and a basename comparison collapses profiles/archive/x.md onto profiles/x.md —
# which is exactly the pair the live exclusion list is about, so the bug would hide the real
# case while reporting a clean tree.
fixture
mkdir -p "$root/src_content/profiles/archive"
cp "$root/src_content/profiles/live_task.md" "$root/src_content/profiles/archive/live_task.md"
capture
assert 'an archived copy is a distinct path, not the same name as its live sibling' \
  "saw 'source-only: profiles/archive/live_task.md'"
assert 'and the live sibling is not reported' "! saw 'source-only: profiles/live_task.md'"
rm -rf "$root"

fixture
echo 'x' > "$root/run_content/config/job-overrides/deep_only.env"
capture
assert 'a nested runtime-only file is named with its full relative path' \
  "saw 'runtime-only: config/job-overrides/deep_only.env'"
rm -rf "$root"

# Same *.bak* exclusion as the bin half. bin/notion_rest.py and the profile editors leave
# dated backups in the runtime as a matter of course.
fixture
echo 'old' > "$root/run_content/profiles/live_task.md.bak-20260713-093716"
capture
assert 'a dated .bak in the runtime content tree is not drift' "clean"
rm -rf "$root"

fixture
rm -rf "$root/src_content/profiles" "$root/run_content/profiles"
capture
assert "a tree in bin/deploy's PATHS that exists in neither place is red, not skipped" \
  "saw 'profiles is in bin/deploy'"
rm -rf "$root"

echo "--- 16c. the STAGING copy of systemd/, the eighth path (W17) ---"
# systemd/ is ONE tree with TWO destinations, and only one of them was compared. The unit
# half above reads /etc directly — correctly, since systemd never reads staging — and that
# read as coverage: "systemd/ is compared" was true of a different destination. The copy
# bin/deploy actually writes, $RUNTIME_ROOT/systemd/, was compared by nothing, and it was
# already populated: three runtime-only units on 2026-09-04, named by `--dry-run --prune`
# and by no check.
fixture
echo '[Unit]x' > "$root/run_content/systemd/staged.service"
capture
assert 'a staged unit whose bytes differ from source is named' \
  "saw 'DRIFT \[content\] content differs: systemd/staged.service'"
rm -rf "$root"

fixture
echo '[Unit]' > "$root/src_content/systemd/added.timer"
capture
assert 'a unit in source and not staged is red' \
  "saw 'DRIFT \[content\] source-only: systemd/added.timer is not deployed'"
rm -rf "$root"

# The direction that was live on this box: bin/deploy is additive, so a unit deleted from
# source sits in staging until --prune runs. discord-bot.service has no source in any tree
# and both content-inbox-finalize files were archived; none of the three was reportable.
fixture
echo '[Unit]' > "$root/run_content/systemd/discord-bot.service"
capture
assert 'a staged unit the source tree disowned is red when nothing declares it' \
  "saw 'DRIFT \[content\] runtime-only: systemd/discord-bot.service has no source and is declared in no exclusion'"

cat > "$root/exclusions.toml" <<'TOML'
[[runtime_only]]
path  = "discord-bot.service"
tree  = "systemd"
since = "2026-09-04"
why   = "fixture"
TOML
capture
assert 'the same exclusion lookup applies to the staging tree' "clean"
assert 'and the staged file is still printed by name' \
  "saw 'info: runtime-only: systemd/discord-bot.service'"
assert 'the info line names the action that resolves it' "saw 'pending bin/deploy --prune'"
rm -rf "$root"

# THE TREE IS NOT FLAT, and this is the assertion the other four cannot make. systemd/user/,
# systemd/archive/ and systemd/qmd-mcp.service.d/ all exist in both copies, so a -maxdepth 1
# regression in relnames() would pass every assertion above while comparing nothing below the
# top level — including the nine --user units the Buzz fleet runs on.
fixture
mkdir -p "$root/run_content/systemd/user"
echo '[Unit]' > "$root/run_content/systemd/user/orphan.service"
capture
assert 'a staged file in a NESTED path is named with its full relative path' \
  "saw 'runtime-only: systemd/user/orphan.service'"
rm -rf "$root"

echo "--- 16b. the tree list agrees with bin/deploy's PATHS ---"
# CONTENT_TREES is a literal in check_deploy_drift.sh rather than a parse of bin/deploy:20,
# because parsing another script's array is a join that breaks silently. This is that join,
# asserted instead — in both directions, so neither list can grow or shrink alone.
#
# A PATH CREDITED BY A LITERAL IN THIS FILE IS A PATH THIS TEST ASSERTS AND THE CHECK DOES
# NOT PERFORM. `bin` is the one legitimate case: it has its own comparison block above
# (SRC_BIN <-> RUNTIME_BIN) and can never come from CONTENT_TREES. `systemd` was credited
# here too from 2026-09-03 to 2026-09-04, and that is exactly how this assertion passed
# 8 = 8 while the staging copy of systemd/ was compared by nothing — the check was measured
# for seven paths and asserted for eight. Nothing else may be added to this printf.
deploy_paths=$(sed -n 's/^PATHS=(\(.*\))$/\1/p' "$REPO/bin/deploy" | tr ' ' '\n' | LC_ALL=C sort)
content_trees=$(sed -n 's/^CONTENT_TREES="${DRIFT_CONTENT_TREES:-\(.*\)}"$/\1/p' "$CHECK" | tr ' ' '\n')
checked=$( { echo "$content_trees"; printf 'bin\n'; } | LC_ALL=C sort)
assert 'every path bin/deploy ships is compared by this check' \
  "[ -z \"\$(comm -23 <(echo \"\$deploy_paths\") <(echo \"\$checked\"))\" ]"
assert 'and this check compares nothing bin/deploy does not ship' \
  "[ -z \"\$(comm -13 <(echo \"\$deploy_paths\") <(echo \"\$checked\"))\" ]"
assert 'both lists actually parsed (an empty comm difference is not evidence)' \
  "[ \"\$(echo \"\$deploy_paths\" | wc -l)\" = 8 ] && [ \"\$(echo \"\$checked\" | wc -l)\" = 8 ]"
# The laundering guard, measured rather than grepped for: re-adding `systemd` to the printf
# leaves it in `checked` twice, which the comm and the count above both catch — and removing
# it from CONTENT_TREES to compensate is what this asserts. Grepping this file for the old
# printf would match the grep's own pattern and fail on the fixed tree.
assert 'systemd is credited by the real CONTENT_TREES, not by a literal in this test' \
  "grep -qx systemd <<<\"\$content_trees\""
exit $fail
