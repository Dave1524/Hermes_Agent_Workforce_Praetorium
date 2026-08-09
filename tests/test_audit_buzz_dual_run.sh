#!/usr/bin/env bash
# bin/audit_buzz_dual_run.sh — the only thing that may certify the seven-day dual run.
#
# The migration exists because two live failures stayed green: a unit that exits 0 and
# a delivery that reached nobody look identical from the journal. So the auditor's job
# is to answer, per expected timer fire, "did Discord, the Buzz channel AND the Pulse
# note all land, or did this job correctly have nothing to say?" — and to exit non-zero
# the moment it cannot say yes.
#
# Every case here builds a synthetic receipt file. The auditor is read-only: it must
# never write, send, or touch a relay.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$REPO_ROOT/bin/audit_buzz_dual_run.sh"

fail=0

# pipefail has no place inside a boolean condition. `grep -q` exits on its first match,
# so whatever feeds it dies of SIGPIPE and the pipeline reports 141 for a pattern that
# was found — failing a true assertion, and silently passing a negated one. It is scoped
# off here rather than per-condition so a later `| grep -q` cannot reintroduce it.
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

day() { date -u -d "$1 days ago" +%Y-%m-%d; }

# A receipt as deliver.sh would have written it, on a given day.
receipt() {  # receipt <file> <days-ago> <job> <outcome> [discord] [buzz] [pulse]
  python3 - "$@" <<'PY'
import json, sys
path, days, job, outcome = sys.argv[1:5]
d, b, p = (sys.argv[5:] + ["ok", "ok", "ok"])[:3]
import subprocess
ts = subprocess.run(["date", "-u", "-d", f"{days} days ago", "+%Y-%m-%dT%H:%M:%SZ"],
                    capture_output=True, text=True).stdout.strip()
row = {"schema": 1, "ts": ts, "job": job, "route": "ops", "channel": "c" * 64,
       "outcome": outcome, "discord_result": d, "buzz_result": b, "pulse_result": p,
       "buzz_event_id": "e" * 64, "pulse_event_id": "f" * 64, "error": ""}
open(path, "a").write(json.dumps(row) + "\n")
PY
}

# The audited window ends yesterday, so seed every day from 1 to 7 days ago.
seed_clean() {  # seed_clean <file>
  local i
  for i in 1 2 3 4 5 6 7; do
    receipt "$1" "$i" overnight-morning-report.service delivered
    receipt "$1" "$i" praetorium-eod-summary.service delivered
  done
}

run_audit() {  # run_audit <receipts-file> [args...]
  local f=$1; shift
  "$SCRIPT" --receipts "$f" --unit overnight-morning-report.service "$@" 2>&1
  return $?
}

echo '--- a clean week of a daily producer passes ---'
r=$(mktemp); seed_clean "$r"
out=$(run_audit "$r"); rc=$?
assert 'exits 0' "[ '$rc' -eq 0 ]"
assert 'reports the audited window' "grep -q '7 day' <<<'$out'"
assert 'reports the unit as clean' "grep -q 'overnight-morning-report.service' <<<'$out'"
assert 'no gaps reported' "! grep -qi 'MISSING' <<<'$out'"

echo '--- one missing day fails the audit and names the date ---'
r=$(mktemp); seed_clean "$r"
grep -v "$(day 3)" "$r" > "$r.tmp" && mv "$r.tmp" "$r"
out=$(run_audit "$r"); rc=$?
assert 'exits non-zero' "[ '$rc' -ne 0 ]"
assert 'names the missing date' "grep -q '$(day 3)' <<<'$out'"
assert 'labels it MISSING' "grep -q 'MISSING' <<<'$out'"

echo '--- a delivered Discord message with a dead Buzz leg is still a gap ---'
r=$(mktemp)
for i in 1 2 3 4 5 6 7; do receipt "$r" "$i" overnight-morning-report.service delivered ok ok ok; done
grep -v "$(day 2)" "$r" > "$r.tmp" && mv "$r.tmp" "$r"
receipt "$r" 2 overnight-morning-report.service partial_success ok failed skipped
out=$(run_audit "$r"); rc=$?
assert 'exits non-zero' "[ '$rc' -ne 0 ]"
assert 'labels the partial day' "grep -q 'PARTIAL' <<<'$out'"
assert 'names the affected date' "grep -q '$(day 2)' <<<'$out'"

echo '--- a channel that landed without its Pulse note is a gap too ---'
r=$(mktemp)
for i in 1 2 3 4 5 6 7; do receipt "$r" "$i" overnight-morning-report.service delivered; done
grep -v "$(day 5)" "$r" > "$r.tmp" && mv "$r.tmp" "$r"
receipt "$r" 5 overnight-morning-report.service delivered ok ok failed
out=$(run_audit "$r"); rc=$?
assert 'a missing Pulse leg fails the audit' "[ '$rc' -ne 0 ]"
assert 'names the affected date' "grep -q '$(day 5)' <<<'$out'"

echo '--- a skipped run (no fresh artifact) is a gap, not a pass ---'
r=$(mktemp)
for i in 1 2 3 4 5 6 7; do receipt "$r" "$i" overnight-morning-report.service delivered; done
grep -v "$(day 1)" "$r" > "$r.tmp" && mv "$r.tmp" "$r"
receipt "$r" 1 overnight-morning-report.service skipped skipped skipped skipped
out=$(run_audit "$r"); rc=$?
assert 'exits non-zero' "[ '$rc' -ne 0 ]"
assert 'labels it SKIPPED rather than silently passing' "grep -q 'SKIPPED' <<<'$out'"

echo '--- silence is a pass only where the producer is allowed to be silent ---'
r=$(mktemp)   # inbox-backlog-alert fires daily and is usually silent by design
out=$("$SCRIPT" --receipts "$r" --unit inbox-backlog-alert.service 2>&1); rc=$?
assert 'an allowed-silent unit with no receipts passes' "[ '$rc' -eq 0 ]"
assert 'the silence is reported, not hidden' "grep -qi 'silent' <<<'$out'"

r=$(mktemp)   # the morning report has no such licence
out=$("$SCRIPT" --receipts "$r" --unit overnight-morning-report.service 2>&1); rc=$?
assert 'a never-silent unit with no receipts fails' "[ '$rc' -ne 0 ]"

echo '--- expected fires come from the timer, not from a duplicated calendar ---'
r=$(mktemp)
# praetorium-daily-plan is Mon..Fri: a week of weekday-only receipts must pass, and
# the auditor must not invent weekend fires.
python3 - "$r" <<'PY'
import datetime, json, sys
today = datetime.datetime.now(datetime.timezone.utc).date()
with open(sys.argv[1], "a") as fh:
    for i in range(1, 8):
        d = today - datetime.timedelta(days=i)
        if d.weekday() > 4:
            continue
        fh.write(json.dumps({
            "schema": 1, "ts": d.strftime("%Y-%m-%dT06:00:00Z"),
            "job": "praetorium-daily-plan.service", "outcome": "delivered",
            "discord_result": "ok", "buzz_result": "ok", "pulse_result": "ok"}) + "\n")
PY
out=$("$SCRIPT" --receipts "$r" --unit praetorium-daily-plan.service 2>&1); rc=$?
assert 'weekday-only producer passes with no weekend receipts' "[ '$rc' -eq 0 ]"

echo '--- the auditor is read-only ---'
r=$(mktemp); seed_clean "$r"
before=$(sha256sum "$r" | cut -d' ' -f1)
run_audit "$r" >/dev/null 2>&1
after=$(sha256sum "$r" | cut -d' ' -f1)
assert 'the receipt file is never modified' "[ '$before' = '$after' ]"
assert 'the auditor invokes no transport' \
  "! grep -vE '^[[:space:]]*#' '$SCRIPT' | grep -qE 'hermes(_cli\.main)? send|buzz messages send|buzz social publish'"

echo '--- a missing receipt file is a loud failure, not an empty pass ---'
out=$("$SCRIPT" --receipts /nonexistent/receipts.jsonl 2>&1); rc=$?
assert 'exits non-zero' "[ '$rc' -ne 0 ]"
assert 'says why' "grep -qi 'no receipt' <<<'$out'"

echo '--- unported producers are reported, never counted as clean ---'
# Against a fixture manifest, not the live one. The live manifest carries no pending row
# now that the producer matrix is complete, and a case that reads its migration state
# would have silently stopped exercising this branch the moment the last row flipped.
m=$(mktemp)
printf 'overnight-morning-report.service\tops\tfile\twired\tnever\n' >> "$m"
printf 'not-yet-ported.service\tops\tfile\tpending\tnever\n' >> "$m"
r=$(mktemp); seed_clean "$r"
out=$(BUZZ_PRODUCERS="$m" "$SCRIPT" --receipts "$r" 2>&1) || true
assert 'pending units are listed as not yet ported' "grep -qi 'pending' <<<'$out'"
assert 'the unported unit is named' "grep -q 'not-yet-ported.service' <<<'$out'"
assert 'a full-fleet audit does not pass while producers are unported' \
  "! BUZZ_PRODUCERS='$m' \"$SCRIPT\" --receipts '$r' >/dev/null 2>&1"
assert 'the wired producer alongside it still audits clean on its own' \
  "BUZZ_PRODUCERS='$m' \"$SCRIPT\" --receipts '$r' --unit overnight-morning-report.service >/dev/null 2>&1"

echo '--- with every row wired, a clean fleet is reported as clean ---'
# The exit criterion of the producer-matrix phase, stated where it can fail: once the
# manifest carries no pending row, nothing else may keep a gapless fleet from passing.
m=$(mktemp)
printf 'overnight-morning-report.service\tops\tfile\twired\tnever\n' >> "$m"
printf 'inbox-backlog-alert.service\tapprovals\tstatus\twired\tallowed\n' >> "$m"
out=$(BUZZ_PRODUCERS="$m" "$SCRIPT" --receipts "$r" 2>&1); rc=$?
assert 'exits 0' "[ '$rc' -eq 0 ]"
assert 'no pending section is printed' "! grep -qi 'pending' <<<'$out'"
assert 'and it says so' "grep -q 'RESULT: clean' <<<'$out'"

exit $fail
