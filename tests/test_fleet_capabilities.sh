#!/usr/bin/env bash
# tests/test_fleet_capabilities.sh — S1 capability isolation: what each buzz-agent is offered
#
# The manifest `design/agents/<name>.toml` [surfaces.interactive] declares each agent's tools
# (a builtin family, a deny list, the bridge families it may call); bin/fleet_capabilities.py
# renders that into buzz-team/agent-settings-<name>.json and buzz-team/buzz-team-mcp-<name>;
# buzz-team/claude-agent-wrapper.sh and systemd/user/buzz-agent@.service are the seams that
# make a session load ONLY those. This suite joins the three: manifest == rendered artefact,
# artefact == what the bridge really advertises, seam == the flags that isolate.
#
# SOURCE, NOT THE BOX. Every subject is a file in this repo, so the suite runs anywhere and
# proves what a deploy would ship; the live half — the flags on the running `claude` child,
# the bridge's tools/list inside augustus's namespace — is buzz-team/verify-fleet.sh gates
# 14 and 15. tests/test_fleet_guards.sh reads the DEPLOYED copies and is the drift-side twin.
#
# FIXTURES FIRST. The renderer's `check` is proven to bite on a hand edit before it is
# credited for the committed tree, so a `check` that compares nothing cannot pass as clean.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFESTS="$REPO_ROOT/design/agents"
BT="$REPO_ROOT/buzz-team"
RENDER="$REPO_ROOT/bin/fleet_capabilities.py"
WRAPPER="$BT/claude-agent-wrapper.sh"
UNIT="$REPO_ROOT/systemd/user/buzz-agent@.service"
BASE_SETTINGS="$BT/agent-settings.json"
MANIFEST_TOML="$BT/MANIFEST.toml"
CONNECTORS="$REPO_ROOT/tests/fixtures/fleet-capabilities/claude-ai-connectors.txt"
QMD_STUB="$REPO_ROOT/tests/fixtures/buzz-team-mcp/qmd-stub.py"

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
fail=0

# pipefail has no place inside a boolean condition (see tests/test_pointer_skills.sh).
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}
is_empty() { [ -z "${!1}" ]; }
count_lines() { grep -c . || true; }

# name|harness|tools_deny,csv|bridge_tools,csv — one row per manifest. A pipe, not a tab:
# tab is IFS whitespace, and `read` collapses an EMPTY tools_deny field into the next one.
agent_rows() {
  python3 - "$MANIFESTS" <<'PY'
import pathlib, sys, tomllib
for p in sorted(pathlib.Path(sys.argv[1]).glob("*.toml")):
    d = tomllib.loads(p.read_text())
    i = d["surfaces"]["interactive"]
    print("|".join([p.stem, d["harness"], ",".join(i["tools_deny"]), ",".join(i["bridge_tools"])]))
PY
}

# The exec command of the wrapper as ONE line: continuation lines joined, so positions of
# "$@" and each flag can be compared.
wrapper_exec_line() {
  sed -n '/^exec /,/[^\\]$/p' "$WRAPPER" | sed 's/\\$//' | tr '\n' ' '
}

# Drive a shim as the harness would: initialize, tools/list, and one call. Prints
# `server <name>`, `tools <names,csv>`, and `call <isError> <first text>`.
probe_shim() {
  local shim=$1 call=$2
  BUZZ_QMD_MCP_COMMAND="$QMD_STUB" BUZZ_BRAVE_MCP_URL="http://127.0.0.1:1/mcp" \
  BUZZ_NOTION_SOCKET="$TMP/no-such.sock" python3 - "$shim" "$call" <<'PY'
import json, subprocess, sys
proc = subprocess.Popen([sys.argv[1]], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                        stderr=subprocess.DEVNULL, text=True, bufsize=1)
n = 0
def rpc(method, params=None):
    global n
    n += 1
    proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": n, "method": method, "params": params or {}}) + "\n")
    proc.stdin.flush()
    while True:
        line = proc.stdout.readline()
        if not line:
            raise SystemExit("bridge closed")
        msg = json.loads(line)
        if msg.get("id") == n:
            return msg
init = rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n"); proc.stdin.flush()
print("server", init["result"]["serverInfo"]["name"])
print("tools", ",".join(t["name"] for t in rpc("tools/list")["result"]["tools"]))
res = rpc("tools/call", {"name": sys.argv[2], "arguments": {}}).get("result", {})
print("call", str(res.get("isError", False)).lower(), (res.get("content") or [{}])[0].get("text", ""))
proc.stdin.close(); proc.wait(timeout=10)
PY
}

echo '--- 0. canary ---'
assert 'a found pattern is never reported as a failure' 'yes | grep -q y'

rows=$(agent_rows)
n_agents=$(count_lines <<<"$rows")
assert "the manifests carry an interactive block each (found $n_agents)" "[ '$n_agents' -ge 5 ]"

echo '--- 1. fixtures: the renderer'"'"'s check bites on a hand edit ---'
FX="$TMP/fx"
mkdir -p "$FX/bin" "$FX/design"
cp -r "$REPO_ROOT/design/agents" "$FX/design/"
cp -r "$BT" "$FX/buzz-team"
cp "$RENDER" "$FX/bin/"
assert 'the copied tree checks clean first' "python3 '$RENDER' check --repo '$FX' >/dev/null"
python3 - "$FX/buzz-team/agent-settings-aurelian.json" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]); d = json.loads(p.read_text())
d["permissions"]["deny"] = [x for x in d["permissions"]["deny"] if x != "Write"]
p.write_text(json.dumps(d, indent=2) + "\n")
PY
out=$(python3 "$RENDER" check --repo "$FX"); rc=$?
assert "a deny removed by hand from a rendered settings file is a red check (exit $rc)" "[ '$rc' = 1 ]"
assert 'and the diff names the file' "grep -q 'agent-settings-aurelian.json' <<<\"\$out\""
chmod -x "$FX/buzz-team/buzz-team-mcp-marcus"
assert 'a shim without its exec bit is named' "python3 '$RENDER' check --repo '$FX' | grep -q 'not executable: buzz-team/buzz-team-mcp-marcus'"
python3 - "$FX/design/agents/trajan.toml" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1]); p.write_text(p.read_text().replace('bridge_tools = ["qmd", "notion", "brave"]', 'bridge_tools = ["qmd"]', 1))
PY
assert 'a manifest edit with no re-render is a red check on both artefacts' \
  "python3 '$RENDER' check --repo '$FX' | grep -q 'buzz-team-mcp-trajan' && python3 '$RENDER' check --repo '$FX' | grep -q 'agent-settings-trajan.json'"

echo '--- 2. the committed artefacts are what the manifests render (::render-matches-committed) ---'
render_out=$(python3 "$RENDER" check --repo "$REPO_ROOT" 2>&1)
render_rc=$?
assert 'bin/fleet_capabilities.py check is clean on the committed tree' "[ '$render_rc' = 0 ]"
[ "$render_rc" = 0 ] || printf '%s\n' "$render_out" | sed 's/^/    /'

echo '--- 3. every per-agent settings file is a superset of the base, and only by what its manifest says (::settings-per-agent-superset) ---'
# The renderer proves shape; this joins the OUTPUT back to the manifest without the renderer
# in the loop: extra denies == tools_deny + every tool of each withheld bridge family, hooks
# untouched. A settings file laxer than the base is the one drift that matters.
superset_problems=$(python3 - "$REPO_ROOT" <<'PY'
import importlib.util, json, pathlib, sys, tomllib
repo = pathlib.Path(sys.argv[1]); bt = repo / "buzz-team"
spec = importlib.util.spec_from_file_location("bridge", bt / "buzz-team-mcp.py"); bridge = importlib.util.module_from_spec(spec); spec.loader.exec_module(bridge)
base = json.loads((bt / "agent-settings.json").read_text())
for m in sorted((repo / "design" / "agents").glob("*.toml")):
    d = tomllib.loads(m.read_text())
    if d["harness"] != "claude-agent-acp":
        continue
    name, i = m.stem, d["surfaces"]["interactive"]
    path = bt / f"agent-settings-{name}.json"
    if not path.is_file():
        print(f"{name}: no rendered settings file"); continue
    s = json.loads(path.read_text())
    deny, base_deny = s["permissions"]["deny"], base["permissions"]["deny"]
    for x in base_deny:
        if x not in deny:
            print(f"{name}: base deny {x} missing")
    if s.get("hooks") != base.get("hooks"):
        print(f"{name}: hooks differ from the base")
    expected = set(i["tools_deny"])
    for fam in bridge.FAMILIES:
        if fam not in i["bridge_tools"]:
            expected |= {f"mcp__buzz-team-mcp-{name}__{t}" for t in bridge.family_tools(fam)}
    extra = set(deny) - set(base_deny)
    if extra != expected:
        print(f"{name}: extra denies {sorted(extra ^ expected)} disagree with the manifest")
PY
)
assert 'every Claude agent'"'"'s settings file is base + exactly its manifest'"'"'s denies' "is_empty superset_problems"
[ -n "$superset_problems" ] && printf '%s\n' "$superset_problems" | sed 's/^/      /'

echo '--- 4. the wrapper'"'"'s flags come after "$@", so they win (::wrapper-flags-after-args) ---'
# The adapter emits --setting-sources=user,project,local and no --strict-mcp-config; for a
# single-value option the LAST occurrence wins, so a flag placed before "$@" is overridden
# by the adapter's own and reads as configured while doing nothing.
exec_line=$(wrapper_exec_line)
assert 'the wrapper has one exec line, passing "$@"' "grep -q '\"\$@\"' <<<\"\$exec_line\""
after_args=${exec_line#*\"\$@\"}
before_args=${exec_line%%\"\$@\"*}
for flag in --strict-mcp-config --setting-sources= --settings --plugin-dir; do
  assert "$flag sits after \"\$@\"" "grep -q -- ' $flag' <<<\"\$after_args\""
done
assert 'no flag precedes "$@"' "! grep -q -- ' --' <<<\"\$before_args\""

echo '--- 5. the isolating flags, and the seams that select per agent (::wrapper-strict-and-sources) ---'
assert '--strict-mcp-config: only the adapter'"'"'s --mcp-config (the bridge) loads' "grep -q -- '--strict-mcp-config' <<<\"\$exec_line\""
assert '--setting-sources= is EMPTY — no user/project/local file, only --settings applies' \
  "grep -q -- '--setting-sources= ' <<<\"\$exec_line\""
assert 'the settings file is agent-settings-$BUZZ_AGENT_NAME.json' \
  "grep -q '^SETTINGS=\"\$HOME/.config/buzz-team/agent-settings-\$BUZZ_AGENT_NAME.json\"$' '$WRAPPER' && grep -q -- '--settings \"\$SETTINGS\"' <<<\"\$exec_line\""
assert 'the skill tree is the deployed skills/$BUZZ_AGENT_NAME' \
  "grep -q '^SKILLS_DIR=\"\$HOME/agent-workforce/skills/\$BUZZ_AGENT_NAME\"$' '$WRAPPER' && grep -q -- '--plugin-dir \"\$SKILLS_DIR\"' <<<\"\$exec_line\""
assert 'the settings file is proved readable before exec' "grep -q '^\[ -r \"\$SETTINGS\" \] ||' '$WRAPPER'"
assert 'the plugin manifest is proved readable before exec (a missing --plugin-dir is silent)' \
  "grep -q '^\[ -r \"\$SKILLS_DIR/.claude-plugin/plugin.json\" \] ||' '$WRAPPER'"
assert 'the unit sets BUZZ_AGENT_NAME from %i' "grep -q '^Environment=\"BUZZ_AGENT_NAME=%i\"$' '$UNIT'"
assert 'the unit names the per-agent shim with --mcp-command' \
  "grep -q -- '--mcp-command %h/.config/buzz-team/buzz-team-mcp-%i' '$UNIT'"
# The guards, live: the wrapper refuses before it could exec claude.
probe=$(env -u BUZZ_AGENT_NAME sh "$WRAPPER" 2>&1); rc=$?
assert "without BUZZ_AGENT_NAME the wrapper refuses (exit $rc) and says why" \
  "[ '$rc' = 1 ] && grep -q 'BUZZ_AGENT_NAME is unset' <<<\"\$probe\""
probe=$(HOME="$TMP/nohome" BUZZ_AGENT_NAME=nobody sh "$WRAPPER" 2>&1); rc=$?
assert "an agent with no settings file is refused (exit $rc), naming the path" \
  "[ '$rc' = 1 ] && grep -q 'agent-settings-nobody.json' <<<\"\$probe\""
mkdir -p "$TMP/nohome/.config/buzz-team"; : > "$TMP/nohome/.config/buzz-team/agent-settings-nobody.json"
probe=$(HOME="$TMP/nohome" BUZZ_AGENT_NAME=nobody sh "$WRAPPER" 2>&1); rc=$?
assert "an agent with no skill tree is refused (exit $rc), not silently offered nothing" \
  "[ '$rc' = 1 ] && grep -q 'skills plugin not readable' <<<\"\$probe\""

echo '--- 6. one shim per manifest, naming its own families, adopted by the MANIFEST (::shim-per-agent) ---'
shim_problems=""
while IFS='|' read -r name harness _deny families; do
  shim="$BT/buzz-team-mcp-$name"
  [ -x "$shim" ] || shim_problems+="$name: no executable shim"$'\n'
  grep -qF "buzz-team-mcp.py\" --agent $name --tools $families \"\$@\"" "$shim" 2>/dev/null \
    || shim_problems+="$name: shim does not exec --agent $name --tools $families"$'\n'
  grep -q "^path = \"buzz-team-mcp-$name\"$" "$MANIFEST_TOML" || shim_problems+="$name: shim not adopted in MANIFEST.toml"$'\n'
  if [ "$harness" = claude-agent-acp ]; then
    grep -q "^path = \"agent-settings-$name.json\"$" "$MANIFEST_TOML" || shim_problems+="$name: settings not adopted in MANIFEST.toml"$'\n'
  else
    [ ! -e "$BT/agent-settings-$name.json" ] || shim_problems+="$name: a settings file for a harness that reads none"$'\n'
  fi
done <<<"$rows"
assert 'every agent has its shim and its MANIFEST rows, and no codex agent has a settings file' "is_empty shim_problems"
[ -n "$shim_problems" ] && printf '%s' "$shim_problems" | sed 's/^/      /'
orphans=$(for f in "$BT"/buzz-team-mcp-*; do n=${f##*/buzz-team-mcp-}; [ -f "$MANIFESTS/$n.toml" ] || echo "$n"; done)
assert "no shim exists for a name with no manifest (${orphans:-none})" "is_empty orphans"

echo '--- 7. what each shim really advertises is its manifest'"'"'s families (::bridge-filter-matches-manifest) ---'
# Spawned the way the harness spawns it, against a qmd stub and no brave/notion, and asked
# tools/list; the families of the names it returns must equal bridge_tools, and a call into a
# withheld family must be refused by the bridge itself — the shim is the mechanism on the
# codex side, where no settings deny backs it.
filter_problems=""
while IFS='|' read -r name _harness _deny families; do
  withheld=$(python3 -c "import sys; print(next((f for f in ('qmd','notion','brave') if f not in sys.argv[1].split(',')), ''))" "$families")
  probe_call=$([ -n "$withheld" ] && python3 -c "
import importlib.util, sys
spec = importlib.util.spec_from_file_location('b', '$BT/buzz-team-mcp.py'); b = importlib.util.module_from_spec(spec); spec.loader.exec_module(b)
print(b.family_tools('$withheld')[0])" || echo query)
  out=$(probe_shim "$BT/buzz-team-mcp-$name" "$probe_call" 2>&1)
  grep -qx "server buzz-team-mcp-$name" <<<"$out" || filter_problems+="$name: serverInfo is not buzz-team-mcp-$name"$'\n'
  listed=$(sed -n 's/^tools //p' <<<"$out" | tr ',' '\n' | python3 -c "
import sys
fam = lambda n: 'notion' if n.startswith('notion_') else 'brave' if n.startswith('brave_') else 'qmd'
print(','.join(sorted({fam(n) for n in sys.stdin.read().split() if n}, key=('qmd','notion','brave').index)))")
  [ "$listed" = "$families" ] || filter_problems+="$name: advertises [$listed], manifest says [$families]"$'\n'
  if [ -n "$withheld" ]; then
    grep -q "^call true .*is not offered to $name" <<<"$out" || filter_problems+="$name: a $withheld call ($probe_call) was not refused"$'\n'
  else
    grep -q "^call false " <<<"$out" || filter_problems+="$name: an offered call ($probe_call) was refused"$'\n'
  fi
done <<<"$rows"
assert "every shim's tools/list is its manifest's families, and a withheld family is refused at the call" "is_empty filter_problems"
[ -n "$filter_problems" ] && printf '%s' "$filter_problems" | sed 's/^/      /'

echo '--- 8. aurelian is enforced as declared: read paths, no writes, no Notion (::aurelian-deny-as-declared) ---'
aur=$(grep '^aurelian|' <<<"$rows")
assert 'the manifest withholds Edit, Write and NotebookEdit' "[ \"\$(cut -d'|' -f3 <<<\"\$aur\")\" = 'Edit,Write,NotebookEdit' ]"
assert 'and offers the bridge without notion' "[ \"\$(cut -d'|' -f4 <<<\"\$aur\")\" = 'qmd,brave' ]"
AUR_SETTINGS="$BT/agent-settings-aurelian.json"
denied() { jq -e --arg f "$1" '.permissions.deny | index($f)' "$AUR_SETTINGS" >/dev/null; }
for tool in Edit Write NotebookEdit; do
  assert "the rendered settings deny $tool" "denied $tool"
done
notion_n=$(jq -r '.permissions.deny[]' "$AUR_SETTINGS" | grep -c '^mcp__buzz-team-mcp-aurelian__notion_')
assert "every notion_* tool is denied under his own bridge namespace (7, found $notion_n)" "[ '$notion_n' = 7 ]"
for tool in Bash Read Glob Grep; do
  assert "$tool stays — he runs checks, he does not write" "! denied $tool"
done
others=$(while IFS='|' read -r name harness deny _f; do [ "$harness" = claude-agent-acp ] && [ "$name" != aurelian ] && [ -n "$deny" ] && echo "$name"; done <<<"$rows")
assert "no other Claude agent withholds a builtin (${others:-none do})" "is_empty others"

echo '--- 9. every claude.ai connector this account exposes is denied in the base (::connector-deny-complete) ---'
# From a fixture, not the network: the list is measured and dated in the file. Both
# directions, so a connector denied here but gone from the account is a stale fixture, and
# one on the account but not here is the hole the 2026-09-18 hotfix closed for Eden.
fixture_list=$(grep -v '^#' "$CONNECTORS" | grep .)
n_fix=$(count_lines <<<"$fixture_list")
assert "the fixture lists connectors at all (found $n_fix)" "[ '$n_fix' -ge 5 ]"
base_connectors=$(jq -r '.permissions.deny[] | select(startswith("mcp__claude_ai_"))' "$BASE_SETTINGS" | LC_ALL=C sort)
undenied=$(comm -23 <(LC_ALL=C sort <<<"$fixture_list") <(printf '%s\n' "$base_connectors") | tr '\n' ' ')
stale=$(comm -13 <(LC_ALL=C sort <<<"$fixture_list") <(printf '%s\n' "$base_connectors") | tr '\n' ' ')
assert "every measured connector is denied in the base (${undenied:-none missing})" "is_empty undenied"
assert "and no denied connector is absent from the measured list (${stale:-none stale})" "is_empty stale"

exit $fail
