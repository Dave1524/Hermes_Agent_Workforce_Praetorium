#!/usr/bin/env bash
# deliver.sh — the single owner of Discord and Buzz transport for scheduled output.
#
# usage: deliver.sh --job <unit> --route <key> --subject <text>
#                   [--message <text>] [--file <exact-path>] [--note <digest>]
#                   [--runtime <name>] [--run-marker <path>] [--max-age-secs <n>]
#
# Every other script in bin/ is an INPUT adapter: it parses its own caller interface,
# selects a payload, and invokes this once. Nothing else may call `hermes send`,
# `buzz messages send` or `buzz social publish` — tests/test_buzz_unit_wiring.sh
# enforces that.
#
# FAIL-SOFT BY CONTRACT. Configuration errors and transport errors both exit 0, because
# a work-producing unit that is marked failed by a delivery hiccup fires
# OnFailure=agent-alert@ — which then tries to deliver the alert down the same broken
# path. Fail-soft is not the same as silent: every invocation writes exactly one
# categorized receipt, and bin/audit_buzz_dual_run.sh reads those, not the journal.
#
# CREDENTIAL BOUNDARY. This script never reads, receives, logs or forwards a private
# key. It knows only an identity slug and the Buzz CLI arguments; bin/buzz_publish.sh
# resolves that slug to a credential file under the deny-listed ~/.config/buzz-agents/
# and execs the absolute buzz binary. The helper itself carries no secret, which is why
# it lives in the repo and is version-controlled — only the .env files it reads are
# withheld. BUZZ_PRIVATE_KEY / BUZZ_AUTH_TAG are stripped from the helper's environment
# here so a leaked service-level variable cannot ride along.
set -uo pipefail

BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROUTES_FILE="${BUZZ_ROUTES_FILE:-$BIN_DIR/buzz_routes.env}"
NOTE_BIN="${BUZZ_NOTE_BIN:-$BIN_DIR/buzz_note.py}"
RECEIPT_BIN="${DELIVERY_RECEIPT_BIN:-$BIN_DIR/delivery_receipt.py}"
HELPER="${BUZZ_DELIVER_HELPER:-$BIN_DIR/buzz_publish.sh}"
IDENTITY="${BUZZ_SERVICE_IDENTITY:-praetorium}"
NOTE_MAX_BYTES="${BUZZ_NOTE_MAX_BYTES:-800}"
# Both defaults are assigned on their own line, never as a ${VAR:-default}: bash ends that
# expansion at the first unescaped `}`, so a literal {placeholder} in the default loses its
# closing brace and appends a stray `}` — to the caller's value too, not just the default.
# Desktop's copy-link form; the CLI neither emits nor parses it. Verified 2026-08-07.
POINTER_TEMPLATE="${BUZZ_POINTER_TEMPLATE:-}"
[ -n "$POINTER_TEMPLATE" ] || POINTER_TEMPLATE='buzz://message?channel={channel}&id={event}'
# Pulse's "everyone" view has no time-based grouping — it renders one card per note.
# A reply nests under its root there, so threading is the only way a night of deliveries
# reads as one card instead of N. Verified 2026-08-07.
PULSE_ROOT_FILE="${BUZZ_PULSE_ROOT_FILE:-$HOME/var/buzz-pulse-root}"
PULSE_ROOT_TEMPLATE="${BUZZ_PULSE_ROOT_TEMPLATE:-}"
[ -n "$PULSE_ROOT_TEMPLATE" ] || PULSE_ROOT_TEMPLATE='Praetorium — {date}'
RECEIPTS="${DELIVERY_RECEIPTS:-$HOME/logs/delivery-receipts.jsonl}"
DELIVER_DISCORD="${DELIVER_DISCORD:-1}"
LOG="${DELIVERY_LOG:-$HOME/logs/deliver.log}"

mkdir -p "$(dirname "$RECEIPTS")" "$(dirname "$LOG")" 2>/dev/null || true
workdir=$(mktemp -d) || workdir=""
cleanup() { [ -n "$workdir" ] && rm -rf "$workdir"; }
trap cleanup EXIT

redact() {
  sed -E 's/nsec1[02-9ac-hj-np-z]{10,}/[redacted]/g
          s/(private[_-]?key|auth[_-]?tag|api[_-]?key|token)("?[[:space:]]*[:=][[:space:]]*"?)[^[:space:]",]+/\1\2[redacted]/Ig'
}
log_line() {
  printf '%s deliver: %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$*" \
    | redact >> "$LOG" 2>/dev/null || true
}

job=""; route=""; subject=""; message=""; artifact=""; digest=""; runtime="unknown"
run_marker=""; max_age=0
while [ $# -gt 0 ]; do
  case "$1" in
    --job)          job="${2:-}" ;;
    --route)        route="${2:-}" ;;
    --subject)      subject="${2:-}" ;;
    --message)      message="${2:-}" ;;
    --file)         artifact="${2:-}" ;;
    --note)         digest="${2:-}" ;;
    --runtime)      runtime="${2:-}" ;;
    --run-marker)   run_marker="${2:-}" ;;
    --max-age-secs) max_age="${2:-0}" ;;
    *) log_line "unrecognized argument: $1"; shift; continue ;;
  esac
  shift 2 2>/dev/null || shift
done

error=""; detail=""; anchor="none"; channel=""
discord_attempted=false; discord_result="skipped"
buzz_attempted=false;    buzz_result="skipped";  buzz_event_id=""
pulse_attempted=false;   pulse_result="skipped"; pulse_event_id=""

fault() {  # fault <category> <detail> — first fault wins; it is the root cause
  [ -n "$error" ] && return 0
  error="$1"; detail="$2"
  log_line "$error: $detail (job=${job:-?} route=${route:-?})"
}

emit_receipt() {  # emit_receipt <outcome>
  local fields=(
    "job=${job:-unknown}" "route=${route:-unknown}" "channel=$channel"
    "subject=$subject" "runtime=$runtime"
    "payload_type=$([ -n "$artifact" ] && echo file || echo text)"
    "anchor=$anchor" "run_marker=$run_marker"
    "discord_attempted=$discord_attempted" "discord_result=$discord_result"
    "buzz_attempted=$buzz_attempted" "buzz_result=$buzz_result"
    "buzz_event_id=$buzz_event_id"
    "pulse_attempted=$pulse_attempted" "pulse_result=$pulse_result"
    "pulse_event_id=$pulse_event_id"
    # The slug, not the pubkey: `buzz messages send` answers
    # {accepted, event_id, message} and never echoes the author back. Resolve the
    # author from the relay via buzz_event_id when an audit needs it.
    "identity=$IDENTITY"
    "outcome=$1" "error=$error" "detail=$detail"
  )
  if [ -n "$artifact" ] && [ -f "$artifact" ]; then
    fields+=(
      "artifact=$(basename "$artifact")"
      "artifact_bytes=$(stat -c %s "$artifact" 2>/dev/null || echo 0)"
      "artifact_sha256=$(sha256sum "$artifact" 2>/dev/null | cut -d' ' -f1)"
    )
  fi
  python3 "$RECEIPT_BIN" --path "$RECEIPTS" "${fields[@]}" 2>/dev/null \
    || log_line "receipt write failed for job=${job:-unknown}"
}

finish() {  # finish <outcome> — one receipt, always exit 0
  emit_receipt "$1"
  exit 0
}

settle() {
  local ok=0 bad=0 r
  for r in "$discord_result" "$buzz_result" "$pulse_result"; do
    [ "$r" = ok ] && ok=$((ok + 1))
    [ "$r" = failed ] && bad=$((bad + 1))
  done
  [ "$buzz_attempted" = false ] && [ -n "$error" ] && bad=$((bad + 1))
  if [ "$ok" -gt 0 ] && [ "$bad" -gt 0 ]; then finish partial_success; fi
  [ "$ok" -gt 0 ] && finish delivered
  finish failed
}

# ── 1. argument contract ────────────────────────────────────────────────────────
if [ -z "$job" ] || [ -z "$route" ] || [ -z "$subject" ]; then
  fault config_error "missing required argument (--job/--route/--subject)"
  finish skipped
fi
if [ -z "$message" ] && [ -z "$artifact" ]; then
  fault config_error "no payload: one of --message or --file is required"
  finish skipped
fi

# ── 2. artifact anchoring ───────────────────────────────────────────────────────
# A stale artifact must never certify a new run. When the caller supplies a run
# marker the artifact is compared against THIS invocation and a missing marker fails
# closed; the age budget is the weaker legacy anchor and is recorded as such so the
# auditor can see which producers still rely on it.
validate_artifact() {
  if [ ! -f "$artifact" ] || [ ! -s "$artifact" ]; then
    fault artifact_error "artifact missing or empty: $artifact"
    return 1
  fi
  if [ -n "$run_marker" ]; then
    anchor="run_marker"
    if [ ! -f "$run_marker" ]; then
      fault artifact_error "run marker missing: $run_marker"
      return 1
    fi
    if [ ! "$artifact" -nt "$run_marker" ]; then
      fault artifact_error "artifact predates this run's marker: $(basename "$artifact")"
      return 1
    fi
    return 0
  fi
  if [ "$max_age" -gt 0 ]; then
    anchor="age_budget"
    local age=$(( $(date +%s) - $(stat -c %Y "$artifact" 2>/dev/null || echo 0) ))
    if [ "$age" -gt "$max_age" ]; then
      fault artifact_error "artifact ${age}s old exceeds ${max_age}s budget"
      return 1
    fi
  fi
  return 0
}
if [ -n "$artifact" ] && ! validate_artifact; then
  finish skipped
fi

# ── 3. Discord (independent of Buzz for the whole dual-run) ─────────────────────
hermes_send() {
  local bin=""
  if [ -n "${HERMES_BIN:-}" ] && [ -x "${HERMES_BIN:-}" ]; then
    bin="$HERMES_BIN"
  elif [ -x "$HOME/.hermes/hermes-agent/venv/bin/hermes" ]; then
    bin="$HOME/.hermes/hermes-agent/venv/bin/hermes"
  elif [ -x "$HOME/.local/bin/hermes" ]; then
    bin="$HOME/.local/bin/hermes"
  fi
  if [ -z "$bin" ]; then
    local py="$HOME/.hermes/hermes-agent/venv/bin/python"
    [ -x "$py" ] || return 127
    set -- -m hermes_cli.main send "$@"
    bin="$py"
  fi
  if [ -n "$artifact" ]; then
    "$bin" send --to discord --subject "$subject" --file "$artifact" --quiet
  else
    "$bin" send --to discord --subject "$subject" "$message" --quiet
  fi
}

if [ "$DELIVER_DISCORD" = 1 ]; then
  discord_attempted=true
  if hermes_send >/dev/null 2>&1; then
    discord_result="ok"
  else
    discord_result="failed"
    fault discord_error "hermes send --to discord failed or no entrypoint resolved"
  fi
fi

# ── 4. route + helper resolution (never via PATH) ───────────────────────────────
resolve_route() {
  case "$route" in
    [a-z]|[a-z][a-z0-9_-]*) ;;
    *) return 1 ;;
  esac
  [ -r "$ROUTES_FILE" ] || return 1
  channel=$(sed -n "s/^ROUTE_${route}=//p" "$ROUTES_FILE" | tail -1 | tr -d "\"' \\r")
  [ -n "$channel" ]
}

if ! resolve_route; then
  fault config_error "route '$route' has no channel UUID in $ROUTES_FILE"
  settle
fi
if [ ! -x "$HELPER" ]; then
  fault config_error "credential helper not executable: $HELPER"
  settle
fi

# ── 5. Buzz channel message ─────────────────────────────────────────────────────
helper_out="$workdir/out"; helper_err="$workdir/err"
buzz_call() {
  env -u BUZZ_PRIVATE_KEY -u BUZZ_AUTH_TAG "$HELPER" "$IDENTITY" "$@" \
    >"$helper_out" 2>"$helper_err"
}

categorize() {  # map the Buzz CLI's documented exit codes + error body to a category
  local rc=$1 body; body=$(cat "$helper_err" 2>/dev/null)
  case "$body" in
    *"not a member"*|*"not a relay member"*|*membership*|*forbidden*)
      echo membership_error; return ;;
  esac
  case "$rc" in
    2) echo network_error ;;
    3) echo auth_error ;;
    *) echo transport_error ;;
  esac
}

read_event_id() {  # event id from the helper's JSON stdout
  python3 - "$helper_out" <<'PY'
import json, sys
try:
    doc = json.load(open(sys.argv[1]))
except Exception:
    doc = {}
if not isinstance(doc, dict):
    doc = {}
nested = doc.get("event") or doc.get("data") or {}
if not isinstance(nested, dict):
    nested = {}
for source in (doc, nested):
    for key in ("event_id", "id", "eventId"):
        if isinstance(source.get(key), str):
            print(source[key])
            raise SystemExit
print("")
PY
}

resolve_pulse_root() {  # today's thread root, published once a day; empty output on failure
  local today root="" stored_date="" stored_id=""
  today=$(date +%F)
  if [ -f "$PULSE_ROOT_FILE" ]; then
    IFS=$'\t' read -r stored_date stored_id < "$PULSE_ROOT_FILE" || true
  fi
  if [ "$stored_date" = "$today" ] && [ -n "$stored_id" ]; then
    printf '%s' "$stored_id"; return 0
  fi
  buzz_call social publish --content "${PULSE_ROOT_TEMPLATE//\{date\}/$today}" || return 0
  root=$(read_event_id) || true
  [ -n "$root" ] || return 0
  mkdir -p "$(dirname "$PULSE_ROOT_FILE")" 2>/dev/null || true
  printf '%s\t%s\n' "$today" "$root" > "$PULSE_ROOT_FILE"
  printf '%s' "$root"
}

content="$subject"
[ -n "$message" ] && content="$subject"$'\n\n'"$message"

buzz_attempted=true
send_args=(messages send --channel "$channel" --content "$content")
[ -n "$artifact" ] && send_args+=(--file "$artifact")
if buzz_call "${send_args[@]}"; then
  buzz_result="ok"
  buzz_event_id=$(read_event_id)
else
  rc=$?  # must be the first statement: any assignment would overwrite it with 0
  buzz_result="failed"
  fault "$(categorize "$rc")" "buzz messages send failed for route $route"
  settle
fi

# ── 6. bounded NIP-01 note, only after the channel send landed ──────────────────
pointer=${POINTER_TEMPLATE//\{channel\}/$channel}
pointer=${pointer//\{event\}/$buzz_event_id}

note_args=(--headline "$subject" --job "$job" --runtime "$runtime"
           --pointer "$pointer" --max-bytes "$NOTE_MAX_BYTES")
digest_source="$digest"
[ -z "$digest_source" ] && digest_source="$message"
while IFS= read -r line; do
  [ -n "$line" ] && note_args+=(--digest "$line")
done <<< "$digest_source"

pulse_attempted=true
note_text=$(python3 "$NOTE_BIN" "${note_args[@]}" 2>/dev/null)
publish_args=(social publish --content "$note_text")
pulse_root=""
[ -n "$note_text" ] && pulse_root=$(resolve_pulse_root)
[ -n "$pulse_root" ] && publish_args+=(--reply-to "$pulse_root")
if [ -n "$note_text" ] && buzz_call "${publish_args[@]}"; then
  pulse_result="ok"
  pulse_event_id=$(read_event_id)
else
  rc=$?
  pulse_result="failed"
  fault "$(categorize "$rc")" "buzz social publish failed after channel event $buzz_event_id"
fi

settle
