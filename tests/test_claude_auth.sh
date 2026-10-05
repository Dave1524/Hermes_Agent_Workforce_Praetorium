#!/usr/bin/env bash
# The headless Claude auth path: the token reader, the probe, and the rule that every claude
# this box launches goes through a seam that reads the token. Offline — stub claudes only.
#
# A claude launched around bin/cc_run.sh and buzz-team/claude-agent-wrapper.sh still works
# today: it falls back to the interactive login. That is exactly the failure — on the day Dave
# mints a headless token, such a runner is the one that still dies with the next /login lapse,
# and nothing says so. The scan below makes it red the day it is written.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
REPO_ROOT=$(pwd)
PROBE="$REPO_ROOT/bin/claude_auth_probe.sh"
HELPER="$REPO_ROOT/bin/claude_oauth_env.sh"
WORK=$(mktemp -d "${TMPDIR:-/tmp}/claude-auth.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

fail=0
assert() {
  local desc=$1 cond=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$cond"; then echo "  ok: $desc"; else echo "  FAIL: $desc"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo '--- every claude launch in bin/ and buzz-team/ goes through a token seam (::claude-launch-through-seams) ---'
# A launch is a non-comment line that runs "$CLAUDE_BIN" or "$BREW/claude"; `[ -x … ]` is a
# probe of the path, not a launch. It is through a seam when the line hands it to cc_run.sh.
# The seams themselves are exempt, and so is a script that reads the token itself — named
# here, and held to sourcing the reader.
SEAMS="bin/cc_run.sh buzz-team/claude-agent-wrapper.sh"
SELF_SET="bin/agent_config_eval.sh"
launches() {
  local f
  for f in bin/* buzz-team/*; do
    [ -f "$f" ] || continue
    head -c 200 "$f" | grep -qE '^#!.*(ba)?sh' || continue
    case " $SEAMS $SELF_SET " in *" $f "*) continue ;; esac
    grep -nE '"\$(CLAUDE_BIN|BREW/claude)"' "$f" | grep -vE '^[0-9]+:[[:space:]]*#' \
      | grep -vE '\[ -x "\$CLAUDE_BIN" \]' | grep -v 'cc_run\.sh' | sed "s|^|$f:|"
  done
}
bypass=$(launches)
assert 'no runner launches claude around the seams' "[ -z \"\$bypass\" ]"
[ -n "$bypass" ] && printf '      %s\n' "$bypass"
assert 'the scan sees launches at all (the runners hand "$CLAUDE_BIN" to cc_run.sh)' \
  "[ \"\$(grep -lE 'cc_run\\.sh\" \"\\\$CLAUDE_BIN\"' bin/run_*_cc.sh | wc -l)\" -ge 9 ]"
for f in $SELF_SET; do
  assert "$f reads the token itself" "grep -q 'claude_oauth_env.sh\"\$' '$f' && grep -qx 'claude_oauth_export' '$f'"
done
assert 'cc_run.sh sources the reader before either exec' \
  "awk '/^claude_oauth_export/{t=NR} /^[[:space:]]*exec \"\\\$@\"/{if(!e)e=NR} END{exit !(t && t<e)}' bin/cc_run.sh"
assert 'the wrapper sources the reader before it execs claude' \
  "awk '/^claude_oauth_export/{t=NR} /^exec /{e=NR} END{exit !(t && t<e)}' buzz-team/claude-agent-wrapper.sh"

echo '--- the token file is parsed, mode-checked and never printed (::oauth-helper-file) ---'
reader() { env -u CLAUDE_CODE_OAUTH_TOKEN CLAUDE_OAUTH_FILE="$1" sh -c ". '$HELPER'; claude_oauth_export; printf '%s|%s' \"\${CLAUDE_CODE_OAUTH_TOKEN:-}\" \"\$(claude_oauth_expiry)\""; }
tok="$WORK/claude_oauth.env"
assert 'no file: nothing exported, no expiry, silent' "[ \"\$(reader '$tok' 2>&1)\" = '|' ]"
printf 'CLAUDE_CODE_OAUTH_TOKEN=sk-one\nCLAUDE_OAUTH_MINTED=2026-10-06\nCLAUDE_OAUTH_EXPIRES="2027-10-06"\n' >"$tok"; chmod 600 "$tok"
assert 'mode 600: token and expiry read, quotes stripped' "[ \"\$(reader '$tok' 2>/dev/null)\" = 'sk-one|2027-10-06' ]"
printf 'CLAUDE_CODE_OAUTH_TOKEN=$(touch %s/ran)\n' "$WORK" >"$tok"; chmod 600 "$tok"; reader "$tok" >/dev/null 2>&1
assert 'the file is parsed, never sourced (nothing in it runs)' "[ ! -e '$WORK/ran' ]"
printf 'CLAUDE_CODE_OAUTH_TOKEN=sk-two\n' >"$tok"; chmod 640 "$tok"
out=$(reader "$tok" 2>&1)
assert 'group-readable: refused out loud, token neither used nor printed' \
  "[[ \"\$out\" == *'not mode 600'* ]] && [[ \"\$out\" != *sk-two* ]] && [[ \"\$out\" == *'|' ]]"
printf 'CLAUDE_OAUTH_EXPIRES=2027-01-01\n' >"$tok"; chmod 600 "$tok"
out=$(reader "$tok" 2>&1)
assert 'a file with no token says so and exports nothing' "[[ \"\$out\" == *'carries no CLAUDE_CODE_OAUTH_TOKEN'* ]] && [[ \"\$out\" == *'|2027-01-01' ]]"

echo '--- the probe: one real turn, three verdicts, unknown is never a refusal (::auth-probe-outcomes) ---'
fake() {  # fake <stdout> <rc>
  printf '#!/usr/bin/env bash\nprintf "%%s\\n" "%s"\nexit %s\n' "$1" "$2" >"$WORK/claude"; chmod +x "$WORK/claude"
}
probe() { CLAUDE_BIN="$WORK/claude" CLAUDE_AUTH_PROBE_TIMEOUT=10 bash "$PROBE"; }
fake CLAUDE_AUTH_OK 0; out=$(probe); rc=$?
assert 'the sentinel back is ok (exit 0)' "[ $rc = 0 ] && [[ \"\$out\" == 'claude-auth: ok '* ]]"
fake 'OAuth session expired and could not be refreshed' 1; out=$(probe); rc=$?
assert 'an OAuth refusal is refused (exit 3), quoting the line' "[ $rc = 3 ] && [[ \"\$out\" == *'refused — OAuth session expired'* ]]"
fake 'Failed to authenticate. API Error: 401' 0; out=$(probe); rc=$?
assert 'a refusal with exit 0 is still refused' "[ $rc = 3 ]"
fake 'API Error: 529 overloaded_error' 1; out=$(probe); rc=$?
assert 'any other failure is unknown (exit 1), not refused' "[ $rc = 1 ] && [[ \"\$out\" == 'claude-auth: unknown'* ]]"
fake 'something else' 0; out=$(probe); rc=$?
assert 'exit 0 without the sentinel is unknown' "[ $rc = 1 ]"
printf '#!/usr/bin/env bash\nprintf "%%s\\n" "$@" > "%s/argv"\nprintf "%%s" "${AGENT_USAGE_JSON:-unset}" > "%s/usage"\necho CLAUDE_AUTH_OK\n' "$WORK" "$WORK" >"$WORK/claude"
AGENT_USAGE_JSON="$WORK/clobber.json" CLAUDE_BIN="$WORK/claude" bash "$PROBE" >/dev/null
assert 'it goes through cc_run.sh without touching the caller'"'"'s usage envelope' "[ \"\$(cat '$WORK/usage')\" = unset ] && [ ! -e '$WORK/clobber.json' ]"
assert 'and offers the turn no MCP server' "grep -qx -- '--strict-mcp-config' '$WORK/argv'"

echo '--- classify reads the whole stream, so pipefail cannot hide a refusal (::auth-probe-classify) ---'
set -o pipefail
{ seq 1 200000; echo 'buzz_acp: OAuth session expired and could not be refreshed'; } | bash "$PROBE" classify >/dev/null; rc=$?
assert 'a refusal after a long stream is found under pipefail (exit 3, not 141)' "[ $rc = 3 ]"
seq 1 200000 | bash "$PROBE" classify >/dev/null; rc=$?
assert 'a clean stream is 0' "[ $rc = 0 ]"
set +o pipefail

[ "$fail" = 0 ] && echo "PASS: claude_auth" || { echo "FAIL: claude_auth"; exit 1; }
