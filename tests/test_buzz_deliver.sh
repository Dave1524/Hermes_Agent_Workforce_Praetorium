#!/usr/bin/env bash
# Offline-by-contract suite for bin/deliver.sh — the single transport owner.
#
# Nothing here can reach a relay or a real credential: every case runs in a throwaway
# HOME with a mock credential helper and a mock hermes entrypoint, and a decoy `buzz`
# and `hermes` on PATH exist only to prove deliver.sh never resolves either via PATH.
#
# The invariant that matters most is fail-soft: a work-producing unit must never be
# marked failed because a transport was unavailable (that would fire OnFailure=
# agent-alert@ for a non-event, which would itself try to deliver). Every case asserts
# exit 0 and a categorized receipt.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/deliver.sh"

CH_ID=1111111111111111111111111111111111111111111111111111111111111111
NOTE_ID=2222222222222222222222222222222222222222222222222222222222222222
AGENT_HEX=3333333333333333333333333333333333333333333333333333333333333333
FAKE_NSEC=nsec1qqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqqq

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match,
# so whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that
# was found — failing a true assertion, and silently passing a negated one. It is scoped
# off here rather than per-condition so a later `| grep -q` cannot reintroduce it.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# ── Sandbox: throwaway HOME + mock helper + mock hermes + decoy PATH binaries ──
sandbox() {
  local h; h=$(mktemp -d)
  mkdir -p "$h/logs" "$h/mock" "$h/pathbin" "$h/artifacts"

  cat > "$h/helper.sh" <<'SH'
#!/usr/bin/env bash
# Mock of the Dave-created credential helper. Records argv + env, emits canned JSON.
# Contract under test: argv is `<identity> <buzz-subcommand...>` and nothing else.
mkdir -p "$MOCK_DIR"
# One log line per invocation: a published note is deliberately multi-line, and
# logging argv verbatim would make a single call look like several.
printf '%s\n' "$(printf '%s' "$*" | tr '\n' ' ')" >> "$MOCK_DIR/argv.log"
env >> "$MOCK_DIR/env.log"
sub=$2
prev=""
for a in "$@"; do
  if [ "$prev" = "--content" ]; then
    # `--content -` is the CLI's documented stdin form; the body never appears in argv.
    if [ "$a" = "-" ]; then cat > "$MOCK_DIR/content.$sub"
    else printf '%s' "$a" > "$MOCK_DIR/content.$sub"
    fi
  fi
  prev="$a"
done
case "$sub" in
  messages) rc=${MOCK_CHANNEL_RC:-0}; id=$MOCK_CHANNEL_ID ;;
  social)   rc=${MOCK_SOCIAL_RC:-0};  id=$MOCK_SOCIAL_ID ;;
  *)        rc=1; id="" ;;
esac
if [ "$rc" -ne 0 ]; then
  printf '{"error":"%s","message":"mock failure"}\n' "${MOCK_ERROR:-other}" >&2
  exit "$rc"
fi
printf '{"accepted":true,"event_id":"%s","message":"published"}\n' "$id"
SH

  cat > "$h/hermes" <<'SH'
#!/usr/bin/env bash
mkdir -p "$MOCK_DIR"
printf '%s\n' "$*" >> "$MOCK_DIR/hermes.log"
exit "${MOCK_HERMES_RC:-0}"
SH

  for decoy in buzz hermes; do
    cat > "$h/pathbin/$decoy" <<'SH'
#!/usr/bin/env bash
touch "$MOCK_DIR/PATH_LEAK"
SH
    chmod +x "$h/pathbin/$decoy"
  done
  chmod +x "$h/helper.sh" "$h/hermes"

  printf 'ROUTE_ops=%s\nROUTE_research=\n' "$CH_ID" > "$h/routes.env"
  printf 'AGENT_marcus=%s\n' "$AGENT_HEX" > "$h/agents.env"
  echo "$h"
}

run_deliver() {
  local h=$1; shift
  HOME="$h" \
  PATH="$h/pathbin:$PATH" \
  MOCK_DIR="$h/mock" \
  MOCK_CHANNEL_ID="$CH_ID" \
  MOCK_SOCIAL_ID="$NOTE_ID" \
  BUZZ_ROUTES_FILE="$h/routes.env" \
  BUZZ_AGENTS_FILE="${AGENTS:-$h/agents.env}" \
  BUZZ_DELIVER_HELPER="${HELPER:-$h/helper.sh}" \
  HERMES_BIN="${HERMES:-$h/hermes}" \
  DELIVERY_RECEIPTS="$h/receipts.jsonl" \
  DELIVERY_LOG="$h/deliver.log" \
  bash "$SCRIPT" "$@" >/dev/null 2>&1
  echo $?
}

field() {  # field <sandbox> <key> -> value of that key on the LAST receipt
  python3 - "$1/receipts.jsonl" "$2" <<'PY'
import json, sys
try:
    lines = [l for l in open(sys.argv[1]).read().splitlines() if l.strip()]
    print(json.loads(lines[-1]).get(sys.argv[2], ""))
except Exception:
    print("<no-receipt>")
PY
}
nreceipts() { [ -f "$1/receipts.jsonl" ] && grep -c . "$1/receipts.jsonl" || echo 0; }
ncalls()    { [ -f "$1/mock/argv.log" ] && grep -c . "$1/mock/argv.log" || echo 0; }

echo '--- route resolution + happy path ---'
h=$(sandbox)
printf 'body\n' > "$h/artifacts/morning-report-1.md"
rc=$(run_deliver "$h" --job overnight-morning-report.service --route ops \
       --subject '[Praetorium] Morning report' --file "$h/artifacts/morning-report-1.md" \
       --runtime claude-sonnet --note $'first line\nsecond line')
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'route resolved to the channel UUID' "[ \"\$(field '$h' channel)\" = '$CH_ID' ]"
assert 'outcome delivered' "[ \"\$(field '$h' outcome)\" = delivered ]"
assert 'channel event id captured' "[ \"\$(field '$h' buzz_event_id)\" = '$CH_ID' ]"
assert 'pulse event id captured' "[ \"\$(field '$h' pulse_event_id)\" = '$NOTE_ID' ]"
assert 'publishing identity recorded' "[ \"\$(field '$h' identity)\" = praetorium ]"
assert 'discord attempted and ok' "[ \"\$(field '$h' discord_result)\" = ok ]"
assert 'artifact sha256 recorded' "[ -n \"\$(field '$h' artifact_sha256)\" ]"
assert 'artifact basename recorded' "[ \"\$(field '$h' artifact)\" = morning-report-1.md ]"
assert 'exactly one receipt per invocation' "[ \"\$(nreceipts '$h')\" -eq 1 ]"
assert 'three helper calls: channel, day-root, pulse' "[ \"\$(ncalls '$h')\" -eq 3 ]"
assert 'helper called with the praetorium identity first' \
  "head -1 '$h/mock/argv.log' | grep -q '^praetorium messages send '"
assert 'the report reaches the channel as message body' "grep -q '^body$' '$h/mock/content.messages'"
assert 'nothing resolved via PATH' "[ ! -e '$h/mock/PATH_LEAK' ]"

echo '--- a text artifact is carried as body, because the store refuses non-media ---'
# The relay's Blossom store accepted an image/png and refused a text/plain as
# application/octet-stream (probed 2026-08-07). `--file` therefore cannot carry a report:
# every payload=file producer would post nothing while Discord quietly kept working.
h=$(sandbox)
printf '# Report\n\nline one\nline two\n' > "$h/artifacts/report.md"
rc=$(run_deliver "$h" --job x.service --route ops --subject s --file "$h/artifacts/report.md")
assert 'delivered' "[ \"\$(field '$h' outcome)\" = delivered ]"
assert 'no attachment offered to the relay' "! grep -q -- '--file' '$h/mock/argv.log'"
assert 'receipt records how the artifact was carried' "[ \"\$(field '$h' buzz_payload)\" = inline ]"
assert 'the artifact body is in the channel content' "grep -q '^line two$' '$h/mock/content.messages'"
assert 'the subject still leads the message' "head -1 '$h/mock/content.messages' | grep -q '^s$'"
assert 'discord still receives the attachment' "grep -q -- '--file $h/artifacts/report.md' '$h/mock/hermes.log'"
assert 'artifact provenance still recorded' "[ -n \"\$(field '$h' artifact_sha256)\" ]"

echo '--- a media artifact is still attached, and an oversized body is cut cleanly ---'
h=$(sandbox)
PNG_1X1=iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAACklEQVR4nGMAAQAABQABDQottAAAAABJRU5ErkJggg==
printf '%s' "$PNG_1X1" | base64 -d > "$h/artifacts/chart.png"
rc=$(run_deliver "$h" --job x.service --route ops --subject s --file "$h/artifacts/chart.png")
assert 'media is attached, not inlined' "grep -q -- '--file $h/artifacts/chart.png' '$h/mock/argv.log'"
assert 'receipt says attached' "[ \"\$(field '$h' buzz_payload)\" = attached ]"

h=$(sandbox)
python3 -c "open('$h/artifacts/big.md','w').write('héllo wörld — padding line\n' * 400)"
rc=$(BUZZ_INLINE_MAX_BYTES=500 run_deliver "$h" --job x.service --route ops \
       --subject s --file "$h/artifacts/big.md")
assert 'delivered despite the artifact exceeding the ceiling' "[ \"\$(field '$h' outcome)\" = delivered ]"
assert 'body is valid UTF-8 after the cut' \
  "python3 -c \"open('$h/mock/content.messages','rb').read().decode('utf-8')\""
assert 'the cut lands on a line boundary' \
  "! grep -q 'héllo wörld — paddi\$' '$h/mock/content.messages'"
assert 'truncation is stated, with the full artifact named' \
  "grep -q 'truncated at .* of .* bytes — full artifact: $h/artifacts/big.md' '$h/mock/content.messages'"

echo '--- an upload the store refuses is an artifact_error, not a vague transport_error ---'
h=$(sandbox)
printf 'x\n' > "$h/artifacts/chart.png"
rc=$(MOCK_CHANNEL_RC=1 MOCK_ERROR='unsupported file type: application/octet-stream' \
     run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'categorized artifact_error' "[ \"\$(field '$h' error)\" = artifact_error ]"

echo '--- unknown route: Buzz skipped, Discord still attempted ---'
h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route nosuchroute --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'error categorized config_error' "[ \"\$(field '$h' error)\" = config_error ]"
assert 'buzz not attempted' "[ \"\$(field '$h' buzz_attempted)\" = False ]"
assert 'discord still attempted and ok' "[ \"\$(field '$h' discord_result)\" = ok ]"
assert 'outcome partial_success (discord landed, buzz did not)' \
  "[ \"\$(field '$h' outcome)\" = partial_success ]"
assert 'helper never invoked' "[ \"\$(ncalls '$h')\" -eq 0 ]"

echo '--- unconfigured route (empty UUID) behaves the same ---'
h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route research --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'empty ROUTE_ value is a config_error' "[ \"\$(field '$h' error)\" = config_error ]"
assert 'discord still attempted' "[ \"\$(field '$h' discord_result)\" = ok ]"

echo '--- the route table decides the event kind, and only 9 or 45001 are sendable ---'
# A forum channel renders kinds:[45001] only, so a kind-9 post into one is accepted by
# the relay, receipted `ok`, and invisible to every reader — the failure mode that looks
# exactly like success. The kind therefore has to be pinned per destination and asserted.
sent_args() { grep 'messages send' "$1/mock/argv.log"; }
route_kind() { printf 'ROUTE_%s=%s\nROUTE_%s_kind=%s\n' "$2" "$CH_ID" "$2" "$3" >> "$1/routes.env"; }

h=$(sandbox); route_kind "$h" forum 45001
rc=$(run_deliver "$h" --job x.service --route forum --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'a forum route sends --kind 45001' "sent_args '$h' | grep -q -- '--kind 45001'"
assert 'and the receipt records the kind that was sent' "[ \"\$(field '$h' kind)\" = 45001 ]"
assert 'outcome delivered' "[ \"\$(field '$h' outcome)\" = delivered ]"

h=$(sandbox); printf 'ROUTE_ops_kind=9\n' >> "$h/routes.env"
rc=$(run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'a stream route sends no --kind at all' "! sent_args '$h' | grep -q -- '--kind'"
assert 'and still receipts kind 9' "[ \"\$(field '$h' kind)\" = 9 ]"

h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'a route with no kind line defaults to 9, unchanged' \
  "! sent_args '$h' | grep -q -- '--kind'"
assert 'and delivers exactly as before' "[ \"\$(field '$h' outcome)\" = delivered ]"

# 45003 is a forum COMMENT: buzz-cli refuses it without --reply-to, and no producer here
# replies to an existing thread. Rejecting it in our own config keeps the receipt honest
# instead of surfacing a CLI usage error as transport_error.
h=$(sandbox); route_kind "$h" comment 45003
rc=$(run_deliver "$h" --job x.service --route comment --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert '45003 is a config_error, not a send' "[ \"\$(field '$h' error)\" = config_error ]"
assert 'the helper is never invoked for it' "[ \"\$(ncalls '$h')\" -eq 0 ]"
assert 'discord still attempted' "[ \"\$(field '$h' discord_result)\" = ok ]"

h=$(sandbox); route_kind "$h" bogus 1234
rc=$(run_deliver "$h" --job x.service --route bogus --subject s --message m)
assert 'an unsupported kind is a config_error' "[ \"\$(field '$h' error)\" = config_error ]"
assert 'and nothing is sent under it' "[ \"\$(ncalls '$h')\" -eq 0 ]"

echo '--- the route table decides which agent a delivery wakes ---'
# The subscription rules run `require_mention = true`, so an event with no `p` tag is
# dropped by every agent no matter which author is admitted. Without a mention this whole
# transport delivers into channels nobody is listening to — 20 receipts, all `delivered`,
# zero turns. The route owns the decision for the same reason it owns the kind: it is one
# choice per destination, not per producer.
route_notify() { printf 'ROUTE_%s=%s\nROUTE_%s_notify=%s\n' "$2" "$CH_ID" "$2" "$3" >> "$1/routes.env"; }

h=$(sandbox); route_notify "$h" owned marcus
rc=$(run_deliver "$h" --job x.service --route owned --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the slug is resolved to a pubkey and mentioned' \
  "sent_args '$h' | grep -q -- '--mention $AGENT_HEX'"
assert 'the receipt names who it was addressed to' "[ \"\$(field '$h' notify)\" = marcus ]"
assert 'outcome delivered' "[ \"\$(field '$h' outcome)\" = delivered ]"
assert 'the pulse note is not addressed to the agent' \
  "[ \"\$(grep -c -- '--mention' '$h/mock/argv.log')\" -eq 1 ]"
assert 'the receipt records the slug, not the pubkey' "! grep -q '$AGENT_HEX' '$h/receipts.jsonl'"

h=$(sandbox); route_notify "$h" nobody none
rc=$(run_deliver "$h" --job x.service --route nobody --subject s --message m)
assert 'an explicit `none` mentions nobody' "! sent_args '$h' | grep -q -- '--mention'"
assert 'and is not an error' "[ -z \"\$(field '$h' error)\" ]"
assert 'the receipt records that nobody was addressed' "[ -z \"\$(field '$h' notify)\" ]"

h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'a route with no notify line mentions nobody, unchanged' \
  "! sent_args '$h' | grep -q -- '--mention'"
assert 'and delivers exactly as before' "[ \"\$(field '$h' outcome)\" = delivered ]"

# An unresolvable owner must not cost the delivery: the message still reaches the channel
# where Dave can read it, and the receipt carries the fault. Which agent owns which route
# is repo state, so tests/test_buzz_unit_wiring.sh is what actually prevents this.
h=$(sandbox); route_notify "$h" ghosted nosuchagent
rc=$(run_deliver "$h" --job x.service --route ghosted --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'an unknown slug is a config_error' "[ \"\$(field '$h' error)\" = config_error ]"
assert 'but the message still reaches the channel' "[ \"\$(field '$h' buzz_result)\" = ok ]"
assert 'unmentioned rather than mis-addressed' "! sent_args '$h' | grep -q -- '--mention'"

h=$(sandbox); route_notify "$h" orphan marcus
rc=$(AGENTS="$h/no-agents.env" run_deliver "$h" --job x.service --route orphan \
       --subject s --message m)
assert 'a missing agent table is a config_error, not a crash' \
  "[ \"\$(field '$h' error)\" = config_error ]"
assert 'and the delivery still lands' "[ \"\$(field '$h' buzz_result)\" = ok ]"

# A pubkey that is not a channel member is a fatal CliError::Usage, not a dropped tag:
# the whole send fails. It has to read as a membership problem or the next reader spends
# the evening on the transport.
h=$(sandbox); route_notify "$h" strangers marcus
rc=$(MOCK_CHANNEL_RC=1 MOCK_ERROR='mentioned pubkeys are not channel members' \
     run_deliver "$h" --job x.service --route strangers --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'a non-member mention is categorized membership_error' \
  "[ \"\$(field '$h' error)\" = membership_error ]"

echo '--- missing credential helper ---'
h=$(sandbox)
rc=$(HELPER="$h/nope.sh" run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'missing helper is a config_error' "[ \"\$(field '$h' error)\" = config_error ]"
assert 'discord still attempted' "[ \"\$(field '$h' discord_result)\" = ok ]"

echo '--- artifact anchoring: run marker ---'
h=$(sandbox)
touch -d '2026-01-01 00:00:00' "$h/marker"
printf 'fresh\n' > "$h/artifacts/report.md"
rc=$(run_deliver "$h" --job x.service --route ops --subject s \
       --file "$h/artifacts/report.md" --run-marker "$h/marker")
assert 'artifact newer than the marker is delivered' "[ \"\$(field '$h' outcome)\" = delivered ]"
assert 'receipt records the run_marker anchor' "[ \"\$(field '$h' anchor)\" = run_marker ]"

h=$(sandbox)
printf 'stale\n' > "$h/artifacts/report.md"
touch -d '2026-01-01 00:00:00' "$h/artifacts/report.md"
touch "$h/marker"
rc=$(run_deliver "$h" --job x.service --route ops --subject s \
       --file "$h/artifacts/report.md" --run-marker "$h/marker")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'artifact older than the marker is rejected' "[ \"\$(field '$h' error)\" = artifact_error ]"
assert 'nothing is sent for a stale artifact' "[ \"\$(ncalls '$h')\" -eq 0 ]"
assert 'discord is NOT given a stale artifact either' "[ ! -f '$h/mock/hermes.log' ]"
assert 'outcome skipped' "[ \"\$(field '$h' outcome)\" = skipped ]"

h=$(sandbox)
printf 'fresh\n' > "$h/artifacts/report.md"
rc=$(run_deliver "$h" --job x.service --route ops --subject s \
       --file "$h/artifacts/report.md" --run-marker "$h/absent-marker")
assert 'a missing run marker fails closed, it does not fall back to an age window' \
  "[ \"\$(field '$h' error)\" = artifact_error ]"
assert 'nothing sent when the marker is missing' "[ \"\$(ncalls '$h')\" -eq 0 ]"

echo '--- artifact anchoring: age budget + missing file ---'
h=$(sandbox)
printf 'old\n' > "$h/artifacts/report.md"
touch -d '2026-01-01 00:00:00' "$h/artifacts/report.md"
rc=$(run_deliver "$h" --job x.service --route ops --subject s \
       --file "$h/artifacts/report.md" --max-age-secs 3600)
assert 'artifact past the age budget is rejected' "[ \"\$(field '$h' error)\" = artifact_error ]"
assert 'receipt records the weaker age_budget anchor' "[ \"\$(field '$h' anchor)\" = age_budget ]"

h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route ops --subject s --file "$h/artifacts/gone.md")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'missing artifact is an artifact_error' "[ \"\$(field '$h' error)\" = artifact_error ]"
assert 'nothing sent for a missing artifact' "[ \"\$(ncalls '$h')\" -eq 0 ]"

echo '--- Buzz failure categories stay fail-soft and distinguishable ---'
for c in "3|auth|auth_error" "2|relay|network_error" "4|other|transport_error" \
         "1|not a member|membership_error" "5|conflict|transport_error"; do
  IFS='|' read -r code err want <<<"$c"
  h=$(sandbox)
  rc=$(MOCK_CHANNEL_RC="$code" MOCK_ERROR="$err" \
       run_deliver "$h" --job x.service --route ops --subject s --message m)
  assert "buzz exit $code exits 0 (fail-soft)" "[ '$rc' = 0 ]"
  assert "buzz exit $code categorized $want" "[ \"\$(field '$h' error)\" = '$want' ]"
  assert "buzz exit $code still wrote a receipt" "[ \"\$(nreceipts '$h')\" -eq 1 ]"
  assert "buzz exit $code did not publish a note" "[ \"\$(field '$h' pulse_attempted)\" = False ]"
done

echo '--- Discord failure is independent of Buzz success ---'
h=$(sandbox)
rc=$(MOCK_HERMES_RC=1 run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'discord failure categorized' "[ \"\$(field '$h' error)\" = discord_error ]"
assert 'buzz still delivered' "[ \"\$(field '$h' buzz_result)\" = ok ]"
assert 'outcome partial_success' "[ \"\$(field '$h' outcome)\" = partial_success ]"

echo '--- no hermes entrypoint at all ---'
h=$(sandbox)
rc=$(HERMES="$h/no-hermes" run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'buzz still delivered' "[ \"\$(field '$h' buzz_result)\" = ok ]"
assert 'no PATH fallback to a bare hermes' "[ ! -e '$h/mock/PATH_LEAK' ]"

echo '--- DELIVER_DISCORD=0 stops attempting Discord (Phase 4 cutover) ---'
h=$(sandbox)
rc=$(DELIVER_DISCORD=0 run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'discord not attempted' "[ \"\$(field '$h' discord_attempted)\" = False ]"
assert 'buzz delivered' "[ \"\$(field '$h' outcome)\" = delivered ]"
assert 'hermes never invoked' "[ ! -f '$h/mock/hermes.log' ]"

echo '--- channel ok + pulse failure => partial_success ---'
h=$(sandbox)
rc=$(MOCK_SOCIAL_RC=2 MOCK_ERROR=relay \
     run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'outcome partial_success' "[ \"\$(field '$h' outcome)\" = partial_success ]"
assert 'channel event id still captured' "[ \"\$(field '$h' buzz_event_id)\" = '$CH_ID' ]"
assert 'pulse failure categorized' "[ \"\$(field '$h' error)\" = network_error ]"
assert 'no pulse event id' "[ -z \"\$(field '$h' pulse_event_id)\" ]"

echo '--- the note is byte-bounded, UTF-8 safe, and never loses the pointer ---'
h=$(sandbox)
long=$(python3 -c 'print("héllo wörld — ünicode padding. " * 200)')
rc=$(BUZZ_NOTE_MAX_BYTES=300 BUZZ_POINTER_TEMPLATE='buzz://c/{channel}/e/{event}' \
     run_deliver "$h" --job x.service --route ops --runtime claude-opus-5 \
       --subject "$long" --message m --note "$long")
note="$h/mock/content.social"
assert 'a note was published' "[ -f '$note' ]"
assert 'note is within the byte budget' "[ \"\$(wc -c < '$note')\" -le 300 ]"
assert 'note is valid UTF-8 after truncation' \
  "python3 -c \"open('$note','rb').read().decode('utf-8')\""
assert 'attribution survives truncation' "grep -q 'job: x.service' '$note'"
assert 'runtime attribution survives truncation' "grep -q 'runtime: claude-opus-5' '$note'"
assert 'the exact channel pointer is never truncated' \
  "grep -qF 'buzz://c/$CH_ID/e/$CH_ID' '$note'"

echo '--- a short note is not padded or mangled ---'
h=$(sandbox)
rc=$(run_deliver "$h" --job y.service --route ops --runtime local \
       --subject 'Headline here' --message m --note $'one\ntwo')
assert 'headline present' "grep -q 'Headline here' '$h/mock/content.social'"
assert 'digest lines present' "grep -q '^one$' '$h/mock/content.social' && grep -q '^two$' '$h/mock/content.social'"

echo '--- credential boundary: a key in deliver.sh env reaches neither argv nor the helper env ---'
h=$(sandbox)
rc=$(BUZZ_PRIVATE_KEY="$FAKE_NSEC" BUZZ_AUTH_TAG='["auth","x","","y"]' \
     run_deliver "$h" --job x.service --route ops --subject s --message m)
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'helper argv carries no private key' "! grep -q 'nsec1' '$h/mock/argv.log'"
assert 'deliver.sh strips BUZZ_PRIVATE_KEY from the helper environment' \
  "! grep -q '^BUZZ_PRIVATE_KEY=' '$h/mock/env.log'"
assert 'deliver.sh strips BUZZ_AUTH_TAG from the helper environment' \
  "! grep -q '^BUZZ_AUTH_TAG=' '$h/mock/env.log'"

echo '--- redaction: key-shaped text never lands in a receipt or the delivery log ---'
h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route ops --subject "s $FAKE_NSEC" --message m)
assert 'subject is recorded for audit' "[ -n \"\$(field '$h' subject)\" ]"
assert 'receipts redact anything nsec-shaped' "! grep -q 'nsec1qqqq' '$h/receipts.jsonl'"
assert 'the delivery log redacts too' "! grep -q 'nsec1qqqq' '$h/deliver.log'"

echo '--- argument validation is fail-soft, not fatal ---'
h=$(sandbox)
rc=$(run_deliver "$h" --route ops --subject s --message m)
assert 'missing --job exits 0' "[ '$rc' = 0 ]"
assert 'missing --job is a config_error receipt' "[ \"\$(field '$h' error)\" = config_error ]"
h=$(sandbox)
rc=$(run_deliver "$h" --job x.service --route ops --subject s)
assert 'no payload at all exits 0' "[ '$rc' = 0 ]"
assert 'no payload is a config_error receipt' "[ \"\$(field '$h' error)\" = config_error ]"

echo '--- Pulse day-root threading ---'
# Pulse has no time-based grouping: only a reply nests under a root. A night of
# deliveries must therefore share one root, published on the first delivery of the day.
h=$(sandbox)
today=$(date +%F)
run_deliver "$h" --job a.service --route ops --subject s1 --message m >/dev/null
assert 'day-root published on the first delivery' \
  "grep -q 'social publish --content Praetorium — $today' '$h/mock/argv.log'"
assert 'the note replies to the root' "grep -q -- '--reply-to $NOTE_ID' '$h/mock/argv.log'"
assert 'root id persisted with its date' "[ \"\$(cat '$h/var/buzz-pulse-root')\" = \"\$(printf '%s\t%s' '$today' '$NOTE_ID')\" ]"

run_deliver "$h" --job b.service --route ops --subject s2 --message m >/dev/null
assert 'second delivery reuses the root instead of publishing a new one' \
  "[ \"\$(grep -c 'social publish --content Praetorium' '$h/mock/argv.log')\" -eq 1 ]"
assert 'second delivery adds only channel + pulse calls' "[ \"\$(ncalls '$h')\" -eq 5 ]"
assert 'second note also replies to the root' \
  "[ \"\$(grep -c -- '--reply-to $NOTE_ID' '$h/mock/argv.log')\" -eq 2 ]"

h=$(sandbox)
mkdir -p "$h/var"
printf '2000-01-01\t%s\n' "$NOTE_ID" > "$h/var/buzz-pulse-root"
run_deliver "$h" --job c.service --route ops --subject s --message m >/dev/null
assert 'a stale root date is replaced, not reused' \
  "grep -q 'social publish --content Praetorium — $today' '$h/mock/argv.log'"
assert 'the stale date is overwritten' "grep -q \"^$today\" '$h/var/buzz-pulse-root'"

# Threading is an enhancement, never a reason to lose a delivery.
h=$(sandbox)
cat > "$h/helper-noid.sh" <<'SH'
#!/usr/bin/env bash
mkdir -p "$MOCK_DIR"
printf '%s\n' "$(printf '%s' "$*" | tr '\n' ' ')" >> "$MOCK_DIR/argv.log"
case "$2" in
  messages) printf '{"accepted":true,"event_id":"%s"}\n' "$MOCK_CHANNEL_ID" ;;
  *)        printf '{}\n' ;;
esac
SH
chmod +x "$h/helper-noid.sh"
rc=$(HELPER="$h/helper-noid.sh" run_deliver "$h" --job d.service --route ops \
       --subject s --message m)
assert 'an unusable root still exits 0' "[ '$rc' = 0 ]"
assert 'no root file written when the root id came back empty' "[ ! -f '$h/var/buzz-pulse-root' ]"
assert 'the note is published standalone, without --reply-to' \
  "! grep -q -- '--reply-to' '$h/mock/argv.log'"

echo '--- {placeholder} templates survive shell defaulting ---'
# bash ends ${VAR:-default} at the first unescaped `}`, so a literal {date} or {channel}
# in a default value loses its closing brace and appends a stray `}` to the result — and
# it does so even when the variable IS set, corrupting a caller-supplied template too.
# Substring greps miss this entirely because the stray brace lands at the end.
h=$(sandbox)
run_deliver "$h" --job p.service --route ops --subject s --message m --note n >/dev/null
assert 'the default day-root is exactly the template with the date substituted' \
  "grep -qE 'social publish --content Praetorium — ${today}\$' '$h/mock/argv.log'"
assert 'the default pointer resolves both placeholders' \
  "grep -qF 'buzz://message?channel=$CH_ID&id=$CH_ID' '$h/mock/content.social'"
assert 'no unsubstituted placeholder survives into the note' \
  "! grep -q '[{}]' '$h/mock/content.social'"

h=$(sandbox)
rc=$(BUZZ_PULSE_ROOT_TEMPLATE='Root {date}' BUZZ_POINTER_TEMPLATE='p/{channel}/{event}' \
     run_deliver "$h" --job p.service --route ops --subject s --message m --note n)
assert 'an overridden day-root template is not corrupted' \
  "grep -qE 'social publish --content Root ${today}\$' '$h/mock/argv.log'"
assert 'an overridden pointer template is not corrupted' \
  "grep -qF 'p/$CH_ID/$CH_ID' '$h/mock/content.social'"
assert 'an overridden template leaves no stray brace' \
  "! grep -q '[{}]' '$h/mock/content.social'"

echo '--- receipt shape ---'
h=$(sandbox)
rc=$(run_deliver "$h" --job z.service --route ops --subject s --message m --runtime rt)
for k in schema ts job route channel payload_type discord_attempted discord_result \
         buzz_attempted buzz_result buzz_event_id pulse_attempted pulse_result outcome runtime; do
  assert "receipt carries $k" "[ \"\$(field '$h' $k)\" != '<no-receipt>' ]"
done
assert 'receipt is one JSON object per line' \
  "python3 -c \"import json;[json.loads(l) for l in open('$h/receipts.jsonl') if l.strip()]\""
assert 'receipt never carries a private key field' "! grep -qi 'private_key' '$h/receipts.jsonl'"

exit $fail
