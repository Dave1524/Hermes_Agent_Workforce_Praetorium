#!/bin/bash
# Machine-level verification gate for the buzz-agent fleet.
#
# `set -e` is deliberately absent: every assertion must run and report, or a red
# gate names only the first failure instead of all of them.
set -uo pipefail
export LC_ALL=C

AGENTS=(marcus claudius trajan augustus aurelian)

declare -A EXPECT_HARNESS=(
  [marcus]=claude-agent-acp
  [claudius]=claude-agent-acp
  [trajan]=claude-agent-acp
  [augustus]=codex-acp
  [aurelian]=claude-agent-acp
)

DAVE_PUBKEY=82cfc202fce4103742578f8f23849eb616f7ef96ca59a1b13a70d720a9be616f
MARCUS_PUBKEY=abbc19ddcc22f6511183936a4993359d4d22c6ef5afc53c7dba65bdeb958916b
# The scheduled-delivery publishing identity. It has no runtime, so it is a source of
# work and never a return edge — admitting it cannot close a cycle.
PRAETORIUM_PUBKEY=b0a6d15f871ab8c502029e57e0fddec3ddecb09846ffdf6a56b6515bd1906fcd
# The three workers. Named here only because they are the authors aurelian admits: a
# worker may submit its own output for review without routing the artifact through
# Marcus first. No other agent's rules mention them.
CLAUDIUS_PUBKEY=818238434309416fa7fd8cc482908e61f8ebcb6978ff974ccf2044d4ed014c7c
TRAJAN_PUBKEY=1212e9a7e5a2c41b4e56d266fe2b42bb1e528cfa58a482975b9e5ba4d389fab0
AUGUSTUS_PUBKEY=d36e4b8b8c8c3c6424c884110c22fcbbed6fc2d55374f4576ee51d43145c7d01

# The isolation contract aurelian exists for: he must reach a verification request with no
# knowledge of how the work under review came about. Asserted from /proc, not from the
# unit files, because a drop-in that was never loaded looks identical to one that was.
#
# BUZZ_ACP_HEARTBEAT_INTERVAL is here for a different reason than the other three. The
# others are set in his drop-in; this one cannot be enforced there, because systemd lets
# EnvironmentFile= override Environment= and buzz-agent@.service loads a .env this tree
# cannot read. Every existing agent runs the heartbeat at 3600 via that file, set nowhere
# a unit file would show it — and the heartbeat prompt opens with `buzz feed get`, an
# hourly self-prompt that reads back history. Copying an existing .env as a template is
# all it would take. Asserting 0 from /proc is the only place that catches it.
declare -A EXPECT_AURELIAN_ENV=(
  [BUZZ_ACP_CONTEXT_MESSAGE_LIMIT]=0
  [BUZZ_ACP_NO_MEMORY]=true
  [BUZZ_ACP_MAX_TURNS_PER_SESSION]=1
  [BUZZ_ACP_HEARTBEAT_INTERVAL]=0
)

TEAM_DIR="$HOME/.config/buzz-team"
UNIT_DIR="$HOME/.config/systemd/user"
TEAM_FILE="$TEAM_DIR/TEAM.md"
# The deployed route table, not ~/dev — the fleet runs this copy.
ROUTES_FILE="$HOME/agent-workforce/bin/buzz_routes.env"

: "${XDG_RUNTIME_DIR:=/run/user/$(id -u)}"
export XDG_RUNTIME_DIR

failures=0

ok() { printf 'OK   %s\n' "$1"; }
fail() { printf 'FAIL %s\n' "$1"; failures=$((failures + 1)); }
check() { if [ "$1" = "$2" ]; then ok "$3"; else fail "$3 (want '$1', got '$2')"; fi; }

# Gates that read a live process cannot speak about a unit that is not running: an
# empty answer means "unknown", not "wrong", and reporting it either way is a lie.
# assert_units_active already fails for the dead unit, so skipping here hides nothing.
skip() { printf 'SKIP %s\n' "$1"; }

main_pid() { systemctl --user show "buzz-agent@$1" -p MainPID --value; }
is_running() { local pid; pid=$(main_pid "$1"); [ -n "$pid" ] && [ "$pid" != 0 ]; }

# Reads one variable out of a live process. Never dumps the whole block — it
# carries the agent's Nostr private key.
proc_env() {
  awk -v key="$2=" 'BEGIN{RS="\0"} index($0, key) == 1 { print substr($0, length(key) + 1) }' \
    "/proc/$1/environ" 2>/dev/null
}

# One argv value out of a live process, by the flag before it (LAST occurrence, which is
# the one a single-value option honours). /proc/<pid>/cmdline is never printed whole:
# buzz-acp's carries the agent's private key, and claude's carries it again inside
# --mcp-config.
proc_arg_after() {
  awk -v flag="$2" 'BEGIN{RS="\0"} prev == flag { val = $0 } { prev = $0 } END { print val }' \
    "/proc/$1/cmdline" 2>/dev/null
}
proc_has_arg() {
  awk -v want="$2" 'BEGIN{RS="\0"; found=1} $0 == want { found=0 } END { exit found }' \
    "/proc/$1/cmdline" 2>/dev/null
}
# The last --setting-sources argument in either spelling the CLI accepts, normalised to the
# `=` form. The adapter passes --setting-sources=user,project,local; the wrapper's
# --setting-sources= comes after it and must be what survives.
proc_last_setting_sources() {
  awk 'BEGIN{RS="\0"} $0 ~ /^--setting-sources=/ { last = $0 }
       prev == "--setting-sources" { last = "--setting-sources=" $0 } { prev = $0 }
       END { print last }' "/proc/$1/cmdline" 2>/dev/null
}
# The claude session processes of a unit: only the SDK's own child carries
# --permission-prompt-tool. There is none between turns, so a caller must treat an empty
# result as "nothing to read", never as proof.
session_pids() {
  local cg pid
  cg=$(systemctl --user show "buzz-agent@$1" -p ControlGroup --value)
  [ -n "$cg" ] || return 0
  while read -r pid; do
    proc_has_arg "$pid" --permission-prompt-tool && printf '%s\n' "$pid"
  done <"/sys/fs/cgroup$cg/cgroup.procs"
}

unit_start_epoch() {
  local stamp
  stamp=$(systemctl --user show "buzz-agent@$1" -p ExecMainStartTimestamp --value)
  [ -n "$stamp" ] && date -d "$stamp" +%s
}

assert_units_active() {
  local agent state
  for agent in "${AGENTS[@]}"; do
    state=$(systemctl --user is-active "buzz-agent@$agent")
    check active "$state" "1/active buzz-agent@$agent"
  done
}

assert_harness() {
  local agent pid resolved
  for agent in "${AGENTS[@]}"; do
    pid=$(main_pid "$agent")
    resolved=$(basename "$(proc_env "$pid" BUZZ_ACP_AGENT_COMMAND)")
    check "${EXPECT_HARNESS[$agent]}" "$resolved" "2/harness $agent"
  done
}

assert_team_instructions() {
  local expected agent pid actual
  expected=$(( $(wc -c <"$TEAM_FILE") - 1 ))
  for agent in "${AGENTS[@]}"; do
    pid=$(main_pid "$agent")
    actual=$(proc_env "$pid" BUZZ_ACP_TEAM_INSTRUCTIONS | wc -c)
    check "$expected" "$((actual - 1))" "3/team-instructions $agent"
  done
}

assert_rules() {
  local agent expected
  for agent in "${AGENTS[@]}"; do
    expected="$DAVE_PUBKEY $PRAETORIUM_PUBKEY"
    [ "$agent" = marcus ] || expected="$expected $MARCUS_PUBKEY"
    # The fleet's only worker-to-worker edge, and it is one-way: no other agent's rules
    # admit aurelian, so his verdict cannot re-enter the agent that submitted the work.
    # Asserting the exact set here is what keeps that asymmetry from being mirrored back
    # into a cycle by a later edit — the reverse edge would have to be added to the three
    # workers' files, where this loop demands they admit nobody but Dave, Marcus and
    # praetorium.
    [ "$agent" != aurelian ] ||
      expected="$expected $CLAUDIUS_PUBKEY $TRAJAN_PUBKEY $AUGUSTUS_PUBKEY"
    # Marcus's return edge, added 2026-09-07. The three workers may now wake him, which
    # closes the cycle this assertion was written to keep open — so the SET is no longer
    # the whole property. `@hop` demands every rule admitting that author carry a hop
    # token inside check-rules.py's budget. An edit that admitted the same three
    # unconditionally would pass a set check while deleting the only bound on the chain;
    # it fails here instead. Workers stay unsuffixed on purpose: their edges must remain
    # ungated, and the checker rejects a hop token there too.
    [ "$agent" != marcus ] ||
      expected="$expected ${CLAUDIUS_PUBKEY}@hop ${TRAJAN_PUBKEY}@hop ${AUGUSTUS_PUBKEY}@hop"
    if python3 "$TEAM_DIR/check-rules.py" "$TEAM_DIR/$agent.toml" $expected; then
      ok "4/rules $agent"
    else
      fail "4/rules $agent"
    fi
  done
}

# The contained process is codex-acp inside bwrap, not the unit's MainPID —
# buzz-acp stays on the host namespace and never acts on the agent's behalf.
# Identify it by the only property that matters: a mount namespace of its own.
sandbox_pid() {
  local cg pid own
  cg=$(systemctl --user show "buzz-agent@$1" -p ControlGroup --value)
  [ -n "$cg" ] || return 1
  own=$(readlink /proc/self/ns/mnt)
  while read -r pid; do
    [ "$(readlink "/proc/$pid/ns/mnt" 2>/dev/null)" != "$own" ] || continue
    printf '%s\n' "$pid"
    return 0
  done <"/sys/fs/cgroup$cg/cgroup.procs"
  return 1
}

# Reads a path from inside that namespace. `codex sandbox` would measure an
# offline code path the agent never takes — codex-acp overrides the sandbox
# policy per turn — and `codex exec` measures whether the model chose to decline,
# not whether anything stopped it. nsenter removes both from the loop.
# nsenter needs root to enter the namespace, so it must drop straight back to the
# agent's own identity: root's DAC_OVERRIDE reads a mode-000 file regardless of
# permissions, which would score the file-level denies as readable.
ns_reads() {
  sudo -n nsenter -t "$1" -m -- \
    setpriv --reuid "$(id -u)" --regid "$(id -g)" --init-groups \
    /bin/sh -c "head -c1 '$2'" >/dev/null 2>&1
}

DENIED_PATHS=(
  "$HOME/.ssh/config"
  "$HOME/.config/buzz-agents/marcus.env"
  "$HOME/.config/agent-workforce/secrets.env"
  "$HOME/.codex/config.toml"
  "$HOME/ENCRYPTION_RECOVERY.md"
  "$HOME/.confidential.img"
)

READABLE_PATHS=(
  "$HOME/dev/WORKSPACE.md"
  "$HOME/CLAUDE.md"
  "$HOME/vault/00_system/CLAUDE.md"
  "$HOME/.local/bin/buzz"
)

assert_containment() {
  local agent pid path
  for agent in "${AGENTS[@]}"; do
    [ "${EXPECT_HARNESS[$agent]}" = codex-acp ] || continue
    if ! pid=$(sandbox_pid "$agent"); then
      fail "5/sandbox $agent (no contained process in the unit cgroup)"
      continue
    fi
    ok "5/sandbox $agent (pid $pid)"
    # A missing path is unreadable too, so ns_reads alone scores a DELETED file as
    # contained. Without this guard the gate would have started certifying nothing the
    # moment check-loaded.sh left this tree on 2026-09-06 — the same fail-open the file
    # itself was rewritten for, one layer up.
    for path in "${DENIED_PATHS[@]}"; do
      if [ ! -e "$path" ]; then
        fail "5/denied $agent ${path#$HOME/} (path absent — containment unproven, not proven)"
      elif ns_reads "$pid" "$path"; then
        fail "5/denied $agent ${path#$HOME/}"
      else
        ok "5/denied $agent ${path#$HOME/}"
      fi
    done
    for path in "${READABLE_PATHS[@]}"; do
      if ns_reads "$pid" "$path"; then
        ok "5/readable $agent ${path#$HOME/}"
      else
        fail "5/readable $agent ${path#$HOME/}"
      fi
    done
  done
}

# The charter reaches the session over ACP: buzz-acp reads --system-prompt-file
# on the host side and sends it as the system prompt, so the file is deliberately
# not visible from inside the agent's own sandbox.
assert_charter() {
  local agent pid path
  for agent in "${AGENTS[@]}"; do
    pid=$(main_pid "$agent")
    path=$(tr '\0' '\n' <"/proc/$pid/cmdline" | grep -x -A1 -- --system-prompt-file | tail -1)
    if [ -s "$path" ]; then
      ok "6/charter $agent"
    else
      fail "6/charter $agent (--system-prompt-file resolved to '$path')"
    fi
  done
}

# Covers the files this gate owns. Staleness of <agent>.env / <agent>.prompt is
# check-loaded.sh's assertion — one owner per check.
assert_no_stale_config() {
  local agent started pid codex_home file stale
  for agent in "${AGENTS[@]}"; do
    if ! is_running "$agent"; then
      skip "7/fresh-config $agent (unit not running — no start time to compare against)"
      continue
    fi
    started=$(unit_start_epoch "$agent")
    pid=$(main_pid "$agent")
    codex_home=$(proc_env "$pid" CODEX_HOME)
    stale=""
    for file in "$UNIT_DIR/buzz-agent@.service" "$UNIT_DIR/buzz-agent@$agent.service.d"/*.conf \
      "$TEAM_DIR/$agent.toml" "$TEAM_FILE" "$TEAM_DIR/heartbeat.prompt" \
      "$TEAM_DIR/buzz-acp-launch.sh" \
      ${codex_home:+"$codex_home/config.toml" "$codex_home/AGENTS.md"}; do
      [ -f "$file" ] || continue
      [ "$(stat -c %Y "$file")" -gt "$started" ] && stale="$stale ${file##*/}"
    done
    if [ -z "$stale" ]; then
      ok "7/fresh-config $agent"
    else
      fail "7/fresh-config $agent (newer than unit start:$stale)"
    fi
  done
}

# The bridge is spawned by the agent, so it inherits the agent's namespace: the
# host-side and in-namespace answers can differ, and did — augustus's Notion
# access was dead for as long as the credential lived somewhere his bwrap mount
# namespace replaced with a tmpfs. Assert both ends, not just the broker.
assert_notion_broker() {
  local state agent pid
  state=$(systemctl --user is-active buzz-notion-broker)
  check active "$state" "9/notion-broker"

  if python3 "$TEAM_DIR/notion-probe.py" >/dev/null 2>&1; then
    ok "9/notion-reachable host"
  else
    fail "9/notion-reachable host"
  fi

  for agent in "${AGENTS[@]}"; do
    [ "${EXPECT_HARNESS[$agent]}" = codex-acp ] || continue
    if ! pid=$(sandbox_pid "$agent"); then
      fail "9/notion-reachable $agent (no contained process in the unit cgroup)"
      continue
    fi
    if sudo -n nsenter -t "$pid" -m -- \
      setpriv --reuid "$(id -u)" --regid "$(id -g)" --init-groups \
      /usr/bin/python3 "$TEAM_DIR/notion-probe.py" >/dev/null 2>&1; then
      ok "9/notion-reachable $agent"
    else
      fail "9/notion-reachable $agent"
    fi
  done
}

# Fleet-wide, not per-agent: the event kind belongs to the destination channel, so
# there is one answer per channel and every agent must be reading the same one.
assert_team_kinds() {
  if python3 "$TEAM_DIR/check-team-kinds.py" "$ROUTES_FILE" "$TEAM_FILE"; then
    ok "8/team-kinds"
  else
    fail "8/team-kinds"
  fi
}

# Aurelian's whole value is that he reaches a review with no history of the work, and
# every one of these is a channel through which history would otherwise arrive. They are
# read from the live process because that is the only thing that can distinguish a drop-in
# that loaded from one that was written and never read — the failure this box has hit
# often enough to have a rule about it.
#
# The 50 asserted for the other four is a regression guard, not a preference: the value
# moved off ExecStart into Environment= in buzz-agent@.service so that aurelian could
# override it, and a mistake there would silently change how often every other agent's
# session rotates.
assert_review_isolation() {
  local agent pid var want got cwd
  for agent in "${AGENTS[@]}"; do
    if ! is_running "$agent"; then
      skip "10/isolation $agent (unit not running — /proc says nothing about intent)"
      continue
    fi
    pid=$(main_pid "$agent")
    if [ "$agent" != aurelian ]; then
      got=$(proc_env "$pid" BUZZ_ACP_MAX_TURNS_PER_SESSION)
      check 50 "$got" "10/session-rotation $agent"
      continue
    fi
    for var in $(printf '%s\n' "${!EXPECT_AURELIAN_ENV[@]}" | sort); do
      want="${EXPECT_AURELIAN_ENV[$var]}"
      got=$(proc_env "$pid" "$var")
      # Unset is only acceptable for the heartbeat, whose buzz-acp default is 0 —
      # i.e. absent from aurelian.env is the outcome we want. Every other variable
      # here falls back to a default that defeats the isolation (context 12, memory
      # injected, 50 turns per session), so unset must fail rather than pass quietly.
      [ "$var" = BUZZ_ACP_HEARTBEAT_INTERVAL ] && [ -z "$got" ] && got=0
      check "$want" "$got" "10/isolation aurelian $var"
    done
    # A shared cwd is a shared Claude Code memory pool: `~/.claude/projects/<slug>/` is
    # derived from it, and the fleet default of $HOME is the pool every other agent and
    # every interactive session on this box writes to.
    cwd=$(readlink "/proc/$pid/cwd" 2>/dev/null)
    check "$HOME/services/aurelian" "$cwd" "10/isolation aurelian cwd"
  done
}

# The roster in TEAM.md is used verbatim by every agent: a mention of an unresolved
# placeholder binds no `p` tag and reaches nobody, which is indistinguishable from a dead
# unit. This fails until aurelian's minted pubkey replaces the placeholder.
assert_roster_complete() {
  if grep -q '<PENDING-MINT>' "$TEAM_FILE"; then
    fail "11/roster (TEAM.md still carries a <PENDING-MINT> placeholder)"
  else
    ok "11/roster"
  fi
}

# Aurelian has no memory, so the calibration pack is the only layer that carries a standard
# between reviews and the only one that can correct him without a charter reinstall. He is
# instructed to return ERROR if it is unreadable, so a missing file degrades every review
# rather than silently loosening one. It must live under buzz-team/ and not buzz-agents/ —
# the latter is deny-listed to agent sessions, so a calibration pack placed beside the
# charter would be unreadable by the one agent that needs it.
CALIBRATION_FILE="$HOME/.config/buzz-team/aurelian-calibration.md"
assert_calibration_pack() {
  if [ ! -r "$CALIBRATION_FILE" ]; then
    fail "12/calibration (unreadable: $CALIBRATION_FILE)"
  elif ! grep -qE '^\*\*version: [0-9]+\*\*' "$CALIBRATION_FILE"; then
    fail "12/calibration (no '**version: N**' line — verdicts cite a version that must exist)"
  else
    ok "12/calibration ($(grep -oE '^\*\*version: [0-9]+' "$CALIBRATION_FILE" | head -1 | tr -d '*'))"
  fi
}

# Same split, second service: the four brave_* tools the bridge forwards reach
# brave-mcp.service over loopback HTTP, and loopback inside a bwrap namespace is
# only known to work because it is measured. initialize + tools/list, no query,
# so the gate spends no search quota and nothing leaves the box.
assert_brave_mcp() {
  local state agent pid
  state=$(systemctl is-active brave-mcp)
  check active "$state" "13/brave-mcp"

  if python3 "$TEAM_DIR/brave-probe.py" >/dev/null 2>&1; then
    ok "13/brave-reachable host"
  else
    fail "13/brave-reachable host"
  fi

  for agent in "${AGENTS[@]}"; do
    [ "${EXPECT_HARNESS[$agent]}" = codex-acp ] || continue
    if ! pid=$(sandbox_pid "$agent"); then
      fail "13/brave-reachable $agent (no contained process in the unit cgroup)"
      continue
    fi
    if sudo -n nsenter -t "$pid" -m -- \
      setpriv --reuid "$(id -u)" --regid "$(id -g)" --init-groups \
      /usr/bin/python3 "$TEAM_DIR/brave-probe.py" >/dev/null 2>&1; then
      ok "13/brave-reachable $agent"
    else
      fail "13/brave-reachable $agent"
    fi
  done
}

# S1 capability isolation (2026-09-18). The Claude agents' sessions are isolated by the
# deployed wrapper — --strict-mcp-config --setting-sources= --settings <per-agent file>
# --plugin-dir <owner tree>, all after "$@" — and the adapter reaches it through
# CLAUDE_CODE_EXECUTABLE and BUZZ_AGENT_NAME in the unit's environment. Both halves are
# read from /proc; the flags on a live claude child are read when there is one, and a
# turn is the only time there is one, so that part skips out loud between turns.
WRAPPER="$TEAM_DIR/claude-agent-wrapper.sh"
SKILLS_ROOT="$HOME/agent-workforce/skills"

wrapper_exec_after_args() {
  sed -n '/^exec /,/[^\\]$/p' "$WRAPPER" | tr -d '\\\n' | sed 's/.*"\$@"//'
}

assert_capability_isolation() {
  local agent pid tail settings tree got spid child bad
  tail=$(wrapper_exec_after_args)
  for got in '--strict-mcp-config' '--setting-sources= ' '--settings "$SETTINGS"' '--plugin-dir "$SKILLS_DIR"'; do
    case "$tail" in
      *"$got"*) ok "14/wrapper carries $got after \"\$@\"" ;;
      *) fail "14/wrapper carries $got after \"\$@\"" ;;
    esac
  done
  for agent in "${AGENTS[@]}"; do
    [ "${EXPECT_HARNESS[$agent]}" = claude-agent-acp ] || continue
    if ! is_running "$agent"; then
      skip "14/isolation $agent (unit not running)"
      continue
    fi
    pid=$(main_pid "$agent")
    check "$WRAPPER" "$(proc_env "$pid" CLAUDE_CODE_EXECUTABLE)" "14/executable $agent"
    check "$agent" "$(proc_env "$pid" BUZZ_AGENT_NAME)" "14/agent-name $agent"
    settings="$TEAM_DIR/agent-settings-$agent.json"
    tree="$SKILLS_ROOT/$agent"
    if jq -e '.permissions.deny | length > 0' "$settings" >/dev/null 2>&1; then
      ok "14/settings $agent ${settings#$HOME/}"
    else
      fail "14/settings $agent ${settings#$HOME/} (missing, unreadable or no deny list)"
    fi
    got=$(jq -r .name "$tree/.claude-plugin/plugin.json" 2>/dev/null)
    check "praetorium-$agent" "$got" "14/skills $agent ${tree#$HOME/}"
    spid=$(session_pids "$agent" | head -1)
    if [ -z "$spid" ]; then
      skip "14/session $agent (no claude child between turns — flags proven from the wrapper)"
      continue
    fi
    proc_has_arg "$spid" --strict-mcp-config && ok "14/session $agent --strict-mcp-config" \
      || fail "14/session $agent --strict-mcp-config"
    check "--setting-sources=" "$(proc_last_setting_sources "$spid")" "14/session $agent --setting-sources"
    check "$settings" "$(proc_arg_after "$spid" --settings)" "14/session $agent --settings"
    check "$tree" "$(proc_arg_after "$spid" --plugin-dir)" "14/session $agent --plugin-dir"
    # Every MCP-shaped child of the session is the bridge. Dave's user servers
    # (brave-search, graft, google-docs, qmd) all carry "mcp" in their argv.
    bad=""
    for child in $(pgrep -P "$spid"); do
      if tr '\0' '\n' <"/proc/$child/cmdline" 2>/dev/null | grep -qi mcp \
         && ! proc_has_arg "$child" "$TEAM_DIR/buzz-team-mcp.py"; then
        bad="$bad $child:$(cat "/proc/$child/comm" 2>/dev/null)"
      fi
    done
    check "" "$bad" "14/session $agent no MCP child but the bridge"
  done
}

# Every unit names its own bridge shim with --mcp-command; the shim declares the families it
# advertises, and the deployed bridge must honour that where the harness spawns it: on the
# host for the Claude agents, inside the bwrap namespace for augustus (gate 9/13 pattern —
# the two ends can disagree). initialize + tools/list only; nothing is spent.
assert_bridge_offer() {
  local agent pid shim families codex_home link target first
  for agent in "${AGENTS[@]}"; do
    if ! is_running "$agent"; then
      skip "15/bridge $agent (unit not running)"
      continue
    fi
    pid=$(main_pid "$agent")
    shim="$TEAM_DIR/buzz-team-mcp-$agent"
    check "$shim" "$(proc_arg_after "$pid" --mcp-command)" "15/mcp-command $agent"
    families=$(sed -n 's/.*--tools \([a-z,]*\).*/\1/p' "$shim" 2>/dev/null)
    if [ -x "$shim" ] && [ -n "$families" ]; then
      ok "15/shim $agent declares $families"
    else
      fail "15/shim $agent (${shim#$HOME/} missing, not executable, or declares no --tools)"
      continue
    fi
    if python3 "$TEAM_DIR/bridge-probe.py" "$shim" --expect "$families" >/dev/null 2>&1; then
      ok "15/offer $agent host advertises $families"
    else
      fail "15/offer $agent host advertises $families"
    fi
    [ "${EXPECT_HARNESS[$agent]}" = codex-acp ] || continue
    if ! pid=$(sandbox_pid "$agent"); then
      fail "15/offer $agent namespace (no contained process in the unit cgroup)"
      continue
    fi
    # HOME=: sudo leaves root's, and the bridge finds qmd-mcp under ~ — the agent's own
    # bridge inherits dave's HOME from codex's sanitised env, so the probe must too.
    if sudo -n nsenter -t "$pid" -m -- \
      setpriv --reuid "$(id -u)" --regid "$(id -g)" --init-groups \
      /usr/bin/env HOME="$HOME" /usr/bin/python3 "$TEAM_DIR/bridge-probe.py" "$shim" --expect "$families" >/dev/null 2>&1; then
      ok "15/offer $agent namespace advertises $families"
    else
      fail "15/offer $agent namespace advertises $families"
    fi
    # His skills: codex scans $CODEX_HOME/skills/, and the owner tree reaches it through a
    # hand-installed symlink. Resolved on the host, then read through the link inside the
    # namespace — the path the harness actually walks.
    codex_home=$(proc_env "$(main_pid "$agent")" CODEX_HOME)
    link="$codex_home/skills/praetorium"
    target=$(readlink -f "$link" 2>/dev/null)
    check "$SKILLS_ROOT/$agent/skills" "$target" "15/skills $agent ${link#$HOME/} resolves"
    first=$(find "$link/" -mindepth 2 -maxdepth 2 -name SKILL.md 2>/dev/null | sort | head -1)
    if [ -n "$first" ] && ns_reads "$pid" "$first"; then
      ok "15/skills $agent namespace reads ${first#$HOME/}"
    else
      fail "15/skills $agent namespace reads a pointer through the link (${first:-none found})"
    fi
  done
}

assert_units_active
assert_harness
assert_team_instructions
assert_rules
assert_containment
assert_charter
assert_no_stale_config
assert_team_kinds
assert_notion_broker
assert_review_isolation
assert_roster_complete
assert_calibration_pack
assert_brave_mcp
assert_capability_isolation
assert_bridge_offer

printf '\n%s\n' "----------------------------------------"
if [ "$failures" -eq 0 ]; then
  printf 'verify-fleet: PASS\n'
  exit 0
fi
printf 'verify-fleet: FAIL (%d assertion(s))\n' "$failures"
exit 1
