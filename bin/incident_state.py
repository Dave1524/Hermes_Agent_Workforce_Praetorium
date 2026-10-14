#!/usr/bin/env python3
"""Incident state (T5.3c): one entry per key, reconciled against what a sweep observed.

The state file is `<runtime>/var/incidents/state.json`, schema 1. `reconcile` is pure and
returns the transitions; `load`/`save` are the only I/O. Absence of evidence is not recovery:
a sweep whose sources are degraded (`sources_ok=False`) closes nothing.

Debounce (criterion 15): an entry is due to open once red for `open_after` seconds since
`first_seen` or for STREAK consecutive sweeps, and resolves only after green for
`recover_after` seconds or STREAK consecutive sweeps. A red sweep inside the recovery hold keeps
the entry and its `first_seen`, so a flapping verdict pages once and recovers once. The default
`Debounce()` is the undebounced rule: due at once, resolved on the first green sweep.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import sys
import tempfile
from typing import Any, NamedTuple

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workflow_receipt import iso_utc, parse_time  # noqa: E402

SCHEMA = 1
UTC = dt.timezone.utc
CARRIED = ("class", "severity", "workflow_id", "agent", "unit", "issue", "failed_assertion",
           "required_action", "run_id", "evidence")
STREAK = 3


class Debounce(NamedTuple):
    open_after: int = 0
    recover_after: int = 0


def empty() -> dict[str, Any]:
    return {"schema": SCHEMA, "last_digest_at": None, "incidents": {}}


def _new_entry(item: dict[str, Any], now: dt.datetime) -> dict[str, Any]:
    return {
        "key": item["key"], **{field: item.get(field) for field in CARRIED},
        "run_ids": [item["run_id"]] if item.get("run_id") else [],
        "observations": 1,
        "first_seen": item.get("observed_at") or iso_utc(now),
        "last_seen": iso_utc(now),
        "resolved_at": None, "notified_at": None, "notify_event_id": None, "notify_channel": None,
        "send_attempts": 0, "last_send_error": None, "recovery_notified_at": None, "digested_at": None,
        "red_streak": 1, "green_streak": 0, "green_since": None,
    }


def _update_entry(entry: dict[str, Any], item: dict[str, Any], now: dt.datetime) -> None:
    run_id = item.get("run_id")
    if run_id and run_id != entry.get("run_id"):
        entry["observations"] += 1
        entry["run_ids"].append(run_id)
    for field in CARRIED:
        entry[field] = item.get(field)
    entry["last_seen"] = iso_utc(now)
    entry["red_streak"] = entry.get("red_streak", 0) + 1
    entry["green_streak"], entry["green_since"] = 0, None


def _held_green(entry: dict[str, Any], now: dt.datetime, debounce: Debounce) -> bool:
    entry["red_streak"] = 0
    entry["green_streak"] = entry.get("green_streak", 0) + 1
    entry["green_since"] = entry.get("green_since") or iso_utc(now)
    since = parse_time(entry["green_since"]) or now
    return entry["green_streak"] >= STREAK or (now - since).total_seconds() >= debounce.recover_after


def due_to_open(entry: dict[str, Any], now: dt.datetime, debounce: Debounce = Debounce()) -> bool:
    if debounce.open_after <= 0 or entry.get("red_streak", 1) >= STREAK:
        return True
    first = parse_time(entry.get("first_seen")) or now
    return (now - first).total_seconds() >= debounce.open_after


def open_entries(state: dict[str, Any]) -> list[dict[str, Any]]:
    entries = [e for e in state["incidents"].values() if e.get("resolved_at") is None]
    return sorted(entries, key=lambda e: e.get("first_seen") or "")


def reconcile(state: dict[str, Any], observed: list[dict[str, Any]], now: dt.datetime,
              sources_ok: bool = True, debounce: Debounce = Debounce()) -> dict[str, list[str]]:
    incidents = state["incidents"]
    transitions: dict[str, list[str]] = {"opened": [], "updated": [], "closed": []}
    seen = set()
    for item in observed:
        key = item["key"]
        seen.add(key)
        entry = incidents.get(key)
        if entry is None or entry.get("resolved_at") is not None:
            incidents[key] = _new_entry(item, now)
            transitions["opened"].append(key)
            continue
        _update_entry(entry, item, now)
        transitions["updated"].append(key)
    if not sources_ok:
        return transitions
    for key, entry in incidents.items():
        if key not in seen and entry.get("resolved_at") is None and _held_green(entry, now, debounce):
            entry["resolved_at"] = iso_utc(now)
            transitions["closed"].append(key)
    return transitions


def prune(state: dict[str, Any], now: dt.datetime, retention_days: int) -> list[str]:
    horizon = now - dt.timedelta(days=retention_days)
    pruned = [key for key, entry in state["incidents"].items()
              if entry.get("resolved_at") and (parse_time(entry["resolved_at"]) or now) < horizon]
    for key in pruned:
        del state["incidents"][key]
    return pruned


def digest_due(state: dict[str, Any], now_local: dt.datetime, at_hhmm: str) -> bool:
    hour, minute = (int(part) for part in at_hhmm.split(":", 1))
    gate = now_local.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now_local < gate:
        return False
    last = parse_time(state.get("last_digest_at"))
    return last is None or last < gate


def load(path: pathlib.Path, now: dt.datetime | None = None) -> tuple[dict[str, Any], str | None]:
    path = pathlib.Path(path)
    if not path.exists():
        return empty(), None
    try:
        data = json.loads(path.read_text())
        if not isinstance(data, dict) or data.get("schema") != SCHEMA or not isinstance(data.get("incidents"), dict):
            raise ValueError("not a schema-1 incident state")
        return data, None
    except (OSError, ValueError) as exc:
        stamp = (now or dt.datetime.now(UTC)).astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
        aside = path.with_name(f"{path.name}.corrupt-{stamp}")
        os.replace(path, aside)
        return empty(), f"state file did not parse ({exc}); moved aside to {aside}, starting fresh"


def save(state: dict[str, Any], path: pathlib.Path) -> None:
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=".state.", suffix=".tmp", delete=False)
    try:
        with handle:
            json.dump(state, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, path)
    except BaseException:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise
