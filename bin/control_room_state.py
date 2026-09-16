#!/usr/bin/env python3
"""Control read-model for the Control Room (T5.3): trigger state, health, the `control` block,
cadence fold, last valid artifact and links. Pure functions over the trigger and receipt dicts
control_room_api assembles; nothing here reads a file or a bus.

`control` is the browser's contract (T5.3 brief § Seams b): state, source, next run (estimated
from last trigger + cadence when systemd prints none), last trigger, persistence, lastAction
(None until T5.3a's reader is passed in) and the five actions with a reason for each one that
is disabled. Execution of any action is entirely outside this module.
"""
from __future__ import annotations

import datetime as dt
from typing import Any, Callable

from control_broker import RUNNING_SUBSTATES
from workflow_receipt import iso_utc, parse_time

API_VERSION = "v1"
REPO_GITHUB = "https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium/blob/main"
DEV_PLAN_TRACKER = "https://app.notion.com/p/071af559943649fb86494b88a67106a6"
DEV_PLAN_DOC = f"{REPO_GITHUB}/docs/dev-plan-2026-09.md"
RETRY_REASON = "contract declares no idempotent operation (T5.3a defines the declaration)"
ACTIVE_STATES = {"active", "activating", "reloading"}
PAUSED_STATES = {"inactive", "deactivating"}
CONTROL_STATES = ("paused", "active", "running", "unknown")
ACTION_IDS = ("pause", "resume", "run_now", "retry", "stop")
ROLES = ("agent-workflow", "system-workflow", "agent-runtime")
ROLE_OF_SURFACE = {
    "scheduled": "agent-workflow",
    "buzz_dispatch": "agent-workflow",
    "platform": "system-workflow",
    "interactive": "agent-runtime",
}


def role_of(surface: Any) -> str:
    """The row's role, from its manifest surface. A surface outside the vocabulary raises rather
    than reading as a fourth role: `unknown` here would be a row the screen files nowhere."""
    try:
        return ROLE_OF_SURFACE[surface]
    except KeyError:
        raise ValueError(f"surface {surface!r} has no role; expected one of {sorted(ROLE_OF_SURFACE)}") from None


def service_running(systemd: dict[str, Any]) -> bool:
    service = systemd["service"]
    return service["activeState"] in {"activating", "active"} and service["subState"] in RUNNING_SUBSTATES


def trigger_state(systemd: dict[str, Any]) -> str:
    if systemd["kind"] == "timer":
        if service_running(systemd):
            return "running"
        active = (systemd["timer"] or {}).get("activeState", "unknown")
    else:
        active = systemd["service"]["activeState"]
    if active in ACTIVE_STATES:
        return "active"
    if active in PAUSED_STATES:
        return "paused"
    return "unknown"


def health(receipt: dict[str, Any] | None, triggers: list[dict[str, Any]]) -> str:
    timer_states = [trigger["state"] for trigger in triggers if trigger["kind"] == "timer"]
    if "running" in timer_states:
        return "running"
    if timer_states and all(state == "paused" for state in timer_states):
        return "paused"
    if receipt is None:
        return "unknown"
    outcome = receipt["terminal"]["outcome"]
    if outcome == "failed" or any(item.get("status") == "failed" for item in receipt["assertions"]):
        return "failed"
    if outcome == "skipped":
        return "incomplete"
    return "healthy"


def control_state(triggers: list[dict[str, Any]]) -> str:
    considered = [trigger for trigger in triggers if trigger["kind"] == "timer"] or triggers
    states = [trigger["state"] for trigger in considered]
    if "running" in states:
        return "running"
    if states and all(state == "paused" for state in states):
        return "paused"
    if "active" in states:
        return "active"
    return "unknown"


def control_actions(state: str, source: str) -> list[dict[str, Any]]:
    def action(action_id: str, enabled: bool, reason: str) -> dict[str, Any]:
        return {"id": action_id, "enabled": enabled, "reason": None if enabled else reason}
    return [
        action("pause", state in {"active", "running"}, f"workflow is {state}, not active"),
        action("resume", state == "paused", f"workflow is {state}, not paused"),
        action("run_now", state != "running" and source == "systemd",
               "a run is in progress" if state == "running" else "systemd state unavailable"),
        action("retry", False, RETRY_REASON),
        action("stop", state == "running", f"workflow is {state}, no run to stop"),
    ]


def _estimated_next(last_trigger: str, cadence: dict[str, Any]) -> str | None:
    parsed = parse_time(last_trigger)
    if parsed is None or cadence.get("status") != "measured":
        return None
    return iso_utc(parsed + dt.timedelta(seconds=cadence["seconds"]))


def control_for(
    logical_id: str,
    triggers: list[dict[str, Any]],
    cadence: dict[str, Any],
    control_reader: Callable[[str], dict[str, Any] | None] | None = None,
) -> dict[str, Any]:
    timers = [trigger["systemd"]["timer"] for trigger in triggers if trigger["systemd"]["timer"]]
    source = "systemd" if any(trigger["systemd"]["status"] == "available" for trigger in triggers) else "unavailable"
    state = control_state(triggers) if source == "systemd" else "unknown"
    last_triggers = sorted(timer["lastTriggerAt"] for timer in timers if timer["lastTriggerAt"])
    next_runs = sorted(timer["nextRunAt"] for timer in timers if timer["nextRunAt"])
    last_trigger = last_triggers[-1] if last_triggers else None
    next_run, estimated = (next_runs[0] if next_runs else None), False
    if next_run is None and state == "active" and last_trigger:
        next_run = _estimated_next(last_trigger, cadence)
        estimated = next_run is not None
    if state == "paused":
        next_run, estimated = None, False
    persistent = cadence.get("persistent")
    if persistent is None:
        persistent = next((timer["persistent"] for timer in timers if timer["persistent"] is not None), None)
    return {
        "state": state,
        "source": source,
        "nextRunAt": next_run,
        "nextRunEstimated": estimated,
        "lastTriggerAt": last_trigger,
        "persistent": persistent,
        "lastAction": control_reader(logical_id) if control_reader else None,
        "actions": control_actions(state, source),
    }


def no_cadence(error: str) -> dict[str, Any]:
    return {"status": "unavailable", "seconds": None, "source": None, "spec": None,
            "persistent": None, "randomizedDelaySec": None, "error": error}


def fold_cadence(triggers: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [trigger["cadence"] for trigger in triggers if trigger["cadence"]["status"] == "measured"]
    if measured:
        return min(measured, key=lambda value: value["seconds"])
    unavailable = [trigger["cadence"] for trigger in triggers if trigger["kind"] == "timer"]
    return unavailable[0] if unavailable else no_cadence("no timer trigger")


def _artifact_of(receipt: dict[str, Any], now: dt.datetime) -> dict[str, Any] | None:
    artifact = receipt.get("artifact") if isinstance(receipt.get("artifact"), dict) else None
    state_change = receipt.get("state_change") if isinstance(receipt.get("state_change"), dict) else None
    ended = parse_time(receipt.get("ended_at"))
    base = {"runId": receipt.get("run_id"), "endedAt": receipt.get("ended_at"),
            "ageSeconds": int((now - ended).total_seconds()) if ended else None}
    if artifact and artifact.get("uri"):
        return {**base, "uri": artifact["uri"], "title": artifact.get("title"), "kind": "artifact"}
    if state_change and state_change.get("evidence"):
        return {**base, "uri": None, "title": state_change.get("kind") or state_change.get("evidence"),
                "kind": "state_change"}
    return None


def last_valid_artifact(receipts: list[dict[str, Any]], now: dt.datetime) -> dict[str, Any] | None:
    for receipt in receipts:
        if (receipt.get("terminal") or {}).get("outcome") != "artifact":
            continue
        found = _artifact_of(receipt, now)
        if found:
            return found
    return None


def links_for(logical_id: str, contract: dict[str, Any] | None) -> dict[str, Any]:
    return {
        "contractLocal": f"/api/{API_VERSION}/workflows/{logical_id}/contract" if contract else None,
        "contractGithub": f"{REPO_GITHUB}/{contract['path']}" if contract else None,
        "devPlanTracker": DEV_PLAN_TRACKER,
        "devPlanDoc": DEV_PLAN_DOC,
        "taskIds": list(contract.get("task_ids") or []) if contract else [],
    }
