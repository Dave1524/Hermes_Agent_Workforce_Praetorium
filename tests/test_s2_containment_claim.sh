#!/usr/bin/env bash
# design/agent-model.md §2 has one row for S2, the scheduled headless surface, and that row
# says what contains it. Until 2026-09-08 it said "explicit --allowedTools". Every runner in
# bin/run_*_cc.sh that invokes claude itself passes that flag under --permission-mode
# bypassPermissions (the rest are one-line exec delegators to such a sibling and carry no flags
# of their own), and under bypass an allowlist pre-approves, it does not restrict — measured 2026-09-01: Edit was absent from a
# runner's list and was used anyway (design/archive/open-decisions-closed-2026-09-07.md:258).
# What holds S2 is that no MCP server is loaded (--strict-mcp-config --mcp-config
# '{"mcpServers":{}}' — no connector tool exists in the session) plus agent_propose.sh's
# proposal write boundary. Anyone who drops --strict-mcp-config believing the allowlist is the
# guard removes containment with no error, which is why the row's wording is joined here.
#
# THE INVARIANTS.
#   1. Every bin/run_*_cc.sh carries the mechanism the row credits: --strict-mcp-config and
#      the empty mcpServers config — on a line that runs, never in a comment, or for a thin
#      delegator on the sibling its exec line names. The smoke suites assert the same on argv
#      for the runners they cover; this is the static join across ALL of them, named per runner.
#      Comment lines are dropped first because every direct runner's header names a sibling and
#      a flag quoted in a comment contains nothing; a checker reading whole files judged a
#      runner stripped of both flags as contained through its comment (found 2026-09-08).
#   2. Exactly one S2 row, and it names --strict-mcp-config.
#   3. While ANY runner passes bypassPermissions, the S2 row says the allowlist is `inert`.
#      T2.2 (docs/dev-plan-2026-09.md) takes the runners off bypass and rewrites the row; this
#      assertion goes vacuous then, and fires again only if a runner regains bypass while the
#      row claims a real allowlist. It never has to be edited for T2.2 to land.
#
# WHAT THIS DOES NOT ASSERT. That the allowlist is inert — that is measured, not testable from
# a checkout. That Bash is bounded under bypass — it is not, and T2.2's brief says what a bare
# Bash entry still permits. That the write boundary holds — tests/test_fleet_guards.sh
# ::propose-write-boundary owns that.
#
# FIXTURES FIRST, LIVE FILE SECOND. No box precondition: every checkout carries both inputs,
# so this suite never prints SKIP.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MODEL="$REPO_ROOT/design/agent-model.md"
BIN="$REPO_ROOT/bin"

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

# --- the checkers, one definition each, used on fixtures and on the live file --------------
# Each prints one offender per line, so a failure names its subject instead of only its count.

runners() {                   # $1 dir
  local f
  for f in "$1"/run_*_cc.sh; do [ -e "$f" ] && echo "$f"; done
  return 0
}

argv() {                      # $1 file — the lines that run; a flag in a comment is not a flag
  grep -vE '^[[:space:]]*#' "$1"
}

# Pipelines below end in a full reader (`grep >/dev/null`, `sort`), never `grep -q`: group 2
# calls these outside assert(), under pipefail, where an early exit reports 141 for a match.
bypass_runners() {            # $1 dir — runners that pass --permission-mode bypassPermissions
  local f
  while IFS= read -r f; do
    argv "$f" | grep -E -- '--permission-mode[[:space:]]+bypassPermissions' >/dev/null && echo "$f"
  done < <(runners "$1")
  return 0
}

contained() {                 # $1 runner file — carries both halves of the no-MCP mechanism
  argv "$1" | grep -- '--strict-mcp-config' >/dev/null \
    && argv "$1" | grep "'{\"mcpServers\":{}}'" >/dev/null
}

uncontained_runners() {       # $1 dir — runners missing either half of the no-MCP mechanism
  # A thin runner that execs a sibling run_*_cc.sh (run_daily_plan_cc.sh → run_daily_rhythm_cc.sh)
  # inherits that sibling's flags, so it is judged by the sibling — read from its exec line only;
  # a sibling named anywhere else is a mention, not a delegation. One level only, by design.
  local f d ok
  while IFS= read -r f; do
    ok=0
    if contained "$f"; then ok=1; else
      while IFS= read -r d; do
        [ -n "$d" ] && [ -e "$1/$d" ] && contained "$1/$d" && ok=1
      done < <(argv "$f" | grep -E '(^|[^A-Za-z0-9_])exec([^A-Za-z0-9_]|$)' | grep -oE 'run_[a-z0-9_]+_cc\.sh' \
                 | grep -vxF "$(basename "$f")" | LC_ALL=C sort -u)
    fi
    [ "$ok" = 1 ] || echo "$f"
  done < <(runners "$1")
  return 0
}

s2_row_defects() {            # $1 model file, $2 runner dir
  local rows n bypass
  rows=$(grep -E '^\| \*\*S2\*\* \|' "$1")
  n=$(grep -cE '^\| \*\*S2\*\* \|' "$1")
  if [ "$n" != 1 ]; then echo "expected one S2 row, found $n"; return 0; fi
  grep -q -- '--strict-mcp-config' <<<"$rows" || echo 'S2 row does not name --strict-mcp-config'
  bypass=$(bypass_runners "$2" | wc -l)
  if [ "$bypass" -gt 0 ] && ! grep -qw inert <<<"$rows"; then
    echo "S2 row does not say the allowlist is inert while $bypass runner(s) pass bypassPermissions"
  fi
  return 0
}

echo "--- 0. canary ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. fixtures: each failure mode is caught, a healthy pair is not ---"
fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT

mkdir -p "$fx/bypass" "$fx/nobypass" "$fx/nomcp"
cat >"$fx/bypass/run_a_cc.sh" <<'EOF'
exec claude -p "x" --permission-mode bypassPermissions --strict-mcp-config --mcp-config '{"mcpServers":{}}' --allowedTools "Bash,Read"
EOF
cat >"$fx/nobypass/run_a_cc.sh" <<'EOF'
exec claude -p "x" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --allowedTools "Bash,Read"
EOF
cat >"$fx/nomcp/run_a_cc.sh" <<'EOF'
exec claude -p "x" --permission-mode bypassPermissions --allowedTools "Bash,Read"
EOF
cp "$fx/bypass/run_a_cc.sh" "$fx/nomcp/run_b_cc.sh"
# a thin delegator to a contained sibling is contained; one to a missing sibling is not
echo 'exec "$(dirname "$0")/run_b_cc.sh" daily-plan' >"$fx/nomcp/run_c_cc.sh"
echo 'exec "$(dirname "$0")/run_zz_cc.sh" daily-plan' >"$fx/nomcp/run_d_cc.sh"
# a direct runner whose comment names a contained sibling and quotes both flags is judged on
# its own exec line: stripped, it is named
cat >"$fx/nomcp/run_e_cc.sh" <<'EOF'
# like run_b_cc.sh, which passes --strict-mcp-config --mcp-config '{"mcpServers":{}}'
exec claude -p "x" --permission-mode bypassPermissions --allowedTools "Bash,Read"
EOF
# a runner whose only bypass is in a comment is not a bypass runner (T2.2 leaves such comments)
cat >"$fx/nobypass/run_b_cc.sh" <<'EOF'
# was: --permission-mode bypassPermissions
exec claude -p "x" --strict-mcp-config --mcp-config '{"mcpServers":{}}' --allowedTools "Bash,Read"
EOF

cat >"$fx/credits.md" <<'EOF'
| # | Surface | Tool set |
| **S1** | Buzz | built-ins |
| **S2** | Scheduled headless CC | explicit `--allowedTools`; **no MCP** (`--strict-mcp-config`) |
EOF
cat >"$fx/inert.md" <<'EOF'
| **S2** | Scheduled headless CC | **no MCP** (`--strict-mcp-config --mcp-config '{"mcpServers":{}}'`); `--allowedTools` is passed but **inert** under `bypassPermissions` |
EOF
cat >"$fx/nostrict.md" <<'EOF'
| **S2** | Scheduled headless CC | `--allowedTools` is inert; the write boundary |
EOF
cat >"$fx/tworows.md" <<'EOF'
| **S2** | Scheduled headless CC | `--strict-mcp-config`; inert |
| **S2** | Scheduled headless CC | `--strict-mcp-config`; inert |
EOF

assert 'a row crediting the allowlist beside a bypass runner is named' \
  "s2_row_defects '$fx/credits.md' '$fx/bypass' | grep -q 'does not say the allowlist is inert while 1 runner'"
assert 'a row that says inert beside a bypass runner is silent' \
  "[ -z \"\$(s2_row_defects '$fx/inert.md' '$fx/bypass')\" ]"
assert 'a row crediting the allowlist beside NO bypass runner is silent (vacuous after T2.2)' \
  "[ -z \"\$(s2_row_defects '$fx/credits.md' '$fx/nobypass')\" ]"
assert 'a row that does not name --strict-mcp-config is named' \
  "s2_row_defects '$fx/nostrict.md' '$fx/nobypass' | grep -q 'does not name --strict-mcp-config'"
assert 'two S2 rows are named by count' \
  "s2_row_defects '$fx/tworows.md' '$fx/nobypass' | grep -q 'found 2'"
assert 'a runner missing the no-MCP flags, a delegator to a missing sibling and a stripped runner whose comment names a sibling are named; the contained sibling and its delegator are not' \
  "[ \"\$(uncontained_runners '$fx/nomcp' | tr '\n' ' ')\" = '$fx/nomcp/run_a_cc.sh $fx/nomcp/run_d_cc.sh $fx/nomcp/run_e_cc.sh ' ]"
assert 'a contained runner set is silent' \
  "[ -z \"\$(uncontained_runners '$fx/bypass')\" ]"
assert 'bypass runners are counted (delegators carry no flag of their own; a bypass in a comment is not one)' \
  "[ \"\$(bypass_runners '$fx/nomcp' | wc -l)\" = 3 ] && [ -z \"\$(bypass_runners '$fx/nobypass')\" ]"

echo "--- 2. the live model and runners: $MODEL, $BIN ---"
uncontained=$(uncontained_runners "$BIN")
defects=$(s2_row_defects "$MODEL" "$BIN")
n_runners=$(runners "$BIN" | wc -l)

assert "there are runners to join against ($n_runners)" "[ '$n_runners' -gt 0 ]"
assert "every runner carries --strict-mcp-config and the empty mcpServers config (${uncontained:-all do})" \
  "[ -z \"\$uncontained\" ]"
assert "the S2 row credits the no-MCP mechanism and, under bypass, calls the allowlist inert (${defects:-yes})" \
  "[ -z \"\$defects\" ]"

exit $fail
