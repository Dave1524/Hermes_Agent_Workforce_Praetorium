#!/usr/bin/env python3
"""Shared fixture for the Control Room suites (T5.3). Not a suite: no `test_` prefix.

Builds a ControlRoomReadModel over the REAL checkout's manifests, contracts and timer files —
what the screen must reconcile, carried by every checkout — with the fake systemd answers,
receipts, cadence table and benefit ledger under tests/fixtures/control-room/. Every receipt
fixture is validated on import, so a fixture that does not validate is a test bug caught here,
never a silently-malformed row downstream.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import json
import pathlib
import sys
import threading

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "control-room"
NOW = dt.datetime(2026, 9, 14, 8, 0, tzinfo=dt.timezone.utc)

sys.path.insert(0, str(ROOT / "bin"))
import control_room_api as api  # noqa: E402
from workflow_receipt import validate as validate_receipt  # noqa: E402


def _validate_fixture_receipts() -> None:
    for path in sorted((FIXTURE / "receipts").glob("*/*.json")):
        if path.name == "bad.json":
            continue
        errors = validate_receipt(json.loads(path.read_text()))
        if errors:
            raise AssertionError(f"fixture receipt {path.name} does not validate: {errors}")


_validate_fixture_receipts()


class FakeSystemd:
    def __init__(self, path: pathlib.Path = FIXTURE / "systemd.json") -> None:
        self._doc = json.loads(path.read_text())

    def show(self, name: str, scope: str):
        overrides = self._doc.get(scope, {})
        if name in overrides:
            value = overrides[name]
            if value is None:
                return {}, "Failed to connect to user scope bus: No such file or directory"
            return dict(value), None
        kind = name.rsplit(".", 1)[-1]
        default = self._doc["default"].get(kind)
        if default is None:
            return {}, f"Unit {name} could not be found."
        return dict(default), None


class FakeCalendar:
    """Stands in for `systemd-analyze calendar`: [T0, T0 + seconds] per mapped spec."""

    def __init__(self, path: pathlib.Path = FIXTURE / "cadence.json", start: dt.datetime = NOW) -> None:
        self._table = {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}
        self._start = start

    def __call__(self, spec: str) -> list[dt.datetime]:
        if spec not in self._table:
            raise ValueError(f"fixture cadence table has no entry for {spec!r}")
        return [self._start, self._start + dt.timedelta(seconds=self._table[spec])]


def build_model(**overrides) -> api.ControlRoomReadModel:
    kwargs = dict(
        paths=api.SourcePaths(repo=ROOT, runtime=FIXTURE, receipts=FIXTURE / "receipts",
                              ledger=FIXTURE / "benefit-ledger.toml"),
        systemd=FakeSystemd(),
        clock=lambda: NOW,
        calendar_runner=FakeCalendar(),
    )
    kwargs.update(overrides)
    return api.ControlRoomReadModel(**kwargs)


@contextlib.contextmanager
def serving(model: api.ControlRoomReadModel):
    server = api.make_server("127.0.0.1", 0, model)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
