#!/usr/bin/env python3
"""buzz-team/buzz-team-mcp.py: the one stdio MCP bridge every buzz-agent@* spawns.

Run against a stub qmd (BUZZ_QMD_MCP_COMMAND) and a stub Brave daemon (BUZZ_BRAVE_MCP_URL),
so nothing here touches the live index, the broker socket or Brave's quota. Anchors are the
`::` comments; tests/test_buzz_team_mcp.sh is the gate entry point.
"""

from __future__ import annotations

import json
import os
import pathlib
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "buzz-team" / "buzz-team-mcp.py"
FIX = ROOT / "tests" / "fixtures" / "buzz-team-mcp"
BRAVE_OFFERED = ["brave_web_search", "brave_news_search", "brave_llm_context", "brave_summarizer"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Bridge:
    def __init__(self, brave_url: str):
        env = dict(os.environ, BUZZ_QMD_MCP_COMMAND=str(FIX / "qmd-stub.py"), BUZZ_BRAVE_MCP_URL=brave_url,
                   BUZZ_NOTION_SOCKET="/nonexistent/buzz-notion.sock")
        self.proc = subprocess.Popen([sys.executable, str(BRIDGE)], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                     stderr=subprocess.PIPE, text=True, bufsize=1, env=env)
        self.n = 0

    def rpc(self, method: str, params: dict | None = None) -> dict:
        self.n += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        while True:
            line = self.proc.stdout.readline()
            if not line:
                raise AssertionError("bridge closed: " + self.proc.stderr.read())
            msg = json.loads(line)
            if msg.get("id") == self.n:
                return msg

    def start(self) -> dict:
        init = self.rpc("initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}})
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}) + "\n")
        self.proc.stdin.flush()
        return init

    def call(self, name: str, args: dict) -> dict:
        return self.rpc("tools/call", {"name": name, "arguments": args})["result"]

    def close(self) -> str:
        self.proc.stdin.close()
        self.proc.wait(timeout=10)
        stderr = self.proc.stderr.read()
        self.proc.stdout.close()
        self.proc.stderr.close()
        return stderr


class BraveStub:
    def __init__(self, tmp: pathlib.Path):
        self.port = free_port()
        self.log = tmp / "brave.log"
        self.url = f"http://127.0.0.1:{self.port}/mcp"
        self.proc = None
        self.start()

    def start(self):
        self.proc = subprocess.Popen([sys.executable, str(FIX / "brave-stub.py"), str(self.port), str(self.log)])
        for _ in range(100):
            try:
                socket.create_connection(("127.0.0.1", self.port), timeout=0.2).close()
                return
            except OSError:
                time.sleep(0.05)
        raise AssertionError("brave stub did not come up")

    def stop(self):
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
            self.proc.wait(timeout=5)

    def requests(self) -> list[dict]:
        if not self.log.exists():
            return []
        return [json.loads(l) for l in self.log.read_text().splitlines() if l.strip()]


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="buzz-team-mcp-"))
        self.brave = BraveStub(self.tmp)
        self.addCleanup(self.brave.stop)

    def test_tools_list_is_qmd_plus_notion_plus_brave(self):
        # (::bridge-tools-list-composite) — one server, three sources, and only the four search
        # tools from the daemon's eight
        bridge = Bridge(self.brave.url)
        init = bridge.start()
        self.assertEqual(init["result"]["serverInfo"]["name"], "praetorium-buzz")
        self.assertIn("LEAVES the box", init["result"]["instructions"])
        names = [t["name"] for t in bridge.rpc("tools/list")["result"]["tools"]]
        self.assertEqual(names[:2], ["query", "status"])
        self.assertIn("notion_query_data_source", names)
        self.assertEqual([n for n in names if n.startswith("brave_")], BRAVE_OFFERED)
        self.assertNotIn("brave_image_search", names)
        # the schema is the daemon's, not a static copy
        web = next(t for t in bridge.rpc("tools/list")["result"]["tools"] if t["name"] == "brave_web_search")
        self.assertIn("freshness", web["inputSchema"]["properties"])
        bridge.close()

    def test_brave_call_is_forwarded_under_one_session(self):
        # (::bridge-brave-call-forwarded) — initialize once, then every call carries the
        # daemon's session id; the daemon's result comes back untouched
        bridge = Bridge(self.brave.url)
        bridge.start()
        bridge.rpc("tools/list")
        result = bridge.call("brave_web_search", {"query": "cold chain logistics", "count": 3})
        self.assertFalse(result.get("isError"))
        self.assertEqual(json.loads(result["content"][0]["text"]), {"tool": "brave_web_search", "echo": {"query": "cold chain logistics", "count": 3}})
        bridge.call("brave_news_search", {"query": "port strike"})
        seen = self.brave.requests()
        self.assertEqual([r["method"] for r in seen].count("initialize"), 1)
        sessions = {r["session"] for r in seen if r["method"] != "initialize"}
        self.assertEqual(len(sessions), 1)
        self.assertIsNotNone(next(iter(sessions)))
        bridge.close()

    def test_unoffered_brave_tool_is_refused_at_the_bridge(self):
        # (::bridge-brave-allowlist) — a name the daemon knows but the fleet is not offered
        # never reaches the daemon
        bridge = Bridge(self.brave.url)
        bridge.start()
        result = bridge.call("brave_image_search", {"query": "x"})
        self.assertTrue(result["isError"])
        self.assertIn("not offered to this fleet", result["content"][0]["text"])
        self.assertEqual([r for r in self.brave.requests() if r["method"] == "tools/call"], [])
        bridge.close()

    def test_daemon_down_costs_one_tool_error_never_the_bridge(self):
        # (::bridge-brave-daemon-down) — with nothing listening, the tools are still advertised
        # (static schema, said so on stderr), a call fails naming the daemon, and qmd and Notion
        # keep answering
        self.brave.stop()
        bridge = Bridge(self.brave.url)
        bridge.start()
        names = [t["name"] for t in bridge.rpc("tools/list")["result"]["tools"]]
        self.assertEqual([n for n in names if n.startswith("brave_")], BRAVE_OFFERED)
        result = bridge.call("brave_web_search", {"query": "anything"})
        self.assertTrue(result["isError"])
        self.assertIn("brave-mcp.service is unreachable", result["content"][0]["text"])
        self.assertIn(self.brave.url, result["content"][0]["text"])
        self.assertEqual(bridge.call("query", {"q": "x"})["content"][0]["text"], "qmd answered query")
        self.assertTrue(bridge.call("notion_status", {})["isError"])  # the broker socket is a fixture path
        stderr = bridge.close()
        self.assertIn("advertising the static Brave schema", stderr)

    def test_daemon_restart_reestablishes_the_session(self):
        # (::bridge-brave-session-recovery) — the real daemon forgets every session on restart
        # and answers 404; the bridge re-initialises once and the call succeeds
        bridge = Bridge(self.brave.url)
        bridge.start()
        bridge.call("brave_web_search", {"query": "one"})
        self.brave.stop()
        self.brave.start()
        result = bridge.call("brave_web_search", {"query": "two"})
        self.assertFalse(result.get("isError"), result)
        self.assertEqual(json.loads(result["content"][0]["text"])["echo"]["query"], "two")
        methods = [r["method"] for r in self.brave.requests()]
        self.assertEqual(methods.count("initialize"), 2)  # one per daemon life, the second forced by the 404
        self.assertEqual(methods.count("tools/call"), 3)  # before the restart, the attempt the daemon 404'd, the retry
        bridge.close()


if __name__ == "__main__":
    unittest.main()
