#!/usr/bin/env bash
# Fake bin/deliver.sh for tests/test_incident_notify.py. Records argv and the environment
# it was called with, then behaves per FAKE_DELIVER_MODE the way the real transport does:
#   ok      appends a `delivered` receipt line (buzz_result=ok, buzz_event_id, channel), exit 0
#   failed  appends an `outcome=failed` line — the real deliver.sh's fail-soft exit 0
#   crash   exit 1, no receipt
#   hang    sleeps 300 so the caller's timeout is what ends it
# Receipt lines are one JSON object each, the bin/delivery_receipt.py shape.
set -u
printf '%s\n' "$*" >> "$FAKE_DIR/argv.log"
job=""; subject=""; route=""
while [ $# -gt 0 ]; do
  case "$1" in
    --job) job=$2; shift ;;
    --route) route=$2; shift ;;
    --subject) subject=$2; shift ;;
    --message) printf '%s\n' "$2" >> "$FAKE_DIR/messages.log"; shift ;;
  esac
  shift
done
printf 'job=%s route=%s subject=%s DELIVER_DISCORD=%s\n' "$job" "$route" "$subject" "${DELIVER_DISCORD:-unset}" \
  >> "$FAKE_DIR/argv.log"
receipt() {  # receipt <outcome> <buzz_result>
  python3 - "$DELIVERY_RECEIPTS" "$job" "$route" "$subject" "$1" "$2" "${FAKE_EVENT_ID:-}" "${FAKE_CHANNEL:-}" <<'PY'
import json, sys, datetime
path, job, route, subject, outcome, result, event, channel = sys.argv[1:]
line = {"schema": 1, "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(), "job": job,
        "route": route, "channel": channel, "subject": subject, "buzz_attempted": True,
        "buzz_result": result, "buzz_event_id": event if result == "ok" else "",
        "outcome": outcome, "error": "" if result == "ok" else "transport_error",
        "detail": "" if result == "ok" else "relay refused"}
with open(path, "a") as fh:
    fh.write(json.dumps(line) + "\n")
PY
}
case "${FAKE_DELIVER_MODE:-ok}" in
  ok) receipt delivered ok; exit 0 ;;
  failed) receipt failed failed; exit 0 ;;
  crash) exit 1 ;;
  hang) sleep 300; exit 0 ;;
  *) echo "fake deliver.sh: unknown FAKE_DELIVER_MODE" >&2; exit 2 ;;
esac
