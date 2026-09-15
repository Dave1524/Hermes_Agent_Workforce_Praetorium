#!/usr/bin/env python3
"""The retirement plan (T5.3b): the subject set of a workflow, the edits that remove it across every
join, the registry record, and the residue scan that is the plan's own post-condition.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import re
import shlex
import tomllib
from typing import Any

import workflow_retire_residue as residue
from workflow_pr_record import Plan, Refused, slug

RETIRABLE = ("standing", "dormant", "spent")
RETENTION_VOCAB = {"receipts": ("keep", "archive"), "notion": ("keep", "archive", "delete"), "inbox": ("keep", "archive", "delete")}
RETENTION_KEYS = ("receipts", "notion", "inbox", "note")
IDLE_STATUSES = {"spent", "planned"}
MIN_REASON = 10
COUNT_LITERAL_RE = re.compile(r"^([A-Z][A-Z_]*)\s*=\s*(\d+)\s*(#.*)?$")
VIEWS_SUITE = "tests/test_control_room_views.py"
REGISTRY = residue.REGISTRY
REGISTRY_HEADER = ("# Retired workflows — one [[retired]] per retired logical workflow, written by the retire plan\n"
                   "# (bin/workflow_pr_retire.py), read by tests/test_workflow_retirements.sh and\n"
                   "# bin/workflow_retire_residue.py --all. The subject set is copied here because the manifest\n"
                   "# entry is gone by the time anything checks the residue.\n")


# --- validation -----------------------------------------------------------------------------------

def validate_request(reason: Any, proposed: Any) -> dict[str, str]:
    if not isinstance(reason, str) or len(reason.strip()) < MIN_REASON:
        raise Refused("bad_request", f"reason must be at least {MIN_REASON} characters for a retirement")
    return validate_retention(proposed if isinstance(proposed, dict) else {})


def validate_retention(proposed: dict[str, Any]) -> dict[str, str]:
    retention = proposed.get("artifact_retention")
    if not isinstance(retention, dict):
        raise Refused("retention_required", "artifact_retention is required: receipts, notion, inbox, note — no default")
    for key in RETENTION_KEYS:
        value = retention.get(key)
        if not isinstance(value, str) or not value.strip():
            raise Refused("retention_required", f"artifact_retention.{key} is required")
    for key, vocab in RETENTION_VOCAB.items():
        if retention[key] not in vocab:
            raise Refused("bad_request", f"artifact_retention.{key} must be one of {', '.join(vocab)}; got {retention[key]!r}")
    unknown = sorted(set(retention) - set(RETENTION_KEYS))
    if unknown:
        raise Refused("bad_request", f"artifact_retention has unknown keys: {', '.join(unknown)}")
    return {key: retention[key] for key in RETENTION_KEYS}


# --- subject set ----------------------------------------------------------------------------------

def runner_file(root: pathlib.Path, runner: Any) -> str | None:
    if not isinstance(runner, str):
        return None
    for tok in re.split(r"(?:->)|[\s;|&]", runner):
        tok = tok.strip().strip("\"'")
        if tok and (root / tok).is_file():
            return tok
    return None


def _exec_targets(root: pathlib.Path, service: pathlib.Path | None) -> list[str]:
    if service is None:
        return []
    out = []
    for line in service.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.startswith("ExecStart="):
            continue
        for tok in shlex.split(line.split("=", 1)[1], posix=True):
            marker = tok.find("/bin/")
            candidate = "bin/" + tok[marker + 5:] if marker >= 0 else tok
            if (root / candidate).is_file() and candidate not in out:
                out.append(candidate)
    return out


def _service_env(service: pathlib.Path | None, key: str, unit: str) -> str | None:
    if service is None:
        return None
    for line in service.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(f"Environment={key}="):
            return line.split("=", 2)[2].strip().strip('"').replace("%n", f"{unit}.service")
    return None


def _unit_path(root: pathlib.Path, unit: str, scope: str, suffix: str) -> pathlib.Path | None:
    candidates = [root / "systemd" / "user" / f"{unit}.{suffix}"] if scope == "user" else []
    candidates.append(root / "systemd" / f"{unit}.{suffix}")
    return next((c for c in candidates if c.is_file()), None)


def _live_services(root: pathlib.Path, own_units: list[str]) -> list[pathlib.Path]:
    services = sorted(root.glob("systemd/**/*.service"))
    return [s for s in services if s.is_file() and "archive" not in s.relative_to(root).parts and s.stem not in own_units]


def _mentions(path: pathlib.Path, name_re: re.Pattern[str]) -> bool:
    lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    return any(not line.lstrip().startswith("#") and name_re.search(line) for line in lines)


def _runner_units(root: pathlib.Path, entries: list[dict[str, Any]], services: list[pathlib.Path]) -> dict[str, list[str]]:
    """bin/ script → the live units that run it, by manifest `runner` or by ExecStart."""
    out: dict[str, list[str]] = {}
    for entry in entries:
        path = runner_file(root, entry.get("runner"))
        if path:
            out.setdefault(path, []).append(f"{entry['unit']}.service")
    for service in services:
        for target in _exec_targets(root, service):
            out.setdefault(target, []).append(service.name)
    return out


def _live_references(root: pathlib.Path, runner: str, own_units: list[str], own_runners: list[str],
                     runner_units: dict[str, list[str]]) -> list[str]:
    """Units that still exec `runner` — directly, or through a bin/ script they run."""
    name_re = re.compile(r"(?<![A-Za-z0-9_.-])" + re.escape(pathlib.PurePosixPath(runner).name) + r"(?![A-Za-z0-9_])")
    users = [s.name for s in _live_services(root, own_units) if _mentions(s, name_re)]
    for path in sorted(root.glob("bin/*")):
        relative = path.relative_to(root).as_posix()
        if not path.is_file() or relative in own_runners or not _mentions(path, name_re):
            continue
        via = [u for u in runner_units.get(relative, []) if u.removesuffix(".service") not in own_units] or [relative]
        users += [u for u in via if u not in users]
    return users


def subject_set(root: pathlib.Path, item: dict[str, Any]) -> dict[str, Any]:
    root = pathlib.Path(root)
    workflow_id = item["id"]
    entries = residue._entries(root)
    mine = [e for _, e in entries if residue._logical(e) == workflow_id]
    others = [e for _, e in entries if residue._logical(e) != workflow_id]
    units = []
    for trigger in item.get("triggers", []):
        unit, scope = trigger["unit"], trigger.get("scope", "system")
        service = _unit_path(root, unit, scope, "service")
        timer = _unit_path(root, unit, scope, "timer")
        units.append({"name": unit, "scope": scope, "kind": trigger.get("kind", "timer"),
                      "timer_path": timer.relative_to(root).as_posix() if timer else None,
                      "service_path": service.relative_to(root).as_posix() if service else None,
                      "env_override": _service_env(service, "AGENT_JOB_OVERRIDES", unit),
                      "run_marker": _service_env(service, "DELIVERY_RUN_MARKER", unit)})
    unit_names = [u["name"] for u in units]
    runner_paths = []
    for entry in mine:
        path = runner_file(root, entry.get("runner"))
        if path and path not in runner_paths:
            runner_paths.append(path)
    for unit in units:
        for target in _exec_targets(root, root / unit["service_path"] if unit["service_path"] else None):
            if target not in runner_paths:
                runner_paths.append(target)
    other_runners = {runner_file(root, e.get("runner")) for e in others}
    runner_units = _runner_units(root, others, _live_services(root, unit_names))
    runners = []
    for path in runner_paths:
        users = _live_references(root, path, unit_names, runner_paths, runner_units)
        named_elsewhere = path in other_runners
        runners.append({"path": path, "owned": not users and not named_elsewhere, "used_by": users})
    profiles = []
    for entry in mine:
        profile = entry.get("profile")
        if entry.get("profile_in_repo", True) is not False and isinstance(profile, str) and (root / profile).is_file() and profile not in profiles:
            profiles.append(profile)
    env_override = next((u["env_override"] for u in units if u["env_override"]), None)
    if env_override:
        example = f"profiles/{pathlib.PurePosixPath(env_override).name}.example"
        if (root / example).is_file() and example not in profiles:
            profiles.append(example)
    other_contracts = {str(e.get("contract")) for e in others if e.get("contract")}
    contract = next((str(e["contract"]) for e in mine if e.get("contract") and not e.get("contract_exempt")), "")
    contract = contract if contract and contract not in other_contracts and (root / contract).is_file() else ""
    suites = []
    for entry in mine:
        for suite in entry.get("suite", []):
            for candidate in (suite, suite[:-3] + ".py" if suite.endswith(".sh") else None):
                if candidate and (root / candidate).is_file() and candidate not in suites:
                    suites.append(candidate)
    return {"logical_id": workflow_id, "owner": item.get("owner") or (mine[0].get("owner") if mine else ""),
            "units": units, "manifest_paths": list(item.get("manifestPaths", [])), "runners": runners, "profiles": profiles,
            "contract": contract, "suites": suites, "env_override": env_override,
            "run_markers": [u["run_marker"] for u in units if u["run_marker"]],
            "slugs": sorted({s for u in [workflow_id, *unit_names] for s in (u, u.replace("-", "_"))})}


def residue_subjects(subjects: dict[str, Any], env_removed_attested: bool = False) -> dict[str, Any]:
    scope = subjects["units"][0]["scope"] if subjects["units"] else "system"
    return {"id": subjects["logical_id"], "units": [u["name"] for u in subjects["units"]], "scope": scope, "owner": subjects["owner"],
            "runners": [r["path"] for r in subjects["runners"] if r["owned"]], "profiles": list(subjects["profiles"]),
            "contract": subjects["contract"], "suites": list(subjects["suites"]), "env_override": subjects["env_override"],
            "run_markers": list(subjects["run_markers"]), "slugs": list(subjects["slugs"]), "env_removed_attested": env_removed_attested}


# --- edits ----------------------------------------------------------------------------------------

def remove_manifest_block(text: str, unit: str, comment: str) -> str:
    lines = text.splitlines(keepends=True)
    starts = [i for i, line in enumerate(lines) if line.strip() == "[[workflows]]"]
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else _next_header(lines, start + 1)
        block = "".join(lines[start:end])
        if re.search(rf'^\s*unit\s*=\s*"{re.escape(unit)}"\s*$', block, re.MULTILINE):
            trailing = "\n" if block.endswith("\n\n") else ""
            return "".join(lines[:start]) + comment.rstrip("\n") + "\n" + trailing + "".join(lines[end:])
    raise Refused("unknown_workflow", f"no [[workflows]] block for unit {unit}")


def _next_header(lines: list[str], start: int) -> int:
    for i in range(start, len(lines)):
        if lines[i].startswith("["):
            return i
    return len(lines)


def flip_empty_surface(text: str, surface: str, date: str) -> str:
    pattern = re.compile(rf"^(\[surfaces\.{re.escape(surface)}\]\s*\n)((?:(?!\[).*\n?)*)", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return text
    body = match.group(2)
    if re.search(r"^present\s*=\s*false", body, re.MULTILINE):
        return text
    body = re.sub(r"^(present\s*=\s*)true(.*)$", rf'\g<1>false\g<2>\n' + _aligned(body, "retired", f'"{date}"'), body, count=1, flags=re.MULTILINE)
    return text[:match.start(2)] + body + text[match.end(2):]


def _aligned(body: str, key: str, value: str) -> str:
    match = re.search(r"^(present)(\s*)=", body, re.MULTILINE)
    width = len(match.group(1) + match.group(2)) if match else len(key)
    return f"{key.ljust(width)}= {value}"


def prune_governed_by(text: str, surface: str, runners: list[str]) -> str:
    pattern = re.compile(rf"^(\[surfaces\.{re.escape(surface)}\]\s*\n)((?:(?!\[).*\n?)*)", re.MULTILINE)
    match = pattern.search(text)
    if not match:
        return text
    body = match.group(2)
    line = re.search(r'^(governed_by\s*=\s*")([^"]*)(".*)$', body, re.MULTILINE)
    if not line:
        return text
    kept = [tok.strip() for tok in line.group(2).split(",") if tok.strip() and tok.strip() not in runners]
    body = body[:line.start()] + line.group(1) + ", ".join(kept) + line.group(3) + body[line.end():]
    return text[:match.start(2)] + body + text[match.end(2):]


def drop_tsv_rows(text: str, first_columns: set[str]) -> str:
    return "".join(line for line in text.splitlines(keepends=True) if line.split("\t")[0].strip() not in first_columns)


def drop_lines_mentioning(text: str, tokens: list[str]) -> str:
    pattern = re.compile("|".join(rf"(?<![A-Za-z0-9_])(?:{re.escape(t)})(?![A-Za-z0-9_])" for t in tokens)) if tokens else None
    return "".join(line for line in text.splitlines(keepends=True) if pattern is None or not pattern.search(line))


def append_exclusions(text: str, entries: list[tuple[str, str]], date: str, pid: str, workflow_id: str) -> str:
    blocks = []
    for tree, name in entries:
        blocks.append(f'[[runtime_only]]\npath  = "{name}"\ntree  = "{tree}"\nsince = "{date}"\n'
                      f'why   = "{workflow_id} retired via Control Room proposal {pid}; the deployed copy waits for bin/deploy --prune."\n')
    return text.rstrip("\n") + "\n\n" + "\n".join(blocks)


def archive_unit(worktree: pathlib.Path, relative: str, scope: str) -> str:
    target = f"systemd/archive/{'user/' if scope == 'user' else ''}{pathlib.PurePosixPath(relative).name}"
    (worktree / target).parent.mkdir(parents=True, exist_ok=True)
    (worktree / relative).rename(worktree / target)
    return target


def archive_contract(worktree: pathlib.Path, relative: str, date: str, pid: str) -> str:
    target = f"design/archive/contracts/{pathlib.PurePosixPath(relative).name}"
    source = worktree / relative
    (worktree / target).parent.mkdir(parents=True, exist_ok=True)
    banner = f"> RETIRED {date} — Control Room proposal {pid}; the workflow no longer exists. Kept as history for T5.4's evidence.\n\n"
    (worktree / target).write_text(banner + source.read_text(encoding="utf-8"), encoding="utf-8")
    source.unlink()
    return target


def count_literals(root: pathlib.Path) -> dict[str, int]:
    entries = [e for _, e in residue._entries(root)]
    scheduled = [e for e in entries if e.get("surface") == "scheduled"]
    return {"standing_all": sum(1 for e in entries if e.get("status") == "standing"),
            "standing_scheduled": sum(1 for e in scheduled if e.get("status") == "standing"),
            "logical_all": len({residue._logical(e) for e in entries}),
            "logical_scheduled": len({residue._logical(e) for e in scheduled})}


def decrement_count_literals(text: str, before: dict[str, int], removed_standing: int, removed_logical: int) -> tuple[str, list[str]]:
    standing = {before["standing_all"], before["standing_scheduled"]}
    logical = {before["logical_all"], before["logical_scheduled"]}
    out, changed = [], []
    for line in text.splitlines(keepends=True):
        match = COUNT_LITERAL_RE.match(line.rstrip("\n"))
        if match:
            value = int(match.group(2))
            delta = removed_standing if value in standing else removed_logical if value in logical else 0
            if delta:
                line = line.replace(match.group(2), str(value - delta), 1)
                changed.append(f"{match.group(1)} {value} → {value - delta}")
        out.append(line)
    return "".join(out), changed


def append_retired_record(text: str, entry: dict[str, Any]) -> str:
    def toml_value(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, list):
            return "[" + ", ".join(toml_value(v) for v in value) + "]"
        if isinstance(value, dict):
            return "{ " + ", ".join(f"{k} = {toml_value(v)}" for k, v in value.items()) + " }"
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'
    lines = ["[[retired]]"] + [f"{key} = {toml_value(value)}" for key, value in entry.items()]
    return text.rstrip("\n") + "\n\n" + "\n".join(lines) + "\n"


# --- the plan -------------------------------------------------------------------------------------

def plan_retire(worktree: pathlib.Path, item: dict[str, Any], proposed: dict[str, Any], now: dt.datetime, pid: str,
                live: dict[str, Any] | None = None) -> Plan:
    worktree = pathlib.Path(worktree)
    retention = validate_request(proposed.get("reason"), proposed)
    if item.get("lifecycle") not in RETIRABLE:
        raise Refused("not_standing", f"{item['id']} is {item.get('lifecycle')}; only {', '.join(RETIRABLE)} entries retire")
    triggers = [t for t in item.get("triggers", []) if t.get("unit")]
    if not triggers or any(t.get("kind") != "timer" for t in triggers):
        raise Refused("not_a_timer", f"{item['id']} has a service entry; retirement covers timer workflows only")
    date = f"{now:%Y-%m-%d}"
    branch = f"control-room/retire-{slug(item['id'])}-{pid.split('-', 1)[0]}"
    subjects = subject_set(worktree, item)
    before = count_literals(worktree)
    edits, removal, deleted, archived = [], [], [], {}
    unit_names = [u["name"] for u in subjects["units"]]
    owned_runners = [r["path"] for r in subjects["runners"] if r["owned"]]
    reason = str(proposed["reason"]).strip()
    for relative in subjects["manifest_paths"]:
        _edit_manifest(worktree, relative, subjects, unit_names, owned_runners, date, pid, branch, reason, retention, removal)
        edits.append(relative)
    _edit_declarations(worktree, unit_names, subjects, edits, removal)
    for unit in subjects["units"]:
        for key in ("timer_path", "service_path"):
            if unit[key]:
                target = archive_unit(worktree, unit[key], unit["scope"])
                archived[unit[key]] = target
                edits += [unit[key], target]
                removal.append({"path": unit[key], "change": f"renamed → {target}", "join": "systemd tree / deploy drift"})
    shared_notes = []
    for runner in subjects["runners"]:
        if runner["owned"]:
            (worktree / runner["path"]).unlink()
            edits.append(runner["path"])
            removal.append({"path": runner["path"], "change": "deleted", "join": "manifest runner / governed_by"})
        else:
            shared_notes.append(f"{runner['path']}: shared, kept — still exec'd by {', '.join(runner['used_by']) or 'another manifest entry'}")
    for profile in subjects["profiles"]:
        (worktree / profile).unlink()
        edits.append(profile)
        removal.append({"path": profile, "change": "deleted", "join": "manifest profile / env example"})
    contract_target = ""
    if subjects["contract"]:
        contract_target = archive_contract(worktree, subjects["contract"], date, pid)
        edits += [subjects["contract"], contract_target]
        removal.append({"path": subjects["contract"], "change": f"renamed → {contract_target} (+ RETIRED banner)", "join": "manifest contract"})
    for suite in subjects["suites"]:
        (worktree / suite).unlink()
        edits.append(suite)
        deleted.append(suite)
        removal.append({"path": suite, "change": "deleted", "join": "manifest suite / fleet-suites"})
    exclusions = worktree / "design/deploy-exclusions.toml"
    exclusion_entries = [("profiles", pathlib.PurePosixPath(p).name) for p in subjects["profiles"] if p.startswith("profiles/")]
    exclusion_entries += [("systemd", pathlib.PurePosixPath(p).name) for p in archived if p.startswith("systemd/") and not p.startswith("systemd/user/")]
    if exclusion_entries and exclusions.is_file():
        exclusions.write_text(append_exclusions(exclusions.read_text(encoding="utf-8"), exclusion_entries, date, pid, item["id"]), encoding="utf-8")
        edits.append("design/deploy-exclusions.toml")
    decremented = _decrement(worktree, before, subjects, item, edits)
    entry = _registry_entry(subjects, item, date, reason, pid, branch, retention, contract_target)
    registry = worktree / REGISTRY
    registry.parent.mkdir(parents=True, exist_ok=True)
    registry.write_text(append_retired_record(registry.read_text(encoding="utf-8") if registry.is_file() else REGISTRY_HEADER, entry), encoding="utf-8")
    edits.append(REGISTRY)
    flat = residue_subjects(subjects)
    source_report = residue.scan_source(worktree, flat)
    live_report = _live_report(flat, live or {})
    description = _description(item, subjects, unit_names, retention, removal, shared_notes, decremented, source_report, live_report, reason)
    attention = list(shared_notes)
    if decremented:
        attention.append("count literals decremented in " + VIEWS_SUITE + ": " + "; ".join(decremented))
    attention += [f"residue on this branch: {i['class']} {i['path']}" for i in source_report["items"] if i["blocks"]]
    summary = f"retire {item['id']}: {', '.join(unit_names)} archived; {len(removal)} paths change"
    subject_paths = residue.subject_paths(worktree, flat) + [u[k] for u in subjects["units"] for k in ("timer_path", "service_path") if u[k]] + list(subjects["profiles"]) + owned_runners
    return Plan("retire", item["id"], unit_names, sorted(set(edits)), description, summary, attention,
                {"subjects": flat, "subject_paths": sorted(set(subject_paths)), "retention": retention, "deleted": deleted,
                 "slugs": subjects["slugs"], "residue": {"source": source_report, "live": live_report},
                 "pinned_extra": [VIEWS_SUITE[:-3] + ".sh"] if decremented else [],
                 "acknowledge_pinned_tests": bool(proposed.get("acknowledge_pinned_tests", False)), "registry_entry": entry})


def _edit_manifest(worktree: pathlib.Path, relative: str, subjects: dict[str, Any], unit_names: list[str], owned_runners: list[str],
                   date: str, pid: str, branch: str, reason: str, retention: dict[str, str], removal: list[dict[str, str]]) -> None:
    path = worktree / relative
    text = path.read_text(encoding="utf-8")
    before = tomllib.loads(text)
    surfaces_touched = set()
    removed = []
    for entry in before.get("workflows", []):
        if entry.get("unit") in unit_names:
            comment = (f"# {entry['unit']} retired {date} via Control Room proposal {pid} (branch {branch}): {reason}. "
                       f"Artifacts: receipts={retention['receipts']} notion={retention['notion']} inbox={retention['inbox']}. Record: {REGISTRY}.")
            text = remove_manifest_block(text, entry["unit"], comment)
            surfaces_touched.add(entry.get("surface"))
            removed.append(entry)
    after = tomllib.loads(text)
    remaining = after.get("workflows", [])
    expected = [e for e in before.get("workflows", []) if e.get("unit") not in unit_names]
    if remaining != expected:
        raise Refused("plan_failed", f"{relative}: removing {', '.join(unit_names)} changed another entry")
    for surface in surfaces_touched:
        live = [e for e in remaining if e.get("surface") == surface and e.get("status") not in IDLE_STATUSES]
        if not live:
            text = flip_empty_surface(text, surface, date)
        text = prune_governed_by(text, surface, owned_runners)
    path.write_text(text, encoding="utf-8")
    for entry in removed:
        removal.append({"path": relative, "change": f"[[workflows]] {entry['unit']} → dated comment", "join": "manifest / fleet-units / surfaces"})


def _rewrite(worktree: pathlib.Path, relative: str, transform, edits: list[str], removal: list[dict[str, str]], change: str, join: str) -> None:
    path = worktree / relative
    if not path.is_file():
        return
    before = path.read_text(encoding="utf-8")
    after = transform(before)
    if after == before:
        return
    path.write_text(after, encoding="utf-8")
    edits.append(relative)
    removal.append({"path": relative, "change": change, "join": join})


def _edit_declarations(worktree: pathlib.Path, unit_names: list[str], subjects: dict[str, Any], edits: list[str], removal: list[dict[str, str]]) -> None:
    services = {f"{u}.service" for u in unit_names}
    suite_names = [pathlib.PurePosixPath(s).name for s in subjects["suites"]]
    _rewrite(worktree, "config/fleet-units.tsv", lambda t: drop_tsv_rows(t, set(unit_names)), edits, removal,
             f"rows {', '.join(unit_names)} dropped", "test_fleet_ownership.sh")
    _rewrite(worktree, "bin/buzz_producers.tsv", lambda t: drop_tsv_rows(t, services), edits, removal,
             f"rows {', '.join(sorted(services))} dropped", "test_buzz_unit_wiring.sh")
    _rewrite(worktree, "tests/ci-expected-skips.txt", lambda t: drop_lines_mentioning(t, suite_names), edits, removal,
             f"lines naming {', '.join(suite_names)} dropped", "CI skip ledger")


def _decrement(worktree: pathlib.Path, before: dict[str, int], subjects: dict[str, Any], item: dict[str, Any], edits: list[str]) -> list[str]:
    views = worktree / VIEWS_SUITE
    if not views.is_file():
        return []
    removed_standing = len(subjects["units"]) if item.get("lifecycle") == "standing" else 0
    text, changed = decrement_count_literals(views.read_text(encoding="utf-8"), before, removed_standing, 1)
    if changed:
        views.write_text(text, encoding="utf-8")
        edits.append(VIEWS_SUITE)
    return changed


def _registry_entry(subjects: dict[str, Any], item: dict[str, Any], date: str, reason: str, pid: str, branch: str,
                    retention: dict[str, str], contract_target: str) -> dict[str, Any]:
    return {"id": item["id"], "units": [u["name"] for u in subjects["units"]], "owner": subjects["owner"] or "",
            "scope": subjects["units"][0]["scope"] if subjects["units"] else "system", "retired_on": date, "reason": reason,
            "proposal": pid, "branch": branch, "pr": "", "runners": [r["path"] for r in subjects["runners"] if r["owned"]],
            "profiles": list(subjects["profiles"]), "contract": contract_target, "suites": list(subjects["suites"]),
            "env_override": subjects["env_override"] or "", "run_markers": list(subjects["run_markers"]),
            "artifact_retention": dict(retention), "residue_cleared_on": "", "env_removed_attested": False}


def _live_report(flat: dict[str, Any], live: dict[str, Any]) -> dict[str, Any] | None:
    if not live.get("runtime_root"):
        return None
    return residue.scan_live(flat, pathlib.Path(live["runtime_root"]), pathlib.Path(live.get("etc_dir", "/etc/systemd/system")),
                             pathlib.Path(live.get("user_tree", "~/.config/systemd/user")).expanduser(), residue.systemctl_runner)


def _description(item: dict[str, Any], subjects: dict[str, Any], unit_names: list[str], retention: dict[str, str], removal: list[dict[str, str]],
                 shared_notes: list[str], decremented: list[str], source_report: dict[str, Any], live_report: dict[str, Any] | None, reason: str) -> dict[str, Any]:
    return {"units": unit_names, "scope": subjects["units"][0]["scope"] if subjects["units"] else "system", "reason": reason,
            "evidence": {"lastValidArtifact": item.get("lastValidArtifact"), "validArtifactRate": item.get("validArtifactRate"),
                         "benefit": (item.get("benefit") or {}).get("decision") if isinstance(item.get("benefit"), dict) else item.get("benefit")},
            "retention": retention, "removal": removal, "shared_runners": shared_notes, "count_literals": decremented,
            "subjects": {"env_override": subjects["env_override"], "run_markers": subjects["run_markers"], "runners": subjects["runners"],
                         "profiles": subjects["profiles"], "contract": subjects["contract"], "suites": subjects["suites"]},
            "residue_verdict": {"source": source_report["verdict"], "live": live_report["verdict"] if live_report else "not scanned"},
            "reviewer_attention": []}


# --- clear (Dave's hand, at land) ----------------------------------------------------------------

def clear_command(workflow_id: str, env_removed: bool, pr: str | None, live: dict[str, Any]) -> int:
    """Dave's hand at land: refuse unless the live scan is clear, else write the registry line in the
    checkout `live["checkout"]` names — the one file this brief edits there. The commit is his."""
    if not live.get("checkout"):
        print("clear needs the checkout path (live.checkout) — bin/workflow_pr.py sets it", flush=True)
        return 2
    checkout = pathlib.Path(live["checkout"]).expanduser()
    registry = checkout / REGISTRY
    entries = residue.registry_entries(checkout)
    entry = next((e for e in entries if e.get("id") == workflow_id), None)
    if entry is None:
        print(f"{workflow_id}: no [[retired]] entry in {registry}", flush=True)
        return 2
    subjects = residue.subjects_from_entry(entry)
    subjects["env_removed_attested"] = bool(env_removed) or bool(entry.get("env_removed_attested"))
    report = residue.scan_live(subjects, pathlib.Path(live.get("runtime_root") or "~/agent-workforce").expanduser(),
                               pathlib.Path(live.get("etc_dir") or "/etc/systemd/system"),
                               pathlib.Path(live.get("user_tree") or "~/.config/systemd/user").expanduser(), residue.systemctl_runner)
    if report["verdict"] != "clear":
        print(residue.render_w19_table(report), flush=True)
        return 1
    today = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")
    text = registry.read_text(encoding="utf-8")
    text = _set_entry_field(text, workflow_id, "residue_cleared_on", f'"{today}"')
    text = _set_entry_field(text, workflow_id, "env_removed_attested", "true" if subjects["env_removed_attested"] else "false")
    if pr:
        text = _set_entry_field(text, workflow_id, "pr", '"' + pr.replace('"', "") + '"')
    registry.write_text(text, encoding="utf-8")
    print(f"{workflow_id}: residue clear on {today}; wrote {registry}", flush=True)
    print(f'now: git -C {checkout} add {REGISTRY} && git -C {checkout} commit -m "retire({workflow_id}): residue cleared"', flush=True)
    return 0


def _set_entry_field(text: str, workflow_id: str, key: str, value: str) -> str:
    blocks = re.split(r"(?m)^(?=\[\[retired\]\])", text)
    for index, block in enumerate(blocks):
        if re.search(rf'^id\s*=\s*"{re.escape(workflow_id)}"\s*$', block, re.MULTILINE):
            if re.search(rf"^{key}\s*=", block, re.MULTILINE):
                blocks[index] = re.sub(rf"^({key}\s*=\s*).*$", lambda m: m.group(1) + value, block, count=1, flags=re.MULTILINE)
            else:
                blocks[index] = block.rstrip("\n") + f"\n{key} = {value}\n"
    return "".join(blocks)
