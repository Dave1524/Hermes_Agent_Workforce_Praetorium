#!/usr/bin/env python3
"""Control Room broker (T5.3a): the root-owned half of the live workflow controls.

One process per request, as root, from a root-owned installed copy of this file. It reads a
root-owned allowlist, runs a fixed vocabulary of `systemctl` verbs against units that appear in
that allowlist and match UNIT_RE, reconciles state from `systemctl show` before and after, and
writes one audit receipt per request whatever the outcome. Self-contained on purpose: stdlib
only, no sibling import — the copy under /usr/local/lib must never execute anything from the
dave-writable bin/ tree.

Two kinds of entry (T5.3g): a `workflows` row is a timer workflow and takes ACTIONS; a
`runtimes` row is an always-on template instance such as buzz-agent@marcus and takes
RUNTIME_ACTIONS — the session-scoped verbs only, never enable/disable. A runtime is read
through RUNTIME_PROPERTIES and nothing else: never `status`, never ExecStart or Environment,
because the launched process carries the agent's credential in its argv.
"""
from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import fcntl
import getpass
import hashlib
import ipaddress
import json
import os
import pathlib
import re
import secrets
import socket
import stat
import struct
import subprocess
import sys
import time
from typing import Any, Callable

UNIT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUNTIME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}@[a-z0-9][a-z0-9-]{0,63}$")
TOKEN_RE = re.compile(r"^\d{8}T\d{6}Z-[a-z_]+-[0-9a-f]{6}$")
ACTIONS = ("pause", "resume", "run_now", "retry", "stop")
RUNTIME_ACTIONS = ("start", "stop", "restart")
ALL_ACTIONS = ACTIONS + tuple(action for action in RUNTIME_ACTIONS if action not in ACTIONS)
STAGES = ("preview", "apply")
RESULTS = ("applied", "refused", "failed", "previewed")
REFUSAL_CODES = (
    "bad_request", "unknown_action", "unknown_workflow", "not_allowlisted", "unit_not_found",
    "masked", "peer_denied", "allowlist_invalid", "locked", "state_conflict", "preview_required",
    "preview_stale", "trigger_required", "not_idempotent", "confirmation_required",
    "reason_required",
)
HTTP_STATUS = {"unknown_workflow": 404, "peer_denied": 403, "not_allowlisted": 403}
REQUEST_KEYS = {"v", "workflow_id", "action", "reason", "stage", "preview_token", "trigger",
                "confirm", "retry_of", "actor"}
MAX_BODY_BYTES = 8192
MAX_FIELD_CHARS = 200
PREVIEW_TTL_SECONDS = 600
STOP_POLL_SECONDS = 15
START_SETTLE_SECONDS = 6
LOCK_WAIT_SECONDS = 30
COMMAND_TIMEOUT_SECONDS = 20
CHILD_ENV = {"PATH": os.environ.get("PATH", "/usr/bin:/bin"), "LC_ALL": "C", "TZ": "UTC"}
TIMER_PROPERTIES = ("ActiveState,SubState,UnitFileState,LoadState,LastTriggerUSec,"
                    "NextElapseUSecRealtime,Persistent,TimersCalendar")
SERVICE_PROPERTIES = ("ActiveState,SubState,LoadState,Result,InvocationID,"
                      "ExecMainStartTimestamp,ExecMainExitTimestamp")
RUN_PROPERTIES = "InvocationID,ActiveState,ExecMainStartTimestamp"
RUNTIME_PROPERTIES = ("ActiveState,SubState,UnitFileState,LoadState,Result,InvocationID,"
                      "ExecMainStartTimestamp,ExecMainExitTimestamp,NRestarts")
SETTLE_PROPERTIES = "ActiveState,SubState,NRestarts"
RUNTIME_ACTIVE_STATES = {"active", "activating", "reloading"}
RUNTIME_PAUSED_STATES = {"inactive", "failed", "deactivating"}
MASKED_STATES = {"masked", "masked-runtime"}
RUNNING_SUBSTATES = {"running", "start", "start-pre", "start-post"}
RECEIPT_KEYS = (
    "schema", "receipt_id", "workflow_id", "requested_workflow_id", "action", "requested_action",
    "stage", "trigger", "actor", "reason", "confirm", "requested_at", "completed_at", "before",
    "after", "result", "refusal", "commands", "run_id", "next_scheduled_run", "catch_up_fired",
    "implication", "note", "links",
)
ACTOR_KINDS = ("screen", "cli")
_CALENDAR_SPEC = re.compile(r"OnCalendar=(.+?)\s*;")
_ELAPSE_LINE = re.compile(r"^\s*(?:Next elapse|Iteration #2):\s*(.+?)\s*$", re.MULTILINE)
_IRREGULAR_SPEC = re.compile(r"\.\.|,|/")


class Refusal(Exception):
    def __init__(self, code: str, message: str, choices: list[str] | None = None) -> None:
        super().__init__(message)
        self.code, self.message, self.choices = code, message, choices


class CommandFailed(Exception):
    pass


@dataclasses.dataclass(frozen=True)
class Config:
    allowlist: pathlib.Path
    receipts: pathlib.Path
    peer_uids: frozenset[int]
    user_manager: str
    system_stamp_dir: pathlib.Path
    user_stamp_dir: pathlib.Path
    lock: pathlib.Path
    now: dt.datetime | None = None
    start_settle: int = START_SETTLE_SECONDS

    def clock(self) -> dt.datetime:
        return self.now or dt.datetime.now(dt.timezone.utc)

    def stamp_dir(self, scope: str) -> pathlib.Path:
        return self.user_stamp_dir if scope == "user" else self.system_stamp_dir


# --- time -----------------------------------------------------------------------------
def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso(value: dt.datetime | None) -> str | None:
    return value.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if value else None


def parse_iso(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc) if parsed.tzinfo is None else parsed.astimezone(dt.timezone.utc)


def parse_systemd_timestamp(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = dt.datetime.strptime(value.strip(), "%a %Y-%m-%d %H:%M:%S %Z")
    except ValueError:
        return None
    return parsed.replace(tzinfo=dt.timezone.utc)


# --- the peer gate --------------------------------------------------------------------
def _is_loopback(address: Any) -> bool:
    try:
        return ipaddress.ip_address(str(address)).is_loopback
    except ValueError:
        return False


def peer_allowed(remote: Any, local: Any) -> tuple[bool, str]:
    if _is_loopback(local):
        return True, "loopback-bound development instance"
    if not remote:
        return False, "no peer address on a non-loopback screen"
    if _is_loopback(remote):
        return False, "loopback peer on a non-loopback screen"
    if remote == local:
        return False, "request from the screen's own host"
    return True, "peer accepted"


# --- the allowlist --------------------------------------------------------------------
class Allowlist:
    def __init__(self, workflows: dict[str, dict[str, Any]], excluded: list[dict[str, Any]],
                 runtimes: dict[str, dict[str, Any]] | None = None) -> None:
        self.workflows, self.excluded, self.runtimes = workflows, excluded, runtimes or {}

    @classmethod
    def load(cls, path: pathlib.Path) -> "Allowlist":
        try:
            data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            raise Refusal("allowlist_invalid", f"allowlist unreadable at {path}: {exc}") from exc
        return cls.load_data(data, path)

    @classmethod
    def load_data(cls, data: Any, path: Any = "<memory>") -> "Allowlist":
        if not isinstance(data, dict) or data.get("schema") != 1:
            raise Refusal("allowlist_invalid", f"allowlist at {path} is not schema 1")
        workflows = data.get("workflows")
        excluded = data.get("excluded")
        if not isinstance(workflows, dict) or not isinstance(excluded, list):
            raise Refusal("allowlist_invalid", f"allowlist at {path} has no workflows/excluded tables")
        for workflow_id, entry in workflows.items():
            cls._check_entry(path, workflow_id, entry)
        runtimes = data.get("runtimes", {})
        if not isinstance(runtimes, dict):
            raise Refusal("allowlist_invalid", f"allowlist at {path}: runtimes is not a table")
        for runtime_id, entry in runtimes.items():
            cls._check_runtime_entry(path, runtime_id, entry)
        return cls(workflows, [row for row in excluded if isinstance(row, dict)], runtimes)

    @staticmethod
    def _check_entry(path: pathlib.Path, workflow_id: Any, entry: Any) -> None:
        if not isinstance(workflow_id, str) or not UNIT_RE.match(workflow_id):
            raise Refusal("allowlist_invalid", f"allowlist at {path}: id outside the unit grammar")
        triggers = entry.get("triggers") if isinstance(entry, dict) else None
        if not isinstance(triggers, list) or not triggers:
            raise Refusal("allowlist_invalid", f"allowlist at {path}: {workflow_id} declares no trigger")
        for trigger in triggers:
            unit = trigger.get("unit") if isinstance(trigger, dict) else None
            scope = trigger.get("scope") if isinstance(trigger, dict) else None
            if not isinstance(unit, str) or not UNIT_RE.match(unit) or scope not in ("system", "user"):
                raise Refusal("allowlist_invalid",
                              f"allowlist at {path}: {workflow_id} carries a unit outside the grammar")

    @staticmethod
    def _check_runtime_entry(path: pathlib.Path, runtime_id: Any, entry: Any) -> None:
        if not isinstance(runtime_id, str) or not RUNTIME_RE.match(runtime_id):
            raise Refusal("allowlist_invalid", f"allowlist at {path}: runtime id outside the runtime grammar")
        unit = entry.get("unit") if isinstance(entry, dict) else None
        scope = entry.get("scope") if isinstance(entry, dict) else None
        owner = entry.get("owner") if isinstance(entry, dict) else None
        if unit != runtime_id or scope not in ("system", "user") or not isinstance(owner, str):
            raise Refusal("allowlist_invalid",
                          f"allowlist at {path}: runtime {runtime_id} needs unit = id, scope and owner")

    def lookup(self, workflow_id: str) -> dict[str, Any]:
        entry = self.workflows.get(workflow_id)
        if entry is not None:
            return {"id": workflow_id, "kind": "workflow", **entry}
        runtime = self.runtimes.get(workflow_id)
        if runtime is not None:
            return {"id": workflow_id, "kind": "runtime", **runtime}
        for row in self.excluded:
            if row.get("unit") == workflow_id:
                raise Refusal("not_allowlisted",
                              f"{workflow_id} is excluded from the control allowlist: {row.get('reason')}")
        raise Refusal("unknown_workflow", f"{workflow_id} is not an allowlisted workflow")


# --- systemctl ------------------------------------------------------------------------
class Runner:
    def __init__(self, cfg: Config) -> None:
        self.cfg = cfg
        self.commands: list[dict[str, Any]] = []

    def run(self, argv: list[str]) -> tuple[int | None, str]:
        started = time.monotonic()
        try:
            completed = subprocess.run(argv, capture_output=True, text=True, check=False,
                                       timeout=COMMAND_TIMEOUT_SECONDS, env=CHILD_ENV)
            code, out, err = completed.returncode, completed.stdout, completed.stderr
        except (OSError, subprocess.TimeoutExpired) as exc:
            code, out, err = None, "", f"{type(exc).__name__}: {exc}"
        self.commands.append({"argv": list(argv), "exit": code, "stderr": err.strip()[:2000],
                              "seconds": round(time.monotonic() - started, 3)})
        return code, out

    def _prefix(self, scope: str) -> list[str]:
        return ["systemctl", "--user", f"--machine={self.cfg.user_manager}"] if scope == "user" else ["systemctl"]

    def show(self, scope: str, unit: str, properties: str) -> dict[str, str]:
        code, out = self.run(self._prefix(scope) + ["show", unit, f"--property={properties}",
                                                    "--timestamp=utc", "--no-pager"])
        if code != 0:
            raise CommandFailed(f"systemctl show {unit} exited {code}")
        values: dict[str, str] = {}
        for line in out.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key.strip()] = value.strip()
        return values

    def mutate(self, scope: str, verb: str, unit: str) -> None:
        flag = "--now" if verb in ("enable", "disable") else "--no-block"
        code, _ = self.run(self._prefix(scope) + [verb, flag, unit, "--no-pager"])
        if code != 0:
            raise CommandFailed(f"systemctl {verb} {unit} exited {code}")

    def calendar(self, spec: str) -> list[dt.datetime]:
        code, out = self.run(["systemd-analyze", "calendar", "--iterations=2", spec])
        if code != 0:
            raise ValueError(self.commands[-1]["stderr"] or f"systemd-analyze exited {code}")
        elapses = [parse_systemd_timestamp(line) for line in _ELAPSE_LINE.findall(out)]
        found = [value for value in elapses if value is not None]
        if len(found) < 2:
            raise ValueError("systemd-analyze printed fewer than two elapses")
        return found[:2]


# --- reconciliation -------------------------------------------------------------------
def _timer_view(unit: str, values: dict[str, str]) -> dict[str, Any]:
    return {
        "name": f"{unit}.timer",
        "activeState": values.get("ActiveState") or "unknown",
        "subState": values.get("SubState") or "unknown",
        "unitFileState": values.get("UnitFileState") or "unknown",
        "loadState": values.get("LoadState") or "unknown",
        "lastTriggerAt": iso(parse_systemd_timestamp(values.get("LastTriggerUSec"))),
        "nextElapseAt": iso(parse_systemd_timestamp(values.get("NextElapseUSecRealtime"))),
        "persistent": {"yes": True, "no": False}.get(values.get("Persistent", "")),
        "calendars": _CALENDAR_SPEC.findall(values.get("TimersCalendar", "")),
        "raw": {"lastTriggerAt": values.get("LastTriggerUSec") or None,
                "nextElapseAt": values.get("NextElapseUSecRealtime") or None},
    }


def _service_view(unit: str, values: dict[str, str]) -> dict[str, Any]:
    return {
        "name": f"{unit}.service",
        "activeState": values.get("ActiveState") or "unknown",
        "subState": values.get("SubState") or "unknown",
        "loadState": values.get("LoadState") or "unknown",
        "result": values.get("Result") or None,
        "invocationId": values.get("InvocationID") or None,
        "startedAt": iso(parse_systemd_timestamp(values.get("ExecMainStartTimestamp"))),
        "endedAt": iso(parse_systemd_timestamp(values.get("ExecMainExitTimestamp"))),
        "raw": {"startedAt": values.get("ExecMainStartTimestamp") or None,
                "endedAt": values.get("ExecMainExitTimestamp") or None},
    }


def _runtime_view(unit: str, values: dict[str, str]) -> dict[str, Any]:
    restarts = values.get("NRestarts") or ""
    return {**_service_view(unit, values),
            "unitFileState": values.get("UnitFileState") or "unknown",
            "nRestarts": int(restarts) if restarts.isdigit() else None}


def _views(unit: dict[str, Any]) -> list[dict[str, Any]]:
    return [view for view in (unit["timer"], unit["service"]) if view is not None]


def service_running(service: dict[str, Any]) -> bool:
    return service["activeState"] in {"active", "activating"} and service["subState"] in RUNNING_SUBSTATES


def timer_paused(timer: dict[str, Any]) -> bool:
    return timer["activeState"] == "inactive" or timer["unitFileState"] in {"disabled", "masked", "masked-runtime"}


def state_of(units: list[dict[str, Any]]) -> str:
    if any(service_running(unit["service"]) for unit in units):
        return "running"
    timers = [unit["timer"] for unit in units]
    if timers and all(timer_paused(timer) for timer in timers):
        return "paused"
    if any(timer["activeState"] == "active" for timer in timers):
        return "active"
    return "unknown"


def runtime_state_of(units: list[dict[str, Any]]) -> str:
    active = units[0]["service"]["activeState"]
    if active in RUNTIME_ACTIVE_STATES:
        return "active"
    if active in RUNTIME_PAUSED_STATES:
        return "paused"
    return "unknown"


def fingerprint(units: list[dict[str, Any]]) -> str:
    rows = sorted((view["name"], view["activeState"], view["subState"], view.get("unitFileState") or "")
                  for unit in units for view in _views(unit))
    return hashlib.sha256(json.dumps(rows).encode("utf-8")).hexdigest()


def reconcile(workflow: dict[str, Any], runner: Runner) -> dict[str, Any]:
    units = []
    for trigger in workflow["triggers"]:
        unit, scope = trigger["unit"], trigger["scope"]
        timer = runner.show(scope, f"{unit}.timer", TIMER_PROPERTIES)
        service = runner.show(scope, f"{unit}.service", SERVICE_PROPERTIES)
        units.append({"unit": unit, "scope": scope, "timer": _timer_view(unit, timer),
                      "service": _service_view(unit, service)})
    return {"state": state_of(units), "fingerprint": fingerprint(units), "units": units}


def reconcile_runtime(runtime: dict[str, Any], runner: Runner) -> dict[str, Any]:
    unit, scope = runtime["unit"], runtime["scope"]
    service = runner.show(scope, f"{unit}.service", RUNTIME_PROPERTIES)
    units = [{"unit": unit, "scope": scope, "timer": None, "service": _runtime_view(unit, service)}]
    return {"state": runtime_state_of(units), "fingerprint": fingerprint(units), "units": units}


def check_loaded(before: dict[str, Any]) -> None:
    for unit in before["units"]:
        for view in _views(unit):
            if view["loadState"] == "not-found":
                raise Refusal("unit_not_found", f"{view['name']} is allowlisted but systemd does not know it")
        gate = unit["timer"] or unit["service"]
        if gate.get("unitFileState") in MASKED_STATES or gate["loadState"] in MASKED_STATES:
            raise Refusal("masked", f"{gate['name']} is masked")


def next_scheduled(after: dict[str, Any] | None) -> str | None:
    if not after:
        return None
    timers = [unit["timer"] for unit in after["units"] if unit["timer"]]
    elapses = sorted(timer["nextElapseAt"] for timer in timers if timer["nextElapseAt"])
    return elapses[0] if elapses else None


# --- the resume preview ---------------------------------------------------------------
def _stamp_time(path: pathlib.Path) -> dt.datetime | None:
    try:
        return dt.datetime.fromtimestamp(path.stat().st_mtime, dt.timezone.utc)
    except OSError:
        return None


def _elapses(specs: list[str], runner: Runner) -> tuple[dt.datetime, dt.datetime, bool]:
    if not specs:
        raise ValueError("timer declares no OnCalendar")
    candidates = []
    for spec in specs:
        first, second = runner.calendar(spec)
        candidates.append((first, first - (second - first)))
    next_elapse = min(first for first, _ in candidates)
    previous = max(previous for _, previous in candidates)
    approximate = len(specs) > 1 or any(_IRREGULAR_SPEC.search(spec) for spec in specs)
    return next_elapse, previous, approximate


def _unit_implication(unit: dict[str, Any], runner: Runner, cfg: Config) -> dict[str, Any]:
    timer, name = unit["timer"], f"{unit['unit']}.timer"
    persistent = bool(timer["persistent"])
    stamp_path = cfg.stamp_dir(unit["scope"]) / f"stamp-{name}"
    stamp = _stamp_time(stamp_path)
    row: dict[str, Any] = {"unit": unit["unit"], "persistent": persistent, "catchUp": None,
                           "lastTriggerAt": iso(stamp), "missedElapseAt": None, "previousElapseAt": None,
                           "nextElapseAt": None, "approximate": False, "stampPath": str(stamp_path)}
    try:
        next_elapse, previous, approximate = _elapses(timer["calendars"], runner)
    except ValueError as exc:
        row["message"] = f"Catch-up unknown: {exc}. Assume it may fire immediately."
        return row
    catch_up = persistent and stamp is not None and stamp < previous
    row.update(catchUp=catch_up, nextElapseAt=iso(next_elapse), previousElapseAt=iso(previous),
               approximate=approximate, missedElapseAt=iso(previous) if catch_up else None)
    note = " (approximate)" if approximate else ""
    if catch_up:
        row["message"] = (f"Persistent=true — {name} last fired {iso(stamp)} and missed {iso(previous)}{note}: "
                          f'"enable --now" starts {unit["unit"]}.service immediately (catch-up). '
                          f"Next scheduled elapse after that: {iso(next_elapse)}.")
    elif persistent:
        row["message"] = (f"Persistent=true, no missed elapse (last {iso(stamp)}, previous {iso(previous)}{note}): "
                          f"next fire {iso(next_elapse)}.")
    else:
        row["message"] = f"Persistent=false — no catch-up; next fire {iso(next_elapse)}."
    return row


def preview_implication(before: dict[str, Any], runner: Runner, cfg: Config) -> dict[str, Any]:
    rows = [_unit_implication(unit, runner, cfg) for unit in before["units"]]
    catch_ups = [row["catchUp"] for row in rows]
    combined = True if any(value is True for value in catch_ups) else (None if None in catch_ups else False)
    missed = next((row["missedElapseAt"] for row in rows if row["catchUp"]), None)
    stamps = sorted(row["lastTriggerAt"] for row in rows if row["lastTriggerAt"])
    nexts = sorted(row["nextElapseAt"] for row in rows if row["nextElapseAt"])
    return {"persistent": any(row["persistent"] for row in rows), "catchUp": combined,
            "lastTriggerAt": stamps[-1] if stamps else None, "missedElapseAt": missed,
            "nextElapseAt": nexts[0] if nexts else None, "approximate": any(row["approximate"] for row in rows),
            "message": " · ".join(row["message"] for row in rows), "units": rows}


# --- receipts -------------------------------------------------------------------------
def validate_receipt(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["receipt is not an object"]
    errors = [f"missing {key}" for key in RECEIPT_KEYS if key not in data]
    if errors:
        return errors
    if data["schema"] != 1:
        errors.append("schema is not 1")
    if data["result"] not in RESULTS:
        errors.append(f"result outside {RESULTS}")
    if data["action"] is not None and data["action"] not in ALL_ACTIONS:
        errors.append(f"action outside {ALL_ACTIONS}")
    if data["stage"] is not None and data["stage"] not in STAGES:
        errors.append("stage outside preview/apply")
    refusal = data["refusal"]
    if data["result"] == "refused" and (not isinstance(refusal, dict) or refusal.get("code") not in REFUSAL_CODES):
        errors.append("refused without a refusal code")
    if data["result"] != "refused" and refusal is not None:
        errors.append("refusal on a non-refused receipt")
    actor = data["actor"]
    if not isinstance(actor, dict) or actor.get("kind") not in ACTOR_KINDS or not isinstance(actor.get("label"), str):
        errors.append("actor needs a kind in screen/cli and a label")
    if not isinstance(data["commands"], list) or any(
            not isinstance(row, dict) or not isinstance(row.get("argv"), list) or "exit" not in row
            for row in data["commands"]):
        errors.append("commands must list argv and exit per call")
    for key in ("before", "after"):
        value = data[key]
        if value is not None and (not isinstance(value, dict) or "state" not in value or "fingerprint" not in value):
            errors.append(f"{key} must be null or carry state and fingerprint")
    links = data["links"]
    if not isinstance(links, dict) or {"workflow", "run", "preview_receipt", "retry_of"} - set(links):
        errors.append("links must carry workflow, run, preview_receipt and retry_of")
    if not isinstance(data["confirm"], bool) or parse_iso(data["requested_at"]) is None or parse_iso(data["completed_at"]) is None:
        errors.append("confirm must be a bool and the timestamps ISO 8601")
    return errors


def write_receipt(receipt: dict[str, Any], root: pathlib.Path) -> pathlib.Path:
    errors = validate_receipt(receipt)
    if errors:
        raise ValueError(f"refusing to write an invalid receipt: {errors}")
    directory = pathlib.Path(root) / (receipt["workflow_id"] or "_refused")
    directory.mkdir(parents=True, exist_ok=True)
    os.chmod(directory, 0o755)
    final = directory / f"{receipt['receipt_id']}.json"
    temp = directory / f".{receipt['receipt_id']}.tmp"
    payload = (json.dumps(receipt, indent=1, sort_keys=True) + "\n").encode("utf-8")
    fd = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
    try:
        os.write(fd, payload)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.chmod(temp, 0o644)
    os.rename(temp, final)
    dir_fd = os.open(directory, os.O_RDONLY)
    try:
        os.fsync(dir_fd)
    finally:
        os.close(dir_fd)
    return final


def load_preview_receipt(root: pathlib.Path, workflow_id: str, token: Any) -> dict[str, Any] | None:
    if not isinstance(token, str) or not TOKEN_RE.match(token):
        return None
    path = pathlib.Path(root) / workflow_id / f"{token}.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return data if isinstance(data, dict) and not validate_receipt(data) else None


# --- request validation ---------------------------------------------------------------
def _short(value: Any) -> str:
    text = value if isinstance(value, str) else json.dumps(value, default=str)
    return text[:MAX_FIELD_CHARS]


def validate_request(request: Any) -> dict[str, Any]:
    if not isinstance(request, dict):
        raise Refusal("bad_request", "body must be one JSON object")
    unknown = sorted(set(request) - REQUEST_KEYS)
    if unknown:
        raise Refusal("bad_request", f"unknown request keys: {', '.join(_short(key) for key in unknown)}")
    if request.get("v", 1) != 1:
        raise Refusal("bad_request", "unsupported protocol version")
    for key in ("workflow_id", "action"):
        if not isinstance(request.get(key), str):
            raise Refusal("bad_request", f"{key} must be a string")
    for key in ("reason", "stage", "preview_token", "trigger", "retry_of"):
        value = request.get(key)
        if value is not None and not isinstance(value, str):
            raise Refusal("bad_request", f"{key} must be a string or null")
        if isinstance(value, str) and key != "reason" and len(value) > MAX_FIELD_CHARS:
            raise Refusal("bad_request", f"{key} is longer than {MAX_FIELD_CHARS} characters")
    if not isinstance(request.get("confirm", False), bool):
        raise Refusal("bad_request", "confirm must be a boolean")
    actor = request.get("actor")
    if actor is not None and (not isinstance(actor, dict)
                              or any(not isinstance(actor.get(key), (str, type(None))) for key in ("remote", "local", "label"))):
        raise Refusal("bad_request", "actor must carry string-or-null remote, local and label")
    action = request["action"]
    if action not in ALL_ACTIONS:
        raise Refusal("unknown_action", f"action must be one of {', '.join(ALL_ACTIONS)}")
    if not UNIT_RE.match(request["workflow_id"]) and not RUNTIME_RE.match(request["workflow_id"]):
        raise Refusal("bad_request", "workflow_id is outside the unit grammar")
    trigger = request.get("trigger")
    if trigger is not None and not UNIT_RE.match(trigger):
        raise Refusal("bad_request", "trigger is outside the unit grammar")
    stage = request.get("stage")
    if stage is not None and (action != "resume" or stage not in STAGES):
        raise Refusal("bad_request", "stage is preview or apply, and only for resume")
    return request


def choose_trigger(workflow: dict[str, Any], request: dict[str, Any], candidates: list[str],
                   none_message: str) -> str:
    units = [trigger["unit"] for trigger in workflow["triggers"]]
    wanted = request.get("trigger")
    if wanted is not None:
        if wanted not in units:
            raise Refusal("bad_request", f"trigger {wanted} is not a unit of {workflow['id']}")
        return wanted
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise Refusal("state_conflict", none_message)
    raise Refusal("trigger_required", f"{workflow['id']} has several triggers; name one", sorted(candidates))


def check_vocabulary(entry: dict[str, Any], action: str) -> None:
    if entry["kind"] == "runtime" and action not in RUNTIME_ACTIONS:
        raise Refusal("unknown_action",
                      f"{action} is not a runtime action; runtimes take {', '.join(RUNTIME_ACTIONS)}")
    if entry["kind"] == "workflow" and action not in ACTIONS:
        raise Refusal("unknown_action",
                      f"{action} is not a workflow action; workflows take {', '.join(ACTIONS)} (run_now starts a run)")


# --- the plan ---------------------------------------------------------------------------
def _scope_of(workflow: dict[str, Any], unit: str) -> str:
    return next(trigger["scope"] for trigger in workflow["triggers"] if trigger["unit"] == unit)


def plan(action: str, workflow: dict[str, Any], request: dict[str, Any],
         before: dict[str, Any] | None = None) -> list[tuple[str, str, str]]:
    """The mutating steps as (scope, verb, unit) — argv is assembled from these constants only."""
    if action == "pause":
        return [(trigger["scope"], "disable", f"{trigger['unit']}.timer") for trigger in workflow["triggers"]]
    if action == "resume":
        return [(trigger["scope"], "enable", f"{trigger['unit']}.timer") for trigger in workflow["triggers"]]
    units = [trigger["unit"] for trigger in workflow["triggers"]]
    if action in ("run_now", "retry"):
        unit = choose_trigger(workflow, request, units, "no trigger to start")
        return [(_scope_of(workflow, unit), "start", f"{unit}.service")]
    running = [unit["unit"] for unit in (before or {"units": []})["units"] if service_running(unit["service"])]
    unit = choose_trigger(workflow, request, running, "no run in progress to stop")
    if unit not in running:
        raise Refusal("state_conflict", f"{unit}.service is not running")
    return [(_scope_of(workflow, unit), "stop", f"{unit}.service")]


def _check_preconditions(action: str, request: dict[str, Any], before: dict[str, Any],
                         workflow: dict[str, Any]) -> None:
    state = before["state"]
    timers = [unit["timer"] for unit in before["units"]]
    if action == "pause" and all(timer_paused(timer) for timer in timers):
        raise Refusal("state_conflict", "already paused: every timer is inactive or disabled")
    if action == "resume" and not all(timer_paused(timer) for timer in timers):
        raise Refusal("state_conflict", f"workflow is {state}, not paused")
    if action in ("run_now", "retry") and state == "running":
        raise Refusal("state_conflict", "a run is in progress")
    if action == "retry" and not workflow.get("retry"):
        raise Refusal("not_idempotent", workflow.get("retry_reason") or "contract declares no idempotent operation")
    if action == "stop":
        if request.get("confirm") is not True:
            raise Refusal("confirmation_required", "stop needs confirm: true")
        if not (request.get("reason") or "").strip():
            raise Refusal("reason_required", "stop needs a non-empty reason")
        if state != "running":
            raise Refusal("state_conflict", "no run in progress to stop")


def plan_runtime(action: str, runtime: dict[str, Any]) -> tuple[str, str, str]:
    """(scope, verb, unit) — the verb is the action itself, argv from the allowlist entry only."""
    return runtime["scope"], action, f"{runtime['unit']}.service"


def _check_runtime_preconditions(action: str, request: dict[str, Any], before: dict[str, Any]) -> None:
    service = before["units"][0]["service"]
    name, active = service["name"], service["activeState"]
    if request.get("confirm") is not True:
        raise Refusal("confirmation_required", f"{action} needs confirm: true")
    if action in ("stop", "restart") and not (request.get("reason") or "").strip():
        raise Refusal("reason_required", f"{action} needs a non-empty reason")
    if action == "start" and active in RUNTIME_ACTIVE_STATES:
        raise Refusal("state_conflict", f"{name} is already {active}")
    if action in ("stop", "restart") and active == "deactivating":
        raise Refusal("state_conflict", f"{name} is still stopping")
    if action in ("stop", "restart") and active not in RUNTIME_ACTIVE_STATES:
        raise Refusal("state_conflict", f"{name} is {active}; nothing to {action}")


def _check_preview_token(request: dict[str, Any], before: dict[str, Any], cfg: Config, now: dt.datetime) -> dict[str, Any]:
    token = request.get("preview_token")
    if not token:
        raise Refusal("preview_required", "resume needs stage: preview first, then apply with its preview_token")
    preview = load_preview_receipt(cfg.receipts, request["workflow_id"], token)
    if preview is None or preview["result"] != "previewed" or preview["action"] != "resume" \
            or preview["workflow_id"] != request["workflow_id"]:
        raise Refusal("preview_required", "preview_token names no preview receipt for this workflow")
    completed = parse_iso(preview["completed_at"])
    if completed is None or (now - completed).total_seconds() > PREVIEW_TTL_SECONDS:
        raise Refusal("preview_stale", f"preview {token} is older than {PREVIEW_TTL_SECONDS} s; preview again")
    if (preview.get("before") or {}).get("fingerprint") != before["fingerprint"]:
        raise Refusal("preview_stale", f"state changed since preview {token}; preview again")
    return preview


class _Lock:
    def __init__(self, path: pathlib.Path) -> None:
        self.path, self.fd = pathlib.Path(path), -1

    def __enter__(self) -> "_Lock":
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.fd = os.open(self.path, os.O_RDWR | os.O_CREAT, 0o600)
        deadline = time.monotonic() + LOCK_WAIT_SECONDS
        while True:
            try:
                fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                return self
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    os.close(self.fd)
                    raise Refusal("locked", f"another broker held {self.path} for over {LOCK_WAIT_SECONDS} s")
                time.sleep(0.2)

    def __exit__(self, *exc: Any) -> None:
        fcntl.flock(self.fd, fcntl.LOCK_UN)
        os.close(self.fd)


# --- one request ------------------------------------------------------------------------
def _receipt_id(now: dt.datetime, action: str | None) -> str:
    return f"{now.strftime('%Y%m%dT%H%M%SZ')}-{action or 'invalid'}-{secrets.token_hex(3)}"


def _default_actor() -> dict[str, Any]:
    user = os.environ.get("SUDO_USER") or getpass.getuser()
    return {"kind": "cli", "label": f"{user} via cli", "remote": None, "local": None, "user": user, "peer": None}


def _execute(action: str, request: dict[str, Any], workflow: dict[str, Any], before: dict[str, Any],
             runner: Runner, cfg: Config, now: dt.datetime, out: dict[str, Any]) -> None:
    stage = request.get("stage")
    if action == "resume" and stage == "preview":
        out["implication"] = preview_implication(before, runner, cfg)
        out["result"] = "previewed"
        return
    if action == "resume":
        if stage != "apply":
            raise Refusal("preview_required", "resume needs stage: preview first, then apply with its preview_token")
        out["preview_receipt"] = _check_preview_token(request, before, cfg, now)["receipt_id"]
    steps = plan(action, workflow, request, before)
    out["trigger"] = steps[0][2].rsplit(".", 1)[0] if action in ("run_now", "retry", "stop") else None
    for scope, verb, unit in steps:
        runner.mutate(scope, verb, unit)
    if action in ("run_now", "retry"):
        scope, _, unit = steps[0]
        out["run_id"] = runner.show(scope, unit, RUN_PROPERTIES).get("InvocationID") or None
    if action == "stop":
        scope, _, unit = steps[0]
        _await_stop(runner, scope, unit, out)
    out["result"] = "applied"


def _await_stop(runner: Runner, scope: str, unit: str, out: dict[str, Any]) -> None:
    deadline = time.monotonic() + STOP_POLL_SECONDS
    while runner.show(scope, unit, "ActiveState").get("ActiveState") in {"active", "deactivating", "activating"}:
        if time.monotonic() >= deadline:
            out["note"] = f"{unit} still deactivating after {STOP_POLL_SECONDS} s; TimeoutStopSec applies"
            break
        time.sleep(1)


def _await_settle(runner: Runner, scope: str, unit: str, seconds: int, out: dict[str, Any]) -> None:
    """Watch the unit for RestartSec + 1: systemd accepted the verb either way, but a unit that
    fails inside the window is in its Restart=on-failure loop and the receipt says so."""
    journal = f"journalctl {'--user ' if scope == 'user' else ''}-u {unit}"
    deadline = time.monotonic() + max(0, seconds)
    while True:
        values = runner.show(scope, unit, SETTLE_PROPERTIES)
        active, sub = values.get("ActiveState"), values.get("SubState")
        if active == "failed" or (active == "activating" and sub == "auto-restart"):
            out["note"] = (f"{unit} is {active}/{sub} inside the {seconds} s settle window "
                           f"(NRestarts={values.get('NRestarts') or '?'}); read `{journal}` and run "
                           f"~/.config/buzz-team/check-loaded.sh")
            return
        if time.monotonic() >= deadline:
            return
        time.sleep(1)


def _await_stop_phase(runner: Runner, scope: str, unit: str, out: dict[str, Any]) -> bool:
    """A restart's stop half runs under TimeoutStopSec, longer than the settle window; the
    settle clock starts once the unit has left `deactivating`, else the receipt would read a
    restart that paused the runtime."""
    deadline = time.monotonic() + STOP_POLL_SECONDS
    while runner.show(scope, unit, "ActiveState").get("ActiveState") == "deactivating":
        if time.monotonic() >= deadline:
            out["note"] = (f"{unit} still deactivating after {STOP_POLL_SECONDS} s; TimeoutStopSec applies "
                           f"and the start half has not begun")
            return False
        time.sleep(1)
    return True


def _execute_runtime(action: str, runtime: dict[str, Any], runner: Runner, cfg: Config, out: dict[str, Any]) -> None:
    scope, verb, unit = plan_runtime(action, runtime)
    runner.mutate(scope, verb, unit)
    if action == "stop":
        _await_stop(runner, scope, unit, out)
    elif action == "start" or _await_stop_phase(runner, scope, unit, out):
        _await_settle(runner, scope, unit, cfg.start_settle, out)
    out["result"] = "applied"


def handle(request: Any, cfg: Config, clock: Callable[[], dt.datetime] | None = None,
           actor: dict[str, Any] | None = None) -> dict[str, Any]:
    clock = clock or cfg.clock
    requested_at = clock()
    runner = Runner(cfg)
    raw = request if isinstance(request, dict) else {}
    out: dict[str, Any] = {"result": None, "refusal": None, "before": None, "after": None,
                           "implication": None, "run_id": None, "preview_receipt": None, "note": None,
                           "trigger": raw.get("trigger") if isinstance(raw.get("trigger"), str) else None}
    workflow: dict[str, Any] | None = None
    action = raw.get("action") if raw.get("action") in ALL_ACTIONS else None
    try:
        if isinstance(request, Refusal):
            raise request
        validate_request(request)
        if actor and actor["kind"] == "screen":
            allowed, why = peer_allowed(actor.get("remote"), actor.get("local"))
            if not allowed:
                raise Refusal("peer_denied", why)
        workflow = Allowlist.load(cfg.allowlist).lookup(request["workflow_id"])
        check_vocabulary(workflow, action)
        if workflow["kind"] == "runtime":
            out["trigger"] = None
            _handle_runtime(action, request, workflow, runner, cfg, out)
        else:
            _handle_workflow(action, request, workflow, runner, cfg, requested_at, out)
    except Refusal as refusal:
        out["result"] = "refused"
        out["refusal"] = {"code": refusal.code, "message": refusal.message, "choices": refusal.choices}
    except CommandFailed as exc:
        out["result"], out["note"] = "failed", str(exc)
    completed_at = clock()
    receipt = _build_receipt(raw, action, workflow, actor or _default_actor(), requested_at, completed_at, runner, out)
    write_receipt(receipt, cfg.receipts)
    return _response(receipt, out)


def _handle_workflow(action: str, request: dict[str, Any], workflow: dict[str, Any], runner: Runner,
                     cfg: Config, requested_at: dt.datetime, out: dict[str, Any]) -> None:
    mutating = not (action == "resume" and request.get("stage") == "preview")
    with (_Lock(cfg.lock) if mutating else _NoLock()):
        out["before"] = reconcile(workflow, runner)
        check_loaded(out["before"])
        _check_preconditions(action, request, out["before"], workflow)
        try:
            _execute(action, request, workflow, out["before"], runner, cfg, requested_at, out)
        except CommandFailed as exc:
            out["result"], out["note"] = "failed", str(exc)
        if out["result"] != "previewed":
            out["after"] = reconcile(workflow, runner)


def _handle_runtime(action: str, request: dict[str, Any], runtime: dict[str, Any], runner: Runner,
                    cfg: Config, out: dict[str, Any]) -> None:
    with _Lock(cfg.lock):
        out["before"] = reconcile_runtime(runtime, runner)
        check_loaded(out["before"])
        _check_runtime_preconditions(action, request, out["before"])
        try:
            _execute_runtime(action, runtime, runner, cfg, out)
        except CommandFailed as exc:
            out["result"], out["note"] = "failed", str(exc)
        out["after"] = reconcile_runtime(runtime, runner)


class _NoLock:
    def __enter__(self) -> "_NoLock":
        return self

    def __exit__(self, *exc: Any) -> None:
        return None


def _build_receipt(raw: dict[str, Any], action: str | None, workflow: dict[str, Any] | None, actor: dict[str, Any],
                   requested_at: dt.datetime, completed_at: dt.datetime, runner: Runner, out: dict[str, Any]) -> dict[str, Any]:
    workflow_id = workflow["id"] if workflow else None
    run_id = out["run_id"]
    return {
        "schema": 1,
        "receipt_id": _receipt_id(requested_at, action),
        "workflow_id": workflow_id,
        "requested_workflow_id": _short(raw.get("workflow_id", "")),
        "action": action,
        "requested_action": _short(raw.get("action", "")),
        "stage": raw.get("stage") if raw.get("stage") in STAGES and action == "resume" else None,
        "trigger": out["trigger"],
        "actor": actor,
        "reason": raw.get("reason") if isinstance(raw.get("reason"), str) else None,
        "confirm": raw.get("confirm") is True,
        "requested_at": iso(requested_at),
        "completed_at": iso(completed_at),
        "before": out["before"],
        "after": out["after"],
        "result": out["result"],
        "refusal": out["refusal"],
        "commands": runner.commands,
        "run_id": run_id,
        "next_scheduled_run": next_scheduled(out["after"]),
        "catch_up_fired": (out["after"]["state"] == "running") if action == "resume" and out["result"] == "applied" else None,
        "implication": out["implication"],
        "note": out["note"],
        "links": {"workflow": f"/workflows/{workflow_id}" if workflow_id else None,
                  "run": f"/runs/{run_id}" if run_id else None,
                  "preview_receipt": out["preview_receipt"],
                  "retry_of": raw.get("retry_of") if action == "retry" and isinstance(raw.get("retry_of"), str) else None,
                  "agent": f"/agents/{workflow['owner']}" if workflow and workflow.get("kind") == "runtime" else None},
    }


def _response(receipt: dict[str, Any], out: dict[str, Any]) -> dict[str, Any]:
    result = receipt["result"]
    if result in ("applied", "previewed"):
        status = 200
    elif result == "failed":
        status = 500
    else:
        status = HTTP_STATUS.get(receipt["refusal"]["code"], 400)
    preview = None
    if result == "previewed":
        preview = {"implication": receipt["implication"], "preview_token": receipt["receipt_id"]}
    return {"v": 1, "result": result, "http_status": status, "refusal": receipt["refusal"],
            "receipt": receipt, "preview": preview}


# --- transport --------------------------------------------------------------------------
def _peer_credentials(fd: int) -> dict[str, int] | None:
    try:
        sock = socket.socket(fileno=os.dup(fd))
    except OSError:
        return None
    try:
        pid, uid, gid = struct.unpack("3i", sock.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
    except OSError:
        return None
    finally:
        sock.close()
    return {"uid": uid, "gid": gid, "pid": pid}


def read_request(stream: Any) -> Any:
    line = stream.readline(MAX_BODY_BYTES + 1)
    if len(line) > MAX_BODY_BYTES:
        return Refusal("bad_request", f"body exceeds {MAX_BODY_BYTES} bytes")
    try:
        return json.loads(line.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        return Refusal("bad_request", "body must be one JSON object")


def _screen_actor(request: Any, peer: dict[str, int] | None) -> dict[str, Any]:
    supplied = request.get("actor") if isinstance(request, dict) and isinstance(request.get("actor"), dict) else {}
    remote = supplied.get("remote") if isinstance(supplied.get("remote"), str) else None
    local = supplied.get("local") if isinstance(supplied.get("local"), str) else None
    label = supplied.get("label") if isinstance(supplied.get("label"), str) else f"screen from {remote or 'unknown'}"
    return {"kind": "screen", "label": label[:MAX_FIELD_CHARS], "remote": remote, "local": local,
            "user": None, "peer": peer}


def serve(stdin: Any, stdout: Any, cfg: Config) -> int:
    is_socket = stat.S_ISSOCK(os.fstat(stdin.fileno()).st_mode)
    peer = _peer_credentials(stdin.fileno()) if is_socket else None
    request: Any = read_request(stdin)
    if is_socket and (peer is None or peer["uid"] not in cfg.peer_uids):
        actor = {"kind": "screen", "label": "unknown peer", "remote": None, "local": None, "user": None, "peer": peer}
        request = Refusal("peer_denied", f"peer uid {peer['uid'] if peer else 'unknown'} is not allowed to connect")
    else:
        actor = _screen_actor(request, peer) if is_socket else _default_actor()
    response = handle(request, cfg, actor=actor)
    stdout.write((json.dumps(response, sort_keys=True) + "\n").encode("utf-8"))
    stdout.flush()
    return 0


def act(args: argparse.Namespace, cfg: Config) -> int:
    request = {"v": 1, "workflow_id": args.workflow_id, "action": args.action, "reason": args.reason,
               "stage": args.stage, "preview_token": args.preview_token, "trigger": args.trigger,
               "confirm": bool(args.confirm), "retry_of": args.retry_of}
    response = handle(request, cfg, actor=_default_actor())
    print(json.dumps(response, indent=1, sort_keys=True))
    return 0 if response["result"] in ("applied", "previewed") else 1


def config_from(args: argparse.Namespace) -> Config:
    uids = frozenset(int(item) for item in str(args.peer_uids).split(",") if item.strip())
    now = parse_iso(args.now) if args.now else None
    if args.now and now is None:
        raise SystemExit(f"--now is not ISO 8601: {args.now}")
    return Config(allowlist=pathlib.Path(args.allowlist), receipts=pathlib.Path(args.receipts), peer_uids=uids,
                  user_manager=args.user_manager, system_stamp_dir=pathlib.Path(args.system_stamp_dir),
                  user_stamp_dir=pathlib.Path(args.user_stamp_dir), lock=pathlib.Path(args.lock), now=now,
                  start_settle=args.start_settle)


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    env = os.environ.get
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--serve", action="store_true", help="one request on stdin, one response on stdout")
    parser.add_argument("--allowlist", default=env("CONTROL_BROKER_ALLOWLIST", "/etc/control-room/allowlist.json"))
    parser.add_argument("--receipts", default=env("CONTROL_BROKER_RECEIPTS", "/var/lib/control-room/receipts"))
    parser.add_argument("--peer-uids", default=env("CONTROL_BROKER_PEER_UIDS", "1000"))
    parser.add_argument("--user-manager", default=env("CONTROL_BROKER_USER_MANAGER", "dave@.host"))
    parser.add_argument("--system-stamp-dir", default=env("CONTROL_BROKER_SYSTEM_STAMP_DIR", "/var/lib/systemd/timers"))
    parser.add_argument("--user-stamp-dir", default=env("CONTROL_BROKER_USER_STAMP_DIR", "/home/dave/.local/share/systemd/timers"))
    parser.add_argument("--lock", default=env("CONTROL_BROKER_LOCK", "/run/control-room/lock"))
    parser.add_argument("--now", default=None, help="fixed clock, ISO 8601 (tests only)")
    parser.add_argument("--start-settle", type=int,
                        default=int(env("CONTROL_BROKER_START_SETTLE_SECONDS", str(START_SETTLE_SECONDS))),
                        help="seconds to watch a started or restarted runtime for a Restart= loop")
    modes = parser.add_subparsers(dest="mode")
    act_parser = modes.add_parser("act", help="build one request from the command line and print the response")
    act_parser.add_argument("action", choices=ALL_ACTIONS)
    act_parser.add_argument("workflow_id")
    act_parser.add_argument("--reason", default=None)
    act_parser.add_argument("--stage", default=None, choices=STAGES)
    act_parser.add_argument("--preview-token", default=None)
    act_parser.add_argument("--trigger", default=None)
    act_parser.add_argument("--confirm", action="store_true")
    act_parser.add_argument("--retry-of", default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    cfg = config_from(args)
    if args.mode == "act":
        return act(args, cfg)
    if args.serve:
        return serve(sys.stdin.buffer, sys.stdout.buffer, cfg)
    print("control_broker.py: pass --serve or `act <action> <workflow_id>`", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
