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
BOARD_OFFERED = ["board_list", "board_get", "board_create", "board_brief", "board_note"]
BRAVE_OFFERED = ["brave_web_search", "brave_news_search", "brave_llm_context", "brave_summarizer"]


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Bridge:
    def __init__(self, brave_url: str, *args: str, **extra_env: str):
        env = dict(os.environ, BUZZ_QMD_MCP_COMMAND=str(FIX / "qmd-stub.py"), BUZZ_BRAVE_MCP_URL=brave_url,
                   BUZZ_NOTION_SOCKET="/nonexistent/buzz-notion.sock",
                   BUZZ_BOARD_COMMAND=str(FIX / "board-stub.py"), **extra_env)
        self.proc = subprocess.Popen([sys.executable, str(BRIDGE), *args], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
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

    def test_shim_families_filter_the_list_and_refuse_the_call(self):
        # (::bridge-tools-filter) — `--agent aurelian --tools qmd,brave` is the rendered
        # aurelian shim: the list carries no notion_*, a notion call is one tool error naming
        # the agent and the families, and the instructions drop the Notion paragraph. The
        # families it does carry are unchanged: qmd's tools and the four brave_* search tools.
        bridge = Bridge(self.brave.url, "--agent", "aurelian", "--tools", "qmd,brave")
        init = bridge.start()
        self.assertEqual(init["result"]["serverInfo"]["name"], "buzz-team-mcp-aurelian")
        self.assertNotIn("Notion:", init["result"]["instructions"])
        self.assertIn("LEAVES the box", init["result"]["instructions"])
        names = [t["name"] for t in bridge.rpc("tools/list")["result"]["tools"]]
        self.assertEqual([n for n in names if n.startswith("notion_")], [])
        self.assertEqual(names[:2], ["query", "status"])
        self.assertEqual([n for n in names if n.startswith("brave_")], BRAVE_OFFERED)
        refused = bridge.call("notion_search", {"query": "x"})
        self.assertTrue(refused["isError"])
        self.assertIn("not offered to aurelian", refused["content"][0]["text"])
        self.assertIn("qmd, brave", refused["content"][0]["text"])
        self.assertNotIn("tools/call", [r["method"] for r in self.brave.requests()])  # the refusal reached no upstream
        bridge.close()

    def test_unknown_family_is_refused_at_startup(self):
        # (::bridge-tools-unknown-family) — a shim rendered with a family this bridge does not
        # know exits 2 with the family named, rather than advertising nothing quietly
        proc = subprocess.run([sys.executable, str(BRIDGE), "--tools", "qmd,gmail"], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 2)
        self.assertIn("gmail", proc.stderr)

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

    def board_bridge(self, *args: str, fail: bool = False) -> "tuple[Bridge, pathlib.Path]":
        log = self.tmp / "board.log"
        extra = {"BOARD_STUB_LOG": str(log), **({"BOARD_STUB_FAIL": "1"} if fail else {})}
        bridge = Bridge(self.brave.url, *(args or ("--agent", "claudius", "--tools", "qmd,board")), **extra)
        bridge.start()
        return bridge, log

    @staticmethod
    def board_calls(log: pathlib.Path) -> list[dict]:
        return [json.loads(l) for l in log.read_text().splitlines()] if log.exists() else []

    def test_board_family_advertises_five_tools_and_nothing_that_decides(self):
        # (::bridge-board-five-tools) — the family is exactly the five the note names, after
        # qmd's; no tool maps to pick, edit or any decision, and a board_ name outside the five
        # is refused by the bridge, never forwarded
        bridge, log = self.board_bridge()
        names = [t["name"] for t in bridge.rpc("tools/list")["result"]["tools"]]
        self.assertEqual([n for n in names if n.startswith("board_")], BOARD_OFFERED)
        for forbidden in ("pick", "edit", "approve", "approved", "brief_approved", "reject", "land"):
            refused = bridge.call(f"board_{forbidden}", {"card": "x"})
            self.assertTrue(refused["isError"], forbidden)
            self.assertIn("is not a board tool", refused["content"][0]["text"])
        self.assertEqual(self.board_calls(log), [])
        self.assertIn("board_brief", bridge.rpc("initialize")["result"]["instructions"])
        bridge.close()

    def test_board_family_withheld_is_refused_and_unlisted(self):
        # (::bridge-board-withheld) — a persona whose bridge_tools omits board sees no board_*
        # and a call is one tool error naming the agent, with the CLI never run
        bridge, log = self.board_bridge("--agent", "marcus", "--tools", "qmd,notion,brave")
        names = [t["name"] for t in bridge.rpc("tools/list")["result"]["tools"]]
        self.assertEqual([n for n in names if n.startswith("board_")], [])
        refused = bridge.call("board_list", {})
        self.assertTrue(refused["isError"])
        self.assertIn("not offered to marcus", refused["content"][0]["text"])
        self.assertEqual(self.board_calls(log), [])
        bridge.close()

    def test_board_reads_run_the_cli_as_the_agent(self):
        # (::bridge-board-reads) — list and get forward to the CLI's read verbs only
        bridge, log = self.board_bridge()
        listed = bridge.call("board_list", {"column": "refine", "owner": "claudius"})
        self.assertFalse(listed.get("isError"))
        self.assertEqual(listed["content"][0]["text"], "stub-ok list")
        bridge.call("board_get", {"card": "local-search"})
        self.assertEqual([c["argv"] for c in self.board_calls(log)],
                         [["list", "--column", "refine", "--owner", "claudius"], ["show", "local-search"]])
        bridge.close()

    def test_board_writes_carry_the_buzz_actor_and_the_text_by_file(self):
        # (::bridge-board-writes) — create, brief and note pass --actor buzz:<agent>, never a
        # caller-supplied actor, and text reaches the CLI as a file with the exact text
        bridge, log = self.board_bridge()
        bridge.call("board_create", {"title": "T", "idea": "I", "scope": ["vault:05_knowledge"], "owner": "claudius",
                                     "tags": ["a", "b"], "actor": "dave"})
        bridge.call("board_brief", {"card": "t", "text": "# Brief: t\nbody\n"})
        bridge.call("board_note", {"card": "t", "text": "a note"})
        created, briefed, noted = self.board_calls(log)
        self.assertEqual(created["argv"], ["create", "--title", "T", "--idea", "I", "--scope", "vault:05_knowledge",
                                           "--owner", "claudius", "--tags", "a,b", "--actor", "buzz:claudius"])
        self.assertEqual(briefed["argv"][:2], ["brief", "t"])
        self.assertEqual(briefed["argv"][-2:], ["--actor", "buzz:claudius"])
        self.assertEqual(briefed["files"]["--from-file"], "# Brief: t\nbody\n")
        self.assertEqual(noted["files"]["--from-file"], "a note")
        bridge.close()

    def test_board_brief_template_prints_the_skeleton_without_a_card(self):
        # (::bridge-board-template) — template=true is the CLI's `template --kind`, writes nothing
        bridge, log = self.board_bridge()
        result = bridge.call("board_brief", {"template": True})
        self.assertEqual(result["content"][0]["text"], "stub-ok template")
        self.assertEqual(self.board_calls(log)[0]["argv"], ["template", "--kind", "research"])
        missing = bridge.call("board_brief", {"card": "t"})
        self.assertTrue(missing["isError"])
        self.assertEqual(len(self.board_calls(log)), 1)
        bridge.close()

    def test_board_refusal_is_the_clis_message_as_a_tool_error(self):
        # (::bridge-board-cli-refusal) — a rule lives in board.py: its stderr comes back whole
        bridge, _ = self.board_bridge(fail=True)
        result = bridge.call("board_note", {"card": "t", "text": "x"})
        self.assertTrue(result["isError"])
        self.assertIn("refused by the stub", result["content"][0]["text"])
        bridge.close()

    def test_board_without_an_agent_name_is_refused(self):
        # (::bridge-board-needs-agent) — the actor is buzz:<agent>; no --agent, no writes
        bridge, log = self.board_bridge("--tools", "qmd,board")
        result = bridge.call("board_note", {"card": "t", "text": "x"})
        self.assertTrue(result["isError"])
        self.assertIn("needs --agent", result["content"][0]["text"])
        self.assertEqual(self.board_calls(log), [])
        bridge.close()


if __name__ == "__main__":
    unittest.main()
