#!/usr/bin/env bash
# A `present = true` surface in design/agents/*.toml is a claim that work runs there. W19
# (design/open-decisions.md) found augustus.toml's [surfaces.scheduled] still `present = true`
# four days after the only two workflows it ever hosted were retired with their unit files:
# the retirement commit touched the two files a test forced it to touch, and no check compared
# a surface's `present` flag against the [[workflows]] entries naming it. Item 10 of the W19
# table says so in as many words — "no test asserts a present surface has workflows". This
# suite is that join (T6.2, docs/dev-plan-2026-09.md).
#
# BOTH DIRECTIONS, FOR DECLARED BLOCKS ONLY. A surface block and the entries naming it are one
# claim with two halves, and either half can be the stale one:
#   `present = true` hosting no live entry — the W19 shape above.
#   `present = false` hosting live entries — a surface switched off while work still names it,
#     which reads to every consumer that walks `surfaces` as work that runs nowhere.
# It does NOT assert that every entry's surface HAS a block: trajan.toml's `platform` entries
# name a surface kind with no [surfaces.platform] block anywhere, by design. Asserting that
# would turn a deliberate shape into sixteen findings; stated so a green run is not read as
# covering it.
#
# HOSTING IS A STATUS QUESTION, NOT AN ENTRY COUNT. `spent` means every date has fired and
# `planned` means nothing is installed (the vocabulary table, design/agent-model.md § R15), so
# neither is work running on a surface. Counting them was how this suite could have missed the
# exact case it was written for: augustus.toml's scheduled surface stayed `present = true` over
# two campaigns that had spent their last date, and an entry-count check calls that hosted. The
# other three values count — `dormant` is disabled, not gone, and its unit files are installed.
# The deny-list is deliberate: an entry whose status is unknown or missing counts as hosting, so
# an unreadable status can never be the reason a surface looks retired. Whether `status` is
# present and legal at all is tests/test_workflow_coverage.py's rule (R15), not this one's.
#
# A MANIFEST THAT DOES NOT PARSE IS NAMED, NEVER DROPPED. Skipping it would make the join
# smaller and greener at once, which is the fail-open every checker in this repo refuses. The
# same for one that parses into a shape the checker cannot walk (`[workflows]` where
# `[[workflows]]` was meant, the typo agent-model.md §4 warns about): it is one named line, not
# a traceback. And the checker's exit status is kept in group 2 — with it dropped, a traceback
# left stdout empty and the verdict printed `all hosted` over a file nothing had checked
# (found 2026-09-08).
#
# FIXTURES FIRST, LIVE TREE SECOND. Group 1 proves the checker names each failure mode on
# synthetic manifests and stays silent on healthy ones; group 2 is the verdict on
# design/agents/. No box precondition: every checkout carries the manifests, so this suite
# never prints SKIP.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
AGENTS="$REPO_ROOT/design/agents"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match, so
# whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that WAS
# found — failing a true assertion, and silently passing a negated one.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# --- the checker, one definition, used on fixtures and on the live tree --------------------
# Prints one offender per line, so a failure names its subject instead of only its count.
surface_disagreements() {     # $1 directory of *.toml manifests
  MANIFEST_DIR="$1" python3 - <<'PY'
import os, pathlib, tomllib
IDLE = {"spent", "planned"}     # every date fired / nothing installed — see the header
d = pathlib.Path(os.environ["MANIFEST_DIR"])
for m in sorted(d.glob("*.toml")):
    try:
        doc = tomllib.loads(m.read_text())
    except Exception as exc:
        print(f"{m.name}: does not parse: {exc}")
        continue
    try:
        live = {}
        for w in doc.get("workflows", []):
            if w.get("status") not in IDLE:
                live[w.get("surface")] = live.get(w.get("surface"), 0) + 1
        for name, s in sorted(doc.get("surfaces", {}).items()):
            if not isinstance(s, dict) or "present" not in s:
                continue
            n = live.get(name, 0)
            if s["present"] is True and not n:
                print(f"{m.name}: [surfaces.{name}] present = true hosts no [[workflows]] entry")
            elif s["present"] is False and n:
                print(f"{m.name}: [surfaces.{name}] present = false hosts {n} live [[workflows]] entry(ies)")
    except Exception as exc:
        print(f"{m.name}: checker error: {type(exc).__name__}: {exc}")
PY
}

echo "--- 0. canary ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. fixtures: each failure mode is caught, a healthy manifest is not ---"
fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT
mkdir -p "$fx/broken" "$fx/shape" "$fx/empty" "$fx/healthy" "$fx/retired" \
         "$fx/spent" "$fx/kept" "$fx/switched-off"

cat >"$fx/broken/bad.toml" <<'EOF'
name = "bad"
[surfaces.scheduled]
present = tru
EOF

cat >"$fx/shape/table.toml" <<'EOF'
name = "table"
[surfaces.scheduled]
present = true
[workflows]
unit    = "nightly-thing"
surface = "scheduled"
EOF

cat >"$fx/empty/hollow.toml" <<'EOF'
name = "hollow"
[surfaces.interactive]
present = true
[surfaces.scheduled]
present = true
governed_by = "bin/some_runner.sh"
[[workflows]]
unit    = "buzz-agent@hollow"
surface = "interactive"
EOF

cat >"$fx/healthy/whole.toml" <<'EOF'
name = "whole"
[surfaces.interactive]
present = true
[surfaces.scheduled]
present = true
[surfaces.kanban]
present = false
retired = "2026-09-02"
[[workflows]]
unit    = "buzz-agent@whole"
surface = "interactive"
[[workflows]]
unit    = "nightly-thing"
surface = "scheduled"
EOF

cat >"$fx/retired/quiet.toml" <<'EOF'
name = "quiet"
[surfaces.scheduled]
present = false
retired = "2026-09-04"
governed_by = "bin/retired_runner.sh"
EOF

# W19's own shape, one step earlier: the campaigns have spent their last date and the surface
# still claims them. An entry count calls this hosted; a status read calls it what it is.
cat >"$fx/spent/campaigns.toml" <<'EOF'
name = "campaigns"
[surfaces.scheduled]
present = true
[[workflows]]
unit    = "content-strategy-research"
surface = "scheduled"
status  = "spent"
[[workflows]]
unit    = "faceless-content-research"
surface = "scheduled"
status  = "planned"
EOF

# present = false over entries kept as history is the retirement done right, not a finding.
# A dormant entry is disabled, not gone, so the surface it names is still present.
cat >"$fx/kept/history.toml" <<'EOF'
name = "history"
[surfaces.scheduled]
present = false
retired = "2026-09-04"
[surfaces.interactive]
present = true
[[workflows]]
unit    = "old-campaign"
surface = "scheduled"
status  = "spent"
[[workflows]]
unit    = "buzz-agent@history"
surface = "interactive"
status  = "dormant"
EOF

# The other half of the join: a surface switched off while live work still names it.
cat >"$fx/switched-off/live.toml" <<'EOF'
name = "live"
[surfaces.scheduled]
present = false
[[workflows]]
unit    = "nightly-thing"
surface = "scheduled"
status  = "standing"
[[workflows]]
unit    = "other-thing"
surface = "scheduled"
status  = "campaign"
EOF

assert 'a manifest that does not parse is named, not dropped from the join' \
  "surface_disagreements '$fx/broken' | grep -q 'bad.toml: does not parse'"  # (::manifest-parse-named)
assert 'a manifest that parses into a shape the checker cannot walk is named, not a traceback' \
  "surface_disagreements '$fx/shape' 2>/dev/null | grep -q 'table.toml: checker error'"  # (::manifest-shape-named)
assert 'a present surface hosting no entry is named by manifest and surface' \
  "surface_disagreements '$fx/empty' | grep -q 'hollow.toml: \[surfaces.scheduled\] present = true hosts no'"  # (::present-surface-hosts-work)
assert 'and the present surface beside it that does host one is not' \
  "[ \"\$(surface_disagreements '$fx/empty' | wc -l)\" = 1 ]"
assert 'a manifest whose present surfaces all host work is silent' \
  "[ -z \"\$(surface_disagreements '$fx/healthy')\" ]"
assert 'present = false over zero entries is the retired shape, not a finding' \
  "[ -z \"\$(surface_disagreements '$fx/retired')\" ]"  # (::retired-surface-silent)
assert 'a present surface whose only entries are spent or planned is named, not counted as hosted' \
  "[ \"\$(surface_disagreements '$fx/spent' | wc -l)\" = 1 ] && surface_disagreements '$fx/spent' | grep -q 'present = true hosts no'"  # (::present-surface-hosts-work)
assert 'present = false over spent history is silent, and a dormant entry still hosts its surface' \
  "[ -z \"\$(surface_disagreements '$fx/kept')\" ]"  # (::idle-status-not-hosting)
assert 'a surface switched off while live entries still name it is named with the count' \
  "surface_disagreements '$fx/switched-off' | grep -q 'live.toml: \[surfaces.scheduled\] present = false hosts 2 live'"  # (::absent-surface-hosts-nothing)

echo "--- 2. the live manifests: $AGENTS ---"
count=$(find "$AGENTS" -maxdepth 1 -name '*.toml' | wc -l)
assert "the join read at least one manifest ($count found) — a verdict over zero would mean nothing" \
  "[ '$count' -ge 1 ]"
offenders=$(surface_disagreements "$AGENTS") || offenders="checker exited $? (${offenders:-no output})"
assert "every surface block agrees with the live entries naming it (${offenders:-all agree})" \
  "[ -z \"\$offenders\" ]"

exit $fail
