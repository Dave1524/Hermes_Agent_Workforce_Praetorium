#!/usr/bin/env bash
# Suite for bin/codex_turn_error.py — the one reader of WHY a codex-acp turn failed.
#
# A Codex refusal reaches buzz-acp as `-32603 Internal error`, fires no notify hook and posts
# nothing; the cause exists only as a `Turn error:` row in $CODEX_HOME/logs_2.sqlite. The
# fixture below is that table's real schema with rows shaped like the ones read live on
# 2026-09-25 (usage limit, 18 Sep and 24 Sep; the model 404 of 2026-09-07).
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BIN="$REPO_ROOT/bin/codex_turn_error.py"
export TZ=Europe/Amsterdam

fail=0
assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

WORK=$(mktemp -d "${TMPDIR:-/tmp}/codexerr.XXXXXX")
trap 'rm -rf "$WORK"' EXIT

# epoch <local time> — the fixture's clock, in the same zone Codex prints its reset in.
epoch() { date -d "$1" +%s; }

make_home() {  # make_home <dir> <row>... ; row = "<local time>|<body>"
  local dir=$1; shift
  mkdir -p "$dir"
  python3 - "$dir/logs_2.sqlite" "$@" <<'PY'
import sqlite3, subprocess, sys
db = sqlite3.connect(sys.argv[1])
db.execute("""CREATE TABLE logs (id INTEGER PRIMARY KEY AUTOINCREMENT, ts INTEGER NOT NULL,
  ts_nanos INTEGER NOT NULL, level TEXT NOT NULL, target TEXT NOT NULL, feedback_log_body TEXT,
  module_path TEXT, file TEXT, line INTEGER, thread_id TEXT, process_uuid TEXT,
  estimated_bytes INTEGER NOT NULL DEFAULT 0)""")
for row in sys.argv[2:]:
    when, body = row.split("|", 1)
    ts = int(subprocess.check_output(["date", "-d", when, "+%s"]).strip())
    db.execute("INSERT INTO logs (ts, ts_nanos, level, target, feedback_log_body) VALUES (?, 5, 'INFO', 't', ?)",
               (ts, body))
db.commit()
PY
}

SPAN='session_loop{thread_id=01a0}:turn{model=gpt-5.5}:session_task.run:run_turn'
QUOTA="$SPAN: Turn error: You've hit your usage limit. Upgrade to Pro (https://chatgpt.com/explore/pro), visit https://chatgpt.com/codex/settings/usage to purchase more credits or try again at Sep 26th, 2026 11:14 AM."
QUOTA_CLOCK="$SPAN: Turn error: You've hit your usage limit. Upgrade to Pro, or try again at 10:32 AM."
NOT_FOUND="$SPAN: Turn error: unexpected status 404 Not Found: The model \`gpt-5.5\` does not exist or you do not have access to it."
SAMPLED="post sampling token usage turn_id=01a0 total_usage_tokens=222633"

echo '--- last: the newest turn error since a point in time ---'
make_home "$WORK/q" "2026-09-24 12:00|$SPAN: ordinary line" "2026-09-24 19:51|$QUOTA"
out=$(python3 "$BIN" last --codex-home "$WORK/q" --since "$(epoch '2026-09-24 19:00')"); rc=$?
assert 'a usage-limit row is found' "[ $rc -eq 0 ]"
assert 'and classed quota-exhausted' "[ \"\$(printf '%s' \"\$out\" | cut -f1)\" = quota-exhausted ]"
assert 'with the reset parsed from the ordinal date' "[ \"\$(printf '%s' \"\$out\" | cut -f2)\" = '2026-09-26 11:14 CEST' ]"
assert 'and as an epoch a caller can compare' "[ \"\$(printf '%s' \"\$out\" | cut -f3)\" = \"$(epoch '2026-09-26 11:14')\" ]"
assert 'and the message without the span noise before it' \
  "printf '%s' \"\$out\" | cut -f5 | grep -q '^You.ve hit your usage limit'"
python3 "$BIN" last --codex-home "$WORK/q" --since "$(epoch '2026-09-24 20:00')" >/dev/null; rc=$?
assert 'nothing after the window is exit 1, not a stale answer' "[ $rc -eq 1 ]"

echo '--- the time-only reset rolls to the next day when it has already passed ---'
make_home "$WORK/c" "2026-09-18 20:05|$QUOTA_CLOCK"
out=$(python3 "$BIN" last --codex-home "$WORK/c" --since 0)
assert '10:32 AM after a 20:05 refusal is the next morning' "[ \"\$(printf '%s' \"\$out\" | cut -f2)\" = '2026-09-19 10:32 CEST' ]"

echo '--- blocking: a quota refusal still in force, and only that ---'
now=$(epoch '2026-09-25 01:30')
python3 "$BIN" blocking --codex-home "$WORK/q" --now "$now" >/dev/null; rc=$?
assert 'before the reset, with nothing succeeding since, it blocks' "[ $rc -eq 0 ]"
python3 "$BIN" blocking --codex-home "$WORK/q" --now "$(epoch '2026-09-26 11:20')" >/dev/null; rc=$?
assert 'after the reset it does not' "[ $rc -eq 1 ]"
make_home "$WORK/paid" "2026-09-24 19:51|$QUOTA" "2026-09-25 08:52|$SAMPLED"
python3 "$BIN" blocking --codex-home "$WORK/paid" --now "$(epoch '2026-09-25 09:00')" >/dev/null; rc=$?
assert 'a model request that succeeded after the refusal clears it (credits bought early)' "[ $rc -eq 1 ]"
make_home "$WORK/nf" "2026-09-24 19:51|$NOT_FOUND"
python3 "$BIN" blocking --codex-home "$WORK/nf" --now "$now" >/dev/null; rc=$?
assert 'a model 404 never blocks a dispatch — it is not a quota' "[ $rc -eq 1 ]"
python3 "$BIN" blocking --codex-home "$WORK/q" --now "$now" --lookback-hours 1 >/dev/null; rc=$?
assert 'a refusal older than the lookback does not block' "[ $rc -eq 1 ]"

echo '--- classify: one vocabulary for every caller ---'
assert 'usage limit' "[ \"\$(python3 '$BIN' classify \"\$QUOTA\")\" = quota-exhausted ]"
assert 'model 404' "[ \"\$(python3 '$BIN' classify \"\$NOT_FOUND\")\" = model-unavailable ]"
assert 'anything else' "[ \"\$(python3 '$BIN' classify 'stream disconnected before completion')\" = harness-error ]"

echo '--- the reader never writes, and an absent log is unknown, not "no error" ---'
before=$(sha256sum "$WORK/q/logs_2.sqlite" | cut -d' ' -f1)
python3 "$BIN" last --codex-home "$WORK/q" --since 0 >/dev/null
python3 "$BIN" blocking --codex-home "$WORK/q" --now "$now" >/dev/null
assert 'the database is byte-identical after reading' "[ \"\$(sha256sum '$WORK/q/logs_2.sqlite' | cut -d' ' -f1)\" = '$before' ]"
python3 "$BIN" last --codex-home "$WORK/absent" --since 0 >/dev/null 2>"$WORK/err"; rc=$?
assert 'a missing log exits 2' "[ $rc -eq 2 ]"
assert 'and says so on stderr' "grep -q 'could not be read' '$WORK/err'"

if [ "$fail" -ne 0 ]; then echo "FAILED"; exit 1; fi
echo "all codex_turn_error assertions passed"
