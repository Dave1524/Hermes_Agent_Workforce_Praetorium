#!/usr/bin/env python3
"""Render the control broker's allowlist from the committed manifests, unit files and contracts.

The broker (bin/control_broker.py, root) trusts nothing it did not read from
/etc/control-room/allowlist.json, and that file is a pure function of this checkout: every
standing timer workflow whose timer and service unit both exist under systemd/, keyed by its
logical id, with `retry` taken from the contract's Identity `Retry` row; and, under `runtimes`
(T5.3g), every standing `kind = "service"` entry whose template unit file exists, keyed by the
instance name the screen already uses (buzz-agent@marcus). The bytes are deterministic (sorted
keys, no timestamp) so the drift check can compare them.

    render [--repo R]                              print the JSON
    check  [--repo R] [--installed PATH]           exit 1 with a diff when PATH differs or is missing
"""
from __future__ import annotations

import argparse
import difflib
import json
import pathlib
import re
import sys
import tomllib
from typing import Any

UNIT_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
RUNTIME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}@[a-z0-9][a-z0-9-]{0,63}$")
INSTALLED = "/etc/control-room/allowlist.json"
NOT_DECLARED = "contract declares no idempotent operation"


def _clean(cell: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", cell)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _identity_section(text: str) -> str:
    match = re.search(r"^## Identity\s*$\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def contract_retry_declaration(text: str) -> tuple[bool, str | None]:
    for line in _identity_section(text).splitlines():
        cells = [_clean(cell) for cell in line.strip().strip("|").split("|")] if line.startswith("|") else []
        if len(cells) >= 2 and cells[0].lower() == "retry":
            first = re.match(r"[*`_]*([A-Za-z]+)", cells[1])
            return bool(first and first.group(1).lower() == "idempotent"), cells[1] or None
    return False, None


def _manifest_entries(repo: pathlib.Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted((repo / "design" / "agents").glob("*.toml")):
        data = tomllib.loads(path.read_text(encoding="utf-8"))
        owner = str(data.get("name") or path.stem)
        for entry in data.get("workflows", []):
            if isinstance(entry, dict) and entry.get("unit"):
                rows.append({**entry, "owner": owner})
    return rows


def _units_present(repo: pathlib.Path, unit: str, scope: str) -> bool:
    base = repo / "systemd" / ("user" if scope == "user" else "")
    return (base / f"{unit}.timer").is_file() and (base / f"{unit}.service").is_file()


def _template_of(repo: pathlib.Path, unit: str, scope: str) -> str | None:
    base = repo / "systemd" / ("user" if scope == "user" else "")
    template = re.sub(r"@[^.]*", "@", f"{unit}.service")
    return template if (base / template).is_file() else None


def _runtime_exclusion_reason(repo: pathlib.Path, entry: dict[str, Any], scope: str) -> str | None:
    if entry.get("status") != "standing":
        return f"status = {entry.get('status')}"
    if not RUNTIME_RE.match(str(entry["unit"])):
        return "unit name outside the broker's grammar"
    if _template_of(repo, str(entry["unit"]), scope) is None:
        return "no service file in systemd/"
    return None


def _exclusion_reason(repo: pathlib.Path, entry: dict[str, Any], logical: str, scope: str) -> str | None:
    kind = str(entry.get("kind") or "timer")
    if kind != "timer":
        return f"kind = {kind}"
    if entry.get("status") != "standing":
        return f"status = {entry.get('status')}"
    if not UNIT_RE.match(str(entry["unit"])) or not UNIT_RE.match(logical):
        return "unit name outside the broker's grammar"
    if not _units_present(repo, str(entry["unit"]), scope):
        return "no timer/service file in systemd/"
    return None


def _retry(repo: pathlib.Path, contracts: set[str]) -> tuple[str | None, bool, str]:
    if not contracts:
        return None, False, "no contract declared"
    if len(contracts) > 1:
        return None, False, "two contracts declared: " + ", ".join(sorted(contracts))
    contract = next(iter(contracts))
    path = repo / contract
    if not path.is_file():
        return contract, False, f"contract unavailable: {contract}"
    declared, value = contract_retry_declaration(path.read_text(encoding="utf-8"))
    return contract, declared, value if declared else (value or NOT_DECLARED)


def render(repo: pathlib.Path | str) -> dict[str, Any]:
    repo = pathlib.Path(repo)
    workflows: dict[str, dict[str, Any]] = {}
    runtimes: dict[str, dict[str, Any]] = {}
    contracts: dict[str, set[str]] = {}
    excluded: list[dict[str, Any]] = []
    for entry in _manifest_entries(repo):
        unit, scope = str(entry["unit"]), str(entry.get("scope") or "system")
        logical = str(entry.get("logical_workflow") or unit)
        if entry.get("kind") == "service":
            reason = _runtime_exclusion_reason(repo, entry, scope)
            if reason:
                excluded.append({"unit": unit, "owner": entry["owner"], "reason": reason})
            else:
                runtimes[unit] = {"owner": entry["owner"], "unit": unit, "scope": scope,
                                  "template": _template_of(repo, unit, scope)}
            continue
        reason = _exclusion_reason(repo, entry, logical, scope)
        if reason:
            excluded.append({"unit": unit, "owner": entry["owner"], "reason": reason})
            continue
        workflow = workflows.setdefault(logical, {"owner": entry["owner"], "triggers": []})
        workflow["triggers"].append({"unit": unit, "scope": scope})
        if entry.get("contract"):
            contracts.setdefault(logical, set()).add(str(entry["contract"]))
    for logical, workflow in workflows.items():
        workflow["contract"], workflow["retry"], workflow["retry_reason"] = _retry(repo, contracts.get(logical, set()))
        workflow["triggers"].sort(key=lambda trigger: trigger["unit"])
    return {"schema": 1, "workflows": workflows, "runtimes": dict(sorted(runtimes.items())),
            "excluded": sorted(excluded, key=lambda row: row["unit"])}


def dumps(data: dict[str, Any]) -> str:
    return json.dumps(data, sort_keys=True, indent=2) + "\n"


def check(repo: pathlib.Path, installed: pathlib.Path) -> int:
    expected = dumps(render(repo))
    if not installed.is_file():
        print(f"allowlist missing: {installed}")
        return 1
    actual = installed.read_text(encoding="utf-8")
    if actual == expected:
        return 0
    sys.stdout.writelines(difflib.unified_diff(actual.splitlines(True), expected.splitlines(True),
                                               fromfile=str(installed), tofile="render"))
    return 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "check"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[1]))
        if name == "check":
            command.add_argument("--installed", default=INSTALLED)
    args = parser.parse_args(argv)
    if args.command == "render":
        sys.stdout.write(dumps(render(pathlib.Path(args.repo))))
        return 0
    return check(pathlib.Path(args.repo), pathlib.Path(args.installed))


if __name__ == "__main__":
    sys.exit(main())
