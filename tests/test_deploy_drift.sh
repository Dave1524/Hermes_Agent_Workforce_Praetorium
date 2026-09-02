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
  mkdir -p "$root"/{src_bin,run_bin,src_sys,etc,src_user,user}
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
}

drift() { # runs the checker against the current fixture; extra env comes from the caller
  DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
  DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
  DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
  DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
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
assert 'praetorium-status.sh feeds the derived list to BOTH of its sites' \
  "[ \"\$(grep -c 'fleet_units system' '$REPO/bin/praetorium-status.sh')\" -eq 2 ]"

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
      DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
      bash "$CHECK" 2>&1); rc=$?
assert 'source and runtime resolving to one tree is refused, not reported clean' "[ $rc -eq 2 ]"
assert 'and says which tree collapsed' "saw 'same tree'"

# design/ is not in bin/deploy's PATHS, so the runtime tree has none. Reading that as "no
# exclusions" turned a clean box into 11 findings including ollama.service.
out=$(DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
      DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
      DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
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
      DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
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

exit $fail
