#!/usr/bin/env python3
"""What a workflow incident is (T5.3c): the vocabulary, the dedup key and the derivation.

    workflow_incidents.py declare --class C --workflow W --agent A --issue TEXT --action TEXT
                                  [--evidence STR]... --id STABLE-ID [--state-dir DIR]
    workflow_incidents.py resolve --key KEY [--state-dir DIR]

`derive()` is pure and reads exactly what bin/control_room_api.py's `workflows()` and
`receipts()` return. Two consumers call it — the Control Room's `incidents()` and
bin/incident_notify.py — so there is one derivation, not two. The key is `<class>:<workflow>`
for run-derived classes: a workflow failing every night is ONE incident that accrues
observations, never a fresh alert per run. A skipped receipt is not a run: the run judged is
`lastEligibleRun`, and a fire is `incomplete-run` only once the receipt sweep has looked
after it and found nothing (bin/missed_receipt.py) — the same judgement the Control Room's
`missed-cadence` makes.

A declared incident is a file under `<state-dir>/declared/`, written by `declare` (the
control broker's seam for a failed control action) and closed by `resolve`; it is observed
while `resolved_at` is null and is absent from the derivation once resolved.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import pathlib
import re
import sys
import tempfile
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from control_room_cadence import parse_systemd_timestamp  # noqa: E402
from missed_receipt import missed_fire, sweep_started_at  # noqa: E402
from workflow_receipt import iso_utc, parse_time  # noqa: E402

SCHEMA = 1
SWEEP_SOURCE = "incident-sweep"
SEVERITY = {
    "failed-assertion": "high",
    "missing-artifact": "high",
    "incomplete-run": "high",
    "malformed-receipt": "high",
    "control-failure": "high",
    "blocked-next-action": "medium",
    "contract-unavailable": "medium",
}
CLASSES = tuple(SEVERITY)
IMMEDIATE_CLASSES = frozenset(CLASSES) - {"contract-unavailable"}
REQUIRED_ACTION = {
    "failed-assertion": "Read the failed check and the attempt log, then re-run by hand.",
    "missing-artifact": "The run ended without an artifact or a decline; read its log and re-run by hand.",
    "incomplete-run": "The run never completed; check the unit's journal and re-run by hand.",
    "malformed-receipt": "Repair or quarantine the malformed receipt; do not infer its run outcome.",
    "control-failure": "The incident sweep cannot see one of its sources; restore it before trusting silence.",
    "blocked-next-action": "Unblock the named next action.",
    "contract-unavailable": "Declare and validate the workflow contract before receipt wiring.",
}
DEFAULT_GRACE_SECS = 7200
UNREADABLE_RECEIPTS = ("receipt directory unreadable", "receipt path is not a directory")
_UNSAFE = re.compile(r"[^A-Za-z0-9_.@-]+")


def key(cls: str, *parts: str) -> str:
    return ":".join((cls, *parts))


def sanitise_key(value: str) -> str:
    cleaned = _UNSAFE.sub("_", value).strip("._") or "incident"
    return cleaned.replace("..", "_")


def parse_systemd_utc(text: Any) -> dt.datetime | None:
    return parse_systemd_timestamp(text) or parse_time(text)


def sources_visible(source_errors: list[str], manifest_errors: list[str]) -> bool:
    return not manifest_errors and not any(e.startswith(UNREADABLE_RECEIPTS) for e in source_errors)


def _incident(cls: str, key_: str, workflow_id: str | None, agent: str | None, unit: str | None,
              issue: str, evidence: list[str], failed_assertion: str | None = None,
              required_action: str | None = None, run_id: str | None = None,
              observed_at: str | None = None) -> dict[str, Any]:
    return {
        "key": key_, "class": cls, "severity": SEVERITY[cls], "workflow_id": workflow_id,
        "agent": agent, "unit": unit, "issue": issue, "failed_assertion": failed_assertion,
        "required_action": required_action or REQUIRED_ACTION[cls], "run_id": run_id,
        "evidence": [e for e in evidence if e], "observed_at": observed_at,
    }


def _from_run(workflow: dict[str, Any], run: dict[str, Any]) -> dict[str, Any] | None:
    if run.get("outcome") != "failed":
        return None
    failed = [a.get("id") for a in run.get("assertions") or [] if a.get("status") == "failed"]
    if failed:
        cls, issue = "failed-assertion", run.get("reason") or f"failed checks: {', '.join(failed)}"
    else:
        cls, issue = "missing-artifact", run.get("reason") or "neither artifact nor decline"
    artifact = run.get("artifact") if isinstance(run.get("artifact"), dict) else {}
    next_action = run.get("nextAction") if isinstance(run.get("nextAction"), dict) else {}
    return _incident(cls, key(cls, workflow["id"]), workflow["id"], run.get("agent") or workflow.get("owner"),
                     run.get("unit"), issue, [run.get("receiptPath"), artifact.get("uri")],
                     failed_assertion=failed[0] if failed else None, required_action=next_action.get("action"),
                     run_id=run.get("id"), observed_at=run.get("endedAt"))


def _stale_trigger(workflow: dict[str, Any], swept_at: dt.datetime | None, grace: int) -> dict[str, Any] | None:
    newest = parse_time((workflow.get("lastRun") or {}).get("startedAt"))
    for trigger in workflow.get("triggers") or []:
        timer = (trigger.get("systemd") or {}).get("timer") or {}
        if trigger.get("state") == "running" or timer.get("activeState") != "active":
            continue
        fired = parse_systemd_utc(timer.get("firedAt"))
        if not missed_fire(fired, newest, swept_at, grace):
            continue
        unit = str(trigger["unit"])
        return _incident("incomplete-run", key("incomplete-run", workflow["id"]), workflow["id"],
                         workflow.get("owner"), unit,
                         f"{unit}.timer fired at {iso_utc(fired)} and the receipt sweep of {iso_utc(swept_at)} found none",
                         [f"journalctl -u {unit} --since {iso_utc(fired)}"], observed_at=iso_utc(fired))
    return None


def _contract(workflow: dict[str, Any]) -> dict[str, Any] | None:
    if workflow.get("contractStatus") != "unavailable":
        return None
    return _incident("contract-unavailable", key("contract-unavailable", workflow["id"]), workflow["id"],
                     workflow.get("owner"), None, workflow.get("contractError") or "contract unavailable",
                     list(workflow.get("manifestPaths") or []), failed_assertion="contract-available")


def _control(source_errors: list[str], manifest_errors: list[str]) -> list[dict[str, Any]]:
    found = []
    unreadable = [e for e in source_errors if e.startswith(UNREADABLE_RECEIPTS)]
    if unreadable:
        found.append(_incident("control-failure", key("control-failure", SWEEP_SOURCE, "receipts"), None, None,
                               None, "; ".join(unreadable), unreadable))
    if manifest_errors:
        found.append(_incident("control-failure", key("control-failure", SWEEP_SOURCE, "manifests"), None, None,
                               None, "; ".join(manifest_errors), list(manifest_errors)))
    return found


def derive(workflows: list[dict[str, Any]], malformed: list[dict[str, Any]], source_errors: list[str],
           declared: list[dict[str, Any]], grace_secs: int = DEFAULT_GRACE_SECS,
           manifest_errors: list[str] | None = None) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    swept_at = sweep_started_at(workflows)
    for workflow in workflows:
        candidates = [_contract(workflow), _from_run(workflow, workflow.get("lastEligibleRun") or {}),
                      _stale_trigger(workflow, swept_at, grace_secs)]
        found.extend(c for c in candidates if c)
    for invalid in malformed:
        found.append(_incident("malformed-receipt", key("malformed-receipt", str(invalid["path"])), None, None, None,
                               "; ".join(invalid.get("errors") or []), [str(invalid["path"])],
                               failed_assertion="receipt-schema-valid"))
    found.extend(_control(source_errors, manifest_errors or []))
    found.extend(d for d in declared if d.get("resolved_at") is None)
    seen: dict[str, dict[str, Any]] = {}
    for item in found:
        seen.setdefault(item["key"], item)
    return list(seen.values())


# --- declared incidents -------------------------------------------------------------------
def _declared_dir(state_dir: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(state_dir) / "declared"


def _validate_declared(data: Any) -> str | None:
    if not isinstance(data, dict):
        return "not an object"
    if data.get("class") not in CLASSES:
        return f"unknown class {data.get('class')!r}"
    for field in ("workflow_id", "id"):
        if not isinstance(data.get(field), str) or not data[field]:
            return f"missing {field}"
    return None


def load_declared(state_dir: pathlib.Path) -> tuple[list[dict[str, Any]], list[str]]:
    directory = _declared_dir(state_dir)
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    if not directory.is_dir():
        return items, errors
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text())
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        problem = _validate_declared(data)
        if problem:
            errors.append(f"{path.name}: {problem}")
            continue
        items.append(_incident(data["class"], key(data["class"], data["workflow_id"], data["id"]),
                               data["workflow_id"], data.get("agent"), data.get("unit"),
                               data.get("issue") or "declared incident", list(data.get("evidence") or []),
                               required_action=data.get("required_action"), observed_at=data.get("declared_at"))
                     | {"resolved_at": data.get("resolved_at"), "declared_path": str(path)})
    return items, errors


def _write_json(path: pathlib.Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", dir=path.parent, prefix=f".{path.stem}.", suffix=".tmp", delete=False)
    try:
        with handle:
            json.dump(data, handle, indent=2, sort_keys=True)
            handle.write("\n")
        os.replace(handle.name, path)
    except BaseException:
        pathlib.Path(handle.name).unlink(missing_ok=True)
        raise


def declare(state_dir: pathlib.Path, incident: dict[str, Any], now: dt.datetime | None = None) -> pathlib.Path:
    problem = _validate_declared(incident)
    if problem:
        raise ValueError(problem)
    key_ = key(incident["class"], incident["workflow_id"], incident["id"])
    path = _declared_dir(state_dir) / f"{sanitise_key(key_)}.json"
    _write_json(path, {**incident, "schema": SCHEMA, "key": key_, "declared_at": iso_utc(now), "resolved_at": None})
    return path


def resolve_declared(state_dir: pathlib.Path, key_: str, now: dt.datetime | None = None) -> bool:
    path = _declared_dir(state_dir) / f"{sanitise_key(key_)}.json"
    if not path.is_file():
        return False
    data = json.loads(path.read_text())
    _write_json(path, {**data, "resolved_at": iso_utc(now)})
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = parser.add_subparsers(dest="command", required=True)
    default_dir = os.environ.get("INCIDENT_STATE_DIR", str(pathlib.Path.home() / "agent-workforce" / "var" / "incidents"))
    dec = sub.add_parser("declare")
    dec.add_argument("--state-dir", default=default_dir)
    dec.add_argument("--class", dest="cls", required=True, choices=CLASSES)
    dec.add_argument("--workflow", required=True)
    dec.add_argument("--agent", default=None)
    dec.add_argument("--issue", required=True)
    dec.add_argument("--action", required=True)
    dec.add_argument("--evidence", action="append", default=[])
    dec.add_argument("--id", required=True)
    res = sub.add_parser("resolve")
    res.add_argument("--state-dir", default=default_dir)
    res.add_argument("--key", required=True)
    args = parser.parse_args(argv)
    if args.command == "declare":
        path = declare(pathlib.Path(args.state_dir), {"class": args.cls, "workflow_id": args.workflow, "agent": args.agent,
                                                      "issue": args.issue, "required_action": args.action,
                                                      "evidence": args.evidence, "id": args.id})
        print(path)
        return 0
    if resolve_declared(pathlib.Path(args.state_dir), args.key):
        return 0
    print(f"no declared incident with key {args.key}", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
