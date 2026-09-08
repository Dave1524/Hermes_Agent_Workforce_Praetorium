#!/usr/bin/env bash
# A `present = true` surface in design/agents/*.toml is a claim that work runs there. W19
# (design/open-decisions.md) found augustus.toml's [surfaces.scheduled] still `present = true`
# four days after the only two workflows it ever hosted were retired with their unit files:
# the retirement commit touched the two files a test forced it to touch, and no check compared
# a surface's `present` flag against the [[workflows]] entries naming it. Item 10 of the W19
# table says so in as many words — "no test asserts a present surface has workflows". This
# suite is that join (T6.2, docs/dev-plan-2026-09.md).
#
# ONE DIRECTION ONLY. It asserts: every surface declared present hosts at least one
# [[workflows]] entry whose `surface` names it. It does NOT assert the reverse — that every
# entry's surface has a block — because trajan.toml's `platform` entries name a surface kind
# that has no [surfaces.platform] block anywhere, by design. Asserting that direction would
# turn a deliberate shape into sixteen findings; stated so a green run is not read as
# covering it.
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
empty_present_surfaces() {    # $1 directory of *.toml manifests
  MANIFEST_DIR="$1" python3 - <<'PY'
import os, pathlib, tomllib
d = pathlib.Path(os.environ["MANIFEST_DIR"])
for m in sorted(d.glob("*.toml")):
    try:
        doc = tomllib.loads(m.read_text())
    except Exception as exc:
        print(f"{m.name}: does not parse: {exc}")
        continue
    try:
        hosted = {w.get("surface") for w in doc.get("workflows", [])}
        for name, s in sorted(doc.get("surfaces", {}).items()):
            if isinstance(s, dict) and s.get("present") is True and name not in hosted:
                print(f"{m.name}: [surfaces.{name}] present = true hosts no [[workflows]] entry")
    except Exception as exc:
        print(f"{m.name}: checker error: {type(exc).__name__}: {exc}")
PY
}

echo "--- 0. canary ---"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "--- 1. fixtures: each failure mode is caught, a healthy manifest is not ---"
fx=$(mktemp -d)
trap 'rm -rf "$fx"' EXIT
mkdir -p "$fx/broken" "$fx/shape" "$fx/empty" "$fx/healthy" "$fx/retired"

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

assert 'a manifest that does not parse is named, not dropped from the join' \
  "empty_present_surfaces '$fx/broken' | grep -q 'bad.toml: does not parse'"  # (::manifest-parse-named)
assert 'a manifest that parses into a shape the checker cannot walk is named, not a traceback' \
  "empty_present_surfaces '$fx/shape' 2>/dev/null | grep -q 'table.toml: checker error'"  # (::manifest-shape-named)
assert 'a present surface hosting no entry is named by manifest and surface' \
  "empty_present_surfaces '$fx/empty' | grep -q 'hollow.toml: \[surfaces.scheduled\] present = true hosts no'"  # (::present-surface-hosts-work)
assert 'and the present surface beside it that does host one is not' \
  "[ \"\$(empty_present_surfaces '$fx/empty' | wc -l)\" = 1 ]"
assert 'a manifest whose present surfaces all host work is silent' \
  "[ -z \"\$(empty_present_surfaces '$fx/healthy')\" ]"
assert 'present = false over zero entries is the retired shape, not a finding' \
  "[ -z \"\$(empty_present_surfaces '$fx/retired')\" ]"  # (::retired-surface-silent)

echo "--- 2. the live manifests: $AGENTS ---"
count=$(find "$AGENTS" -maxdepth 1 -name '*.toml' | wc -l)
assert "the join read at least one manifest ($count found) — a verdict over zero would mean nothing" \
  "[ '$count' -ge 1 ]"
offenders=$(empty_present_surfaces "$AGENTS") || offenders="checker exited $? (${offenders:-no output})"
assert "every present surface hosts a workflow (${offenders:-all hosted})" \
  "[ -z \"\$offenders\" ]"

exit $fail
