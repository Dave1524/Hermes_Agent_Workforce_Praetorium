#!/usr/bin/env python3
"""A streamable-HTTP MCP server standing in for brave-mcp.service.

    brave-stub.py <port> <log>   — serves /mcp; appends one JSON line per request to <log>.

Speaks the daemon's dialect: initialize answers with an mcp-session-id header, every later
request must carry it (404 otherwise, which is what the real daemon does after a restart),
and results come back as SSE `data:` frames. Offers the daemon's eight tools.
"""
import json
import sys
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

PORT, LOG = int(sys.argv[1]), sys.argv[2]
NAMES = ["brave_web_search", "brave_local_search", "brave_video_search", "brave_image_search",
         "brave_news_search", "brave_summarizer", "brave_llm_context", "brave_place_search"]
SESSIONS = set()


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        sid = self.headers.get("mcp-session-id")
        with open(LOG, "a") as log:
            log.write(json.dumps({"method": body.get("method"), "session": sid, "params": body.get("params")}) + "\n")
        if body.get("method") == "initialize":
            sid = str(uuid.uuid4()); SESSIONS.add(sid)
            return self._reply(body, {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                                      "serverInfo": {"name": "brave-stub", "version": "0"}}, sid)
        if sid not in SESSIONS:
            self.send_response(404); self.end_headers(); return
        if body.get("id") is None:
            self.send_response(202); self.end_headers(); return
        if body["method"] == "tools/list":
            return self._reply(body, {"tools": [{"name": n, "description": f"{n} from the daemon",
                                                 "inputSchema": {"type": "object", "properties": {"query": {"type": "string"}, "freshness": {"type": "string"}}}} for n in NAMES]}, sid)
        if body["method"] == "tools/call":
            name = body["params"]["name"]
            return self._reply(body, {"content": [{"type": "text", "text": json.dumps({"tool": name, "echo": body["params"].get("arguments")})}]}, sid)
        return self._reply(body, {}, sid)

    def _reply(self, body, result, sid):
        payload = ("event: message\ndata: " + json.dumps({"jsonrpc": "2.0", "id": body.get("id"), "result": result}) + "\n\n").encode()
        self.send_response(200)
        self.send_header("content-type", "text/event-stream")
        self.send_header("mcp-session-id", sid)
        self.send_header("content-length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
