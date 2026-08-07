#!/usr/bin/env bash
# Shared seam for the input adapters. An adapter owns exactly two decisions —
# "should this send at all?" and "what does it say" — and nothing else. Resolving
# deliver.sh, naming the route, and the fail-soft handoff are identical in every
# one of them, so they live here: N private copies of a transport handoff is N
# places for a delivery to drift out of the receipt trail.
#
# Source it, then compose the payload arguments and call delivery_handoff once.
# Not executable on its own.

DELIVERY_ADAPTER="${DELIVERY_ADAPTER:-$(basename "${BASH_SOURCE[1]:-adapter.sh}")}"
DELIVERY_NAME="${DELIVERY_ADAPTER%.sh}"
DELIVER_BIN="${DELIVER_BIN:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deliver.sh}"

# There is deliberately no default route. A caller that has not been given one keeps
# exactly its pre-migration behaviour — Discord only — and deliver.sh files a
# config_error receipt, so an unported producer surfaces in the dual-run audit
# instead of defaulting into someone else's channel.
DELIVERY_ROUTE="${DELIVERY_ROUTE:-unrouted}"
DELIVERY_JOB="${DELIVERY_JOB:-$DELIVERY_ADAPTER}"
DELIVERY_RUNTIME="${DELIVERY_RUNTIME:-${AGENT_PROFILE:-unknown}}"

mkdir -p "$HOME/logs" 2>/dev/null || true

note() {
  printf '%s %s: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$DELIVERY_NAME" "$*" \
    >> "$HOME/logs/${DELIVERY_NAME}.log" 2>/dev/null || true
}

delivery_handoff() {  # delivery_handoff <payload args...> — at most one per invocation
  if "$DELIVER_BIN" --job "$DELIVERY_JOB" --route "$DELIVERY_ROUTE" \
       --runtime "$DELIVERY_RUNTIME" "$@"; then
    note "handed to deliver.sh (route=$DELIVERY_ROUTE)"
  else
    note "deliver.sh returned non-zero (non-fatal)"
  fi
}
