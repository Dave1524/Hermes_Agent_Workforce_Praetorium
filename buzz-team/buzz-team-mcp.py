#!/usr/bin/env python3
"""Composite MCP server for the Buzz fleet.

The Buzz harness accepts one stdio MCP command. This process preserves the
existing qmd server by proxying its JSON-RPC stream, adds a small Notion
REST surface, and forwards web search to brave-mcp.service. It holds no
credential: the agent spawns this process, so for augustus it runs inside
codex-acp's bwrap namespace where `~/.config/agent-workforce` is a tmpfs.
Notion calls are forwarded to buzz-notion-broker.py over a unix socket; Brave
calls to the daemon on 127.0.0.1:8766 (streamable HTTP), which holds the API
key in its own EnvironmentFile. Token, key and write policy all live out
there, on the host side of the namespace.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from typing import Any


QMD_COMMAND = [os.environ.get("BUZZ_QMD_MCP_COMMAND") or os.path.expanduser("~/.local/bin/qmd-mcp")]
NOTION_SOCKET = os.environ.get(
    "BUZZ_NOTION_SOCKET",
    f"/run/user/{os.getuid()}/buzz-notion.sock",
)
BRAVE_URL = os.environ.get("BUZZ_BRAVE_MCP_URL", "http://127.0.0.1:8766/mcp")
# The daemon offers eight tools; these four are search. local/place need a Pro plan,
# image/video are not this fleet's work.
BRAVE_TOOLS = ("brave_web_search", "brave_news_search", "brave_llm_context", "brave_summarizer")
# qmd's own tools, proxied from its tools/list; named here so a per-agent deny list can be
# rendered for them (bin/fleet_capabilities.py) — the filter below treats every proxied
# tool as this family, so a new qmd tool is filtered even before it is named here.
QMD_TOOLS = ("query", "get", "multi_get", "status")
# The three families a shim may advertise (`--tools qmd,notion,brave`). A manifest's
# bridge_tools names families, never tools; the tool names are this file's.
FAMILIES = ("qmd", "notion", "brave")
BRAVE_RULE = (
    "Web: brave_web_search, brave_news_search, brave_llm_context (grounding snippets) and "
    "brave_summarizer, via brave-mcp.service. A query string LEAVES the box (Brave Software, "
    "US): public names and generic terms only, never client-identifiable strings, deal "
    "specifics or internal reasoning (docs/data_boundary.md, NUC-21). Free tier: 2,000 "
    "queries/month, 1/sec."
)


NOTION_TOOLS: list[dict[str, Any]] = [
    {
        "name": "notion_status",
        "title": "Notion Connection Status",
        "description": (
            "Verify that the dedicated Buzz Notion integration can authenticate. "
            "Returns no token or workspace content."
        ),
        "inputSchema": {"type": "object", "properties": {}},
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "notion_search",
        "title": "Search Notion",
        "description": (
            "Search pages and data sources shared with the Buzz Notion integration. "
            "Use notion_fetch or notion_query_data_source on returned IDs."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "object_type": {
                    "type": "string",
                    "enum": ["page", "data_source"],
                    "description": "Optional result type filter.",
                },
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "start_cursor": {"type": "string"},
            },
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "notion_fetch",
        "title": "Fetch Notion Object",
        "description": (
            "Fetch a page, database, data source, or one page of a block's children. "
            "For page content, fetch the page ID again with object_type=block_children."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "id": {"type": "string"},
                "object_type": {
                    "type": "string",
                    "enum": ["page", "database", "data_source", "block_children"],
                },
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "start_cursor": {"type": "string"},
            },
            "required": ["id", "object_type"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "notion_query_data_source",
        "title": "Query Notion Data Source",
        "description": (
            "Query a Notion data source shared with the integration. Pass native "
            "Notion REST filter and sorts objects when filtering is needed."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "data_source_id": {"type": "string"},
                "filter": {"type": "object"},
                "sorts": {"type": "array", "items": {"type": "object"}},
                "page_size": {"type": "integer", "minimum": 1, "maximum": 100},
                "start_cursor": {"type": "string"},
            },
            "required": ["data_source_id"],
        },
        "annotations": {"readOnlyHint": True, "openWorldHint": False},
    },
    {
        "name": "notion_create_page",
        "title": "Create Notion Page",
        "description": (
            "Create a page under a shared page or data source using native Notion REST "
            "parent, properties, and optional children/icon/cover objects."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "parent": {"type": "object"},
                "properties": {"type": "object"},
                "children": {"type": "array", "items": {"type": "object"}},
                "icon": {"type": "object"},
                "cover": {"type": "object"},
            },
            "required": ["parent", "properties"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "notion_update_page",
        "title": "Update Notion Page",
        "description": (
            "Update properties, icon, or cover on a shared Notion page. Archiving and "
            "moving pages to trash are deliberately blocked."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "page_id": {"type": "string"},
                "properties": {"type": "object"},
                "icon": {"type": ["object", "null"]},
                "cover": {"type": ["object", "null"]},
            },
            "required": ["page_id"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
    {
        "name": "notion_append_blocks",
        "title": "Append Notion Blocks",
        "description": (
            "Append native Notion block objects to a shared page or block. Existing "
            "content is not replaced or deleted."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "block_id": {"type": "string"},
                "children": {"type": "array", "items": {"type": "object"}},
                "after": {"type": "string"},
            },
            "required": ["block_id", "children"],
        },
        "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False},
    },
]
NOTION_NAMES = [tool["name"] for tool in NOTION_TOOLS]


def emit(message: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
    sys.stdout.flush()


def tool_result(value: Any, *, is_error: bool = False) -> dict[str, Any]:
    text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
    result: dict[str, Any] = {"content": [{"type": "text", "text": text}]}
    if is_error:
        result["isError"] = True
    return result


def notion_tool(name: str, args: dict[str, Any]) -> Any:
    request = json.dumps({"tool": name, "arguments": args}, separators=(",", ":"))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
            client.settimeout(60)
            client.connect(NOTION_SOCKET)
            client.sendall(request.encode("utf-8") + b"\n")
            client.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = client.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
    except OSError as exc:
        raise RuntimeError(f"Buzz Notion broker is unreachable: {exc}") from exc
    if not chunks:
        raise RuntimeError("Buzz Notion broker closed the connection without answering")
    response = json.loads(b"".join(chunks).decode("utf-8"))
    if not response.get("ok"):
        raise RuntimeError(str(response.get("error", "Notion broker reported an unknown error")))
    return response.get("value")


class BraveProxy:
    """Streamable-HTTP client for brave-mcp.service, initialised on first use.

    Lazy on purpose: a daemon that is down costs the agent one named tool error, never the
    bridge — qmd and Notion keep working. The tool schemas are taken from the daemon when it
    answers, so they are exact; when it does not, a minimal static schema is advertised so
    the tools still exist to be called and to fail with the daemon's name in the message.
    """

    def __init__(self, url: str) -> None:
        self.url = url
        self.session_id: str | None = None

    def _post(self, body: dict[str, Any]) -> list[dict[str, Any]]:
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session_id:
            headers["mcp-session-id"] = self.session_id
        request = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
        with urllib.request.urlopen(request, timeout=90) as response:
            self.session_id = response.headers.get("mcp-session-id") or self.session_id
            raw = response.read().decode("utf-8")
            content_type = response.headers.get("content-type", "")
        if not raw.strip():
            return []
        if content_type.startswith("text/event-stream"):
            return [json.loads(line[6:]) for line in raw.splitlines() if line.startswith("data: ")]
        parsed = json.loads(raw)
        return parsed if isinstance(parsed, list) else [parsed]

    def _connect(self) -> None:
        if self.session_id:
            return
        self._post({"jsonrpc": "2.0", "id": "brave-init", "method": "initialize", "params": {
            "protocolVersion": "2025-03-26", "capabilities": {},
            "clientInfo": {"name": "praetorium-buzz", "version": "1.1.0"}}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})

    def _request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        for attempt in (1, 2):
            try:
                self._connect()
                messages = self._post({"jsonrpc": "2.0", "id": f"brave-{method}", "method": method, "params": params})
            except urllib.error.HTTPError as exc:
                if exc.code in (400, 404) and attempt == 1:  # the daemon restarted: our session is gone
                    self.session_id = None
                    continue
                raise RuntimeError(f"brave-mcp.service at {self.url} answered HTTP {exc.code}") from exc
            except (urllib.error.URLError, OSError, ValueError) as exc:
                self.session_id = None
                raise RuntimeError(f"brave-mcp.service is unreachable at {self.url}: {exc}") from exc
            replies = [m for m in messages if m.get("id") == f"brave-{method}"]
            if not replies:
                raise RuntimeError(f"brave-mcp.service returned no reply to {method}")
            if "error" in replies[-1]:
                raise RuntimeError(str(replies[-1]["error"].get("message", replies[-1]["error"])))
            return replies[-1].get("result") or {}
        raise RuntimeError(f"brave-mcp.service at {self.url}: session could not be re-established")

    def tools(self) -> list[dict[str, Any]]:
        try:
            live = self._request("tools/list", {}).get("tools", [])
            by_name = {tool.get("name"): tool for tool in live if isinstance(tool, dict)}
            if all(name in by_name for name in BRAVE_TOOLS):
                return [by_name[name] for name in BRAVE_TOOLS]
            missing = [name for name in BRAVE_TOOLS if name not in by_name]
            print(f"buzz-team-mcp: brave daemon lacks {missing}; advertising the static schema", file=sys.stderr)
        except RuntimeError as exc:
            print(f"buzz-team-mcp: {exc}; advertising the static Brave schema", file=sys.stderr)
        return [self._static_tool(name) for name in BRAVE_TOOLS]

    @staticmethod
    def _static_tool(name: str) -> dict[str, Any]:
        key = "key" if name == "brave_summarizer" else "query"
        return {
            "name": name,
            "description": f"{name} via brave-mcp.service (schema unavailable at startup — the daemon was not answering). " + BRAVE_RULE,
            "inputSchema": {"type": "object", "properties": {key: {"type": "string"}, "count": {"type": "integer"}}, "required": [key]},
            "annotations": {"readOnlyHint": True, "openWorldHint": True},
        }

    def call(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
        if name not in BRAVE_TOOLS:
            raise RuntimeError(f"{name} is not offered to this fleet — the bridge forwards only {', '.join(BRAVE_TOOLS)}")
        return self._request("tools/call", {"name": name, "arguments": args})


class QmdProxy:
    def __init__(self) -> None:
        self.process = subprocess.Popen(
            QMD_COMMAND,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=sys.stderr,
            text=True,
            bufsize=1,
        )

    def notify(self, request: dict[str, Any]) -> None:
        if self.process.poll() is not None or self.process.stdin is None:
            return
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()

    def request(self, request: dict[str, Any]) -> dict[str, Any]:
        if self.process.poll() is not None:
            raise RuntimeError("qmd MCP subprocess is not running")
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps(request, separators=(",", ":")) + "\n")
        self.process.stdin.flush()
        request_id = request.get("id")
        while True:
            line = self.process.stdout.readline()
            if not line:
                raise RuntimeError("qmd MCP subprocess closed its output")
            response = json.loads(line)
            if response.get("id") == request_id:
                return response
            emit(response)

    def close(self) -> None:
        if self.process.poll() is None:
            self.process.terminate()


def family_of(name: str) -> str:
    if name in NOTION_NAMES:
        return "notion"
    if name.startswith("brave_"):
        return "brave"
    return "qmd"


def family_tools(family: str) -> tuple[str, ...]:
    """The tool names a family denies when a shim leaves it out — one owner for the
    renderer's deny list and the filter's refusal."""
    if family == "notion":
        return tuple(NOTION_NAMES)
    if family == "brave":
        return BRAVE_TOOLS
    return QMD_TOOLS


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", default=None,
                        help="the buzz-agent this bridge serves; goes into serverInfo (the shim passes it)")
    parser.add_argument("--tools", default=",".join(FAMILIES),
                        help="comma-separated families to advertise, of qmd,notion,brave (default: all)")
    args = parser.parse_args(argv)
    args.families = tuple(f for f in args.tools.split(",") if f)
    unknown = [f for f in args.families if f not in FAMILIES]
    if unknown:
        parser.error(f"--tools names no family: {', '.join(unknown)} (families: {', '.join(FAMILIES)})")
    return args


def instructions_for(families: tuple[str, ...], qmd_text: str) -> str:
    text = qmd_text
    if "notion" in families:
        text += ("\n\nNotion: use notion_search, notion_fetch, and notion_query_data_source for "
                 "content shared with the dedicated Buzz integration. Write only when Dave's "
                 "request and your charter permit it.")
    if "brave" in families:
        text += "\n\n" + BRAVE_RULE
    return text


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    families = args.families
    server_name = f"buzz-team-mcp-{args.agent}" if args.agent else "praetorium-buzz"
    qmd = QmdProxy()
    brave = BraveProxy(BRAVE_URL)
    try:
        for line in sys.stdin:
            try:
                request = json.loads(line)
                method = request.get("method")
                request_id = request.get("id")

                if request_id is None:
                    qmd.notify(request)
                    continue

                if method == "initialize":
                    response = qmd.request(request)
                    if "result" in response:
                        result = response["result"]
                        result["serverInfo"] = {"name": server_name, "version": "1.2.0"}
                        result["instructions"] = instructions_for(families, result.get("instructions", ""))
                    emit(response)
                    continue

                if method == "tools/list":
                    response = qmd.request(request)
                    if "result" in response:
                        tools = response["result"].setdefault("tools", [])
                        if "notion" in families:
                            tools.extend(NOTION_TOOLS)
                        if "brave" in families:
                            tools.extend(brave.tools())
                        response["result"]["tools"] = [t for t in tools if family_of(t["name"]) in families]
                    emit(response)
                    continue

                if method == "tools/call":
                    params = request.get("params") or {}
                    name = params.get("name", "")
                    family = family_of(name)
                    if family not in families:
                        emit({"jsonrpc": "2.0", "id": request_id, "result": tool_result(
                            f"{name} is not offered to {args.agent or 'this agent'} — the bridge "
                            f"advertises {', '.join(families)} only", is_error=True)})
                    elif family == "notion":
                        try:
                            value = notion_tool(name, params.get("arguments") or {})
                            result = tool_result(value)
                        except Exception as exc:
                            result = tool_result(str(exc), is_error=True)
                        emit({"jsonrpc": "2.0", "id": request_id, "result": result})
                    elif family == "brave":
                        try:
                            result = brave.call(name, params.get("arguments") or {})
                        except Exception as exc:
                            result = tool_result(str(exc), is_error=True)
                        emit({"jsonrpc": "2.0", "id": request_id, "result": result})
                    else:
                        emit(qmd.request(request))
                    continue

                emit(qmd.request(request))
            except Exception as exc:
                emit(
                    {
                        "jsonrpc": "2.0",
                        "id": request.get("id") if isinstance(request, dict) else None,
                        "error": {"code": -32603, "message": str(exc)},
                    }
                )
    finally:
        qmd.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
