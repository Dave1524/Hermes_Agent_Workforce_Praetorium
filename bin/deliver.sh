#!/usr/bin/env bash
# deliver.sh — the single owner of Discord and Buzz transport for scheduled output.
#
# usage: deliver.sh --job <unit> --route <key> --subject <text>
#                   [--message <text>] [--file <exact-path>] [--note <digest>]
#                   [--runtime <name>] [--run-marker <path>] [--max-age-secs <n>]
#                   [--canvas off|mirror|only]
#                   [--artifact-type <t>] [--target <path>] [--operation <op>]
#                   [--base-revision <rev>] [--risk-tier auto|review|strict]
#                   [--acceptance-check <text>]...
#
# Every other script in bin/ is an INPUT adapter: it parses its own caller interface,
# selects a payload, and invokes this once. Nothing else may call `hermes send`,
# `buzz messages send`, `buzz social publish` or `buzz canvas set` —
# tests/test_buzz_unit_wiring.sh enforces that.
#
# THE ARTIFACT IS THE REVIEW SURFACE. A message that only names what a run produced is
# not reviewable in Buzz, and for the proposal producers it was the whole delivery. The
# body therefore travels on stdin (`--content -`), which removes the kernel's
# MAX_ARG_STRLEN ceiling on a single argument, and the only remaining limit is the Buzz
# CLI's own MAX_CONTENT_BYTES. An artifact-carrying message leads with a typed envelope
# so a downstream broker can identify, hash-check and supersede it without parsing prose;
# docs/buzz-artifact-envelope.md is the normative spec.
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
# buzz-cli refuses a larger --content outright (crates/buzz-cli/src/validate.rs:4,
# MAX_CONTENT_BYTES = 65_536; the relay itself allows 256 KiB, so the CLI is the binding
# constraint). It is a ceiling on the WHOLE content — subject and envelope included — so
# the artifact's share is computed by subtraction rather than assumed.
CONTENT_CEILING=65536
CONTENT_MAX_BYTES="${BUZZ_CONTENT_MAX_BYTES:-$CONTENT_CEILING}"
case "$CONTENT_MAX_BYTES" in ''|*[!0-9]*) CONTENT_MAX_BYTES=$CONTENT_CEILING ;; esac
# Legacy knob: it bounded the artifact when the body was one argv string. Honoured only
# downwards, so a caller that pinned it still gets a smaller message, never a larger one.
case "${BUZZ_INLINE_MAX_BYTES:-}" in
  ''|*[!0-9]*) ;;
  *) [ "$BUZZ_INLINE_MAX_BYTES" -lt "$CONTENT_MAX_BYTES" ] \
       && CONTENT_MAX_BYTES="$BUZZ_INLINE_MAX_BYTES" ;;
esac
ARTIFACT_STATE="${BUZZ_ARTIFACT_STATE:-$HOME/var/buzz-artifact-ids}"
CANVAS_STATE="${BUZZ_CANVAS_STATE:-$HOME/var/buzz-canvas-hashes}"
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
run_marker=""; max_age=0; canvas_mode="off"
artifact_type="report"; target="none"; operation="none"; base_revision="unknown"
risk_tier="review"; acceptance_checks=()
while [ $# -gt 0 ]; do
  case "$1" in
    --job)              job="${2:-}" ;;
    --route)            route="${2:-}" ;;
    --subject)          subject="${2:-}" ;;
    --message)          message="${2:-}" ;;
    --file)             artifact="${2:-}" ;;
    --note)             digest="${2:-}" ;;
    --runtime)          runtime="${2:-}" ;;
    --run-marker)       run_marker="${2:-}" ;;
    --max-age-secs)     max_age="${2:-0}" ;;
    --canvas)           canvas_mode="${2:-off}" ;;
    --artifact-type)    artifact_type="${2:-report}" ;;
    --target)           target="${2:-none}" ;;
    --operation)        operation="${2:-none}" ;;
    --base-revision)    base_revision="${2:-unknown}" ;;
    --risk-tier)        risk_tier="${2:-review}" ;;
    --acceptance-check) acceptance_checks+=("${2:-}") ;;
    *) log_line "unrecognized argument: $1"; shift; continue ;;
  esac
  shift 2 2>/dev/null || shift
done

error=""; detail=""; anchor="none"; channel=""; kind=9
artifact_id=""; content_sha256=""; supersedes="none"
discord_attempted=false; discord_result="skipped"
buzz_attempted=false;    buzz_result="skipped";  buzz_event_id=""; buzz_payload="none"
pulse_attempted=false;   pulse_result="skipped"; pulse_event_id=""
canvas_attempted=false;  canvas_result="skipped"

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
    "buzz_event_id=$buzz_event_id" "buzz_payload=$buzz_payload" "kind=$kind"
    "artifact_id=$artifact_id" "supersedes=$supersedes"
    "canvas_attempted=$canvas_attempted" "canvas_result=$canvas_result"
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
  # `unchanged` is a canvas that already holds exactly this content. Nothing failed and
  # the intended state is present, so it settles as a success — otherwise a `--canvas
  # only` producer would report failed on every quiet week, which is most weeks.
  for r in "$discord_result" "$buzz_result" "$canvas_result" "$pulse_result"; do
    { [ "$r" = ok ] || [ "$r" = unchanged ]; } && ok=$((ok + 1))
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
case "$canvas_mode" in
  off|mirror|only) ;;
  *) fault config_error "--canvas '$canvas_mode' is not off, mirror or only"; finish skipped ;;
esac
# The default leans toward asking Dave. A caller that wants an artifact auto-applied has
# to say so; nothing may arrive at `auto` by omission, and no confidence score upgrades it.
case "$risk_tier" in
  auto|review|strict) ;;
  *) fault config_error "--risk-tier '$risk_tier' is not auto, review or strict"; finish skipped ;;
esac
if [ "$CONTENT_MAX_BYTES" -gt "$CONTENT_CEILING" ]; then
  fault config_error "content ceiling ${CONTENT_MAX_BYTES}B exceeds the Buzz CLI limit of ${CONTENT_CEILING}B"
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

# The event kind is a property of the DESTINATION, not of the producer: whether a channel
# is read as a running feed or as reviewable threads is one decision per channel, and
# scattering it across the units is how half of them would end up disagreeing. 45003 is
# excluded on purpose — it is a forum COMMENT and buzz-cli requires --reply-to for it
# (crates/buzz-cli/src/commands/messages.rs:652), and no scheduled producer replies to an
# existing thread. Rejecting it here keeps the fault on our side of the boundary instead
# of surfacing as an opaque CLI usage error categorized as a transport failure.
resolve_route_kind() {
  kind=$(sed -n "s/^ROUTE_${route}_kind=//p" "$ROUTES_FILE" | tail -1 | tr -d "\"' \\r")
  [ -n "$kind" ] || kind=9
  case "$kind" in
    9|45001) return 0 ;;
    45003)
      fault config_error "route '$route' declares kind 45003; a forum comment needs --reply-to and no producer replies"
      return 1 ;;
    *)
      fault config_error "route '$route' declares unsupported kind '$kind' (use 9 or 45001)"
      return 1 ;;
  esac
}

if ! resolve_route; then
  fault config_error "route '$route' has no channel UUID in $ROUTES_FILE"
  settle
fi
if ! resolve_route_kind; then
  settle
fi
if [ ! -x "$HELPER" ]; then
  fault config_error "credential helper not executable: $HELPER"
  settle
fi

# ── 5. Buzz channel message ─────────────────────────────────────────────────────
helper_out="$workdir/out"; helper_err="$workdir/err"
# Set to a file for the calls that pass `--content -`; every other call is given
# /dev/null so the helper can never inherit and block on the caller's stdin.
call_stdin="/dev/null"
buzz_call() {
  env -u BUZZ_PRIVATE_KEY -u BUZZ_AUTH_TAG "$HELPER" "$IDENTITY" "$@" \
    <"$call_stdin" >"$helper_out" 2>"$helper_err"
}

categorize() {  # map the Buzz CLI's documented exit codes + error body to a category
  local rc=$1 body; body=$(cat "$helper_err" 2>/dev/null)
  case "$body" in
    *"not a member"*|*"not a relay member"*|*membership*|*forbidden*)
      echo membership_error; return ;;
  esac
  case "$body" in
    *"unsupported file type"*) echo artifact_error; return ;;
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

# The relay's Blossom store accepts media only. The CLI declares every other file as
# application/octet-stream, which the upload endpoint refuses outright, so a text
# artifact reaches a Buzz channel as message body or it does not reach it at all.
# Discord still gets the attachment, and the receipt still carries the sha256.
is_media_artifact() {
  case "$(file -b --mime-type "$artifact" 2>/dev/null)" in
    image/*|video/*|audio/*) return 0 ;;
  esac
  return 1
}

# ── 5a. typed envelope ──────────────────────────────────────────────────────────
# A pointer is not a review surface, and neither is an artifact a reader has to diff by
# eye against the last one. The envelope states what this is, what it would change, what
# it hashes to and which delivery it replaces — enough for a broker to verify a decision
# without reading the prose. docs/buzz-artifact-envelope.md is the normative spec.
#
# artifact_id is derived, not minted: the same job re-delivering the same artifact name
# must land on the same id or supersession chains break on every restart.
derive_artifact_id() {
  printf '%s\0%s' "$job" "$(basename "$artifact")" | sha256sum | cut -c1-16
}

previous_event() {  # previous_event <artifact_id>
  [ -r "$ARTIFACT_STATE" ] || return 0
  sed -n "s/^$1\t//p" "$ARTIFACT_STATE" | tail -1
}

record_artifact_event() {  # record_artifact_event <artifact_id> <event_id>
  [ -n "$2" ] || return 0
  mkdir -p "$(dirname "$ARTIFACT_STATE")" 2>/dev/null || true
  local tmp="$workdir/artifact-state"
  { [ -r "$ARTIFACT_STATE" ] && grep -v "^$1	" "$ARTIFACT_STATE"
    printf '%s\t%s\n' "$1" "$2"; } > "$tmp" 2>/dev/null && mv "$tmp" "$ARTIFACT_STATE"
}

render_envelope() {
  python3 - "$artifact_id" "$artifact_type" "$target" "$operation" "$content_sha256" \
            "$base_revision" "$risk_tier" "$supersedes" "${acceptance_checks[@]}" <<'PY'
import json, sys

KEYS = ["artifact_id", "artifact_type", "target", "operation",
        "content_sha256", "base_revision", "risk_tier", "supersedes"]
values, checks = sys.argv[1:1 + len(KEYS)], sys.argv[1 + len(KEYS):]
out = ["```yaml"]
out += ["%s: %s" % (k, json.dumps(v)) for k, v in zip(KEYS, values)]
if checks:
    out.append("acceptance_checks:")
    out += ["  - %s" % json.dumps(c) for c in checks]
else:
    out.append("acceptance_checks: []")
out.append("```")
print("\n".join(out))
PY
}

envelope=""
if [ -n "$artifact" ]; then
  artifact_id=$(derive_artifact_id)
  content_sha256=$(sha256sum "$artifact" 2>/dev/null | cut -d' ' -f1)
  supersedes=$(previous_event "$artifact_id")
  [ -n "$supersedes" ] || supersedes="none"
  envelope=$(render_envelope)
fi

# ── 5b. compose the content inside the CLI's byte ceiling ───────────────────────
fit_body() {  # fit_body <budget> — body on stdin, cut at a line boundary if oversized
  python3 - "$1" "${artifact:-}" <<'PY'
import sys

budget, origin = int(sys.argv[1]), sys.argv[2]
raw = sys.stdin.buffer.read()
if len(raw) <= budget:
    sys.stdout.buffer.write(raw)
    raise SystemExit
tail = " — full artifact: " + origin if origin else ""
notice = "\n\n[truncated at {n} of %d bytes%s]\n" % (len(raw), tail)
# The notice is measured at its widest (the budget has at least as many digits as any
# length it can report), so the cut can never be undone by the notice it makes room for.
room = budget - len(notice.format(n=budget).encode("utf-8"))
head = raw[:max(room, 0)]
cut = head.rfind(b"\n")
if cut > 0:
    head = head[:cut]
sys.stdout.write(head.decode("utf-8", "replace"))
sys.stdout.write(notice.format(n=len(head)))
PY
}

header="$subject"
[ -n "$envelope" ] && header="$subject"$'\n\n'"$envelope"

body_source="$workdir/body"
if [ -n "$artifact" ] && ! is_media_artifact; then
  buzz_payload="inline"
  cp "$artifact" "$body_source" 2>/dev/null || : > "$body_source"
elif [ -n "$artifact" ]; then
  buzz_payload="attached"
  printf '%s' "$message" > "$body_source"
else
  printf '%s' "$message" > "$body_source"
fi

budget=$(( CONTENT_MAX_BYTES - $(printf '%s\n\n' "$header" | wc -c) ))
if [ "$budget" -le 0 ]; then
  fault config_error "subject and envelope alone exceed the ${CONTENT_MAX_BYTES}B content ceiling"
  settle
fi

content_file="$workdir/content"
printf '%s' "$header" > "$content_file"
if [ -s "$body_source" ]; then
  printf '\n\n' >> "$content_file"
  fit_body "$budget" < "$body_source" >> "$content_file"
fi

# ── 5c. Buzz channel message ────────────────────────────────────────────────────
send_message() {
  buzz_attempted=true
  local send_args=(messages send --channel "$channel" --content -)
  [ "$kind" != 9 ] && send_args+=(--kind "$kind")
  [ "$buzz_payload" = attached ] && send_args+=(--file "$artifact")
  call_stdin="$content_file"
  if buzz_call "${send_args[@]}"; then
    call_stdin="/dev/null"
    buzz_result="ok"
    buzz_event_id=$(read_event_id)
    [ -n "$artifact_id" ] && record_artifact_event "$artifact_id" "$buzz_event_id"
    return 0
  fi
  local rc=$?  # must be the first statement: any assignment would overwrite it with 0
  call_stdin="/dev/null"
  buzz_result="failed"
  fault "$(categorize "$rc")" "buzz messages send failed for route $route"
  return 1
}

if [ "$canvas_mode" != only ] && ! send_message; then
  settle
fi

# ── 5d. canvas: one living document per channel, one designated writer ──────────
# A recurring rollup that posts a new message every week buries the previous one and
# gives the channel N copies of the same document. The canvas is the same content held
# at one address, so `unchanged` is a real outcome and must not read as a failure.
canvas_hash_stored() {
  [ -r "$CANVAS_STATE" ] || return 0
  sed -n "s/^$channel\t//p" "$CANVAS_STATE" | tail -1
}

record_canvas_hash() {  # record_canvas_hash <hash>
  mkdir -p "$(dirname "$CANVAS_STATE")" 2>/dev/null || true
  local tmp="$workdir/canvas-state"
  { [ -r "$CANVAS_STATE" ] && grep -v "^$channel	" "$CANVAS_STATE"
    printf '%s\t%s\n' "$channel" "$1"; } > "$tmp" 2>/dev/null && mv "$tmp" "$CANVAS_STATE"
}

if [ "$canvas_mode" != off ]; then
  canvas_attempted=true
  canvas_hash=$(sha256sum "$content_file" 2>/dev/null | cut -d' ' -f1)
  if [ -n "$canvas_hash" ] && [ "$canvas_hash" = "$(canvas_hash_stored)" ]; then
    canvas_result="unchanged"
  else
    call_stdin="$content_file"
    if buzz_call canvas set --channel "$channel" --content -; then
      call_stdin="/dev/null"
      canvas_result="ok"
      record_canvas_hash "$canvas_hash"
    else
      rc=$?
      call_stdin="/dev/null"
      canvas_result="failed"
      fault "$(categorize "$rc")" "buzz canvas set failed for route $route"
    fi
  fi
fi

[ "$canvas_mode" = only ] && settle

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
