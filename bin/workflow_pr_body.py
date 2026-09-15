#!/usr/bin/env python3
"""PR title, body and commit message for a proposal (T5.3b) — pure over the record. The body is
what the reviewer reads instead of the branch: current → proposed, the exact diff, every check,
the residue tables and the land steps this PR deliberately does not perform.
"""
from __future__ import annotations

from typing import Any

W19_COLUMNS = ("#", "residue", "tree", "has a check?", "who clears it", "how")
DIFF_BODY_LIMIT = 40000


def title(rec: dict[str, Any]) -> str:
    return commit_message(rec).splitlines()[0]


def commit_message(rec: dict[str, Any]) -> str:
    desc = rec.get("description") or {}
    if rec["kind"] == "schedule":
        first = f"control-room(schedule): {rec['workflow_id']} — {desc.get('unit', rec['workflow_id'])}.timer to {' / '.join(desc.get('proposed', {}).get('on_calendar', []))}"
        detail = f"OnCalendar: {' / '.join(desc.get('current', {}).get('on_calendar', []))} → {' / '.join(desc.get('proposed', {}).get('on_calendar', []))}"
    else:
        first = f"control-room(retire): {rec['workflow_id']} — retire {', '.join(desc.get('units', [rec['workflow_id']]))}"
        detail = "Removed: " + ", ".join(f"{f['path']} ({f['change']})" for f in rec.get("files", [])) if rec.get("files") else "Removed: see diff"
    return "\n".join([first, "", f"Requested from the Control Room by {(rec.get('actor') or {}).get('label', 'unknown')} at {rec.get('requested_at')}.",
                      f"Proposal: {rec['proposal_id']}", f"Reason: {rec.get('reason') or ''}", detail, ""])


def _request_line(rec: dict[str, Any]) -> str:
    actor = (rec.get("actor") or {}).get("label", "unknown")
    return f"Requested by **{actor}** at {rec.get('requested_at')} · proposal `{rec['proposal_id']}` · reason: {rec.get('reason') or '—'}"


def _table(headers: tuple[str, ...], rows: list[list[str]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers)]
    out += ["| " + " | ".join(str(cell).replace("|", "\\|").replace("\n", " ") for cell in row) + " |" for row in rows]
    return "\n".join(out)


def _checks(rec: dict[str, Any]) -> str:
    rows = [[c["id"], c["class"], c["status"], (c.get("output") or "").splitlines()[0][:160] if c.get("output") else ""] for c in rec.get("checks", [])]
    return _table(("check", "class", "status", "first line"), rows) if rows else "_no checks recorded_"


def _attention(rec: dict[str, Any]) -> str:
    desc = rec.get("description") or {}
    lines = list(desc.get("reviewer_attention") or [])
    for check in rec.get("checks", []):
        if check["id"] == "schedule-collisions" and check["status"] == "warn":
            lines.extend(f"collision: {line}" for line in check["output"].splitlines())
        if check["class"] == "pinned" and check["status"] == "fail":
            for line in check["output"].splitlines():
                if "(exit" in line:
                    lines.append(f"Red on purpose until {line.split(' (exit')[0]} is updated for the new schedule/removal — this PR opened as a draft.")
    return "\n".join(f"- {line}" for line in lines) or "_nothing beyond the diff_"


def _diff(rec: dict[str, Any]) -> str:
    text = (rec.get("diff") or "(diff stored beside the record)").rstrip()
    if len(text) > DIFF_BODY_LIMIT:  # GitHub refuses a body over 65,536 characters; the branch carries the rest
        text = text[:DIFF_BODY_LIMIT].rstrip() + f"\n… diff truncated at {DIFF_BODY_LIMIT} characters; the branch and the record ({rec.get('diff_stat') or 'see files'}) carry the whole change"
    return f"```diff\n{text}\n```"


def _residue_table(report: dict[str, Any] | None) -> str:
    if not report or not report.get("items"):
        return f"_none — verdict {report.get('verdict', 'clear') if report else 'clear'}_"
    rows = [[str(i + 1), f"{item['class']}: {item['what']}" + (f" ({item['path']}{':' + str(item['line']) if item.get('line') else ''})" if item.get("path") else ""),
             item.get("tree", ""), item.get("has_check", ""), item.get("clears", ""), item.get("how", "")] for i, item in enumerate(report["items"])]
    return _table(W19_COLUMNS, rows) + f"\n\nVerdict: **{report.get('verdict')}**"


def _schedule_body(rec: dict[str, Any]) -> str:
    desc = rec.get("description") or {}
    cur, new = desc.get("current", {}), desc.get("proposed", {})
    nexts = lambda side: "<br>".join(f"{e['local']} = {e['utc']}" for e in side.get("next", [])) or "—"  # noqa: E731
    rows = [["OnCalendar", " / ".join(cur.get("on_calendar", [])), " / ".join(new.get("on_calendar", []))],
            ["RandomizedDelaySec", cur.get("randomized_delay_sec") or "—", new.get("randomized_delay_sec") or "—"],
            ["Persistent", str(cur.get("persistent")), str(new.get("persistent"))],
            [f"next elapses ({(desc.get('timezone') or {}).get('name', 'local')} / UTC)", nexts(cur), nexts(new)],
            ["catch-up", "", desc.get("catch_up", "")], ["takes effect", "", desc.get("takes_effect", "")],
            ["manifest trigger", "", desc.get("manifest_trigger") or ""], ["contract trigger", "", desc.get("contract_trigger") or ""]]
    unit = desc.get("unit", rec["workflow_id"])
    scope = desc.get("scope", "system")
    land = _schedule_land(unit, scope, desc)
    return "\n\n".join([f"# Schedule change: {rec['workflow_id']} ({unit}.timer)", _request_line(rec),
                        "## Current → proposed\n\n" + _table(("field", "current", "proposed"), rows),
                        "## Diff\n\n" + _diff(rec), "## Checks\n\n" + _checks(rec), "## Reviewer attention\n\n" + _attention(rec), land]) + "\n"


def _schedule_land(unit: str, scope: str, desc: dict[str, Any]) -> str:
    etc = "~/.config/systemd/user/" if scope == "user" else "/etc/systemd/system/"
    sudo = "" if scope == "user" else "sudo "
    user = "--user " if scope == "user" else ""
    active = "restart" in desc.get("takes_effect", "")
    steps = ["1. Merge (no auto-merge; `allow_auto_merge` is off).",
             "2. On the box: `git -C ~/dev/agent-workforce pull --ff-only`",
             "3. `bin/deploy`",
             f"4. `{sudo}cp systemd/{'user/' if scope == 'user' else ''}{unit}.timer {etc} && {sudo}systemctl {user}daemon-reload`",
             (f"5. The timer is active: `{sudo}systemctl {user}restart {unit}.timer`" if active else
              f"5. Only if the timer is active: `{sudo}systemctl {user}restart {unit}.timer` — it is paused today, so the schedule applies at resume."),
             "6. `bash bin/verify.sh`"]
    return "## Land (Dave-only; this PR does none of it)\n\n" + "\n".join(steps)


def _retire_body(rec: dict[str, Any]) -> str:
    desc = rec.get("description") or {}
    units = desc.get("units") or [rec["workflow_id"]]
    evidence = desc.get("evidence") or {}
    retention = rec.get("retention") or {}
    subjects = desc.get("subjects") or {}
    residue = rec.get("residue") or {}
    ev_rows = [["last valid artifact", str(evidence.get("lastValidArtifact") or "Unknown")],
               ["valid-artifact rate", str(evidence.get("validArtifactRate") or "Unknown")],
               ["benefit decision", str(evidence.get("benefit") or "Unknown")]]
    ret_rows = [[key, str(retention.get(key, "—")), _retention_command(key, retention.get(key), rec["workflow_id"])] for key in ("receipts", "notion", "inbox")]
    ret_rows.append(["note", str(retention.get("note", "—")), ""])
    removal = _table(("path", "change", "join that forces it"), [[r["path"], r["change"], r["join"]] for r in desc.get("removal", [])]) or "_nothing_"
    deploy = next((c for c in rec.get("checks", []) if c["id"] == "deploy-preview"), None)
    land = _retire_land(units, subjects, desc, deploy, rec)
    return "\n\n".join([f"# Retire: {rec['workflow_id']}", _request_line(rec),
                        "## Decision evidence\n\n" + _table(("evidence", "value"), ev_rows),
                        "## Artifact retention\n\n" + _table(("artifact", "decision", "Dave-only command"), ret_rows),
                        "## Removal\n\n" + removal,
                        "## Residue (W19 class)\n\n### On this branch after the removal\n\n" + _residue_table(residue.get("source"))
                        + "\n\n### On the box after merge (live scan from the screen at preview time)\n\n" + _residue_table(residue.get("live")),
                        "## Diff\n\n" + _diff(rec), "## Checks\n\n" + _checks(rec), "## Reviewer attention\n\n" + _attention(rec), land]) + "\n"


def _retention_command(key: str, value: Any, workflow_id: str) -> str:
    if key == "receipts" and value == "archive":
        return f"`mv ~/agent-workforce/var/workflow-receipts/{workflow_id} ~/agent-workforce/var/workflow-receipts-retired/{workflow_id}`"
    if key in ("notion", "inbox") and value in ("archive", "delete"):
        return f"Mac-side: {value} the {key} artifacts (never from the box)"
    return "nothing — kept"


def _retire_land(units: list[str], subjects: dict[str, Any], desc: dict[str, Any], deploy: dict[str, Any] | None, rec: dict[str, Any]) -> str:
    scope = desc.get("scope", "system")
    sudo = "" if scope == "user" else "sudo "
    user = "--user " if scope == "user" else ""
    etc = "~/.config/systemd/user" if scope == "user" else "/etc/systemd/system"
    unit_files = " ".join(f"{etc}/{u}.timer {etc}/{u}.service" for u in units)
    steps = ["1. Merge → on the box `git -C ~/dev/agent-workforce pull --ff-only` → `bin/deploy` (ships `systemd/archive/`).",
             f"2. `{sudo}systemctl {user}disable --now " + " ".join(f"{u}.timer" for u in units) + "` — a no-op while the fleet is off; it is the retirement, not a fleet change.",
             f"3. `{sudo}rm {unit_files} && {sudo}systemctl {user}daemon-reload && {sudo}systemctl {user}reset-failed`"]
    env_override = subjects.get("env_override")
    if env_override:
        steps.append(f"4. `ls -l {env_override}` then `rm {env_override}` — deny-listed for agents; only your hand and your attestation clear it.")
    else:
        steps.append("4. No per-job override env to remove.")
    also = _also_deleted(deploy)
    steps.append("5. `bin/deploy --prune` **which also deletes:** " + (", ".join(also) if also else "nothing beyond this workflow's files"))
    steps.append(f"6. `bin/workflow_pr.py clear {rec['workflow_id']}" + (" --env-removed" if env_override else "") + " --pr <url>` → commit the registry line it writes.")
    steps.append("7. `bash bin/verify.sh` green.")
    return "## Land (Dave-only; this PR does none of it)\n\n" + "\n".join(steps)


def _also_deleted(deploy: dict[str, Any] | None) -> list[str]:
    if not deploy or not deploy.get("output"):
        return []
    lines = deploy["output"].splitlines()
    try:
        start = next(i for i, line in enumerate(lines) if line.startswith("also deleted by --prune"))
    except StopIteration:
        return []
    return [_tree_path(line) for line in lines[start + 1:] if line.strip() and line.strip() != "(nothing)"]


def _tree_path(line: str) -> str:
    """`  [systemd] delete deferred.service` → `systemd/deferred.service`."""
    line = line.strip()
    if not line.startswith("[") or "]" not in line:
        return line
    tree, rest = line[1:].split("]", 1)
    return f"{tree.strip()}/{rest.split()[-1]}" if rest.split() else line


def body(rec: dict[str, Any]) -> str:
    return _schedule_body(rec) if rec["kind"] == "schedule" else _retire_body(rec)
