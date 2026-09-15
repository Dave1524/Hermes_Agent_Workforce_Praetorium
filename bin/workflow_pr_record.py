#!/usr/bin/env python3
"""Proposal records (T5.3b): one JSON file per request under <state>/proposals/, whatever the
outcome — previewed, submitted, refused or failed. The preview token IS the proposal id, so a
submit is checked against the record it names: same diff bytes, not expired, still previewed.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import secrets
from typing import Any

SCHEMA = 1
STAGES = ("previewed", "submitted", "refused", "failed")
KINDS = ("schedule", "retire")
PREVIEW_TTL_SECONDS = 1800
DIFF_INLINE_LIMIT = 200_000
PROPOSAL_ID_RE = re.compile(r"^\d{8}T\d{6}Z-(schedule|retire)-[a-z0-9][a-z0-9-]{0,63}-[0-9a-f]{6}$")

_TYPES: dict[str, tuple[type, ...]] = {
    "schema": (int,), "proposal_id": (str,), "kind": (str,), "workflow_id": (str,), "stage": (str,),
    "actor": (dict,), "reason": (str, type(None)), "requested_at": (str,), "completed_at": (str,),
    "base": (dict, type(None)), "branch": (str, type(None)), "files": (list,), "diff_sha256": (str, type(None)),
    "diff_stat": (str, type(None)), "description": (dict, type(None)), "checks": (list,),
    "residue": (dict, type(None)), "retention": (dict, type(None)), "pr": (dict, type(None)),
    "refusal": (dict, type(None)), "commands": (list,),
}


def stamp(now: dt.datetime) -> str:
    return now.astimezone(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_stamp(text: str) -> dt.datetime:
    return dt.datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=dt.timezone.utc)


def slug(workflow_id: str) -> str:
    return re.sub(r"[^a-z0-9-]", "-", workflow_id.lower())[:64].strip("-") or "unknown"


def proposal_id(now: dt.datetime, kind: str, workflow_id: str) -> str:
    return f"{now.astimezone(dt.timezone.utc):%Y%m%dT%H%M%SZ}-{kind}-{slug(workflow_id)}-{secrets.token_hex(3)}"


def new_record(kind: str, workflow_id: str, actor: dict[str, Any], reason: str | None, now: dt.datetime) -> dict[str, Any]:
    return {
        "schema": SCHEMA, "proposal_id": proposal_id(now, kind, workflow_id), "kind": kind,
        "workflow_id": workflow_id, "stage": "refused", "actor": actor, "reason": reason,
        "requested_at": stamp(now), "completed_at": stamp(now), "base": None, "branch": None, "files": [],
        "diff_sha256": None, "diff_stat": None, "diff": None, "description": None, "checks": [],
        "residue": None, "retention": None, "pr": None, "refusal": None, "commands": [],
    }


def validate_record(data: Any) -> list[str]:
    if not isinstance(data, dict):
        return ["record must be a JSON object"]
    problems = [f"{key} missing" for key in _TYPES if key not in data]
    problems += [f"{key} must be {'/'.join(t.__name__ for t in types)}" for key, types in _TYPES.items()
                 if key in data and not isinstance(data[key], types)]
    if data.get("schema") != SCHEMA:
        problems.append(f"schema must be {SCHEMA}")
    if data.get("stage") not in STAGES:
        problems.append(f"stage must be one of {', '.join(STAGES)}")
    if data.get("kind") not in KINDS:
        problems.append(f"kind must be one of {', '.join(KINDS)}")
    if "diff" not in data and "diff_path" not in data:
        problems.append("diff or diff_path required")
    for key in ("requested_at", "completed_at"):
        try:
            parse_stamp(str(data.get(key)))
        except ValueError:
            problems.append(f"{key} must be a UTC stamp YYYY-MM-DDTHH:MM:SSZ")
    if data.get("stage") == "refused" and not isinstance(data.get("refusal"), dict):
        problems.append("a refused record carries a refusal")
    if data.get("stage") == "submitted" and not isinstance(data.get("pr"), dict):
        problems.append("a submitted record carries a pr")
    return problems


def _dir(state: pathlib.Path) -> pathlib.Path:
    return pathlib.Path(state) / "proposals"


def write(state: pathlib.Path, rec: dict[str, Any]) -> pathlib.Path:
    problems = validate_record(rec)
    if problems:
        raise ValueError(f"record does not validate: {problems[0]}")
    directory = _dir(state)
    directory.mkdir(parents=True, exist_ok=True)
    stored = dict(rec)
    diff = stored.get("diff")
    if isinstance(diff, str) and len(diff) > DIFF_INLINE_LIMIT:
        diff_path = directory / f"{rec['proposal_id']}.diff"
        _atomic(diff_path, diff)
        stored["diff_path"] = str(diff_path)
        del stored["diff"]
    path = directory / f"{rec['proposal_id']}.json"
    _atomic(path, json.dumps(stored, indent=2, sort_keys=True) + "\n")
    return path


def _atomic(path: pathlib.Path, text: str) -> None:
    tmp = path.with_name(path.name + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.chmod(tmp, 0o644)
    os.replace(tmp, path)


def load(path: pathlib.Path) -> dict[str, Any]:
    data = json.loads(pathlib.Path(path).read_text(encoding="utf-8"))
    if "diff_path" in data and "diff" not in data:
        try:
            data["diff"] = pathlib.Path(data["diff_path"]).read_text(encoding="utf-8")
        except OSError:
            data["diff"] = None
    return data


def _all(state: pathlib.Path) -> list[dict[str, Any]]:
    records = []
    for path in sorted(_dir(state).glob("*.json")):
        try:
            data = load(path)
        except (OSError, ValueError):
            continue
        if not validate_record(data):
            records.append(data)
    return sorted(records, key=lambda r: (r["completed_at"], r["proposal_id"]), reverse=True)


def find(state: pathlib.Path, pid: str) -> dict[str, Any] | None:
    if not PROPOSAL_ID_RE.match(pid or ""):
        return None
    path = _dir(state) / f"{pid}.json"
    try:
        data = load(path)
    except (OSError, ValueError):
        return None
    return data if not validate_record(data) else None


def newest(state: pathlib.Path, workflow_id: str, kind: str) -> dict[str, Any] | None:
    matches = list_records(state, workflow_id, kind, with_diff=True)
    return matches[0] if matches else None


def list_records(state: pathlib.Path, workflow_id: str, kind: str, with_diff: bool = False) -> list[dict[str, Any]]:
    rows = [r for r in _all(state) if r["workflow_id"] == workflow_id and r["kind"] == kind]
    if with_diff:
        return rows
    return [{k: v for k, v in r.items() if k not in ("diff", "diff_path")} for r in rows]


def token_valid(rec: dict[str, Any], now: dt.datetime) -> tuple[bool, str | None]:
    if rec.get("stage") != "previewed":
        return False, f"record is {rec.get('stage')}, not previewed"
    issued = parse_stamp(rec["completed_at"])
    if now.astimezone(dt.timezone.utc) - issued > dt.timedelta(seconds=PREVIEW_TTL_SECONDS):
        return False, "preview expired"
    return True, None
