#!/usr/bin/env python3
"""The schedule plan (T5.3b): pure over a worktree path. Rewrites exactly three things — the
timer's OnCalendar/RandomizedDelaySec/Persistent lines, the manifest entry's `trigger` string
and the contract's `## Trigger` tokens — and describes the change the way a reviewer needs it:
local and UTC elapses, the catch-up rule Persistent= implies, and when it takes effect.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workflow_pr_record import Plan, Refused  # noqa: E402

SPEC_RE = re.compile(r"^[A-Za-z0-9*,.:/ -]{1,80}$")
DELAY_RE = re.compile(r"^\d+(s|m|min|h)?$")
COLLISION_WINDOW_SECONDS = 1800
ELAPSE_LINE = re.compile(r"^\s*(?:Next elapse|Iteration #\d+):\s*(.+?)\s*$")
UTC_LINE = re.compile(r"^\s*\(in UTC\):\s*(.+?)\s*$")
TIMER_KEY = re.compile(r"^(OnCalendar|RandomizedDelaySec|Persistent)=(.*)$")
MONOTONIC_KEYS = ("OnUnitActiveSec", "OnBootSec", "OnStartupSec", "OnUnitInactiveSec", "OnActiveSec")
TRIGGER_LINE = re.compile(r'^(\s*trigger\s*=\s*)"([^"\n]*)"(\s*(?:#.*)?)$')
ALLOWED_KEYS = {"trigger", "on_calendar", "randomized_delay_sec", "persistent", "manifest_trigger", "contract_trigger",
                "acknowledge_pinned_tests"}
CalendarRunner = Callable[[str], list[dict[str, str]]]


def systemd_analyze_calendar(spec: str, iterations: int = 3) -> list[dict[str, str]]:
    done = subprocess.run(["systemd-analyze", "calendar", f"--iterations={iterations}", spec], capture_output=True,
                          text=True, env={**os.environ, "LC_ALL": "C"}, timeout=30)
    if done.returncode != 0:
        raise ValueError((done.stderr or done.stdout).strip() or f"systemd-analyze calendar exited {done.returncode}")
    elapses, pending = [], None

    def flush() -> None:  # a UTC process zone prints the elapse in UTC and no "(in UTC)" line at all
        if pending is not None and pending.endswith(" UTC"):
            elapses.append({"local": pending, "utc": pending})

    for line in done.stdout.splitlines():
        elapse = ELAPSE_LINE.match(line)
        utc = UTC_LINE.match(line)
        if elapse:
            flush()
            pending = elapse.group(1)
        elif utc and pending is not None:
            elapses.append({"local": pending, "utc": utc.group(1)})
            pending = None
    flush()
    if not elapses:
        raise ValueError(f"systemd-analyze calendar printed no elapse for {spec!r}")
    return elapses


def utc_datetime(text: str) -> dt.datetime:
    return dt.datetime.strptime(text.split(" ", 1)[1], "%Y-%m-%d %H:%M:%S UTC").replace(tzinfo=dt.timezone.utc)


def timer_path(worktree: pathlib.Path, unit: str, scope: str) -> pathlib.Path:
    return pathlib.Path(worktree) / "systemd" / ("user" if scope == "user" else "") / f"{unit}.timer"


def parse_timer(text: str) -> dict[str, Any]:
    parsed: dict[str, Any] = {"on_calendar": [], "randomized_delay_sec": None, "persistent": None, "monotonic": [], "description": None}
    for line in text.splitlines():
        match = TIMER_KEY.match(line.strip())
        if match and match.group(1) == "OnCalendar":
            parsed["on_calendar"].append(match.group(2).strip())
        elif match and match.group(1) == "RandomizedDelaySec":
            parsed["randomized_delay_sec"] = match.group(2).strip()
        elif match:
            parsed["persistent"] = match.group(2).strip().lower() in ("true", "yes", "1", "on")
        elif line.strip().split("=", 1)[0] in MONOTONIC_KEYS:
            parsed["monotonic"].append(line.strip().split("=", 1)[0])
        elif line.startswith("Description="):
            parsed["description"] = line.split("=", 1)[1]
    return parsed


def render_timer(text: str, on_calendar: list[str], delay: str | None, persistent: bool | None) -> str:
    lines = text.splitlines(keepends=True)
    out: list[str] = []
    placed_calendar = placed_delay = placed_persistent = False
    for line in lines:
        match = TIMER_KEY.match(line.strip())
        key = match.group(1) if match else None
        if key == "OnCalendar":
            if not placed_calendar:
                out.extend(f"OnCalendar={spec}\n" for spec in on_calendar)
                placed_calendar = True
            continue
        if key == "RandomizedDelaySec":
            if delay is not None:
                out.append(f"RandomizedDelaySec={delay}\n")
            else:
                out.append(line)
            placed_delay = True
            continue
        if key == "Persistent":
            out.append(line if persistent is None else f"Persistent={'true' if persistent else 'false'}\n")
            placed_persistent = True
            continue
        out.append(line)
    rendered = "".join(out)
    if delay is not None and not placed_delay:
        rendered = _insert_after_last_calendar(rendered, f"RandomizedDelaySec={delay}\n")
    if persistent is not None and not placed_persistent:
        rendered = _insert_after_last_calendar(rendered, f"Persistent={'true' if persistent else 'false'}\n", after_delay=True)
    return rendered


def _insert_after_last_calendar(text: str, new_line: str, after_delay: bool = False) -> str:
    lines = text.splitlines(keepends=True)
    index = max(i for i, line in enumerate(lines) if line.startswith("OnCalendar=") or (after_delay and line.startswith("RandomizedDelaySec=")))
    lines.insert(index + 1, new_line)
    return "".join(lines)


def rewrite_manifest_trigger(text: str, unit: str, trigger: str) -> str:
    lines = text.splitlines(keepends=True)
    start = _block_start(lines, unit)
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith("[")), len(lines))
    for i in range(start, end):
        stripped = lines[i].rstrip("\n")
        if re.match(r"^\s*trigger\s*=", stripped):
            match = TRIGGER_LINE.match(stripped)
            if not match:
                raise Refused("bad_request", f"{unit}: the manifest trigger is not a single-line string; edit it by hand")
            lines[i] = f'{match.group(1)}"{trigger}"{match.group(3)}\n'
            rewritten = "".join(lines)
            _assert_only_trigger_changed(text, rewritten, unit)
            return rewritten
    raise Refused("bad_request", f"{unit}: the manifest entry carries no trigger line")


def _block_start(lines: list[str], unit: str) -> int:
    for i, line in enumerate(lines):
        if line.strip() == "[[workflows]]":
            end = next((j for j in range(i + 1, len(lines)) if lines[j].startswith("[")), len(lines))
            if any(re.match(rf'^\s*unit\s*=\s*"{re.escape(unit)}"', l) for l in lines[i:end]):
                return i
    raise Refused("bad_request", f"{unit}: no [[workflows]] entry in the manifest")


def _assert_only_trigger_changed(before: str, after: str, unit: str) -> None:
    old, new = tomllib.loads(before), tomllib.loads(after)
    old_rows, new_rows = old.pop("workflows", []), new.pop("workflows", [])
    if old != new or len(old_rows) != len(new_rows):
        raise Refused("bad_request", f"{unit}: the manifest rewrite changed more than the trigger")
    for a, b in zip(old_rows, new_rows):
        keys = {k for k in set(a) | set(b) if a.get(k) != b.get(k)}
        if keys and (a.get("unit") != unit or keys != {"trigger"}):
            raise Refused("bad_request", f"{unit}: the manifest rewrite changed {sorted(keys)} on {a.get('unit')}")


def rewrite_contract_trigger(text: str, current_specs: list[str], proposed_specs: list[str], current_delay: str | None,
                             proposed_delay: str | None, date: str, pid: str, contract_trigger: str | None = None) -> str:
    match = re.search(r"^## Trigger\s*$\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    if not match:
        raise Refused("bad_request", "the contract has no ## Trigger section")
    body = match.group(1)
    if contract_trigger is not None:
        new_body = contract_trigger.rstrip("\n") + "\n\n"
    else:
        new_body = _rewrite_tokens(body, current_specs, proposed_specs, current_delay, proposed_delay, date, pid)
    return text[:match.start(1)] + new_body + text[match.end(1):]


def _rewrite_tokens(body: str, current: list[str], proposed: list[str], current_delay: str | None,
                    proposed_delay: str | None, date: str, pid: str) -> str:
    if not any(f"`OnCalendar={spec}`" in body for spec in current):
        line = f"Schedule changed {date} (Control Room proposal {pid}): " + ", ".join(f"`OnCalendar={s}`" for s in proposed) + ".\n"
        return body.rstrip("\n") + "\n\n" + line + "\n"
    joined = ", ".join(f"`OnCalendar={s}`" for s in proposed)
    first = True
    for spec in current:
        token = f"`OnCalendar={spec}`"
        if token not in body:
            continue
        if first:
            body, first = body.replace(token, joined, 1), False
        else:
            body = body.replace(f", {token}", "").replace(token, "")
    if current_delay and proposed_delay and current_delay != proposed_delay:
        body = body.replace(f"`RandomizedDelaySec={current_delay}`", f"`RandomizedDelaySec={proposed_delay}`")
    return body


def validate_proposed(proposed: Any) -> dict[str, Any]:
    if not isinstance(proposed, dict):
        raise Refused("bad_request", "proposed must be an object")
    unknown = sorted(set(proposed) - ALLOWED_KEYS)
    if unknown:
        raise Refused("bad_request", f"unknown proposed keys: {', '.join(unknown)}")
    specs = proposed.get("on_calendar")
    if not isinstance(specs, list) or not 1 <= len(specs) <= 4 or not all(isinstance(s, str) for s in specs):
        raise Refused("bad_request", "on_calendar must be a list of 1 to 4 strings")
    for spec in specs:
        if not SPEC_RE.match(spec) or "=" in spec or "[" in spec or "\n" in spec:
            raise Refused("bad_request", f"on_calendar spec {spec[:80]!r} is not a calendar expression")
    delay = proposed.get("randomized_delay_sec")
    if delay is not None and (not isinstance(delay, str) or not DELAY_RE.match(delay)):
        raise Refused("bad_request", "randomized_delay_sec must match ^\\d+(s|m|min|h)?$ or be null")
    persistent = proposed.get("persistent")
    if persistent is not None and not isinstance(persistent, bool):
        raise Refused("bad_request", "persistent must be true, false or null")
    for key in ("trigger", "manifest_trigger", "contract_trigger"):
        if proposed.get(key) is not None and not isinstance(proposed[key], str):
            raise Refused("bad_request", f"{key} must be a string or null")
    if not isinstance(proposed.get("acknowledge_pinned_tests", False), bool):
        raise Refused("bad_request", "acknowledge_pinned_tests must be a boolean")
    return {"on_calendar": [s.strip() for s in specs], "randomized_delay_sec": delay, "persistent": persistent,
            "trigger": proposed.get("trigger"), "manifest_trigger": proposed.get("manifest_trigger"),
            "contract_trigger": proposed.get("contract_trigger"),
            "acknowledge_pinned_tests": bool(proposed.get("acknowledge_pinned_tests", False))}


def select_trigger(item: dict[str, Any], requested: str | None) -> dict[str, Any]:
    triggers = [t for t in item.get("triggers", []) if t.get("unit")]
    timers = [t for t in triggers if t.get("kind") == "timer"]
    if not timers:
        raise Refused("not_a_timer", f"{item['id']} is a {triggers[0].get('kind') if triggers else 'service'} entry, not a timer")
    if requested is None and len(timers) > 1:
        raise Refused("trigger_required", f"{item['id']} has {len(timers)} timers; name one", choices=[t["unit"] for t in timers])
    if requested is None:
        return timers[0]
    for trigger in timers:
        if trigger["unit"] == requested:
            return trigger
    raise Refused("bad_request", f"{requested!r} is not a timer of {item['id']}", choices=[t["unit"] for t in timers])


def _elapses(spec: str, runner: CalendarRunner) -> tuple[list[dict[str, str]], str | None]:
    try:
        return runner(spec)[:3], None
    except (ValueError, OSError) as exc:
        return [], str(exc).splitlines()[0] if str(exc) else "calendar spec did not parse"


def describe_schedule(current: dict[str, Any], proposed: dict[str, Any], tz: dict[str, str], calendar_runner: CalendarRunner,
                      control_state: str | None, unit: str, scope: str) -> dict[str, Any]:
    attention: list[str] = []
    sides = {}
    for name, side in (("current", current), ("proposed", proposed)):
        nexts: list[dict[str, str]] = []
        for spec in side["on_calendar"]:
            elapses, problem = _elapses(spec, calendar_runner)
            nexts.extend(elapses)
            if problem:
                attention.append(f"{name} spec {spec!r}: {problem}")
        sides[name] = {"on_calendar": side["on_calendar"], "randomized_delay_sec": side.get("randomized_delay_sec"),
                       "persistent": side.get("persistent"), "next": nexts[:3] if name == "current" else nexts[:3 * len(side["on_calendar"])]}
    persistent = proposed.get("persistent")
    paused = control_state != "active"
    if persistent:
        catch_up = ("Persistent=true and the timer is paused: a resume through the Control Room fires the service immediately "
                    "if the stamp predates the previous elapse of the NEW schedule — T5.3a's resume preview shows it before applying."
                    if paused else
                    f"Persistent=true and the timer is active: a missed elapse fires at the next daemon-reload/boot; the new "
                    f"schedule applies after `systemctl restart {unit}.timer`.")
    else:
        catch_up = "Persistent=false: no catch-up; an elapse missed while the box is down or the timer is paused is skipped."
    takes_effect = "at resume (no unit is restarted by this PR)" if paused else f"after the land-time `restart {unit}.timer`"
    if current.get("description") and re.search(r"\b(Mon|Tue|Wed|Thu|Fri|Sat|Sun|Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday|\d{1,2}:\d{2})\b",
                                                current["description"]):
        attention.append(f"prose: Description= reads {current['description']!r} — not edited")
    return {"unit": unit, "scope": scope, "current": sides["current"], "proposed": sides["proposed"],
            "timezone": {"name": tz["name"], "source": tz.get("source", "TZ"),
                         "explicit_in_spec": any(re.search(r"\b(UTC|GMT|[A-Z][a-z]+/[A-Z][A-Za-z_]+)$", s) for s in proposed["on_calendar"])},
            "catch_up": catch_up, "takes_effect": takes_effect, "reviewer_attention": attention}


def collisions(worktree: pathlib.Path, unit: str, scope: str, proposed_specs: list[str], calendar_runner: CalendarRunner) -> list[str]:
    mine: list[dt.datetime] = []
    for spec in proposed_specs:
        mine.extend(utc_datetime(e["utc"]) for e in _elapses(spec, calendar_runner)[0])
    found = []
    for path in sorted(pathlib.Path(worktree).glob("systemd/**/*.timer")):
        if "archive" in path.parts or path == timer_path(worktree, unit, scope):
            continue
        for spec in parse_timer(path.read_text(encoding="utf-8"))["on_calendar"]:
            for elapse in _elapses(spec, calendar_runner)[0]:
                other = utc_datetime(elapse["utc"])
                near = [m for m in mine if abs((m - other).total_seconds()) <= COLLISION_WINDOW_SECONDS]
                if near:
                    found.append(f"{path.name} ({spec}) elapses {elapse['utc']}, within {COLLISION_WINDOW_SECONDS // 60} min of "
                                 f"{near[0]:%a %Y-%m-%d %H:%M:%S UTC} — both runs contend for the shared agent_propose.sh flock (agent-model §6.6)")
    return found


def plan_schedule(worktree: pathlib.Path, item: dict[str, Any], proposed: Any, now: dt.datetime, pid: str, tz: dict[str, str],
                  calendar_runner: CalendarRunner) -> Plan:
    worktree = pathlib.Path(worktree)
    wanted = validate_proposed(proposed)
    trigger = select_trigger(item, wanted["trigger"])
    unit, scope = trigger["unit"], trigger.get("scope", "system")
    path = timer_path(worktree, unit, scope)
    if not path.is_file():
        raise Refused("not_a_timer", f"{unit}: {path.relative_to(worktree)} is not in the checkout")
    text = path.read_text(encoding="utf-8")
    current = parse_timer(text)
    if not current["on_calendar"]:
        raise Refused("not_calendar_timer", f"{unit}.timer fires on {', '.join(current['monotonic']) or 'no calendar'}, not OnCalendar=")
    delay = wanted["randomized_delay_sec"] if wanted["randomized_delay_sec"] is not None else current["randomized_delay_sec"]
    persistent = wanted["persistent"] if wanted["persistent"] is not None else current["persistent"]
    path.write_text(render_timer(text, wanted["on_calendar"], wanted["randomized_delay_sec"], wanted["persistent"]), encoding="utf-8")
    edits = [str(path.relative_to(worktree))]
    manifest_trigger = wanted["manifest_trigger"] or _generated_trigger(wanted["on_calendar"], delay)
    for relative in item.get("manifestPaths", []):
        manifest = worktree / relative
        if _names_unit(manifest, unit):
            manifest.write_text(rewrite_manifest_trigger(manifest.read_text(encoding="utf-8"), unit, manifest_trigger), encoding="utf-8")
            edits.append(relative)
    contract_relative = (item.get("contract") or {}).get("path")
    contract_trigger_text = None
    if contract_relative and (worktree / contract_relative).is_file():
        contract = worktree / contract_relative
        rewritten = rewrite_contract_trigger(contract.read_text(encoding="utf-8"), current["on_calendar"], wanted["on_calendar"],
                                             current["randomized_delay_sec"], delay, f"{now:%Y-%m-%d}", pid, wanted["contract_trigger"])
        contract.write_text(rewritten, encoding="utf-8")
        edits.append(contract_relative)
        section = re.search(r"^## Trigger\s*$\n(.*?)(?=^## |\Z)", rewritten, re.MULTILINE | re.DOTALL)
        contract_trigger_text = section.group(1).strip() if section else None
    description = describe_schedule(current, {"on_calendar": wanted["on_calendar"], "randomized_delay_sec": delay, "persistent": persistent},
                                    tz, calendar_runner, (item.get("control") or {}).get("state"), unit, scope)
    description["manifest_trigger"] = manifest_trigger
    description["contract_trigger"] = contract_trigger_text
    summary = f"{unit}.timer: OnCalendar {' / '.join(current['on_calendar'])} → {' / '.join(wanted['on_calendar'])}"
    proposed_utc = [e["utc"] for e in description["proposed"]["next"]]
    return Plan("schedule", item["id"], [unit], edits, description, summary, description["reviewer_attention"],
                {"unit": unit, "scope": scope, "specs": wanted["on_calendar"], "timer_path": str(path.relative_to(worktree)),
                 "proposed_utc": proposed_utc, "slugs": _slugs(item["id"], unit), "deleted": [], "calendar_runner": calendar_runner,
                 "acknowledge_pinned_tests": wanted["acknowledge_pinned_tests"]})


def _generated_trigger(specs: list[str], delay: str | None) -> str:
    return " / ".join(specs) + (f" (+{delay} jitter)" if delay else "")


def _names_unit(manifest: pathlib.Path, unit: str) -> bool:
    try:
        return any(w.get("unit") == unit for w in tomllib.loads(manifest.read_text(encoding="utf-8")).get("workflows", []))
    except (OSError, tomllib.TOMLDecodeError):
        return False


def _slugs(workflow_id: str, unit: str) -> list[str]:
    return sorted({workflow_id, unit, workflow_id.replace("-", "_"), unit.replace("-", "_")})
