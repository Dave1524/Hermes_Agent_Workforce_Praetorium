#!/usr/bin/env bash
# Screen-side suite for the T5.3a workflow controls: the Control Room's POST handler over the real
# broker served on a unix socket by tests/fixtures/control-broker/fake_broker_socket.py, against
# the fixture shims; also lints tests/acceptance/control_room_controls.sh. No real unit is touched.
set -uo pipefail
cd "$(dirname "$0")/.."

python3 tests/test_control_room_control.py
