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
assert 'every row has six tab-separated columns' \
  "[ \"\$(rows | awk -F'\t' 'NF!=6' | wc -l)\" -eq 0 ]"
assert 'no duplicate units' \
  "[ \"\$(rows | cut -f1 | sort | uniq -d | wc -l)\" -eq 0 ]"

echo '--- every declared route resolves to a key in the route table ---'
while IFS=$'\t' read -r unit route payload status silence canvas; do
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
  case "$canvas" in
    none|mirror|only) ;;
    *) assert "canvas mode '$canvas' for $unit is known" "false" ;;
  esac
done < <(rows)

echo '--- at most one producer per route writes that route canvas ---'
# `buzz canvas set` is a blind replace: no base hash, no conflict, no history. Two
# writers on one route do not merge, they alternate, and the loser's document is gone
# with nothing in either receipt to say so — both report canvas_result=ok.
doubled=$(rows | awk -F'\t' '$6!="none" {print $2}' | sort | uniq -d)
assert 'no route has two canvas writers' "[ -z '$doubled' ]"
[ -n "$doubled" ] && echo "      doubled routes: $doubled"

echo '--- the route table carries routes only, never credentials or identities ---'
assert 'route table has no npub/nsec/pubkey material' \
  "! grep -qE 'nsec1|npub1|PRIVATE_KEY|AUTH_TAG' '$ROUTES'"
assert 'every non-comment line is a ROUTE_ assignment' \
  "[ \"\$(grep -v '^#' '$ROUTES' | grep -v '^[[:space:]]*\$' | grep -cv '^ROUTE_[a-z][a-z0-9_-]*=')\" -eq 0 ]"

echo '--- every route declares an event kind deliver.sh will accept ---'
# A kind deliver.sh rejects is a config_error receipt on every run of every producer on
# that route — the route goes quiet while each unit still exits 0. Catch it here, where
# the table is edited, not on the next scheduled fire.
kind_lines() { grep '^ROUTE_[a-z][a-z0-9_-]*_kind=' "$ROUTES"; }
while IFS= read -r line; do
  [ -n "$line" ] || continue
  key=${line%%=*}; key=${key#ROUTE_}; key=${key%_kind}
  assert "kind for '$key' names a route that exists" "grep -q '^ROUTE_${key}=' '$ROUTES'"
  case "${line#*=}" in
    9|45001) assert "kind for '$key' is a value deliver.sh sends" "true" ;;
    *) assert "kind for '$key' is 9 or 45001, not '${line#*=}'" "false" ;;
  esac
done < <(kind_lines)

while IFS= read -r route; do
  assert "route '$route' states its kind rather than defaulting" \
    "grep -q '^ROUTE_${route}_kind=' '$ROUTES'"
done < <(rows | cut -f2 | sort -u)

echo '--- wired units carry their route and a delivery hook ---'
while IFS=$'\t' read -r unit route payload status silence canvas; do
  f="$REPO_ROOT/systemd/$unit"
  assert "$unit has a unit source in this repo" "[ -f '$f' ]"
  [ -f "$f" ] || continue

  has_route=$(code "$f" | grep -c "^Environment=DELIVERY_ROUTE=$route\$" || true)
  has_hook=$(code "$f" | grep -cE '/bin/(deliver[a-z_]*|notify|inbox_backlog_alert)\.sh' || true)

  if [ "$status" = wired ]; then
    assert "$unit declares DELIVERY_ROUTE=$route" "[ '$has_route' -ge 1 ]"
    assert "$unit invokes a delivery adapter" "[ '$has_hook' -ge 1 ]"
    assert "$unit passes its own name as the job" \
      "code '$f' | grep -q '^Environment=DELIVERY_JOB=%n\$'"
    # A hook without its exec bit is 203/EXEC: the run itself succeeded, the report
    # never left the box, and nothing in the receipt trail records the attempt.
    for hook in $(code "$f" | grep -E '^ExecSt(art|op)Post=' | sed 's/^[^=]*=//' | awk '{print $1}'); do
      assert "$unit's hook ${hook##*/} is executable in this repo" \
        "[ -x '$REPO_ROOT/bin/${hook##*/}' ]"
    done
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

echo '--- wired artifact-lookup units anchor to THIS run ---'
# `file` and `status` both answer "did this run produce something?" by looking up a
# dated artifact in a directory shared with every other producer. A 26-hour age budget
# cannot tell "produced by tonight's run" from "left over from last night's", and the
# newest glob hit belongs to another job on any night this one wrote nothing. The
# marker is stamped by ExecStartPre before ExecStart writes anything, so the lookup
# can require newer-than-marker exactly.
#
# `summary` is exempt by construction: it is composed from current state at delivery
# time, so there is no prior run's artifact to be confused with. Where a summary
# adapter does read run-scoped state, that is the adapter's contract and is pinned in
# tests/test_buzz_adapters.sh, not here.
while IFS=$'\t' read -r unit route payload status silence canvas; do
  [ "$status" = wired ] || continue
  case "$payload" in file|status) ;; *) continue ;; esac
  f="$REPO_ROOT/systemd/$unit"
  [ -f "$f" ] || continue
  assert "$unit declares DELIVERY_RUN_MARKER" \
    "code '$f' | grep -q '^Environment=DELIVERY_RUN_MARKER=/home/dave/logs/run-markers/%n\$'"
  assert "$unit creates the marker directory before ExecStart" \
    "code '$f' | grep -q '^ExecStartPre=/usr/bin/mkdir -p /home/dave/logs/run-markers\$'"
  assert "$unit stamps its marker before ExecStart" \
    "code '$f' | grep -q '^ExecStartPre=/usr/bin/touch /home/dave/logs/run-markers/%n\$'"

  # Whichever way the artifact is named, it must be named HERE. Inheriting an
  # adapter default means delivering whatever that default happens to point at.
  case "$payload" in
    file)
      assert "$unit names its own artifact directory explicitly" \
        "code '$f' | grep -q '^Environment=REPORT_DIR='"
      assert "$unit names its own artifact glob explicitly" \
        "code '$f' | grep -q '^Environment=REPORT_GLOB='"
      ;;
    status)
      assert "$unit names the agent_propose.sh task whose proposal it reports" \
        "code '$f' | grep -q '^Environment=DELIVERY_TASK=[a-z0-9-]\\+\$'"
      ;;
  esac
done < <(rows)

echo '--- the manifest canvas column matches what the adapter actually passes ---'
# The manifest is what the one-writer-per-route rule is enforced against, so a row that
# says `none` while its adapter passes `--canvas mirror` makes that rule decorative.
while IFS=$'\t' read -r unit route payload status silence canvas; do
  [ "$status" = wired ] || continue
  f="$REPO_ROOT/systemd/$unit"
  [ -f "$f" ] || continue
  declared=none
  for hook in $(code "$f" | grep -E '^ExecSt(art|op)Post=' | sed 's/^[^=]*=//' | awk '{print $1}'); do
    s="$REPO_ROOT/bin/${hook##*/}"
    [ -f "$s" ] || continue
    mode=$(grep -v '^[[:space:]]*#' "$s" | sed -n 's/.*--canvas \([a-z][a-z]*\).*/\1/p' | tail -1)
    [ -n "$mode" ] && declared="$mode"
  done
  assert "$unit's adapter passes canvas '$canvas' as the manifest declares" \
    "[ '$declared' = '$canvas' ]"
done < <(rows)

echo '--- every wired unit states where its receipt runtime comes from ---'
# The receipt's `runtime` answers "which profile produced this". A unit either runs no
# model (DELIVERY_RUNTIME=none) or names the agent_propose.sh task whose cost.log record
# the adapter reads it back from. Declaring neither is how the field silently read
# `unknown` on every hook-fired receipt, while the one unit with an EnvironmentFile
# inherited a box-wide AGENT_PROFILE and named a persona that had not run.
while IFS=$'\t' read -r unit route payload status silence canvas; do
  [ "$status" = wired ] || continue
  f="$REPO_ROOT/systemd/$unit"
  [ -f "$f" ] || continue
  assert "$unit declares DELIVERY_RUNTIME=none or a DELIVERY_TASK to resolve it from" \
    "code '$f' | grep -qE '^Environment=(DELIVERY_RUNTIME=none|DELIVERY_TASK=[a-z0-9-]+)\$'"
  # A profile pinned in a unit is a claim about a model choice made elsewhere: the
  # 2026-07-30 migration re-pointed seven jobs at headless Claude Code and any such
  # pin would still be naming the persona they left behind.
  assert "$unit pins no profile name in DELIVERY_RUNTIME" \
    "! code '$f' | grep -E '^Environment=DELIVERY_RUNTIME=' | grep -qv '=none\$'"
done < <(rows)

echo '--- exactly one script may invoke a transport ---'
offenders=$(
  for f in "$REPO_ROOT"/bin/* "$REPO_ROOT"/systemd/*; do
    [ -f "$f" ] || continue
    case "$f" in */deliver.sh) continue ;; esac
    if grep -v '^[[:space:]]*#' "$f" \
         | grep -qE 'hermes(_cli\.main)? send|buzz messages send|buzz social publish|buzz canvas set'; then
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
