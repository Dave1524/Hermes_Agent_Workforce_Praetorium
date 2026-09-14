#!/usr/bin/env python3
"""Timer cadence and artifact freshness for the Control Room (T5.3).

Cadence is read from the committed timer file, never from `systemctl`: a paused timer reports
no next elapse, and the screen must still say how often the workflow is *meant* to run. A
calendar spec's interval is the gap between its next two elapses, asked of `systemd-analyze
calendar` through an injectable runner; a monotonic span needs no runner. Anything that
cannot be read is `unavailable` with the reason named — a cadence of 0 is never emitted.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import subprocess
import time
from typing import Any, Callable

STALE_MULTIPLIER = 2
STALE_SLACK_SECONDS = 3600
CACHE_TTL_SECONDS = 600
_SPAN_UNITS = {
    "s": 1, "sec": 1, "second": 1, "seconds": 1,
    "m": 60, "min": 60, "minute": 60, "minutes": 60,
    "h": 3600, "hr": 3600, "hour": 3600, "hours": 3600,
    "d": 86400, "day": 86400, "days": 86400,
    "w": 604800, "week": 604800, "weeks": 604800,
}
_SPAN_TOKEN = re.compile(r"(\d+(?:\.\d+)?)\s*([a-z]*)")
_UTC_STAMP = re.compile(r"^(?:[A-Za-z]{3} )?(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2}) UTC$")
_CALENDAR_UTC_LINE = re.compile(r"^\s*\(in UTC\):\s*(.+)$", re.MULTILINE)
_CALENDAR_ELAPSE_LINE = re.compile(r"^\s*(?:Next elapse|Iteration #\d+):\s*(.+)$", re.MULTILINE)

CalendarRunner = Callable[[str], list[dt.datetime]]
_calendar_cache: dict[str, tuple[float, list[dt.datetime]]] = {}


def parse_systemd_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str):
        return None
    match = _UTC_STAMP.match(value.strip())
    if not match:
        return None
    return dt.datetime.fromisoformat(f"{match.group(1)}T{match.group(2)}+00:00")


def parse_span(value: Any) -> int | None:
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if _SPAN_TOKEN.sub("", text).strip():
        return None
    total = 0.0
    for match in _SPAN_TOKEN.finditer(text):
        unit = match.group(2) or "s"
        if unit not in _SPAN_UNITS:
            return None
        total += float(match.group(1)) * _SPAN_UNITS[unit]
    return int(total)


def parse_calendar_output(output: str) -> list[dt.datetime]:
    lines = _CALENDAR_UTC_LINE.findall(output) or _CALENDAR_ELAPSE_LINE.findall(output)
    elapses = [parse_systemd_timestamp(line.strip()) for line in lines]
    return [value for value in elapses if value is not None]


def DEFAULT_RUNNER(spec: str) -> list[dt.datetime]:  # noqa: N802 - named as the brief's export
    cached = _calendar_cache.get(spec)
    if cached and time.monotonic() - cached[0] < CACHE_TTL_SECONDS:
        return cached[1]
    completed = subprocess.run(
        ["systemd-analyze", "calendar", "--iterations=2", spec],
        check=False, capture_output=True, text=True, timeout=3,
    )
    if completed.returncode != 0:
        raise RuntimeError((completed.stderr or completed.stdout).strip() or "systemd-analyze failed")
    elapses = parse_calendar_output(completed.stdout)
    if len(elapses) < 2:
        raise RuntimeError("systemd-analyze printed fewer than two elapses")
    _calendar_cache[spec] = (time.monotonic(), elapses)
    return elapses


def timer_file(repo: pathlib.Path, unit: str, scope: str) -> pathlib.Path:
    name = unit if unit.endswith(".timer") else f"{unit}.timer"
    base = pathlib.Path(repo) / "systemd"
    return (base / "user" / name) if scope == "user" else (base / name)


def _unavailable(error: str, **fields: Any) -> dict[str, Any]:
    return {"status": "unavailable", "seconds": None, "source": None, "spec": None,
            "persistent": None, "randomizedDelaySec": None, **fields, "error": error}


def _timer_directives(text: str) -> dict[str, list[str]]:
    directives: dict[str, list[str]] = {}
    for line in text.splitlines():
        key, separator, value = line.strip().partition("=")
        if separator and not key.startswith("#"):
            directives.setdefault(key.strip(), []).append(value.strip())
    return directives


def _calendar_interval(specs: list[str], runner: CalendarRunner) -> tuple[int | None, str | None, str | None]:
    best: tuple[int, str] | None = None
    for spec in specs:
        try:
            elapses = runner(spec)
        except Exception as exc:  # the runner is external; its failure is the finding
            return None, None, f"calendar {spec!r}: {type(exc).__name__}: {exc}"
        if len(elapses) < 2:
            return None, None, f"calendar {spec!r}: fewer than two elapses"
        seconds = int((elapses[1] - elapses[0]).total_seconds())
        if seconds <= 0:
            return None, None, f"calendar {spec!r}: non-positive interval"
        if best is None or seconds < best[0]:
            best = (seconds, spec)
    if best is None:
        return None, None, "no OnCalendar spec"
    return best[0], best[1], None


def cadence_for(repo: pathlib.Path, unit: str, scope: str, runner: CalendarRunner | None = None) -> dict[str, Any]:
    path = timer_file(repo, unit, scope)
    relative = path.relative_to(pathlib.Path(repo)) if path.is_relative_to(pathlib.Path(repo)) else path
    if not path.is_file():
        return _unavailable(f"timer file missing: {relative}")
    try:
        directives = _timer_directives(path.read_text())
    except OSError as exc:
        return _unavailable(f"timer file unreadable: {relative}: {exc}")
    persistent = {"true": True, "yes": True, "false": False, "no": False}.get(
        (directives.get("Persistent") or [""])[-1].lower())
    delay = parse_span((directives.get("RandomizedDelaySec") or [""])[-1])
    common = {"persistent": persistent, "randomizedDelaySec": delay}
    monotonic = directives.get("OnUnitActiveSec")
    if monotonic:
        seconds = parse_span(monotonic[-1])
        if seconds is None:
            return _unavailable(f"OnUnitActiveSec unparsable: {monotonic[-1]!r}", **common)
        return {"status": "measured", "seconds": seconds, "source": "OnUnitActiveSec",
                "spec": monotonic[-1], **common, "error": None}
    calendars = directives.get("OnCalendar")
    if not calendars:
        return _unavailable(f"{relative} declares no recurring trigger", **common)
    seconds, spec, error = _calendar_interval(calendars, runner or DEFAULT_RUNNER)
    if error:
        return _unavailable(error, **common)
    return {"status": "measured", "seconds": seconds, "source": "OnCalendar", "spec": spec,
            **common, "error": None}


def freshness(age_seconds: Any, cadence: dict[str, Any] | None) -> str:
    if not isinstance(age_seconds, (int, float)) or isinstance(age_seconds, bool):
        return "unknown"
    if not isinstance(cadence, dict) or cadence.get("status") != "measured":
        return "unknown"
    seconds = cadence.get("seconds")
    if not isinstance(seconds, (int, float)) or seconds <= 0:
        return "unknown"
    return "stale" if age_seconds > STALE_MULTIPLIER * seconds + STALE_SLACK_SECONDS else "current"
