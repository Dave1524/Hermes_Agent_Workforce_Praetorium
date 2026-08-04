#!/usr/bin/env bash
# Wiring gate for the Buzz surface migration.
#
# bin/buzz_producers.tsv is the manifest: which unit delivers to which route, with
# what payload, and whether it has been ported yet. This suite proves the repo agrees
# with it in both directions — a unit marked `wired` really is, and a unit marked
# `pending` carries no half-finished wiring that would deliver somewhere unintended.
#
# It also holds the two containment invariants the migration must not lose:
#   * exactly one script may invoke a transport, so "did it actually send?" has one
#     answer and one receipt;
#   * no unit file may carry Buzz signing material, because service-level environment
#     is inherited by ExecStart — which is the LLM runner.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
MANIFEST="$REPO_ROOT/bin/buzz_producers.tsv"
ROUTES="$REPO_ROOT/bin/buzz_routes.env"

fail=0
assert() { local d=$1 c=$2; if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi; }

rows() { grep -v '^#' "$MANIFEST" | grep -v '^[[:space:]]*$'; }

# Unit files are configuration, not prose: a rule about what a unit *does* must not be
# satisfied or broken by a comment describing what it used to do.
code() { grep -v '^[[:space:]]*#' "$1"; }

echo '--- the manifest itself is well-formed ---'
assert 'manifest exists' "[ -f '$MANIFEST' ]"
assert 'route table exists' "[ -f '$ROUTES' ]"
assert 'every row has five tab-separated columns' \
  "[ \"\$(rows | awk -F'\t' 'NF!=5' | wc -l)\" -eq 0 ]"
assert 'no duplicate units' \
  "[ \"\$(rows | cut -f1 | sort | uniq -d | wc -l)\" -eq 0 ]"

echo '--- every declared route resolves to a key in the route table ---'
while IFS=$'\t' read -r unit route payload status silence; do
  assert "route '$route' is declared for $unit" "grep -q '^ROUTE_${route}=' '$ROUTES'"
  case "$payload" in
    file|status|summary) ;;
    *) assert "payload '$payload' for $unit is a known kind" "false" ;;
  esac
  case "$status" in
    wired|pending) ;;
    *) assert "status '$status' for $unit is known" "false" ;;
  esac
  case "$silence" in
    never|allowed) ;;
    *) assert "silence policy '$silence' for $unit is known" "false" ;;
  esac
done < <(rows)

echo '--- the route table carries routes only, never credentials or identities ---'
assert 'route table has no npub/nsec/pubkey material' \
  "! grep -qE 'nsec1|npub1|PRIVATE_KEY|AUTH_TAG' '$ROUTES'"
assert 'every non-comment line is a ROUTE_ assignment' \
  "[ \"\$(grep -v '^#' '$ROUTES' | grep -v '^[[:space:]]*\$' | grep -cv '^ROUTE_[a-z][a-z0-9_-]*=')\" -eq 0 ]"

echo '--- wired units carry their route and a delivery hook ---'
while IFS=$'\t' read -r unit route payload status silence; do
  f="$REPO_ROOT/systemd/$unit"
  assert "$unit has a unit source in this repo" "[ -f '$f' ]"
  [ -f "$f" ] || continue

  has_route=$(code "$f" | grep -c "^Environment=DELIVERY_ROUTE=$route\$" || true)
  has_hook=$(code "$f" | grep -cE 'deliver_report\.sh|notify\.sh|inbox_backlog_alert\.sh|deliver\.sh' || true)

  if [ "$status" = wired ]; then
    assert "$unit declares DELIVERY_ROUTE=$route" "[ '$has_route' -ge 1 ]"
    assert "$unit invokes a delivery adapter" "[ '$has_hook' -ge 1 ]"
    assert "$unit passes its own name as the job" \
      "code '$f' | grep -q '^Environment=DELIVERY_JOB=%n\$'"
  else
    # A pending unit may keep its pre-migration Discord hook — that path IS the
    # dual-run baseline, and the adapters route it to `unrouted`, which delivers
    # to Discord exactly as before and files a config_error receipt. What it must
    # not do is claim a route it has not been ported to: that half-state posts to
    # a channel nobody has agreed owns it, and reads as a completed migration.
    assert "$unit (pending) claims no route yet" "[ '$has_route' -eq 0 ]"
    assert "$unit (pending) claims no run marker yet" \
      "! code '$f' | grep -q '^Environment=DELIVERY_RUN_MARKER='"
  fi
done < <(rows)

echo '--- wired file-payload units anchor their artifact to THIS run ---'
# A 26-hour age budget cannot tell "produced by tonight's run" from "left over from
# last night's". The marker is stamped by ExecStartPre before ExecStart writes
# anything, so deliver.sh can require artifact-newer-than-marker exactly.
while IFS=$'\t' read -r unit route payload status silence; do
  [ "$status" = wired ] && [ "$payload" = file ] || continue
  f="$REPO_ROOT/systemd/$unit"
  [ -f "$f" ] || continue
  assert "$unit declares DELIVERY_RUN_MARKER" \
    "code '$f' | grep -q '^Environment=DELIVERY_RUN_MARKER=/home/dave/logs/run-markers/%n\$'"
  assert "$unit creates the marker directory before ExecStart" \
    "code '$f' | grep -q '^ExecStartPre=/usr/bin/mkdir -p /home/dave/logs/run-markers\$'"
  assert "$unit stamps its marker before ExecStart" \
    "code '$f' | grep -q '^ExecStartPre=/usr/bin/touch /home/dave/logs/run-markers/%n\$'"
  assert "$unit names its own artifact directory explicitly" \
    "code '$f' | grep -q '^Environment=REPORT_DIR='"
  assert "$unit names its own artifact glob explicitly" \
    "code '$f' | grep -q '^Environment=REPORT_GLOB='"
done < <(rows)

echo '--- exactly one script may invoke a transport ---'
offenders=$(
  for f in "$REPO_ROOT"/bin/* "$REPO_ROOT"/systemd/*; do
    [ -f "$f" ] || continue
    case "$f" in */deliver.sh) continue ;; esac
    if grep -v '^[[:space:]]*#' "$f" \
         | grep -qE 'hermes(_cli\.main)? send|buzz messages send|buzz social publish'; then
      basename "$f"
    fi
  done
)
assert 'no script or unit outside bin/deliver.sh invokes a transport' "[ -z '$offenders' ]"
[ -n "$offenders" ] && echo "      offenders: $offenders"

echo '--- no unit file may hold Buzz signing material ---'
# Service-level environment is inherited by ExecStart, i.e. by the LLM runner. A key
# reachable from the agent process is a key the agent can be talked into using.
for f in "$REPO_ROOT"/systemd/*.service; do
  u=$(basename "$f")
  assert "$u carries no Buzz key or auth tag" \
    "! grep -qE 'BUZZ_PRIVATE_KEY|BUZZ_AUTH_TAG|nsec1' '$f'"
  assert "$u sources no buzz-agents environment file" \
    "! grep -qE '^EnvironmentFile=.*buzz-agents' '$f'"
done

echo '--- deliver.sh keeps the credential boundary at the helper ---'
assert 'deliver.sh never reads a private key from its own environment' \
  "! grep -vE '^[[:space:]]*#' '$REPO_ROOT/bin/deliver.sh' | grep -qE '\\\$\\{?BUZZ_PRIVATE_KEY|\\\$\\{?BUZZ_AUTH_TAG'"
assert 'deliver.sh strips key material from the helper environment' \
  "grep -q 'env -u BUZZ_PRIVATE_KEY -u BUZZ_AUTH_TAG' '$REPO_ROOT/bin/deliver.sh'"

exit $fail
