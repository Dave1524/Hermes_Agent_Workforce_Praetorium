#!/usr/bin/env bash
# Phase-B brief writer — structural assertions.
#
# The defect this suite exists for: a timer can be active, enabled and correct in
# `list-timers` while the ExecStart it names does not exist, so it produces nothing and
# alerts on every firing. Verified by asserting the artifacts, never by trusting unit state.
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
QUEUE="$REPO_ROOT/design/phaseb-brief-queue.toml"
RUNNER="$REPO_ROOT/bin/run_phaseb_brief_cc.sh"
TASK="$REPO_ROOT/profiles/phaseb_brief_cc_task.md"
SERVICE="$REPO_ROOT/systemd/praetorium-phaseb-brief@.service"
DEPLOYED_RUNNER="$HOME/agent-workforce/bin/run_phaseb_brief_cc.sh"
ETC=/etc/systemd/system
fail=0

assert() {
  local d=$1 c=$2 pf
  pf=$(shopt -po pipefail)
  set +o pipefail
  if eval "$c"; then echo "  ok: $d"; else echo "  FAIL: $d"; fail=1; fi
  eval "$pf"
}

queue_covers() { python3 -c "
import tomllib,sys
ids={b['id'] for b in tomllib.load(open('$QUEUE','rb'))['brief']}
sys.exit(0 if ids=={2,3,4,5,6} else 1)"; }
queue_entries_complete() { python3 -c "
import tomllib,sys
for b in tomllib.load(open('$QUEUE','rb'))['brief']:
    for k in ('id','slug','title','section','ships','must_carry','preconditions'):
        if k not in b: sys.exit(1)
    if not b['must_carry']: sys.exit(1)
sys.exit(0)"; }
runner_pins_full_model_name() { grep -q -- '--model claude-opus-5' "$RUNNER"; }
runner_rejects_the_alias() { ! grep -qE -- '--model +opus *$' "$RUNNER"; }
runner_is_idempotent() { grep -q 'already exists' "$RUNNER"; }
runner_never_writes_current() { ! grep -q 'briefs/current' "$RUNNER"; }
task_forbids_current() { grep -q 'current\.md' "$TASK"; }
timer_is_one_shot() { grep -qE '^OnCalendar=20[0-9]{2}-[0-9]{2}-[0-9]{2} ' "$1"; }
etc_matches_source() { cmp -s "$1" "$ETC/$(basename "$1")"; }

echo "test: phaseb-brief jobs ::phaseb-brief"
assert 'a found pattern is never reported as a failure' "yes | grep -q y"

echo "-- queue"
assert 'the brief queue exists' "[ -r '$QUEUE' ]"
assert 'the queue is valid TOML' "python3 -c \"import tomllib;tomllib.load(open('$QUEUE','rb'))\""
assert 'the queue covers exactly briefs 2-6' "queue_covers"
assert 'every entry carries a non-empty must_carry list' "queue_entries_complete"

echo "-- runner"
assert 'the runner exists' "[ -f '$RUNNER' ]"
assert 'the runner is executable' "[ -x '$RUNNER' ]"
assert 'the runner pins claude-opus-5 by full name' "runner_pins_full_model_name"
assert 'the runner does not use the rolling opus alias' "runner_rejects_the_alias"
assert 'the runner skips a brief that already exists' "runner_is_idempotent"
assert 'the runner never writes briefs/current.md' "runner_never_writes_current"
assert 'the task profile names current.md as off limits' "task_forbids_current"
assert 'the task profile exists' "[ -r '$TASK' ]"

echo "-- units"
assert 'the template service exists' "[ -f '$SERVICE' ]"
assert 'its ExecStart names the deployed runner' "grep -q 'ExecStart=/home/dave/agent-workforce/bin/run_phaseb_brief_cc.sh %i' '$SERVICE'"
assert 'the ExecStart target is deployed and executable' "[ -x '$DEPLOYED_RUNNER' ]"
assert 'the service alerts on failure' "grep -q 'OnFailure=agent-alert@%n.service' '$SERVICE'"
for id in 2 3 4 5 6; do
  t="$REPO_ROOT/systemd/praetorium-phaseb-brief@${id}.timer"
  assert "timer $id exists" "[ -f '$t' ]"
  assert "timer $id is one-shot, not recurring" "timer_is_one_shot '$t'"
  assert "timer $id names its own service instance" "grep -q 'Unit=praetorium-phaseb-brief@${id}.service' '$t'"
done

echo "-- source matches /etc (D8's class, asserted early for these units)"
for u in "$SERVICE" "$REPO_ROOT"/systemd/praetorium-phaseb-brief@[0-9].timer; do
  b="$(basename "$u")"
  assert "$b is installed in /etc" "[ -f '$ETC/$b' ]"
  assert "$b is byte-identical in source and /etc" "etc_matches_source '$u'"
done

[ "$fail" -eq 0 ] || exit 1
