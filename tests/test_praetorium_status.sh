#!/usr/bin/env bash
# bin/praetorium-status.sh — the box's most-read health view, and until now the largest
# script here with no suite of its own (W11).
#
# WHAT WAS AND WAS NOT ALREADY COVERED. tests/test_ops_view.sh looks like coverage and is
# not: it STUBS praetorium-status.sh with a one-line marker to prove ops-view.sh embeds
# *something*. tests/test_working_memory_status.sh does run the real script, but asserts one
# section (NUC-21 working memory) and nothing else — so that section is deliberately not
# re-asserted here.
#
# THE HIGHEST-VALUE THING THIS FILE PINS is the user-services block. Brief 5 replaced a
# two-unit whitelist with a `systemctl --user --failed` query and proved both branches BY
# HAND — a reachable bus prints the failed set or `none`, an unreachable bus prints `UNKNOWN`
# rather than a false `none`. This box has a recorded incident where a health section was a
# 4-item whitelist that never ran `--failed`, so an 8-day `failed` unit went unnamed twice a
# day: a check that cannot fail is not a check. A regression from `UNKNOWN` back to a
# confident `none` is what this suite exists to catch, and nothing else would notice it.
#
# Offline by contract. The script is copied into a fixture tree beside a fixture
# config/fleet-units.tsv (FLEET_UNITS is resolved from $0, which is what makes that possible
# and is asserted below), HOME is a scratch dir, and systemctl/curl/qmd/ss/tailscale/
# uptime/df/free/agent-browser are stubbed on PATH. Nothing here queries the live manager,
# opens a socket, reads a real credential file, or writes outside its own mktemp root.
#
# STDOUT AND STDERR ARE CAPTURED SEPARATELY, on purpose. The two FATALs this script can emit
# go to different streams (line 17 to stdout, fleet_or_die to stderr), and merging them would
# both hide that split and expose the assertions to stdio buffering order. bin/ops-view.sh
# merges with `2>&1`, so both reach the ops page; a human redirecting stdout alone does not.
#
# PROVEN RED, 2026-09-04, by reverting bin/praetorium-status.sh in the working tree one
# regression at a time and restoring it with `git checkout --` (the script itself is NOT
# changed by this branch — it is deployed, and editing it would make the drift check red):
#   1. `|| true` on the --failed assignment, dropping the rc  -> 4 assertions red, and ONLY
#      the unreachable-bus ones; the failed-set and `none` branches stayed green, which is
#      what makes them a control rather than three restatements of one fact.
#   2. the two-unit whitelist this block replaced             -> 10 red, including the one
#      that names a failed unit no list declares.
#   3. `NF>=4` and the kind filter dropped from fleet_units   -> 8 red, across the kind
#      filter and all three empty-list refusals.
#   4. the inbox UNKNOWN branch reporting the disk count      -> 2 red.
#   5. the OpenRouter key echoed into its own error line      -> 1 red (the leak assertion).
#   6. `head -30` widened to `head -100`                      -> 2 red, so the truncation
#      characterization tracks the actual bound and is not a restatement of the fixture.
# Restored after each; the suite is green against the real file and stayed deterministic
# across four consecutive runs.
#
# REGISTRATION (D6 coverage join): deliberately left UNCLAIMED, like tests/test_ops_view.sh
# next door. `no-orphan-suite` reports an unclaimed suite only when its subject is exec'd
# solely by an ARCHIVED unit; praetorium-status.sh is exec'd by no unit at all — it is a CLI
# Dave runs and ops-view.sh shells out to — so it can never be an orphan and the gate stays
# green (measured 2026-09-04: 20 of 51 unclaimed, 0 orphaned). Registering it in
# design/fleet-suites.toml would mean inventing a third `owner` value for a suite that is
# neither fleet state nor a retired tool, and that file's structure is asserted by
# tests/test_fleet_guards.sh, which skips off the box — so the entry would go unasserted on
# every CI run. An unclaimed suite with a live subject is the honest record.
set -euo pipefail

# shellcheck source=tests/rhythm_test_lib.sh
. "$(dirname "$0")/rhythm_test_lib.sh"

# Deterministic canary for the pipefail/SIGPIPE regression in the shared assert(): `yes` is
# still writing when `grep -q` exits, so this fails if and only if a condition is evaluated
# under pipefail. It lives in every caller because the assert it guards is shared.
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

STATUS="$REPO_ROOT/bin/praetorium-status.sh"

# Fixture unit list. Deliberately NOT a copy of the real one: one row of each shape the
# script must treat differently, including a kind=service row with no timer at all and two
# rows whose `status` must keep them out of every section.
tsv_row() { printf '%s\t%s\t%s\t%s\t%s\n' "$@"; }
FIXTURE_TSV=$(
  echo '# fixture'
  tsv_row alpha-unit      system standing trajan   timer
  tsv_row beta-unit       system standing claudius timer
  tsv_row gamma-unit      system standing marcus   timer
  tsv_row usertimer-unit  user   standing trajan   timer
  tsv_row buzz-agent@marcus user standing marcus   service
  tsv_row campaign-unit   system campaign augustus timer
  tsv_row dormant-unit    system dormant  claudius timer
)

# ── Stubs ───────────────────────────────────────────────────────────────────────────────
# The systemctl stub records every invocation WITH the XDG_RUNTIME_DIR it saw, and answers
# from mode files so each branch can be driven deliberately rather than hoped for.
make_stubs() { # dir
  local dir=$1
  cat > "$dir/systemctl" <<EOF
#!/usr/bin/env bash
printf 'xdg=%s argv=%s\n' "\${XDG_RUNTIME_DIR:-UNSET}" "\$*" >> "$dir/calls.log"
mode() { cat "$dir/mode.\$1" 2>/dev/null || echo "\$2"; }
rows() {  # one list-timers row per non-flag argument, so a dropped unit is visible
  echo "NEXT                         LEFT      LAST PASSED UNIT ACTIVATES"
  for a in "\$@"; do
    case "\$a" in --*) ;; *) echo "Thu 2026-09-04 04:30:00 CEST 1h left n/a n/a \$a stub.service" ;; esac
  done
}
if [ "\${1:-}" = --user ]; then
  if [ "\$(mode userbus up)" != up ]; then
    echo "Failed to connect to bus: No such file or directory" >&2
    exit 1
  fi
  shift
  case "\${1:-}" in
    --failed)
      if [ "\$(mode failed clean)" = failed ]; then cat "$dir/failed-units.txt"; fi
      exit 0 ;;
    is-active) echo active; exit 0 ;;
    list-timers)
      shift
      rows "\$@"
      # More than the pipe buffer holds, so a downstream \`head -10\` closes the pipe while
      # this is still writing. The status of the flood is this stub's OWN exit status — a
      # trailing \`exit 0\` here would hide the SIGPIPE that real systemctl would die of, and
      # the characterization group below would silently assert nothing.
      if [ "\$(mode usertimerflood no)" = yes ]; then
        seq 1 200000 | sed 's/^/flood-timer-/'
      fi
      exit \$? ;;
  esac
  exit 0
fi
if [ "\$(mode sysbus up)" != up ]; then exit 1; fi
case "\${1:-}" in
  is-active)  echo active;  exit 0 ;;
  is-enabled) echo enabled; exit 0 ;;
  list-timers) shift; rows "\$@"; exit 0 ;;
esac
exit 0
EOF
  # Created empty, not on first call. `! grep -q X missing_file` is TRUE and `grep -c` on a
  # missing path returns a clean 0 — so a fixture that never invoked the stub would satisfy
  # every "systemctl is never reached" assertion below without proving anything. Every
  # absence assertion in this file additionally proves its subject exists first.
  : > "$dir/calls.log"
  : > "$dir/curl.log"

  cat > "$dir/curl" <<EOF
#!/usr/bin/env bash
printf 'curl argv=%s\n' "\$*" >> "$dir/curl.log"
case "\$*" in
  *8765/health*)
    if [ "\$(cat "$dir/mode.qmdhealth" 2>/dev/null || echo down)" = up ]; then exit 0; fi
    exit 22 ;;
esac
# The OpenRouter key endpoint always fails, so no fixture can perform a real GET.
exit 7
EOF

  cat > "$dir/qmd" <<EOF
#!/usr/bin/env bash
if [ "\$(cat "$dir/mode.qmd" 2>/dev/null || echo ok)" != ok ]; then exit 1; fi
echo "QMD-INDEX-MARKER: 498 documents"
exit 0
EOF

  # The matching line comes FIRST so `| grep -q ':8766'` exits on it, then the flood keeps
  # writing into a closed pipe. No trailing `exit 0`: the `if` is the last command, so its
  # status IS the stub's, which is how a real ss dying of SIGPIPE behaves and the only way
  # the characterization below can observe anything.
  cat > "$dir/ss" <<EOF
#!/usr/bin/env bash
echo "LISTEN 0 511 127.0.0.1:8766 0.0.0.0:*"
if [ "\$(cat "$dir/mode.ssflood" 2>/dev/null || echo no)" = yes ]; then
  seq 1 200000 | sed 's/^/LISTEN 0 128 10.0.0.1:/'
fi
EOF

  printf '#!/usr/bin/env bash\necho "100.0.0.1 stub-node TAILSCALE-MARKER linux -"\n' > "$dir/tailscale"
  printf '#!/usr/bin/env bash\necho " 12:00:00 up 1 day, 0 users, load average: 0.00, 0.00, 0.00"\n' > "$dir/uptime"
  printf '#!/usr/bin/env bash\necho "Filesystem Size Used Avail Use%% Mounted"\necho "/dev/sda1 20G 5G 15G 25%% /"\n' > "$dir/df"
  printf '#!/usr/bin/env bash\necho "        total used free"\necho "Mem: 31Gi 4Gi 27Gi"\n' > "$dir/free"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$dir/agent-browser"
  chmod +x "$dir"/*
}

# tsv-content -> fixture root with ./bin/praetorium-status.sh, ./config/fleet-units.tsv,
# ./stub (on PATH) and ./home (as HOME).
make_fixture() {
  local tsv=$1 root
  root=$(mktemp -d)
  mkdir -p "$root/bin" "$root/config" "$root/stub" "$root/home"
  cp "$STATUS" "$root/bin/praetorium-status.sh"
  printf '%s\n' "$tsv" > "$root/config/fleet-units.tsv"
  make_stubs "$root/stub"
  echo "$root"
}

# XDG_RUNTIME_DIR is unset for a different reason than the two keys: the script SETS it before
# every `systemctl --user` call (a system unit has no session bus), and leaving the caller's
# value in place makes that assertion measure the operator's shell instead of the script.
# Proven 2026-09-04: with it inherited, deleting all three assignments from the production
# script left this suite 92/92 green. A check that cannot fail is not a check.
# BRAVE_API_KEY and OPENROUTER_API_KEY are unset per run so an operator's own environment can
# never decide a branch; AGENT_BROWSER_EXECUTABLE_PATH points into the stub dir so the fetch
# section is the same on this box (no system chrome) and on a runner image (which ships one).
run_status() { # root [cwd] -> rc; stdout in $root/out.log, stderr in $root/err.log
  local root=$1 cwd=${2:-$root} rc=0
  ( cd "$cwd" && env -u BRAVE_API_KEY -u OPENROUTER_API_KEY -u LLM_BASE_URL -u XDG_RUNTIME_DIR \
      HOME="$root/home" PATH="$root/stub:$PATH" \
      AGENT_BROWSER_EXECUTABLE_PATH="$root/stub/agent-browser" \
      bash "$root/bin/praetorium-status.sh" ) > "$root/out.log" 2> "$root/err.log" || rc=$?
  echo "$rc"
}

# Body of one `── Section` heading, exclusive of the next — so an assertion about the failed
# units cannot be satisfied by text that happens to appear three sections away. index() is a
# plain string match, not a regex, because the heading rule is a multibyte literal.
section_of() { # root, exact-heading-text
  awk -v h="── $2" -v hp="── " '$0==h{f=1;next} index($0,hp)==1{f=0} f' "$1/out.log"
}

# ── Group 1: the failed-units block, all three branches ──────────────────────────────────
echo "--- praetorium-status: a reachable user bus prints the FAILED SET, by query not by list ---"
# The whitelist this replaced could only ever report units someone had thought to add.
# ghost-unit.service is in NO manifest and NO fixture list — if it is named, the block is
# genuinely asking the manager what is wrong rather than asking a list whether it is fine.
root=$(make_fixture "$FIXTURE_TSV")
echo failed > "$root/stub/mode.failed"
printf '%s\n' \
  '● buzz-agent@marcus.service loaded failed failed Buzz agent (marcus)' \
  '● ghost-unit.service        loaded failed failed A unit no manifest declares' \
  > "$root/stub/failed-units.txt"
rc=$(run_status "$root")
section_of "$root" 'User services (failed units)' > "$root/failed.txt"
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the block really asked the user manager for --failed' \
  "grep -q 'argv=--user --failed' '$root/stub/calls.log'"
assert 'the failed section is present and non-empty' "[ -s '$root/failed.txt' ]"
assert 'a declared failed unit is named' "grep -q 'buzz-agent@marcus.service' '$root/failed.txt'"
assert 'and so is one NO list declares — the whitelist defect cannot recur' \
  "grep -q 'ghost-unit.service' '$root/failed.txt'"
assert 'the section never says none while units are failing' \
  "! grep -qx '  none' '$root/failed.txt'"
assert 'nor UNKNOWN — the bus was reachable' "! grep -q 'UNKNOWN' '$root/failed.txt'"

echo "--- praetorium-status: a reachable bus with nothing failed says none, and only none ---"
# The control that makes the branch above evidence rather than a coincidence: a block
# hard-wired to print whatever the stub emits would pass that group and fail this one.
root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
section_of "$root" 'User services (failed units)' > "$root/failed.txt"
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the block still asked --failed (the query ran; there was nothing to report)' \
  "grep -q 'argv=--user --failed' '$root/stub/calls.log'"
assert 'the section is exactly the one word none' "[ \"\$(cat '$root/failed.txt')\" = '  none' ]"
assert 'and carries no UNKNOWN' "! grep -q 'UNKNOWN' '$root/failed.txt'"

echo "--- praetorium-status: an UNREACHABLE user bus says UNKNOWN, never none ---"
# THE REGRESSION THIS SUITE EXISTS FOR. `|| true` on the assignment alone would print "none"
# when the bus is down, which is the same false green the whitelist produced. The rc has to
# survive, and the wording has to say out loud that this is not "nothing failed".
root=$(make_fixture "$FIXTURE_TSV")
echo down > "$root/stub/mode.userbus"
rc=$(run_status "$root")
section_of "$root" 'User services (failed units)' > "$root/failed.txt"
assert 'exits 0 — one dead manager does not abort the report' "[ '$rc' = 0 ]"
assert 'the stub WAS reached, so the absence below has a subject' \
  "grep -q 'argv=--user --failed' '$root/stub/calls.log'"
assert 'the section is present and non-empty' "[ -s '$root/failed.txt' ]"
assert 'it says UNKNOWN' "grep -q 'UNKNOWN' '$root/failed.txt'"
assert 'it names the rc, so the reader can tell a dead bus from a dead unit' \
  "grep -q 'rc=1' '$root/failed.txt'"
assert "it says in words that this is not 'nothing failed'" \
  "grep -qF \"this is not 'nothing failed'\" '$root/failed.txt'"
assert 'and the word none appears NOWHERE in it' "! grep -q 'none' '$root/failed.txt'"
# The two neighbouring user-scope sections read the same dead bus and must not go quiet
# either — a live agent reported as absent is the same failure in the other direction.
assert 'the user-timer section says it could not reach the manager' \
  "section_of '$root' 'User timers (scope=user, next runs)' | grep -q 'could not reach the user manager'"
assert 'and the kind=service section reports UNKNOWN state, not a blank' \
  "section_of '$root' 'User services (scope=user, kind=service — always-on)' | grep -qE 'buzz-agent@marcus\\.service +active=UNKNOWN'"

# ── Group 2: the list is a filter, not six hand-written lists ────────────────────────────
echo "--- praetorium-status: scope and kind are honoured; status excludes what it should ---"
root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'the system timer query names exactly the three standing system timers, in list order' \
  "grep -qF 'argv=list-timers alpha-unit.timer beta-unit.timer gamma-unit.timer --no-pager' '$root/stub/calls.log'"
assert 'the user-scope query is separate and names only the user timer' \
  "grep -qF 'argv=--user list-timers usertimer-unit.timer --no-pager' '$root/stub/calls.log'"
# The five buzz-agent@* rows are Type=simple services. Appending ".timer" asks the manager for
# a unit that does not exist, and list-timers answers by SILENTLY DROPPING the name — rc=0,
# empty stderr — so a live, healthy agent renders as one that has never fired.
assert 'the kind=service row is asked for with is-active instead' \
  "grep -q 'argv=--user is-active buzz-agent@marcus.service' '$root/stub/calls.log'"
assert 'and buzz-agent@marcus.timer, which does not exist, is never requested' \
  "[ -s '$root/stub/calls.log' ] && ! grep -q 'buzz-agent@marcus.timer' '$root/stub/calls.log'"
assert 'campaign and dormant rows are asked about nowhere' \
  "[ -s '$root/stub/calls.log' ] && ! grep -qE 'campaign-unit|dormant-unit' '$root/stub/calls.log'"
assert 'and appear in no section of the report' \
  "[ -s '$root/out.log' ] && ! grep -qE 'campaign-unit|dormant-unit' '$root/out.log'"
# Every --user call carries XDG_RUNTIME_DIR: praetorium-status is also read through
# ops-view.sh, and a bare `systemctl --user` with no session bus exits 1 and renders the whole
# user half as empty rather than as broken.
assert 'every --user call carries XDG_RUNTIME_DIR (no session bus under a system unit)' \
  "grep -q 'argv=--user ' '$root/stub/calls.log' \
   && ! grep 'argv=--user ' '$root/stub/calls.log' | grep -q 'xdg=UNSET'"
assert 'the Services section reports the two MCP daemons AND the derived timers' \
  "section_of '$root' 'Services' | grep -q 'qmd-mcp.service' \
   && section_of '$root' 'Services' | grep -qE 'alpha-unit\\.timer +active=active'"
assert 'the report runs to its last section — nothing exits early' \
  "grep -qF 'Log inspection: journalctl -u qmd-mcp' '$root/out.log' \
   && grep -qx '── Tailscale' '$root/out.log' \
   && grep -qx '── Overnight logs (NUC-36)' '$root/out.log'"

# ── Group 3: an empty derived list refuses instead of reporting ──────────────────────────
echo "--- praetorium-status: a 4-column list REFUSES rather than listing every timer on the box ---"
# `NF>=5` matches nothing against a 4-column (pre-2026-09-03) copy of the list — which is what
# ~/agent-workforce/config/ still holds until bin/deploy runs — and `systemctl list-timers`
# with an EMPTY argument array lists every timer on the box (44, measured 2026-09-03). So the
# failure mode of a stale list is a full-looking report derived from nothing, which is
# strictly worse than the glob it replaced.
four_col=$(printf '%s\n' "$FIXTURE_TSV" | awk -F'\t' 'BEGIN{OFS="\t"} !/^#/ && NF>=5 {print $1,$2,$3,$4}')
root4=$(make_fixture "$four_col")
rc=$(run_status "$root4")
assert 'still exits 0 (fail-soft per section, by design — no set -e)' "[ '$rc' = 0 ]"
assert 'the FATAL names the file and the scope/kind that came back empty' \
  "grep -q 'FATAL: .*fleet-units.tsv declares no system/timer units' '$root4/err.log'"
assert 'and says coverage is UNKNOWN, not none' \
  "grep -qF \"Unit coverage is UNKNOWN, not 'none'\" '$root4/err.log'"
assert 'the timers section says UNKNOWN, never no timers' \
  "section_of '$root4' 'Timers (next runs)' | grep -qF \"NOT 'no timers'\""
assert 'the user-timer section refuses independently' \
  "section_of '$root4' 'User timers (scope=user, next runs)' | grep -qF \"NOT 'none declared'\""
assert 'so does the kind=service section' \
  "section_of '$root4' 'User services (scope=user, kind=service — always-on)' | grep -qF \"NOT 'none declared'\""
assert 'list-timers is NEVER called, so no 44-timer listing can be produced' \
  "[ -f '$root4/stub/calls.log' ] && ! grep -q 'list-timers' '$root4/stub/calls.log'"
# CHARACTERIZATION, not an endorsement (see defects note in the header of this group).
# fleet_or_die writes to stderr while the missing-file FATAL on line 17 writes to stdout, and
# the Services section's `while read` loop simply produces nothing. bin/ops-view.sh merges
# both streams so the ops page is fine; `praetorium-status.sh > report.txt` is not — that file
# gets a Services section holding two daemons and no refusal at all.
assert 'CHARACTERIZATION: on stdout alone the Services section carries no refusal marker' \
  "[ -s '$root4/out.log' ] && section_of '$root4' 'Services' | grep -q 'qmd-mcp.service' \
   && ! section_of '$root4' 'Services' | grep -qE 'FATAL|UNKNOWN'"

rootE=$(make_fixture "")
rc=$(run_status "$rootE")
assert 'an empty list file refuses the same way (missing rows and no rows are one failure)' \
  "[ '$rc' = 0 ] && grep -q 'FATAL' '$rootE/err.log' \
   && [ -f '$rootE/stub/calls.log' ] && ! grep -q 'list-timers' '$rootE/stub/calls.log'"

echo "--- praetorium-status: an unreadable unit list is fatal, and stops the run ---"
# The one place this script exits non-zero. A missing list must not render as a clean short
# report — that is the whitelist defect in its worst form, where the check reports nothing
# wrong because it checked nothing.
rootM=$(make_fixture "$FIXTURE_TSV")
rm -f "$rootM/config/fleet-units.tsv"
rc=$(run_status "$rootM")
assert 'exits 1' "[ '$rc' = 1 ]"
assert 'and says FATAL, naming the path it could not read' \
  "grep -q 'FATAL: cannot read .*fleet-units.tsv' '$rootM/out.log'"
assert "saying coverage is unknown, not 'fine'" \
  "grep -qF \"unit coverage unknown, not 'fine'\" '$rootM/out.log'"
assert 'no section is rendered at all — a truncated report cannot read as a complete one' \
  "[ -s '$rootM/out.log' ] && ! grep -q '^── ' '$rootM/out.log'"
assert 'and systemctl is never reached' \
  "[ -f '$rootM/stub/calls.log' ] && [ ! -s '$rootM/stub/calls.log' ]"

echo "--- praetorium-status: FLEET_UNITS is script-relative, not cwd-relative ---"
# `$(dirname "$0")/../config/fleet-units.tsv` is what lets one script work from the repo and
# from ~/agent-workforce/ alike. design/ is not deployed, so reading the manifests at run time
# would work here and empty silently in the tree systemd actually execs. Proven by running
# from an unrelated cwd and checking that the FIXTURE's units, not this repo's, came out.
root=$(make_fixture "$FIXTURE_TSV")
elsewhere=$(mktemp -d)
rc=$(run_status "$root" "$elsewhere")
assert 'exits 0 from an unrelated cwd' "[ '$rc' = 0 ]"
assert "it read the SCRIPT's neighbouring config, not the caller's" \
  "grep -q 'alpha-unit' '$root/out.log'"
assert "and none of this repo's real unit names leaked in" \
  "[ -s '$root/out.log' ] && ! grep -qE 'knowledge-digest|overnight-pre-snapshot' '$root/out.log'"

# ── Group 4: the inbox backlog — UNKNOWN is not zero ─────────────────────────────────────
echo "--- praetorium-status: an unavailable pending count is UNKNOWN, never 0 ---"
# NUC-26/45. The pending figure comes from agent_inbox_notion_sync.py --count, which knows the
# Notion Status per file; the raw disk count overstates the backlog by however many files are
# already decided but not yet cleared (40 on disk vs 25 pending, 2026-08-10). When the helper
# cannot run — no token, no network, not deployed — a confident "0 pending" would tell Dave
# the approval queue is clear on a morning when it is not.
mk_inbox() { # root, n-files
  local root=$1 n=$2 i
  mkdir -p "$root/home/agent-worktrees/inbox/_inbox/agents"
  for ((i = 1; i <= n; i++)); do
    printf 'proposal\n' > "$root/home/agent-worktrees/inbox/_inbox/agents/2026-09-0${i}_x.md"
  done
}
mk_count_helper() { # root, body...
  local root=$1; shift
  mkdir -p "$root/home/agent-workforce/bin"
  printf '%s\n' "$@" > "$root/home/agent-workforce/bin/agent_inbox_notion_sync.py"
}
root=$(make_fixture "$FIXTURE_TSV")
mk_inbox "$root" 3          # helper deliberately absent
rc=$(run_status "$root")
section_of "$root" 'Agent inbox backlog (pending proposals, NUC-26/45)' > "$root/inbox.txt"
assert 'the section is present and non-empty' "[ -s '$root/inbox.txt' ]"
assert 'pending is UNKNOWN and says why' "grep -q 'pending  : UNKNOWN' '$root/inbox.txt'"
assert 'it is never reported as a clear queue' "! grep -q 'pending  : 0' '$root/inbox.txt'"
assert 'the raw disk count is still offered, labelled raw' \
  "grep -q 'on disk  : 3 files (raw count' '$root/inbox.txt'"

root=$(make_fixture "$FIXTURE_TSV")
mk_inbox "$root" 5
# The date is computed here, not written literally: the assertion below is about the AGE the
# script derives, and a fixed date would drift into a different number of days every morning.
mk_count_helper "$root" 'print("PENDING_COUNT=2")' \
  "print(\"OLDEST_PENDING_DATE=$(date -d '5 days ago' +%F)\")"
rc=$(run_status "$root")
section_of "$root" 'Agent inbox backlog (pending proposals, NUC-26/45)' > "$root/inbox.txt"
assert 'a Notion-verified count is reported as pending' \
  "grep -q 'pending  : 2 awaiting Mac-side promote/reject' '$root/inbox.txt'"
assert 'with the oldest proposal aged in days, not merely dated' \
  "grep -qE 'oldest   : [0-9]{4}-[0-9]{2}-[0-9]{2} \\(5d old\\)' '$root/inbox.txt'"
assert 'and the disk surplus is shown as already-decided, never as backlog' \
  "grep -q 'on disk  : 5 files (3 already decided in Notion, not yet cleared)' '$root/inbox.txt'"

root=$(make_fixture "$FIXTURE_TSV")
mk_inbox "$root" 4
mk_count_helper "$root" 'print("PENDING_COUNT=0")' 'print("OLDEST_PENDING_DATE=none")'
rc=$(run_status "$root")
section_of "$root" 'Agent inbox backlog (pending proposals, NUC-26/45)' > "$root/inbox.txt"
assert 'a genuinely clear queue says 0, Notion-verified — the control for UNKNOWN above' \
  "grep -q 'pending  : 0 (inbox clear, Notion-verified)' '$root/inbox.txt'"
assert 'and four undecided-looking files on disk do not become a phantom backlog' \
  "grep -q 'on disk  : 4 files (4 already decided' '$root/inbox.txt'"

# CHARACTERIZATION of a real defect, NOT a fix (bin/praetorium-status.sh:236). W11 is
# test-authoring, so the behaviour is pinned rather than repaired.
# `oldest_secs=$(date -d "$oldest_date" +%s 2>/dev/null || echo "$now_secs")` swallows an
# unparseable date into *today*, so a garbled OLDEST_PENDING_DATE renders as `(0d old)` — the
# most reassuring possible age — for a queue whose true age is unknown. Same class as the
# readiness-report phantom-blocker family: a number that is exact and means nothing.
root=$(make_fixture "$FIXTURE_TSV")
mk_inbox "$root" 3
mk_count_helper "$root" 'print("PENDING_COUNT=3")' 'print("OLDEST_PENDING_DATE=not-a-date")'
rc=$(run_status "$root")
section_of "$root" 'Agent inbox backlog (pending proposals, NUC-26/45)' > "$root/inbox.txt"
assert 'CHARACTERIZATION: an unparseable oldest date is reported as 0 days old, not UNKNOWN' \
  "grep -qF 'oldest   : not-a-date (0d old)' '$root/inbox.txt'"

root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'a missing inbox worktree says so, naming the path it looked for' \
  "section_of '$root' 'Agent inbox backlog (pending proposals, NUC-26/45)' \
     | grep -q 'inbox worktree not present'"

# ── Group 5: credentials are read, used, and never printed ───────────────────────────────
echo "--- praetorium-status: it reports that a key is set without ever printing the key ---"
# Both key probes exist to answer "is it configured", and both read a file whose whole
# contents are secret. The OpenRouter block runs in a SUBSHELL for exactly this reason. These
# assertions prove the value reached curl's argv (so the probe is real) and never reached the
# report (so the report is safe to paste into Notion via ops-view.sh --publish).
root=$(make_fixture "$FIXTURE_TSV")
mkdir -p "$root/home/.hermes" "$root/home/.config/agent-workforce"
printf 'BRAVE_API_KEY=BSA-FIXTURE-BRAVE-SECRET\n' > "$root/home/.hermes/.env"
printf 'OPENROUTER_API_KEY="sk-or-FIXTURE-OPENROUTER-SECRET"\n' > "$root/home/.config/agent-workforce/secrets.env"
rc=$(run_status "$root")
assert 'the fixture really carries both secrets (the absence proofs below need a subject)' \
  "grep -q 'BSA-FIXTURE-BRAVE-SECRET' '$root/home/.hermes/.env' \
   && grep -q 'sk-or-FIXTURE-OPENROUTER-SECRET' '$root/home/.config/agent-workforce/secrets.env'"
assert 'Brave reports key: set' \
  "section_of '$root' 'Research MCP (Brave)' | grep -q 'key      : set'"
assert 'the OpenRouter key was genuinely read and handed to curl' \
  "grep -q 'sk-or-FIXTURE-OPENROUTER-SECRET' '$root/stub/curl.log'"
assert 'the unreachable key endpoint degrades to a note, not a crash' \
  "section_of '$root' 'OpenRouter budget (NUC-27)' | grep -q 'key endpoint unreachable'"
assert 'and NEITHER secret appears anywhere in the report or on stderr' \
  "[ -s '$root/out.log' ] \
   && ! grep -qE 'BSA-FIXTURE-BRAVE-SECRET|sk-or-FIXTURE-OPENROUTER-SECRET' '$root/out.log' '$root/err.log'"

root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'with no key file at all, Brave says MISSING rather than leaving a blank' \
  "section_of '$root' 'Research MCP (Brave)' | grep -q 'key      : MISSING'"
assert 'and OpenRouter says the budget cannot be checked, rather than reporting one' \
  "section_of '$root' 'OpenRouter budget (NUC-27)' | grep -qF 'key: MISSING — cannot check budget'"

# ── Group 6: the reachability probes, both directions ────────────────────────────────────
echo "--- praetorium-status: the qmd MCP probe distinguishes reachable from unreachable ---"
# A probe that reported "reachable" unconditionally would satisfy either case alone, so both
# are asserted. The daemon is the transport every agent's vault retrieval runs over.
root=$(make_fixture "$FIXTURE_TSV")
echo up > "$root/stub/mode.qmdhealth"
rc=$(run_status "$root")
assert 'a healthy health endpoint reports reachable' \
  "section_of '$root' 'qmd MCP daemon (agent transport, NUC-16)' | grep -qF 'endpoint : http://127.0.0.1:8765/mcp (reachable)'"
root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'a failing one reports unreachable, not a blank' \
  "section_of '$root' 'qmd MCP daemon (agent transport, NUC-16)' | grep -qF '(unreachable)'"
assert 'with no claudius profile on disk the qmd wiring is unknown, not assumed healthy' \
  "section_of '$root' 'qmd MCP daemon (agent transport, NUC-16)' | grep -q 'claudius qmd = unknown'"

echo "--- praetorium-status: a cold-spawn qmd profile is named as the NUC-16 regression ---"
root=$(make_fixture "$FIXTURE_TSV")
mkdir -p "$root/home/.hermes/profiles/claudius"
printf 'mcp:\n  qmd:\n    command: qmd\n    args: [mcp]\n  other:\n    url: x\n' \
  > "$root/home/.hermes/profiles/claudius/config.yaml"
rc=$(run_status "$root")
assert 'a command: entry under qmd is called out as the regression it is' \
  "section_of '$root' 'qmd MCP daemon (agent transport, NUC-16)' | grep -qF 'cold-spawn (stdio) — NUC-16 regression'"
root=$(make_fixture "$FIXTURE_TSV")
mkdir -p "$root/home/.hermes/profiles/claudius"
printf 'mcp:\n  qmd:\n    url: http://127.0.0.1:8765/mcp\n' \
  > "$root/home/.hermes/profiles/claudius/config.yaml"
rc=$(run_status "$root")
assert 'and a url: entry reads as the wired daemon — the control for the line above' \
  "section_of '$root' 'qmd MCP daemon (agent transport, NUC-16)' | grep -qF 'claudius qmd = daemon (http)'"

echo "--- praetorium-status: a broken qmd CLI degrades to the build hint, not to silence ---"
root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'a working index is shown' \
  "section_of '$root' 'qmd index' | grep -q 'QMD-INDEX-MARKER'"
root=$(make_fixture "$FIXTURE_TSV")
echo broken > "$root/stub/mode.qmd"
rc=$(run_status "$root")
assert 'a failing one says the index is not built, naming the tool that builds it' \
  "section_of '$root' 'qmd index' | grep -q 'qmd index not built yet (finish_boxsafe_clone.sh)'"

echo "--- praetorium-status: the vault clone and the run logs distinguish absence from silence ---"
root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'an uncloned vault says so rather than printing an empty line' \
  "section_of '$root' 'Vault clone' | grep -q 'not cloned yet (deploy key gate)'"
assert 'no agent_propose.log yet reads as no runs, not as a clean run' \
  "section_of '$root' 'Last agent runs' | grep -q 'no runs yet'"
assert 'and no cost.log reads as no entries' \
  "section_of '$root' 'Cost log' | grep -q 'no cost entries yet'"
assert 'the fetch backend honours AGENT_BROWSER_EXECUTABLE_PATH' \
  "section_of '$root' 'Fetch backend (browser, NUC-22)' | grep -q 'chromium: installed'"

# ── Group 7: characterizations of defects found while writing this suite ─────────────────
echo "--- praetorium-status: CHARACTERIZATION — pipefail + an early-exiting reader ---"
# bin/praetorium-status.sh:153 is `if ss -ltn 2>/dev/null | grep -q ':8766'; then` under
# `set -uo pipefail`, which CLAUDE.md's Verification section forbids in as many words: grep -q
# exits on its first match, ss dies of SIGPIPE, the pipeline reports 141, and a pattern that
# WAS found is read as not found. Measured 2026-09-04: with ss output under the pipe buffer
# the check is correct; past it, a listening :8766 is reported `down`, deterministically,
# three runs out of three. Today's box has ~20 listeners so it never fires — this is a latent
# inverter, pinned here so a future box (or a busier one) does not discover it as an outage.
# The same shape sits at :79 (`--user list-timers | head -10 || echo UNKNOWN`) and :126
# (`qmd status | head -8 || echo not built`); the first is pinned below, and one fix covers
# all three. NOT repaired here: W11 is test-authoring and bin/ is deployed.
root=$(make_fixture "$FIXTURE_TSV")
rc=$(run_status "$root")
assert 'a small ss listing reports the Brave endpoint up (the correct case)' \
  "section_of '$root' 'Research MCP (Brave)' | grep -qF 'endpoint : up (127.0.0.1:8766/mcp)'"
root=$(make_fixture "$FIXTURE_TSV")
echo yes > "$root/stub/mode.ssflood"
rc=$(run_status "$root")
assert 'CHARACTERIZATION: past the pipe buffer the SAME listening port reports down' \
  "section_of '$root' 'Research MCP (Brave)' | grep -qF 'endpoint : down (127.0.0.1:8766/mcp)'"

root=$(make_fixture "$FIXTURE_TSV")
echo yes > "$root/stub/mode.usertimerflood"
rc=$(run_status "$root")
section_of "$root" 'User timers (scope=user, next runs)' > "$root/usertimers.txt"
assert 'the user-timer listing is still rendered' \
  "grep -q 'usertimer-unit.timer' '$root/usertimers.txt'"
assert 'CHARACTERIZATION: and is contradicted by a spurious could-not-reach note beneath it' \
  "grep -q 'UNKNOWN — could not reach the user manager' '$root/usertimers.txt'"

echo "--- praetorium-status: CHARACTERIZATION — the timers section is a bounded window ---"
# bin/praetorium-status.sh:67 ends `| head -30`, and the section states no boundary. Today
# that is 22 standing system timers plus one header line — seven rows of headroom — but W3
# made this list a projection of design/agents/*.toml, so it grows whenever a persona gains a
# job, and the 30th unit is the last one anyone will ever see. The Services loop above has no
# cap, so the same unit appears there and vanishes here: the report contradicts itself rather
# than truncating visibly. A bounded window must state its boundary; this one does not.
many=$(
  echo '# fixture: more standing system timers than the section is willing to print'
  for i in $(seq -w 1 35); do tsv_row "many-$i" system standing trajan timer; done
  tsv_row usertimer-unit    user standing trajan timer
  tsv_row buzz-agent@marcus user standing marcus service
)
root=$(make_fixture "$many")
rc=$(run_status "$root")
section_of "$root" 'Timers (next runs)' > "$root/timers.txt"
assert 'exits 0' "[ '$rc' = 0 ]"
assert 'all 35 timers WERE requested — the loss is downstream of the query' \
  "grep -qF 'many-35.timer' '$root/stub/calls.log'"
assert 'and all 35 are listed in the Services section, which has no cap' \
  "section_of '$root' 'Services' | grep -qF 'many-35.timer'"
assert 'the section is present and non-empty' "[ -s '$root/timers.txt' ]"
assert 'the early timers are shown' "grep -qF 'many-01.timer' '$root/timers.txt'"
assert 'CHARACTERIZATION: the 35th is silently absent, contradicting Services above' \
  "! grep -qF 'many-35.timer' '$root/timers.txt'"
assert 'CHARACTERIZATION: the window is exactly 30 lines and says so nowhere' \
  "[ \"\$(grep -c . '$root/timers.txt')\" = 30 ] \
   && ! grep -qiE 'truncat|more units|not shown' '$root/timers.txt'"

echo "--- praetorium-status: CHARACTERIZATION — a dead system manager renders as blanks ---"
# The kind=service block defaults its state to UNKNOWN (`${st:-UNKNOWN}`); the older Services
# loop above it does not. So when the system manager cannot answer, every Services row prints
# `active=` with nothing after it, and the Timers section renders as a bare heading over
# nothing — which reads as "no timers scheduled" to anyone skimming. Same family as the
# whitelist incident: the report says nothing is wrong because it learned nothing.
root=$(make_fixture "$FIXTURE_TSV")
echo down > "$root/stub/mode.sysbus"
rc=$(run_status "$root")
assert 'exits 0 — a dead system manager is still a fail-soft section' "[ '$rc' = 0 ]"
assert 'the stub was reached, so the blanks below are the script and not an empty fixture' \
  "grep -q 'argv=is-active qmd-mcp.service' '$root/stub/calls.log'"
assert 'CHARACTERIZATION: the Services rows print an empty state rather than UNKNOWN' \
  "section_of '$root' 'Services' | grep -qE '^  qmd-mcp\\.service +active= +enabled=\$'"
assert 'CHARACTERIZATION: and the Timers section is an empty heading, not a stated UNKNOWN' \
  "grep -qx '── Timers (next runs)' '$root/out.log' \
   && [ -z \"\$(section_of '$root' 'Timers (next runs)')\" ]"

exit $fail
