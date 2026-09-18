#!/usr/bin/env python3
"""A stdio MCP server standing in for ~/.local/bin/qmd-mcp: two tools, echoes calls."""
import json
import sys

TOOLS = [{"name": "query", "inputSchema": {"type": "object"}}, {"name": "status", "inputSchema": {"type": "object"}}]
for line in sys.stdin:
    req = json.loads(line)
    if req.get("id") is None:
        continue
    method = req["method"]
    if method == "initialize":
        result = {"protocolVersion": "2025-03-26", "capabilities": {"tools": {}},
                  "serverInfo": {"name": "qmd-stub", "version": "0"}, "instructions": "qmd stub."}
    elif method == "tools/list":
        result = {"tools": TOOLS}
    elif method == "tools/call":
        result = {"content": [{"type": "text", "text": "qmd answered " + req["params"]["name"]}]}
    else:
        result = {}
    sys.stdout.write(json.dumps({"jsonrpc": "2.0", "id": req["id"], "result": result}) + "\n")
    sys.stdout.flush()
