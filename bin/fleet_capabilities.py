#!/usr/bin/env python3
"""Render each buzz-agent's S1 capability artefacts from its manifest — or check them.

The manifest `design/agents/<name>.toml` `[surfaces.interactive]` block is the source:

    tools        = "claude-code-builtins" | "codex-builtins"
    tools_deny   = [<builtin tool names withheld>]
    bridge_tools = [<families of qmd, notion, brave the bridge shim advertises>]
    plugins      = [<Claude Code plugins enabled in the session, by marketplace name>]  # optional

From it, two artefacts per agent land in buzz-team/ (deployed to ~/.config/buzz-team/ by
bin/deploy_buzz_team.sh, drift-checked like every adopted file):

  buzz-team-mcp-<name>          the bridge shim buzz-agent@.service names with
                                --mcp-command %h/.config/buzz-team/buzz-team-mcp-%i; execs
                                buzz-team-mcp.py --agent <name> --tools <families>. The
                                server name is the file stem, so the tools are
                                mcp__buzz-team-mcp-<name>__*. Every harness gets one.
  agent-settings-<name>.json    claude-agent-acp harness only: the base agent-settings.json
                                (secret-path denies, connector denies, the cloud-scheduling deny
                                — Skill(schedule) plus the RemoteTrigger tool it drives —
                                and the Stop receipt hook)
                                plus tools_deny plus a deny for every tool of a bridge
                                family the shim does not advertise, plus enabledPlugins
                                for the manifest's plugins. Belt to the shim's braces on
                                the Claude side; codex reads no settings file.

One artefact is fleet-wide and root-installed, never deployed:

  etc/claude-code/managed-settings.json   the base's secret-path denies (Read/Edit of the
                                six credential paths) and nothing else. Claude Code applies
                                a managed file to every session on the box whatever
                                --setting-sources or --settings say, so this is the one
                                deny no flag can drop. Fleet policy (connectors,
                                Skill(schedule)) stays out: it would bind Dave's own
                                sessions and the scheduled runners. Installed by hand
                                (sudo install -D -o root -g root -m 0644) and compared by
                                bin/check_deploy_drift.sh.

`render` writes them; `check` exits 1 with a diff when a committed file differs from what
the manifests render — the gate's way of refusing a hand edit.
"""

from __future__ import annotations

import argparse
import difflib
import importlib.util
import json
import pathlib
import sys
import tomllib
from typing import Any

BASE_SETTINGS = "agent-settings.json"
MANAGED_SETTINGS = "etc/claude-code/managed-settings.json"
CLAUDE_HARNESS = "claude-agent-acp"
TOOL_FAMILIES = {"claude-code-builtins": CLAUDE_HARNESS, "codex-builtins": "codex-acp"}


def bridge_module(repo: pathlib.Path):
    """The bridge owns the family -> tool-name table; the renderer reads it from the file
    rather than keeping a second copy that could drift from what the shim filters."""
    path = repo / "buzz-team" / "buzz-team-mcp.py"
    spec = importlib.util.spec_from_file_location("buzz_team_mcp", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def manifests(repo: pathlib.Path) -> dict[str, dict[str, Any]]:
    return {p.stem: tomllib.loads(p.read_text(encoding="utf-8"))
            for p in sorted((repo / "design" / "agents").glob("*.toml"))}


def interactive(name: str, data: dict[str, Any]) -> dict[str, Any]:
    block = (data.get("surfaces") or {}).get("interactive") or {}
    if not block.get("present"):
        raise SystemExit(f"{name}: no present [surfaces.interactive] block")
    for key in ("tools", "tools_deny", "bridge_tools"):
        if key not in block:
            raise SystemExit(f"{name}: [surfaces.interactive] lacks {key}")
    if TOOL_FAMILIES.get(block["tools"]) != data.get("harness"):
        raise SystemExit(f"{name}: tools = {block['tools']!r} does not match harness = {data.get('harness')!r}")
    return block


def shim_text(name: str, families: list[str]) -> str:
    return (
        "#!/bin/sh\n"
        f"# Rendered by bin/fleet_capabilities.py from design/agents/{name}.toml — edit the manifest, not this file.\n"
        f"# buzz-agent@{name} names this shim with --mcp-command; the server name is this file's stem.\n"
        f'exec "$(dirname "$0")/buzz-team-mcp.py" --agent {name} --tools {",".join(families)} "$@"\n'
    )


def settings_text(name: str, block: dict[str, Any], base: dict[str, Any], bridge) -> str:
    withheld = [family for family in bridge.FAMILIES if family not in block["bridge_tools"]]
    unknown = [family for family in block["bridge_tools"] if family not in bridge.FAMILIES]
    if unknown:
        raise SystemExit(f"{name}: bridge_tools names no family: {unknown}")
    deny = list(base["permissions"]["deny"])
    deny += [tool for tool in block["tools_deny"] if tool not in deny]
    for family in withheld:
        deny += [f"mcp__buzz-team-mcp-{name}__{tool}" for tool in bridge.family_tools(family)]
    rendered = dict(base)
    rendered["permissions"] = dict(base["permissions"], deny=deny)
    plugins = block.get("plugins") or []
    if plugins:
        rendered["enabledPlugins"] = {name: True for name in plugins}
    return json.dumps(rendered, indent=2) + "\n"


def is_secret_path_deny(rule: str) -> bool:
    return rule.startswith(("Read(//", "Edit(//"))


def managed_settings_text(base: dict[str, Any]) -> str:
    deny = [rule for rule in base["permissions"]["deny"] if is_secret_path_deny(rule)]
    return json.dumps({"permissions": {"deny": deny}}, indent=2) + "\n"


def render(repo: pathlib.Path) -> dict[str, str]:
    """Every artefact as {path relative to the repo: text}."""
    bridge = bridge_module(repo)
    base = json.loads((repo / "buzz-team" / BASE_SETTINGS).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, data in manifests(repo).items():
        block = interactive(name, data)
        out[f"buzz-team/buzz-team-mcp-{name}"] = shim_text(name, block["bridge_tools"])
        if data.get("harness") == CLAUDE_HARNESS:
            out[f"buzz-team/agent-settings-{name}.json"] = settings_text(name, block, base, bridge)
    out[MANAGED_SETTINGS] = managed_settings_text(base)
    return out


def is_shim(rel: str) -> bool:
    return pathlib.PurePath(rel).name.startswith("buzz-team-mcp-")


def write(repo: pathlib.Path) -> int:
    for rel, text in render(repo).items():
        path = repo / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        if is_shim(rel):
            path.chmod(0o755)
        print(f"rendered {rel}")
    return 0


def check(repo: pathlib.Path) -> int:
    status = 0
    for rel, expected in render(repo).items():
        path = repo / rel
        if not path.is_file():
            print(f"missing: {path.relative_to(repo)} — run bin/fleet_capabilities.py render")
            status = 1
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            sys.stdout.writelines(difflib.unified_diff(actual.splitlines(True), expected.splitlines(True),
                                                       fromfile=str(path.relative_to(repo)), tofile="render"))
            status = 1
        if is_shim(rel) and not path.stat().st_mode & 0o111:
            print(f"not executable: {path.relative_to(repo)} — the harness spawns it directly")
            status = 1
    return status


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    for name in ("render", "check"):
        command = sub.add_parser(name)
        command.add_argument("--repo", default=str(pathlib.Path(__file__).resolve().parents[1]))
    args = parser.parse_args(argv)
    repo = pathlib.Path(args.repo)
    return write(repo) if args.command == "render" else check(repo)


if __name__ == "__main__":
    sys.exit(main())
