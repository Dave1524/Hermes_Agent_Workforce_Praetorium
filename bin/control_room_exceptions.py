#!/usr/bin/env python3
"""Exception classifier for the Control Room (T5.3): one row per (workflow, kind), pure.

An exception is a condition the operator owes an action on. Unknown is not one: a workflow with
no receipt, a receipt with no consumption record, a next action with no due date all yield no
row. Paused is owned state, not an exception — paused workflows keep the rows that are owed
before resume (a failed run, a stale input, an overdue action) and lose the ones that only an
active timer can produce (a missed cadence, an artifact rate over runs that are not happening).
`stale-input` is a free-text heuristic over the reason and failed assertion ids; a typed cause
field is T5.2/T5.4's to add, and the row says so.
"""
from __future__ import annotations

import datetime as dt
import re
from typing import Any

from workflow_receipt import iso_utc, parse_time

KINDS = ("failed", "stale-input", "missing-artifact", "missed-cadence", "overdue-next-action", "unconsumed-output",
         "dependency-down")
UNCONSUMED_GRACE_SECONDS = 7 * 86400
MISSED_GRACE_SECONDS = 900
NEXT_RUN_SLACK_SECONDS = 3600
STALE_INPUT_PATTERN = re.compile(r"\b(stale|dirty|behind|not current|out of date)\b", re.IGNORECASE)
INPUT_CHECK_PATTERN = re.compile(r"(stale|fresh|mirror|sync|current)", re.IGNORECASE)
STALE_INPUT_NOTE = ("heuristic: the reason text or a failed check id matched the stale-input pattern; "
                    "a typed cause field is T5.2/T5.4's to add")
CONSUMPTION_SIGNALS = ("opened", "approved", "sent", "marked_useful")
REQUIRED_ACTION = {
    "failed": "Inspect the failed run, then fix and re-run or retire the workflow.",
    "stale-input": "Refresh the input (vault mirror sync or source), then re-run.",
    "missing-artifact": "Confirm why the run produced no artifact; clear the blocker and re-run.",
    "missed-cadence": "Check the timer and the service journal: the scheduled run left no receipt.",
    "overdue-next-action": "Do the owed next action or move its due date.",
    "unconsumed-output": "Open, approve, send or mark the output useful, or retire the workflow.",
    "dependency-down": "Start the required unit or resume its workflow; until then every run is refused at pre-flight.",
}


def classify(workflow_item: dict[str, Any], receipts: list[dict[str, Any]], now: dt.datetime) -> list[dict[str, Any]]:
    context = _Context(workflow_item, receipts, now)
    rows = [row for rule in (_failed_or_stale, _missing_artifact, _missed_cadence, _overdue, _unconsumed, _dependency_down)
            for row in rule(context)]
    return sorted(rows, key=lambda row: (KINDS.index(row["kind"]), row["since"] or ""))


class _Context:
    def __init__(self, item: dict[str, Any], receipts: list[dict[str, Any]], now: dt.datetime) -> None:
        self.item = item
        self.receipts = receipts
        self.now = now
        self.latest = receipts[0] if receipts else None
        control = item.get("control") or {}
        self.state = control.get("state") or "unknown"
        self.paused = self.state == "paused"
        self.last_trigger = parse_time(control.get("lastTriggerAt"))
        self.next_run = parse_time(control.get("nextRunAt"))

    def row(self, kind: str, issue: str, *, since: str | None, receipt: dict[str, Any] | None = None,
            failed: list[str] | None = None, also_failed: bool = False, action: str | None = None) -> dict[str, Any]:
        artifact = (receipt or {}).get("artifact") if isinstance((receipt or {}).get("artifact"), dict) else None
        return {
            "kind": kind,
            "workflowId": self.item.get("id"),
            "owner": self.item.get("owner"),
            "issue": issue,
            "failedAssertions": failed or [],
            "requiredAction": action or REQUIRED_ACTION[kind],
            "evidence": {"runId": (receipt or {}).get("run_id"), "artifactUri": (artifact or {}).get("uri")},
            "paused": self.paused,
            "since": since,
            "alsoFailed": also_failed,
        }


def _failed_ids(receipt: dict[str, Any]) -> list[str]:
    return [str(item.get("id")) for item in receipt.get("assertions") or [] if item.get("status") == "failed"]


def _is_failed(receipt: dict[str, Any]) -> bool:
    return receipt["terminal"]["outcome"] == "failed" or bool(_failed_ids(receipt))


def _is_stale_input(receipt: dict[str, Any]) -> bool:
    if receipt["terminal"]["outcome"] not in {"decline", "failed"}:
        return False
    reason = receipt["terminal"].get("reason") or ""
    return bool(STALE_INPUT_PATTERN.search(reason)) or any(INPUT_CHECK_PATTERN.search(i) for i in _failed_ids(receipt))


def _failed_or_stale(ctx: _Context) -> list[dict[str, Any]]:
    latest = ctx.latest
    if latest is None:
        return []
    failed_ids = _failed_ids(latest)
    reason = latest["terminal"].get("reason") or "run ended failed"
    named = f"{reason} (failed checks: {', '.join(failed_ids)})" if failed_ids and not any(i in reason for i in failed_ids) else reason
    action = _next_action_text(latest)
    if _is_stale_input(latest):
        issue = f"{named} — {STALE_INPUT_NOTE}"
        return [ctx.row("stale-input", issue, since=latest.get("ended_at"), receipt=latest, failed=failed_ids,
                        also_failed=_is_failed(latest))]
    if _is_failed(latest):
        return [ctx.row("failed", named, since=latest.get("ended_at"), receipt=latest, failed=failed_ids, action=action)]
    return []


def _next_action_text(receipt: dict[str, Any]) -> str | None:
    next_action = receipt.get("next_action")
    return next_action.get("action") if isinstance(next_action, dict) and next_action.get("action") else None


def _missing_artifact(ctx: _Context) -> list[dict[str, Any]]:
    latest = ctx.latest
    if latest is not None and latest["terminal"]["outcome"] == "skipped":
        issue = latest["terminal"].get("reason") or "run skipped without a reason"
        return [ctx.row("missing-artifact", issue, since=latest.get("ended_at"), receipt=latest)]
    if ctx.paused or not _declares_artifact(ctx.item):
        return []
    eligible, rate = ctx.item.get("eligibleRuns") or 0, ctx.item.get("validArtifactRate")
    if eligible >= 1 and rate == 0:
        issue = f"{eligible} eligible run(s), none ended with the declared artifact"
        return [ctx.row("missing-artifact", issue, since=(latest or {}).get("ended_at"), receipt=latest)]
    return []


def _declares_artifact(item: dict[str, Any]) -> bool:
    contract = item.get("contract")
    return isinstance(contract, dict) and bool(contract.get("artifact"))


def _missed_cadence(ctx: _Context) -> list[dict[str, Any]]:
    if ctx.paused or ctx.state == "running":
        return []
    if ctx.state == "active" and ctx.last_trigger and not _receipt_since(ctx, ctx.last_trigger):
        issue = f"timer fired {iso_utc(ctx.last_trigger)} and no receipt followed"
        return [ctx.row("missed-cadence", issue, since=iso_utc(ctx.last_trigger))]
    if ctx.next_run and ctx.next_run < ctx.now - dt.timedelta(seconds=NEXT_RUN_SLACK_SECONDS):
        issue = f"next run was due {iso_utc(ctx.next_run)} and has not started"
        return [ctx.row("missed-cadence", issue, since=iso_utc(ctx.next_run))]
    return []


def _receipt_since(ctx: _Context, trigger: dt.datetime) -> bool:
    floor = trigger - dt.timedelta(seconds=MISSED_GRACE_SECONDS)
    return any((parse_time(r.get("started_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc)) >= floor
               for r in ctx.receipts)


def _overdue(ctx: _Context) -> list[dict[str, Any]]:
    latest = ctx.latest
    next_action = (latest or {}).get("next_action")
    if not isinstance(next_action, dict):
        return []
    due = parse_time(next_action.get("due_at"))
    if due is None or due >= ctx.now:
        return []
    issue = f"{next_action.get('actor') or 'someone'} owes: {next_action.get('action') or 'unnamed action'} (due {iso_utc(due)})"
    return [ctx.row("overdue-next-action", issue, since=iso_utc(due), receipt=latest, action=_next_action_text(latest))]


def _unconsumed(ctx: _Context) -> list[dict[str, Any]]:
    last_valid = ctx.item.get("lastValidArtifact")
    if not isinstance(last_valid, dict):
        return []
    receipt = next((r for r in ctx.receipts if r.get("run_id") == last_valid.get("runId")), None)
    consumption = (receipt or {}).get("consumption")
    if not isinstance(consumption, dict) or any(consumption.get(s) is not False for s in CONSUMPTION_SIGNALS):
        return []
    age = last_valid.get("ageSeconds")
    if not isinstance(age, (int, float)) or age <= UNCONSUMED_GRACE_SECONDS:
        return []
    issue = f"artifact from {last_valid.get('endedAt')} not opened, approved, sent or marked useful after {int(age // 86400)} days"
    return [ctx.row("unconsumed-output", issue, since=last_valid.get("endedAt"), receipt=receipt)]


def _dependency_down(ctx: _Context) -> list[dict[str, Any]]:
    """`requires` rows are tri-state (bin/workflow_requires.py); only a requirement known down
    is owed an action, and a paused workflow is not running into it."""
    if ctx.paused:
        return []
    down = [r for r in ctx.item.get("requires") or [] if isinstance(r, dict) and r.get("satisfied") is False]
    if not down:
        return []
    issue = "requires " + "; ".join(f"{r.get('unit')} ({r.get('scope')}): {r.get('state')}" for r in down)
    return [ctx.row("dependency-down", issue, since=None)]
