#!/usr/bin/env bash
# bin/auto-sync — the 15-minute platform timer that commits and pushes this repo.
# W6: it carried status = "standing" with neither `suite` nor `suite_exempt` from D6 until
# 2026-09-03, which is a strange thing for the one job that can PUSH TO origin/main unattended.
#
# Offline by contract. Every fixture is a throwaway bare origin plus a clone with a COPY of
# bin/auto-sync in it; the script's own `cd "$(dirname "$0")/.."` is what makes that work, and
# is itself asserted below. Nothing here runs against this checkout and nothing reaches GitHub.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in the shared assert(): `yes` is
# still writing when `grep -q` exits, so this fails if and only if a condition is evaluated
# under pipefail. It lives in every caller because the assert it guards is shared.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

SYNC="$REPO_ROOT/bin/auto-sync"

# state -> a fixture root whose ./work is a clone of ./origin.git carrying its own bin/auto-sync.
make_sync_fixture() {
  local state=$1 root origin work
  root=$(mktemp -d); origin="$root/origin.git"; work="$root/work"
  git init -q --bare -b main "$origin"
  git init -q -b main "$work"
  git -C "$work" config user.email test@example.com
  git -C "$work" config user.name test
  mkdir -p "$work/bin"
  cp "$SYNC" "$work/bin/auto-sync"
  printf 'tracked\n' > "$work/tracked.md"
  git -C "$work" add -A
  git -C "$work" commit -q -m base
  git -C "$work" remote add origin "$origin"
  git -C "$work" push -q -u origin main

  case "$state" in
    clean) : ;;
    tracked_edit)   printf 'edited\n' >> "$work/tracked.md" ;;
    untracked_only) printf 'brand new script\n' > "$work/bin/newly_added.sh" ;;
    # The half of `git status --porcelain` that must NOT wake the job up. Both --porcelain and
    # `git add -A` honour .gitignore, so an ignored-only tree still has genuinely nothing to
    # commit; if they ever disagreed the job would try to commit an empty index and die under
    # `set -e`. .gitignore is committed in the base commit so it is tracked, not itself pending.
    ignored_only)   printf 'logs/\n' > "$work/.gitignore"
                    git -C "$work" add .gitignore
                    git -C "$work" commit -q -m "ignore logs"
                    git -C "$work" push -q origin main
                    mkdir -p "$work/logs"
                    printf 'noise\n' > "$work/logs/run.log" ;;
    # A tracked edit AND an unrelated untracked file. The `git add -A` stage does not
    # distinguish them, which is the hazard CLAUDE.md warns about in prose.
    mixed)          printf 'edited\n' >> "$work/tracked.md"
                    printf 'unrelated WIP\n' > "$work/scratch.md" ;;
    # An untracked DIRECTORY holding a nested repository — the shape `git worktree add` and the
    # agent harness both produce. untracked_only cannot exercise it: that one writes into bin/, a
    # directory git already tracks, so porcelain emits `?? bin/newly_added.sh` and add -A stages
    # exactly that file. Here porcelain COLLAPSES the directory to a single `?? nested/` entry
    # whose expansion under add -A is a 160000 gitlink, not the files inside it. Two different
    # sets from two different entries, which is why 33 green assertions missed this.
    nested_repo)    git init -q -b main "$work/nested"
                    git -C "$work/nested" config user.email nested@example.com
                    git -C "$work/nested" config user.name nested
                    printf 'inside a nested repo\n' > "$work/nested/file.md"
                    git -C "$work/nested" add -A
                    git -C "$work/nested" commit -q -m "nested base" ;;
    off_branch)     git -C "$work" checkout -q -b agents/2026-09-03-something
                    printf 'edited\n' >> "$work/tracked.md" ;;
    # origin rewritten under the clone: pull --ff-only cannot fast-forward.
    diverged)       local other="$root/other"
                    git clone -q "$origin" "$other"
                    git -C "$other" config user.email mac@example.com
                    git -C "$other" config user.name mac
                    printf 'from elsewhere\n' >> "$other/tracked.md"
                    git -C "$other" commit -qam "upstream moved"
                    git -C "$other" push -q origin main
                    printf 'diverging locally\n' >> "$work/tracked.md"
                    git -C "$work" commit -qam "box moved too" ;;
  esac
  echo "$root"
}

run_sync() { # root -> rc, output in $root/run.log
  local root=$1 rc=0
  bash "$root/work/bin/auto-sync" > "$root/run.log" 2>&1 || rc=$?
  echo "$rc"
}

origin_head() { git -C "$1/origin.git" rev-parse main; }

echo "--- auto-sync: refuses off the primary branch ---"
# The one refusal that keeps a feature branch from being force-marched onto main by a timer.
root=$(make_sync_fixture off_branch); before=$(origin_head "$root")
rc=$(run_sync "$root")
assert 'exits non-zero on a non-main branch' "[ '$rc' != 0 ]"
assert 'names the branch it found (an alert with no name is a second search)' \
  "grep -q 'not on main (current: agents/2026-09-03-something)' '$root/run.log'"
assert 'and origin is untouched' "[ \"\$(origin_head '$root')\" = '$before' ]"

echo "--- auto-sync: refuses when it cannot fast-forward ---"
# A diverged origin means someone pushed from elsewhere. Merging here unattended would put a
# machine-authored merge commit on main; refusing leaves the tree dirty and visible instead.
root=$(make_sync_fixture diverged); before=$(origin_head "$root")
rc=$(run_sync "$root")
assert 'exits non-zero rather than merging' "[ '$rc' != 0 ]"
assert 'says manual resolution is required' \
  "grep -q 'Manual resolution required' '$root/run.log'"
assert 'and origin is untouched' "[ \"\$(origin_head '$root')\" = '$before' ]"

echo "--- auto-sync: a genuinely clean tree pushes nothing ---"
# The regression the W16 fix could plausibly introduce: a broader "is there anything to do?"
# test that fires on a tree with nothing to do reaches `git add -A && git commit`, which has
# nothing to stage and exits non-zero under `set -e`. So this case asserts the LOCAL history
# too — an unpushed empty commit would leave origin untouched and hide the fault here.
root=$(make_sync_fixture clean); before=$(origin_head "$root")
local_before=$(git -C "$root/work" rev-parse HEAD)
rc=$(run_sync "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'says so' "grep -q 'working tree clean. Nothing to do' '$root/run.log'"
assert 'and creates no commit' "[ \"\$(origin_head '$root')\" = '$before' ]"
assert 'not even an unpushed local one' \
  "[ \"\$(git -C '$root/work' rev-parse HEAD)\" = '$local_before' ]"

echo "--- auto-sync: an IGNORED-only tree is still clean ---"
# `git status --porcelain` is a wider view than `git diff`, and the question this answers is
# whether it is wider than `git add -A` — i.e. whether it can report work the commit step cannot
# stage. It cannot: neither lists ignored paths (--porcelain needs --ignored to), so the two
# agree on what is out of scope and the job stays quiet. Were they to disagree, the failure is
# loud rather than silent — `git commit` with an empty index exits non-zero under `set -e` — but
# it would be a 15-minute alert loop, so it is pinned here rather than left to inference.
root=$(make_sync_fixture ignored_only); before=$(origin_head "$root")
local_before=$(git -C "$root/work" rev-parse HEAD)
rc=$(run_sync "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'reports clean' "grep -q 'working tree clean. Nothing to do' '$root/run.log'"
assert 'commits nothing locally' \
  "[ \"\$(git -C '$root/work' rev-parse HEAD)\" = '$local_before' ]"
assert 'and origin is untouched' "[ \"\$(origin_head '$root')\" = '$before' ]"
assert 'the ignored file is still on disk and still ignored' \
  "[ -f '$root/work/logs/run.log' ] && git -C '$root/work' check-ignore -q logs/run.log"

echo "--- auto-sync: a tracked edit is committed and pushed ---"
root=$(make_sync_fixture tracked_edit); before=$(origin_head "$root")
rc=$(run_sync "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'origin/main advanced' "[ \"\$(origin_head '$root')\" != '$before' ]"
assert 'under the generic Auto-sync subject' \
  "git -C '$root/work' log -1 --format=%s | grep -q '^Auto-sync: main updates at '"
# The timestamp is stamped UTC and says so. journalctl on this box renders CEST (+2), and an
# unlabelled timestamp in a commit subject is the same silent-offset trap that once inverted
# cause and effect in a fleet timeline.
assert 'and the timestamp is explicitly UTC, not a bare local time' \
  "git -C '$root/work' log -1 --format=%s | grep -qE '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2} UTC\$'"
assert 'it reports the sha it pushed' "grep -q 'auto-sync: pushed main at ' '$root/run.log'"

echo "--- auto-sync: PINNED — git add -A sweeps unrelated WIP into the same commit ---"
# Characterization of a known hazard, not approval of it. CLAUDE.md states this in prose
# ("Any dirty tree here reaches origin/main within 15 minutes under a generic `Auto-sync:`
# message, sweeping unrelated WIP along with it"); this is that sentence with a test behind it.
# The mitigation is procedural — commit your own work immediately, or stop the timer for a long
# batch — so the assertion exists to keep the behaviour honest, not to bless it.
root=$(make_sync_fixture mixed)
rc=$(run_sync "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the deliberate edit is in the commit' \
  "git -C '$root/work' show --name-only --format= HEAD | grep -qx 'tracked.md'"
assert 'and so is the unrelated scratch file, under the same generic message' \
  "git -C '$root/work' show --name-only --format= HEAD | grep -qx 'scratch.md'"

echo "--- auto-sync: W16 FIXED — an untracked-only tree is committed and pushed ---"
# This group pinned the fail-open until 2026-09-03 and now pins its absence. The old gate was
# `git diff --quiet && git diff --cached --quiet`; neither command looks at untracked files,
# while the very next stage is `git add -A`, which would have committed them. So a tree holding
# ONLY new files took the early return and printed "working tree clean. Nothing to do", every
# 15 minutes, indefinitely — the log saying "Nothing to do" in a voice that sounded like it
# looked. The cost was not a lost edit but a DELAYED one with a wrong author story: the file
# waited for some unrelated tracked change, then got swept in under an `Auto-sync:` subject
# dated days after it was written. A whole new script — the thing this repo adds most often —
# was invisible to origin the entire time.
#
# `git status --porcelain` closed it (W16 in design/open-decisions.md). These assertions are the
# mirror image of what they were: the untracked-only tree must now behave exactly like the
# tracked_edit case below it — committed, pushed, and reported by sha. The negative half is
# load-bearing on its own, because the old code exited 0 too: exit 0 was never the tell, the
# "working tree clean" line was.
root=$(make_sync_fixture untracked_only); before=$(origin_head "$root")
rc=$(run_sync "$root")
assert 'W16: exits 0' "[ '$rc' = 0 ]"
assert 'W16: does NOT call an untracked-only tree clean' \
  "! grep -q 'working tree clean. Nothing to do' '$root/run.log'"
assert 'W16: origin/main advanced' "[ \"\$(origin_head '$root')\" != '$before' ]"
assert 'W16: and the new file is what it carries' \
  "git -C '$root/work' show --name-only --format= HEAD | grep -qx 'bin/newly_added.sh'"
assert 'W16: under the same generic Auto-sync subject as any other sync' \
  "git -C '$root/work' log -1 --format=%s | grep -q '^Auto-sync: main updates at '"
assert 'W16: it reports the sha it pushed' "grep -q 'auto-sync: pushed main at ' '$root/run.log'"
# The loop converges: one run is enough, so the next tick has genuinely nothing to do rather
# than re-committing the same file forever.
assert 'W16: and the tree is clean afterwards, so the next tick is a no-op' \
  "[ -z \"\$(git -C '$root/work' status --porcelain)\" ]"

echo "--- auto-sync: it REFUSES to push a nested repository as a gitlink ---"
# The regression the W16 widening made reachable, caught by review before it merged rather than
# by origin/main afterwards. Under the old tracked-only gate an untracked worktree directory
# never woke the job; under `git status --porcelain` it does, and `git add -A` stages it as a
# 160000 gitlink — an accidental submodule, no .gitmodules, recording a commit that exists only
# in this clone. It commits and pushes cleanly with exit 0, so nothing downstream would ever have
# said so; a fresh clone just gets a directory git refuses to populate. Not hypothetical: the
# live source checkout held six agent worktrees under .claude/worktrees/ on 2026-09-03, a path
# that was untracked, unignored and unexcluded.
root=$(make_sync_fixture nested_repo); before=$(origin_head "$root")
local_before=$(git -C "$root/work" rev-parse HEAD)
rc=$(run_sync "$root")
assert 'exits non-zero, so OnFailure=agent-alert@%n.service fires' "[ '$rc' != 0 ]"
assert 'it says it is refusing, in those words' \
  "grep -q 'REFUSING to sync' '$root/run.log'"
# The path, not just the class. An alert naming only "a nested repository" is a second search.
assert 'and names the offending path' "grep -qx '  nested' '$root/run.log'"
assert 'origin is untouched' "[ \"\$(origin_head '$root')\" = '$before' ]"
assert 'and there is no local commit either' \
  "[ \"\$(git -C '$root/work' rev-parse HEAD)\" = '$local_before' ]"
# Fail-closed has to be RECOVERABLE. A left-behind index would let the next tick commit the
# gitlink through the ordinary path, turning one loud refusal into a quiet wrong push.
# Companion, not a detector: with the guard removed the commit succeeds and empties the index
# too, so this passes either way. It is here to catch a FUTURE guard that refuses without
# cleaning up — which would turn one loud refusal into a quiet wrong push on the next tick.
assert 'the index is reset, so the next tick starts clean' \
  "[ -z \"\$(git -C '$root/work' diff --cached --name-only)\" ]"

# The positive control, and the documented remedy: ignoring the nested repo restores normal
# behaviour on the very next run. Without this the guard could be a permanent 15-minute alert
# loop and every assertion above would still pass.
printf 'nested/\n' > "$root/work/.gitignore"
rc=$(run_sync "$root")
assert 'once the path is ignored, the next run syncs normally' "[ '$rc' = 0 ]"
assert 'carrying the .gitignore' \
  "git -C '$root/work' show --name-only --format= HEAD | grep -qx '.gitignore'"
# NOT merely "absent from the last commit" — that shape passes even when a guard-less run
# already pushed the gitlink one commit EARLIER, which is exactly what happened when this
# group was revert-tested. The question is whether a 160000 entry ever reached origin at
# all, so the whole pushed history is scanned.
assert 'and no gitlink ever reached origin, in any commit' \
  "! git -C '$root/origin.git' log --all --raw --format= | grep -qE '^:[0-7]{6} 160000'"
assert 'so origin advanced after all' "[ \"\$(origin_head '$root')\" != '$before' ]"

echo "--- auto-sync: it syncs the repo it LIVES in, not the caller's cwd ---"
# `cd "$(dirname "$0")/.."` is why the fixtures above work at all, and it is also the reason a
# stray copy of this script in another tree would quietly push THAT tree. Proven by running the
# fixture copy from an unrelated directory and checking which origin moved.
root=$(make_sync_fixture tracked_edit); before=$(origin_head "$root")
elsewhere=$(mktemp -d)
rc=0
( cd "$elsewhere" && bash "$root/work/bin/auto-sync" ) > "$root/run.log" 2>&1 || rc=$?
assert 'exits 0 when invoked from an unrelated cwd' "[ '$rc' = 0 ]"
assert "and it is the SCRIPT's repo that advanced" "[ \"\$(origin_head '$root')\" != '$before' ]"

exit $fail
