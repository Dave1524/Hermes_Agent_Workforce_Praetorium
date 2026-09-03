#!/usr/bin/env bash
# Proves the fleet can actually ANSWER, not merely that its supervisors are alive.
#
# Written 2026-08-31 after a four-day total outage in which every conventional
# signal on this box stayed green: units active, timers scheduled, presence
# online. The single failure -- an OAuth refresh token that could no longer be
# refreshed -- was visible only to something that attempted a real turn.
#
# Design rules this file is required to keep:
#   * Ask the system what exists; never assert against a hardcoded roster.
#   * Bound each per-unit window at BOTH ends: never earlier than that unit's own
#     ActiveEnterTimestamp (so a restart cannot charge a healthy unit for its
#     predecessor's errors) and never earlier than now-LOOKBACK_MIN (so a
#     long-lived unit is judged on current state, not on its whole history).
#     Anchoring alone reported augustus's 19-20 Aug errors as live on 31 Aug.
#   * Print the boundary of every window examined, and which bound produced it.
#   * Name a quiet unit out loud; absence of attempts is not evidence of health.
#   * Exit non-zero on failure so OnFailure=agent-alert@%n.service fires.

set -uo pipefail
export HOME=/home/dave
export XDG_RUNTIME_DIR=${XDG_RUNTIME_DIR:-/run/user/1000}
export PATH="/home/dave/.local/bin:/usr/local/bin:/usr/bin:/bin"

CLAUDE_BIN=/usr/local/bin/claude
ACP_BIN=/usr/local/bin/claude-agent-acp
PROBE_MODEL=${FLEET_PROBE_MODEL:-claude-haiku-4-5-20251001}
SENTINEL=FLEET_TURN_OK
LOOKBACK_MIN=${FLEET_LOOKBACK_MIN:-90}
STATE=${FLEET_STATE_FILE:-/home/dave/logs/fleet-turn-check.state}
# CPU burned between two runs that counts as "this agent did real work". One real
# marcus turn measured ~40s; an idle unit ticks a heartbeat and costs milliseconds.
CPU_WORK_NS=${FLEET_CPU_WORK_NS:-5000000000}

fail=0
note() { printf '%s\n' "$*"; }
gate() { printf '\n[gate %s] %s\n' "$1" "$2"; }
pass_() { printf '  PASS  %s\n' "$*"; }
fail_() { printf '  FAIL  %s\n' "$*"; fail=1; }
info_() { printf '        %s\n' "$*"; }

note "fleet-turn-check  $(date -Is)  host=$(hostname)"

# ---------------------------------------------------------------- gate 1
# The credential, read through the exact binary the Claude-backed agents spawn.
# Scope: covers marcus/claudius/trajan/aurelian. augustus runs codex-acp and is
# NOT covered by this gate -- gate 3 is what watches him.
gate 1 "auth-live (claude-agent-acp --cli auth status)"
auth_out=$("$ACP_BIN" --cli auth status 2>&1)
auth_rc=$?
if [ $auth_rc -ne 0 ]; then
  fail_ "auth status exited $auth_rc"
  info_ "$(printf '%s' "$auth_out" | head -5)"
elif printf '%s' "$auth_out" | grep -qi '"\?loggedIn"\?[: ]\+true'; then
  pass_ "loggedIn: true  ($(printf '%s' "$auth_out" | grep -oi 'subscriptionType[": ]*[a-z]*' | head -1))"
else
  fail_ "claude-agent-acp does not report loggedIn: true"
  info_ "$(printf '%s' "$auth_out" | head -5)"
fi

# ---------------------------------------------------------------- gate 2
# A real model round trip. This is the gate that would have caught 2026-08-27:
# an expired refresh token cannot complete a turn, however healthy the units look.
gate 2 "turn-completes (synthetic turn, model=$PROBE_MODEL)"
t0=$(date +%s)
turn_out=$(timeout 120 "$CLAUDE_BIN" -p --model "$PROBE_MODEL" \
  "Reply with exactly this token and nothing else: $SENTINEL" 2>&1)
turn_rc=$?
t1=$(date +%s)
if [ $turn_rc -ne 0 ]; then
  fail_ "probe turn exited $turn_rc after $((t1-t0))s"
  info_ "$(printf '%s' "$turn_out" | head -5)"
elif [ "$(printf '%s' "$turn_out" | tr -d '[:space:]')" = "$SENTINEL" ]; then
  pass_ "model returned the sentinel in $((t1-t0))s"
else
  fail_ "probe turn completed but did not return the sentinel"
  info_ "got: $(printf '%s' "$turn_out" | head -3)"
fi

# ---------------------------------------------------------------- gate 3
# Per-agent state, enumerated FROM SYSTEMD. A hardcoded roster cannot report an
# agent it does not know about; verify-fleet.sh's AGENTS=() array is the pattern
# this deliberately does not copy.
gate 3 "agents-answering (units enumerated from systemd, window anchored per unit)"
:>"$STATE.new" 2>/dev/null || { info_ "cannot write $STATE.new -- CPU deltas unavailable this run"; STATE=/dev/null; :>"$STATE.new" 2>/dev/null || true; }
units=$(systemctl --user list-units --all --no-legend --plain 'buzz-agent@*.service' 2>/dev/null | awk '{print $1}' | sort)
if [ -z "$units" ]; then
  fail_ "systemd lists no buzz-agent@*.service units at all"
else
  info_ "$(printf '%s\n' "$units" | wc -l) unit(s) known to systemd; window = max(unit restart, now-${LOOKBACK_MIN}m)"
  quiet_list=""
  for u in $units; do
    name=${u#buzz-agent@}; name=${name%.service}
    active=$(systemctl --user show "$u" -p ActiveState --value 2>/dev/null)
    anchor=$(systemctl --user show "$u" -p ActiveEnterTimestamp --value 2>/dev/null)
    if [ "$active" != "active" ]; then
      fail_ "$name: ActiveState=$active"
      continue
    fi
    if [ -z "$anchor" ]; then
      fail_ "$name: active but has no ActiveEnterTimestamp -- cannot bound a window"
      continue
    fi
    anchor_s=$(date -d "$anchor" +%s 2>/dev/null) || anchor_s=0
    look_s=$(date -d "$LOOKBACK_MIN minutes ago" +%s)
    if [ "$anchor_s" -gt "$look_s" ]; then
      win_s=$anchor_s; bound="since restart"
    else
      win_s=$look_s;  bound="last ${LOOKBACK_MIN}m"
    fi
    win=$(date -d "@$win_s" '+%Y-%m-%d %H:%M:%S')
    errs=$(journalctl --user -u "$u" --since "$win" --no-pager 2>/dev/null \
      | grep -c 'Failed to authenticate\|OAuth session expired\|reported error')
    # A COMPLETED TURN LOGS NOTHING. Measured 2026-08-31: marcus answered a DM at
    # 11:58 and left zero journal lines, and outcome="ok" has never once been
    # emitted by any agent (444 outcome= lines in the 17-31 Aug fortnight, all
    # "error"). So the ANSWERED branch was dead code and this gate could only ever
    # report ERRORED or QUIET. CPU is the signal instead -- one real turn cost
    # marcus ~40s against a 2.4s idle sibling. Delta is measured across runs;
    # a restart resets the counter, so a lower current value means "restarted",
    # not "negative work".
    cpu_now=$(systemctl --user show "$u" -p CPUUsageNSec --value 2>/dev/null)
    case $cpu_now in ''|*[!0-9]*) cpu_now=0 ;; esac
    cpu_prev=$(awk -v u="$u" '$1==u{print $2}' "$STATE" 2>/dev/null | tail -1)
    seeded=0
    case $cpu_prev in ''|*[!0-9]*) cpu_prev=0; seeded=1 ;; esac
    if [ "$cpu_now" -lt "$cpu_prev" ]; then cpu_prev=0; fi
    cpu_delta=$(( cpu_now - cpu_prev ))
    printf '%s\t%s\t%s\n' "$u" "$cpu_now" "$win_s" >>"$STATE.new"
    # With no prior reading the "delta" is the unit's whole lifetime, which would
    # report a 14-day-old unit as busy on the strength of history. Seed, don't judge.
    if [ "$seeded" -eq 1 ]; then
      turns=0
    else
      turns=$(( cpu_delta >= CPU_WORK_NS ? 1 : 0 ))
    fi
    if [ "$errs" -gt 0 ]; then
      fail_ "$name: ERRORED -- $errs error line(s) in window [$win, now] ($bound)"
      journalctl --user -u "$u" --since "$win" --no-pager 2>/dev/null \
        | grep 'Failed to authenticate\|OAuth session expired\|reported error' | tail -2 \
        | while IFS= read -r l; do info_ "  ${l:0:150}"; done
    elif [ "$turns" -gt 0 ]; then
      pass_ "$name: ANSWERED -- $(( cpu_delta / 1000000000 )).$(( (cpu_delta / 100000000) % 10 ))s CPU burned since the last check ($bound)"
    else
      quiet_list="$quiet_list $name"
      if [ "$seeded" -eq 1 ]; then
        info_ "SEED  $name: 0 errors; no prior CPU reading, baseline recorded ($bound) -- judged from the next run on"
      else
        info_ "QUIET $name: 0 errors, $(( cpu_delta / 1000000 ))ms CPU since last check ($bound) -- nothing was asked, so nothing is proven"
      fi
    fi
  done
  [ -n "$quiet_list" ] && info_ "quiet (unproven, not failed):$quiet_list"
fi
# Promote regardless of gate outcome: the next run needs this run's CPU readings
# to compute a delta, whether or not anything failed here.
[ -s "$STATE.new" ] && mv -f "$STATE.new" "$STATE" 2>/dev/null || rm -f "$STATE.new" 2>/dev/null || true

# ---------------------------------------------------------------- gate 4
# Defends the 2026-08-31 OnFailure fix against the next unit somebody adds.
# Closes the class, not the three instances that happened to surface.
gate 4 "no-silent-units (every agent_propose.sh unit must alert on failure)"
silent=""; checked=0
for f in /etc/systemd/system/*.service; do
  grep -q 'agent_propose\.sh' "$f" 2>/dev/null || continue
  u=$(basename "$f")
  checked=$((checked+1))
  if ! grep -q '^OnFailure=' "$f"; then silent="$silent $u"; fi
done
if [ "$checked" -eq 0 ]; then
  fail_ "found no agent_propose.sh units -- the discovery pattern itself is broken"
elif [ -n "$silent" ]; then
  fail_ "unwired:$silent"
else
  pass_ "all $checked agent_propose.sh unit(s) carry OnFailure="
fi

printf '\n== fleet-turn-check %s ==\n' "$([ $fail -eq 0 ] && echo PASS || echo FAIL)"
exit $fail
