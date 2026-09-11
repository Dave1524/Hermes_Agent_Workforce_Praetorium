#!/usr/bin/env python3
"""Read-only Praetorium Control Room API.

The API is a projection over committed manifests/contracts, live systemd state and the
structured workflow receipts T5.1/T5.2 will write.  It deliberately does not mutate any
of those sources.  Missing evidence is represented as unavailable, never as success or 0.
"""

from __future__ import annotations

import argparse
import dataclasses
import datetime as dt
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib
import urllib.parse
from collections import defaultdict
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable, Iterable


API_VERSION = "v1"
RECEIPT_SCHEMA_VERSION = 1
TERMINAL_OUTCOMES = {"artifact", "decline", "failed", "skipped"}
ASSERTION_STATUSES = {"passed", "failed", "not_applicable"}
MEASUREMENT_STATUSES = {"measured", "unavailable"}
OUTPUT_LABELS = (
    "Beneficiary",
    "Next actor",
    "Next action",
    "Benefit hypothesis",
    "Benefit signal",
)


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


def clean_markdown(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"`([^`]*)`", r"\1", value)
    text = re.sub(r"\[([^]]+)]\([^)]+\)", r"\1", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def section(text: str, name: str) -> str:
    match = re.search(
        rf"^## {re.escape(name)}\s*$\n(.*?)(?=^## |\Z)",
        text,
        re.MULTILINE | re.DOTALL,
    )
    return match.group(1).strip() if match else ""


def output_fields(text: str) -> dict[str, str | None]:
    body = section(text, "Outputs")
    result: dict[str, str | None] = {}
    for label in OUTPUT_LABELS:
        match = re.search(
            rf"^- \*\*{re.escape(label)}:\*\*\s*(.*?)(?=\n- \*\*[A-Z]|\Z)",
            body,
            re.MULTILINE | re.DOTALL,
        )
        result[label] = clean_markdown(match.group(1)) if match else None
    artifact_match = re.search(
        r"^- \*\*(?:Artifact|State change|Notion row|Body file):\*\*\s*(.*?)(?=\n- \*\*|\Z)",
        body,
        re.MULTILINE | re.DOTALL,
    )
    result["Artifact"] = clean_markdown(artifact_match.group(1)) if artifact_match else None
    return result


def contract_identity(text: str) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in section(text, "Identity").splitlines():
        if not line.startswith("|") or line.startswith("|---"):
            continue
        cells = [clean_markdown(cell) or "" for cell in line.strip("|").split("|")]
        if len(cells) >= 2 and cells[0] in {"Unit", "Units", "Owner", "Owners", "Surface"}:
            result[cells[0]] = cells[1]
    return result


@dataclasses.dataclass(frozen=True)
class SourcePaths:
    repo: pathlib.Path
    runtime: pathlib.Path
    receipts: pathlib.Path

    @classmethod
    def defaults(cls) -> "SourcePaths":
        repo = pathlib.Path(
            os.environ.get("CONTROL_ROOM_REPO_ROOT", pathlib.Path(__file__).resolve().parents[1])
        ).resolve()
        runtime = pathlib.Path(
            os.environ.get("CONTROL_ROOM_RUNTIME_ROOT", pathlib.Path.home() / "agent-workforce")
        ).resolve()
        receipts = pathlib.Path(
            os.environ.get("CONTROL_ROOM_RECEIPT_ROOT", runtime / "var" / "workflow-receipts")
        ).resolve()
        return cls(repo=repo, runtime=runtime, receipts=receipts)


class SystemdReader:
    """Small read-only adapter, injectable in tests."""

    PROPERTIES = (
        "ActiveState",
        "SubState",
        "Result",
        "ExecMainStartTimestamp",
        "ExecMainExitTimestamp",
        "ExecMainStatus",
        "UnitFileState",
        "LastTriggerUSec",
        "NextElapseUSecRealtime",
        "Persistent",
    )

    def show(self, name: str, scope: str) -> tuple[dict[str, str], str | None]:
        command = ["systemctl"]
        if scope == "user":
            command.append("--user")
        command.extend(["show", name, "--no-pager"])
        command.extend(f"--property={prop}" for prop in self.PROPERTIES)
        try:
            completed = subprocess.run(
                command,
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {}, f"{type(exc).__name__}: {exc}"
        if completed.returncode != 0:
            message = (completed.stderr or completed.stdout).strip()
            return {}, message or f"systemctl exited {completed.returncode}"
        values: dict[str, str] = {}
        for line in completed.stdout.splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value
        return values, None


class ControlRoomReadModel:
    def __init__(
        self,
        paths: SourcePaths | None = None,
        systemd: SystemdReader | None = None,
        clock: Callable[[], dt.datetime] = utc_now,
    ) -> None:
        self.paths = paths or SourcePaths.defaults()
        self.systemd = systemd or SystemdReader()
        self.clock = clock

    def _manifests(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        errors: list[str] = []
        manifest_dir = self.paths.repo / "design" / "agents"
        if not manifest_dir.is_dir():
            return [], [f"manifest directory unavailable: {manifest_dir}"]
        for path in sorted(manifest_dir.glob("*.toml")):
            try:
                data = tomllib.loads(path.read_text())
            except (OSError, tomllib.TOMLDecodeError) as exc:
                errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
                continue
            owner = str(data.get("name") or path.stem)
            for workflow in data.get("workflows", []):
                if not isinstance(workflow, dict) or not workflow.get("unit"):
                    errors.append(f"{path.name}: workflow entry has no unit")
                    continue
                row = dict(workflow)
                row["owner"] = owner
                row["manifest"] = str(path.relative_to(self.paths.repo))
                row["logical_workflow"] = str(row.get("logical_workflow") or row["unit"])
                rows.append(row)
        return rows, errors

    def _contract(self, relative: Any) -> tuple[dict[str, Any] | None, str | None]:
        if not isinstance(relative, str) or not relative.strip():
            return None, "contract not declared"
        path = (self.paths.repo / relative).resolve()
        try:
            path.relative_to(self.paths.repo)
        except ValueError:
            return None, f"contract escapes repo root: {relative}"
        if not path.is_file():
            return None, f"contract missing: {relative}"
        try:
            text = path.read_text()
        except OSError as exc:
            return None, f"contract unreadable: {relative}: {exc}"
        fields = output_fields(text)
        identity = contract_identity(text)
        trigger_text = clean_markdown(section(text, "Trigger"))
        return {
            "path": relative,
            "identity": identity,
            "trigger": trigger_text,
            "artifact": fields.get("Artifact"),
            "beneficiary": fields.get("Beneficiary"),
            "next_actor": fields.get("Next actor"),
            "next_action": fields.get("Next action"),
            "benefit_hypothesis": fields.get("Benefit hypothesis"),
            "benefit_signal": fields.get("Benefit signal"),
        }, None

    def _receipt_files(self) -> tuple[list[pathlib.Path], list[str]]:
        root = self.paths.receipts
        if not root.exists():
            return [], [f"receipt directory unavailable: {root}"]
        if not root.is_dir():
            return [], [f"receipt path is not a directory: {root}"]
        try:
            files = sorted(root.glob("*/*.json"))
        except OSError as exc:
            return [], [f"receipt directory unreadable: {exc}"]
        return files, []

    @staticmethod
    def _validate_receipt(data: Any, path: pathlib.Path) -> list[str]:
        errors: list[str] = []
        if not isinstance(data, dict):
            return ["root is not an object"]
        for key in ("schema_version", "workflow_id", "run_id", "started_at", "ended_at"):
            if data.get(key) in (None, ""):
                errors.append(f"missing {key}")
        if data.get("schema_version") != RECEIPT_SCHEMA_VERSION:
            errors.append(f"schema_version is not {RECEIPT_SCHEMA_VERSION}")
        terminal = data.get("terminal")
        if not isinstance(terminal, dict) or terminal.get("outcome") not in TERMINAL_OUTCOMES:
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
                if assertion.get("status") not in ASSERTION_STATUSES:
                    errors.append(f"assertions[{index}].status is invalid")
        for key in ("usage", "cost"):
            measurement = data.get(key)
            if not isinstance(measurement, dict) or measurement.get("status") not in MEASUREMENT_STATUSES:
                errors.append(f"{key}.status is invalid")
                continue
            if measurement.get("status") == "unavailable":
                numeric = ("input_tokens", "output_tokens", "cache_tokens", "total_tokens")
                if key == "cost":
                    numeric = ("amount",)
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

    def receipts(self) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[str]]:
        files, source_errors = self._receipt_files()
        valid: list[dict[str, Any]] = []
        malformed: list[dict[str, Any]] = []
        for path in files:
            try:
                if path.stat().st_size > 1_000_000:
                    raise ValueError("receipt exceeds 1 MB")
                data = json.loads(path.read_text())
                errors = self._validate_receipt(data, path)
            except (OSError, json.JSONDecodeError, ValueError) as exc:
                data = None
                errors = [f"{type(exc).__name__}: {exc}"]
            relative = str(path.relative_to(self.paths.receipts))
            if errors:
                malformed.append({"path": relative, "errors": errors})
                continue
            assert isinstance(data, dict)
            data = dict(data)
            data["receipt_path"] = relative
            valid.append(data)
        valid.sort(key=lambda item: parse_time(item.get("ended_at")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
        return valid, malformed, source_errors

    def _systemd_for(self, workflow: dict[str, Any]) -> dict[str, Any]:
        scope = str(workflow.get("scope") or "system")
        kind = str(workflow.get("kind") or "timer")
        unit = str(workflow["unit"])
        service_name = unit if unit.endswith(".service") else f"{unit}.service"
        service, service_error = self.systemd.show(service_name, scope)
        timer: dict[str, str] = {}
        timer_error: str | None = None
        if kind == "timer":
            timer_name = unit if unit.endswith(".timer") else f"{unit}.timer"
            timer, timer_error = self.systemd.show(timer_name, scope)
        errors = [error for error in (service_error, timer_error) if error]
        return {
            "scope": scope,
            "kind": kind,
            "service": {
                "name": service_name,
                "activeState": service.get("ActiveState") or "unknown",
                "subState": service.get("SubState") or "unknown",
                "result": service.get("Result") or "unknown",
                "startedAt": service.get("ExecMainStartTimestamp") or None,
                "endedAt": service.get("ExecMainExitTimestamp") or None,
                "exitStatus": int(service["ExecMainStatus"]) if service.get("ExecMainStatus", "").isdigit() else None,
            },
            "timer": None if kind != "timer" else {
                "name": unit if unit.endswith(".timer") else f"{unit}.timer",
                "activeState": timer.get("ActiveState") or "unknown",
                "subState": timer.get("SubState") or "unknown",
                "enabledState": timer.get("UnitFileState") or "unknown",
                "lastTriggerAt": timer.get("LastTriggerUSec") or None,
                "nextRunAt": timer.get("NextElapseUSecRealtime") or None,
                "persistent": ({"yes": True, "no": False}.get(timer.get("Persistent", "")) if timer else None),
            },
            "status": "available" if not errors else "unavailable",
            "errors": errors,
        }

    @staticmethod
    def _health(receipt: dict[str, Any] | None, triggers: list[dict[str, Any]]) -> str:
        if any(trigger["systemd"]["service"]["activeState"] in {"activating", "active"}
               and trigger["systemd"]["service"]["subState"] in {"running", "start"}
               for trigger in triggers):
            return "running"
        timers = [trigger["systemd"]["timer"] for trigger in triggers if trigger["systemd"]["timer"]]
        if timers and all(timer["activeState"] == "inactive" for timer in timers):
            return "paused"
        if receipt is None:
            return "unknown"
        outcome = receipt["terminal"]["outcome"]
        if outcome == "failed" or any(item.get("status") == "failed" for item in receipt["assertions"]):
            return "failed"
        if outcome == "skipped":
            return "incomplete"
        return "healthy"

    @staticmethod
    def _measurement(measurement: Any, fields: Iterable[str]) -> dict[str, Any]:
        if not isinstance(measurement, dict) or measurement.get("status") != "measured":
            return {"status": "unavailable", **{field: None for field in fields}}
        return {"status": "measured", **{field: measurement.get(field) for field in fields}}

    def workflows(self, include_nonstanding: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        entries, manifest_errors = self._manifests()
        receipts, malformed, receipt_errors = self.receipts()
        if not include_nonstanding:
            entries = [entry for entry in entries if entry.get("status") == "standing"]
        receipt_by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for receipt in receipts:
            receipt_by_workflow[str(receipt["workflow_id"])].append(receipt)
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for entry in entries:
            grouped[str(entry["logical_workflow"])].append(entry)
        items: list[dict[str, Any]] = []
        systemd_errors: list[str] = []
        contract_errors: list[str] = []
        for logical_id, group in sorted(grouped.items()):
            owner_set = sorted({str(entry["owner"]) for entry in group})
            contract_paths = sorted({str(entry.get("contract")) for entry in group if entry.get("contract")})
            contract, contract_error = self._contract(contract_paths[0] if len(contract_paths) == 1 else None)
            if len(contract_paths) > 1:
                contract_error = f"logical workflow declares multiple contracts: {contract_paths}"
            if contract_error:
                contract_errors.append(f"{logical_id}: {contract_error}")
            triggers: list[dict[str, Any]] = []
            for entry in sorted(group, key=lambda value: str(value["unit"])):
                systemd = self._systemd_for(entry)
                systemd_errors.extend(f"{entry['unit']}: {error}" for error in systemd["errors"])
                triggers.append({
                    "unit": entry["unit"],
                    "scope": entry.get("scope", "system"),
                    "kind": entry.get("kind", "timer"),
                    "surface": entry.get("surface"),
                    "trigger": entry.get("trigger"),
                    "runner": entry.get("runner"),
                    "route": entry.get("route"),
                    "systemd": systemd,
                })
            workflow_receipts = receipt_by_workflow.get(logical_id, [])
            latest = workflow_receipts[0] if workflow_receipts else None
            usage = self._measurement(
                latest.get("usage") if latest else None,
                ("input_tokens", "output_tokens", "cache_tokens", "total_tokens"),
            )
            cost = self._measurement(latest.get("cost") if latest else None, ("amount", "currency", "source", "confidence"))
            artifact = latest.get("artifact") if latest and isinstance(latest.get("artifact"), dict) else None
            purpose = next((clean_markdown(str(entry.get("what"))) for entry in group if entry.get("what")), None)
            if purpose is None and contract:
                purpose = clean_markdown(
                    f"Produces {contract.get('artifact') or 'a declared outcome'} for "
                    f"{contract.get('beneficiary') or 'its beneficiary'}"
                )
            item = {
                "id": logical_id,
                "name": logical_id.replace("-", " ").title(),
                "owners": owner_set,
                "owner": owner_set[0] if len(owner_set) == 1 else None,
                "purpose": purpose,
                "lifecycle": group[0].get("status", "unknown"),
                "health": self._health(latest, triggers),
                "manifestPaths": sorted({str(entry["manifest"]) for entry in group}),
                "contract": contract,
                "contractStatus": "available" if contract else "unavailable",
                "contractError": contract_error,
                "triggers": triggers,
                "lastRun": self._run_summary(latest) if latest else None,
                "latestOutput": artifact,
                "usage": usage,
                "cost": cost,
                "receiptCount": len(workflow_receipts),
            }
            items.append(item)
        status = {
            "manifests": "available" if not manifest_errors else "degraded",
            "contracts": "available" if not contract_errors else "degraded",
            "receipts": "available" if not receipt_errors and not malformed else "degraded",
            "systemd": "available" if not systemd_errors else "degraded",
            "errors": {
                "manifests": manifest_errors,
                "contracts": contract_errors,
                "receipts": receipt_errors,
                "malformedReceipts": malformed,
                "systemd": systemd_errors,
            },
        }
        return items, status

    @staticmethod
    def _run_summary(receipt: dict[str, Any] | None) -> dict[str, Any] | None:
        if not receipt:
            return None
        return {
            "id": receipt.get("run_id"),
            "workflowId": receipt.get("workflow_id"),
            "unit": receipt.get("unit"),
            "agent": receipt.get("agent"),
            "model": receipt.get("model"),
            "startedAt": receipt.get("started_at"),
            "endedAt": receipt.get("ended_at"),
            "outcome": (receipt.get("terminal") or {}).get("outcome"),
            "reason": (receipt.get("terminal") or {}).get("reason"),
            "artifact": receipt.get("artifact"),
            "stateChange": receipt.get("state_change"),
            "assertions": receipt.get("assertions", []),
            "usage": receipt.get("usage"),
            "cost": receipt.get("cost"),
            "nextAction": receipt.get("next_action"),
            "parentRunId": receipt.get("parent_run_id"),
            "handoff": receipt.get("handoff"),
        }

    def _envelope(self, items: Any, status: dict[str, Any]) -> dict[str, Any]:
        return {
            "apiVersion": API_VERSION,
            "generatedAt": iso_utc(self.clock()),
            "dataStatus": status,
            "items": items,
        }

    def list_workflows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        include_nonstanding = query.get("lifecycle") == ["all"]
        items, status = self.workflows(include_nonstanding=include_nonstanding)
        exact_filters = {
            "health": "health",
            "agent": "owner",
            "lifecycle": "lifecycle",
        }
        for parameter, field in exact_filters.items():
            wanted = query.get(parameter, [])
            if wanted and wanted != ["all"]:
                items = [item for item in items if str(item.get(field, "")).lower() in {value.lower() for value in wanted}]
        search = (query.get("q") or [""])[0].strip().lower()
        if search:
            items = [item for item in items if search in " ".join(str(item.get(key) or "") for key in ("id", "name", "owner", "purpose")).lower()]
        return self._envelope(items, status)

    def workflow_detail(self, workflow_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        items, status = self.workflows(include_nonstanding=True)
        return next((item for item in items if item["id"] == workflow_id), None), status

    def list_runs(self, workflow_id: str | None = None) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        receipts, malformed, source_errors = self.receipts()
        if workflow_id:
            receipts = [receipt for receipt in receipts if receipt.get("workflow_id") == workflow_id]
        items = [self._run_summary(receipt) for receipt in receipts]
        status = {
            "receipts": "available" if not source_errors and not malformed else "degraded",
            "errors": {"receipts": source_errors, "malformedReceipts": malformed},
        }
        return [item for item in items if item], status

    def run_detail(self, run_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        runs, status = self.list_runs()
        return next((run for run in runs if run["id"] == run_id), None), status

    def incidents(self) -> dict[str, Any]:
        workflows, status = self.workflows()
        _, malformed, _ = self.receipts()
        incidents: list[dict[str, Any]] = []
        for workflow in workflows:
            latest = workflow.get("lastRun")
            if workflow["contractStatus"] == "unavailable":
                incidents.append({
                    "id": f"contract-{workflow['id']}",
                    "severity": "medium",
                    "status": "open",
                    "workflowId": workflow["id"],
                    "agent": workflow["owner"],
                    "issue": workflow["contractError"],
                    "failedAssertion": "contract-available",
                    "requiredAction": "Declare and validate the workflow contract before receipt wiring.",
                    "runId": None,
                    "evidence": workflow["manifestPaths"],
                })
            if latest and workflow["health"] in {"failed", "incomplete"}:
                failed = [item.get("id") for item in latest.get("assertions", []) if item.get("status") == "failed"]
                incidents.append({
                    "id": f"run-{latest['id']}",
                    "severity": "high" if workflow["health"] == "failed" else "medium",
                    "status": "open",
                    "workflowId": workflow["id"],
                    "agent": workflow["owner"],
                    "issue": latest.get("reason") or f"run ended {workflow['health']}",
                    "failedAssertion": failed[0] if failed else None,
                    "requiredAction": (latest.get("nextAction") or {}).get("action") if isinstance(latest.get("nextAction"), dict) else None,
                    "runId": latest["id"],
                    "evidence": [latest.get("artifact", {}).get("uri")] if isinstance(latest.get("artifact"), dict) else [],
                })
        for index, invalid in enumerate(malformed):
            incidents.append({
                "id": f"malformed-receipt-{index + 1}",
                "severity": "high",
                "status": "open",
                "workflowId": None,
                "agent": None,
                "issue": "; ".join(invalid["errors"]),
                "failedAssertion": "receipt-schema-valid",
                "requiredAction": "Repair or quarantine the malformed receipt; do not infer its run outcome.",
                "runId": None,
                "evidence": [invalid["path"]],
            })
        return self._envelope(incidents, status)

    def usage(self) -> dict[str, Any]:
        receipts, malformed, source_errors = self.receipts()
        _, entries_errors = self._manifests()
        owners = sorted({entry["owner"] for entry in self._manifests()[0]})
        by_owner: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for receipt in receipts:
            by_owner[str(receipt.get("agent") or "unknown")].append(receipt)
        items: list[dict[str, Any]] = []
        for owner in owners:
            owner_receipts = by_owner.get(owner, [])
            measured_usage = [r["usage"] for r in owner_receipts if (r.get("usage") or {}).get("status") == "measured"]
            measured_cost = [r["cost"] for r in owner_receipts if (r.get("cost") or {}).get("status") == "measured"]
            usage = {"status": "unavailable", "inputTokens": None, "outputTokens": None, "cacheTokens": None, "totalTokens": None}
            if measured_usage:
                usage = {
                    "status": "measured",
                    "inputTokens": sum(int(value.get("input_tokens") or 0) for value in measured_usage),
                    "outputTokens": sum(int(value.get("output_tokens") or 0) for value in measured_usage),
                    "cacheTokens": sum(int(value.get("cache_tokens") or 0) for value in measured_usage),
                    "totalTokens": sum(int(value.get("total_tokens") or 0) for value in measured_usage),
                }
            currencies = {value.get("currency") for value in measured_cost}
            cost: dict[str, Any] = {"status": "unavailable", "amount": None, "currency": None}
            if measured_cost and len(currencies) == 1:
                cost = {"status": "measured", "amount": round(sum(float(value.get("amount") or 0) for value in measured_cost), 8), "currency": currencies.pop()}
            items.append({"agent": owner, "runCount": len(owner_receipts), "usage": usage, "cost": cost})
        status = {
            "receipts": "available" if not source_errors and not malformed else "degraded",
            "manifests": "available" if not entries_errors else "degraded",
            "errors": {"receipts": source_errors, "malformedReceipts": malformed, "manifests": entries_errors},
        }
        return self._envelope(items, status)

    def overview(self) -> dict[str, Any]:
        workflows, status = self.workflows()
        incidents = self.incidents()["items"]
        counts = defaultdict(int)
        for workflow in workflows:
            counts[workflow["health"]] += 1
        runs, _ = self.list_runs()
        outputs = [run for run in runs if isinstance(run.get("artifact"), dict)][:10]
        return {
            "apiVersion": API_VERSION,
            "generatedAt": iso_utc(self.clock()),
            "dataStatus": status,
            "summary": {
                "workflows": len(workflows),
                "healthy": counts["healthy"],
                "running": counts["running"],
                "needAttention": counts["failed"] + counts["incomplete"],
                "paused": counts["paused"],
                "unknown": counts["unknown"],
            },
            "needsAttention": incidents,
            "recentOutputs": outputs,
            "agentUsage": self.usage()["items"],
        }

    def activity(self) -> dict[str, Any]:
        runs, status = self.list_runs()
        items: list[dict[str, Any]] = []
        for run in runs:
            items.append({
                "id": f"run-{run['id']}-ended",
                "time": run["endedAt"],
                "type": "run",
                "actor": run.get("agent"),
                "event": f"{run['workflowId']} ended {run['outcome']}",
                "runId": run["id"],
                "status": run["outcome"],
            })
        items.sort(key=lambda item: parse_time(item.get("time")) or dt.datetime.min.replace(tzinfo=dt.timezone.utc), reverse=True)
        return self._envelope(items, status)

    def health(self) -> tuple[dict[str, Any], int]:
        entries, manifest_errors = self._manifests()
        _, malformed, receipt_errors = self.receipts()
        healthy = bool(entries) and not manifest_errors
        body = {
            "status": "ok" if healthy else "degraded",
            "apiVersion": API_VERSION,
            "generatedAt": iso_utc(self.clock()),
            "sources": {
                "manifests": "available" if entries and not manifest_errors else "unavailable",
                "receipts": "available" if not receipt_errors and not malformed else "degraded",
            },
            "errors": {"manifests": manifest_errors, "receipts": receipt_errors, "malformedReceipts": malformed},
        }
        return body, HTTPStatus.OK if healthy else HTTPStatus.SERVICE_UNAVAILABLE


class ControlRoomHandler(BaseHTTPRequestHandler):
    server_version = "PraetoriumControlRoom/1"
    model: ControlRoomReadModel

    def log_message(self, fmt: str, *args: Any) -> None:
        sys.stderr.write("control-room-api: " + fmt % args + "\n")

    def _json(self, status: int, body: Any, head_only: bool = False) -> None:
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _route(self, head_only: bool = False) -> None:
        parsed = urllib.parse.urlsplit(self.path)
        try:
            decoded = urllib.parse.unquote(parsed.path, errors="strict")
        except UnicodeDecodeError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid path encoding"}, head_only)
            return
        if ".." in decoded.split("/") or "\\" in decoded:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "invalid path"}, head_only)
            return
        segments = [segment for segment in decoded.split("/") if segment]
        query = urllib.parse.parse_qs(parsed.query, keep_blank_values=False)
        if segments == ["api", API_VERSION, "health"]:
            body, status = self.model.health()
            self._json(status, body, head_only)
            return
        if segments == ["api", API_VERSION, "overview"]:
            self._json(HTTPStatus.OK, self.model.overview(), head_only)
            return
        if segments == ["api", API_VERSION, "workflows"]:
            self._json(HTTPStatus.OK, self.model.list_workflows(query), head_only)
            return
        if len(segments) == 4 and segments[:3] == ["api", API_VERSION, "workflows"]:
            item, status = self.model.workflow_detail(segments[3])
            if item is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "workflow not found"}, head_only)
            else:
                self._json(HTTPStatus.OK, self.model._envelope(item, status), head_only)
            return
        if len(segments) == 5 and segments[:3] == ["api", API_VERSION, "workflows"] and segments[4] == "runs":
            item, _ = self.model.workflow_detail(segments[3])
            if item is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "workflow not found"}, head_only)
            else:
                runs, status = self.model.list_runs(segments[3])
                self._json(HTTPStatus.OK, self.model._envelope(runs, status), head_only)
            return
        if len(segments) == 4 and segments[:3] == ["api", API_VERSION, "runs"]:
            item, status = self.model.run_detail(segments[3])
            if item is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "run not found"}, head_only)
            else:
                self._json(HTTPStatus.OK, self.model._envelope(item, status), head_only)
            return
        if segments == ["api", API_VERSION, "incidents"]:
            self._json(HTTPStatus.OK, self.model.incidents(), head_only)
            return
        if segments == ["api", API_VERSION, "usage"]:
            self._json(HTTPStatus.OK, self.model.usage(), head_only)
            return
        if segments == ["api", API_VERSION, "activity"]:
            self._json(HTTPStatus.OK, self.model.activity(), head_only)
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "route not found"}, head_only)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._route()

    def do_HEAD(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        self._route(head_only=True)

    def _read_only(self) -> None:
        self._json(
            HTTPStatus.METHOD_NOT_ALLOWED,
            {"error": "read-only API; workflow controls use the separate allowlisted broker"},
        )

    do_POST = _read_only  # type: ignore[assignment]
    do_PUT = _read_only  # type: ignore[assignment]
    do_PATCH = _read_only  # type: ignore[assignment]
    do_DELETE = _read_only  # type: ignore[assignment]


def make_server(host: str, port: int, model: ControlRoomReadModel) -> ThreadingHTTPServer:
    handler = type("BoundControlRoomHandler", (ControlRoomHandler,), {"model": model})
    return ThreadingHTTPServer((host, port), handler)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1", help="listen address; defaults to loopback")
    parser.add_argument("--port", type=int, default=8787, help="listen port; defaults to 8787")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    model = ControlRoomReadModel()
    server = make_server(args.host, args.port, model)
    print(f"control-room-api: listening on http://{args.host}:{server.server_port}/api/{API_VERSION}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
