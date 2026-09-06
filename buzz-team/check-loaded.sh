#!/usr/bin/env bash
# Reports, per hosted Buzz agent: whether the running process predates its config (needs a
# restart), whether its credential is accepted by the relay right now, whether it is currently
# connected, and whether its prompt predates GUARDRAILS.md (needs a re-sync).
# Usage: check-loaded.sh [name ...]   (default: every hosted or provisioned identity)
#
# The credential check PROBES the relay. It used to grep the journal for 'Auth failed' and print a
# hardcoded cause, which pinned the gate red for two days over a reconnect storm that had already
# healed (2026-09-04 claudius: attempts 1-4 failed, attempt 5 succeeded 21s later). A checker that
# greps for an error string reports a past symptom, never present state.
set -uo pipefail

# Overridable so the fixture suite can point it at a temp tree; defaults to the real one.
BASE="${BUZZ_AGENTS_DIR:-$HOME/.config/buzz-agents}"
GUARDRAILS="$BASE/GUARDRAILS.md"
BUZZ="$HOME/.local/bin/buzz"
status=0

# Empty output from a failed stat is what made the old (( a > b )) report OK on a missing file:
# a malformed expression and a false comparison both return 1. Fail loudly instead.
mtime() {
  local m
  m=$(stat -c %Y "$1" 2>/dev/null) || return 1
  [[ -n $m ]] || return 1
  printf '%s' "$m"
}

hosted_agents() {
  systemctl --user list-units 'buzz-agent@*' --all --no-legend --plain 2>/dev/null \
    | sed -n 's/^buzz-agent@\([^.]*\)\.service .*/\1/p'
}

provisioned_ids() {
  local env
  for env in "$BASE"/*.env; do
    [[ -e $env ]] || continue
    basename "$env" .env
  done
}

started_at() {
  local stamp
  stamp=$(systemctl --user show "buzz-agent@$1" -p ExecMainStartTimestamp --value 2>/dev/null)
  [[ -n $stamp ]] || return 1
  date -d "$stamp" +%s 2>/dev/null
}

# The agent's own identity, from its startup line — so an identity swap cannot leave a hardcoded
# roster probing a dead pubkey. grep -o and tail both read to EOF, so pipefail sees no SIGPIPE.
agent_pubkey() {
  local pk
  pk=$(journalctl --user -u "buzz-agent@$1" -o cat 2>/dev/null \
       | grep -o 'pubkey=[0-9a-f]\{64\}' | tail -1)
  [[ -n $pk ]] || return 1
  printf '%s' "${pk#pubkey=}"
}

report() {
  local verdict=$1 name=$2 detail=$3
  printf '  %-8s %-10s %s\n' "$verdict" "$name" "$detail"
  case $verdict in
    OK|INFO) ;;
    *) status=1 ;;
  esac
}

# systemd-run loads the deny-listed .env without this script ever reading it, and propagates the
# child's exit code. Output is discarded: the exit code is the whole verdict.
probe_credential() {
  timeout 60 systemd-run --user --pipe --collect --quiet \
    -p EnvironmentFile="$BASE/$1.env" \
    "$BUZZ" users get --pubkey "$2" >/dev/null 2>&1
}

check_credential() {
  local name=$1 pk rc
  if ! pk=$(agent_pubkey "$name"); then
    report UNKNOWN "$name" "no startup pubkey in the journal — credential unprobed"
    return
  fi
  probe_credential "$name" "$pk"
  rc=$?
  case $rc in
    0)   report OK      "$name" "relay accepted a live credential probe" ;;
    124) report UNKNOWN "$name" "credential probe timed out — relay unreachable, not a verdict" ;;
    *)   report BADAUTH "$name" "relay refused a live probe under its own .env (rc=$rc)" ;;
  esac
}

# The LAST relay event since start, not any historical one, so a recovered storm reads as
# recovered. Reads stdin so the fixture suite can pin these strings against real log text:
# the first draft matched only 'connected to relay' and reported claudius disconnected while
# a live credential probe said otherwise, because a RECONNECT logs
# 'autonomous reconnect succeeded' and never re-logs the initial-connect line.
last_relay_event() {
  grep -oE 'connected to relay|autonomous reconnect succeeded|Auth failed|relay connection lost' \
    | tail -1
}

# Names the evidence rather than asserting a cause — the defect this whole file was rewritten
# for. Fails closed: mid-reconnect is a ~1s window and a rerun costs nothing.
check_connection() {
  local name=$1 started=$2 last
  last=$(journalctl --user -u "buzz-agent@$name" --since "@$started" -o cat 2>/dev/null \
         | last_relay_event)
  case $last in
    'connected to relay'|'autonomous reconnect succeeded')
      report OK    "$name" "connected to the relay (last event: $last)" ;;
    '')
      report WAIT  "$name" "no relay event logged yet on this start" ;;
    *)
      report RELAY "$name" "not connected — last relay event was: $last" ;;
  esac
}

check_loaded() {
  local name=$1 started=$2 newest p
  if ! newest=$(mtime "$BASE/$name.env"); then
    report UNKNOWN "$name" "cannot stat $name.env — load state unchecked"
    return
  fi
  if p=$(mtime "$BASE/$name.prompt") && (( p > newest )); then
    newest=$p
  fi
  if (( newest > started )); then
    report STALE "$name" "config edited $(( (newest - started) / 60 ))m after start — restart to load it"
  else
    report OK "$name" "running process is newer than its config"
  fi
}

check_sync() {
  local name=$1 g p
  if ! g=$(mtime "$GUARDRAILS"); then
    report UNKNOWN "$name" "cannot stat GUARDRAILS.md — prompt freshness unchecked"
    return
  fi
  if ! p=$(mtime "$BASE/$name.prompt"); then
    report UNKNOWN "$name" "no $name.prompt — prompt freshness unchecked"
    return
  fi
  if (( g > p )); then
    report STALE "$name" "prompt is older than GUARDRAILS.md — re-sync the guardrail tail"
  else
    report OK "$name" "prompt is current with GUARDRAILS.md"
  fi
}

main() {
  HOSTED=" $(hosted_agents | tr '\n' ' ')"
  is_hosted() { [[ $HOSTED == *" $1 "* ]]; }

  names=("$@")
  if (( ${#names[@]} == 0 )); then
    mapfile -t names < <({ hosted_agents; provisioned_ids; } | sort -u)
  fi

  for name in "${names[@]}"; do
    if [[ ! -f $BASE/$name.env ]]; then
      report SKIP "$name" "not provisioned (no $name.env)"
      continue
    fi
    if ! is_hosted "$name"; then
      if [[ -f $BASE/$name.prompt ]]; then
        report INFO "$name" "provisioned with a prompt but no buzz-agent unit — never enabled"
        check_sync "$name"
      else
        report INFO "$name" "credential identity with no buzz-agent unit — not hosted here"
      fi
      continue
    fi
    if ! started=$(started_at "$name"); then
      report DEAD "$name" "unit exists but has never started"
    elif [[ $(systemctl --user is-active "buzz-agent@$name") != active ]]; then
      report DEAD "$name" "unit is not active — relay presence is not proof of life"
    else
      check_loaded "$name" "$started"
      check_credential "$name"
      check_connection "$name" "$started"
    fi
    check_sync "$name"
  done

  exit "$status"
}

# Sourcing exposes the checks to the fixture suite without running them.
if [[ ${BASH_SOURCE[0]} == "$0" ]]; then
  main "$@"
fi
