#!/usr/bin/env python3
"""Layout shell and rendering helpers for the Control Room (T5.3). No view content lives here.

`cell()` is the one rendering rule: None or missing renders `Unknown`, a measurement dict whose
status is not `measured` renders `unavailable`, a measured number renders as that number — a
measured 0 is `0`, never blank, never a dash. Every string passes through html.escape.
"""
from __future__ import annotations

import html
from typing import Any, Iterable

from workflow_receipt import parse_time

NAV = (("/exceptions", "Exceptions"), ("/portfolio", "Portfolio"), ("/benefit", "Benefit"))
UNKNOWN = '<span class="unknown">Unknown</span>'
UNAVAILABLE = '<span class="unknown">unavailable</span>'
SOURCES = ("manifests", "contracts", "systemd", "receipts", "benefitLedger")


def esc(value: Any) -> str:
    return html.escape(str(value), quote=True)


def cell(value: Any, key: str | None = None) -> str:
    if value is None:
        return UNKNOWN
    if isinstance(value, dict) and "status" in value:
        if value.get("status") != "measured":
            return UNAVAILABLE
        return cell(value.get(key)) if key else esc(value["status"])
    if isinstance(value, bool):
        return "yes" if value else "no"
    if isinstance(value, float):
        return esc(f"{value:g}")
    if isinstance(value, (list, tuple)):
        return ", ".join(cell(item) for item in value) if value else UNKNOWN
    return esc(value)


def chip(state: Any, *classes: str) -> str:
    if state is None:
        return UNKNOWN
    names = " ".join(("chip", f"chip-{esc(state)}", *classes))
    return f'<span class="{names}">{esc(state)}</span>'


def fmt_time(value: Any) -> str:
    parsed = parse_time(value)
    if parsed is None:
        return UNKNOWN
    return f'<time datetime="{esc(value)}" title="{esc(value)}">{parsed.strftime("%Y-%m-%d %H:%M")}Z</time>'


def fmt_duration(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return UNKNOWN
    seconds = int(seconds)
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m {seconds % 60:02d}s"
    if seconds < 86400:
        return f"{seconds // 3600}h {(seconds % 3600) // 60:02d}m"
    return f"{seconds // 86400}d {(seconds % 86400) // 3600}h"


def fmt_tokens(usage: Any) -> str:
    if not isinstance(usage, dict) or usage.get("status") != "measured":
        return UNAVAILABLE
    total = usage.get("totalTokens", usage.get("total_tokens"))
    return f"{cell(total)} tokens"


def fmt_cost(cost: Any) -> str:
    if not isinstance(cost, dict) or cost.get("status") != "measured":
        return UNAVAILABLE
    return f"{cell(cost.get('amount'))} {esc(cost.get('currency') or '')}".strip()


def fmt_rate(rate: Any) -> str:
    if not isinstance(rate, (int, float)) or isinstance(rate, bool):
        return UNKNOWN
    return f"{round(rate * 100)}%"


def link(href: Any, text: Any, *, external: bool = False) -> str:
    if not href:
        return UNKNOWN
    target = ' target="_blank" rel="noopener"' if external else ""
    return f'<a href="{esc(href)}"{target}>{esc(text)}</a>'


def table(headers: Iterable[str], rows: Iterable[str], *, table_id: str | None = None, classes: str = "") -> str:
    ident = f' id="{esc(table_id)}"' if table_id else ""
    head = "".join(f"<th>{esc(header)}</th>" for header in headers)
    body = "".join(rows)
    return f'<table{ident} class="dense {classes}"><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table>'


def _status_strip(status: dict[str, Any]) -> str:
    errors = status.get("errors") or {}
    items = []
    for source in SOURCES:
        state = status.get(source) or "unknown"
        details = errors.get(source) or []
        if source == "receipts":
            details = [*details, *(f"malformed: {m.get('path')}" for m in errors.get("malformedReceipts") or [])]
        detail_html = "".join(f"<li>{esc(detail)}</li>" for detail in details) or "<li>no errors</li>"
        items.append(
            f'<details class="source source-{esc(state)}"><summary>{esc(source)}: {esc(state)}</summary>'
            f"<ul>{detail_html}</ul></details>"
        )
    return f'<div class="data-status">{"".join(items)}</div>'


def layout(title: str, body: str, status: dict[str, Any], generated_at: Any, *, scripts: Iterable[str] = ()) -> str:
    nav = "".join(f'<a href="{href}"{" class=current" if title == label else ""}>{label}</a>' for href, label in NAV)
    script_tags = "".join(f'<script src="/static/{esc(name)}" defer></script>' for name in ("app.js", *scripts))
    return (
        "<!doctype html><html lang=\"en\"><head><meta charset=\"utf-8\">"
        f"<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\"><title>{esc(title)} · Control Room</title>"
        f"<link rel=\"stylesheet\" href=\"/static/app.css\">{script_tags}</head><body>"
        f"<header><nav>{nav}</nav><div class=\"meta\"><span>generated {fmt_time(generated_at)}</span>"
        "<label class=\"auto-refresh\"><input type=\"checkbox\" id=\"auto-refresh\"> auto-refresh 60 s</label></div></header>"
        f"{_status_strip(status)}<main>{body}</main></body></html>"
    )


def not_found(what: str, status: dict[str, Any], generated_at: Any) -> str:
    body = f"<h1>Not found</h1><p>{esc(what)}</p><p><a href=\"/exceptions\">Back to Exceptions</a></p>"
    return layout("Not found", body, status, generated_at)


def age_text(seconds: Any) -> str:
    if not isinstance(seconds, (int, float)) or isinstance(seconds, bool):
        return UNKNOWN
    return f"{fmt_duration(seconds)} ago"

