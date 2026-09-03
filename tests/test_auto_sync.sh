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
    # A tracked edit AND an unrelated untracked file. `git add -A` on line 32 does not
    # distinguish them, which is the hazard CLAUDE.md warns about in prose.
    mixed)          printf 'edited\n' >> "$work/tracked.md"
                    printf 'unrelated WIP\n' > "$work/scratch.md" ;;
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
root=$(make_sync_fixture clean); before=$(origin_head "$root")
rc=$(run_sync "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'says so' "grep -q 'working tree clean. Nothing to do' '$root/run.log'"
assert 'and creates no commit' "[ \"\$(origin_head '$root')\" = '$before' ]"

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

echo "--- auto-sync: PINNED FAIL-OPEN — an untracked-only tree reports CLEAN ---"
# Characterization, not approval. Line 24 gates on `git diff --quiet && git diff --cached
# --quiet`, and neither looks at untracked files — while line 32 is `git add -A`, which would
# have committed them. So a tree holding ONLY new files takes the early return and prints
# "working tree clean. Nothing to do", every 15 minutes, indefinitely.
#
# The consequence is not a lost edit but a DELAYED one with a wrong author story: the new file
# sits unsynced until some tracked file happens to change, and is then swept in by `git add -A`
# under an `Auto-sync:` subject dated days after it was written. A whole new script — the exact
# thing this repo adds most often — is invisible to origin the entire time, and the log says
# "Nothing to do" in a voice that sounds like it looked.
#
# `git status --porcelain` is the one-character-per-line fix. Tracked as W16 in
# design/open-decisions.md. Verified 2026-09-03 against bin/auto-sync:24.
#
# WHEN THIS IS FIXED THESE THREE GO RED. That is the intent — read the row, then rewrite them
# to the tracked_edit shape above.
root=$(make_sync_fixture untracked_only); before=$(origin_head "$root")
rc=$(run_sync "$root")
assert 'W16: exits 0' "[ '$rc' = 0 ]"
assert 'W16: reports the tree CLEAN while holding an uncommitted new file' \
  "grep -q 'working tree clean. Nothing to do' '$root/run.log' && [ -f '$root/work/bin/newly_added.sh' ]"
assert 'W16: so origin never receives it' "[ \"\$(origin_head '$root')\" = '$before' ]"
# The positive control that dates the gap: git itself sees the file the script does not.
assert 'W16: and git status --porcelain DOES see it (the one-line fix)' \
  "git -C '$root/work' status --porcelain | grep -q '^?? bin/newly_added.sh\$'"

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
