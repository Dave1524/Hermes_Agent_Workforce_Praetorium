#!/usr/bin/env python3
"""Benefit view for the Control Room (T5.3): measured from receipts, decided in the ledger, else Unknown."""
from __future__ import annotations

from typing import Any

from control_room_views import UNKNOWN, cell, esc, fmt_duration, fmt_rate, layout, link, table

DEFINITIONS = (
    ("decision", "Keep, Improve or Retire from design/benefit-ledger.toml; Unknown until one is recorded (T5.4)."),
    ("eligible runs", "receipts whose outcome is artifact, decline or failed; a skipped run never ran."),
    ("valid-artifact rate", "artifact outcomes over eligible runs; Unknown with no eligible run."),
    ("consumption", "four separate counts of opened / approved / sent / marked useful over artifact receipts that record them; Unknown when none does."),
    ("latency", "median run duration over eligible runs."),
    ("manual minutes avoided", "the ledger's own figure per run; never estimated here."),
)
HEADERS = ("workflow", "decision", "baseline", "eligible runs", "valid-artifact rate",
           "opened", "approved", "sent", "marked useful", "latency", "manual minutes avoided", "evidence", "owner")


def render_benefit(benefit_env: dict[str, Any]) -> str:
    definitions = "".join(f"<dt>{esc(term)}</dt><dd>{esc(text)}</dd>" for term, text in DEFINITIONS)
    rows = (_row(row) for row in sorted(benefit_env["items"], key=lambda row: row["workflowId"]))
    body = (
        "<h1>Benefit</h1>"
        f'<section id="definitions"><dl>{definitions}</dl></section>'
        f"{table(HEADERS, rows, table_id='benefit')}"
    )
    return layout("Benefit", body, benefit_env["dataStatus"], benefit_env["generatedAt"])


def _row(row: dict[str, Any]) -> str:
    consumption = row.get("consumption") or {}
    measured = consumption.get("status") == "measured"
    cells = [
        ("workflow", link(f"/workflows/{row['workflowId']}", row["workflowId"])),
        ("decision", cell(row.get("decision"))),
        ("baseline", cell(row.get("baseline"))),
        ("eligible-runs", cell(row.get("eligibleRuns"))),
        ("rate", fmt_rate(row.get("validArtifactRate"))),
    ]
    cells.extend((signal, cell(consumption.get(signal)) if measured else UNKNOWN)
                 for signal in ("opened", "approved", "sent", "marked_useful"))
    cells.extend([
        ("latency", fmt_duration(row.get("latencySeconds"))),
        ("manual-minutes", cell(row.get("manualMinutesAvoided"))),
        ("evidence", cell(row.get("evidence"))),
        ("owner", cell(row.get("decidedBy"))),
    ])
    tds = "".join(f'<td data-cell="{name}">{html}</td>' for name, html in cells)
    return f'<tr data-workflow="{esc(row["workflowId"])}">{tds}</tr>'
