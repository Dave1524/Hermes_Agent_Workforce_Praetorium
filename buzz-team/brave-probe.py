#!/usr/bin/env python3
"""Round-trip brave-mcp.service. Exits 0 when the daemon offers the four tools the bridge forwards.

Its own file so verify-fleet.sh can run it unchanged on the host and inside an agent's bwrap
namespace via nsenter — the two places that can disagree (notion-probe.py, 2026-08-10).
initialize + tools/list only: no query leaves the box and no search quota is spent.
The daemon holds the API key; nothing here can see it.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request

BRAVE_URL = os.environ.get("BUZZ_BRAVE_MCP_URL", "http://127.0.0.1:8766/mcp")
FORWARDED = {"brave_web_search", "brave_news_search", "brave_llm_context", "brave_summarizer"}
HEADERS = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}


def post(body: dict, session_id: str | None) -> tuple[list[dict], str | None]:
    headers = dict(HEADERS)
    if session_id:
        headers["mcp-session-id"] = session_id
    request = urllib.request.Request(BRAVE_URL, data=json.dumps(body).encode("utf-8"), headers=headers)
    with urllib.request.urlopen(request, timeout=30) as response:
        raw = response.read().decode("utf-8")
        sid = response.headers.get("mcp-session-id") or session_id
    if response.headers.get("Content-Type", "").startswith("text/event-stream"):
        return [json.loads(line[5:]) for line in raw.splitlines() if line.startswith("data:")], sid
    return [json.loads(raw)] if raw.strip() else [], sid


def offered_tools() -> set[str]:
    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
        "protocolVersion": "2025-03-26", "capabilities": {},
        "clientInfo": {"name": "brave-probe", "version": "1"}}}
    _, sid = post(init, None)
    post({"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
    replies, _ = post({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}}, sid)
    for reply in replies:
        if reply.get("id") == 2:
            return {t["name"] for t in reply.get("result", {}).get("tools", [])}
    return set()


def main() -> int:
    try:
        tools = offered_tools()
    except (urllib.error.URLError, OSError, ValueError) as exc:
        print(f"brave-mcp unreachable at {BRAVE_URL}: {exc}", file=sys.stderr)
        return 1
    missing = sorted(FORWARDED - tools)
    print(json.dumps({"url": BRAVE_URL, "tools": len(tools), "missing": missing}))
    return 1 if missing else 0


if __name__ == "__main__":
    raise SystemExit(main())
