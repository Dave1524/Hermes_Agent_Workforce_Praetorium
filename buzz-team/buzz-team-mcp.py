#!/usr/bin/env python3
"""Composite MCP server for the Buzz fleet.

The Buzz harness accepts one stdio MCP command. This process preserves the
existing qmd server by proxying its JSON-RPC stream, and adds a small Notion
REST surface. It holds no credential: the agent spawns this process, so for
augustus it runs inside codex-acp's bwrap namespace where
`~/.config/agent-workforce` is a tmpfs. Notion calls are forwarded to
buzz-notion-broker.py over a unix socket; the token and the write policy live
out there, on the host side of the namespace.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
from typing import Any


QMD_COMMAND = [os.path.expanduser("~/.local/bin/qmd-mcp")]
NOTION_SOCKET = os.environ.get(
    "BUZZ_NOTION_SOCKET",
    f"/run/user/{os.getuid()}/buzz-notion.sock",
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


def main() -> int:
    qmd = QmdProxy()
    notion_names = {tool["name"] for tool in NOTION_TOOLS}
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
                        result["serverInfo"] = {"name": "praetorium-buzz", "version": "1.0.0"}
                        result["instructions"] = (
                            result.get("instructions", "")
                            + "\n\nNotion: use notion_search, notion_fetch, and "
                            "notion_query_data_source for content shared with the dedicated "
                            "Buzz integration. Write only when Dave's request and your charter permit it."
                        )
                    emit(response)
                    continue

                if method == "tools/list":
                    response = qmd.request(request)
                    if "result" in response:
                        response["result"].setdefault("tools", []).extend(NOTION_TOOLS)
                    emit(response)
                    continue

                if method == "tools/call":
                    params = request.get("params") or {}
                    name = params.get("name", "")
                    if name in notion_names:
                        try:
                            value = notion_tool(name, params.get("arguments") or {})
                            result = tool_result(value)
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
