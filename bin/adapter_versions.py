#!/usr/bin/env python3
"""Installed vs published versions of the three packages the Buzz fleet runs on.

Usage: adapter_versions.py [--json] [--offline] [--installed-from npm-ls.json] [--latest-from versions.json]

    @agentclientprotocol/claude-agent-acp   the Claude harness (marcus, claudius, trajan, aurelian)
    @agentclientprotocol/codex-acp          the codex harness (augustus)
    @anthropic-ai/claude-code               what claude-agent-acp spawns through the wrapper

One line per package: `<name> installed=<v> latest=<v|unavailable> <current|stale|unknown>`.
Installed comes from `npm ls -g --json --depth=0`, latest from `npm view <name> version`;
`--offline` skips npm view, and the two `--*-from` files stand in for either call so the
compare is testable without a registry. Exit 0 whatever the verdict — a stale adapter is a
decision for the operator (the canary procedure in docs/runbook.md), not a defect — and 1
only when the installed list itself cannot be read.
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

PACKAGES = (
    "@agentclientprotocol/claude-agent-acp",
    "@agentclientprotocol/codex-acp",
    "@anthropic-ai/claude-code",
)
NPM_TIMEOUT = 20


def installed_versions(listing: dict) -> dict[str, str | None]:
    deps = listing.get("dependencies") or {}
    return {name: (deps.get(name) or {}).get("version") for name in PACKAGES}


def npm_ls_global() -> dict:
    out = subprocess.run(["npm", "ls", "-g", "--json", "--depth=0"], capture_output=True, text=True, timeout=NPM_TIMEOUT)
    return json.loads(out.stdout or "{}")


def npm_view_version(name: str) -> str | None:
    try:
        out = subprocess.run(["npm", "view", name, "version"], capture_output=True, text=True, timeout=NPM_TIMEOUT)
    except (subprocess.TimeoutExpired, OSError):
        return None
    return out.stdout.strip() or None if out.returncode == 0 else None


def verdict(installed: str | None, latest: str | None) -> str:
    if installed is None or latest is None:
        return "unknown"
    return "current" if installed == latest else "stale"


def report(installed: dict[str, str | None], latest: dict[str, str | None]) -> list[dict]:
    return [{"name": name, "installed": installed.get(name), "latest": latest.get(name),
             "verdict": verdict(installed.get(name), latest.get(name))} for name in PACKAGES]


def text_line(row: dict) -> str:
    return f"{row['name']} installed={row['installed'] or 'missing'} latest={row['latest'] or 'unavailable'} {row['verdict']}"


def parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--offline", action="store_true", help="installed only; latest reads unavailable")
    parser.add_argument("--installed-from", help="a saved `npm ls -g --json` instead of running npm")
    parser.add_argument("--latest-from", help="a {name: version} file instead of npm view")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        listing = json.load(open(args.installed_from)) if args.installed_from else npm_ls_global()
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"adapter_versions: cannot read the installed list: {exc}", file=sys.stderr)
        return 1
    installed = installed_versions(listing)
    if args.latest_from:
        latest = {name: json.load(open(args.latest_from)).get(name) for name in PACKAGES}
    elif args.offline:
        latest = {name: None for name in PACKAGES}
    else:
        latest = {name: npm_view_version(name) for name in PACKAGES}
    rows = report(installed, latest)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("\n".join(text_line(row) for row in rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
