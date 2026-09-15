#!/usr/bin/env python3
"""W19-class residue scanner for a retired workflow (T5.3b).

W19 retired two campaigns by deleting their units and left the shims executable, the profiles
present and the registry rows standing — nothing checked. This module is that check: a source
scan over a checkout (the retire PR's branch) and a live scan over the box (installed units,
deployed copies, the deny-listed override env that is printed and never stat'ed).

    bin/workflow_retire_residue.py --source ROOT --workflow ID [--json]
    bin/workflow_retire_residue.py --live --workflow ID [--runtime R --etc E --user-tree U] [--json]
    bin/workflow_retire_residue.py --all [--live] [--json]

Exit 0 clear / 1 residue / 2 unknown workflow.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import tomllib
from typing import Any, Callable

CLASSES = ("executable", "inert", "files", "declared", "declared-pending-prune", "prose",
           "installed", "deployed", "dave-only", "runtime-state")
BLOCKING_SOURCE = frozenset({"executable", "files", "declared"})
BLOCKING_LIVE = frozenset({"installed", "deployed", "inert"})
CLEARERS = ("this PR", "bin/deploy --prune", "sudo", "Dave", "nothing")
W19_COLUMNS = ("#", "residue", "tree", "has a check?", "who clears it", "how")
REGISTRY = "design/retired-workflows.toml"
EXCLUDED_PREFIXES = ("systemd/archive/", "design/archive/", ".git/", "graft/", "node_modules/", ".claude/")
PROSE_PREFIXES = ("docs/", "design/", "profiles/", "skills/")
DECLARATION_FILES = ("config/fleet-units.tsv", "bin/buzz_producers.tsv", "tests/ci-expected-skips.txt",
                     "design/deploy-exclusions.toml", REGISTRY)
COMMENT_PREFIXES = ("#", ";", "//")
SystemctlRunner = Callable[[list[str]], tuple[int, str]]


def path_exists(path: pathlib.Path | str) -> bool:
    """The one stat hook; the env_override path is never passed through it."""
    return pathlib.Path(path).exists()


def systemctl_runner(argv: list[str]) -> tuple[int, str]:
    env = {**os.environ, "TZ": "UTC", "SYSTEMD_PAGER": ""}
    try:
        done = subprocess.run(["systemctl", "--no-pager", *argv], capture_output=True, text=True, env=env, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return 1, str(exc)
    return done.returncode, done.stdout


# --- subjects -------------------------------------------------------------------------------------

def _manifests(root: pathlib.Path) -> list[tuple[str, pathlib.Path, dict[str, Any]]]:
    out = []
    for path in sorted((root / "design" / "agents").glob("*.toml")):
        try:
            data = tomllib.loads(path.read_text(encoding="utf-8"))
        except (tomllib.TOMLDecodeError, OSError):
            continue
        out.append((data.get("name") or path.stem, path, data))
    return out


def _entries(root: pathlib.Path) -> list[tuple[str, dict[str, Any]]]:
    return [(owner, entry) for owner, _, data in _manifests(root) for entry in data.get("workflows", []) if entry.get("unit")]


def _logical(entry: dict[str, Any]) -> str:
    return str(entry.get("logical_workflow") or entry["unit"])


def _unit_file(root: pathlib.Path, unit: str, suffix: str) -> pathlib.Path | None:
    for candidate in (root / "systemd" / f"{unit}.{suffix}", root / "systemd" / "user" / f"{unit}.{suffix}"):
        if path_exists(candidate):
            return candidate
    return None


def _service_env(root: pathlib.Path, unit: str, key: str) -> str | None:
    path = _unit_file(root, unit, "service")
    if path is None:
        return None
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if line.startswith(f"Environment={key}="):
            return line.split("=", 2)[2].strip().strip('"').replace("%n", f"{unit}.service")
    return None


def subjects_from_manifests(root: pathlib.Path, workflow_id: str) -> dict[str, Any] | None:
    root = pathlib.Path(root)
    entries = _entries(root)
    mine = [(owner, e) for owner, e in entries if _logical(e) == workflow_id]
    if not mine:
        return None
    others = [e for _, e in entries if _logical(e) != workflow_id]
    shared = lambda key: {str(e.get(key)) for e in others if e.get(key)}  # noqa: E731
    shared_suites = {s for e in others for s in e.get("suite", [])}
    units = [str(e["unit"]) for _, e in mine]
    slugs = sorted({s for u in [workflow_id, *units] for s in (u, u.replace("-", "_"))})
    profiles = {str(e["profile"]) for _, e in mine if e.get("profile")} - shared("profile")
    for slug in slugs:
        example = root / "profiles" / f"{slug}.env.example"
        if path_exists(example):
            profiles.add(f"profiles/{slug}.env.example")
    contracts = {str(e["contract"]) for _, e in mine if e.get("contract")} - shared("contract")
    run_markers = [marker for u in units if (marker := _service_env(root, u, "DELIVERY_RUN_MARKER"))]
    env_override = next((env for u in units if (env := _service_env(root, u, "AGENT_JOB_OVERRIDES"))), None)
    return {"id": workflow_id, "units": units, "scope": str(mine[0][1].get("scope", "system")), "owner": mine[0][0],
            "runners": sorted({str(e["runner"]) for _, e in mine if e.get("runner")} - shared("runner")),
            "profiles": sorted(profiles), "contract": sorted(contracts)[0] if contracts else "",
            "suites": sorted({s for _, e in mine for s in e.get("suite", [])} - shared_suites),
            "env_override": env_override, "run_markers": run_markers, "slugs": slugs, "env_removed_attested": False}


def subjects_from_registry(root: pathlib.Path, workflow_id: str) -> dict[str, Any] | None:
    for entry in registry_entries(root):
        if entry.get("id") == workflow_id:
            return subjects_from_entry(entry)
    return None


def subjects_from_entry(entry: dict[str, Any]) -> dict[str, Any]:
    units = list(entry.get("units", []))
    return {"id": entry["id"], "units": units, "scope": entry.get("scope", "system"), "owner": entry.get("owner", ""),
            "runners": list(entry.get("runners", [])), "profiles": list(entry.get("profiles", [])),
            "contract": entry.get("contract", ""), "suites": list(entry.get("suites", [])),
            "env_override": entry.get("env_override") or None, "run_markers": list(entry.get("run_markers", [])),
            "slugs": sorted({s for u in [entry["id"], *units] for s in (u, u.replace("-", "_"))}),
            "env_removed_attested": bool(entry.get("env_removed_attested", False))}


def registry_entries(root: pathlib.Path) -> list[dict[str, Any]]:
    path = pathlib.Path(root) / REGISTRY
    if not path_exists(path):
        return []
    try:
        return list(tomllib.loads(path.read_text(encoding="utf-8")).get("retired", []))
    except tomllib.TOMLDecodeError:
        return []


def subject_paths(root: pathlib.Path, subjects: dict[str, Any]) -> list[str]:
    out = [*subjects["runners"], *subjects["profiles"], *subjects["suites"]]
    if subjects.get("contract"):
        out.append(subjects["contract"])
    for unit in subjects["units"]:
        for suffix in ("timer", "service"):
            path = _unit_file(pathlib.Path(root), unit, suffix)
            if path is not None:
                out.append(path.relative_to(root).as_posix())
    return sorted(set(out))


# --- items ----------------------------------------------------------------------------------------

def _item(cls: str, path: Any, line: int | None, what: str, tree: str, has_check: str, clears: str, how: str, blocks: bool) -> dict[str, Any]:
    return {"class": cls, "path": str(path), "line": line, "what": what, "tree": tree, "has_check": has_check,
            "clears": clears, "how": how, "blocks": blocks}


def _source_item(cls: str, path: str, line: int | None, what: str, clears: str, how: str) -> dict[str, Any]:
    checks = {"executable": "residue-source (this PR)", "files": "residue-source (this PR)", "declared": "residue-source (this PR)",
              "declared-pending-prune": "check_deploy_drift.sh", "inert": "none — inert, listed", "prose": "none — listed"}
    return _item(cls, path, line, what, "source", checks[cls], clears, how, cls in BLOCKING_SOURCE)


def _boundary_re(words: list[str]) -> re.Pattern[str] | None:
    if not words:
        return None
    return re.compile(r"(?<![A-Za-z0-9])(?:" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")(?![A-Za-z0-9])")


def _is_comment(line: str) -> bool:
    return line.lstrip().startswith(COMMENT_PREFIXES)


def _read(path: pathlib.Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None


def _walk(root: pathlib.Path):
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.is_symlink():
            continue
        relative = path.relative_to(root).as_posix()
        if relative.startswith(EXCLUDED_PREFIXES):
            continue
        text = _read(path)
        if text is not None:
            yield relative, text


def _line_of(text: str, needle: str, key: str | None = None) -> int | None:
    for number, line in enumerate(text.splitlines(), 1):
        if needle in line and (key is None or line.lstrip().startswith(key)):
            return number
    return None


# --- source scan ----------------------------------------------------------------------------------

def scan_source(root: pathlib.Path, subjects: dict[str, Any]) -> dict[str, Any]:
    root = pathlib.Path(root)
    files = list(_walk(root))
    items: list[dict[str, Any]] = []
    items += _unit_items(root, subjects)
    items += _manifest_items(root, subjects)
    items += _runner_items(root, subjects, files)
    items += _file_items(root, subjects)
    items += _declared_items(root, subjects, files)
    items += _pending_prune_items(root, subjects)
    items += _prose_items(root, subjects, files)
    return _report("source", subjects["id"], items)


def _report(mode: str, workflow_id: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {"mode": mode, "id": workflow_id, "items": items, "verdict": verdict(items)}


def verdict(items: list[dict[str, Any]]) -> str:
    return "residue" if any(item["blocks"] for item in items) else "clear"


def _unit_items(root: pathlib.Path, subjects: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for unit in subjects["units"]:
        for suffix in ("timer", "service"):
            path = _unit_file(root, unit, suffix)
            if path is not None:
                relative = path.relative_to(root).as_posix()
                out.append(_source_item("executable", relative, None, f"unit file {relative} still present (live tree)", "this PR",
                                        f"git mv {relative} systemd/archive/{path.name}"))
    return out


def _manifest_items(root: pathlib.Path, subjects: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    slug_re = _boundary_re(subjects["slugs"])
    runner_re = _boundary_re([pathlib.PurePosixPath(r).name for r in subjects["runners"]])
    for _, path, data in _manifests(root):
        relative = path.relative_to(root).as_posix()
        text = _read(path) or ""
        for entry in data.get("workflows", []):
            unit = str(entry.get("unit", ""))
            if unit in subjects["units"]:
                out.append(_source_item("executable", relative, _line_of(text, f'"{unit}"', "unit"), f"[[workflows]] entry unit = {unit}", "this PR",
                                        "remove the block; flip the surface to present = false if it empties"))
                continue
            if runner_re and entry.get("runner") and runner_re.search(str(entry["runner"])) and path_exists(root / str(entry["runner"])):
                out.append(_source_item("executable", relative, _line_of(text, str(entry["runner"]), "runner"), f"[[workflows]] {unit} runner = {entry['runner']} names an owned runner", "this PR",
                                        "the runner is shared — take it out of the subject set or retire both"))
            notes = str(entry.get("notes", ""))
            if slug_re and notes and slug_re.search(notes):
                out.append(_source_item("prose", relative, _line_of(text, notes[:40], "notes"), f"[[workflows]] {unit} notes mention {subjects['id']}", "nothing",
                                        "prose — listed, not edited"))
        for surface, body in (data.get("surfaces") or {}).items():
            governed = str(body.get("governed_by", "")) if isinstance(body, dict) else ""
            for runner in subjects["runners"]:
                if runner_re and runner_re.search(governed):
                    cls = "executable" if path_exists(root / runner) else "declared"
                    out.append(_source_item(cls, relative, _line_of(text, "governed_by"), f"[surfaces.{surface}] governed_by names {runner}", "this PR",
                                            f"drop {runner} from governed_by"))
            notes = str(body.get("notes", "")) if isinstance(body, dict) else ""
            if slug_re and notes and slug_re.search(notes):
                out.append(_source_item("prose", relative, _line_of(text, notes[:40], "notes"), f"[surfaces.{surface}] notes mention {subjects['id']}", "nothing",
                                        "prose — listed, not edited"))
    return out


def _is_live(rel: str) -> bool:
    if rel in DECLARATION_FILES:
        return False
    if rel.startswith("design/agents/"):
        return True
    return not rel.startswith(PROSE_PREFIXES) and not rel.endswith((".md", ".txt"))


def _references(runner: str, files: list[tuple[str, str]]) -> list[tuple[str, int, str]]:
    name_re = _boundary_re([pathlib.PurePosixPath(runner).name])
    hits = []
    for rel, text in files:
        if rel == runner or not _is_live(rel) or name_re is None:
            continue
        for number, line in enumerate(text.splitlines(), 1):
            if _is_comment(line) or _is_manifest_notes(rel, line) or not name_re.search(line):
                continue
            hits.append((rel, number, line.strip()[:60]))
    return sorted(hits, key=lambda hit: (not hit[2].startswith("Exec"), hit[0], hit[1]))


def _is_manifest_notes(rel: str, line: str) -> bool:
    return rel.startswith("design/agents/") and line.lstrip().startswith("notes")


def _shim_target(root: pathlib.Path, runner: str) -> str | None:
    text = _read(root / runner) or ""
    for line in text.splitlines():
        if _is_comment(line):
            continue
        for match in re.finditer(r"([A-Za-z0-9_.-]+\.(?:sh|py))\b", line):
            candidate = f"bin/{match.group(1)}"
            if candidate != runner and path_exists(root / candidate):
                return candidate
    return None


def _runner_items(root: pathlib.Path, subjects: dict[str, Any], files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    out = []
    for runner in subjects["runners"]:
        refs = _references(runner, files)
        if not path_exists(root / runner):
            for rel, number, line in refs:
                if line.startswith("Exec"):
                    out.append(_source_item("executable", rel, number, f"Exec line names the removed {runner} — the unit would fail", "this PR",
                                            "archive the unit or point it elsewhere"))
            continue
        if refs:
            shown = ", ".join(f"{rel}:{number} ({line})" for rel, number, line in refs[:4])
            out.append(_source_item("executable", runner, None, f"present in bin/ and referenced from {shown}", "this PR", f"git rm {runner}"))
            continue
        target = _shim_target(root, runner)
        if target:
            out.append(_source_item("executable", runner, None, f"shim still execs {target}, which exists", "this PR", f"git rm {runner}"))
        else:
            out.append(_source_item("inert", runner, None, "present in bin/, referenced by nothing live (inert is not dangerous)", "this PR", f"git rm {runner}"))
    return out


def _file_items(root: pathlib.Path, subjects: dict[str, Any]) -> list[dict[str, Any]]:
    out = []
    for relative in subjects["profiles"]:
        if path_exists(root / relative):
            out.append(_source_item("files", relative, None, "profile still present", "this PR", f"git rm {relative}"))
    contract = subjects.get("contract") or ""
    if contract and not contract.startswith("design/archive/") and path_exists(root / contract):
        out.append(_source_item("files", contract, None, "contract still live (outside design/archive/)", "this PR",
                                f"git mv {contract} design/archive/contracts/{pathlib.PurePosixPath(contract).name}"))
    for relative in subjects["suites"]:
        if path_exists(root / relative):
            out.append(_source_item("files", relative, None, "suite still present", "this PR", f"git rm {relative}"))
    return out


def _declared_items(root: pathlib.Path, subjects: dict[str, Any], files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    out = []
    texts = dict(files)
    units = set(subjects["units"])
    for number, line in enumerate(texts.get("config/fleet-units.tsv", "").splitlines(), 1):
        first = line.split("\t")[0]
        if first in units:
            out.append(_source_item("declared", "config/fleet-units.tsv", number, f"fleet-units row {first}", "this PR", "drop the row"))
    for number, line in enumerate(texts.get("bin/buzz_producers.tsv", "").splitlines(), 1):
        first = line.split("\t")[0]
        if first.split(".")[0] in units:
            out.append(_source_item("declared", "bin/buzz_producers.tsv", number, f"buzz producer row {first}", "this PR", "drop the row"))
    skip_re = _boundary_re(subjects["slugs"] + [pathlib.PurePosixPath(s).name for s in subjects["suites"]])
    for number, line in enumerate(texts.get("tests/ci-expected-skips.txt", "").splitlines(), 1):
        if skip_re and skip_re.search(line):
            out.append(_source_item("declared", "tests/ci-expected-skips.txt", number, "ci-expected-skips line", "this PR", "drop the line"))
    return out


def _pending_prune_items(root: pathlib.Path, subjects: dict[str, Any]) -> list[dict[str, Any]]:
    path = root / "design/deploy-exclusions.toml"
    text = _read(path)
    if text is None:
        return []
    try:
        entries = tomllib.loads(text).get("runtime_only", [])
    except tomllib.TOMLDecodeError:
        return []
    owned = set(subject_paths(root, subjects)) | {*subjects["runners"], *subjects["profiles"], *subjects["suites"]}
    for unit in subjects["units"]:
        owned |= {f"systemd/{unit}.timer", f"systemd/{unit}.service", f"systemd/user/{unit}.timer", f"systemd/user/{unit}.service"}
    slug_re = _boundary_re(subjects["slugs"])
    out = []
    for entry in entries:
        entry_path = str(entry.get("path", ""))
        if entry_path in owned or (slug_re and slug_re.search(entry_path)):
            out.append(_source_item("declared-pending-prune", "design/deploy-exclusions.toml", _line_of(text, entry_path, "path"),
                                    f"runtime_only entry {entry_path} (self-clearing)", "bin/deploy --prune", "bin/deploy --prune, then drop the entry"))
    return out


def _prose_items(root: pathlib.Path, subjects: dict[str, Any], files: list[tuple[str, str]]) -> list[dict[str, Any]]:
    slug_re = _boundary_re(subjects["slugs"])
    if slug_re is None:
        return []
    own = set(subject_paths(root, subjects))
    out = []
    for rel, text in files:
        if rel in own or rel in DECLARATION_FILES:
            continue
        is_prose_file = not _is_live(rel)
        for number, line in enumerate(text.splitlines(), 1):
            if not slug_re.search(line) or _is_manifest_notes(rel, line):
                continue
            if is_prose_file or _is_comment(line) or line.startswith("Description="):
                out.append(_source_item("prose", rel, number, f"mentions {subjects['id']}: {line.strip()[:70]}", "nothing", "prose — listed, not edited"))
    return out


# --- live scan ------------------------------------------------------------------------------------

def scan_live(subjects: dict[str, Any], runtime_root: pathlib.Path, etc_dir: pathlib.Path, user_tree: pathlib.Path,
              systemctl_runner: SystemctlRunner = systemctl_runner) -> dict[str, Any]:
    runtime_root, etc_dir, user_tree = pathlib.Path(runtime_root), pathlib.Path(etc_dir), pathlib.Path(user_tree)
    items: list[dict[str, Any]] = []
    items += _installed_items(subjects, etc_dir, user_tree, systemctl_runner)
    items += _deployed_items(subjects, runtime_root)
    items += _dave_only_items(subjects)
    items += _runtime_state_items(subjects, runtime_root)
    return _report("live", subjects["id"], items)


def _sudo(scope: str) -> tuple[str, str]:
    return ("", "--user ") if scope == "user" else ("sudo ", "")


def _installed_items(subjects: dict[str, Any], etc_dir: pathlib.Path, user_tree: pathlib.Path, runner: SystemctlRunner) -> list[dict[str, Any]]:
    out = []
    scope = subjects.get("scope", "system")
    sudo, user = _sudo(scope)
    base = user_tree if scope == "user" else etc_dir
    names = [f"{u}.{suffix}" for u in subjects["units"] for suffix in ("timer", "service")]
    present = [base / name for name in names if path_exists(base / name)]
    rm_line = f"{sudo}rm {' '.join(str(p) for p in present)} && {sudo}systemctl {user}daemon-reload && {sudo}systemctl {user}reset-failed"
    for path in present:
        out.append(_item("installed", path, None, f"{path} still installed", "installed", "test_workflow_retirements.sh group 2 / --live", "sudo", rm_line, True))
    user_flag = ["--user"] if scope == "user" else []
    argv = [*user_flag, "list-unit-files", *names]
    code, stdout = runner(argv)
    listed = [line.split()[0] for line in stdout.splitlines() if line.strip() and line.split()[0] in names]
    for name in listed:
        out.append(_item("installed", name, None, f"systemctl {user}list-unit-files still lists {name}", "installed", "--live", "sudo",
                         f"{sudo}systemctl {user}disable --now {name}; then the rm + daemon-reload line", True))
    if listed:
        _, active_out = runner([*user_flag, "is-active", *listed])
        for name, state in zip(listed, active_out.splitlines()):
            if state.strip() and state.strip() != "inactive":
                out.append(_item("installed", name, None, f"systemctl {user}is-active {name} = {state.strip()}", "installed", "--live", "sudo",
                                 f"{sudo}systemctl {user}disable --now {name}", True))
    return out


def _deployed_items(subjects: dict[str, Any], runtime_root: pathlib.Path) -> list[dict[str, Any]]:
    candidates = [*subjects["runners"], *subjects["profiles"]]
    for unit in subjects["units"]:
        candidates += [f"systemd/{unit}.timer", f"systemd/{unit}.service", f"systemd/user/{unit}.timer", f"systemd/user/{unit}.service"]
    out = []
    for relative in candidates:
        path = runtime_root / relative
        if path_exists(path):
            out.append(_item("deployed", path, None, f"deployed copy {path} still present", "deployed", "check_deploy_drift.sh / --live", "bin/deploy --prune",
                             "bin/deploy --prune (the PR body lists what else prune deletes)", True))
    return out


def _dave_only_items(subjects: dict[str, Any]) -> list[dict[str, Any]]:
    env = subjects.get("env_override")
    if not env:
        return []
    attested = bool(subjects.get("env_removed_attested"))
    what = f"unverifiable from an agent (deny-listed); Dave runs: ls -l {env}; rm {env}" + (" — attested removed" if attested else "")
    return [_item("dave-only", env, None, what, "deny-listed", "none — Dave's attestation (--env-removed)", "Dave",
                  f"rm {env}; then bin/workflow_pr.py clear {subjects['id']} --env-removed", not attested)]


def _runtime_state_items(subjects: dict[str, Any], runtime_root: pathlib.Path) -> list[dict[str, Any]]:
    out = []
    for marker in subjects.get("run_markers", []):
        out.append(_item("runtime-state", marker, None, "run marker (listed, not stat'ed; never blocking)", "runtime", "none", "nothing",
                         "rm by hand if the marker exists; governed by nothing", False))
    receipts = runtime_root / "var" / "workflow-receipts" / subjects["id"]
    if path_exists(receipts):
        out.append(_item("runtime-state", receipts, None, "run receipts present — governed by the retention decision", "runtime", "none", "Dave",
                         "per artifact_retention.receipts (keep / archive)", False))
    return out


# --- rendering + CLI ------------------------------------------------------------------------------

def render_w19_table(report: dict[str, Any]) -> str:
    lines = ["| " + " | ".join(W19_COLUMNS) + " |", "|" + "---|" * len(W19_COLUMNS)]
    for number, item in enumerate(report["items"], 1):
        where = f"{item['path']}:{item['line']}" if item.get("line") else item["path"]
        residue = f"{item['class']}: {item['what']} ({where})"
        cells = [str(number), residue, item["tree"], item["has_check"], item["clears"], item["how"]]
        lines.append("| " + " | ".join(c.replace("|", "\\|").replace("\n", " ") for c in cells) + " |")
    lines.append("")
    lines.append(f"Verdict: {report['verdict']}")
    return "\n".join(lines)


def _default_root() -> pathlib.Path:
    return pathlib.Path(__file__).resolve().parent.parent


def _scan_one(args: argparse.Namespace, root: pathlib.Path, subjects: dict[str, Any]) -> dict[str, Any]:
    if args.live:
        return scan_live(subjects, pathlib.Path(args.runtime), pathlib.Path(args.etc), pathlib.Path(args.user_tree))
    return scan_source(root, subjects)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--source", help="checkout to scan (default: this checkout)")
    parser.add_argument("--workflow", help="logical workflow id")
    parser.add_argument("--live", action="store_true", help="scan the box: installed units, deployed copies, the override env")
    parser.add_argument("--all", action="store_true", help="every [[retired]] entry in the registry")
    parser.add_argument("--runtime", default=os.path.expanduser("~/agent-workforce"))
    parser.add_argument("--etc", default="/etc/systemd/system")
    parser.add_argument("--user-tree", default=os.path.expanduser("~/.config/systemd/user"))
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    root = pathlib.Path(args.source).resolve() if args.source else _default_root()
    if args.all:
        subject_sets = [subjects_from_entry(entry) for entry in registry_entries(root)]
    elif args.workflow:
        found = subjects_from_registry(root, args.workflow) or subjects_from_manifests(root, args.workflow)
        if found is None:
            print(f"unknown workflow: {args.workflow} (not in {REGISTRY} nor design/agents/*.toml)", file=sys.stderr)
            return 2
        subject_sets = [found]
    else:
        parser.error("--workflow ID or --all")
    reports = [_scan_one(args, root, subjects) for subjects in subject_sets]
    if args.json:
        print(json.dumps(reports[0] if len(reports) == 1 and not args.all else reports, indent=2))
    else:
        for report in reports:
            print(f"## {report['id']} ({report['mode']})")
            print(render_w19_table(report) if report["items"] else f"no residue\n\nVerdict: {report['verdict']}")
    return 1 if any(report["verdict"] != "clear" for report in reports) else 0


if __name__ == "__main__":
    sys.exit(main())
