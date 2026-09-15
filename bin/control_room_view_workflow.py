#!/usr/bin/env python3
"""Workflow and run pages for the Control Room (T5.3), including the Controls panel (§ Seams) and Lineage."""
from __future__ import annotations

import json
from typing import Any

from control_room_lineage import STAGES
from control_room_views import (UNAVAILABLE, UNKNOWN, age_text, cell, chip, esc, fmt_cost, fmt_duration, fmt_rate,
                                fmt_time, fmt_tokens, layout, link, table)

ACTIONS = (("pause", "Pause", False), ("resume", "Resume", False), ("run_now", "Run now", False),
           ("retry", "Retry", False), ("stop", "Stop current run", True))
PROPOSALS = (("schedule", "Change schedule…"), ("retire", "Retire…"))
RUN_HEADERS = ("run", "ended", "outcome", "reason", "failed checks")
ASSERTION_HEADERS = ("id", "status", "message")


def render_workflow(item: dict[str, Any], runs: list[dict[str, Any]], *,
                    status: dict[str, Any] | None = None, generated_at: Any = None) -> str:
    sections = (
        _header(item), _controls(item), _triggers(item), _runs(item, runs), _artifact(item),
        _tokens(item, runs), _benefit(item), _lineage(item), _links(item), _handoffs(item),
    )
    return layout(item["id"], "".join(sections), status or {}, generated_at, scripts=("actions.js", "proposals.js"))


def render_run(run: dict[str, Any], *, status: dict[str, Any] | None = None, generated_at: Any = None) -> str:
    artifact = run.get("artifact") if isinstance(run.get("artifact"), dict) else None
    next_action = run.get("nextAction") if isinstance(run.get("nextAction"), dict) else {}
    body = (
        f'<h1>Run {esc(run["id"])}</h1><p>{link(f"/workflows/{run["workflowId"]}", run["workflowId"])} · '
        f'{chip(run.get("outcome"))} · started {fmt_time(run.get("startedAt"))} · ended {fmt_time(run.get("endedAt"))}</p>'
        f'<section id="outcome"><h2>Outcome</h2><dl><dt>outcome</dt><dd>{chip(run.get("outcome"))}</dd>'
        f'<dt>reason</dt><dd>{reason_cell(run)}</dd></dl></section>'
        f'<section id="assertions"><h2>Assertions</h2>{_assertions(run.get("assertions") or [])}</section>'
        f'<section id="artifact"><h2>Artifact / state change</h2><dl>'
        f'<dt>artifact</dt><dd>{link(artifact.get("uri"), artifact.get("title") or artifact.get("uri"), external=True) if artifact else UNKNOWN}</dd>'
        f'<dt>state change</dt><dd>{_raw(run.get("stateChange"))}</dd></dl></section>'
        f'<section id="tokens"><h2>Usage and cost</h2><dl><dt>tokens</dt><dd>{fmt_tokens(run.get("usage"))}</dd>'
        f'<dt>cost</dt><dd>{fmt_cost(run.get("cost"))}</dd></dl></section>'
        f'<section id="next-action"><h2>Next action</h2><dl><dt>actor</dt><dd>{cell(next_action.get("actor"))}</dd>'
        f'<dt>action</dt><dd>{cell(next_action.get("action"))}</dd><dt>due</dt><dd>{fmt_time(next_action.get("due_at"))}</dd></dl></section>'
        f'<section id="parent"><h2>Parent run</h2><p>{link(f"/runs/{run["parentRunId"]}", run["parentRunId"]) if run.get("parentRunId") else UNKNOWN}</p></section>'
        f'<section id="handoffs"><h2>Handoff</h2>{_raw(run.get("handoff"))}</section>'
        f'<section id="receipt"><h2>Receipt</h2><p><code>{cell(run.get("receiptPath"))}</code></p></section>'
    )
    return layout(f"Run {run['id']}", body, status or {}, generated_at)


def _header(item: dict[str, Any]) -> str:
    return (
        f'<section id="header"><h1>{esc(item["id"])} {chip(item.get("health"))}</h1>'
        f'<dl><dt>owner</dt><dd>{cell(item.get("owner"))}</dd><dt>purpose</dt><dd>{cell(item.get("purpose"))}</dd>'
        f'<dt>lifecycle</dt><dd>{cell(item.get("lifecycle"))}</dd></dl></section>'
    )


def _controls(item: dict[str, Any]) -> str:
    control = item.get("control") or {}
    enabled = {action["id"]: action for action in control.get("actions") or []}
    buttons = "".join(_action_button(action, label, requires, enabled.get(action)) for action, label, requires in ACTIONS)
    proposals = "".join(f'<button type="button" data-proposal-kind="{kind}">{esc(label)}</button>' for kind, label in PROPOSALS)
    next_run = fmt_time(control.get("nextRunAt")) + (" (estimated)" if control.get("nextRunEstimated") else "")
    last_action = _raw(control.get("lastAction"))
    return (
        f'<section id="controls" data-workflow-id="{esc(item["id"])}"><h2>Controls</h2>'
        f'<dl><dt>state</dt><dd>{chip(control.get("state") or "unknown", "control-state")}</dd>'
        f'<dt>source</dt><dd>{cell(control.get("source"))}</dd><dt>next run</dt><dd>{next_run}</dd>'
        f'<dt>persistent</dt><dd>{cell(control.get("persistent"))}</dd><dt>last action</dt><dd>{last_action}</dd></dl>'
        f'<div class="buttons" data-row="actions">{buttons}</div><div class="buttons" data-row="proposals">{proposals}</div>'
        '<pre id="control-result"></pre></section>'
    )


def _action_button(action: str, label: str, requires_reason: bool, state: dict[str, Any] | None) -> str:
    is_enabled = bool(state and state.get("enabled"))
    reason = (state or {}).get("reason") or ("control state unavailable" if state is None else "")
    disabled = "" if is_enabled else " disabled"
    title = f' title="{esc(reason)}"' if reason else ""
    return (f'<button type="button" data-action="{action}" data-requires-reason="{"true" if requires_reason else "false"}"'
            f'{disabled}{title}>{esc(label)}</button>')


def _triggers(item: dict[str, Any]) -> str:
    rows = []
    for trigger in item.get("triggers") or []:
        systemd = trigger.get("systemd") or {}
        timer = systemd.get("timer") or {}
        cadence = trigger.get("cadence") or {}
        rows.append(
            f'<tr><td><code>{esc(trigger.get("unit"))}</code></td><td>{cell(trigger.get("scope"))}</td><td>{cell(trigger.get("kind"))}</td>'
            f'<td>{cell(trigger.get("trigger"))}</td><td>{_cadence(cadence)}</td>'
            f'<td>{cell(timer.get("activeState"))} / {cell(timer.get("enabledState"))}</td>'
            f'<td>{fmt_time(timer.get("lastTriggerAt"))}</td><td>{fmt_time(timer.get("nextRunAt"))}</td>'
            f'<td>{chip(trigger.get("state") or "unknown", "trigger-state")}</td></tr>'
        )
    body = table(("unit", "scope", "kind", "trigger", "cadence", "timer active / enabled", "last trigger", "next run", "state"), rows) if rows else UNKNOWN
    control = item.get("control") or {}
    estimated = f'<p>next run {fmt_time(control.get("nextRunAt"))} (estimated from last trigger + cadence)</p>' if control.get("nextRunEstimated") else ""
    return f'<section id="triggers"><h2>Triggers &amp; schedules</h2>{body}{estimated}</section>'


def _cadence(cadence: dict[str, Any]) -> str:
    if cadence.get("status") != "measured":
        return f'<span class="unknown" title="{esc(cadence.get("error") or "")}">unavailable</span>'
    return f'{fmt_duration(cadence.get("seconds"))} ({esc(cadence.get("source"))} {esc(cadence.get("spec"))})'


def _runs(item: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    last = item.get("lastRun")
    running = sum(1 for t in item.get("triggers") or [] if t.get("state") == "running")
    incomplete = len(item.get("incompleteRuns") or []) + running
    strip = "".join(f'{link(f"/runs/{run["id"]}", run.get("outcome") or "Unknown")} ' for run in runs[:10]) or UNKNOWN
    rows = (_run_row(run) for run in runs[:10])
    return (
        f'<section id="runs"><h2>Runs</h2><dl><dt>last run</dt><dd>{_run_line(last)}</dd>'
        f'<dt>incomplete runs</dt><dd>{incomplete if runs or running else UNKNOWN}</dd>'
        f'<dt>reliability</dt><dd>{fmt_rate(item.get("validArtifactRate"))} over {cell(item.get("eligibleRuns"))} eligible runs</dd>'
        f'<dt>last 10 outcomes</dt><dd class="strip">{strip}</dd></dl>'
        f'{table(RUN_HEADERS, rows, table_id="run-list") if runs else ""}</section>'
    )


def reason_cell(run: dict[str, Any]) -> str:
    if run.get("outcome") == "artifact" and run.get("reason") is None:
        return "none"
    return cell(run.get("reason"))


def _run_line(run: dict[str, Any] | None) -> str:
    if not run:
        return UNKNOWN
    return f'{link(f"/runs/{run["id"]}", run["id"])} {fmt_time(run.get("endedAt"))} {chip(run.get("outcome"))} {reason_cell(run)}'


def _run_row(run: dict[str, Any]) -> str:
    failed = [a.get("id") for a in run.get("assertions") or [] if a.get("status") == "failed"]
    return (
        f'<tr data-run="{esc(run["id"])}"><td>{link(f"/runs/{run["id"]}", run["id"])}</td><td>{fmt_time(run.get("endedAt"))}</td>'
        f'<td>{chip(run.get("outcome"))}</td><td>{reason_cell(run)}</td><td>{cell(failed) if failed else "none"}</td></tr>'
    )


def _artifact(item: dict[str, Any]) -> str:
    last = item.get("lastValidArtifact")
    cadence = item.get("cadence") or {}
    freshness = item.get("artifactFreshness") or "unknown"
    if not last:
        body = f"<p>{UNKNOWN}</p>"
    else:
        body = (
            f'<dl><dt>title</dt><dd>{link(last.get("uri"), last.get("title") or last.get("uri"), external=True)}</dd>'
            f'<dt>kind</dt><dd>{cell(last.get("kind"))}</dd><dt>ended</dt><dd>{fmt_time(last.get("endedAt"))}</dd>'
            f'<dt>freshness</dt><dd><span data-freshness="{esc(freshness)}">{chip("Unknown" if freshness == "unknown" else freshness, "freshness")}</span></dd>'
            f'<dt>age</dt><dd>{age_text(last.get("ageSeconds"))}</dd><dt>cadence</dt><dd>{_cadence(cadence)}</dd></dl>'
        )
    return f'<section id="artifact"><h2>Latest valid artifact</h2>{body}</section>'


def _tokens(item: dict[str, Any], runs: list[dict[str, Any]]) -> str:
    last = item.get("lastRun") or {}
    measured_usage = [r["usage"] for r in runs if isinstance(r.get("usage"), dict) and r["usage"].get("status") == "measured"]
    measured_cost = [r["cost"] for r in runs if isinstance(r.get("cost"), dict) and r["cost"].get("status") == "measured"]
    totals = f'{sum(int(u.get("total_tokens") or 0) for u in measured_usage)} tokens over {len(measured_usage)} measured runs' if measured_usage else UNAVAILABLE
    currencies = {c.get("currency") for c in measured_cost}
    total_cost = (f'{round(sum(float(c.get("amount") or 0) for c in measured_cost), 4):g} {esc(currencies.pop())}'
                  if measured_cost and len(currencies) == 1 else UNAVAILABLE)
    return (
        f'<section id="tokens"><h2>Tokens &amp; cost</h2><dl><dt>latest run tokens</dt><dd>{fmt_tokens(last.get("usage"))}</dd>'
        f'<dt>latest run cost</dt><dd>{fmt_cost(last.get("cost"))}</dd><dt>total tokens</dt><dd>{totals}</dd>'
        f'<dt>total cost</dt><dd>{total_cost}</dd></dl></section>'
    )


def _benefit(item: dict[str, Any]) -> str:
    row = item.get("benefit") or {}
    consumption = row.get("consumption") or {}
    measured = consumption.get("status") == "measured"
    signals = " / ".join(cell(consumption.get(s)) if measured else UNKNOWN for s in ("opened", "approved", "sent", "marked_useful"))
    return (
        f'<section id="benefit"><h2>Benefit &amp; consumption</h2><dl><dt>decision</dt><dd>{cell(row.get("decision"))}</dd>'
        f'<dt>baseline</dt><dd>{cell(row.get("baseline"))}</dd><dt>eligible runs</dt><dd>{cell(row.get("eligibleRuns"))}</dd>'
        f'<dt>valid-artifact rate</dt><dd>{fmt_rate(row.get("validArtifactRate"))}</dd>'
        f'<dt>opened / approved / sent / marked useful</dt><dd>{signals}</dd>'
        f'<dt>latency</dt><dd>{fmt_duration(row.get("latencySeconds"))}</dd>'
        f'<dt>manual minutes avoided</dt><dd>{cell(row.get("manualMinutesAvoided"))}</dd>'
        f'<dt>evidence</dt><dd>{cell(row.get("evidence"))}</dd><dt>decided by</dt><dd>{cell(row.get("decidedBy"))}</dd></dl></section>'
    )


def _lineage(item: dict[str, Any]) -> str:
    stages = {stage["stage"]: stage for stage in item.get("lineage") or []}
    items = "".join(
        f'<li data-stage="{stage}" data-source="{esc(stages.get(stage, {}).get("source") or "")}">'
        f'<strong>{esc(stage.replace("_", " "))}</strong> {_stage_value(stages.get(stage, {}).get("value"))}'
        f' <small>{esc(stages.get(stage, {}).get("source") or "no source")}</small></li>'
        for stage in STAGES
    )
    return f'<section id="lineage"><h2>Lineage</h2><ol class="lineage">{items}</ol></section>'


def _stage_value(value: Any) -> str:
    if isinstance(value, list):
        return "".join(f'<div class="stage-line">{esc(v)}</div>' for v in value)
    return cell(value)


def _links(item: dict[str, Any]) -> str:
    links = item.get("links") or {}
    task_ids = cell(links.get("taskIds")) if links.get("taskIds") else UNKNOWN
    manifests = cell(item.get("manifestPaths"))
    return (
        f'<section id="links"><h2>Links</h2><dl><dt>contract</dt><dd>{link(links.get("contractLocal"), "local")} · '
        f'{link(links.get("contractGithub"), "GitHub", external=True)}</dd>'
        f'<dt>Dev Plan</dt><dd>{link(links.get("devPlanTracker"), "tracker", external=True)} · {link(links.get("devPlanDoc"), "doc", external=True)}</dd>'
        f'<dt>task ids</dt><dd>{task_ids}</dd><dt>manifests</dt><dd>{manifests}</dd></dl></section>'
    )


def _handoffs(item: dict[str, Any]) -> str:
    handoff = (item.get("lastRun") or {}).get("handoff")
    return f'<section id="handoffs"><h2>Handoffs</h2>{_raw(handoff)}</section>'


def _raw(value: Any) -> str:
    if value is None:
        return UNKNOWN
    return f"<pre>{esc(json.dumps(value, indent=2, sort_keys=True))}</pre>"


def _assertions(assertions: list[dict[str, Any]]) -> str:
    if not assertions:
        return f"<p>{UNKNOWN}</p>"
    rows = (f'<tr><td>{cell(a.get("id"))}</td><td>{chip(a.get("status"))}</td><td>{cell(a.get("message"))}</td></tr>' for a in assertions)
    return table(ASSERTION_HEADERS, rows, table_id="assertion-list")
