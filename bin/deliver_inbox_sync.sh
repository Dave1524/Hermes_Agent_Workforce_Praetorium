#!/usr/bin/env bash
# Reconcile receipt for agent-inbox-sync — the `summary` payload.
#
# The unit ticks every 30 minutes and reconciles two systems that usually already
# agree, so an unchanged poll says nothing. What it must never do is stay quiet about
# a tick that DID move something, or about one that failed: a reconciler whose
# failures are invisible converges on a lie, and the box half of that pair is the
# vault inbox worktree.
#
# This hangs off ExecStopPost, not ExecStartPost. systemd skips ExecStartPost entirely
# when ExecStart fails, which would make the one outcome most worth reporting the one
# outcome that cannot be reported. ExecStopPost runs either way and is handed
# SERVICE_RESULT and EXIT_STATUS.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=bin/delivery_common.sh
. "$BIN_DIR/delivery_common.sh"

OUTPUT="${AGENT_INBOX_OUTPUT:-$HOME/agent-workforce/logs/agent_inbox_pipeline.last}"
MARKER="${DELIVERY_RUN_MARKER:-}"
SUBJECT="${REPORT_SUBJECT:-[Praetorium] Agent inbox reconcile}"
RESULT="${SERVICE_RESULT:-success}"

is_this_run() {
  [ -s "$OUTPUT" ] || return 1
  [ -n "$MARKER" ] || return 0
  [ "$OUTPUT" -nt "$MARKER" ]
}

changes() {  # the lines that mean state moved, or that something went wrong
  grep -E '^  (created|reflected) this run:|^  REJECT |^ *! ' "$OUTPUT"
  grep -E '^Rejected to action: [1-9]' "$OUTPUT"
}

standing() {  # context worth carrying once we are speaking anyway
  grep -E '^agent-inbox-sync: |^Rejected to action: ' "$OUTPUT" | head -2
}

if [ "$RESULT" != success ]; then
  detail=$(is_this_run && tail -5 "$OUTPUT" | tr '\n' ' ')
  note "reconcile failed ($RESULT)"
  delivery_handoff --subject "$SUBJECT" \
    --message "$(printf 'RECONCILE FAILED — %s (exit %s)\n%s' \
                 "$RESULT" "${EXIT_STATUS:-?}" "${detail:-no output captured}")"
  exit 0
fi

if ! is_this_run; then
  note "no output from this run"
  delivery_handoff --subject "$SUBJECT" \
    --message "the reconcile reported success but wrote no output — nothing certifies it ran"
  exit 0
fi

moved=$(changes)
if [ -z "$moved" ]; then
  note "nothing moved — staying silent"
  exit 0
fi

summary=$(printf '%s\n%s' "$moved" "$(standing)")
note "${summary//$'\n'/ | }"
delivery_handoff --subject "$SUBJECT" --message "$summary"

exit 0
