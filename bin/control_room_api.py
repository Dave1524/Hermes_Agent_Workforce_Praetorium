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

# The receipt schema — version, vocabularies, validation, time helpers — lives in the sibling
# bin/workflow_receipt.py since 2026-09-11 (T5.1), so the executor that writes receipts and
# this reader validate one shape. Sibling import, as the other bin/*.py do.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from workflow_receipt import iso_utc, parse_time, utc_now, validate as validate_receipt  # noqa: E402
from control_room_cadence import cadence_for, freshness, parse_systemd_timestamp  # noqa: E402
from control_room_benefit import benefit_row, load_ledger  # noqa: E402
import control_room_control  # noqa: E402
import control_room_proposals  # noqa: E402
from control_room_exceptions import KINDS, classify  # noqa: E402
from control_room_lineage import lineage  # noqa: E402
import incident_state  # noqa: E402
import workflow_incidents  # noqa: E402
import workflow_requires  # noqa: E402
from control_room_static import serve as serve_static, serve_app_asset, serve_app_shell  # noqa: E402
from control_room_view_benefit import render_benefit  # noqa: E402
from control_room_view_exceptions import render_exceptions  # noqa: E402
from control_room_view_portfolio import render_portfolio  # noqa: E402
from control_room_view_workflow import render_run, render_workflow  # noqa: E402
from control_room_views import not_found  # noqa: E402
from control_room_state import (  # noqa: E402
    ACTION_IDS,
    ACTIVE_STATES,
    control_for,
    fold_cadence,
    health as health_of,
    last_valid_artifact,
    links_for,
    no_cadence,
    role_of,
    trigger_state,
)


API_VERSION = "v1"
TASK_ID = re.compile(r"\bT\d+\.\d+[a-d]?\b")
OUTPUT_LABELS = (
    "Beneficiary",
    "Next actor",
    "Next action",
    "Benefit hypothesis",
    "Benefit signal",
)


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


def contract_inputs(text: str) -> list[dict[str, str | None]]:
    rows: list[dict[str, str | None]] = []
    for line in section(text, "Inputs").splitlines():
        if not line.startswith("|") or line.startswith("|---") or line.startswith("| Source"):
            continue
        cells = [clean_markdown(cell) for cell in line.strip().strip("|").split("|")]
        if len(cells) < 3 or not cells[0]:
            continue
        rows.append({"source": cells[0], "freshness": cells[1], "if_stale": cells[2]})
    return rows


def contract_task_ids(text: str) -> list[str]:
    head = "\n".join(text.splitlines()[:10])
    return sorted(set(TASK_ID.findall(head)))


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
    ledger: pathlib.Path | None = None
    incidents: pathlib.Path | None = None

    @property
    def incident_root(self) -> pathlib.Path:
        return self.incidents or self.runtime / "var" / "incidents"

    @classmethod
    def defaults(cls) -> "SourcePaths":
        script_root = pathlib.Path(__file__).resolve().parents[1]
        # bin/deploy copies this script into ~/agent-workforce, but design/ deliberately
        # remains source-only. Prefer the adjacent checkout during development and the
        # canonical source checkout when running from the deployed tree.
        default_repo = script_root
        if not (default_repo / "design" / "agents").is_dir():
            default_repo = pathlib.Path.home() / "dev" / "agent-workforce"
        repo = pathlib.Path(os.environ.get("CONTROL_ROOM_REPO_ROOT", default_repo)).resolve()
        runtime = pathlib.Path(
            os.environ.get("CONTROL_ROOM_RUNTIME_ROOT", pathlib.Path.home() / "agent-workforce")
        ).resolve()
        receipts = pathlib.Path(
            os.environ.get("CONTROL_ROOM_RECEIPT_ROOT", runtime / "var" / "workflow-receipts")
        ).resolve()
        incidents = pathlib.Path(
            os.environ.get("CONTROL_ROOM_INCIDENT_ROOT", runtime / "var" / "incidents")
        ).resolve()
        return cls(repo=repo, runtime=runtime, receipts=receipts, incidents=incidents)


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
        "NextElapseUSecMonotonic",
        "Persistent",
    )

    def show(self, name: str, scope: str) -> tuple[dict[str, str], str | None]:
        command = ["systemctl"]
        if scope == "user":
            command.append("--user")
        command.extend(["show", name, "--no-pager", "--timestamp=utc"])
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
        calendar_runner: Callable[[str], list[dt.datetime]] | None = None,
        control_reader: Callable[[str], dict[str, Any] | None] | None = None,
        static_dir: pathlib.Path | None = None,
        retry_policy: Callable[[dict[str, Any]], tuple[bool, str | None]] | None = None,
    ) -> None:
        self.paths = paths or SourcePaths.defaults()
        self.systemd = systemd or SystemdReader()
        self.clock = clock
        self.calendar_runner = calendar_runner
        self.control_reader = control_reader
        self.retry_policy = retry_policy
        self.static_dir = static_dir or pathlib.Path(__file__).resolve().parent / "control_room_ui"

    def _manifest_docs(self) -> tuple[list[tuple[pathlib.Path, dict[str, Any]]], list[str]]:
        docs: list[tuple[pathlib.Path, dict[str, Any]]] = []
        errors: list[str] = []
        manifest_dir = self.paths.repo / "design" / "agents"
        if not manifest_dir.is_dir():
            return [], [f"manifest directory unavailable: {manifest_dir}"]
        for path in sorted(manifest_dir.glob("*.toml")):
            try:
                docs.append((path, tomllib.loads(path.read_text())))
            except (OSError, tomllib.TOMLDecodeError) as exc:
                errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
        return docs, errors

    def _personas(self) -> list[dict[str, Any]]:
        """One per design/agents/*.toml — the persona, whether or not it owns a workflow."""
        docs, _ = self._manifest_docs()
        return [{"name": str(data.get("name") or path.stem), "title": data.get("role"),
                 "harness": data.get("harness"), "manifest": str(path.relative_to(self.paths.repo))}
                for path, data in docs]

    def _manifests(self) -> tuple[list[dict[str, Any]], list[str]]:
        rows: list[dict[str, Any]] = []
        docs, errors = self._manifest_docs()
        for path, data in docs:
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
            "inputs": contract_inputs(text),
            "decline_conditions": clean_markdown(section(text, "Decline conditions").replace("```", "")),
            "task_ids": contract_task_ids(text),
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
        return validate_receipt(data)

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

    @staticmethod
    def _stamp(values: dict[str, str], key: str) -> tuple[str | None, str | None]:
        raw = values.get(key) or None
        parsed = parse_systemd_timestamp(raw)
        return (iso_utc(parsed) if parsed else None), raw

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
        started, started_raw = self._stamp(service, "ExecMainStartTimestamp")
        ended, ended_raw = self._stamp(service, "ExecMainExitTimestamp")
        last_trigger, last_trigger_raw = self._stamp(timer, "LastTriggerUSec")
        next_run, next_run_raw = self._stamp(timer, "NextElapseUSecRealtime")
        return {
            "scope": scope,
            "kind": kind,
            "service": {
                "name": service_name,
                "activeState": service.get("ActiveState") or "unknown",
                "subState": service.get("SubState") or "unknown",
                "result": service.get("Result") or "unknown",
                "startedAt": started,
                "endedAt": ended,
                "exitStatus": int(service["ExecMainStatus"]) if service.get("ExecMainStatus", "").isdigit() else None,
                "raw": {"startedAt": started_raw, "endedAt": ended_raw},
            },
            "timer": None if kind != "timer" else {
                "name": unit if unit.endswith(".timer") else f"{unit}.timer",
                "activeState": timer.get("ActiveState") or "unknown",
                "subState": timer.get("SubState") or "unknown",
                "enabledState": timer.get("UnitFileState") or "unknown",
                "lastTriggerAt": last_trigger,
                "nextRunAt": next_run,
                "nextElapseMonotonic": timer.get("NextElapseUSecMonotonic") or None,
                "persistent": ({"yes": True, "no": False}.get(timer.get("Persistent", "")) if timer else None),
                "raw": {"lastTriggerAt": last_trigger_raw, "nextRunAt": next_run_raw},
            },
            "status": "available" if not errors else "unavailable",
            "errors": errors,
        }

    @staticmethod
    def _measurement(measurement: Any, fields: Iterable[str]) -> dict[str, Any]:
        if not isinstance(measurement, dict) or measurement.get("status") != "measured":
            return {"status": "unavailable", **{field: None for field in fields}}
        return {"status": "measured", **{field: measurement.get(field) for field in fields}}

    def _requires_for(self, group: list[dict[str, Any]], entries: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
        """One resolver for the screen and the executor pre-flights (bin/workflow_requires.py);
        the fold's entries declare the same list, so the union is that list."""
        requirements: dict[str, workflow_requires.Requirement] = {}
        errors: list[str] = []
        for entry in group:
            try:
                for requirement in workflow_requires.requirements_for(entry, entries, self.paths.repo):
                    requirements.setdefault(requirement.key, requirement)
            except ValueError as exc:
                errors.append(f"{entry['unit']}: {exc}")
        rows = []
        for requirement in requirements.values():
            state = workflow_requires.state_of(requirement, self.systemd.show)
            rows.append({"unit": requirement.unit, "scope": requirement.scope, "workflow": requirement.workflow,
                         "state": state, "satisfied": workflow_requires.satisfied(state)})
        return rows, errors

    @staticmethod
    def _fill_required_by(items: list[dict[str, Any]]) -> None:
        by_id = {item["id"]: item for item in items}
        for item in items:
            for requirement in item["requires"]:
                target = by_id.get(requirement["workflow"] or "")
                if target is not None:
                    target["requiredBy"].append({"workflow": item["id"], "enabled": item["control"]["state"] != "paused"})
        for item in items:
            item["requiredBy"].sort(key=lambda dependent: dependent["workflow"])

    def workflows(self, include_nonstanding: bool = False) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        all_entries, manifest_errors = self._manifests()
        receipts, malformed, receipt_errors = self.receipts()
        ledger, ledger_errors = load_ledger(self.paths.repo, self.paths.ledger)
        entries = all_entries
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
                kind = str(entry.get("kind") or "timer")
                scope = str(entry.get("scope") or "system")
                cadence = (cadence_for(self.paths.repo, str(entry["unit"]), scope, self.calendar_runner)
                           if kind == "timer" else no_cadence("not a timer"))
                triggers.append({
                    "unit": entry["unit"],
                    "scope": scope,
                    "kind": kind,
                    "surface": entry.get("surface"),
                    "trigger": entry.get("trigger"),
                    "runner": entry.get("runner"),
                    "route": entry.get("route"),
                    "systemd": systemd,
                    "state": trigger_state(systemd),
                    "cadence": cadence,
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
            cadence = fold_cadence(triggers)
            surface = triggers[0]["surface"]
            requires, requires_errors = self._requires_for(group, all_entries)
            manifest_errors.extend(requires_errors)
            last_valid = last_valid_artifact(workflow_receipts, self.clock())
            benefit = benefit_row({"id": logical_id, "contract": contract}, workflow_receipts,
                                  (ledger or {}).get(logical_id))
            item = {
                "id": logical_id,
                "name": logical_id.replace("-", " ").title(),
                "owners": owner_set,
                "owner": owner_set[0] if len(owner_set) == 1 else None,
                "purpose": purpose,
                "surface": surface,
                "role": role_of(surface),
                "requires": requires,
                "requiredBy": [],
                "guards": next((str(entry["guards"]) for entry in group if entry.get("guards")), None),
                "lifecycle": group[0].get("status", "unknown"),
                "health": health_of(latest, triggers),
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
                "cadence": cadence,
                "lastValidArtifact": last_valid,
                "artifactFreshness": freshness(last_valid["ageSeconds"] if last_valid else None, cadence),
                "control": control_for(logical_id, triggers, cadence, self.control_reader),
                "links": links_for(logical_id, contract),
                "benefit": benefit,
                "eligibleRuns": benefit["eligibleRuns"],
                "validArtifactRate": benefit["validArtifactRate"],
                "incompleteRuns": [self._run_summary(r) for r in workflow_receipts
                                   if r["terminal"]["outcome"] in {"skipped", "failed"}],
            }
            if self.retry_policy is not None:
                self._apply_retry_policy(item)
            item["lineage"] = lineage(item, latest)
            items.append(item)
        self._fill_required_by(items)
        status = {
            "manifests": "available" if not manifest_errors else "degraded",
            "contracts": "available" if not contract_errors else "degraded",
            "receipts": self._receipt_status(receipt_errors, malformed),
            "systemd": "available" if not systemd_errors else "degraded",
            "benefitLedger": "unavailable" if ledger is None else ("degraded" if ledger_errors else "available"),
            "errors": {
                "manifests": manifest_errors,
                "contracts": contract_errors,
                "receipts": receipt_errors,
                "malformedReceipts": malformed,
                "systemd": systemd_errors,
                "benefitLedger": ledger_errors,
            },
        }
        return items, status

    @staticmethod
    def _receipt_status(source_errors: list[str], malformed: list[dict[str, Any]]) -> str:
        if source_errors:
            return "unavailable"
        return "degraded" if malformed else "available"

    def _apply_retry_policy(self, item: dict[str, Any]) -> None:
        enabled, reason = self.retry_policy(item)
        for action in item["control"]["actions"]:
            if action["id"] == "retry":
                action["enabled"], action["reason"] = bool(enabled), reason

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
            "receiptPath": receipt.get("receipt_path"),
        }

    def _envelope(self, items: Any, status: dict[str, Any]) -> dict[str, Any]:
        return {
            "apiVersion": API_VERSION,
            "generatedAt": iso_utc(self.clock()),
            "dataStatus": status,
            "items": items,
        }

    def list_workflows(self, query: dict[str, list[str]]) -> dict[str, Any]:
        """Runtimes (`agent-runtime`) leave the list here and only here: the read model is the
        registry every other consumer reads, and `?role=all` is the `?lifecycle=all` convention."""
        include_nonstanding = query.get("lifecycle") == ["all"]
        items, status = self.workflows(include_nonstanding=include_nonstanding)
        if not query.get("role"):
            items = [item for item in items if item["role"] != "agent-runtime"]
        exact_filters = {
            "health": "health",
            "agent": "owner",
            "lifecycle": "lifecycle",
            "role": "role",
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
            "receipts": self._receipt_status(source_errors, malformed),
            "errors": {"receipts": source_errors, "malformedReceipts": malformed},
        }
        return [item for item in items if item], status

    def run_detail(self, run_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        runs, status = self.list_runs()
        return next((run for run in runs if run["id"] == run_id), None), status

    def contract_text(self, workflow_id: str) -> str | None:
        item, _ = self.workflow_detail(workflow_id)
        contract = (item or {}).get("contract")
        if not contract:
            return None
        path = (self.paths.repo / contract["path"]).resolve()
        if not path.is_relative_to(self.paths.repo) or not path.is_file():
            return None
        return path.read_text()

    INCIDENT_FIELDS = (
        ("class", "class"), ("key", "key"), ("severity", "severity"), ("workflowId", "workflow_id"),
        ("agent", "agent"), ("issue", "issue"), ("failedAssertion", "failed_assertion"),
        ("requiredAction", "required_action"), ("runId", "run_id"), ("evidence", "evidence"),
        ("firstSeen", "first_seen"), ("lastSeen", "last_seen"), ("resolvedAt", "resolved_at"),
        ("notifiedAt", "notified_at"), ("observations", "observations"),
    )

    def _incident_state(self) -> tuple[dict[str, Any], str]:
        """Read-only view of the notifier's state file; never moves a corrupt file aside."""
        path = self.paths.incident_root / "state.json"
        if not path.is_file():
            return incident_state.empty(), "unavailable"
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            return incident_state.empty(), "unavailable"
        if not isinstance(data, dict) or data.get("schema") != incident_state.SCHEMA or not isinstance(data.get("incidents"), dict):
            return incident_state.empty(), "unavailable"
        return data, "available"

    def _incident_item(self, entry: dict[str, Any], status: str) -> dict[str, Any]:
        item = {"id": entry["key"], "status": status}
        item.update({public: entry.get(field) for public, field in self.INCIDENT_FIELDS})
        item["observations"] = entry.get("observations") or 1
        return item

    def incidents(self) -> dict[str, Any]:
        workflows, status = self.workflows()
        _, malformed, source_errors = self.receipts()
        declared, _ = workflow_incidents.load_declared(self.paths.incident_root)
        observed = workflow_incidents.derive(
            workflows, malformed, source_errors, declared, self.clock(),
            manifest_errors=status["errors"]["manifests"],
        )
        state, state_status = self._incident_state()
        known = state["incidents"]
        items: list[dict[str, Any]] = []
        for observation in observed:
            entry = known.get(observation["key"])
            if entry and entry.get("resolved_at") is None:
                items.append(self._incident_item(entry, "open"))
                continue
            fresh = dict(observation, first_seen=observation.get("observed_at"), last_seen=iso_utc(self.clock()),
                         resolved_at=None, notified_at=None, observations=1)
            items.append(self._incident_item(fresh, "open"))
        seen = {item["id"] for item in items}
        for key, entry in sorted(known.items()):
            if key not in seen and entry.get("resolved_at"):
                items.append(self._incident_item(entry, "resolved"))
        status = dict(status, incidentState=state_status)
        return self._envelope(items, status)

    DATA_QUALITY_ASSERTIONS = {"contract-available", "receipt-schema-valid"}

    def exceptions(self) -> dict[str, Any]:
        workflows, status = self.workflows()
        receipts, _, _ = self.receipts()
        by_workflow: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for receipt in receipts:
            by_workflow[str(receipt["workflow_id"])].append(receipt)
        now = self.clock()
        rows = [row for workflow in workflows for row in classify(workflow, by_workflow.get(workflow["id"], []), now)]
        rows.sort(key=lambda row: (KINDS.index(row["kind"]), row["since"] or ""))
        envelope = self._envelope(rows, status)
        envelope["dataQuality"] = self._data_quality(status)
        return envelope

    def _data_quality(self, status: dict[str, Any]) -> list[dict[str, Any]]:
        quality = [item for item in self.incidents()["items"]
                   if item["failedAssertion"] in self.DATA_QUALITY_ASSERTIONS]
        for source in ("systemd", "manifests"):
            for error in status["errors"].get(source, []):
                quality.append({"id": f"{source}-{len(quality) + 1}", "severity": "medium", "status": "open",
                                "workflowId": None, "agent": None, "issue": error,
                                "failedAssertion": f"{source}-available", "requiredAction": None,
                                "runId": None, "evidence": []})
        return quality

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
            usage, cost = self._sum_measured(owner_receipts)
            items.append({"agent": owner, "runCount": len(owner_receipts), "usage": usage, "cost": cost})
        status = {
            "receipts": "available" if not source_errors and not malformed else "degraded",
            "manifests": "available" if not entries_errors else "degraded",
            "errors": {"receipts": source_errors, "malformedReceipts": malformed, "manifests": entries_errors},
        }
        return self._envelope(items, status)

    @staticmethod
    def _sum_measured(receipts: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
        """Sums over measured receipts only; none measured reads unavailable with null fields, never 0."""
        measured_usage = [r["usage"] for r in receipts if (r.get("usage") or {}).get("status") == "measured"]
        measured_cost = [r["cost"] for r in receipts if (r.get("cost") or {}).get("status") == "measured"]
        usage: dict[str, Any] = {"status": "unavailable", "inputTokens": None, "outputTokens": None,
                                 "cacheTokens": None, "totalTokens": None}
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
            cost = {"status": "measured", "amount": round(sum(float(value.get("amount") or 0) for value in measured_cost), 8),
                    "currency": currencies.pop()}
        return usage, cost

    def benefit(self) -> dict[str, Any]:
        workflows, status = self.workflows()
        return self._envelope([workflow["benefit"] for workflow in workflows], status)

    TURN_WINDOW_DAYS = 7

    def _runtime_of(self, row: dict[str, Any] | None) -> dict[str, Any]:
        """The agent's runtime from its `interactive` row: systemd's ActiveState as printed, `unknown`
        when the bus answered nothing; `since` is the start when active, else the last exit."""
        if row is None:
            return {"unit": None, "scope": None, "state": "unknown", "since": None}
        trigger = row["triggers"][0]
        service = trigger["systemd"]["service"]
        state = service["activeState"] if trigger["systemd"]["status"] == "available" else "unknown"
        since = service["startedAt"] if state in ACTIVE_STATES else service["endedAt"]
        return {"unit": trigger["unit"], "scope": trigger["scope"], "state": state, "since": since}

    def _agent_items(self, workflows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        receipts, _, _ = self.receipts()
        floor = self.clock() - dt.timedelta(days=self.TURN_WINDOW_DAYS)
        items: list[dict[str, Any]] = []
        for persona in sorted(self._personas(), key=lambda value: value["name"]):
            name = persona["name"]
            runtime_row = next((w for w in workflows if w["role"] == "agent-runtime" and w["id"] == f"buzz-agent@{name}"), None)
            turns = [r for r in receipts if r.get("vantage") == "interaction" and r.get("workflow_id") == f"buzz-agent@{name}"]
            recent = [r for r in turns if (parse_time(r.get("ended_at")) or floor) > floor]
            usage, cost = self._sum_measured(recent)
            items.append({
                **persona,
                "runtime": self._runtime_of(runtime_row),
                "health": runtime_row["health"] if runtime_row else "unknown",
                "lastTurn": self._run_summary(turns[0]) if turns else None,
                "turns7d": len(recent),
                "usage7d": usage,
                "cost7d": cost,
                "ownedWorkflows": [{"id": w["id"], "role": w["role"]} for w in workflows
                                   if name in w["owners"] and w["role"] != "agent-runtime"],
                "requiredBy": list(runtime_row["requiredBy"]) if runtime_row else [],
            })
        return items

    def agents(self) -> dict[str, Any]:
        workflows, status = self.workflows()
        return self._envelope(self._agent_items(workflows), status)

    def agent_detail(self, name: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        envelope = self.agents()
        return next((item for item in envelope["items"] if item["name"] == name), None), envelope["dataStatus"]

    @staticmethod
    def _agent_summary(agents: list[dict[str, Any]]) -> dict[str, int]:
        buckets = {"total": len(agents), "up": 0, "down": 0, "unknown": 0}
        for agent in agents:
            state = agent["runtime"]["state"]
            buckets["up" if state in ACTIVE_STATES else "unknown" if state == "unknown" else "down"] += 1
        return buckets

    def overview(self) -> dict[str, Any]:
        every_row, status = self.workflows()
        workflows = [workflow for workflow in every_row if workflow["role"] != "agent-runtime"]
        agents = self._agent_summary(self._agent_items(every_row))
        incidents = [item for item in self.incidents()["items"] if item["status"] == "open"]
        counts = defaultdict(int)
        for workflow in workflows:
            counts[workflow["health"]] += 1
        runs, _ = self.list_runs()
        outputs = [run for run in runs if isinstance(run.get("artifact"), dict)][:10]
        return {
            "apiVersion": API_VERSION,
            "generatedAt": iso_utc(self.clock()),
            "dataStatus": status,
            "reliability7d": self._reliability_7d(runs, status["receipts"]),
            "summary": {
                "workflows": len(workflows),
                "healthy": counts["healthy"],
                "running": counts["running"],
                "failed": counts["failed"],
                "incomplete": counts["incomplete"],
                "needAttention": counts["failed"] + counts["incomplete"],
                "paused": counts["paused"],
                "unknown": counts["unknown"],
                "incompleteRuns": sum(len(w["incompleteRuns"]) for w in workflows) + counts["running"],
                "agents": agents,
            },
            "needsAttention": incidents,
            "recentOutputs": outputs,
            "agentUsage": self.usage()["items"],
        }

    RELIABILITY_DAYS = 7
    ELIGIBLE_OUTCOMES = {"artifact", "decline", "failed"}

    def _reliability_7d(self, runs: list[dict[str, Any]], receipts_status: str) -> dict[str, Any]:
        """Valid artifacts over eligible runs per UTC day, the last seven ending today. A day with no
        runs is a measured 0/0; the whole series is unavailable only when the receipt source is."""
        if receipts_status == "unavailable":
            return {"status": "unavailable", "days": []}
        today = self.clock().astimezone(dt.timezone.utc).date()
        days = [today - dt.timedelta(days=offset) for offset in range(self.RELIABILITY_DAYS - 1, -1, -1)]
        counts = {day: {"eligible": 0, "valid": 0} for day in days}
        for run in runs:
            ended = parse_time(run.get("endedAt"))
            if ended is None or run.get("outcome") not in self.ELIGIBLE_OUTCOMES:
                continue
            bucket = counts.get(ended.astimezone(dt.timezone.utc).date())
            if bucket is None:
                continue
            bucket["eligible"] += 1
            bucket["valid"] += int(run["outcome"] == "artifact")
        return {"status": "measured", "days": [{"day": day.isoformat(), **counts[day]} for day in days]}

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

    CSP = "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'"
    COMMON_HEADERS = (("Cache-Control", "no-store"), ("X-Content-Type-Options", "nosniff"), ("Referrer-Policy", "no-referrer"))
    HTML_HEADERS = (("Content-Security-Policy", CSP), ("X-Frame-Options", "DENY"), *COMMON_HEADERS)
    STUBS = {
        "actions": ("action", ACTION_IDS, "control broker not wired (T5.3a)"),
        "proposals": ("kind", ("schedule", "retire"), "PR generator not wired (T5.3b)"),
    }

    def _send(self, status: int, content_type: str, payload: bytes, head_only: bool,
              headers: tuple[tuple[str, str], ...] = COMMON_HEADERS) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        for name, value in headers:
            self.send_header(name, value)
        self.end_headers()
        if not head_only:
            self.wfile.write(payload)

    def _json(self, status: int, body: Any, head_only: bool = False) -> None:
        payload = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._send(status, "application/json; charset=utf-8", payload, head_only)

    def _html(self, status: int, html: str, head_only: bool) -> None:
        self._send(status, "text/html; charset=utf-8", html.encode("utf-8"), head_only, self.HTML_HEADERS)

    def _text(self, status: int, text: str, head_only: bool) -> None:
        self._send(status, "text/plain; charset=utf-8", text.encode("utf-8"), head_only)

    APP_PREFIX = "app"

    def _route_page(self, segments: list[str], head_only: bool) -> bool:
        model = self.model
        if not segments:
            self.send_response(HTTPStatus.FOUND)
            self.send_header("Location", f"/{self.APP_PREFIX}/")
            self.send_header("Content-Length", "0")
            self.end_headers()
        elif segments[0] == self.APP_PREFIX:
            self._app(segments[1:], head_only)
        elif segments == ["favicon.ico"]:
            self.send_response(HTTPStatus.NO_CONTENT)
            self.end_headers()
        elif segments == ["exceptions"]:
            self._html(HTTPStatus.OK, render_exceptions(model.exceptions(), model.overview(), model.incidents()), head_only)
        elif segments == ["portfolio"]:
            self._html(HTTPStatus.OK, render_portfolio(model.list_workflows({"role": ["all"]})), head_only)
        elif segments == ["benefit"]:
            self._html(HTTPStatus.OK, render_benefit(model.benefit()), head_only)
        elif len(segments) == 2 and segments[0] == "workflows":
            self._workflow_page(segments[1], head_only)
        elif len(segments) == 2 and segments[0] == "runs":
            self._run_page(segments[1], head_only)
        elif len(segments) == 2 and segments[0] == "static":
            self._static(segments[1], head_only)
        else:
            return False
        return True

    def _workflow_page(self, workflow_id: str, head_only: bool) -> None:
        item, status = self.model.workflow_detail(workflow_id)
        generated = iso_utc(self.model.clock())
        if item is None:
            self._html(HTTPStatus.NOT_FOUND, not_found(f"no workflow {workflow_id}", status, generated), head_only)
            return
        runs, _ = self.model.list_runs(workflow_id)
        self._html(HTTPStatus.OK, render_workflow(item, runs, status=status, generated_at=generated), head_only)

    def _run_page(self, run_id: str, head_only: bool) -> None:
        run, status = self.model.run_detail(run_id)
        generated = iso_utc(self.model.clock())
        if run is None:
            self._html(HTTPStatus.NOT_FOUND, not_found(f"no run {run_id}", status, generated), head_only)
            return
        self._html(HTTPStatus.OK, render_run(run, status=status, generated_at=generated), head_only)

    def _static(self, name: str, head_only: bool) -> None:
        status, content_type, payload = serve_static(self.model.static_dir, name)
        if status != HTTPStatus.OK or content_type is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "static file not found"}, head_only)
            return
        self._send(HTTPStatus.OK, content_type, payload, head_only)

    def _app(self, segments: list[str], head_only: bool) -> None:
        """/app and every client route serve the SPA shell; only /app/assets/<name> is a file.

        The shell carries HTML_HEADERS like the SSR pages, so the CSP governs the bundle it loads.
        A shell that is not on disk means the runtime tree was deployed without a build — a 404
        that names it, never a fallback to the SSR views, which would hide the missing deploy."""
        if segments[:1] == ["assets"]:
            status, content_type, payload = (404, None, b"")
            if len(segments) == 2:
                status, content_type, payload = serve_app_asset(self.model.static_dir, segments[1])
            if status != HTTPStatus.OK or content_type is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "app asset not found"}, head_only)
                return
            self._send(HTTPStatus.OK, content_type, payload, head_only)
            return
        status, payload = serve_app_shell(self.model.static_dir)
        if status != HTTPStatus.OK:
            self._json(HTTPStatus.NOT_FOUND, {"error": "app shell not found"}, head_only)
            return
        self._send(HTTPStatus.OK, "text/html; charset=utf-8", payload, head_only, self.HTML_HEADERS)

    def _route_api_extra(self, segments: list[str], head_only: bool) -> bool:
        if len(segments) == 5 and segments[:3] == ["api", API_VERSION, "workflows"] and segments[4] == "contract":
            text = self.model.contract_text(segments[3])
            if text is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "contract not found"}, head_only)
            else:
                self._text(HTTPStatus.OK, text, head_only)
            return True
        if len(segments) >= 3 and segments[:3] == ["api", API_VERSION, "control"]:
            self._json(HTTPStatus.METHOD_NOT_ALLOWED, {"error": "control endpoints accept POST only"}, head_only)
            return True
        return False

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
        if self._route_page(segments, head_only) or self._route_api_extra(segments, head_only):
            return
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
        if segments == ["api", API_VERSION, "agents"]:
            self._json(HTTPStatus.OK, self.model.agents(), head_only)
            return
        if len(segments) == 4 and segments[:3] == ["api", API_VERSION, "agents"]:
            item, status = self.model.agent_detail(segments[3])
            if item is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "agent not found"}, head_only)
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
        if segments == ["api", API_VERSION, "benefit"]:
            self._json(HTTPStatus.OK, self.model.benefit(), head_only)
            return
        if segments == ["api", API_VERSION, "exceptions"]:
            self._json(HTTPStatus.OK, self.model.exceptions(), head_only)
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

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        segments = [s for s in urllib.parse.urlsplit(self.path).path.split("/") if s]
        if segments == ["api", API_VERSION, "control", "actions"]:
            control_room_control.handle_post(self, getattr(type(self), "control", None), self.model)
        elif segments == ["api", API_VERSION, "control", "proposals"]:
            control_room_proposals.handle_post(self, getattr(type(self), "proposals", None), self.model)
        elif len(segments) == 4 and segments[:3] == ["api", API_VERSION, "control"] and segments[3] in self.STUBS:
            self._control_stub(*self.STUBS[segments[3]])
        else:
            self._read_only()

    def _control_stub(self, field: str, vocabulary: tuple[str, ...], error: str) -> None:
        if self.headers.get("X-Control-Room") != "1":
            self._json(HTTPStatus.BAD_REQUEST, {"error": "X-Control-Room: 1 header required"})
            return
        body = self._json_body()
        if body is None:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
            return
        value = body.get(field)
        if value not in vocabulary:
            self._json(HTTPStatus.BAD_REQUEST, {"error": f"{field} must be one of {', '.join(vocabulary)}"})
            return
        workflow_id = str(body.get("workflow_id") or "")
        if self.model.workflow_detail(workflow_id)[0] is None:
            self._json(HTTPStatus.NOT_FOUND, {"error": "workflow not found"})
            return
        self._json(HTTPStatus.NOT_IMPLEMENTED, {"status": "not_implemented", "error": error,
                                               "workflow_id": workflow_id, field: value})

    def _json_body(self) -> dict[str, Any] | None:
        try:
            length = min(int(self.headers.get("Content-Length") or 0), 65536)
            body = json.loads(self.rfile.read(length) or b"")
        except (ValueError, OSError):
            return None
        return body if isinstance(body, dict) else None

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
    parser.add_argument("--static-dir", default=str(pathlib.Path(__file__).resolve().parent / "control_room_ui"),
                        help="directory served under /static/ (SSR assets) and, from its app/ subtree, /app/ "
                             "(the committed SPA build); defaults to bin/control_room_ui next to this script")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = SourcePaths.defaults()
    control = control_room_control.ControlRoomControl.from_env(paths.repo)
    model = ControlRoomReadModel(paths=paths, static_dir=pathlib.Path(args.static_dir),
                                 control_reader=control.receipts.last_action, retry_policy=control.retry_policy)
    server = make_server(args.host, args.port, model)
    server.RequestHandlerClass.control = control
    server.RequestHandlerClass.proposals = control_room_proposals.ProposalsControl.from_env()
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
