#!/usr/bin/env bash
# bin/skill_telemetry.py (T3.3): which pointer skills a headless run was offered, invoked and
# read, taken from the run's Claude Code transcript and nothing else.
#
# WHY A PARSER AND NOT A GREP. 23 of the 85 transcripts on this box contain the string
# `"name":"Skill"` and none of them is an invocation — it is the Skill tool's own schema,
# snapshotted into every transcript inside a `prompt_snapshot` attachment. A grep-shaped
# extractor reports 23 false invocations; the real signal is a `tool_use` block in an
# assistant record. `telemetry-schema-not-an-invocation` is the fixture that keeps it a parser.
#
# THE THREE SETS, each taken from a record shape recorded verbatim off claude 2.1.268:
#   offered  — `attachment.type == "skill_listing"` -> `names[]`, namespace-filtered
#   invoked  — assistant `tool_use` named `Skill` whose `input.skill` is in the namespace
#   read     — assistant `tool_use` named `Read` whose `input.file_path` is a SKILL.md, either
#              the canonical vault file (`/08_skills/<name>/SKILL.md`) or the pointer itself
#              (`/skills/<owner>/skills/<name>/SKILL.md`)
# Names are printed unqualified (`meeting-prep`, never `praetorium-claudius:meeting-prep`),
# sorted, unique, comma-joined — the form agent_propose.sh appends to cost.log.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
EXTRACTOR="$REPO_ROOT/bin/skill_telemetry.py"
TD="$(mktemp -d)"

fail=0
# See CLAUDE.md § Verification: a condition must not run under pipefail, or an early-exiting
# reader (grep -q) SIGPIPEs its producer and turns a satisfied assertion red.
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

assert "a found pattern is never reported as a failure" "yes | grep -q y"

# ── Record fixtures: one transcript line each, in the shapes the CLI writes ──────────────
LISTING='{"type":"attachment","attachment":{"type":"skill_listing","isInitial":true,"skillCount":27,"names":["finish","implement","shared:codex","praetorium-claudius:investment-research","praetorium-claudius:meeting-prep","praetorium-claudius:prospect-research"]},"sessionId":"4c351116-7248-4b1e-9995-207c4cd2e8a8","cwd":"/home/dave/agent-worktrees/inbox","timestamp":"2026-09-11T11:40:00.000Z"}'
INVOKE_MEETING='{"type":"assistant","message":{"role":"assistant","content":[{"type":"text","text":"Loading the skill."},{"type":"tool_use","id":"toolu_01","name":"Skill","input":{"skill":"praetorium-claudius:meeting-prep"}}]}}'
INVOKE_RESULT='{"type":"user","message":{"role":"user","content":[{"type":"tool_result","tool_use_id":"toolu_01","content":"Launching skill: praetorium-claudius:meeting-prep"}]}}'
INVOKE_FOREIGN='{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_02","name":"Skill","input":{"skill":"shared:codex"}}]}}'
READ_CANONICAL='{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_03","name":"Read","input":{"file_path":"/home/dave/vault/08_skills/meeting-prep/SKILL.md"}}]}}'
READ_POINTER='{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_04","name":"Read","input":{"file_path":"/home/dave/agent-workforce/skills/claudius/skills/prospect-research/SKILL.md"}}]}}'
READ_REFERENCE='{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","id":"toolu_05","name":"Read","input":{"file_path":"/home/dave/vault/08_skills/meeting-prep/references/x.md"}}]}}'
# The trap: the Skill tool's schema, carried by every transcript in a prompt_snapshot.
SCHEMA_LINE='{"type":"attachment","attachment":{"type":"prompt_snapshot","tools":[{"name":"Read","description":"Reads a file"},{"name":"Skill","description":"Invoke a skill","input_schema":{"type":"object","properties":{"skill":{"type":"string"}}}}]},"timestamp":"2026-09-11T11:40:00.000Z"}'

ERR="$TD/stderr"
run() {  # extractor args; sets OUT (stdout), RC (exit status), ERR (stderr file)
  OUT=$(python3 "$EXTRACTOR" "$@" 2>"$ERR"); RC=$?
}

echo '--- 1. listing + Skill invoke + canonical Read (::telemetry-offer-from-listing) (::telemetry-invoked-from-skill-tool) (::telemetry-read-from-skill-md) ---'
t1="$TD/t1.jsonl"
printf '%s\n' "$SCHEMA_LINE" "$LISTING" "$INVOKE_MEETING" "$INVOKE_RESULT" "$READ_CANONICAL" > "$t1"
run "$t1"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'exactly one line of output' "[ \"\$(printf '%s\n' \"\$out\" | wc -l)\" = 1 ]"
assert 'offered = the three namespace names, sorted, unqualified' "[ \"\$(printf '%s' \"\$out\" | tr ' ' '\n' | grep '^offered=')\" = 'offered=investment-research,meeting-prep,prospect-research' ]"
assert 'invoked = meeting-prep' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=meeting-prep'"
assert 'read = meeting-prep' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'read=meeting-prep'"
assert 'the full line, in key order' "[ \"\$out\" = 'offered=investment-research,meeting-prep,prospect-research invoked=meeting-prep read=meeting-prep' ]"

echo '--- 2. listing only -> invoked=none read=none ---'
t2="$TD/t2.jsonl"
printf '%s\n' "$LISTING" > "$t2"
run "$t2"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'offered still populated' "printf '%s' \"\$out\" | grep -q 'offered=investment-research,meeting-prep,prospect-research'"
assert 'invoked=none' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=none'"
assert 'read=none' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'read=none'"

echo '--- 3. a foreign-namespace invoke and a references/ Read are ignored (::telemetry-ignores-foreign-namespace) ---'
t3="$TD/t3.jsonl"
printf '%s\n' "$LISTING" "$INVOKE_FOREIGN" "$READ_REFERENCE" > "$t3"
run "$t3"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'shared:codex is not an invocation in the praetorium- namespace' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=none'"
assert 'a Read under references/ is not a SKILL.md read' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'read=none'"
assert 'shared:codex is not offered either (listing is namespace-filtered)' "! printf '%s' \"\$out\" | grep -q codex"
run "$t3" --namespace shared; out=$OUT
assert '--namespace shared flips the filter: shared:codex is now the invocation' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=codex'"
assert 'and the praetorium- names drop out of offered' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'offered=codex'"

echo '--- 4. the tool schema line alone is not an invocation (::telemetry-schema-not-an-invocation) ---'
t4="$TD/t4.jsonl"
printf '%s\n' "$SCHEMA_LINE" > "$t4"
run "$t4"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'invoked=none despite "name":"Skill" being in the file' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=none'"
assert 'the string really is in the fixture (the trap is real)' "grep -q '\"name\":\"Skill\"' '$t4'"
assert 'offered=none (a prompt_snapshot is not a skill_listing)' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'offered=none'"

echo '--- 5. a Read of the pointer file itself counts as read ---'
t5="$TD/t5.jsonl"
printf '%s\n' "$READ_POINTER" > "$t5"
run "$t5"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'read=prospect-research from skills/<owner>/skills/<name>/SKILL.md' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'read=prospect-research'"

echo '--- 6. duplicates collapse and output is sorted ---'
t6="$TD/t6.jsonl"
printf '%s\n' "$LISTING" "$LISTING" "$READ_POINTER" "$READ_CANONICAL" "$READ_CANONICAL" "$READ_POINTER" "$INVOKE_MEETING" "$INVOKE_MEETING" > "$t6"
run "$t6"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'read is meeting-prep,prospect-research once each, sorted' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'read=meeting-prep,prospect-research'"
assert 'invoked collapsed to one' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=meeting-prep'"
assert 'offered collapsed across two listings' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'offered=investment-research,meeting-prep,prospect-research'"

echo '--- 7. a missing transcript exits 2 with a message on stderr (::telemetry-missing-transcript-fails-loud) ---'
run "$TD/does-not-exist.jsonl"; out=$OUT
assert 'exits 2' "[ '$RC' = 2 ]"
assert 'names the path on stderr' "grep -q 'does-not-exist.jsonl' '$ERR'"
assert 'prints nothing on stdout' "[ -z \"\$out\" ]"
out=$(run)
assert 'no argument is a usage error, not exit 0' "[ '$RC' != 0 ]"

echo '--- 8. blank and malformed lines do not abort ---'
t8="$TD/t8.jsonl"
{
  echo
  echo '{not json at all'
  printf '%s\n' "$LISTING"
  echo '   '
  echo '"a bare json string"'
  echo '{"type":"assistant","message":"content is a string not a list"}'
  echo '{"type":"assistant","message":{"content":[{"type":"tool_use","name":"Skill","input":"not an object"}]}}'
  printf '%s\n' "$INVOKE_MEETING"
  echo '[1,2,3]'
} > "$t8"
run "$t8"; out=$OUT
assert 'exits 0' "[ '$RC' = 0 ]"
assert 'the good records were still counted' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'invoked=meeting-prep'"
assert 'offered survived the noise' "printf '%s' \"\$out\" | tr ' ' '\n' | grep -qx 'offered=investment-research,meeting-prep,prospect-research'"

rm -rf "$TD"
exit $fail
