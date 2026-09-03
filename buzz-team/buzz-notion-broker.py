#!/usr/bin/env python3
"""Notion credential + policy broker for the Buzz fleet.

`buzz-team-mcp.py` is spawned by the *agent*, not by buzz-acp. For the three
claude-agent-acp agents that lands on the host namespace, but codex-acp runs
inside the bwrap mount namespace of /usr/local/bin/codex-acp, so augustus's copy
of the bridge inherits `--tmpfs ~/.config/agent-workforce` and cannot see
notion-buzz.env at all.

Handing the token into that namespace would defeat the namespace: anything the
bridge can read there, the agent's own shell can read too. So the token stays
out here, and the bridge becomes transport. This process owns both the
credential and the write policy — the archiving/trash refusal and the id and
page-size validation are enforced on this side of the namespace, where an agent
cannot route around them by talking to the socket directly.
"""

from __future__ import annotations

import json
import os
import re
import socketserver
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any


NOTION_ENV_FILE = os.environ.get(
    "NOTION_BUZZ_ENV_FILE",
    os.path.expanduser("~/.config/agent-workforce/notion-buzz.env"),
)
SOCKET_PATH = os.environ.get(
    "BUZZ_NOTION_SOCKET",
    f"/run/user/{os.getuid()}/buzz-notion.sock",
)
NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
NOTION_ID = re.compile(r"^[0-9a-fA-F-]{32,36}$")
MAX_REQUEST_BYTES = 4 * 1024 * 1024
MAX_RESPONSE_BYTES = 4 * 1024 * 1024


def load_notion_token() -> str:
    token = ""
    try:
        with open(NOTION_ENV_FILE, encoding="utf-8") as handle:
            for raw_line in handle:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, value = line.split("=", 1)
                if key.strip() == "NOTION_API_TOKEN":
                    token = value.strip().strip('"').strip("'")
    except OSError as exc:
        raise RuntimeError("Buzz Notion credential file is unavailable") from exc
    if not token:
        raise RuntimeError("NOTION_API_TOKEN is missing from the Buzz credential file")
    return token


def valid_id(value: Any, label: str) -> str:
    value = str(value or "")
    if not NOTION_ID.fullmatch(value):
        raise ValueError(f"{label} must be a Notion UUID")
    return value


def page_size(value: Any, default: int = 20) -> int:
    if value is None:
        return default
    number = int(value)
    if not 1 <= number <= 100:
        raise ValueError("page_size must be between 1 and 100")
    return number


def notion_request(method: str, path: str, payload: Any = None) -> Any:
    token = load_notion_token()
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = urllib.request.Request(
        NOTION_API + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
            "User-Agent": "praetorium-buzz-notion-bridge/1.0",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read(MAX_RESPONSE_BYTES + 1)
            if len(body) > MAX_RESPONSE_BYTES:
                raise RuntimeError("Notion response exceeded the 4 MiB bridge limit")
            return json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read(4096).decode("utf-8", errors="replace")
        try:
            detail = json.loads(body).get("message", body)
        except json.JSONDecodeError:
            detail = body
        raise RuntimeError(f"Notion API returned HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Notion API network error: {exc.reason}") from exc


def status(_args: dict[str, Any]) -> Any:
    notion_request("GET", "/users/me")
    return {"authenticated": True, "notion_version": NOTION_VERSION}


def search(args: dict[str, Any]) -> Any:
    payload: dict[str, Any] = {"page_size": page_size(args.get("page_size"))}
    if args.get("query"):
        payload["query"] = str(args["query"])
    if args.get("object_type"):
        payload["filter"] = {"property": "object", "value": args["object_type"]}
    if args.get("start_cursor"):
        payload["start_cursor"] = str(args["start_cursor"])
    return notion_request("POST", "/search", payload)


def fetch(args: dict[str, Any]) -> Any:
    object_id = valid_id(args.get("id"), "id")
    object_type = args.get("object_type")
    if object_type == "page":
        return notion_request("GET", f"/pages/{object_id}")
    if object_type == "database":
        return notion_request("GET", f"/databases/{object_id}")
    if object_type == "data_source":
        return notion_request("GET", f"/data_sources/{object_id}")
    if object_type == "block_children":
        query = {"page_size": page_size(args.get("page_size"), 100)}
        if args.get("start_cursor"):
            query["start_cursor"] = str(args["start_cursor"])
        return notion_request("GET", f"/blocks/{object_id}/children?{urllib.parse.urlencode(query)}")
    raise ValueError("unsupported object_type")


def query_data_source(args: dict[str, Any]) -> Any:
    source_id = valid_id(args.get("data_source_id"), "data_source_id")
    payload: dict[str, Any] = {"page_size": page_size(args.get("page_size"), 100)}
    for key in ("filter", "sorts", "start_cursor"):
        if args.get(key) is not None:
            payload[key] = args[key]
    return notion_request("POST", f"/data_sources/{source_id}/query", payload)


def create_page(args: dict[str, Any]) -> Any:
    payload = {"parent": args.get("parent"), "properties": args.get("properties")}
    if not isinstance(payload["parent"], dict) or not isinstance(payload["properties"], dict):
        raise ValueError("parent and properties must be objects")
    for key in ("children", "icon", "cover"):
        if args.get(key) is not None:
            payload[key] = args[key]
    return notion_request("POST", "/pages", payload)


def update_page(args: dict[str, Any]) -> Any:
    page_id = valid_id(args.get("page_id"), "page_id")
    if "archived" in args or "in_trash" in args:
        raise ValueError("archiving and trash operations are not exposed by this bridge")
    payload = {key: args[key] for key in ("properties", "icon", "cover") if key in args}
    if not payload:
        raise ValueError("provide properties, icon, or cover")
    return notion_request("PATCH", f"/pages/{page_id}", payload)


def append_blocks(args: dict[str, Any]) -> Any:
    block_id = valid_id(args.get("block_id"), "block_id")
    children = args.get("children")
    if not isinstance(children, list) or not children:
        raise ValueError("children must be a non-empty array")
    payload: dict[str, Any] = {"children": children}
    if args.get("after"):
        payload["after"] = valid_id(args["after"], "after")
    return notion_request("PATCH", f"/blocks/{block_id}/children", payload)


HANDLERS = {
    "notion_status": status,
    "notion_search": search,
    "notion_fetch": fetch,
    "notion_query_data_source": query_data_source,
    "notion_create_page": create_page,
    "notion_update_page": update_page,
    "notion_append_blocks": append_blocks,
}


def dispatch(request: dict[str, Any]) -> dict[str, Any]:
    tool = request.get("tool")
    handler = HANDLERS.get(str(tool))
    if handler is None:
        return {"ok": False, "error": f"unknown Notion tool: {tool}"}
    arguments = request.get("arguments") or {}
    if not isinstance(arguments, dict):
        return {"ok": False, "error": "arguments must be an object"}
    try:
        return {"ok": True, "value": handler(arguments)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


class Handler(socketserver.StreamRequestHandler):
    timeout = 60

    def handle(self) -> None:
        line = self.rfile.readline(MAX_REQUEST_BYTES + 1)
        if not line or len(line) > MAX_REQUEST_BYTES:
            return
        try:
            request = json.loads(line)
        except json.JSONDecodeError as exc:
            response: dict[str, Any] = {"ok": False, "error": f"malformed request: {exc}"}
        else:
            response = dispatch(request) if isinstance(request, dict) else {
                "ok": False,
                "error": "request must be an object",
            }
        self.wfile.write(json.dumps(response, separators=(",", ":")).encode("utf-8") + b"\n")


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True
    allow_reuse_address = True


def main() -> int:
    load_notion_token()
    if os.path.exists(SOCKET_PATH):
        os.unlink(SOCKET_PATH)
    previous = os.umask(0o177)
    try:
        server = Server(SOCKET_PATH, Handler)
    finally:
        os.umask(previous)
    print(f"buzz-notion-broker listening on {SOCKET_PATH}", file=sys.stderr, flush=True)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if os.path.exists(SOCKET_PATH):
            os.unlink(SOCKET_PATH)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
