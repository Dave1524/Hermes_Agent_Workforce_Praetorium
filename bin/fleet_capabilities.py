#!/usr/bin/env python3
"""Render each buzz-agent's S1 capability artefacts from its manifest — or check them.

The manifest `design/agents/<name>.toml` `[surfaces.interactive]` block is the source:

    tools        = "claude-code-builtins" | "codex-builtins"
    tools_deny   = [<builtin tool names withheld>]
    bridge_tools = [<families of qmd, notion, brave the bridge shim advertises>]

From it, two artefacts per agent land in buzz-team/ (deployed to ~/.config/buzz-team/ by
bin/deploy_buzz_team.sh, drift-checked like every adopted file):

  buzz-team-mcp-<name>          the bridge shim buzz-agent@.service names with
                                --mcp-command %h/.config/buzz-team/buzz-team-mcp-%i; execs
                                buzz-team-mcp.py --agent <name> --tools <families>. The
                                server name is the file stem, so the tools are
                                mcp__buzz-team-mcp-<name>__*. Every harness gets one.
  agent-settings-<name>.json    claude-agent-acp harness only: the base agent-settings.json
                                (secret-path denies, connector denies, Stop receipt hook)
                                plus tools_deny plus a deny for every tool of a bridge
                                family the shim does not advertise. Belt to the shim's
                                braces on the Claude side; codex reads no settings file.

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
    return json.dumps(rendered, indent=2) + "\n"


def render(repo: pathlib.Path) -> dict[str, str]:
    """Every artefact as {relative path under buzz-team/: text}."""
    bridge = bridge_module(repo)
    base = json.loads((repo / "buzz-team" / BASE_SETTINGS).read_text(encoding="utf-8"))
    out: dict[str, str] = {}
    for name, data in manifests(repo).items():
        block = interactive(name, data)
        out[f"buzz-team-mcp-{name}"] = shim_text(name, block["bridge_tools"])
        if data.get("harness") == CLAUDE_HARNESS:
            out[f"agent-settings-{name}.json"] = settings_text(name, block, base, bridge)
    return out


def write(repo: pathlib.Path) -> int:
    for rel, text in render(repo).items():
        path = repo / "buzz-team" / rel
        path.write_text(text, encoding="utf-8")
        if rel.startswith("buzz-team-mcp-"):
            path.chmod(0o755)
        print(f"rendered {path.relative_to(repo)}")
    return 0


def check(repo: pathlib.Path) -> int:
    status = 0
    for rel, expected in render(repo).items():
        path = repo / "buzz-team" / rel
        if not path.is_file():
            print(f"missing: {path.relative_to(repo)} — run bin/fleet_capabilities.py render")
            status = 1
            continue
        actual = path.read_text(encoding="utf-8")
        if actual != expected:
            sys.stdout.writelines(difflib.unified_diff(actual.splitlines(True), expected.splitlines(True),
                                                       fromfile=str(path.relative_to(repo)), tofile="render"))
            status = 1
        if rel.startswith("buzz-team-mcp-") and not path.stat().st_mode & 0o111:
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
