#!/usr/bin/env bash
# Shell adapter for workflow-incidents.service: the unit execs this, this execs the sweep.
# Transport is bin/deliver.sh, called from incident_notify.py — nothing here talks to Buzz.
set -u
BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 "$BIN_DIR/incident_notify.py" "$@"
