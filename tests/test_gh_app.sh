#!/usr/bin/env bash
# bin/gh_app.sh — `gh` acting as the GitHub App this box pushes with (T8.2).
#
# Offline by contract: a fake credential helper stands in for github_app_credential.py and a
# fake `gh` on PATH records what reached it. Nothing here mints a token or touches GitHub.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in the shared assert(): `yes` is
# still writing when `grep -q` exits, so this fails if and only if a condition is evaluated
# under pipefail. It lives in every caller because the assert it guards is shared.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

GH_APP="$REPO_ROOT/bin/gh_app.sh"
TOKEN="ghs_fakeinstallationtoken0123456789"

# state -> a fixture root holding a fake helper (prints the token, or nothing) and a fake gh
# that writes its argv and the GH_TOKEN it saw to files the assertions read back.
make_fixture() {
  local state=$1 root
  root=$(mktemp -d)
  mkdir -p "$root/bin"
  cat > "$root/helper.py" <<PY
import sys
sys.stdin.read()
open("$root/helper.argv", "w").write(" ".join(sys.argv[1:]))
if "$state" == "token":
    print("username=x-access-token")
    print("password=$TOKEN")
PY
  cat > "$root/bin/gh" <<SH
#!/usr/bin/env bash
printf '%s\n' "\$@" > "$root/gh.argv"
printf '%s' "\${GH_TOKEN:-}" > "$root/gh.token"
echo "fake gh ran"
SH
  chmod +x "$root/bin/gh"
  echo "$root"
}

run_gh_app() {
  local root=$1; shift
  PATH="$root/bin:$PATH" GH_APP_HELPER="$root/helper.py" bash "$GH_APP" "$@"
}

echo '--- argv reaches gh untouched (::argv-passthrough) ---'
root=$(make_fixture token)
rc=0
run_gh_app "$root" pr create --title "a title with spaces" --body "" > "$root/out" 2>&1 || rc=$?
assert 'exits with gh'"'"'s status' "[ '$rc' = 0 ]"
printf '%s\n' pr create --title "a title with spaces" --body "" > "$root/expected.argv"
assert 'gh saw every argument, in order, spaces intact, the empty one included' \
  "cmp -s '$root/expected.argv' '$root/gh.argv'"
assert 'gh'"'"'s output is the caller'"'"'s output' "grep -q 'fake gh ran' '$root/out'"

echo '--- the token reaches gh through its environment only (::token-env-only) ---'
assert 'GH_TOKEN in gh'"'"'s environment is the minted token' "[ \"\$(cat '$root/gh.token')\" = '$TOKEN' ]"
assert 'the token is not in gh'"'"'s argv' "! grep -q '$TOKEN' '$root/gh.argv'"
assert 'the helper was asked to get, over the git-credential protocol' \
  "[ \"\$(cat '$root/helper.argv')\" = 'get' ]"

echo '--- the token never reaches stdout or stderr (::token-not-printed) ---'
assert 'success output carries no token' "! grep -q '$TOKEN' '$root/out'"

echo '--- an empty token refuses before gh runs (::empty-token-refuses) ---'
root=$(make_fixture empty)
rc=0
run_gh_app "$root" pr list > "$root/out" 2>&1 || rc=$?
assert 'exit 2' "[ '$rc' = 2 ]"
assert 'gh was never invoked' "[ ! -e '$root/gh.argv' ]"
assert 'the refusal names the helper' "grep -q 'helper.py' '$root/out'"

echo '--- a missing helper refuses the same way (::missing-helper-refuses) ---'
rc=0
PATH="$root/bin:$PATH" GH_APP_HELPER="$root/nowhere.py" bash "$GH_APP" pr list > "$root/out2" 2>&1 || rc=$?
assert 'exit 2' "[ '$rc' = 2 ]"
assert 'gh was never invoked' "[ ! -e '$root/gh.argv' ]"

exit $fail
