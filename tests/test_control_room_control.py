#!/usr/bin/env python3
"""Screen-side suite for bin/control_room_control.py (T5.3a).

The HTTP server binds 127.0.0.1:0 over the T5.3 read model; the broker end is the real
bin/control_broker.py served by tests/fixtures/control-broker/fake_broker_socket.py on a unix
socket, against the fixture shims. StateFileSystemd reads the same state.json the shim mutates,
so the state the screen reports after a click is what the broker's `after` re-read saw. No real
unit is touched. Each test method carries the `::` anchor design/fleet-suites.toml declares.
"""
from __future__ import annotations

import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from contextlib import redirect_stderr

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "control-broker"
ACCEPTANCE = ROOT / "tests" / "acceptance" / "control_room_controls.sh"
ACTIONS_JS = ROOT / "bin" / "control_room_ui" / "actions.js"
NOW = "2026-09-14T08:00:00Z"
HEADERS = {"Content-Type": "application/json", "X-Control-Room": "1"}

sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(FIXTURE))
import control_room_fixture as fixture  # noqa: E402
import fake_broker_socket  # noqa: E402

api = fixture.api
sys.path.insert(0, str(ROOT / "bin"))
import control_broker as broker  # noqa: E402
import control_room_control as control  # noqa: E402


def post(base: str, payload, headers=None, path="/api/v1/control/actions", method="POST"):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    request = urllib.request.Request(f"{base}{path}", data=body, method=method, headers=HEADERS if headers is None else headers)
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            raw, status = response.read(), response.status
    except urllib.error.HTTPError as error:
        raw, status = error.read(), error.code
    try:
        return status, json.loads(raw)
    except json.JSONDecodeError:
        return status, None


class StateFileSystemd:
    """The read model's systemd answers, from the state.json the broker shim mutates."""

    def __init__(self, path: pathlib.Path, fallback=None) -> None:
        self.path, self.fallback = path, fallback or fixture.FakeSystemd()

    def show(self, name: str, scope: str):
        state = json.loads(self.path.read_text())
        if name in state:
            return {k: v for k, v in state[name].items() if not k.startswith("_")}, None
        return self.fallback.show(name, scope)


class Served:
    def __init__(self, control_obj=None, receipts: pathlib.Path | None = None, systemd=None,
                 retry_policy=None, control_reader=None) -> None:
        kwargs = {}
        if systemd is not None:
            kwargs["systemd"] = systemd
        if retry_policy is not None:
            kwargs["retry_policy"] = retry_policy
        if control_reader is not None:
            kwargs["control_reader"] = control_reader
        self.model = fixture.build_model(**kwargs)
        self.server = api.make_server("127.0.0.1", 0, self.model)
        if control_obj is not None:
            self.server.RequestHandlerClass.control = control_obj
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)


class BrokerEnd:
    def __init__(self, now: str = NOW) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.receipts = self.root / "receipts"
        self.socket = self.root / "crb.sock"
        env, argv = fake_broker_socket.sandbox(self.receipts, now=now, root=self.root)
        self.server = fake_broker_socket.make_server(str(self.socket), env, argv)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    @property
    def state_path(self) -> pathlib.Path:
        return self.root / "state.json"

    def stamp(self, unit: str, when: str) -> None:
        import datetime as dt
        path = self.root / "stamps" / f"stamp-{unit}.timer"
        path.write_text("")
        seconds = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        os.utime(path, (seconds, seconds))

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        self.temp.cleanup()


class PeerRule(unittest.TestCase):  # (::control-peer-rule)
    TABLE = [("100.64.0.9", "100.86.82.16", True), ("100.86.82.16", "100.86.82.16", False),
             ("127.0.0.1", "100.86.82.16", False), (None, "100.86.82.16", False), ("127.0.0.1", "127.0.0.1", True)]

    def test_table_and_agreement_with_the_broker(self):
        for remote, local, expected in self.TABLE:
            allowed, reason = control.peer_allowed(remote, local)
            self.assertEqual(allowed, expected, (remote, local, reason))
            self.assertEqual(control.peer_allowed(remote, local), broker.peer_allowed(remote, local), (remote, local))
        self.assertEqual(control.peer_allowed("127.0.0.1", "127.0.0.1")[1], "loopback-bound development instance")


class LastActionFromReceipts(unittest.TestCase):  # (::control-last-action-from-receipts)
    def test_newest_non_preview_wins_and_malformed_is_named(self):
        stderr = io.StringIO()
        with redirect_stderr(stderr):
            last = control.ControlReceipts(FIXTURE / "receipts").last_action("knowledge-digest")
        self.assertIsNotNone(last)
        self.assertEqual(set(last), {"action", "actor", "reason", "at", "result", "before", "after", "receiptId", "links"})
        self.assertEqual(last["receiptId"], "20260913T193000Z-resume-447a45")
        self.assertEqual(last["result"], "refused")
        self.assertEqual(last["action"], "resume")
        self.assertEqual(last["at"], "2026-09-13T19:30:00Z")
        self.assertIsInstance(last["actor"], str)
        self.assertEqual(last["actor"], "dave via control-room from 100.64.0.9")
        self.assertEqual(last["before"], "paused")
        self.assertIsNone(last["after"])
        self.assertEqual(last["links"]["workflow"], "/workflows/knowledge-digest")
        self.assertTrue(last["links"]["receipt"].endswith("20260913T193000Z-resume-447a45.json"))
        self.assertIn("previewReceipt", last["links"])
        self.assertIn("run", last["links"])
        self.assertIn("bad.json", stderr.getvalue())
        self.assertEqual(stderr.getvalue().count("bad.json"), 1)

    def test_same_second_tie_goes_to_the_receipt_written_last(self):
        first = json.loads((FIXTURE / "receipts" / "knowledge-digest" / "20260913T193000Z-resume-447a45.json").read_text())
        with tempfile.TemporaryDirectory() as temp:
            folder = pathlib.Path(temp) / "buzz-agent@marcus"
            folder.mkdir()
            for suffix, reason in (("ffffff", "clicked first"), ("000000", "clicked last")):
                receipt = {**first, "receipt_id": f"20260913T193000Z-start-{suffix}", "action": "start", "reason": reason}
                path = folder / f"{receipt['receipt_id']}.json"
                path.write_text(json.dumps(receipt))
                os.utime(path, ns=(1_000_000_000, 1_000_000_000 + (1 if suffix == "000000" else 0)))
            last = control.ControlReceipts(pathlib.Path(temp)).last_action("buzz-agent@marcus")
        self.assertEqual((last["receiptId"], last["reason"]), ("20260913T193000Z-start-000000", "clicked last"))

    def test_missing_root_and_no_receipts(self):
        self.assertIsNone(control.ControlReceipts(FIXTURE / "receipts").last_action("scorecard"))
        self.assertIsNone(control.ControlReceipts(pathlib.Path("/nonexistent/receipts")).last_action("knowledge-digest"))
        with tempfile.TemporaryDirectory() as temp:
            self.assertIsNone(control.ControlReceipts(pathlib.Path(temp)).last_action("knowledge-digest"))

    def test_page_renders_the_last_action(self):
        served = Served(control_reader=control.ControlReceipts(FIXTURE / "receipts").last_action)
        try:
            item, _ = served.model.workflow_detail("knowledge-digest")
            self.assertEqual(item["control"]["lastAction"]["receiptId"], "20260913T193000Z-resume-447a45")
        finally:
            served.close()


DECLARED = "## Identity\n\n| | |\n|---|---|\n| Unit | `x.service` |\n| Retry | idempotent: same-day skip |\n\n## Trigger\n"


class RetryPolicy(unittest.TestCase):  # (::control-retry-policy)
    def item(self, text, outcome="failed", state="paused"):
        with tempfile.TemporaryDirectory() as temp:
            repo = pathlib.Path(temp)
            (repo / "design" / "contracts").mkdir(parents=True)
            contract = None
            if text is not None:
                (repo / "design" / "contracts" / "x.md").write_text(text)
                contract = {"path": "design/contracts/x.md"}
            policy = control.retry_policy(repo)
            return policy({"id": "x", "contract": contract, "lastRun": {"id": "r1", "outcome": outcome} if outcome else None,
                           "control": {"state": state}})

    def test_policy_table(self):
        self.assertEqual(self.item(DECLARED), (True, None))
        enabled, reason = self.item(DECLARED, outcome="artifact")
        self.assertFalse(enabled)
        self.assertIn("artifact", reason)
        enabled, reason = self.item(DECLARED, outcome=None)
        self.assertFalse(enabled)
        self.assertIn("none", reason)
        self.assertEqual(self.item(DECLARED.replace("| Retry | idempotent: same-day skip |\n", "")),
                         (False, "contract declares no idempotent operation"))
        self.assertEqual(self.item(None), (False, "contract unavailable"))
        enabled, _ = self.item(DECLARED, state="running")
        self.assertFalse(enabled)
        self.assertEqual(control.contract_retry_declaration(DECLARED), (True, "idempotent: same-day skip"))

    def test_the_read_model_consults_the_policy_and_leaves_the_other_actions_alone(self):
        calls = []

        def policy(item):
            calls.append(item["id"])
            return (True, None) if item["id"] == "scorecard" else (False, "policy says no")

        served = Served(retry_policy=policy)
        try:
            item, _ = served.model.workflow_detail("scorecard")
            baseline, _ = fixture.build_model().workflow_detail("scorecard")
            actions = {a["id"]: a for a in item["control"]["actions"]}
            self.assertEqual(actions["retry"], {"id": "retry", "enabled": True, "reason": None})
            for action_id in ("pause", "resume", "run_now", "stop"):
                self.assertEqual(actions[action_id], next(a for a in baseline["control"]["actions"] if a["id"] == action_id))
            other, _ = served.model.workflow_detail("knowledge-digest")
            self.assertEqual(next(a for a in other["control"]["actions"] if a["id"] == "retry"),
                             {"id": "retry", "enabled": False, "reason": "policy says no"})
            self.assertIn("scorecard", calls)
        finally:
            served.close()


class FakeBroker:
    def __init__(self, response=None, error=None) -> None:
        self.response, self.error, self.requests = response, error, []

    def call(self, request):
        self.requests.append(request)
        if self.error:
            raise self.error
        return self.response


def refusal_response(code, status):
    receipt = {"receipt_id": "20260914T080000Z-pause-000000", "result": "refused", "refusal": {"code": code, "message": "m"}}
    return {"v": 1, "result": "refused", "http_status": status, "refusal": receipt["refusal"], "receipt": receipt, "preview": None}


class RefusalStatusMap(unittest.TestCase):  # (::control-refusal-status-map)
    def serve_with(self, fake):
        obj = control.ControlRoomControl(client=fake, receipts=control.ControlReceipts(FIXTURE / "receipts"),
                                         retry_policy=control.retry_policy(ROOT))
        return Served(control_obj=obj)

    def test_status_map(self):
        for code, status in (("unknown_workflow", 404), ("peer_denied", 403), ("not_allowlisted", 403), ("state_conflict", 400),
                             ("preview_stale", 400), ("allowlist_invalid", 400)):
            self.assertEqual(control.HTTP_STATUS_BY_CODE.get(code, 400), status, code)
            served = self.serve_with(FakeBroker(refusal_response(code, status)))
            try:
                got, body = post(served.base, {"workflow_id": "knowledge-digest", "action": "pause", "reason": "x"})
                self.assertEqual(got, status, code)
                self.assertEqual(body["receipt"]["refusal"]["code"], code)
                self.assertEqual(body["error"], "m")
                self.assertIn("control", body)
            finally:
                served.close()

    def test_failed_unreachable_timeout_and_the_kept_checks(self):
        failed = {"v": 1, "result": "failed", "http_status": 500, "refusal": None, "preview": None,
                  "receipt": {"receipt_id": "r", "result": "failed", "refusal": None}}
        served = self.serve_with(FakeBroker(failed))
        try:
            status, body = post(served.base, {"workflow_id": "knowledge-digest", "action": "pause", "reason": "x"})
            self.assertEqual(status, 500)
            self.assertEqual(set(body), {"error", "receipt", "control"})
            self.assertEqual(body["receipt"]["result"], "failed")
        finally:
            served.close()
        served = self.serve_with(control.BrokerClient("/nonexistent/crb.sock", timeout=1))
        try:
            status, body = post(served.base, {"workflow_id": "knowledge-digest", "action": "pause", "reason": "x"})
            self.assertEqual(status, 502)
            self.assertTrue(body["error"].startswith("control broker unreachable: "), body)
            self.assertIsNone(body["receipt"])
            self.assertEqual(post(served.base, {"workflow_id": "knowledge-digest", "action": "resume"},
                                  headers={"Content-Type": "application/json"})[0], 400)
            self.assertEqual(post(served.base, b"not json")[0], 400)
            self.assertEqual(post(served.base, {"workflow_id": "knowledge-digest", "action": "rm -rf"})[0], 400)
            self.assertEqual(post(served.base, {"workflow_id": 7, "action": "pause"})[0], 400)
            self.assertEqual(post(served.base, {}, path="/api/v1/workflows/x")[0], 405)
            self.assertEqual(post(served.base, b"", method="HEAD")[0], 405)
            status, body = post(served.base, {"workflow_id": "knowledge-digest", "kind": "schedule"}, path="/api/v1/control/proposals")
            self.assertEqual(status, 501)
        finally:
            served.close()
        served = self.serve_with(FakeBroker(error=control.BrokerTimeout("no answer in 1 s")))
        try:
            self.assertEqual(post(served.base, {"workflow_id": "knowledge-digest", "action": "pause", "reason": "x"})[0], 504)
        finally:
            served.close()

    def test_a_socket_that_never_answers_times_out(self):
        import socket
        with tempfile.TemporaryDirectory() as temp:
            path = os.path.join(temp, "mute.sock")
            listener = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            listener.bind(path)
            listener.listen(1)
            served = self.serve_with(control.BrokerClient(path, timeout=1))
            try:
                status, body = post(served.base, {"workflow_id": "knowledge-digest", "action": "pause", "reason": "x"})
                self.assertEqual(status, 504)
                self.assertIn("timed out", body["error"])
            finally:
                served.close()
                listener.close()

    def test_no_control_bound_keeps_the_501_stub(self):
        served = Served()
        try:
            status, body = post(served.base, {"workflow_id": "knowledge-digest", "action": "resume", "reason": "t"})
            self.assertEqual(status, 501)
            self.assertEqual(body["status"], "not_implemented")
            self.assertEqual(post(served.base, {"workflow_id": "nope", "action": "resume"})[0], 404)
        finally:
            served.close()


class PostForwardsAndReconciles(unittest.TestCase):  # (::control-post-forwards-and-reconciles)
    def setUp(self):
        self.broker = BrokerEnd()
        self.broker.stamp("knowledge-digest", "2026-09-06T09:04:00Z")
        obj = control.ControlRoomControl(client=control.BrokerClient(str(self.broker.socket), timeout=60),
                                         receipts=control.ControlReceipts(self.broker.receipts),
                                         retry_policy=control.retry_policy(ROOT))
        self.served = Served(control_obj=obj, systemd=StateFileSystemd(self.broker.state_path),
                             control_reader=obj.receipts.last_action, retry_policy=obj.retry_policy)

    def tearDown(self):
        self.served.close()
        self.broker.close()

    def test_resume_preview_then_apply_reconciles_from_the_re_read(self):
        before, _ = self.served.model.workflow_detail("knowledge-digest")
        self.assertEqual(before["control"]["state"], "paused")
        status, body = post(self.served.base, {"workflow_id": "knowledge-digest", "action": "resume", "reason": "test", "stage": "preview"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["receipt"]["result"], "previewed")
        token = body["preview"]["preview_token"]
        self.assertTrue(token)
        self.assertIn("immediately", body["preview"]["implication"]["message"])
        self.assertEqual(body["control"]["state"], "paused")
        self.assertEqual(body["receipt"]["actor"]["kind"], "screen")
        self.assertEqual(body["receipt"]["actor"]["local"], "127.0.0.1")
        self.assertEqual(body["receipt"]["actor"]["remote"], "127.0.0.1")
        self.assertEqual(body["receipt"]["actor"]["peer"]["uid"], os.getuid())
        status, body = post(self.served.base, {"workflow_id": "knowledge-digest", "action": "resume", "reason": "test",
                                               "stage": "apply", "preview_token": token})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["receipt"]["result"], "applied")
        self.assertEqual(body["control"]["state"], "running")
        self.assertEqual(body["control"]["lastAction"]["receiptId"], body["receipt"]["receipt_id"])
        self.assertEqual(body["control"]["lastAction"]["result"], "applied")
        after, _ = self.served.model.workflow_detail("knowledge-digest")
        self.assertEqual(after["control"]["state"], "running")
        self.assertEqual(sorted(p.parent.name for p in self.broker.receipts.rglob("*.json")),
                         ["knowledge-digest", "knowledge-digest"])

    def test_runtime_start_reconciles_from_the_re_read(self):  # (::control-runtime-post)
        self.assertIsNone(control.validate_shape({"action": "start", "workflow_id": "buzz-agent@marcus"}))
        self.assertIsNone(control.validate_shape({"action": "restart", "workflow_id": "buzz-agent@marcus"}))
        self.assertIn("action must be one of", control.validate_shape({"action": "enable", "workflow_id": "buzz-agent@marcus"}))
        before, _ = self.served.model.workflow_detail("buzz-agent@marcus")
        self.assertEqual(before["control"]["state"], "paused")
        self.assertEqual([a["id"] for a in before["control"]["actions"]], ["start", "stop", "restart"])
        status, body = post(self.served.base, {"workflow_id": "buzz-agent@marcus", "action": "start"})
        self.assertEqual(status, 400, body)
        self.assertEqual(body["receipt"]["refusal"]["code"], "confirmation_required")
        self.assertEqual(body["control"]["state"], "paused")
        status, body = post(self.served.base, {"workflow_id": "buzz-agent@marcus", "action": "start", "confirm": True})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["receipt"]["result"], "applied")
        self.assertEqual(body["receipt"]["actor"]["kind"], "screen")
        self.assertEqual(body["control"]["state"], "active")
        actions = {a["id"]: a for a in body["control"]["actions"]}
        self.assertEqual((actions["start"]["enabled"], actions["stop"]["enabled"], actions["restart"]["enabled"]),
                         (False, True, True))
        self.assertEqual(body["control"]["lastAction"]["receiptId"], body["receipt"]["receipt_id"])
        self.assertEqual(body["control"]["lastAction"]["links"]["agent"], "/agents/marcus")
        agent, _ = self.served.model.agent_detail("marcus")
        self.assertEqual(agent["control"]["state"], "active")
        self.assertEqual(agent["runtime"]["state"], "active")
        self.assertEqual(agent["control"]["lastAction"]["action"], "start")
        self.assertEqual(sorted(p.parent.name for p in self.broker.receipts.rglob("*.json")),
                         ["buzz-agent@marcus", "buzz-agent@marcus"])
        status, body = post(self.served.base, {"workflow_id": "buzz-agent@marcus", "action": "pause", "reason": "x"})
        self.assertEqual(status, 400, body)
        self.assertEqual(body["receipt"]["refusal"]["code"], "unknown_action")

    def test_refusals_travel_with_their_receipt(self):
        status, body = post(self.served.base, {"workflow_id": "nope", "action": "pause", "reason": "x"})
        self.assertEqual(status, 404)
        self.assertEqual(body["receipt"]["refusal"]["code"], "unknown_workflow")
        self.assertTrue(list((self.broker.receipts / "_refused").glob("*.json")))
        status, body = post(self.served.base, {"workflow_id": "knowledge-digest", "action": "stop", "reason": "x"})
        self.assertEqual(status, 400)
        self.assertEqual(body["receipt"]["refusal"]["code"], "confirmation_required")
        self.assertEqual(body["control"]["state"], "paused")


class ActionsJsFlow(unittest.TestCase):  # (::control-actions-js-flow)
    def test_grep_level_flow(self):
        text = ACTIONS_JS.read_text()
        for needle in ('"stage":"preview"', "preview_token", "trigger_required", "retry_of", "confirm(", "/api/v1/workflows/${",
                       "run_id", "Apply resume?", "SIGTERM"):
            self.assertIn(needle, text.replace("stage: \"preview\"", '"stage":"preview"'), needle)
        self.assertGreaterEqual(text.count("confirm("), 2)


class AcceptanceScriptLints(unittest.TestCase):  # (::control-acceptance-script-lints)
    def test_syntax_shellcheck_and_never_resumes(self):
        self.assertTrue(ACCEPTANCE.is_file(), ACCEPTANCE)
        self.assertEqual(subprocess.run(["bash", "-n", str(ACCEPTANCE)], capture_output=True).returncode, 0)
        if shutil.which("shellcheck"):
            lint = subprocess.run(["shellcheck", "-S", "error", str(ACCEPTANCE)], capture_output=True, text=True)
            self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        text = ACCEPTANCE.read_text()
        for forbidden in ("enable --now", 'stage":"apply"', "--stage apply"):
            self.assertNotIn(forbidden, text, forbidden)
        self.assertIn("--stage preview", text)


class RunInProgressRule(unittest.TestCase):
    def test_every_activating_substate_of_a_oneshot_is_running(self):
        import control_room_state as state
        for substate in ("start-pre", "start", "start-post"):
            with self.subTest(substate=substate):
                systemd = {"kind": "timer", "timer": {"activeState": "active"},
                           "service": {"activeState": "activating", "subState": substate}}
                self.assertTrue(state.service_running(systemd))
                self.assertEqual(state.trigger_state(systemd), "running")
        self.assertEqual(state.RUNNING_SUBSTATES, broker.RUNNING_SUBSTATES)


if __name__ == "__main__":
    unittest.main()
