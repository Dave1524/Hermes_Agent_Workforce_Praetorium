#!/usr/bin/env python3
"""`requires` — the one manifest field for a workflow's hard runtime dependencies (T5.3f).

    workflow_requires.py check <unit> [--repo-root DIR]
    workflow_requires.py audit [--repo-root DIR]

`requires = ["<unit>", …]` on a `[[workflows]]` entry in design/agents/*.toml. A bare name is a
manifest unit and takes its scope from that entry; a unit outside the manifests is written
`user/<unit>` or `system/<unit>` and must be a repo unit file under systemd/ or systemd/user/ —
every unit this box depends on has a source here. Every requirement resolves statically, so
the audit runs on a hosted runner with no bus.

`check` asks systemd for each requirement's ActiveState and exits 1 on the first that is
known to be down, printing `requires <unit>: <state>`. A bus that answers nothing is
`unknown`, and unknown is not a refusal: the run proceeds and the Control Room's row reads
`satisfied: null` for the same reason. The Control Room imports the resolver; the executor
pre-flight (bin/agent_propose.sh) calls the CLI.
"""
from __future__ import annotations

import argparse
import dataclasses
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import Any, Callable

SCOPES = ("system", "user")
ACTIVE_STATES = {"active", "activating", "reloading"}
UNIT_DIRS = {"system": "systemd", "user": "systemd/user"}
HANDOFF_RUNNER = "run_content_via_buzz.sh"
DEPENDENCY_LINE = re.compile(r"^\s*(Wants|Requires|BindsTo)\s*=\s*(.*)$")
HARD_KEYS = {"Requires", "BindsTo"}

Show = Callable[[str, str], tuple[dict[str, str], str | None]]


@dataclasses.dataclass(frozen=True)
class Requirement:
    unit: str
    scope: str
    workflow: str | None

    @property
    def service_name(self) -> str:
        return self.unit if self.unit.endswith((".service", ".timer", ".socket")) else f"{self.unit}.service"

    @property
    def key(self) -> str:
        return f"{self.scope}/{self.unit}"


def repo_root_default() -> pathlib.Path:
    """bin/deploy copies this script into ~/agent-workforce, where design/ is never shipped;
    the adjacent checkout wins, the source checkout is the fallback, the env the override."""
    script_root = pathlib.Path(__file__).resolve().parents[1]
    fallback = script_root if (script_root / "design" / "agents").is_dir() else pathlib.Path.home() / "dev" / "agent-workforce"
    return pathlib.Path(os.environ.get("CONTROL_ROOM_REPO_ROOT", fallback)).resolve()


def load_entries(repo_root: pathlib.Path) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for path in sorted((repo_root / "design" / "agents").glob("*.toml")):
        data = tomllib.loads(path.read_text())
        owner = str(data.get("name") or path.stem)
        for workflow in data.get("workflows", []):
            if isinstance(workflow, dict) and workflow.get("unit"):
                entries.append({**workflow, "owner": owner, "manifest": path.name})
    return entries


def _unit_file(repo_root: pathlib.Path, scope: str, unit: str) -> pathlib.Path | None:
    name = unit if unit.endswith((".service", ".timer", ".socket")) else f"{unit}.service"
    template = re.sub(r"@[^.]*", "@", name)
    for candidate in (name, template):
        path = repo_root / UNIT_DIRS[scope] / candidate
        if path.is_file():
            return path
    return None


def resolve(raw: Any, entries: list[dict[str, Any]], repo_root: pathlib.Path) -> Requirement:
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"requires entry {raw!r} is not a unit name")
    raw = raw.strip()
    by_unit = {str(e["unit"]): e for e in entries}
    if "/" not in raw:
        entry = by_unit.get(raw)
        if entry is None:
            raise ValueError(f"requires {raw!r}: a bare name must be a manifest unit; write system/{raw} or user/{raw} for a unit outside the manifests")
        return Requirement(raw, str(entry.get("scope") or "system"), str(entry.get("logical_workflow") or entry["unit"]))
    scope, _, unit = raw.partition("/")
    if scope not in SCOPES or not unit:
        raise ValueError(f"requires {raw!r}: the scope prefix must be system/ or user/")
    if _unit_file(repo_root, scope, unit) is None:
        raise ValueError(f"requires {raw!r}: no repo unit file under {UNIT_DIRS[scope]}/")
    entry = by_unit.get(unit)
    workflow = str(entry.get("logical_workflow") or entry["unit"]) if entry else None
    return Requirement(unit, scope, workflow)


def requirements_for(entry: dict[str, Any], entries: list[dict[str, Any]], repo_root: pathlib.Path) -> list[Requirement]:
    declared = entry.get("requires") or []
    if not isinstance(declared, list):
        raise ValueError(f"{entry['unit']}: requires must be a list of unit names")
    return [resolve(raw, entries, repo_root) for raw in declared]


def requirements_of_unit(unit: str, repo_root: pathlib.Path) -> list[Requirement]:
    entries = load_entries(repo_root)
    entry = next((e for e in entries if str(e["unit"]) == unit), None)
    return requirements_for(entry, entries, repo_root) if entry else []


def _declared_dependencies(path: pathlib.Path) -> dict[str, set[str]]:
    found: dict[str, set[str]] = {"Wants": set(), "Requires": set(), "BindsTo": set()}
    for line in path.read_text().splitlines():
        match = DEPENDENCY_LINE.match(line)
        if match:
            found[match.group(1)].update(match.group(2).split())
    return found


def _audit_entry(entry: dict[str, Any], entries: list[dict[str, Any]], repo_root: pathlib.Path) -> list[str]:
    unit = str(entry["unit"])
    try:
        requirements = requirements_for(entry, entries, repo_root)
    except ValueError as exc:
        return [f"{unit}: {exc}"]
    problems: list[str] = []
    runner = str(entry.get("runner") or "")
    if HANDOFF_RUNNER in runner and f"buzz-agent@{entry['owner']}" not in (entry.get("requires") or []):
        problems.append(f"{unit}: runner hands off through {HANDOFF_RUNNER} and does not require buzz-agent@{entry['owner']}")
    scope = str(entry.get("scope") or "system")
    unit_file = _unit_file(repo_root, scope, unit)
    declared = _declared_dependencies(unit_file) if unit_file else None
    for requirement in requirements:
        if requirement.scope != scope or declared is None:
            continue
        if requirement.service_name not in declared["Wants"] | declared["Requires"] | declared["BindsTo"]:
            problems.append(f"{unit}: requires {requirement.key} and its unit file {unit_file.relative_to(repo_root)} "
                            f"names no Wants=/Requires=/BindsTo= {requirement.service_name}")
    if declared is not None:
        mirrored = {r.service_name for r in requirements if r.scope == scope}
        for key in sorted(HARD_KEYS):
            for hard in sorted(declared[key] - mirrored):
                problems.append(f"{unit}: unit file {unit_file.relative_to(repo_root)} declares {key}={hard} "
                                f"and the manifest entry does not mirror it in requires")
    return problems


def _audit_folds(entries: list[dict[str, Any]]) -> list[str]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        groups.setdefault(str(entry.get("logical_workflow") or entry["unit"]), []).append(entry)
    problems: list[str] = []
    for key, members in sorted(groups.items()):
        lists = {str(m["unit"]): sorted(m.get("requires") or []) for m in members}
        if len({tuple(v) for v in lists.values()}) > 1:
            problems.append(f"{key}: the entries of one logical workflow declare different requires across the fold: "
                            + "; ".join(f"{unit} {declared}" for unit, declared in sorted(lists.items())))
    return problems


def audit(repo_root: pathlib.Path) -> list[str]:
    entries = load_entries(repo_root)
    problems = [p for entry in entries for p in _audit_entry(entry, entries, repo_root)]
    return problems + _audit_folds(entries)


def state_of(requirement: Requirement, show: Show) -> str:
    values, error = show(requirement.service_name, requirement.scope)
    if error or not values.get("ActiveState"):
        return "unknown"
    return values["ActiveState"]


def satisfied(state: str) -> bool | None:
    if state == "unknown":
        return None
    return state in ACTIVE_STATES


def systemctl_show(name: str, scope: str) -> tuple[dict[str, str], str | None]:
    command = ["systemctl", *(["--user"] if scope == "user" else []), "show", name, "--property=ActiveState"]
    env = dict(os.environ)
    if scope == "user":
        # A system unit running as dave exports neither; without them `systemctl --user`
        # cannot find the user manager and every user-scope requirement would read unknown.
        runtime_dir = env.setdefault("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}")
        env.setdefault("DBUS_SESSION_BUS_ADDRESS", f"unix:path={runtime_dir}/bus")
    try:
        done = subprocess.run(command, capture_output=True, text=True, timeout=5, check=False, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return {}, f"{type(exc).__name__}: {exc}"
    if done.returncode != 0:
        return {}, (done.stderr or done.stdout).strip() or f"systemctl exited {done.returncode}"
    values = dict(line.partition("=")[::2] for line in done.stdout.splitlines() if "=" in line)
    return values, None


def check(unit: str, repo_root: pathlib.Path, show: Show = systemctl_show) -> int:
    for requirement in requirements_of_unit(unit, repo_root):
        state = state_of(requirement, show)
        print(f"requires {requirement.unit}: {state}")
        if satisfied(state) is False:
            return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("command", choices=["check", "audit"])
    parser.add_argument("unit", nargs="?", help="the manifest unit whose requirements to check")
    parser.add_argument("--repo-root", type=pathlib.Path, default=None)
    args = parser.parse_args(argv)
    repo_root = (args.repo_root or repo_root_default()).resolve()
    if args.command == "check":
        if not args.unit:
            parser.error("check needs a unit")
        return check(args.unit, repo_root)
    problems = audit(repo_root)
    for problem in problems:
        print(f"PROBLEM\t{problem}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
