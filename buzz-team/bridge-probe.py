#!/usr/bin/env python3
"""Spawn one per-agent bridge shim the way its harness does and report what it advertises.

    bridge-probe.py <shim> [--expect qmd,notion,brave]

Prints `server=<serverInfo.name> families=<csv>` from initialize + tools/list — the real
bridge over the real qmd, broker socket and Brave daemon, so nothing is stubbed and nothing
is spent (no tools/call). With --expect, exits 1 when the advertised families differ.

Its own file so verify-fleet.sh gate 15 can run it unchanged on the host and inside
augustus's bwrap namespace via nsenter — the two places that can disagree (notion-probe.py,
2026-08-10). The shim's stdout is the only thing read; its stderr is left alone.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys

FAMILIES = ("qmd", "notion", "brave")


def family_of(name: str) -> str:
    if name.startswith("notion_"):
        return "notion"
    if name.startswith("brave_"):
        return "brave"
    return "qmd"


class Shim:
    def __init__(self, path: str):
        self.proc = subprocess.Popen([path], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
        self.n = 0

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self._send({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise SystemExit(f"bridge-probe: the shim closed its stdout before answering {method}")
            msg = json.loads(line)
            if msg.get("id") == self.n:
                if "error" in msg:
                    raise SystemExit(f"bridge-probe: {method} failed: {msg['error']}")
                return msg["result"]

    def _send(self, msg: dict) -> None:
        self.proc.stdin.write(json.dumps(msg) + "\n")
        self.proc.stdin.flush()

    def close(self) -> None:
        self.proc.stdin.close()
        self.proc.wait(timeout=15)


def advertised(path: str) -> tuple[str, list[str]]:
    shim = Shim(path)
    try:
        init = shim.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {},
                                       "clientInfo": {"name": "bridge-probe", "version": "0"}})
        shim._send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        names = [tool["name"] for tool in shim.rpc("tools/list").get("tools", [])]
    finally:
        shim.close()
    present = {family_of(name) for name in names}
    return init["serverInfo"]["name"], [family for family in FAMILIES if family in present]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("shim")
    parser.add_argument("--expect", default=None, help="comma-separated families the shim must advertise")
    args = parser.parse_args(argv)
    server, families = advertised(args.shim)
    print(f"server={server} families={','.join(families)}")
    if args.expect is not None and families != [f for f in args.expect.split(",") if f]:
        print(f"bridge-probe: expected families {args.expect}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
