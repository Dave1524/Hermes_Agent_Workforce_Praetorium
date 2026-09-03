#!/bin/sh
# Merged, agent-labelled view of the four buzz-agent units for guardrail testing.
#   watch-test.sh            follow live
#   watch-test.sh -5min      replay since a journalctl time expression
set -eu
export XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"

UNITS="-u buzz-agent@marcus -u buzz-agent@claudius -u buzz-agent@trajan -u buzz-agent@augustus"

# Strip ANSI, shorten the unit name to just the agent, drop the reconnect/ping chatter.
clean() {
  sed 's/\x1b\[[0-9;]*m//g' \
    | sed 's/buzz-agent@\([a-z]*\)\.service/\1/' \
    | grep -vE 'sent ping to relay|received pong|EOSE for subscription'
}

if [ $# -eq 0 ]; then
  journalctl --user $UNITS -f -o with-unit | clean
else
  journalctl --user $UNITS --since "$1" --no-pager -o with-unit | clean
fi
