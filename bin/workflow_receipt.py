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
- A `closed` block (T7.5) is an operator's review of a failed receipt — who, when, why —
  and only a failed one: a receipt with nothing failed has nothing to close. The recorded
  outcome stays as written; `judged` is what every reader asks, and a closed receipt is not
  a run to judge, exactly as a skipped one is not.
- A `swept` block (T7.3) records that the receipt sweep amended a run-vantage receipt with
  its contract's `when=sweep` results, once. The run's own facts stay as written; a sweep
  can add failed checks and turn the outcome `failed`, never the reverse.
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
SWEEP_WORKFLOW_ID = "workflow-receipt-sweep"
CLOSED_FIELDS = ("at", "by", "reason")
SWEPT_FIELDS = ("at", "sweep_run_id")
RUN_VANTAGE = "run"
SWEEP_VANTAGE = "sweep"


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


# S1 skill telemetry (2026-09-18): which pointer skills an interaction turn was offered,
# invoked and read — the same three sets cost.log records for a scheduled run under
# skills_offered= / skills= (T3.3), so bin/scorecard.sh can fold both surfaces into one
# table. `source` names the evidence (transcript | rollout); unavailable carries empty
# lists and no source, never a guess.
SKILL_SETS = ("offered", "invoked", "read")


def measured_skills(offered: set[str], invoked: set[str], read: set[str], source: str) -> dict[str, Any]:
    return {"status": "measured", "offered": sorted(offered), "invoked": sorted(invoked),
            "read": sorted(read), "source": source}


def unavailable_skills() -> dict[str, Any]:
    return {"status": "unavailable", **{name: [] for name in SKILL_SETS}, "source": None}


def _int_or_none(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _costliest_model(models: Any) -> tuple[str, dict[str, Any]] | None:
    """(name, entry) of the modelUsage member with the largest costUSD; ties keep map order."""
    if not isinstance(models, dict) or not models:
        return None
    entries = [(name, e if isinstance(e, dict) else {}) for name, e in models.items()]

    def cost(item: tuple[str, dict[str, Any]]) -> float:
        value = item[1].get("costUSD")
        return float(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else 0.0

    return max(entries, key=cost)


def usage_from_claude_code(envelope: Any) -> tuple[dict[str, Any], dict[str, Any], str | None]:
    """(usage, cost, model) from a `claude -p --output-format json` result envelope.

    `measured` only when the envelope carries all four token counts as integers; a zero is
    then the runtime's zero. Anything less is `unavailable` — never a partial sum rendered
    as a total. Cost is measured only when `total_cost_usd` is a number; its confidence is
    `modelUsage.<model>.costBasis`. The model is the map's costliest key: a sonnet or opus
    run also carries a few-cent haiku entry (Claude Code's own helper calls), and until
    2026-09-17 the first key was taken, so ten live receipts named haiku for runs that had
    spent $1-2 on opus.
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
    model, basis = None, None
    entry = _costliest_model(envelope.get("modelUsage"))
    if entry is not None:
        model, basis = entry[0], entry[1].get("costBasis")
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
    errors.extend(_closed_errors(data))
    errors.extend(_swept_errors(data))
    return errors


def _closed_errors(data: dict[str, Any]) -> list[str]:
    closed = data.get("closed")
    if closed is None:
        return []
    if not isinstance(closed, dict):
        return ["closed is not an object"]
    errors = [f"closed.{field} is missing" for field in CLOSED_FIELDS
              if not isinstance(closed.get(field), str) or not closed[field].strip()]
    if not errors and parse_time(closed["at"]) is None:
        errors.append("closed.at must be an ISO-8601 timestamp")
    if not has_failure(data):
        errors.append("closed on a receipt with nothing failed")
    return errors


def _swept_errors(data: dict[str, Any]) -> list[str]:
    swept = data.get("swept")
    if swept is None:
        return []
    if not isinstance(swept, dict):
        return ["swept is not an object"]
    errors = [f"swept.{field} is missing" for field in SWEPT_FIELDS
              if not isinstance(swept.get(field), str) or not swept[field].strip()]
    if not errors and parse_time(swept["at"]) is None:
        errors.append("swept.at must be an ISO-8601 timestamp")
    if data.get("vantage") != RUN_VANTAGE:
        errors.append("swept on a receipt the sweep wrote itself")
    return errors


# --- the sweep's amendment (T7.3) ----------------------------------------------------------
def is_swept(receipt: dict[str, Any]) -> bool:
    return isinstance(receipt.get("swept"), dict)


def sweep_assertions(receipt: dict[str, Any]) -> list[dict[str, Any]]:
    assertions = receipt.get("assertions") if isinstance(receipt.get("assertions"), list) else []
    return [a for a in assertions if isinstance(a, dict) and a.get("when") == SWEEP_VANTAGE]


def sweep_pending(receipt: dict[str, Any]) -> str | None:
    """Why the sweep must leave this receipt alone, or None when it owes it an amendment:
    a run-vantage receipt that ran (not skipped), is not closed, is not yet swept and lists
    at least one `when=sweep` check the run recorded as not applicable."""
    if receipt.get("vantage") != RUN_VANTAGE:
        return "written by the sweep"
    if (receipt.get("terminal") or {}).get("outcome") == "skipped":
        return "a skip is not a run"
    if is_closed(receipt):
        return "closed by an operator"
    if is_swept(receipt):
        return f"swept {receipt['swept'].get('at')}"
    if not sweep_assertions(receipt):
        return "no sweep checks"
    return None


def amended_terminal(terminal: dict[str, Any], fresh: list[dict[str, Any]]) -> dict[str, Any]:
    """Monotone: failed sweep checks make the outcome `failed`; nothing else changes it."""
    failed = [a["id"] for a in fresh if a.get("status") == "failed"]
    if not failed:
        return terminal
    note = "failed sweep checks: " + ", ".join(failed)
    outcome, reason = terminal.get("outcome"), terminal.get("reason")
    if outcome == "failed":
        return {"outcome": "failed", "reason": f"{reason}; {note}" if reason else note}
    return {"outcome": "failed", "reason": f"{note}; run outcome was {outcome}" + (f": {reason}" if reason else "")}


def amend(receipt: dict[str, Any], fresh: list[dict[str, Any]], sweep_run_id: str,
          now: dt.datetime | None = None) -> dict[str, Any]:
    """The receipt with the sweep's results folded in by id and a `swept` block; refuses a
    receipt the sweep does not owe (sweep_pending says why)."""
    why = sweep_pending(receipt)
    if why is not None:
        raise ValueError(f"nothing to sweep: {why}")
    if not sweep_run_id.strip():
        raise ValueError("an amendment names the sweep run that made it")
    by_id = {a["id"]: a for a in fresh}
    assertions = [by_id.pop(a["id"], a) if a.get("when") == SWEEP_VANTAGE else a for a in receipt["assertions"]]
    assertions.extend(by_id.values())
    return {**receipt, "assertions": assertions,
            "terminal": amended_terminal(receipt["terminal"], fresh),
            "swept": {"at": iso_utc(now), "sweep_run_id": sweep_run_id.strip()}}


# --- review -------------------------------------------------------------------------------
def has_failure(receipt: dict[str, Any]) -> bool:
    outcome = (receipt.get("terminal") or {}).get("outcome") if isinstance(receipt.get("terminal"), dict) else None
    assertions = receipt.get("assertions") if isinstance(receipt.get("assertions"), list) else []
    return outcome == "failed" or any(isinstance(a, dict) and a.get("status") == "failed" for a in assertions)


def is_closed(receipt: dict[str, Any]) -> bool:
    return isinstance(receipt.get("closed"), dict)


def judged(receipt: dict[str, Any]) -> bool:
    """A run every reader may judge: it ran (not skipped) and no operator has closed it."""
    return (receipt.get("terminal") or {}).get("outcome") != "skipped" and not is_closed(receipt)


def close(receipt: dict[str, Any], by: str, reason: str, now: dt.datetime | None = None) -> dict[str, Any]:
    """The receipt with a review recorded on it; refuses a receipt that has nothing failed,
    is already closed, or a review with no author or reason."""
    if not has_failure(receipt):
        raise ValueError("nothing failed in this receipt; there is nothing to close")
    if is_closed(receipt):
        closed = receipt["closed"]
        raise ValueError(f"already closed {closed.get('at')} by {closed.get('by')}: {closed.get('reason')}")
    if not by.strip() or not reason.strip():
        raise ValueError("a closure names who closed it and why")
    return {**receipt, "closed": {"at": iso_utc(now), "by": by.strip(), "reason": reason.strip()}}


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
