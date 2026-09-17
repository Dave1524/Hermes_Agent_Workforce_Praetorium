#!/usr/bin/env python3
"""Benefit row per workflow for the Control Room (T5.3): measured from receipts, decided in
design/benefit-ledger.toml, and `Unknown` wherever neither speaks.

Nothing here estimates. Eligible runs are artifact/decline/failed receipts (a skipped run never
ran) that no operator has closed (workflow_receipt.judged); the valid-artifact rate is artifact / eligible; latency is the median run duration over
eligible runs; consumption is four separate counts of `true` over artifact receipts that carry
a `consumption` object, and `unavailable` when none does. The decision, baseline and manual
minutes avoided come from the ledger only — T5.4 owns its entries — and a decision outside
the vocabulary is an error named to the operator, never coerced.
"""
from __future__ import annotations

import pathlib
import statistics
import tomllib
from typing import Any

from workflow_receipt import judged, parse_time

DECISIONS = ("Keep", "Improve", "Retire", "Unknown")
ELIGIBLE_OUTCOMES = {"artifact", "decline", "failed"}
CONSUMPTION_SIGNALS = ("opened", "approved", "sent", "marked_useful")
LEDGER_PATH = pathlib.Path("design") / "benefit-ledger.toml"
LEDGER_FIELDS = ("baseline", "manual_minutes_avoided", "decided_at", "decided_by", "evidence")


def load_ledger(repo: pathlib.Path,
                path: pathlib.Path | None = None) -> tuple[dict[str, dict[str, Any]] | None, list[str]]:
    path = pathlib.Path(path) if path else pathlib.Path(repo) / LEDGER_PATH
    if not path.is_file():
        return None, [f"benefit ledger unavailable: {LEDGER_PATH}"]
    try:
        data = tomllib.loads(path.read_text())
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return None, [f"{LEDGER_PATH}: {type(exc).__name__}: {exc}"]
    entries: dict[str, dict[str, Any]] = {}
    errors: list[str] = []
    for index, entry in enumerate(data.get("workflow", [])):
        problem = _ledger_entry_problem(entry, index)
        if problem:
            errors.append(problem)
            continue
        entries[str(entry["id"])] = dict(entry)
    return entries, errors


def _ledger_entry_problem(entry: Any, index: int) -> str | None:
    if not isinstance(entry, dict) or not entry.get("id"):
        return f"{LEDGER_PATH}: [[workflow]] #{index + 1} has no id"
    decision = entry.get("decision")
    if decision not in DECISIONS:
        return f"{entry['id']}: decision {decision!r} is not one of {'|'.join(DECISIONS)}"
    return None


def eligible_receipts(receipts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in receipts if judged(r) and (r.get("terminal") or {}).get("outcome") in ELIGIBLE_OUTCOMES]


def valid_artifact_rate(receipts: list[dict[str, Any]]) -> tuple[int, float | None]:
    eligible = eligible_receipts(receipts)
    if not eligible:
        return 0, None
    artifacts = sum(1 for r in eligible if r["terminal"]["outcome"] == "artifact")
    return len(eligible), artifacts / len(eligible)


def _duration(receipt: dict[str, Any]) -> float | None:
    started, ended = parse_time(receipt.get("started_at")), parse_time(receipt.get("ended_at"))
    if started is None or ended is None:
        return None
    return (ended - started).total_seconds()


def median_latency(receipts: list[dict[str, Any]]) -> float | None:
    durations = [d for d in (_duration(r) for r in eligible_receipts(receipts)) if d is not None]
    return statistics.median(durations) if durations else None


def consumption_counts(receipts: list[dict[str, Any]]) -> dict[str, Any]:
    carrying = [r["consumption"] for r in receipts
                if (r.get("terminal") or {}).get("outcome") == "artifact" and isinstance(r.get("consumption"), dict)]
    if not carrying:
        return {"status": "unavailable", **{signal: None for signal in CONSUMPTION_SIGNALS}, "artifactRuns": 0}
    counts = {signal: sum(1 for c in carrying if c.get(signal) is True) for signal in CONSUMPTION_SIGNALS}
    return {"status": "measured", **counts, "artifactRuns": len(carrying)}


def benefit_row(workflow_item: dict[str, Any], receipts: list[dict[str, Any]],
                ledger_entry: dict[str, Any] | None) -> dict[str, Any]:
    entry = ledger_entry or {}
    eligible, rate = valid_artifact_rate(receipts)
    return {
        "workflowId": workflow_item.get("id"),
        "decision": entry.get("decision") or "Unknown",
        "baseline": entry.get("baseline"),
        "eligibleRuns": eligible,
        "validArtifactRate": rate,
        "latencySeconds": median_latency(receipts),
        "consumption": consumption_counts(receipts),
        "manualMinutesAvoided": entry.get("manual_minutes_avoided"),
        "decidedAt": str(entry["decided_at"]) if entry.get("decided_at") is not None else None,
        "decidedBy": entry.get("decided_by"),
        "evidence": entry.get("evidence"),
    }
