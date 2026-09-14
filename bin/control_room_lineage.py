#!/usr/bin/env python3
"""Research lineage for the Control Room (T5.3): six stages from source to human action, pure.

Each stage names where its value came from — contract, manifest, receipt or systemd — so the
reader can tell a declared rule from an observed run. A stage with nothing behind it carries
`value: None` and `source: None` and renders Unknown; no stage is ever filled from a guess.
"""
from __future__ import annotations

import urllib.parse
from typing import Any

STAGES = ("source", "selection", "trigger", "agent", "output", "human_action")
NOTION_HOSTS = ("notion.so", "notion.site")


def lineage(workflow_item: dict[str, Any], latest_receipt: dict[str, Any] | None) -> list[dict[str, Any]]:
    contract = workflow_item.get("contract") if isinstance(workflow_item.get("contract"), dict) else {}
    receipt = latest_receipt or {}
    builders = {
        "source": lambda: _source(contract),
        "selection": lambda: _selection(contract, receipt),
        "trigger": lambda: _trigger(workflow_item),
        "agent": lambda: _agent(workflow_item, receipt),
        "output": lambda: _output(workflow_item),
        "human_action": lambda: _human_action(contract, receipt),
    }
    return [{"stage": stage, **builders[stage]()} for stage in STAGES]


def _stage(value: Any, source: str | None) -> dict[str, Any]:
    if value in (None, "", []):
        return {"value": None, "source": None}
    return {"value": value, "source": source}


def _inputs(contract: dict[str, Any]) -> list[dict[str, Any]]:
    return [row for row in contract.get("inputs") or [] if isinstance(row, dict)]


def _source(contract: dict[str, Any]) -> dict[str, Any]:
    sources = [str(row["source"]) for row in _inputs(contract) if row.get("source")]
    return _stage(sources, "contract")


def _selection(contract: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    lines: list[str] = []
    rule = contract.get("decline_conditions")
    if rule:
        lines.append(f"rule: {rule}")
    lines.extend(f"freshness: {row['source']} — {row['freshness']}"
                 for row in _inputs(contract) if row.get("source") and row.get("freshness"))
    reason = _selection_reason(receipt)
    if reason:
        lines.append(f"reason: {reason}")
    source = "contract" if len(lines) > (1 if reason else 0) else "receipt"
    return _stage(lines, source)


def _selection_reason(receipt: dict[str, Any]) -> str | None:
    terminal = receipt.get("terminal") or {}
    if terminal.get("outcome") == "decline":
        return terminal.get("reason")
    artifact = receipt.get("artifact")
    if terminal.get("outcome") == "artifact" and isinstance(artifact, dict):
        return artifact.get("title")
    return None


def _trigger(item: dict[str, Any]) -> dict[str, Any]:
    state = (item.get("control") or {}).get("state") or "unknown"
    texts = [f"{t.get('unit')}: {t.get('trigger')}" for t in item.get("triggers") or [] if t.get("trigger")]
    if texts:
        return _stage([*texts, f"state: {state}"], "manifest")
    return _stage(f"state: {state}" if state != "unknown" else None, "systemd")


def _agent(item: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    owner = item.get("owner")
    agent, model = receipt.get("agent"), receipt.get("model")
    if agent or model:
        ran = " ".join(part for part in (f"agent {agent}" if agent else None, f"model {model}" if model else None) if part)
        return _stage(f"{owner or 'owner Unknown'} — {ran}", "receipt")
    return _stage(owner, "manifest")


def output_label(uri: str) -> str:
    parsed = urllib.parse.urlsplit(uri)
    host = (parsed.hostname or "").lower()
    if any(host == suffix or host.endswith("." + suffix) for suffix in NOTION_HOSTS):
        return "Notion"
    return parsed.scheme or "uri"


def _output(item: dict[str, Any]) -> dict[str, Any]:
    last_valid = item.get("lastValidArtifact")
    if not isinstance(last_valid, dict) or not last_valid.get("uri"):
        return _stage(None, None)
    uri = str(last_valid["uri"])
    return _stage(f"{output_label(uri)}: {uri}", "receipt")


def _human_action(contract: dict[str, Any], receipt: dict[str, Any]) -> dict[str, Any]:
    lines: list[str] = []
    actor, action = contract.get("next_actor"), contract.get("next_action")
    if actor or action:
        lines.append(" → ".join(part for part in (actor, action) if part))
    next_action = receipt.get("next_action")
    if isinstance(next_action, dict) and (next_action.get("actor") or next_action.get("action")):
        due = f" (due {next_action['due_at']})" if next_action.get("due_at") else ""
        lines.append(f"receipt: {next_action.get('actor') or 'someone'} → {next_action.get('action') or 'unnamed'}{due}")
    return _stage(lines, "contract" if (actor or action) else "receipt")
