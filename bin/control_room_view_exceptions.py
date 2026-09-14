#!/usr/bin/env python3
"""Exceptions view for the Control Room (T5.3): the opening screen — what is owed, and by whom."""
from __future__ import annotations

from typing import Any

from control_room_exceptions import KINDS, STALE_INPUT_NOTE
from control_room_views import UNKNOWN, cell, chip, esc, fmt_cost, fmt_time, fmt_tokens, layout, link, table

HEALTHS = ("healthy", "running", "failed", "incomplete", "paused", "unknown")
QUEUE_HEADERS = ("kind", "workflow", "owner", "issue", "required action", "evidence", "paused", "since")
QUALITY_HEADERS = ("check", "workflow", "issue", "required action", "evidence")


def render_exceptions(exceptions_env: dict[str, Any], overview: dict[str, Any], incidents: dict[str, Any]) -> str:
    rows = exceptions_env["items"]
    status = exceptions_env["dataStatus"]
    body = (
        "<h1>Exceptions</h1>"
        f"{_tiles(overview['summary'], rows)}"
        f"{_usage_strip(overview.get('agentUsage') or [])}"
        f"{_queue(rows, status, overview['summary'])}"
        f"{_data_quality(exceptions_env.get('dataQuality') or [])}"
    )
    return layout("Exceptions", body, status, exceptions_env["generatedAt"])


def _tiles(summary: dict[str, Any], rows: list[dict[str, Any]]) -> str:
    health = "".join(
        f'<div class="tile" data-tile="{state}"><strong>{cell(summary.get(state))}</strong> {state}</div>' for state in HEALTHS
    )
    incomplete = summary.get("incompleteRuns")
    by_kind = "".join(
        f'<div class="tile" data-tile="kind-{kind}"><strong>{sum(1 for r in rows if r["kind"] == kind)}</strong> {kind}</div>'
        for kind in KINDS
    )
    runs = (
        f'<div class="tile" data-tile="incomplete-runs"><strong>{cell(incomplete)}</strong> '
        f'<a href="#queue">incomplete + failed runs</a></div>'
    )
    return f'<section id="tiles"><div class="tiles">{health}{runs}</div><div class="tiles">{by_kind}</div></section>'


def _usage_strip(usage: list[dict[str, Any]]) -> str:
    cards = "".join(
        f'<div class="card" data-agent="{esc(agent["agent"])}"><strong>{esc(agent["agent"])}</strong> '
        f'<span>{cell(agent.get("runCount"))} runs</span> <span>{fmt_tokens(agent.get("usage"))}</span> '
        f'<span>{fmt_cost(agent.get("cost"))}</span></div>'
        for agent in usage
    ) or f'<div class="card">{UNKNOWN}</div>'
    return f'<section id="agent-usage"><h2>Agent usage</h2><div class="cards">{cards}</div></section>'


def _queue(rows: list[dict[str, Any]], status: dict[str, Any], summary: dict[str, Any]) -> str:
    if not rows:
        return f'<section id="queue-section"><h2>Queue</h2><p class="empty">{_empty_state(status, summary)}</p></section>'
    return f'<section id="queue-section"><h2>Queue</h2>{table(QUEUE_HEADERS, (_queue_row(r) for r in rows), table_id="queue")}</section>'


def _empty_state(status: dict[str, Any], summary: dict[str, Any]) -> str:
    if status.get("receipts") == "unavailable":
        return "Receipts unavailable — health is Unknown for every workflow; no exceptions can be derived."
    return f"No exceptions. {cell(summary.get('paused'))} paused, {cell(summary.get('unknown'))} unknown."


def _queue_row(row: dict[str, Any]) -> str:
    evidence = row.get("evidence") or {}
    title = f' title="{esc(STALE_INPUT_NOTE)}"' if row["kind"] == "stale-input" else ""
    also = ' <span class="chip chip-failed">also failed</span>' if row.get("alsoFailed") else ""
    links = " · ".join(part for part in (
        link(f"/runs/{evidence['runId']}", "run") if evidence.get("runId") else "",
        link(evidence.get("artifactUri"), "artifact", external=True) if evidence.get("artifactUri") else "",
    ) if part) or UNKNOWN
    cells = (
        f'<td data-cell="kind"{title}>{chip(row["kind"], "kind")}{also}</td>',
        f'<td data-cell="workflow">{link(f"/workflows/{row["workflowId"]}", row["workflowId"])}</td>',
        f'<td data-cell="owner">{cell(row.get("owner"))}</td>',
        f'<td data-cell="issue">{cell(row.get("issue"))}</td>',
        f'<td data-cell="action">{cell(row.get("requiredAction"))}</td>',
        f'<td data-cell="evidence">{links}</td>',
        f'<td data-cell="paused">{chip("paused") if row.get("paused") else ""}</td>',
        f'<td data-cell="since">{fmt_time(row.get("since"))}</td>',
    )
    return f'<tr data-workflow="{esc(row["workflowId"])}" data-kind="{esc(row["kind"])}">{"".join(cells)}</tr>'


def _data_quality(items: list[dict[str, Any]]) -> str:
    if not items:
        return '<section id="data-quality"><h2>Data quality</h2><p class="empty">No data-quality findings.</p></section>'
    rows = (
        f'<tr data-quality="{esc(item.get("failedAssertion"))}"><td>{cell(item.get("failedAssertion"))}</td>'
        f'<td>{link(f"/workflows/{item["workflowId"]}", item["workflowId"]) if item.get("workflowId") else UNKNOWN}</td>'
        f'<td>{cell(item.get("issue"))}</td><td>{cell(item.get("requiredAction"))}</td>'
        f'<td>{cell(item.get("evidence"))}</td></tr>'
        for item in items
    )
    return f'<section id="data-quality"><h2>Data quality</h2><p>Not exceptions: these say what the screen could not read.</p>{table(QUALITY_HEADERS, rows, table_id="quality")}</section>'
