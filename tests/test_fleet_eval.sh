#!/usr/bin/env bash
# Gate for the fleet eval suite — the thing that watches for drift must not drift itself.
#
# Two classes of bug are pinned here, and both have already happened once:
#
#   * A verdict computed from the wrong evidence. `@@ -84,3 @@ (83 before, 0 after)` is a
#     hunk header followed by the count of lines OUTSIDE the chunk. Reading the pair as
#     the chunk's context window reconstructs the whole document, so a stale top hit
#     appears to carry a pointer to the fresh one and the suite reports an improvement
#     that never happened. The span assertions below fix that semantics in a test.
#
#   * A field that exists in only some of the evidence. `kind` and `notify` were added to
#     the delivery receipt on 2026-08-08; every receipt before that carries neither.
#     Treating absent as mismatched turns a schema change into a wall of false failures,
#     which is how a suite gets muted.
#
# Fixtures are synthetic throughout: a test that reads the live receipt log or the live
# vault passes or fails on today's weather, not on the code. The one exception is the
# orchestrator section, which checks plumbing (scorecard, history spine) and not verdicts.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BEHAVIOUR="$REPO_ROOT/bin/fleet_eval_behaviour.py"
GROUNDING="$REPO_ROOT/bin/fleet_eval_grounding.py"
ORCHESTRATOR="$REPO_ROOT/bin/fleet_eval.sh"
PROBES="$REPO_ROOT/bin/fleet_eval_probes.json"

fail=0
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match,
# so whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that
# was found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# Named so it has no sibling in bin/ — the deploy-drift assertion compares against a
# same-named source file, and a fixture must not be graded against the real table.
ROUTES="$TMP/routes_fixture.env"
AGENTS="$TMP/agents_fixture.env"

cat >"$ROUTES" <<'EOF'
ROUTE_ops=62f321f3-bd6a-4b31-b19b-b8b49bed30f4
ROUTE_ops_kind=9
ROUTE_ops_notify=marcus
ROUTE_research=6ea596af-248f-46ee-b89d-8b13696083e4
ROUTE_research_kind=45001
ROUTE_research_notify=claudius
EOF

cat >"$AGENTS" <<'EOF'
AGENT_marcus=abbc19ddcc22f6511183936a4993359d4d22c6ef5afc53c7dba65bdeb958916b
AGENT_claudius=818238434309416fa7fd8cc482908e61f8ebcb6978ff974ccf2044d4ed014c7c
EOF

receipt() {
  python3 - "$@" <<'PY'
import json, sys
receipt = {"ts": sys.argv[1], "job": "t.service", "route": sys.argv[2],
           "channel": sys.argv[3], "buzz_attempted": True, "buzz_result": "ok",
           "identity": "praetorium"}
for pair in sys.argv[4:]:
    key, value = pair.split("=", 1)
    receipt[key] = value
print(json.dumps(receipt))
PY
}

behaviour() {
  python3 "$BEHAVIOUR" --routes "${2:-$ROUTES}" --agents "$AGENTS" \
    --receipts "$1" --days 2 --no-coverage
}

NOW="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
OPS=62f321f3-bd6a-4b31-b19b-b8b49bed30f4
RESEARCH=6ea596af-248f-46ee-b89d-8b13696083e4

echo '--- tier 1: a conforming delivery certifies clean ---'
receipt "$NOW" ops "$OPS" kind=9 notify=marcus >"$TMP/good.jsonl"
receipt "$NOW" research "$RESEARCH" kind=45001 notify=claudius >>"$TMP/good.jsonl"
behaviour "$TMP/good.jsonl" >"$TMP/good.out"
assert 'conforming receipts exit 0' "[ $? -eq 0 ]"
assert 'conformance passes' "grep -q '^receipt-conformance|PASS|2|' '$TMP/good.out'"
assert 'both routes register as exercised' "grep -q '^route-exercise|PASS|2/2|' '$TMP/good.out'"

echo '--- tier 1: a kind that contradicts the route table is caught ---'
receipt "$NOW" research "$RESEARCH" kind=9 notify=claudius >"$TMP/badkind.jsonl"
behaviour "$TMP/badkind.jsonl" >"$TMP/badkind.out"
assert 'a kind-9 post to a forum route fails' "grep -q '^receipt-conformance|FAIL|' '$TMP/badkind.out'"
assert 'the failure names the field and both values' \
  "grep -q \"kind='9' but route says '45001'\" '$TMP/badkind.out'"

echo '--- tier 1: a delivery that woke the wrong agent is caught ---'
receipt "$NOW" ops "$OPS" kind=9 notify=claudius >"$TMP/badnotify.jsonl"
behaviour "$TMP/badnotify.jsonl" >"$TMP/badnotify.out"
assert 'a mismatched notify slug fails' "grep -q '^receipt-conformance|FAIL|' '$TMP/badnotify.out'"
assert 'the failure names the slug that was woken' \
  "grep -q \"notify='claudius' but route says 'marcus'\" '$TMP/badnotify.out'"

echo '--- tier 1: a pre-2026-08-08 receipt carries no kind and is not a mismatch ---'
receipt "$NOW" research "$RESEARCH" >"$TMP/legacy.jsonl"
behaviour "$TMP/legacy.jsonl" >"$TMP/legacy.out"
assert 'a receipt with no kind/notify field passes' "grep -q '^receipt-conformance|PASS|' '$TMP/legacy.out'"
assert 'and is counted as legacy rather than certified' "grep -q 'pre-2026-08-08' '$TMP/legacy.out'"

echo '--- tier 1: a delivery to an undeclared route is caught ---'
receipt "$NOW" nowhere "$OPS" kind=9 notify=marcus >"$TMP/unknown.jsonl"
behaviour "$TMP/unknown.jsonl" >"$TMP/unknown.out"
assert 'an unknown route fails' "grep -q '^receipt-route-known|FAIL|' '$TMP/unknown.out'"

echo '--- tier 1: the route table is checked before any receipt is read ---'
sed 's/ROUTE_ops_notify=marcus/ROUTE_ops_notify=nobody/' "$ROUTES" >"$TMP/no_such_agent.env"
behaviour "$TMP/good.jsonl" "$TMP/no_such_agent.env" >"$TMP/no_such_agent.out"
assert 'a notify slug resolving to no agent fails — the send would be fatal' \
  "grep -q '^route-table|FAIL|' '$TMP/no_such_agent.out'"

sed 's/ROUTE_research_kind=45001/ROUTE_research_kind=45003/' "$ROUTES" >"$TMP/kind45003.env"
behaviour "$TMP/good.jsonl" "$TMP/kind45003.env" >"$TMP/kind45003.out"
assert '45003 is not a legal route kind (it is a reply, and nothing here replies)' \
  "grep -q '^route-table|FAIL|' '$TMP/kind45003.out'"

sed 's|^ROUTE_ops=.*|ROUTE_ops=not-a-uuid|' "$ROUTES" >"$TMP/notauuid.env"
behaviour "$TMP/good.jsonl" "$TMP/notauuid.env" >"$TMP/notauuid.out"
assert 'a channel that is not a uuid fails' "grep -q '^route-table|FAIL|' '$TMP/notauuid.out'"

echo '--- tier 2: the retrieved span is the hunk header, not the surrounding document ---'
cat >"$TMP/span_test.py" <<PY
import importlib.util, sys

spec = importlib.util.spec_from_file_location("grounding", "$GROUNDING")
grounding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grounding)

HIT = {"file": "qmd://vault/a.md", "line": 85,
       "snippet": "@@ -84,3 @@ (83 before, 0 after)\n\nbody"}

asked = []
grounding.qmd_get = lambda path: asked.append(path) or "chunk body, no pointer here"
grounding._span_text(HIT)
if asked != ["vault/a.md:84:3"]:
    sys.exit(f"read {asked}, expected the hunk header range ['vault/a.md:84:3']")

# The banner sits at lines 6-10 of an 85-line file. Reading '(83 before, 0 after)' as a
# context window would pull lines 2-85 and find it; the chunk is 84-86 and does not.
BANNER = "> superseded — read [[buzz_architecture]]"
grounding.qmd_get = lambda path: BANNER if path.endswith(":2:84") else "tail of the document"
if "buzz_architecture" in grounding._span_text(HIT):
    sys.exit("a banner outside the retrieved chunk was counted as a pointer")

# A snippet with no hunk header falls back to the preview text, and must not pass by
# reading a chunk it was never given a range for.
headerless = {"file": "qmd://vault/a.md", "snippet": BANNER}
if "buzz_architecture" not in grounding._span_text(headerless):
    sys.exit("a pointer in a headerless snippet was missed")
PY
python3 "$TMP/span_test.py" >"$TMP/span.out" 2>&1
assert 'the chunk read is exactly the hunk header range' \
  "[ $? -eq 0 ] || { cat '$TMP/span.out'; false; }"

echo '--- tier 2: a probe is scored against its baseline, not against absolute state ---'
cat >"$TMP/baseline_test.py" <<PY
import importlib.util, sys

spec = importlib.util.spec_from_file_location("grounding", "$GROUNDING")
grounding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grounding)

ANCHOR = {"index": "p/anchor.md", "disk": "p/anchor.md", "pointer": "buzz[_-]architecture"}
FOUND = [{"file": "qmd://vault/p/anchor.md", "line": 1, "snippet": "@@ -1,2 @@"}]
MISSED = [{"file": "qmd://vault/p/other.md", "line": 1, "snippet": "@@ -1,2 @@"}]

def score(results, baseline):
    grounding.run_query = lambda probe: results
    grounding.qmd_get = lambda path: "a chunk that points nowhere"
    report = grounding.Report()
    grounding.run_probe(report, {"id": "t", "limit": 1, "searches": [],
                                 "max_rank": 1, "baseline": baseline}, ANCHOR)
    _check, status, verdict, _detail = report.rows[0]
    return status, verdict, report.failed

CASES = [
    (MISSED, "FAIL", "PASS", "FAIL", False, "a probe still at its FAIL baseline must not fail the suite"),
    (FOUND, "FAIL", "PASS", "PASS", False, "a probe that beats its baseline reports an improvement"),
    (MISSED, "PASS", "FAIL", "FAIL", True, "a probe that falls below its baseline is a regression"),
    (FOUND, "PASS", "PASS", "PASS", False, "a probe holding a PASS baseline stays green"),
]
for results, baseline, want_status, want_verdict, want_failed, why in CASES:
    status, verdict, failed = score(results, baseline)
    if (status, verdict, failed) != (want_status, want_verdict, want_failed):
        sys.exit(f"{why}: got {status}/{verdict}/exit-fail={failed}, "
                 f"expected {want_status}/{want_verdict}/exit-fail={want_failed}")
PY
python3 "$TMP/baseline_test.py" >"$TMP/baseline.out" 2>&1
assert 'a verdict is scored against the recorded baseline, not against PASS' \
  "[ $? -eq 0 ] || { cat '$TMP/baseline.out'; false; }"

echo '--- tier 2: a must_answer probe asserts the window, not the document ---'
cat >"$TMP/window_test.py" <<PY
import importlib.util, sys

spec = importlib.util.spec_from_file_location("grounding", "$GROUNDING")
grounding = importlib.util.module_from_spec(spec)
spec.loader.exec_module(grounding)

ANCHOR = {"index": "p/anchor.md", "disk": "p/anchor.md", "pointer": "buzz[_-]architecture"}
ANCHOR_FIRST = [{"file": "qmd://vault/p/anchor.md", "line": 44, "snippet": "@@ -44,4 @@"}]
ANCHOR_ABSENT = [{"file": "qmd://vault/p/other.md", "line": 1, "snippet": "@@ -1,2 @@"}]
ANSWER = "| Forum — root post | 45001 |"

def score(results, chunk):
    reads = []
    grounding.run_query = lambda probe: results
    grounding.qmd_get = lambda path: reads.append(path) or chunk
    report = grounding.Report()
    grounding.run_probe(report, {"id": "t", "limit": 1, "searches": [], "max_rank": 1,
                                 "must_answer": r"\b45001\b", "baseline": "PASS"}, ANCHOR)
    _check, _status, verdict, _detail = report.rows[0]
    return verdict, report.failed, reads

CASES = [
    (ANCHOR_FIRST, ANSWER, "PASS", False,
     "the anchor ranks and the window it hands over carries the answer"),
    (ANCHOR_FIRST, "prose about forums that names no kind at all", "POINTER", True,
     "right document, wrong window — the placement regression this shape exists to catch"),
    (ANCHOR_ABSENT, ANSWER, "FAIL", True,
     "another document's span must never satisfy the anchor's assertion"),
]
for results, chunk, want_verdict, want_failed, why in CASES:
    verdict, failed, reads = score(results, chunk)
    if (verdict, failed) != (want_verdict, want_failed):
        sys.exit(f"{why}: got {verdict}/exit-fail={failed}, "
                 f"expected {want_verdict}/exit-fail={want_failed}")
    if results is ANCHOR_ABSENT and reads:
        sys.exit(f"{why}: read {reads} — a span assertion with no anchor has nothing to read")
PY
python3 "$TMP/window_test.py" >"$TMP/window.out" 2>&1
assert 'a span that loses the answer is a regression even at rank 1' \
  "[ $? -eq 0 ] || { cat '$TMP/window.out'; false; }"

echo '--- the fixture is data the runner never second-guesses ---'
cat >"$TMP/fixture_test.py" <<PY
import json, re, sys

fixture = json.load(open("$PROBES"))
probes = fixture["probes"]

for probe in probes:
    if "must_answer" not in probe:
        continue
    try:
        re.compile(probe["must_answer"])
    except re.error as error:
        sys.exit(f"{probe['id']}: must_answer is not a valid regex — {error}")
if not any("must_answer" in probe for probe in probes):
    sys.exit("no probe asserts a retrieved span — nothing here would catch a re-cut chunk")

if not all("baseline" in probe for probe in probes):
    sys.exit("a probe with no baseline would be scored against PASS and go red on day one")
if not all(probe["baseline"] in ("PASS", "POINTER", "FAIL") for probe in probes):
    sys.exit("a baseline outside PASS/POINTER/FAIL raises KeyError in RANK mid-run")
if not all(probe.get("why") for probe in probes):
    sys.exit("a probe with no 'why' cannot be judged when it goes red a month from now")
if len({probe["id"] for probe in probes}) != len(probes):
    sys.exit("duplicate probe ids collapse two rows into one in the history spine")
if fixture["anchor"]["index"] == fixture["anchor"]["disk"]:
    sys.exit("the anchor must be spelled in both dialects — they differ and the error is identical")
PY
python3 "$TMP/fixture_test.py" >"$TMP/fixture.out" 2>&1
assert 'the probe fixture is self-consistent' "[ $? -eq 0 ] || { cat '$TMP/fixture.out'; false; }"
assert 'no query text leaks from the fixture into the runner' \
  "! grep -qi 'approval gate\|publish its work' '$GROUNDING'"

echo '--- the regression post goes somewhere that exists ---'
# fleet-eval is not a row in bin/buzz_producers.tsv — it delivers from inside ExecStart,
# conditionally, rather than through an ExecStartPost adapter, so the manifest's wired
# contract cannot describe it (the header there says why). That makes these the only
# assertions standing between a renamed route and a regression report that goes nowhere.
ROUTE_TABLE="$REPO_ROOT/bin/buzz_routes.env"
route=$(grep -oE '\-\-route [a-z][a-z0-9_-]*' "$ORCHESTRATOR" | awk '{print $2}' | sort -u)
assert 'the orchestrator names exactly one delivery route' "[ \$(echo $route | wc -w) -eq 1 ]"
assert "its route '$route' is defined in the route table" "grep -q '^ROUTE_${route}=' '$ROUTE_TABLE'"
assert "its route '$route' names the agent the post wakes" \
  "grep -q '^ROUTE_${route}_notify=' '$ROUTE_TABLE'"
assert 'the scorecard it posts is anchored to the run that produced it' \
  "grep -q -- '--run-marker' '$ORCHESTRATOR'"
assert 'delivery goes through bin/deliver.sh, never a transport directly' \
  "! grep -vE '^[[:space:]]*#' '$ORCHESTRATOR' | grep -E 'buzz messages send|buzz canvas set' >/dev/null"

echo '--- the orchestrator writes a scorecard and a history spine ---'
FLEET_EVAL_LOG_ROOT="$TMP/logs" FLEET_EVAL_LOCK="$TMP/lock" \
  bash "$ORCHESTRATOR" --skip-probes --no-coverage --quiet
assert 'the history spine is created with a header' \
  "head -1 '$TMP/logs/history.psv' | grep -q '^run_ts|tier|check|status|value$'"
assert 'a scorecard is written for the run' "ls '$TMP'/logs/*/scorecard.md >/dev/null 2>&1"
assert 'both tiers report into the same run' \
  "[ \$(cut -d'|' -f2 '$TMP/logs/history.psv' | sort -u | grep -c 'tier[12]') -eq 2 ]"
assert 'each tier produced rows rather than an empty runner' \
  "! grep -q '|runner|FAIL|' '$TMP'/logs/*/results.psv"

before=$(wc -l <"$TMP/logs/history.psv")
FLEET_EVAL_LOG_ROOT="$TMP/logs" FLEET_EVAL_LOCK="$TMP/lock" \
  bash "$ORCHESTRATOR" --skip-probes --no-coverage --quiet
assert 'a second run appends to the spine rather than replacing it' \
  "[ \$(wc -l <'$TMP/logs/history.psv') -gt $before ]"

echo '--- a run already in flight is skipped, not queued ---'
# Held by this shell rather than a background sleep, so there is no window in which the
# orchestrator wins the lock and the assertion measures an ordinary run instead.
exec 8>"$TMP/lock2"
flock -n 8
FLEET_EVAL_LOG_ROOT="$TMP/logs" FLEET_EVAL_LOCK="$TMP/lock2" \
  bash "$ORCHESTRATOR" --skip-probes --no-coverage --quiet 2>"$TMP/contended.err"
contended=$?
exec 8>&-
assert 'a contended run exits 0 — a skipped measurement is not a regression' "[ $contended -eq 0 ]"
assert 'and says so on stderr' "grep -q 'skipping' '$TMP/contended.err'"

echo
[ $fail -eq 0 ] && echo "PASS" || echo "FAIL"
exit $fail
