#!/usr/bin/env bash
# S1 — the Buzz interactive harness. Every DM, every channel message, every forum thread.
#
# Phase B built a harness for the SCHEDULED surface and only for it. All 26 [[workflows]]
# entries were platform, scheduled or buzz_dispatch, so the coverage checker, the status
# vocabulary and the suite requirement were structurally blind to S1: nothing was failing
# and nothing was looking. This suite is the looking.
#
# WHAT IT ASSERTS, AND WHY EACH ONE IS A MECHANISM RATHER THAN A STYLE RULE:
#
#   * The DAG.  buzz-team/<name>.toml is the loop guardrail. Five hand-maintained files
#     whose agreement with design/agents/*.toml was stated in prose and checked by nothing
#     in this repo. A worker admitting another worker is the edge that turns a fan-out into
#     a cascade, and it is one line in one file.
#
#   * require_mention on EVERY rule.  Config mode MERGES the flag across every rule that
#     applies to a channel, so a single `false` sets require_mention = false for that
#     channel's whole subscription, for every author (buzz-acp config.rs:1499-1500, and
#     again at :1408-1409). One relaxed rule in one file widens a channel for everyone —
#     including DMs, which are not a separate path and have no exemption from it.
#
#   * No key material.  This repo is PUBLIC and agent-workforce-auto-sync.timer pushes any
#     dirty tree within 15 minutes. The 64-hex strings in the tree are PUBKEYS — public by
#     construction, already in bin/buzz_agents.env — so the assertion permits exactly the
#     six declared ones and rejects every other 64-hex string rather than waving at the
#     shape.
#
# IT IS NOT BOX-GATED, DELIBERATELY. buzz-team/ is in the checkout now, so a hosted runner
# can assert the DAG, the rules and the key material with no box at all. Only the two
# groups that compare against ~/.config/buzz-team/ build synthetic trees to do it, which
# needs no box either. Box-gating the whole file would hand CI a suite that skips whole and
# asserts nothing — which is the failure this suite exists to notice one level up.
#
# CRITERION 14's OTHER HALF: aurelian's absence from bin/buzz_agents.env is asserted by
# tests/test_fleet_guards.sh::aurelian-unaddressable, which owns that id. The route-table
# half is here rather than duplicated there, because bin/buzz_routes.env is in-repo and can
# be read off the box while that suite is box-gated. Read the two together.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TREE="$REPO_ROOT/buzz-team"
MANIFEST="$TREE/MANIFEST.toml"
AGENTS="$REPO_ROOT/design/agents"
AGENT_TABLE="$REPO_ROOT/bin/buzz_agents.env"
ROUTES="$REPO_ROOT/bin/buzz_routes.env"
CHECK="$REPO_ROOT/bin/check_deploy_drift.sh"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one. Scoped off here
# rather than per-condition so a later `| grep -q` cannot reintroduce it.
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

if ! python3 -c 'import tomllib' 2>/dev/null; then
  echo "SKIP: tomllib unavailable (needs Python 3.11+)"
  exit 77
fi

PERSONAS=(marcus claudius augustus trajan aurelian)
WORKERS=(claudius augustus trajan)

echo '--- the adopted tree is present, declared, and parses ---'
assert 'buzz-team/ exists in this checkout' "[ -d '$TREE' ]"
assert 'it carries a MANIFEST.toml' "[ -f '$MANIFEST' ]"
assert 'every persona has a rule file' \
  "[ \"\$(ls '$TREE'/{marcus,claudius,augustus,trajan,aurelian}.toml 2>/dev/null | wc -l)\" -eq 5 ]"

# Both directions. A file on disk that the manifest does not declare is undeclared config in
# a public repo; a declared file that is not on disk is a converge that would silently ship
# less than it says. The drift check enforces the same pair against the box.
manifest_problems=$(MANIFEST="$MANIFEST" TREE="$TREE" python3 <<'PY'
import os, pathlib, tomllib
tree = pathlib.Path(os.environ["TREE"])
data = tomllib.loads(pathlib.Path(os.environ["MANIFEST"]).read_text())
adopted = {r["path"] for r in data.get("adopted", []) if r.get("path")}
excluded = {r["path"] for r in data.get("excluded", []) if r.get("path")}
on_disk = {p.name for p in tree.iterdir() if p.is_file() and p.name != "MANIFEST.toml"}
for name in sorted(on_disk - adopted):
    print(f"{name}: on disk in buzz-team/ and declared in no [[adopted]] entry")
for name in sorted(adopted - on_disk):
    print(f"{name}: declared [[adopted]] and not on disk")
if not adopted:
    print("MANIFEST.toml declares no [[adopted]] files — a declaration that declares nothing")
if not excluded:
    print("MANIFEST.toml declares no [[excluded]] files — an absence cannot be told from a deletion")
for row in data.get("adopted", []) + data.get("excluded", []):
    if not row.get("why"):
        print(f"{row.get('path')}: declared with no `why`")
PY
)
assert 'the manifest and the tree agree in both directions, and every entry states why' \
  "[ -z \"\$manifest_problems\" ] || { printf '      %s\n' \$manifest_problems; false; }"

# Adopted verbatim from the box, so these are NOT in bin/verify.sh's shellcheck sweep (its
# scope is bin/). Syntax is asserted here instead: a corrupt adoption is caught without a
# lint finding forcing an edit that would break byte-identity on day one.
for f in "$TREE"/*.sh; do
  assert "adopted script parses: ${f##*/}" "bash -n '$f'"
done
for f in "$TREE"/*.py; do
  assert "adopted module compiles: ${f##*/}" "python3 -m py_compile '$f'"
done
rm -rf "$TREE/__pycache__"

echo '--- no adopted file carries key material (criterion 3) ---'
# The identity table has ONE owner in this repo: buzz-team/verify-fleet.sh, which declares
# all six with a comment explaining each. Hardcoding them here would be a second copy of the
# fact — and a copy that drifts silently is how a permitted-list check stops checking.
identities=$(sed -n 's/^\([A-Z]*\)_PUBKEY=\([0-9a-f]\{64\}\)$/\1 \2/p' "$TREE/verify-fleet.sh")
assert 'verify-fleet.sh declares the six identities this box knows' \
  "[ \"\$(wc -l <<<\"\$identities\")\" -eq 6 ]"

# The four AGENT identities are cross-checked against bin/buzz_agents.env in both
# directions, so the permitted-list cannot drift from the table a scheduled delivery
# resolves. owner and praetorium have no second in-repo source and are non-agent identities
# by construction — praetorium publishes and has no runtime, Dave is not an agent — which is
# precisely why neither may appear in the slug table.
key_mismatch=$(
  a=$(awk '{print tolower($1)"="$2}' <<<"$identities" \
        | grep -Ev '^(dave|praetorium)=' | LC_ALL=C sort)
  b=$(sed -n 's/^AGENT_\([a-z]*\)=\([0-9a-f]\{64\}\)$/\1=\2/p' "$AGENT_TABLE" | LC_ALL=C sort)
  diff <(printf '%s\n' "$a") <(printf '%s\n' "$b")
)
assert 'the agent half of that table equals bin/buzz_agents.env, both directions' \
  "[ -z \"\$key_mismatch\" ]"

permitted=$(awk '{print $2}' <<<"$identities" | LC_ALL=C sort -u)
stray_hex=$(
  grep -rohE '[0-9a-f]{64}' "$TREE" --include='*' 2>/dev/null | LC_ALL=C sort -u \
    | comm -23 - <(printf '%s\n' "$permitted")
)
assert 'every 64-hex string in the tree is one of the six declared PUBKEYS' \
  "[ -z \"\$stray_hex\" ] || { printf '      unexpected: %s\n' \$stray_hex; false; }"

assert 'no bech32 private key anywhere in the tree' \
  "! grep -rq 'nsec1' '$TREE'"
assert 'no BUZZ_PRIVATE_KEY is assigned a value' \
  "! grep -rqE 'BUZZ_PRIVATE_KEY=[^\"'\\''[:space:]]' '$TREE'"
assert 'no Notion integration token' \
  "! grep -rq 'ntn_' '$TREE'"
# The VALUE after Bearer, not the word. buzz-notion-broker.py:88 builds the header as
# `"Bearer " + token`, which is the correct shape — a check that banned the literal string
# would fail the one file doing it right and teach the next author to concatenate obscurely.
assert 'no bearer token is embedded (a Bearer followed by a value, not by a quote)' \
  "! grep -rqE 'Bearer [A-Za-z0-9_-]' '$TREE'"

echo '--- the Notion token is READ at call time, never embedded ---'
assert 'buzz-notion-broker.py defines load_notion_token' \
  "grep -q 'def load_notion_token' '$TREE/buzz-notion-broker.py'"
assert 'it opens the deny-listed credential file rather than holding a token' \
  "grep -q 'open(NOTION_ENV_FILE' '$TREE/buzz-notion-broker.py'"
assert 'and that file is under ~/.config/agent-workforce/, outside this repo' \
  "grep -q 'agent-workforce/notion-buzz.env' '$TREE/buzz-notion-broker.py'"

echo '--- every rule in every file is mention-gated (criterion 12) ---'
# Not style. resolve_channel_filters merges require_mention across every rule applying to a
# channel, so ONE false relaxes that channel's whole subscription for every author. DMs are
# not exempt: buzz-acp runs one listener for both and `channels = "all"` matches a DM channel
# like any other (lib.rs:3478-3493, read at upstream 40220d5).
mention_problems=$(TREE="$TREE" python3 <<'PY'
import os, pathlib, tomllib
tree = pathlib.Path(os.environ["TREE"])
for name in ("marcus", "claudius", "augustus", "trajan", "aurelian"):
    rules = tomllib.loads((tree / f"{name}.toml").read_text()).get("rules", [])
    if not rules:
        print(f"{name}.toml: parsed 0 [[rules]] — a file that admits nobody is not a guardrail")
        continue
    for rule in rules:
        if rule.get("require_mention") is not True:
            print(f"{name}.toml: rule {rule.get('name')!r} has "
                  f"require_mention = {rule.get('require_mention')!r}, not true")
PY
)
assert 'every [[rules]] entry sets require_mention = true' \
  "[ -z \"\$mention_problems\" ] || { printf '      %s\n' \"\$mention_problems\"; false; }"

echo '--- the DAG equals design/agents/*.toml, both directions (criterion 11) ---'
# A pubkey resolving to NEITHER an agent slug NOR one of the two declared non-agent
# identities is RED. An unrecognised author in a rules file is an identity nothing in this
# repo can name, which is the one case a set comparison would otherwise pass silently by
# matching two unknowns against each other.
admits_map=$(mktemp)
trap 'rm -f "$admits_map"' EXIT
dag_problems=$(TREE="$TREE" AGENTS="$AGENTS" IDENT="$identities" ADMITS_OUT="$admits_map" python3 <<'PY'
import os, pathlib, re, tomllib

tree = pathlib.Path(os.environ["TREE"])
agents = pathlib.Path(os.environ["AGENTS"])
slug = {}
for line in os.environ["IDENT"].splitlines():
    name, key = line.split()
    slug[key] = "owner" if name.lower() == "dave" else name.lower()

AUTHOR = re.compile(r'author\s*==\s*"([0-9a-f]{64})"')
out = open(os.environ["ADMITS_OUT"], "w")
for name in ("marcus", "claudius", "augustus", "trajan", "aurelian"):
    rules = tomllib.loads((tree / f"{name}.toml").read_text()).get("rules", [])
    admits = set()
    for rule in rules:
        found = AUTHOR.findall(rule.get("filter", ""))
        if not found:
            print(f"{name}.toml: rule {rule.get('name')!r} names no author pubkey")
            continue
        for key in found:
            if key not in slug:
                print(f"{name}.toml: rule {rule.get('name')!r} admits {key[:8]}…, "
                      "which resolves to no known slug")
                continue
            admits.add(slug[key])
    declared = set(tomllib.loads((agents / f"{name}.toml").read_text())
                   .get("surfaces", {}).get("interactive", {}).get("admits", []))
    for extra in sorted(admits - declared):
        print(f"{name}: buzz-team/{name}.toml admits {extra!r}; the manifest does not declare it")
    for missing in sorted(declared - admits):
        print(f"{name}: the manifest declares admits = {missing!r}; "
              f"buzz-team/{name}.toml has no such rule")
    for who in sorted(admits):
        out.write(f"{name}\t{who}\n")
out.close()
PY
)
assert 'each rules file admits exactly what its manifest declares' \
  "[ -z \"\$dag_problems\" ] || { printf '      %s\n' \"\$dag_problems\"; false; }"

echo '--- no worker admits another worker, and the aurelian edge is ONE-WAY (criterion 13) ---'
# READS the map the DAG check above materialised. It does NOT reparse the rules files.
#
# It used to, with `grep -oE 'author == "[0-9a-f]{64}"'` — exactly one space either side of
# `==`, while the Python parser above uses `\s*`. That is a FAIL-OPEN: write `author=="<key>"`
# in a rules file and this function returns nothing, so every negative assertion below ("$a
# does not admit $b", "$a does NOT admit aurelian") passes without reading a single edge.
# Two parsers for one fact, with the weaker one guarding the safety property — the same shape
# as the pipefail trap `assert()` exists to prevent, and here the symptom is silence.
admits_of() { # persona -> newline-separated slugs
  awk -F'\t' -v p="$1" '$1==p {print $2}' "$admits_map"
}
# An empty or short map makes every negative assertion vacuous, so prove it is populated
# BEFORE relying on it. Without this, deleting the DAG block above would turn the whole
# section green.
assert 'the admits map covers all five personas (or the negatives below are vacuous)' \
  "[ \"\$(cut -f1 \"\$admits_map\" 2>/dev/null | LC_ALL=C sort -u | wc -l)\" -eq 5 ]"
for a in "${WORKERS[@]}"; do
  for b in "${WORKERS[@]}"; do
    [ "$a" = "$b" ] && continue
    assert "$a does not admit the worker $b" \
      "! admits_of '$a' | grep -qx '$b'"
  done
  # The asymmetry itself, not just the contents. A symmetric edge is what turns a fan-out
  # into a cascade; aurelian is safe ONLY because the reverse edge does not exist. Assert
  # both halves or the exception silently becomes the rule.
  assert "aurelian admits the worker $a (so $a can submit its own output for review)" \
    "admits_of aurelian | grep -qx '$a'"
  assert "$a does NOT admit aurelian — the verification edge is one-way by construction" \
    "! admits_of '$a' | grep -qx 'aurelian'"
done
assert 'marcus, the DAG root, admits nobody but owner and praetorium' \
  "[ \"\$(admits_of marcus | LC_ALL=C sort | tr '\n' ' ')\" = 'owner praetorium ' ]"

# Scoped to the RULE FILES, which the tree-wide stray-hex check above cannot say anything
# about: that one proves no unknown key is anywhere in buzz-team/, this one proves no
# unknown key is in a position that ADMITS an author. A key in a comment is inert; the same
# key inside a filter is a live subscription.
rule_authors=$(grep -hoE 'author == "[0-9a-f]{64}"' \
                 "$TREE"/{marcus,claudius,augustus,trajan,aurelian}.toml \
               | grep -oE '[0-9a-f]{64}' | LC_ALL=C sort -u)
unknown_authors=$(comm -23 <(printf '%s\n' "$rule_authors") <(printf '%s\n' "$permitted"))
assert 'every author a rule admits is owner, praetorium or a live agent' \
  "[ -n \"\$rule_authors\" ] && [ -z \"\$unknown_authors\" ]"

echo '--- aurelian is unreachable from any scheduled route (criterion 14) ---'
# The sibling half — his absence from bin/buzz_agents.env — is
# tests/test_fleet_guards.sh::aurelian-unaddressable. A route that could wake the read-only
# verifier is a route that can be made to execute by a scheduled job, so both halves matter
# and neither implies the other: deliver.sh resolves a notify SLUG in the agent table, and a
# slug named in a route with no table entry is a different failure from one with an entry.
notify_slugs_resolve() {
  local slug seen=0
  while IFS= read -r slug; do
    [ -n "$slug" ] || continue
    seen=1
    [ "$slug" = none ] && continue
    grep -q "^AGENT_${slug}=" "$AGENT_TABLE" || return 1
  done < <(sed -n 's/^ROUTE_[a-z0-9_-]*_notify=\(.*\)$/\1/p' "$ROUTES")
  # A table that matched no notify line would pass this vacuously, which is the shape of a
  # check that has quietly stopped checking.
  [ "$seen" -eq 1 ]
}
assert 'the route table exists' "[ -f '$ROUTES' ]"
assert 'no ROUTE_*_notify names aurelian' \
  "! sed -n 's/^ROUTE_[a-z0-9_-]*_notify=//p' '$ROUTES' | grep -qi aurelian"
assert 'every notify slug resolves in bin/buzz_agents.env, or is the literal none' \
  "notify_slugs_resolve"

echo '--- the kind checker bin/verify.sh runs is itself checked ---'
# buzz-team/check-team-kinds.py is the mechanism behind the kind obligation: a channel sent
# the wrong event kind is accepted by the relay, receipted `ok`, and rendered to nobody, so
# TEAM.md falling behind buzz_routes.env is invisible at runtime. bin/verify.sh calls it and
# nothing called the caller until 2026-09-03.
#
# The fixture is synthetic on purpose. Pointing it at the live TEAM.md would assert box state
# rather than the code, and TEAM.md is declared excluded — this repo does not own it.
KINDS="$REPO_ROOT/buzz-team/check-team-kinds.py"
kroot=$(mktemp -d)
cat > "$kroot/routes.env" <<'ROUTES'
ROUTE_ops=9abcdef0-1234-5678-9abc-def012345678
ROUTE_forum=11111111-2222-3333-4444-555555555555
ROUTE_forum_kind=45001
ROUTES
kinds_table() { cat > "$kroot/TEAM.md"; }
kinds_run() { python3 "$KINDS" "$kroot/routes.env" "$kroot/TEAM.md" 2>&1; }

kinds_table <<'MD'
| channel | uuid | kind |
| --- | --- | --- |
| ops | 9abcdef0-1234-5678-9abc-def012345678 | 9 — no `--kind` |
| forum | 11111111-2222-3333-4444-555555555555 | `--kind 45001` |
MD
assert 'a table that agrees with the route file passes' "kinds_run >/dev/null"

kinds_table <<'MD'
| channel | uuid | kind |
| --- | --- | --- |
| ops | 9abcdef0-1234-5678-9abc-def012345678 | 9 — no `--kind` |
| forum | 11111111-2222-3333-4444-555555555555 | 9 — no `--kind` |
MD
assert 'a documented kind that disagrees with the route file is red' \
  "! kinds_run >/dev/null && kinds_run | grep -q '45001 in buzz_routes.env, 9 in TEAM.md'"

# THE FAIL-OPEN, fixed 2026-09-03. The kind was scanned right-to-left across every cell, and
# a UUID is 32 hex digits — so a row that names no kind fell through to the UUID cell and
# "documented" the digit run that starts it. For any UUID beginning 9 followed by a hex
# letter that is exactly 9, the stream default, and the row passed as agreeing. The `else
# None` branch was unreachable for the same reason, which is what hid it: the code looked
# like it handled the case it could never enter.
kinds_table <<'MD'
| channel | uuid | kind |
| --- | --- | --- |
| ops | 9abcdef0-1234-5678-9abc-def012345678 |
| forum | 11111111-2222-3333-4444-555555555555 | `--kind 45001` |
MD
assert 'a row that names NO kind is red, not silently read off its own UUID' \
  "! kinds_run >/dev/null && kinds_run | grep -q 'names no kind'"

# The two directions the checker exists to cover, kept alongside so a future edit to the
# scan cannot quietly cost one of them.
kinds_table <<'MD'
| channel | uuid | kind |
| --- | --- | --- |
| ops | 9abcdef0-1234-5678-9abc-def012345678 | 9 — no `--kind` |
MD
assert 'a routed channel missing from the table is red' \
  "! kinds_run >/dev/null && kinds_run | grep -q 'absent from the TEAM.md table'"

kinds_table <<'MD'
| channel | uuid | kind |
| --- | --- | --- |
| ops | 9abcdef0-1234-5678-9abc-def012345678 | 9 — no `--kind` |
| forum | 11111111-2222-3333-4444-555555555555 | `--kind 45001` |
| ghost | aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee | 9 — no `--kind` |
MD
assert 'a documented channel that names no route is red' \
  "! kinds_run >/dev/null && kinds_run | grep -q 'names no route'"
rm -rf "$kroot"

echo '--- the drift check reads the manifest: exclusions are silent, undeclared is red ---'
# Synthetic trees, never the live one. A suite that asserted "the box is clean" would be red
# for reasons unrelated to the code under test, and everyone would learn to ignore it. All
# five trees are overridable for exactly this reason.
buzz_fixture() {
  root=$(mktemp -d)
  mkdir -p "$root"/{src_bin,run_bin,src_sys,etc,src_user,user,src_buzz,buzz,manifests}
  echo 'shared' > "$root/src_bin/keep.sh"
  echo 'shared' > "$root/run_bin/keep.sh"
  printf '' > "$root/ownership.toml"
  printf '' > "$root/manifests/none.toml"
  echo 'rules' > "$root/src_buzz/marcus.toml"
  echo 'rules' > "$root/buzz/marcus.toml"
  cat > "$root/src_buzz/MANIFEST.toml" <<'TOML'
[[adopted]]
path = "marcus.toml"
why  = "fixture"
[[excluded]]
path = "TEAM.md"
why  = "fixture prose"
TOML
}
buzz_drift() {
  DRIFT_SRC_BIN="$root/src_bin" DRIFT_RUNTIME_BIN="$root/run_bin" \
  DRIFT_SRC_SYSTEM="$root/src_sys" DRIFT_ETC="$root/etc" \
  DRIFT_SRC_USER="$root/src_user" DRIFT_USER="$root/user" \
  DRIFT_SRC_BUZZ="$root/src_buzz" DRIFT_BUZZ="$root/buzz" \
  DRIFT_BUZZ_MANIFEST="$root/src_buzz/MANIFEST.toml" \
  DRIFT_OWNERSHIP="$root/ownership.toml" DRIFT_MANIFESTS="$root/manifests" \
  DRIFT_NOW='2026-09-03 12:00:00' \
  bash "$CHECK" 2>&1
}
out=''
saw()   { grep -q "$1" <<<"$out"; }
clean() { ! grep -q '^  DRIFT \[buzz\]' <<<"$out"; }

buzz_fixture
echo 'prose' > "$root/buzz/TEAM.md"
out=$(buzz_drift)
assert 'a DECLARED box-only exclusion is not drift' "clean"
assert 'and is named rather than silently skipped' "saw 'box-only: TEAM.md — declared excluded'"

echo 'prose' > "$root/buzz/heartbeat.prompt"
out=$(buzz_drift)
assert 'an UNDECLARED box-only file is red — a rebuild from source loses it' \
  "saw 'DRIFT \[buzz\] box-only: heartbeat.prompt'"
rm -f "$root/buzz/heartbeat.prompt"

echo 'x' > "$root/src_buzz/stray.toml"
out=$(buzz_drift)
assert 'an UNDECLARED source-side file is red, and says it is undeclared rather than undeployed' \
  "saw 'source-only: stray.toml is in .* and declared in no MANIFEST.toml'"
rm -f "$root/src_buzz/stray.toml"
rm -rf "$root"

buzz_fixture
rm -f "$root/src_buzz/MANIFEST.toml"
rc=0; out=$(buzz_drift) || rc=$?
assert 'a MISSING MANIFEST.toml is a refusal to run, not an empty exclusion set' "[ $rc -eq 2 ]"
assert 'and the refusal explains what would otherwise have gone wrong' "saw 'undeclared drift'"
rm -rf "$root"

exit $fail
