#!/usr/bin/env python3
"""Portfolio view for the Control Room (T5.3): one row per logical workflow, nothing hidden."""
from __future__ import annotations

from typing import Any

from control_room_views import UNKNOWN, cell, chip, esc, fmt_time, layout, link, table

HEALTH_ORDER = {"failed": 0, "incomplete": 1, "unknown": 2, "paused": 3, "running": 4, "healthy": 5}
HEADERS = ("workflow", "owner", "purpose", "trigger(s)", "artifact / state change", "beneficiary",
           "next actor → next action", "benefit", "health", "last run", "last valid artifact", "links")


def render_portfolio(workflows_env: dict[str, Any]) -> str:
    items = sorted(workflows_env["items"], key=lambda item: (HEALTH_ORDER.get(item.get("health"), 9), item["id"]))
    owners = sorted({item.get("owner") or "Unknown" for item in items})
    body = (
        "<h1>Portfolio</h1>"
        f"{_filters(owners)}"
        f"{table(HEADERS, (_row(item) for item in items), table_id='portfolio')}"
    )
    return layout("Portfolio", body, workflows_env["dataStatus"], workflows_env["generatedAt"])


def _filters(owners: list[str]) -> str:
    options = "".join(f'<option value="{esc(owner)}">{esc(owner)}</option>' for owner in owners)
    healths = "".join(f'<option value="{state}">{state}</option>' for state in HEALTH_ORDER)
    return (
        '<form class="filters" id="portfolio-filters" onsubmit="return false">'
        '<input type="search" id="filter-text" placeholder="filter text" aria-label="filter text">'
        f'<select id="filter-owner" aria-label="owner"><option value="">any owner</option>{options}</select>'
        f'<select id="filter-health" aria-label="health"><option value="">any health</option>{healths}</select>'
        '<span id="filter-count"></span></form>'
    )


def _row(item: dict[str, Any]) -> str:
    contract = item.get("contract") or {}
    links = item.get("links") or {}
    cells = (
        ("workflow", link(f"/workflows/{item['id']}", item["id"])),
        ("owner", cell(item.get("owner"))),
        ("purpose", cell(item.get("purpose"))),
        ("triggers", _triggers(item.get("triggers") or [])),
        ("artifact", cell(contract.get("artifact"))),
        ("beneficiary", cell(contract.get("beneficiary"))),
        ("next-action", _next_action(contract)),
        ("benefit", cell((item.get("benefit") or {}).get("decision"))),
        ("health", chip(item.get("health"))),
        ("last-run", _last_run(item.get("lastRun"))),
        ("last-artifact", _last_artifact(item)),
        ("links", _links(links)),
    )
    tds = "".join(_td(name, html) for name, html in cells)
    return f'<tr data-workflow="{esc(item["id"])}" data-health="{esc(item.get("health") or "unknown")}" data-owner="{esc(item.get("owner") or "")}">{tds}</tr>'


def _td(name: str, html: str, **attrs: str) -> str:
    extra = "".join(f' {key}="{esc(value)}"' for key, value in attrs.items())
    return f'<td data-cell="{name}"{extra}>{html}</td>'


def _triggers(triggers: list[dict[str, Any]]) -> str:
    if not triggers:
        return UNKNOWN
    return "".join(
        f'<div class="trigger"><code>{esc(t.get("unit"))}</code> {cell(t.get("trigger"))} {chip(t.get("state") or "unknown", "trigger-state")}</div>'
        for t in triggers
    )


def _next_action(contract: dict[str, Any]) -> str:
    actor, action = contract.get("next_actor"), contract.get("next_action")
    if not actor and not action:
        return UNKNOWN
    return f"{cell(actor)} → {cell(action)}"


def _last_run(run: dict[str, Any] | None) -> str:
    if not run:
        return UNKNOWN
    return f'{link(f"/runs/{run["id"]}", "run")} {fmt_time(run.get("endedAt"))} {chip(run.get("outcome"))}'


def _last_artifact(item: dict[str, Any]) -> str:
    last = item.get("lastValidArtifact")
    freshness = item.get("artifactFreshness") or "unknown"
    if not last:
        return f'<span data-freshness="{esc(freshness)}">{UNKNOWN}</span>'
    label = "Unknown" if freshness == "unknown" else freshness
    return (
        f'<span data-freshness="{esc(freshness)}">{fmt_time(last.get("endedAt"))} {chip(label, "freshness")} '
        f'{link(last.get("uri"), last.get("title") or "open", external=True)}</span>'
    )


def _links(links: dict[str, Any]) -> str:
    return " · ".join((
        link(links.get("contractLocal"), "contract"),
        link(links.get("contractGithub"), "GitHub", external=True),
        link(links.get("devPlanTracker"), "Dev Plan", external=True),
    ))
