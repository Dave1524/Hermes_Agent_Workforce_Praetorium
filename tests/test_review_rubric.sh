#!/usr/bin/env bash
# tests/test_review_rubric.sh — the review rubric is versioned with the code it judges (T8.3)
#
# ship-dev-plan.js's land step judges every diff against aurelian's calibration pack and
# records calibration_digest in the archive commit. Until 2026-09-22 the pack lived only at
# ~/.config/buzz-team/, declared [[excluded]] and held by a sha256 pin — the policy that gates
# every land was outside the repo it gates. This suite asserts the three facts of the move:
# the pack is a repo file, adopted and drift-checked like every other buzz-team file; it
# still carries the `**version: N**` line buzz-team/verify-fleet.sh gate 12 greps on the box,
# and its H1 agrees with it; and the land step digests the repo copy, not the box path.
#
# SOURCE, NOT THE BOX. Byte-identity with ~/.config/buzz-team/ is bin/check_deploy_drift.sh's
# job (the in-both-trees cmp), run by bin/verify.sh before any suite; every subject here is
# a file in this repo, so it runs anywhere. Each check takes its paths as arguments and is
# run against a mutated copy before the committed tree, so a check that cannot go red is
# never credited for a green.
set -uo pipefail
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
RUBRIC_NAME="aurelian-calibration.md"
RUBRIC="$REPO_ROOT/buzz-team/$RUBRIC_NAME"
MANIFEST="$REPO_ROOT/buzz-team/MANIFEST.toml"
LAND="$REPO_ROOT/.claude/workflows/ship-dev-plan.js"
REPO_DIGEST_CMD="sha256sum buzz-team/$RUBRIC_NAME"
BOX_PATH=".config/buzz-team/$RUBRIC_NAME"
fail=0
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail); set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

# --- the three checks, each over the paths it is given ------------------------------------

# Adopted means: one [[adopted]] entry naming the file, with a non-empty read_by and why,
# and no [[excluded]] entry left behind — the drift check would read the latter as "the
# repo does not hold this" and go red on the copy it does hold.
adopted_entry() {
  python3 - "$1" "$2" <<'PY'
import sys, tomllib
manifest, name = sys.argv[1], sys.argv[2]
with open(manifest, "rb") as fh:
    data = tomllib.load(fh)
adopted = [e for e in data.get("adopted", []) if e.get("path") == name]
excluded = [e for e in data.get("excluded", []) if e.get("path") == name]
problems = []
if not adopted:
    problems.append("no [[adopted]] entry")
for entry in adopted:
    for key in ("read_by", "why"):
        if not str(entry.get(key, "")).strip():
            problems.append(f"[[adopted]] entry has an empty {key}")
if excluded:
    problems.append("still declared [[excluded]]")
print("; ".join(problems) if problems else f"adopted: {name}")
sys.exit(1 if problems else 0)
PY
}

# gate 12's grep, verbatim, plus the H1 — two statements of one version, which is the
# pair a bump has to move together.
version_line() { grep -oE '^\*\*version: [0-9]+\*\*' "$1" | head -1 | grep -oE '[0-9]+'; }
h1_version()   { sed -n '1s/^# .*— v\([0-9][0-9]*\)$/\1/p' "$1"; }
version_agrees() {
  local line h1
  line=$(version_line "$1"); h1=$(h1_version "$1")
  [ -n "$line" ] && [ -n "$h1" ] && [ "$line" = "$h1" ]
}

# The land prompt digests the repo copy at the merged main and names the box path nowhere.
land_reads_repo() {
  grep -qF "$REPO_DIGEST_CMD" "$1" && ! grep -qF "$BOX_PATH" "$1"
}

echo '--- 0. canary ---'
assert 'a true piped condition reads as true' 'yes | grep -q y'

echo '--- 1. every check bites on a mutated copy before it is credited ---'
tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
cat >"$tmp/absent.toml" <<'TOML'
[[adopted]]
path = "marcus.toml"
read_by = "buzz-acp"
why = "unrelated"
TOML
cat >"$tmp/empty-why.toml" <<TOML
[[adopted]]
path = "$RUBRIC_NAME"
read_by = "the land step"
why = ""
TOML
cat >"$tmp/both.toml" <<TOML
[[adopted]]
path = "$RUBRIC_NAME"
read_by = "the land step"
why = "adopted"
[[excluded]]
path = "$RUBRIC_NAME"
kind = "prose"
why = "and still excluded"
TOML
cat >"$tmp/good.toml" <<TOML
[[adopted]]
path = "$RUBRIC_NAME"
read_by = "the land step"
why = "adopted"
TOML
assert 'adopted_entry: no entry is red'            "! adopted_entry '$tmp/absent.toml' '$RUBRIC_NAME' >/dev/null"
assert 'adopted_entry: an empty why is red'         "! adopted_entry '$tmp/empty-why.toml' '$RUBRIC_NAME' >/dev/null"
assert 'adopted_entry: adopted AND excluded is red' "! adopted_entry '$tmp/both.toml' '$RUBRIC_NAME' >/dev/null"
assert 'adopted_entry: the well-formed entry is green' "adopted_entry '$tmp/good.toml' '$RUBRIC_NAME' >/dev/null"

printf '# Pack — v3\n\n**version: 2** · maintained by Dave\n' >"$tmp/disagree.md"
printf '# Pack — v2\n\nversion 2, unstarred\n' >"$tmp/no-line.md"
printf '# Pack\n\n**version: 2** · maintained by Dave\n' >"$tmp/no-h1.md"
printf '# Pack — v2\n\n**version: 2** · maintained by Dave\n' >"$tmp/agree.md"
assert 'version_agrees: H1 v3 over **version: 2** is red' "! version_agrees '$tmp/disagree.md'"
assert 'version_agrees: no **version: N** line is red'    "! version_agrees '$tmp/no-line.md'"
assert 'version_agrees: an H1 without — vN is red'        "! version_agrees '$tmp/no-h1.md'"
assert 'version_agrees: the agreeing pair is green'       "version_agrees '$tmp/agree.md'"

printf 'Read ~/%s and calibration_digest = sha256sum of that file\n' "$BOX_PATH" >"$tmp/box-path.js"
printf 'calibration_digest = %s; also Read ~/%s\n' "$REPO_DIGEST_CMD" "$BOX_PATH" >"$tmp/both-paths.js"
printf 'calibration_digest = %s\n' "$REPO_DIGEST_CMD" >"$tmp/repo-path.js"
assert 'land_reads_repo: the box path alone is red'         "! land_reads_repo '$tmp/box-path.js'"
assert 'land_reads_repo: the repo digest beside the box path is red' "! land_reads_repo '$tmp/both-paths.js'"
assert 'land_reads_repo: the repo digest alone is green'    "land_reads_repo '$tmp/repo-path.js'"

echo '--- 2. the pack is a repo file, adopted in MANIFEST.toml (::rubric-adopted) ---'
assert "buzz-team/$RUBRIC_NAME exists and is not empty" "[ -s '$RUBRIC' ]"
out=$(adopted_entry "$MANIFEST" "$RUBRIC_NAME" 2>&1); rc=$?
assert "one [[adopted]] entry with read_by and why, no [[excluded]] row ($out)" "[ '$rc' = 0 ]"

echo '--- 3. the version gate 12 greps, and the H1 agree (::rubric-version-line) ---'
assert "repo copy carries '**version: N**' (gate 12 shape)" "grep -qsE '^\*\*version: [0-9]+\*\*' '$RUBRIC'"
assert "H1 '— vN' names the same N ($(version_line "$RUBRIC" 2>/dev/null || true) vs $(h1_version "$RUBRIC" 2>/dev/null || true))" "version_agrees '$RUBRIC'"

echo '--- 4. the land step digests the repo copy, never the box path (::land-reads-repo-rubric) ---'
assert "ship-dev-plan.js computes calibration_digest = $REPO_DIGEST_CMD" "grep -qF '$REPO_DIGEST_CMD' '$LAND'"
assert "ship-dev-plan.js names $BOX_PATH nowhere" "! grep -qF '$BOX_PATH' '$LAND'"

exit $fail
