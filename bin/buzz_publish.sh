#!/usr/bin/env bash
# Credential helper for bin/deliver.sh. argv is `<identity> <buzz-subcommand...>`.
#
# This file holds no secret — it loads one. deliver.sh scrubs BUZZ_PRIVATE_KEY and
# BUZZ_AUTH_TAG from its own environment before calling it, so the signing credential
# exists only inside this process and the `buzz` child it execs, and never reaches
# deliver.sh's argv, environment, receipts or logs.
#
# `exec` is load-bearing: deliver.sh categorizes the Buzz CLI's own exit codes
# (2 network, 3 auth), so nothing may sit between them and rewrite the status.
set -uo pipefail

CRED_DIR="${BUZZ_CRED_DIR:-$HOME/.config/buzz-agents}"
BUZZ_BIN="${BUZZ_BIN:-$HOME/.local/bin/buzz}"

die() { printf '{"error":"auth_error","message":"%s"}\n' "$1" >&2; exit 3; }

identity=${1:-}
[ -n "$identity" ] || die "no identity argument"
shift
case "$identity" in
  */*|*.*|"") die "identity must be a bare name" ;;
esac

envf="$CRED_DIR/${identity}.env"
[ -r "$envf" ] || die "no credential file for identity ${identity}"
[ -x "$BUZZ_BIN" ] || die "buzz binary not executable: ${BUZZ_BIN}"

# Deliberately NOT `. "$envf"`. These files are systemd EnvironmentFile format, where an
# unquoted value keeps its inner double quotes; shell sourcing strips them, which turns
# the JSON auth tag ["auth",...] into [auth,...] and the relay rejects it at column 2.
# Assigning through `export "$k=$v"` never re-parses quotes inside the value.
while IFS= read -r line || [ -n "$line" ]; do
  case "$line" in ''|'#'*) continue ;; esac
  key=${line%%=*}
  val=${line#*=}
  case "$key" in ''|*[!A-Za-z0-9_]*) continue ;; esac
  case "$val" in
    \'*\') val=${val#\'}; val=${val%\'} ;;
    \"*\") val=${val#\"}; val=${val%\"} ;;
  esac
  export "$key=$val"
done < "$envf"

exec "$BUZZ_BIN" "$@"
