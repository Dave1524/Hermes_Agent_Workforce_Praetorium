#!/usr/bin/env bash
# Fleet guard suite — the assertion half of D1 (design/open-decisions.md D1, D9).
#
# Every `enforced = true` must_not rule in design/agents/*.toml claims a mechanism blocks
# it. This suite is what makes that claim non-forgeable: each such rule names an assertion
# id here, and the last group checks the reverse direction — a flag with nothing asserting
# it is a red gate, not a green one.
#
# THE CONSTRAINT THAT GOVERNS EVERY ASSERTION BELOW: a negative test asserts the ABSENCE OF
# CAPABILITY. It never attempts the forbidden action. You cannot test "must not send email"
# by sending email — the test would BE the violation, and a "safe" recipient is still an
# outward action from a box whose entire charter is that it performs none. So every
# assertion here reads the state of a mechanism: a config key, an installed hook, an absent
# credential, a namespace that lacks a path.
#
# Most of what it asserts lives OUTSIDE this repo — ~/.claude/settings.json, a .git/hooks
# file in two other clones, a bwrap wrapper in /usr/local/bin, a --user unit. That is
# deliberate, and it is the reason the suite exists: this repo's commits cannot see those
# files move, so a test is the only thing that fails loudly when the far side does.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BASE_SETTINGS="$HOME/.claude/settings.json"
STRICT_SETTINGS="$HOME/.config/buzz-team/agent-settings.json"
WRAPPER="$HOME/.config/buzz-team/claude-agent-wrapper.sh"
UNIT="$HOME/.config/systemd/user/buzz-agent@.service"
AUGUSTUS_DROPIN="$HOME/.config/systemd/user/buzz-agent@augustus.service.d/harness.conf"
CODEX_ACP=/usr/local/bin/codex-acp
AGENT_TABLE="$REPO_ROOT/bin/buzz_agents.env"
PROPOSE="$REPO_ROOT/bin/agent_propose.sh"
SUITE_DECL="$REPO_ROOT/design/fleet-suites.toml"

# Every group below reads a file outside this repo (see the header). Off the box there is
# nothing to assert against, so the suite skips whole rather than reporting the absent
# fleet as a broken one.
# shellcheck source=tests/box_precondition.sh
. "$(dirname "$0")/box_precondition.sh"
box_only 'the live fleet state this suite asserts' \
  "$BASE_SETTINGS" "$STRICT_SETTINGS" "$UNIT" || exit 77

fail=0

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

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# Conditions that need literal `$` or nested quotes go in a function rather than through
# eval's quoting — an assertion nobody can read is an assertion nobody can correct.
denied_in_strict() { jq -e --arg f "$1" '.permissions.deny | index($f)' "$STRICT_SETTINGS" >/dev/null; }
# Multi-line findings must be tested through a global, never interpolated into the condition
# string — `[ -z "$x" ]` with an embedded newline reaches test(1) as several arguments and
# dies "too many arguments", which is a suite bug wearing a failing assertion's clothes.
is_empty() { [ -z "${!1}" ]; }
lists_line() { printf '%s\n' "${!1}" | grep -qx "$2"; }
wrapper_execs_strict_settings() { grep -q '^exec .*--settings .*agent-settings\.json' "$WRAPPER"; }
codex_acp_tmpfs_over_ssh() { grep -qF -- '--tmpfs "$HOME/.ssh"' "$CODEX_ACP"; }
augustus_runs_codex_harness() { grep -qF 'Environment="BUZZ_ACP_AGENT_COMMAND=/usr/local/bin/codex-acp"' "$AUGUSTUS_DROPIN"; }
propose_scopes_violations() { grep -qF "grep -v \"^_inbox/agents/\"" "$PROPOSE"; }
propose_discards_on_violation() { grep -qF 'reset --hard -q' "$PROPOSE"; }

echo '--- outward connectors are denied for agent sessions (::connector-deny) ---'
# The seam is CLAUDE_CODE_EXECUTABLE, not --settings in BUZZ_ACP_AGENT_ARGS: buzz-acp's
# index.js parses only --version/-v from argv, so the flag there would be accepted and
# ignored — configured-looking and inert.
assert 'the strict settings file exists' "[ -f '$STRICT_SETTINGS' ]"
assert 'the strict settings file is valid JSON' "jq -e . '$STRICT_SETTINGS' >/dev/null"
for family in mcp__claude_ai_Gmail mcp__claude_ai_Microsoft_365 mcp__claude_ai_Google_Drive mcp__claude_ai_Figma; do
  assert "$family is denied for agent sessions" "denied_in_strict '$family'"
done
assert 'the agent wrapper exists' "[ -f '$WRAPPER' ]"
# Without the exec bit the SDK reports "exists but failed to launch", which reads as a
# broken install rather than an unenforced policy.
assert 'the agent wrapper is executable' "[ -x '$WRAPPER' ]"
assert 'the wrapper execs claude with the strict settings file' "wrapper_execs_strict_settings"

unit_code() { grep -v '^[[:space:]]*#' "$UNIT"; }
assert 'the agent unit exists' "[ -f '$UNIT' ]"
assert 'the unit sets CLAUDE_CODE_EXECUTABLE in Environment=, not on ExecStart' \
  "unit_code | grep -q '^Environment=\"CLAUDE_CODE_EXECUTABLE='"
# A value on ExecStart cannot be overridden from a drop-in — the unit's own comments say
# so, and it is why every BUZZ_ACP_* var moved off ExecStart in August.
assert 'CLAUDE_CODE_EXECUTABLE is absent from ExecStart' \
  "! unit_code | grep -q 'ExecStart.*CLAUDE_CODE_EXECUTABLE'"

exec_path=$(sed -n 's/^Environment="CLAUDE_CODE_EXECUTABLE=\(.*\)"$/\1/p' "$UNIT" | sed "s|^%h|$HOME|")
assert 'CLAUDE_CODE_EXECUTABLE names the agent wrapper' "[ '$exec_path' = '$WRAPPER' ]"
assert 'CLAUDE_CODE_EXECUTABLE resolves to a file that exists and is executable' \
  "[ -n '$exec_path' ] && [ -x '$exec_path' ]"

echo '--- augustus never had the claude.ai connector surface (::augustus-no-claude-connectors) ---'
# augustus is on codex-acp inside bwrap. The claude.ai OAuth connectors are a Claude Code
# surface he has never had, so the strict settings file neither reaches him nor needs to —
# and must NOT be credited for him. Crediting the wrong mechanism is the defect D3 found in
# agent-model.md §2/§6.1. What IS checkable is that his harness is still not Claude's: if
# he were ever moved onto claude-agent-acp, this goes red and his rule needs the strict file.
assert 'augustus has a harness drop-in' "[ -f '$AUGUSTUS_DROPIN' ]"
assert 'augustus runs the codex harness, not claude-agent-acp' "augustus_runs_codex_harness"

echo '--- the strict file is a superset of the base file (::deny-superset) ---'
# Written as a superset deliberately, so it is correct whether --settings merges or
# replaces. This assertion is what makes that hold: it fails red when a deny is added to
# ~/.claude/settings.json and not mirrored here, which is the only way the two can drift
# into agents being LESS restricted than Dave.
missing_denies=$(python3 - "$BASE_SETTINGS" "$STRICT_SETTINGS" <<'PY'
import json, sys

def denies(path):
    with open(path) as fh:
        return json.load(fh).get("permissions", {}).get("deny", [])

try:
    base, strict = denies(sys.argv[1]), set(denies(sys.argv[2]))
except Exception as exc:                      # unreadable is a failure, not a pass
    print(f"unreadable: {exc}")
    sys.exit(0)

for entry in base:
    if entry not in strict:
        print(entry)
PY
)
assert 'every deny in ~/.claude/settings.json is present in the strict file' "is_empty missing_denies"
[ -n "$missing_denies" ] && echo "      missing from strict: $missing_denies"

echo '--- the vault main-push guard is installed in every vault clone (::vault-push-guard) ---'
# Discover the clones; do not hardcode the two known paths. A hand-maintained whitelist is
# the exact defect class this repo keeps rediscovering — a check that asks a list whether
# it is fine cannot fail. Rule: a git clone under ~/dev that contains 00_system/ and has a
# push remote.
clones=()
for candidate in "$HOME"/dev/*/; do
  [ -d "$candidate/00_system" ] || continue
  git -C "$candidate" rev-parse --git-common-dir >/dev/null 2>&1 || continue
  git -C "$candidate" remote -v 2>/dev/null | grep '(push)' >/dev/null || continue
  clones+=("$(cd "$candidate" && pwd)")
done
assert 'at least one vault clone with a push remote was discovered' "[ ${#clones[@]} -ge 1 ]"

for clone in ${clones[@]+"${clones[@]}"}; do
  common_dir=$(git -C "$clone" rev-parse --git-common-dir)
  case "$common_dir" in /*) ;; *) common_dir="$clone/$common_dir" ;; esac
  hook="$common_dir/hooks/pre-push"
  name=${clone##*/}
  assert "$name: a pre-push hook is installed" "[ -f '$hook' ]"
  assert "$name: the pre-push hook is executable" "[ -x '$hook' ]"
  assert "$name: the pre-push hook is the main-push guard" "grep -q 'vault-main-push-guard' '$hook'"
done

# A vault clone living outside ~/dev would be missed by the loop above and its absence
# would look identical to "no such clone". ~/vault is the one path that names the clone the
# running qmd daemon actually serves, so it is the control on the discovery rule itself.
vault_target=$(readlink -f "$HOME/vault" 2>/dev/null || true)
clone_list=$(printf '%s\n' ${clones[@]+"${clones[@]}"})
assert '~/vault resolves to a clone the discovery rule found' \
  "[ -n '$vault_target' ] && lists_line clone_list '$vault_target'"

echo '--- aurelian is unaddressable by scheduled delivery (::aurelian-unaddressable) ---'
# Absence from the slug table is the whole mechanism: bin/deliver.sh resolves a notify slug
# to a pubkey here, and every ~/.config/buzz-team/*.toml runs require_mention = true, so an
# event that cannot carry his `p` tag reaches him never.
assert 'the agent slug table exists' "[ -f '$AGENT_TABLE' ]"
assert 'aurelian appears nowhere in the slug table' "! grep -qi 'aurelian' '$AGENT_TABLE'"

echo '--- the proposal write boundary still holds (::propose-write-boundary) ---'
# Covers marcus and claudius, who share it: agent_propose.sh is the only path either has
# into the vault, and it discards the whole worktree rather than committing the safe part
# of a violating change.
assert 'agent_propose.sh exists' "[ -f '$PROPOSE' ]"
assert 'it counts anything outside _inbox/agents/ as a violation' "propose_scopes_violations"
assert 'a violation hard-resets the worktree rather than committing part of it' "propose_discards_on_violation"
assert 'a violation exits non-zero' \
  "grep -A6 'FATAL: agent touched files outside' '$PROPOSE' | grep -q 'exit 1'"

echo '--- augustus has no ssh credential inside his namespace (::augustus-no-fetch) ---'
# The bwrap wrapper mounts an empty tmpfs over ~/.ssh, so his namespace has neither the
# deploy keys nor the Host aliases from ~/.ssh/config. Never fix a fetch failure by
# widening this: anything his tooling can read, his shell can read.
assert 'the codex-acp bwrap wrapper exists' "[ -f '$CODEX_ACP' ]"
assert 'it mounts an empty tmpfs over ~/.ssh, so git fetch has no credential' "codex_acp_tmpfs_over_ssh"

echo '--- every enforced flag is backed by an assertion that exists (::enforced-has-test) ---'
# D9's redefinition, made machine-checkable: `enforced = true` iff a machine-checkable
# artifact exists whose removal or absence a test can detect. This group is the reverse
# direction — it reads the manifests and proves each flag names an assertion id that is
# really in the file it names. Without it, `enforced = true` is a string anyone can type.
manifest_problems=$(python3 - "$REPO_ROOT" "$SUITE_DECL" <<'PY'
import pathlib, sys, tomllib

repo = pathlib.Path(sys.argv[1])
decl = pathlib.Path(sys.argv[2])
problems = []

def load(path):
    with path.open("rb") as fh:
        return tomllib.load(fh)

for manifest in sorted((repo / "design" / "agents").glob("*.toml")):
    try:
        data = load(manifest)
    except Exception as exc:
        problems.append(f"{manifest.name}: does not parse: {exc}")
        continue
    for entry in data.get("must_not", []):
        rule = entry.get("rule", "<unnamed>")
        if not entry.get("enforced"):
            continue
        if not entry.get("why"):
            problems.append(f"{manifest.name}: '{rule}' is enforced with no why")
        ref = entry.get("test")
        if ref is None:
            # An exemption is a declared hole, readable and greppable. Silence is not.
            if not entry.get("test_exempt"):
                problems.append(f"{manifest.name}: '{rule}' is enforced but names no test")
            continue
        if "::" not in ref:
            problems.append(f"{manifest.name}: '{rule}' test '{ref}' names no assertion id")
            continue
        rel, assertion = ref.split("::", 1)
        target = repo / rel
        if not target.is_file():
            problems.append(f"{manifest.name}: '{rule}' names missing suite {rel}")
        elif f"::{assertion}" not in target.read_text():
            problems.append(f"{manifest.name}: '{rule}' names absent assertion ::{assertion} in {rel}")

# design/fleet-suites.toml gives D6's coverage checker a second valid owner value. Without
# it, brief 3's checker classifies this suite as an orphan and its first act is to
# recommend deleting the security tests.
if not decl.is_file():
    problems.append(f"{decl.name}: missing")
else:
    try:
        suites = load(decl).get("suite", [])
    except Exception as exc:
        problems.append(f"{decl.name}: does not parse: {exc}")
        suites = []
    if not suites:
        problems.append(f"{decl.name}: declares no suite")
    for suite in suites:
        path = suite.get("path", "")
        if not path or not (repo / path).is_file():
            problems.append(f"{decl.name}: declares missing path '{path}'")
        if not suite.get("owner"):
            problems.append(f"{decl.name}: '{path}' declares no owner")
        if not suite.get("asserts"):
            problems.append(f"{decl.name}: '{path}' declares no asserts")
    this_suite = "tests/test_fleet_guards.sh"
    if not any(s.get("path") == this_suite and s.get("owner") == "fleet" for s in suites):
        problems.append(f"{decl.name}: {this_suite} is not declared with owner = \"fleet\"")

print("\n".join(problems))
PY
)
assert 'every enforced rule names an assertion that exists, and this suite is declared to D6' \
  "is_empty manifest_problems"
[ -n "$manifest_problems" ] && printf '      %s\n' "$manifest_problems"

exit $fail
