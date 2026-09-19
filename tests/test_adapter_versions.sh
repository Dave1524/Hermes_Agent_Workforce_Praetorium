#!/usr/bin/env bash
# bin/adapter_versions.py: installed vs published for the three fleet packages, compared
# without a registry (the two --*-from fixtures), and the INFO rows check-loaded.sh renders
# from it. Stale is a verdict word, never an exit code: the upgrade is the operator's
# canary procedure (docs/runbook.md), so nothing here may go red for a version number.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/adapter_versions.py"
FX="$REPO_ROOT/tests/fixtures/adapter-versions"
CHECKER="$REPO_ROOT/buzz-team/check-loaded.sh"
fail=0
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail); set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

echo '--- 0. canary ---'
assert 'a true piped condition reads as true' 'yes | grep -q y'

echo '--- 1. the compare, from fixtures (::adapter-versions-compare) ---'
out=$(python3 "$SCRIPT" --installed-from "$FX/npm-ls.json" --latest-from "$FX/latest.json"); rc=$?
assert "exit 0 with a stale package in the list (rc=$rc)" "[ '$rc' = 0 ]"
assert 'claude-agent-acp reads stale, both versions named' \
  "grep -qx '@agentclientprotocol/claude-agent-acp installed=0.64.0 latest=0.79.0 stale' <<<\"\$out\""
assert 'codex-acp reads current' "grep -qx '@agentclientprotocol/codex-acp installed=1.1.9 latest=1.1.9 current' <<<\"\$out\""
assert 'exactly the three fleet packages, never the rest of npm -g' "[ \"\$(wc -l <<<\"\$out\")\" = 3 ] && ! grep -q corepack <<<\"\$out\""
out=$(python3 "$SCRIPT" --installed-from "$FX/npm-ls.json" --offline)
assert '--offline: latest is unavailable and the verdict unknown, not stale' \
  "grep -qx '@agentclientprotocol/claude-agent-acp installed=0.64.0 latest=unavailable unknown' <<<\"\$out\""
out=$(python3 "$SCRIPT" --installed-from "$FX/npm-ls.json" --latest-from "$FX/latest.json" --json)
assert '--json carries the same rows' "python3 -c 'import json,sys; r=json.loads(sys.argv[1]); assert [x[\"verdict\"] for x in r]==[\"stale\",\"current\",\"current\"]' \"\$out\""
out=$(python3 "$SCRIPT" --installed-from "$FX/nope.json" 2>&1); rc=$?
assert "an unreadable installed list is the one exit 1 (rc=$rc), said out loud" "[ '$rc' = 1 ] && grep -q 'cannot read the installed list' <<<\"\$out\""

echo '--- 2. check-loaded renders INFO rows and never a verdict from them (::adapter-versions-info-row) ---'
rows=$(ADAPTER_VERSIONS="$SCRIPT" ADAPTER_VERSIONS_ARGS="--installed-from $FX/npm-ls.json --latest-from $FX/latest.json" \
  bash -c '. "$1"; status=0; check_adapters; echo "status=$status"' _ "$CHECKER")
assert 'three INFO rows, short package names' "[ \"\$(grep -c '^  INFO ' <<<\"\$rows\")\" = 3 ] && grep -q 'INFO     claude-agent-acp 0.64.0 installed, 0.79.0 on npm — stale' <<<\"\$rows\""
assert 'a stale row leaves status 0' "grep -qx 'status=0' <<<\"\$rows\""
rows=$(ADAPTER_VERSIONS="$FX/missing.py" bash -c '. "$1"; status=0; check_adapters; echo "status=$status"' _ "$CHECKER")
assert 'an undeployed script is one INFO row naming the path, status 0' "grep -q 'INFO     adapters   not deployed' <<<\"\$rows\" && grep -qx 'status=0' <<<\"\$rows\""
assert 'the rows run only on the whole-fleet invocation' "grep -B2 -A0 'check_adapters$' '$CHECKER' | grep -q 'mapfile -t names'"

exit $fail
