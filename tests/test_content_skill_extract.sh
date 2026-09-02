#!/usr/bin/env bash
# The shared gate between this repo and the vault (D3 part 1).
#
# profiles/augustus_content_task.md tells augustus which sections of
# 08_skills/linkedin-content-engine/SKILL.md to read. The profile is here; the skill is in
# the vault, published from the Mac. NO COMMIT ON EITHER SIDE CAN SEE THE OTHER MOVE, which
# is how six pinned line ranges came to have three wrong ones by 2026-09-02 with nothing
# erroring and no suite covering it. This file is the only thing that fails when the far
# side moves, so it asserts against the vault copy the JOB ACTUALLY READS — `~/vault`
# resolved at read time, never a hardcoded side of that symlink.
#
# It is deliberately not a spell-checker over heading names. Groups 1 and 4b prove the
# names resolve; group 3 proves the resolved text is the RIGHT text, by naming the three
# lines the old pins dropped and the two they wrongly injected. Group 1 alone would have
# gone green throughout the drift it exists to catch.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXTRACT="$REPO_ROOT/bin/skill_sections.sh"
PROFILE="$REPO_ROOT/profiles/augustus_content_task.md"
SKILL_REL="08_skills/linkedin-content-engine/SKILL.md"

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

echo "--- 0. canaries ---"
# `yes` is guaranteed to still be writing when grep -q exits, so this is the race made
# deterministic: it fails if and only if a condition is evaluated under pipefail.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

# Group 3's needles start with `- `, and a bare `grep -F '- x'` reads that as an OPTION and
# exits 2 — which a MUST-NOT-CONTAIN assertion reads as "absent", certifying nothing. Every
# content assertion below uses `grep -F --`; this proves the difference is real rather than
# remembered.
dash_probe=$(mktemp); printf 'no needle here\n' > "$dash_probe"
assert 'a leading-dash needle is reported ABSENT (1), not as a usage error (2)' \
  "grep -qF -- '- absent needle' '$dash_probe'; [ \$? -eq 1 ]"
rm -f "$dash_probe"

# --- the section list the profile actually passes ---------------------------------------
#
# Read out of the profile rather than restated here. A copy in this file would be a second
# place for the list to drift, which is the defect one layer up.
profile_sections() {
  awk '
    /skill_sections\.sh/ { collecting = 1 }
    collecting {
      buf = buf " " $0
      if ($0 !~ /\\[ \t]*$/) { print buf; exit }
    }
  ' "$PROFILE" | grep -o "'[^']*'" | sed "s/^'//; s/'$//"
}

mapfile -t SECTIONS < <(profile_sections)

echo "--- 4a. the profile names its sections, and names them only once ---"
assert 'the pinned sed line ranges are gone from the profile' \
  "! grep -qE \"sed -n '[0-9]+,[0-9]+p\" '$PROFILE'"
assert 'and so is the sentence calling the line ranges the whole point' \
  "! grep -qF -- 'line ranges are the whole point' '$PROFILE'"
assert 'the profile invokes the extractor' "grep -q 'skill_sections\.sh' '$PROFILE'"
assert 'its call parses into at least one quoted section name' "[ ${#SECTIONS[@]} -ge 1 ]"
assert 'it passes all nine sections the job needs' "[ ${#SECTIONS[@]} -eq 9 ]"
# The prose enumeration and the argument list were the same list stated twice. Collapsed to
# one by this brief; this is what stops it growing back.
assert 'no second, prose enumeration of the sections survives' \
  "! grep -qF -- 'That is: Hard non-negotiables' '$PROFILE'"
assert 'the extractor is a script under bin/, where the gate lints and syntax-checks it' \
  "[ -f '$EXTRACT' ] && [ -x '$EXTRACT' ]"

echo "--- 2. the extractor is fail-loud (fixtures, not the live file) ---"
fx=$(mktemp)
cat > "$fx" <<'MD'
# Title

## Alpha
alpha body

### Step 2.5
two-point-five body

### Step 2.55
two-point-five-five body

## Beta
beta body

## Alpha
a second Alpha, making the name ambiguous
MD

run() { out=$("$EXTRACT" "$@" 2>"$errf"); rc=$?; return 0; }
errf=$(mktemp); out=''; rc=0

run "$fx" 'Nope'
assert 'an absent section name exits non-zero' "[ $rc -ne 0 ]"
assert 'and prints nothing at all on stdout' "[ -z \"\$out\" ]"
assert 'and names the offending section on stderr' "grep -q 'Nope' '$errf'"

run "$fx" 'Alpha'
assert 'an ambiguous name (two matching headings) exits non-zero' "[ $rc -ne 0 ]"
assert 'and prints nothing on stdout — never the first match' "[ -z \"\$out\" ]"
assert 'and says it was ambiguous, not absent' "grep -q 'ambiguous' '$errf'"

run "$fx" 'Step 2.5'
assert 'a name that is a strict prefix of another heading still resolves' "[ $rc -eq 0 ]"
assert 'to the exact heading' "grep -qx '### Step 2.5' <<<\"\$out\""
assert 'and never silently to both' "! grep -qx '### Step 2.55' <<<\"\$out\""

run "$fx" 'Beta' 'Alpha'
assert 'one bad name in a list poisons the whole read — no partial output' \
  "[ $rc -ne 0 ] && [ -z \"\$out\" ]"

# Extent: a section runs to the next heading of the SAME OR HIGHER level, so it carries its
# subsections. `## Alpha` here holds two `###` children, which a "stop at the next heading"
# rule would truncate and a "stop at the next blank line" rule would truncate harder.
fx2=$(mktemp)
cat > "$fx2" <<'MD'
## Parent
parent body

### Child one
child one body

### Child two
child two body

## Sibling
sibling body
MD
run "$fx2" 'Parent'
assert 'a section carries its subsections' "grep -q 'child two body' <<<\"\$out\""
assert 'and stops at the next same-level heading' "! grep -q 'sibling body' <<<\"\$out\""

# Latent today (zero #-leading lines inside the 8 fenced blocks in the live skill) and wrong
# on the first fenced example that starts a line with #.
fx3=$(mktemp)
cat > "$fx3" <<'MD'
## Real
before

```sh
# Fake heading inside a fence
echo hi
```

after

## Next
next body
MD
run "$fx3" 'Real'
assert 'a #-leading line inside a code fence is not treated as a heading' \
  "grep -q 'after' <<<\"\$out\""
rm -f "$fx" "$fx2" "$fx3" "$errf"

# --- the live vault half ------------------------------------------------------------------
#
# Groups 1, 3 and 4b read the vault. A MISSING VAULT ON THIS BOX IS A FAILURE, not a skip:
# a suite that goes quietly green when its subject vanishes is the failure mode this repo
# keeps rediscovering. So the guard's predicate is NOT "the skill file is absent" — it is
# "this is not Praetorium", proven by the deployed runtime tree being absent too. On the box
# that tree exists, so a vanished vault falls through to a red.
VAULT_ROOT=$(readlink -f "$HOME/vault" 2>/dev/null || true)
SKILL="${VAULT_ROOT:-$HOME/vault}/$SKILL_REL"

if [ ! -e "$SKILL" ] && [ ! -d "$HOME/agent-workforce" ]; then
  printf 'SKIP: %s — the vault the content job reads (absent: %s)\n' \
    "$(basename "$0")" '~/vault/08_skills/linkedin-content-engine/SKILL.md'
  exit $((fail == 0 ? 77 : 1))
fi

echo "--- 1. every section the profile names resolves in the live skill ---"
assert 'the skill file the job reads exists' "[ -r '$SKILL' ]"
# Without this the loop below runs zero times and the group prints a header and no
# assertions — green by vacancy, which is the shape of every bug in this file's lineage.
assert 'the per-section loop has sections to run over' "[ ${#SECTIONS[@]} -gt 0 ]"
for s in "${SECTIONS[@]}"; do
  run "$SKILL" "$s"
  assert "resolves to exactly one heading: $s" \
    "[ $rc -eq 0 ] && grep -qxF -- \"\$(grep -o '^#\\+ ' <<<\"\$out\" | head -1)$s\" <<<\"\$out\""
done

echo "--- 3. the extracted text is the RIGHT text ---"
errf=$(mktemp)
run "$SKILL" "${SECTIONS[@]}"
assert 'the full nine-section read succeeds' "[ $rc -eq 0 ]"
# The three lines the old pins dropped. Each is the last line of its section, which is why a
# range short by one or two lines lost them and nothing noticed.
for needle in \
  '11. **AI-tell scan**' \
  '- Bridge to the adjacent audience without hijacking the post.' \
  '- Recommended N: 3 (more than 5 is decision fatigue)'
do
  assert "contains the line the pinned ranges dropped: ${needle:0:44}" \
    "grep -qF -- \"$needle\" <<<\"\$out\""
done
# The two the old pins wrongly injected, both from sections the profile explicitly excludes.
# `[ -n "$out" ] &&` is load-bearing, not defensive: a failed read leaves $out empty, and an
# empty haystack satisfies every negative assertion at once. Observed on this suite's first
# run — both of these reported ok while the extraction they describe had not happened.
for needle in '**Codex sandbox note:**' 'Out of scope for this skill'; do
  assert "does not contain the line the pinned ranges injected: $needle" \
    "[ -n \"\$out\" ] && ! grep -qF -- \"$needle\" <<<\"\$out\""
done

echo "--- 4b. the command in the profile is the command that works ---"
# Executed, not pattern-matched. Nothing in this repo runs a shell line embedded in profile
# markdown — bin/verify.sh lints bin/, never profiles/ — and that asymmetry is exactly why
# the pins rotted unobserved. This assertion closes it.
cmd=$(awk '
  /skill_sections\.sh/ { collecting = 1 }
  collecting {
    # Whether the line continues must be read BEFORE the backslash is stripped — testing
    # the already-substituted $0 is always true, which silently truncates the command to
    # its first line and then reports the truncation as the profile being broken.
    cont = ($0 ~ /\\[ \t]*$/)
    sub(/\\[ \t]*$/, "")
    buf = buf " " $0
    if (!cont) { print buf; exit }
  }
' "$PROFILE" | sed "s|~/agent-workforce/bin/|$REPO_ROOT/bin/|; s|~/vault|${VAULT_ROOT:-$HOME/vault}|")
assert 'the profile carries a runnable extraction command' "[ -n \"\$cmd\" ]"
live=$(eval "$cmd" 2>/dev/null); live_rc=$?
# Both of the next two pass on an EMPTY command: `eval ""` exits 0, and two empty section
# sets compare equal. Conjoined with the emptiness checks so they cannot certify a command
# that was never found — the same false green as group 3, one layer further out.
assert 'running it verbatim against the live skill succeeds' \
  "[ -n \"\$cmd\" ] && [ $live_rc -eq 0 ] && [ -n \"\$live\" ]"
emitted=$(grep -o '^#\+ .*' <<<"$live" | sed 's/^#\+ //' | LC_ALL=C sort)
wanted=$(printf '%s\n' "${SECTIONS[@]}" | LC_ALL=C sort)
assert 'and emits exactly the sections it was asked for — no more, no fewer' \
  "[ -n \"\$emitted\" ] && [ \"\$emitted\" = \"\$wanted\" ]"
rm -f "$errf"

exit $fail
