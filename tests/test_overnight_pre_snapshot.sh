#!/usr/bin/env bash
# bin/overnight_pre_snapshot.sh — the model-free 04:25 state capture the morning report reads.
# W6: it carried status = "standing" with neither `suite` nor `suite_exempt` from D6 until
# 2026-09-03. It is the ancestor the other five unit-list consumers copied, so a defect here
# propagates by imitation rather than by call graph.
#
# Offline by contract. The script is copied into a fixture tree beside a fixture
# config/fleet-units.tsv (FLEET_UNITS is resolved from $0, which is what makes that possible
# and is asserted below), and systemctl/curl/ss/timedatectl are stubbed on PATH. Nothing here
# queries the live manager, opens a socket, or writes ~/logs/overnight.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in the shared assert(): `yes` is
# still writing when `grep -q` exits, so this fails if and only if a condition is evaluated
# under pipefail. It lives in every caller because the assert it guards is shared.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

SNAP="$REPO_ROOT/bin/overnight_pre_snapshot.sh"

# Fixture unit list. Deliberately NOT a copy of the real one: it carries one row of each shape
# the script must treat differently, including a kind=service row that has no timer at all.
FIXTURE_TSV=$(printf '%s\n' \
  '# fixture' \
  'notinstalled-unit	system	standing	trajan	timer' \
  'neverran-unit	system	standing	trajan	timer' \
  'healthy-unit	system	standing	claudius	timer' \
  'usertimer-unit	user	standing	trajan	timer' \
  'buzz-agent@marcus	user	standing	marcus	service')

# Stub manager. Records every invocation, and answers `show` from a per-unit mode file so the
# three branches of the "Recent unit results" loop can each be driven deliberately.
make_stubs() { # dir, [systemctl_rc]
  local dir=$1 rc=${2:-0}
  cat > "$dir/systemctl" <<EOF
#!/usr/bin/env bash
printf 'xdg=%s argv=%s\n' "\${XDG_RUNTIME_DIR:-UNSET}" "\$*" >> "$dir/calls.log"
if [ "\$1" = show ]; then
  unit=\$2
  mode=\$(cat "$dir/mode.\${unit%.service}" 2>/dev/null || echo ok)
  case "\$*" in
    *LoadState*) [ "\$mode" = notinstalled ] && echo not-found || echo loaded ;;
    *ExecMainStartTimestamp\ --value*)
      [ "\$mode" = neverran ] || echo "Wed 2026-09-03 04:25:01 CEST" ;;
    *)
      # systemd's OWN order, not the order of the -p flags. A consumer that parsed
      # \`--value\` positionally would mislabel every field against this.
      printf 'ExecMainStartTimestamp=Wed 2026-09-03 04:25:01 CEST\nActiveState=inactive\nResult=success\nExecMainStatus=0\n' ;;
  esac
  exit 0
fi
echo "(stub systemctl: \$*)"
exit $rc
EOF
  chmod +x "$dir/systemctl"
  # Created empty, not on first call. `! grep -q X missing_file` is TRUE — so a fixture that
  # never invokes the stub would satisfy every "systemctl is never reached" assertion below
  # without proving anything. Same shape as `grep -c` on a missing path returning a clean 0.
  : > "$dir/calls.log"
  for c in curl ss timedatectl; do
    printf '#!/usr/bin/env bash\nexit 1\n' > "$dir/$c"
    chmod +x "$dir/$c"
  done
}

# tsv-content -> fixture root with ./bin/overnight_pre_snapshot.sh and ./config/fleet-units.tsv
make_snap_fixture() {
  local tsv=$1 root
  root=$(mktemp -d)
  mkdir -p "$root/bin" "$root/config" "$root/stub" "$root/home/logs"
  cp "$SNAP" "$root/bin/overnight_pre_snapshot.sh"
  printf '%s\n' "$tsv" > "$root/config/fleet-units.tsv"
  make_stubs "$root/stub"
  # One unit per branch of the "Recent unit results" loop. The stub defaults to "ok", so
  # without these two files all three units answer loaded+started and the two branches that
  # exist to catch systemd's reset defaults are never reached.
  echo notinstalled > "$root/stub/mode.notinstalled-unit"
  echo neverran     > "$root/stub/mode.neverran-unit"
  echo "$root"
}

# Alert-log fixture with an EXPLICIT age, because the age is the variable under test. A marker
# that printed "STALE" unconditionally would satisfy a stale-only fixture, so the fresh case is
# what makes the stale case evidence rather than a coincidence.
#
# The default line is shaped like a real one: bin/agent_alert.sh:122 writes
# `agent-workforce ALERT: unit <u> failed at <ISO>Z`, so the tail ALREADY contains a timestamp
# even when the log is dead. That is deliberate — it makes "a date appears in the section" true
# of the broken code, and forces the assertions below onto the age instead.
make_alert_log() { # root, touch-date [, line...]
  local root=$1 when=$2; shift 2
  [ $# -gt 0 ] || set -- 'agent-workforce ALERT: unit qmd-refresh.service failed at 2026-08-26T04:25:01Z'
  printf '%s\n' "$@" > "$root/home/logs/agent-alert.log"
  touch -d "$when" "$root/home/logs/agent-alert.log"
}

run_snap() { # root -> rc; snapshot path in $root/snap_path, output in $root/run.log
  local root=$1 rc=0
  HOME="$root/home" PATH="$root/stub:$PATH" OVERNIGHT_LOG_DIR="$root/out" \
    bash "$root/bin/overnight_pre_snapshot.sh" > "$root/run.log" 2>&1 || rc=$?
  sed -n 's/^wrote //p' "$root/run.log" > "$root/snap_path"
  echo "$rc"
}

snap() { cat "$(cat "$1/snap_path")"; }

# Body of one `## Section` heading, exclusive of the next — so an assertion about the alerts
# section cannot be satisfied by text that happens to appear in the disk section.
section_of() { # root, heading
  awk -v h="## $2" '$0==h{f=1;next} /^## /{f=0} f' "$(cat "$1/snap_path")"
}

echo "--- pre-snapshot: writes one timestamped artifact and says where ---"
root=$(make_snap_fixture "$FIXTURE_TSV")
rc=$(run_snap "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'honours OVERNIGHT_LOG_DIR (which is why this suite touches no real log dir)' \
  "[[ \"\$(cat '$root/snap_path')\" == '$root/out/'* ]]"
assert 'the artifact exists and is non-empty' "[ -s \"\$(cat '$root/snap_path')\" ]"
# UTC in the filename, and journalctl on this box renders CEST (+2). A snapshot named in local
# time would sort correctly and correlate wrongly, which is the silent-offset trap.
assert 'the filename is stamped UTC, with the Z that says so' \
  "[[ \"\$(basename \"\$(cat '$root/snap_path')\")\" =~ ^pre-snapshot-[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{4}Z\.log\$ ]]"
assert 'and stdout names the file for the ExecStartPost consumer' \
  "grep -q '^wrote $root/out/pre-snapshot-' '$root/run.log'"

echo "--- pre-snapshot: kind is honoured — a service is never asked for as a timer ---"
# The five buzz-agent@* rows are Type=simple services. Appending ".timer" unconditionally asks
# the manager for a unit that does not exist, and list-timers answers by SILENTLY DROPPING the
# name: rc=0, empty stderr, "1 timers listed" for six units requested. A live, healthy agent
# renders as one that has never fired.
assert 'the user-scope timer call names the timer row' \
  "grep -q 'argv=--user list-timers usertimer-unit.timer' '$root/stub/calls.log'"
assert 'and never asks for buzz-agent@marcus.timer, which does not exist' \
  "! grep -q 'buzz-agent@marcus.timer' '$root/stub/calls.log'"
assert 'the service row is asked for with is-active instead' \
  "grep -q 'argv=--user is-active buzz-agent@marcus.service' '$root/stub/calls.log'"
assert 'its state is reported under its own heading' \
  "section_of '$root' 'Systemd services, user scope (kind=service — always-on, no timer)' | grep -qE 'buzz-agent@marcus\\.service +active='"
# Both --user calls carry XDG_RUNTIME_DIR: this runs as a SYSTEM unit with no session bus,
# where a bare `systemctl --user` exits 1 and the user-scope half reads as empty.
assert 'every --user call carries XDG_RUNTIME_DIR (no session bus under a system unit)' \
  "! grep -E 'argv=--user ' '$root/stub/calls.log' | grep -q 'xdg=UNSET'"

echo "--- pre-snapshot: Recent unit results distinguishes systemd's reset defaults ---"
# Result=success and ExecMainStatus=0 are what systemd returns for a unit that does not exist
# and for one that has never run since boot. Printing them unqualified reports an uninstalled
# unit as healthy — which is exactly what agent-drift-check.service did while it was declared
# in the manifests and absent from /etc.
recent=$(section_of "$root" 'Recent unit results')
printf '%s\n' "$recent" > "$root/recent.txt"
assert 'a not-found unit is reported NOT INSTALLED, not healthy' \
  "grep -A1 -x -- '--- notinstalled-unit.service ---' '$root/recent.txt' | grep -q 'NOT INSTALLED (LoadState=not-found)'"
assert 'and its reset-default Result= is never printed' \
  "! grep -A1 -x -- '--- notinstalled-unit.service ---' '$root/recent.txt' | grep -q 'Result='"
assert 'a loaded-but-never-run unit says NEVER RAN since boot' \
  "grep -A1 -x -- '--- neverran-unit.service ---' '$root/recent.txt' | grep -q 'NEVER RAN since boot'"
assert 'and its reset-default Result= is never printed either' \
  "! grep -A1 -x -- '--- neverran-unit.service ---' '$root/recent.txt' | grep -q 'Result='"
assert 'a genuinely-run unit does get its outcome' \
  "grep -A1 -x -- '--- healthy-unit.service ---' '$root/recent.txt' | grep -q 'Result=success'"
# KEY=VALUE, not --value. `systemctl show -p A -p B --value` prints in systemd's OWN order
# rather than the order of the flags, so a positional parse silently swaps fields. The stub
# answers in a deliberately different order from the flags to keep that honest.
assert 'the outcome line is KEY=VALUE, so no field can be positionally mislabelled' \
  "grep -A1 -x -- '--- healthy-unit.service ---' '$root/recent.txt' | grep -q 'ActiveState=inactive' \
   && grep -A1 -x -- '--- healthy-unit.service ---' '$root/recent.txt' | grep -q 'ExecMainStatus=0'"

echo "--- pre-snapshot: an empty derived list REFUSES rather than reporting ---"
# `NF>=5` matches nothing in a 4-column (pre-2026-09-03) copy of the list, and `systemctl
# list-timers` with an empty argument array lists EVERY timer on the box — 44, measured
# 2026-09-03. So the failure mode of a stale list is a full-looking report derived from
# nothing, which is strictly worse than the glob it replaced.
four_col=$(printf '%s\n' "$FIXTURE_TSV" | awk -F'\t' 'BEGIN{OFS="\t"} !/^#/ && NF>=5 {print $1,$2,$3,$4}')
root4=$(make_snap_fixture "$four_col")
rc=$(run_snap "$root4")
assert 'still exits 0 (fail-soft per section, by design)' "[ '$rc' = 0 ]"
assert 'the snapshot carries the FATAL, since stderr is captured into it' \
  "grep -q 'FATAL: .*declares no system/timer units' \"\$(cat '$root4/snap_path')\""
assert 'and says coverage is UNKNOWN, not none' \
  "grep -q \"Unit coverage is UNKNOWN, not 'none'\" \"\$(cat '$root4/snap_path')\""
assert 'the timer section says UNKNOWN, never no timers' \
  "section_of '$root4' 'Systemd timers (fleet schedule)' | grep -q \"NOT 'no timers'\""
assert 'the user-scope section refuses independently' \
  "section_of '$root4' 'Systemd timers (user scope)' | grep -q \"NOT 'no user-scope timers'\""
assert 'so does the kind=service section' \
  "section_of '$root4' 'Systemd services, user scope (kind=service — always-on, no timer)' | grep -q \"NOT 'no user-scope services'\""
assert 'and list-timers is NEVER called, so no 44-timer listing can be produced' \
  "[ -f '$root4/stub/calls.log' ] && ! grep -q 'list-timers' '$root4/stub/calls.log'"

emptyroot=$(make_snap_fixture "")
rc=$(run_snap "$emptyroot")
assert 'an empty list file refuses the same way (missing and empty are one failure)' \
  "[ '$rc' = 0 ] && grep -q 'FATAL' \"\$(cat '$emptyroot/snap_path')\" \
   && [ -f '$emptyroot/stub/calls.log' ] && ! grep -q 'list-timers' '$emptyroot/stub/calls.log'"

echo "--- pre-snapshot: FLEET_UNITS is script-relative, not cwd-relative ---"
# `$(dirname "$0")/../config/fleet-units.tsv` is what lets the same script work from the repo
# and from ~/agent-workforce/. design/ is not deployed, so reading the manifests at run time
# would work here and empty silently in the tree systemd actually execs — which is why the
# list is a committed literal. Proven by running from an unrelated cwd and checking that the
# FIXTURE's units, not this repo's, came out.
root=$(make_snap_fixture "$FIXTURE_TSV")
rc=0
( cd "$(mktemp -d)" && HOME="$root/home" PATH="$root/stub:$PATH" OVERNIGHT_LOG_DIR="$root/out" \
    bash "$root/bin/overnight_pre_snapshot.sh" ) > "$root/run.log" 2>&1 || rc=$?
sed -n 's/^wrote //p' "$root/run.log" > "$root/snap_path"
assert 'exits 0 from an unrelated cwd' "[ '$rc' = 0 ]"
assert "it read the SCRIPT's neighbouring config, not the caller's" \
  "grep -q 'healthy-unit' \"\$(cat '$root/snap_path')\""
assert 'and none of this repo real unit names leaked in' \
  "! grep -q 'knowledge-digest' \"\$(cat '$root/snap_path')\""

echo "--- pre-snapshot: fail-soft — one dead command does not truncate the snapshot ---"
# `set -uo pipefail` with no `-e`, and every external call wrapped in run_or_note. The whole
# point is that a broken section costs one section. A snapshot that stopped at the first
# failure would hand the morning report a file that looks complete and ends early.
root=$(make_snap_fixture "$FIXTURE_TSV")
make_stubs "$root/stub" 1          # systemctl now exits 1 for every non-show call
rc=$(run_snap "$root")
assert 'exits 0 despite systemctl failing' "[ '$rc' = 0 ]"
assert 'the failure is recorded, not swallowed' \
  "grep -q '(command failed:' \"\$(cat '$root/snap_path')\""
assert 'and every later section is still present' \
  "grep -q '^## Box clock sanity' \"\$(cat '$root/snap_path')\" \
   && grep -q '^## Disk / system' \"\$(cat '$root/snap_path')\" \
   && grep -q '^## Alerts (last 10)' \"\$(cat '$root/snap_path')\""
assert 'a failing timedatectl is noted rather than left blank' \
  "section_of '$root' 'Box clock sanity' | grep -q '(command failed: timedatectl status)'"

echo "--- pre-snapshot: retired S3 surfaces stay retired ---"
# Gateway health and Kanban state were removed with the S3 retirement (D7, 2026-09-02). Both
# were wrapped in run_or_note, so reinstating them would not break anything — they would
# capture a dead surface every night and hand the morning report a diff of nothing, forever.
assert 'no Gateway health section' "! grep -q '^## Gateway health' \"\$(cat '$root/snap_path')\""
assert 'no Kanban state section' "! grep -q '^## Kanban state' \"\$(cat '$root/snap_path')\""

echo "--- pre-snapshot: the alerts tail is DATED, so a dead log cannot read as a live one ---"
# W17, FIXED 2026-09-03 (design/open-decisions.md). This group pinned the defect until then:
# `tail -10 ~/logs/agent-alert.log` with no clock renders an eight-day-dead alert log identically
# to a live one — presence is not freshness — and the consumer downstream is a morning report
# whose whole job is to say what is wrong. The section now prints
# `newest entry: <iso> (N days ago) — FRESH|STALE` above the tail, and a stale log carries an
# explicit instruction not to report its lines as current.
#
# THE ASSERTIONS KEY ON THE AGE, NOT ON A TIMESTAMP EXISTING, and the fixture is built to make
# that the only thing that can pass: its lines carry `failed at <ISO>Z` exactly as
# bin/agent_alert.sh:122 writes them. So "a date appears in the section" was TRUE of the broken
# code and is worthless as evidence — ten dated lines from eight days ago still read as last
# night's to an LLM skimming the artifact. What the fix adds, and what is asserted here, is the
# age in days plus a one-word verdict.
root=$(make_snap_fixture "$FIXTURE_TSV")
make_alert_log "$root" '8 days ago'
rc=$(run_snap "$root")
assert 'still exits 0 — the marker is inside a fail-soft section' "[ '$rc' = 0 ]"
assert 'the fixture is adversarial: the tail line already carries its own ISO stamp' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'failed at 2026-08-26T04:25:01Z'"
assert 'W17: the eight-day-old line is still reported' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'agent-workforce ALERT: unit qmd-refresh.service'"
assert 'W17: and the section states its AGE IN DAYS, not merely a timestamp' \
  "section_of '$root' 'Alerts (last 10)' | grep -qE 'newest entry: .*\\(8 days ago\\)'"
# The age has to be the LOG's, not the snapshot's. This file carries ISO stamps of its own in
# the header, so a marker that dated the run rather than the log would look identical in a grep
# for "a timestamp" — and would be exactly as blind as the bare tail.
alert_iso=$(date -d "@$(stat -c %Y "$root/home/logs/agent-alert.log")" -Is)
assert "W17: the timestamp is the LOG's mtime, not the snapshot's own clock" \
  "section_of '$root' 'Alerts (last 10)' | grep -qF '$alert_iso'"
assert 'W17: an eight-day-old log is labelled STALE in a word, not left to arithmetic' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'STALE'"
assert 'W17: and the consumer is told, in words, not to report those lines as current' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'do not report them as current'"

# The case the old fixture lacked. A marker hard-coded to say STALE would have passed every
# assertion above; only a fresh log can tell the two apart.
root=$(make_snap_fixture "$FIXTURE_TSV")
make_alert_log "$root" 'now'
rc=$(run_snap "$root")
assert 'W17: a log written today is labelled FRESH, with its age' \
  "section_of '$root' 'Alerts (last 10)' | grep -qE '\\(0 days ago\\) — FRESH'"
assert 'W17: and carries no STALE verdict' \
  "! section_of '$root' 'Alerts (last 10)' | grep -q 'STALE'"
assert 'W17: nor the do-not-report-as-current instruction, which would cry wolf every morning' \
  "! section_of '$root' 'Alerts (last 10)' | grep -q 'do not report them as current'"

# An unreadable mtime must degrade to a STATED unknown. A blank here would read as freshness,
# which is the defect being fixed, and a crash would truncate the last section of the snapshot.
root=$(make_snap_fixture "$FIXTURE_TSV")
make_alert_log "$root" '8 days ago'
printf '#!/usr/bin/env bash\nexit 1\n' > "$root/stub/stat"
chmod +x "$root/stub/stat"
rc=$(run_snap "$root")
assert 'W17: a failed stat still exits 0 (fail-soft, like every other section)' "[ '$rc' = 0 ]"
assert 'W17: and says UNKNOWN out loud rather than printing an undated tail' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'newest entry: UNKNOWN'"
assert 'W17: naming the age UNVERIFIED, so it cannot be read as fresh' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'UNVERIFIED'"
assert 'W17: the alerts themselves are still shown — unknown age, not withheld' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'agent-workforce ALERT: unit qmd-refresh.service'"

# Absence is distinguished from silence — the one thing this section always got right — and now
# so is emptiness, which the marker would otherwise render as a header over nothing.
root=$(make_snap_fixture "$FIXTURE_TSV")
rc=$(run_snap "$root")
assert 'a MISSING alert log says so, rather than rendering as an empty section' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'no agent-alert.log yet'"
root=$(make_snap_fixture "$FIXTURE_TSV")
: > "$root/home/logs/agent-alert.log"
rc=$(run_snap "$root")
assert 'a PRESENT but empty log says that instead of leaving a bare marker' \
  "section_of '$root' 'Alerts (last 10)' | grep -q 'the log exists but is empty'"

exit $fail
