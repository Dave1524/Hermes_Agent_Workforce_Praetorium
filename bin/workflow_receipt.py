#!/usr/bin/env python3
"""Workflow run receipt, schema version 1 — the one place that knows the field names.

bin/contract_exec.py writes one receipt per run; bin/control_room_api.py reads them. Moved
out of the API on 2026-09-11 (T5.1) so the writer and the reader validate ONE shape: a
receipt the executor can write is a receipt the Control Room can read, by construction.

Two rules the shape enforces rather than documents:
- Exactly one terminal outcome, from TERMINAL_OUTCOMES. A receipt without one does not
  validate and `write` refuses it, so silent success cannot reach disk.
- Usage and cost are `measured` or `unavailable`, and `unavailable` carries nulls, never
  zeros. Today's `tokens=unknown` and the frozen OpenRouter `0.000000` read as measured
  zero downstream; this schema makes that unrepresentable.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import tempfile
from typing import Any

SCHEMA_VERSION = 1
TERMINAL_OUTCOMES = {"artifact", "decline", "failed", "skipped"}
ASSERTION_STATUSES = {"passed", "failed", "not_applicable"}
MEASUREMENT_STATUSES = {"measured", "unavailable"}
USAGE_FIELDS = ("input_tokens", "output_tokens", "cache_tokens", "total_tokens")
COST_FIELDS = ("amount",)
CLAUDE_CODE_SOURCE = "claude-code"
CLAUDE_CODE_CURRENCY = "USD"


def utc_now() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def iso_utc(value: dt.datetime | None = None) -> str:
    value = value or utc_now()
    return value.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def parse_time(value: Any) -> dt.datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    raw = value.strip().replace("Z", "+00:00")
    try:
        parsed = dt.datetime.fromisoformat(raw)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=dt.timezone.utc)
    return parsed.astimezone(dt.timezone.utc)


# --- usage and cost -----------------------------------------------------------------------
def unavailable_usage() -> dict[str, Any]:
    return {"status": "unavailable", **{field: None for field in USAGE_FIELDS}}


def unavailable_cost() -> dict[str, Any]:
    return {"status": "unavailable", "amount": None, "currency": None, "source": None,
            "confidence": None}


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def usage_from_claude_code(envelope: Any) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """(usage, cost, model) from a `claude -p --output-format json` result envelope.

    `measured` only when the envelope carries all four token counts as integers; a zero is
    then the runtime's zero. Anything less is `unavailable` — never a partial sum rendered
    as a total. Cost is measured only when `total_cost_usd` is a number; its confidence is
    `modelUsage.<model>.costBasis`, and that map's key names the model that actually ran.
    """
    if not isinstance(envelope, dict):
        return unavailable_usage(), unavailable_cost(), None
    raw = envelope.get("usage")
    usage = unavailable_usage()
    if isinstance(raw, dict):
        counts = [_int_or_none(raw.get(k)) for k in ("input_tokens", "output_tokens",
                                                     "cache_creation_input_tokens",
                                                     "cache_read_input_tokens")]
        if all(c is not None for c in counts):
            cache = counts[2] + counts[3]
            usage = {"status": "measured", "input_tokens": counts[0], "output_tokens": counts[1],
                     "cache_tokens": cache, "total_tokens": counts[0] + counts[1] + cache}
    models = envelope.get("modelUsage")
    model, basis = None, None
    if isinstance(models, dict) and models:
        model = next(iter(models))
        entry = models[model]
        basis = entry.get("costBasis") if isinstance(entry, dict) else None
    amount = envelope.get("total_cost_usd")
    cost = unavailable_cost()
    if isinstance(amount, (int, float)) and not isinstance(amount, bool):
        cost = {"status": "measured", "amount": amount, "currency": CLAUDE_CODE_CURRENCY,
                "source": CLAUDE_CODE_SOURCE, "confidence": basis}
    return usage, cost, model


# --- validation ---------------------------------------------------------------------------
def _one_of(value: Any, allowed: set[str]) -> bool:
    """A vocabulary test that reports rather than raises: a list or dict where a string
    belongs is malformed data, and `x in set` would throw on it — which, from inside
    control_room_api's receipts(), took the whole read model down instead of one file."""
    return isinstance(value, str) and value in allowed


def validate(data: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(data, dict):
        return ["root is not an object"]
    for key in ("schema_version", "workflow_id", "run_id", "started_at", "ended_at"):
        if data.get(key) in (None, ""):
            errors.append(f"missing {key}")
    if data.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version is not {SCHEMA_VERSION}")
    terminal = data.get("terminal")
    if not isinstance(terminal, dict) or not _one_of(terminal.get("outcome"), TERMINAL_OUTCOMES):
        errors.append("terminal.outcome is invalid")
    assertions = data.get("assertions")
    if not isinstance(assertions, list):
        errors.append("assertions is not a list")
    else:
        seen: set[str] = set()
        for index, assertion in enumerate(assertions):
            if not isinstance(assertion, dict):
                errors.append(f"assertions[{index}] is not an object")
                continue
            assertion_id = assertion.get("id")
            if not isinstance(assertion_id, str) or not assertion_id:
                errors.append(f"assertions[{index}] has no id")
            elif assertion_id in seen:
                errors.append(f"duplicate assertion id: {assertion_id}")
            else:
                seen.add(assertion_id)
            if not _one_of(assertion.get("status"), ASSERTION_STATUSES):
                errors.append(f"assertions[{index}].status is invalid")
    for key in ("usage", "cost"):
        measurement = data.get(key)
        if not isinstance(measurement, dict) or not _one_of(measurement.get("status"), MEASUREMENT_STATUSES):
            errors.append(f"{key}.status is invalid")
            continue
        if measurement.get("status") == "unavailable":
            numeric = COST_FIELDS if key == "cost" else USAGE_FIELDS
            if any(measurement.get(field) is not None for field in numeric):
                errors.append(f"{key} unavailable values must be null")
    started, ended = parse_time(data.get("started_at")), parse_time(data.get("ended_at"))
    if started is None or ended is None:
        errors.append("started_at/ended_at must be ISO-8601 timestamps")
    elif ended < started:
        errors.append("ended_at precedes started_at")
    if isinstance(terminal, dict) and terminal.get("outcome") == "artifact":
        artifact = data.get("artifact")
        state_change = data.get("state_change")
        has_artifact = isinstance(artifact, dict) and bool(artifact.get("uri"))
        has_state = isinstance(state_change, dict) and bool(state_change.get("evidence"))
        if not has_artifact and not has_state:
            errors.append("artifact outcome has no artifact URI or state-change evidence")
    return errors


# --- writing ------------------------------------------------------------------------------
def receipt_path(root: pathlib.Path, receipt: dict[str, Any]) -> pathlib.Path:
    """`<root>/<workflow_id>/<run_id>.json` — the layout control_room_api globs."""
    for key in ("workflow_id", "run_id"):
        value = receipt[key]
        if not isinstance(value, str) or "/" in value or value in (".", ".."):
            raise ValueError(f"{key} is not a path segment: {value!r}")
    return pathlib.Path(root) / receipt["workflow_id"] / f"{receipt['run_id']}.json"


def write(receipt: dict[str, Any], root: pathlib.Path) -> pathlib.Path:
    """Validate, then write atomically: temp file beside the target, fsync, rename.

    A receipt that does not validate is refused before anything touches disk; an error
    mid-serialisation leaves no partial file behind, because the target only ever appears
    by rename of a complete one.
    """
    errors = validate(receipt)
    if errors:
        raise ValueError("receipt does not validate: " + "; ".join(errors))
    target = receipt_path(root, receipt)
    target.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", dir=target.parent, prefix=f".{target.stem}.",
                                         suffix=".tmp", delete=False)
    try:
        with handle:
            json.dump(receipt, handle, indent=2, sort_keys=True)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(handle.name, target)
    except BaseException:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise
    return target
