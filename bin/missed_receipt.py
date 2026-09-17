#!/usr/bin/env python3
"""When a timer fire is owed a receipt: one answer for the Control Room's `missed-cadence`
exception and the incident sweep's `incomplete-run`, which until 2026-09-17 flagged the
whole sweep-receipted fleet for a day after every fire and every timer the fleet resume
had touched.

Two things systemd reports are not what they look like. `LastTriggerUSec` is not always a
fire: a `Persistent=` timer reads it back from its stamp file when it starts, and the fleet
resume touches that stamp on purpose so a resumed timer does not catch up, so a trigger at
or before the timer's own `ActiveEnterTimestamp` ran nothing. And a fire that ran is owed
a receipt only once `workflow-receipt-sweep` has looked after it had time to finish: most
standing timers are receipted by the sweep, daily, so between a fire and the next sweep the
absence of a receipt is the normal case. A fire the sweep has not judged yet is unknown,
and unknown is not an exception.
"""
from __future__ import annotations

import datetime as dt
from typing import Any

from workflow_receipt import SWEEP_WORKFLOW_ID, parse_time


def fired_at(last_trigger: str | None, active_since: str | None) -> str | None:
    trigger, activation = parse_time(last_trigger), parse_time(active_since)
    if trigger is None:
        return None
    if activation is not None and trigger <= activation:
        return None
    return last_trigger


def sweep_started_at(workflows: list[dict[str, Any]]) -> dt.datetime | None:
    sweep = next((w for w in workflows if w.get("id") == SWEEP_WORKFLOW_ID), None)
    return parse_time(((sweep or {}).get("lastRun") or {}).get("startedAt"))


def missed_fire(fired: dt.datetime | None, newest_receipt_started: dt.datetime | None,
                swept_at: dt.datetime | None, grace_seconds: int) -> bool:
    if fired is None or swept_at is None:
        return False
    slack = dt.timedelta(seconds=grace_seconds)
    if swept_at < fired + slack:
        return False
    return newest_receipt_started is None or newest_receipt_started < fired - slack
