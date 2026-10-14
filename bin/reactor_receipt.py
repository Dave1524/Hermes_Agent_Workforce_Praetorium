#!/usr/bin/env python3
"""The board reactor's receipt producer: one vantage-`run` receipt per health flip.

The reactor is an always-on service, so the contract executor refuses it (no run to decide a
check from); its receipts are written here, in the one shape `workflow_receipt` owns. `ok` and
`transient` are artifacts whose state change is the flip; `capped` and `permanent` are `failed`
with `<health>: <reason>`. Usage and cost are unavailable: the reactor runs no model.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_receipt  # noqa: E402

WORKFLOW = "board-reactor"
OWNER = "claudius"
FAILED_HEALTH = {"capped", "permanent"}


def evidence(health: str, reason: str | None, detail: str = "") -> str:
    return f"reactor: health={health} reason={reason or 'none'} {detail}".strip()


def terminal(health: str, reason: str | None) -> dict[str, Any]:
    if health in FAILED_HEALTH:
        return {"outcome": "failed", "reason": f"{health}: {reason}"}
    return {"outcome": "artifact", "reason": None}


def build(health: str, reason: str | None, now: dt.datetime, detail: str = "") -> dict[str, Any]:
    stamp = workflow_receipt.iso_utc(now)
    return {
        "schema_version": workflow_receipt.SCHEMA_VERSION,
        "workflow_id": WORKFLOW,
        "run_id": f"{WORKFLOW}-{now.astimezone(dt.timezone.utc):%Y%m%dT%H%M%S%fZ}-{health}",
        "unit": f"{WORKFLOW}.service",
        "agent": OWNER,
        "model": None,
        "vantage": workflow_receipt.RUN_VANTAGE,
        "started_at": stamp,
        "ended_at": stamp,
        "terminal": terminal(health, reason),
        "state_change": {"evidence": evidence(health, reason, detail)},
        "assertions": [],
        "usage": workflow_receipt.unavailable_usage(),
        "cost": workflow_receipt.unavailable_cost(),
        "skills": workflow_receipt.unavailable_skills(),
        "next_action": {"actor": None, "action": None},
        "parent_run_id": None,
    }


def write(health: str, reason: str | None, now: dt.datetime, root: pathlib.Path, detail: str = "") -> pathlib.Path:
    return workflow_receipt.write(build(health, reason, now, detail), root)
