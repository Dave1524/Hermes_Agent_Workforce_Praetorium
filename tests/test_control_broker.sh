#!/usr/bin/env bash
# Fixture suite for bin/control_broker.py (T5.3a): every case runs the broker against the fake
# systemctl/systemd-analyze shims under tests/fixtures/control-broker/bin/. No real unit is touched.
set -uo pipefail
cd "$(dirname "$0")/.."

python3 tests/test_control_broker.py
