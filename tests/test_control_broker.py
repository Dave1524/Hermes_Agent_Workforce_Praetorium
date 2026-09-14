#!/usr/bin/env python3
"""Fixture suite for bin/control_broker.py, the T5.3a root-side control broker.

Every case runs the broker as a subprocess (`--serve` on a pipe or a socketpair, or `act`)
with tests/fixtures/control-broker/bin/ on the front of PATH: a fake `systemctl` that keeps
its state in a JSON file beside itself and logs every argv, and a fake `systemd-analyze`.
No real unit is touched — the scheduled fleet is off and stays off. Each test method carries
the `::` anchor design/fleet-suites.toml declares for it.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURE = ROOT / "tests" / "fixtures" / "control-broker"
BROKER = ROOT / "bin" / "control_broker.py"
NOW = "2026-09-14T08:00:00Z"
UTC = dt.timezone.utc


sys.path.insert(0, str(ROOT / "bin"))
import control_broker as broker  # noqa: E402


class Sandbox:
    def __init__(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        shutil.copytree(FIXTURE / "bin", self.root / "bin")
        shutil.copy(FIXTURE / "state.json", self.root / "state.json")
        shutil.copy(FIXTURE / "calendar.json", self.root / "calendar.json")
        self.allowlist = FIXTURE / "allowlist.json"
        self.receipts = self.root / "receipts"
        self.stamps = self.root / "stamps"
        self.ustamps = self.root / "ustamps"
        for path in (self.receipts, self.stamps, self.ustamps):
            path.mkdir()
        self.log_path = self.root / "calls.log"

    def close(self) -> None:
        self.temp.cleanup()

    def stamp(self, unit: str, when: str, scope: str = "system") -> None:
        path = (self.ustamps if scope == "user" else self.stamps) / f"stamp-{unit}.timer"
        path.write_text("")
        seconds = dt.datetime.fromisoformat(when.replace("Z", "+00:00")).timestamp()
        os.utime(path, (seconds, seconds))

    def fail(self, unit: str) -> None:
        (self.root / "fail").write_text(unit)

    def argv(self, now: str = NOW, allowlist: pathlib.Path | None = None, peer_uids: str | None = None) -> list[str]:
        return [sys.executable, str(BROKER), "--allowlist", str(allowlist or self.allowlist),
                "--receipts", str(self.receipts), "--system-stamp-dir", str(self.stamps),
                "--user-stamp-dir", str(self.ustamps), "--lock", str(self.root / "lock"),
                "--peer-uids", peer_uids if peer_uids is not None else str(os.getuid()), "--now", now]

    def env(self, **extra: str) -> dict[str, str]:
        env = {"PATH": f"{self.root / 'bin'}{os.pathsep}{os.environ.get('PATH', '')}", "HOME": str(self.root)}
        env.update(extra)
        return env

    def call(self, request: dict | bytes, now: str = NOW, allowlist: pathlib.Path | None = None,
             peer_uids: str | None = None, env: dict[str, str] | None = None) -> dict:
        body = request if isinstance(request, bytes) else (json.dumps(request) + "\n").encode()
        completed = subprocess.run(self.argv(now, allowlist, peer_uids) + ["--serve"], input=body,
                                   capture_output=True, env=env or self.env(), check=False, timeout=60)
        assert completed.returncode == 0, completed.stderr.decode()
        return json.loads(completed.stdout.decode())

    def call_socket(self, request: dict, now: str = NOW, peer_uids: str | None = None) -> dict:
        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with ours, theirs:
            process = subprocess.Popen(self.argv(now, peer_uids=peer_uids) + ["--serve"], stdin=theirs, stdout=theirs,
                                       stderr=subprocess.PIPE, env=self.env())
            theirs.close()
            ours.sendall((json.dumps(request) + "\n").encode())
            ours.shutdown(socket.SHUT_WR)
            chunks = []
            while True:
                chunk = ours.recv(65536)
                if not chunk:
                    break
                chunks.append(chunk)
            _, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr.decode()
        return json.loads(b"".join(chunks).decode())

    def act(self, *args: str, now: str = NOW, env: dict[str, str] | None = None) -> tuple[int, dict]:
        completed = subprocess.run(self.argv(now) + ["act", *args], capture_output=True, env=env or self.env(),
                                   check=False, timeout=60)
        assert completed.stdout, completed.stderr.decode()
        return completed.returncode, json.loads(completed.stdout.decode())

    def log(self) -> list[str]:
        return self.log_path.read_text().splitlines() if self.log_path.exists() else []

    def clear_log(self) -> None:
        if self.log_path.exists():
            self.log_path.unlink()

    def state(self) -> dict:
        return json.loads((self.root / "state.json").read_text())

    def receipt_files(self) -> list[pathlib.Path]:
        return sorted(self.receipts.rglob("*.json"))


def mutating(lines: list[str]) -> list[str]:
    return [line for line in lines if any(f" {verb} " in line for verb in ("enable", "disable", "start", "stop"))]


def req(workflow_id: str, action: str, **fields) -> dict:
    return {"workflow_id": workflow_id, "action": action, "reason": "test", **fields}


class BrokerCase(unittest.TestCase):
    def setUp(self) -> None:
        self.box = Sandbox()

    def tearDown(self) -> None:
        self.box.close()

    def assertRefused(self, response: dict, code: str, status: int | None = None) -> dict:
        self.assertEqual(response["result"], "refused", response)
        self.assertEqual(response["refusal"]["code"], code, response["refusal"])
        if status is not None:
            self.assertEqual(response["http_status"], status)
        self.assertEqual(response["receipt"]["result"], "refused")
        self.assertEqual(response["receipt"]["refusal"]["code"], code)
        return response


class AllowlistRefuses(BrokerCase):  # (::broker-allowlist-refuses)
    def test_unknown_id_is_refused_receipted_and_runs_nothing(self):
        response = self.assertRefused(self.box.call(req("nope", "pause")), "unknown_workflow", 404)
        self.assertEqual(self.box.log(), [])
        files = self.box.receipt_files()
        self.assertEqual(len(files), 1)
        self.assertEqual(files[0].parent.name, "_refused")
        self.assertIsNone(response["receipt"]["workflow_id"])
        self.assertEqual(response["receipt"]["requested_workflow_id"], "nope")

    def test_shape_refusals(self):
        self.assertRefused(self.box.call(req("knowledge-digest", "rm -rf")), "unknown_action", 400)
        self.assertRefused(self.box.call(req("../etc", "pause")), "bad_request", 400)
        self.assertRefused(self.box.call(req("knowledge-digest", "pause", extra=1)), "bad_request", 400)
        self.assertRefused(self.box.call(req("knowledge-digest", "pause", reason="x" * 9216)), "bad_request", 400)
        self.assertRefused(self.box.call(b"not json\n"), "bad_request", 400)
        self.assertRefused(self.box.call(req("knowledge-digest", "pause", stage="preview")), "bad_request", 400)
        self.assertEqual(self.box.log(), [])
        self.assertEqual(len(self.box.receipt_files()), 6)
        self.assertEqual(sorted(p.name for p in self.box.receipts.iterdir()), ["_refused"])

    def test_excluded_and_absent_workflows(self):
        response = self.assertRefused(self.box.call(req("buzz-agent@marcus", "pause")), "bad_request", 400)
        self.assertIn("grammar", response["refusal"]["message"])
        response = self.assertRefused(self.box.call(req("nekovri-subsidy-kickoff", "pause")), "not_allowlisted", 403)
        self.assertIn("status = spent", response["refusal"]["message"])
        self.assertRefused(self.box.call(req("raw-ingest", "pause")), "unknown_workflow", 404)
        self.assertEqual(self.box.log(), [])

    def test_bad_allowlist_refuses_everything(self):
        bad = FIXTURE / "allowlist-bad.json"
        for workflow in ("knowledge-digest", "evil", "local-tier-eval"):
            self.assertRefused(self.box.call(req(workflow, "pause"), allowlist=bad), "allowlist_invalid", 400)
        missing = self.box.root / "absent.json"
        self.assertRefused(self.box.call(req("knowledge-digest", "pause"), allowlist=missing), "allowlist_invalid", 400)
        self.assertEqual(self.box.log(), [])
        self.assertEqual(len(self.box.receipt_files()), 4)

    def test_masked_and_not_found_units(self):
        self.assertRefused(self.box.call(req("masked-job", "pause")), "masked", 400)
        allowlist = json.loads(self.box.allowlist.read_text())
        allowlist["workflows"]["ghost-job"] = {"owner": "trajan", "contract": None, "retry": False,
                                              "retry_reason": None,
                                              "triggers": [{"unit": "ghost-job", "scope": "system"}]}
        path = self.box.root / "allowlist-ghost.json"
        path.write_text(json.dumps(allowlist))
        self.assertRefused(self.box.call(req("ghost-job", "pause"), allowlist=path), "unit_not_found", 400)
        self.assertEqual(mutating(self.box.log()), [])


class PauseKeepsCurrentRun(BrokerCase):  # (::broker-pause-keeps-current-run)
    def test_pause_disables_the_timer_and_leaves_the_service_running(self):
        response = self.box.call(req("local-tier-eval", "pause"))
        self.assertEqual(response["result"], "applied", response)
        self.assertEqual(response["http_status"], 200)
        lines = self.box.log()
        self.assertEqual(mutating(lines), ["systemctl disable --now local-tier-eval.timer --no-pager"])
        self.assertTrue(all(" show " in line or " disable " in line for line in lines))
        self.assertFalse(any(" stop " in line for line in lines))
        receipt = response["receipt"]
        unit = receipt["after"]["units"][0]
        self.assertEqual((unit["timer"]["activeState"], unit["timer"]["unitFileState"]), ("inactive", "disabled"))
        self.assertEqual((unit["service"]["activeState"], unit["service"]["subState"]), ("active", "running"))
        self.assertEqual(receipt["after"]["state"], "running")
        self.assertEqual(receipt["before"]["state"], "running")
        self.assertIsNone(receipt["next_scheduled_run"])

    def test_pausing_a_paused_workflow_is_a_state_conflict(self):
        response = self.assertRefused(self.box.call(req("knowledge-digest", "pause")), "state_conflict", 400)
        self.assertIn("already paused", response["refusal"]["message"])
        self.assertEqual(mutating(self.box.log()), [])
        self.assertEqual(response["receipt"]["before"]["state"], "paused")


class ResumePreviewBeforeApply(BrokerCase):  # (::broker-resume-preview-before-apply)
    def preview(self, workflow: str = "knowledge-digest", now: str = NOW) -> dict:
        response = self.box.call(req(workflow, "resume", stage="preview"), now=now)
        self.assertEqual(response["result"], "previewed", response)
        self.assertEqual(response["http_status"], 200)
        return response

    def test_apply_without_a_preview_is_refused(self):
        self.assertRefused(self.box.call(req("knowledge-digest", "resume")), "preview_required", 400)
        self.assertRefused(self.box.call(req("knowledge-digest", "resume", stage="apply")), "preview_required", 400)
        self.assertRefused(self.box.call(req("knowledge-digest", "resume", stage="apply", preview_token="20260914T080000Z-resume-abcdef")),
                           "preview_required", 400)
        self.assertEqual(mutating(self.box.log()), [])

    def test_preview_states_the_catch_up_and_apply_needs_its_token(self):
        self.box.stamp("knowledge-digest", "2026-09-06T09:04:00Z")
        response = self.preview()
        implication = response["preview"]["implication"]
        self.assertIs(implication["catchUp"], True)
        self.assertIs(implication["persistent"], True)
        self.assertEqual(implication["missedElapseAt"], "2026-09-13T09:00:00Z")
        self.assertEqual(implication["nextElapseAt"], "2026-09-20T09:00:00Z")
        self.assertEqual(implication["lastTriggerAt"], "2026-09-06T09:04:00Z")
        self.assertIn("knowledge-digest.service", implication["message"])
        self.assertIn("immediately", implication["message"])
        self.assertIs(implication["approximate"], False)
        token = response["preview"]["preview_token"]
        self.assertEqual(token, response["receipt"]["receipt_id"])
        self.assertTrue((self.box.receipts / "knowledge-digest" / f"{token}.json").is_file())
        self.assertEqual(mutating(self.box.log()), [])
        self.assertTrue(any("systemd-analyze calendar --iterations=2 Sun 09:00" == " ".join(c["argv"])
                            for c in response["receipt"]["commands"]))

        applied = self.box.call(req("knowledge-digest", "resume", stage="apply", preview_token=token))
        self.assertEqual(applied["result"], "applied", applied)
        self.assertEqual(mutating(self.box.log()), ["systemctl enable --now knowledge-digest.timer --no-pager"])
        receipt = applied["receipt"]
        self.assertEqual(receipt["after"]["state"], "running")
        self.assertIs(receipt["catch_up_fired"], True)
        self.assertEqual(receipt["next_scheduled_run"], "2026-09-20T09:00:00Z")
        self.assertEqual(receipt["links"]["preview_receipt"], token)
        self.assertEqual(receipt["stage"], "apply")

        stale = self.box.call(req("knowledge-digest", "resume", stage="apply", preview_token=token))
        self.assertRefused(stale, "state_conflict", 400)

    def test_a_token_from_a_changed_state_or_an_old_preview_is_stale(self):
        token = self.preview()["preview"]["preview_token"]
        state = self.box.state()
        state["knowledge-digest.timer"]["UnitFileState"] = "enabled"
        (self.box.root / "state.json").write_text(json.dumps(state))
        response = self.box.call(req("knowledge-digest", "resume", stage="apply", preview_token=token))
        self.assertRefused(response, "preview_stale", 400)
        self.assertIn("state changed", response["refusal"]["message"])
        self.assertEqual(mutating(self.box.log()), [])
        state["knowledge-digest.timer"]["UnitFileState"] = "disabled"
        (self.box.root / "state.json").write_text(json.dumps(state))
        old = self.preview(now="2026-09-14T07:49:00Z")["preview"]["preview_token"]
        response = self.box.call(req("knowledge-digest", "resume", stage="apply", preview_token=old))
        self.assertRefused(response, "preview_stale", 400)
        self.assertIn("older", response["refusal"]["message"])
        fresh = self.preview(now="2026-09-14T07:51:00Z")["preview"]["preview_token"]
        self.assertEqual(self.box.call(req("knowledge-digest", "resume", stage="apply", preview_token=fresh))["result"], "applied")

    def test_no_catch_up_cases(self):
        self.box.stamp("scorecard", "2026-09-14T07:05:00Z")
        implication = self.preview("scorecard")["preview"]["implication"]
        self.assertIs(implication["catchUp"], False)
        self.assertIn("no missed elapse", implication["message"])
        self.box.stamp("buzz-pr-watch", "2026-09-01T09:23:00Z", scope="user")
        implication = self.preview("buzz-pr-watch")["preview"]["implication"]
        self.assertIs(implication["catchUp"], False)
        self.assertIs(implication["persistent"], False)
        self.assertIn("no catch-up", implication["message"])

    def test_unmapped_calendar_spec_is_unknown_not_refused(self):
        state = self.box.state()
        state["knowledge-digest.timer"]["TimersCalendar"] = "{ OnCalendar=Mon *-*-08..14 09:37 ; next_elapse=n/a }"
        (self.box.root / "state.json").write_text(json.dumps(state))
        implication = self.preview()["preview"]["implication"]
        self.assertIsNone(implication["catchUp"])
        self.assertIn("unknown", implication["message"])
        self.assertIn("immediately", implication["message"])


class RunNowReturnsRunId(BrokerCase):  # (::broker-run-now-returns-run-id)
    def test_run_now_starts_the_service_and_reports_its_invocation_id(self):
        response = self.box.call(req("knowledge-digest", "run_now"))
        self.assertEqual(response["result"], "applied", response)
        self.assertEqual(mutating(self.box.log()), ["systemctl start --no-block knowledge-digest.service --no-pager"])
        invocation = self.box.state()["knowledge-digest.service"]["InvocationID"]
        self.assertEqual(response["receipt"]["run_id"], invocation)
        self.assertEqual(response["receipt"]["links"]["run"], f"/runs/{invocation}")
        self.assertEqual(response["receipt"]["trigger"], "knowledge-digest")
        self.assertEqual(response["receipt"]["after"]["state"], "running")
        self.assertTrue(any("InvocationID" in " ".join(c["argv"]) for c in response["receipt"]["commands"][-3:]))

    def test_run_now_refusals(self):
        self.assertRefused(self.box.call(req("local-tier-eval", "run_now")), "state_conflict", 400)
        response = self.assertRefused(self.box.call(req("augustus-content", "run_now")), "trigger_required", 400)
        self.assertEqual(response["refusal"]["choices"], ["augustus-content", "content-change-dispatch"])
        self.assertEqual(mutating(self.box.log()), [])
        self.assertRefused(self.box.call(req("augustus-content", "run_now", trigger="sshd")), "bad_request", 400)
        response = self.box.call(req("augustus-content", "run_now", trigger="content-change-dispatch"))
        self.assertEqual(response["result"], "applied", response)
        self.assertEqual(mutating(self.box.log()),
                         ["systemctl start --no-block content-change-dispatch.service --no-pager"])
        self.assertEqual(self.box.state()["augustus-content.service"]["ActiveState"], "inactive")


class RetryIdempotentOnly(BrokerCase):  # (::broker-retry-idempotent-only)
    def test_retry_is_gated_on_the_contract_declaration(self):
        response = self.assertRefused(self.box.call(req("knowledge-digest", "retry")), "not_idempotent", 400)
        self.assertIn("idempotent", response["refusal"]["message"])
        self.assertEqual(mutating(self.box.log()), [])
        response = self.box.call(req("scorecard", "retry", retry_of="run-0908"))
        self.assertEqual(response["result"], "applied", response)
        self.assertEqual(response["receipt"]["links"]["retry_of"], "run-0908")
        self.assertEqual(mutating(self.box.log()), ["systemctl start --no-block scorecard.service --no-pager"])
        self.assertEqual(response["receipt"]["run_id"], self.box.state()["scorecard.service"]["InvocationID"])


class StopNeedsConfirmAndReason(BrokerCase):  # (::broker-stop-needs-confirm-and-reason)
    def test_stop_gates_and_effect(self):
        self.assertRefused(self.box.call(req("local-tier-eval", "stop")), "confirmation_required", 400)
        self.assertRefused(self.box.call(req("local-tier-eval", "stop", confirm=True, reason="  ")), "reason_required", 400)
        self.assertEqual(mutating(self.box.log()), [])
        response = self.box.call(req("local-tier-eval", "stop", confirm=True, reason="stuck"))
        self.assertEqual(response["result"], "applied", response)
        self.assertEqual(mutating(self.box.log()), ["systemctl stop --no-block local-tier-eval.service --no-pager"])
        self.assertTrue(any(c["argv"][-3:-1] == ["local-tier-eval.service", "--property=ActiveState"]
                            or "--property=ActiveState" in c["argv"] for c in response["receipt"]["commands"]))
        receipt = response["receipt"]
        self.assertEqual(receipt["after"]["units"][0]["service"]["activeState"], "inactive")
        self.assertEqual(receipt["after"]["state"], "active")
        self.assertIs(receipt["confirm"], True)
        self.assertIsNone(receipt["note"])
        self.assertRefused(self.box.call(req("knowledge-digest", "stop", confirm=True, reason="x")), "state_conflict", 400)


class ScopeAddressing(BrokerCase):  # (::broker-scope-addressing)
    def test_user_units_go_through_the_user_manager_and_system_units_do_not(self):
        self.box.stamp("buzz-pr-watch", "2026-09-13T09:23:00Z", scope="user")
        self.box.stamp("knowledge-digest", "2026-09-06T09:04:00Z")
        user = self.box.call(req("buzz-pr-watch", "resume", stage="preview"))
        self.assertEqual(user["result"], "previewed", user)
        user_lines = [line for line in self.box.log() if "buzz-pr-watch" in line]
        self.assertTrue(user_lines)
        for line in user_lines:
            self.assertTrue(line.startswith("systemctl --user --machine=dave@.host "), line)
        self.assertEqual(user["preview"]["implication"]["units"][0]["stampPath"],
                         str(self.box.ustamps / "stamp-buzz-pr-watch.timer"))
        self.box.clear_log()
        system = self.box.call(req("knowledge-digest", "resume", stage="preview"))
        for line in [line for line in self.box.log() if line.startswith("systemctl")]:
            self.assertRegex(line, r"^systemctl (show|disable|enable|start|stop) ")
            self.assertNotIn("--user", line)
            self.assertNotIn("--machine", line)
        self.assertEqual(system["preview"]["implication"]["units"][0]["stampPath"],
                         str(self.box.stamps / "stamp-knowledge-digest.timer"))
        self.assertEqual(system["preview"]["implication"]["lastTriggerAt"], "2026-09-06T09:04:00Z")


class EveryOutcomeReceipted(BrokerCase):  # (::broker-every-outcome-receipted)
    def test_one_valid_receipt_per_request_for_every_result(self):
        self.box.call(req("local-tier-eval", "pause"))
        self.box.call(req("nope", "pause"))
        self.box.call(req("knowledge-digest", "resume", stage="preview"))
        self.box.fail("augustus-content.timer")
        failed = self.box.call(req("augustus-content", "pause"))
        self.assertEqual(failed["result"], "failed", failed)
        self.assertEqual(failed["http_status"], 500)
        commands = failed["receipt"]["commands"]
        disable = [c for c in commands if "disable" in c["argv"]]
        self.assertEqual(len(disable), 1)
        self.assertEqual(disable[0]["exit"], 1)
        self.assertIn("fake failure", disable[0]["stderr"])
        self.assertIsNotNone(failed["receipt"]["after"])
        self.assertEqual(failed["receipt"]["after"]["state"], "active")
        files = self.box.receipt_files()
        self.assertEqual(len(files), 4)
        results = []
        for path in files:
            data = json.loads(path.read_text())
            self.assertEqual(broker.validate_receipt(data), [], path.name)
            self.assertEqual(set(data), set(broker.RECEIPT_KEYS), path.name)
            self.assertEqual(oct(path.stat().st_mode & 0o777), "0o644")
            self.assertTrue(all("exit" in c and isinstance(c["argv"], list) for c in data["commands"]))
            results.append(data["result"])
        self.assertEqual(sorted(results), ["applied", "failed", "previewed", "refused"])
        self.assertEqual(list(self.box.receipts.rglob("*.tmp")), [])
        self.assertEqual(list(self.box.receipts.rglob(".*")), [])
        applied = next(json.loads(p.read_text()) for p in files if p.parent.name == "local-tier-eval")
        self.assertTrue([c for c in applied["commands"] if "show" in c["argv"]])


class PeerGate(BrokerCase):  # (::broker-peer-gate)
    def screen(self, remote, local="100.86.82.16", peer_uids=None, **fields) -> dict:
        request = req("knowledge-digest", "pause", **fields)
        request["actor"] = {"kind": "screen", "remote": remote, "local": local, "label": f"dave via control-room from {remote}"}
        return self.box.call_socket(request, peer_uids=peer_uids)

    def test_peer_rules_in_screen_mode(self):
        self.assertRefused(self.screen("100.86.82.16"), "peer_denied", 403)
        self.assertRefused(self.screen("127.0.0.1"), "peer_denied", 403)
        self.assertRefused(self.screen(None), "peer_denied", 403)
        self.assertEqual(self.box.log(), [])
        allowed = self.screen("100.64.0.9")
        self.assertRefused(allowed, "state_conflict", 400)
        self.assertEqual(allowed["receipt"]["actor"]["kind"], "screen")
        self.assertEqual(allowed["receipt"]["actor"]["remote"], "100.64.0.9")
        self.assertEqual(allowed["receipt"]["actor"]["peer"]["uid"], os.getuid())
        self.assertEqual(allowed["receipt"]["actor"]["label"], "dave via control-room from 100.64.0.9")
        self.assertRefused(self.screen("127.0.0.1", local="127.0.0.1"), "state_conflict", 400)
        self.box.clear_log()
        denied = self.screen("100.64.0.9", peer_uids="99999")
        self.assertRefused(denied, "peer_denied", 403)
        self.assertEqual(self.box.log(), [])
        self.assertEqual(denied["receipt"]["actor"]["peer"]["uid"], os.getuid())
        self.assertIsNone(denied["receipt"]["before"])

    def test_pipe_mode_is_a_cli_actor(self):
        response = self.box.call(req("knowledge-digest", "pause"), env=self.box.env(SUDO_USER="dave"))
        self.assertEqual(response["receipt"]["actor"]["kind"], "cli")
        self.assertEqual(response["receipt"]["actor"]["user"], "dave")
        self.assertIsNone(response["receipt"]["actor"]["peer"])
        code, response = self.box.act("pause", "knowledge-digest", "--reason", "acceptance")
        self.assertEqual(code, 1)
        self.assertEqual(response["refusal"]["code"], "state_conflict")
        code, response = self.box.act("resume", "knowledge-digest", "--stage", "preview")
        self.assertEqual(code, 0)
        self.assertEqual(response["result"], "previewed")


class ConcurrencyLock(BrokerCase):  # (::broker-concurrency-lock)
    def test_two_concurrent_pauses_serialise_to_one_applied(self):
        results: list[dict] = []
        lock = threading.Lock()

        def worker() -> None:
            response = self.box.call(req("local-tier-eval", "pause"))
            with lock:
                results.append(response)

        threads = [threading.Thread(target=worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join(timeout=90)
        self.assertEqual(sorted(r["result"] for r in results), ["applied", "refused"])
        refused = next(r for r in results if r["result"] == "refused")
        self.assertEqual(refused["refusal"]["code"], "state_conflict")
        self.assertEqual(mutating(self.box.log()), ["systemctl disable --now local-tier-eval.timer --no-pager"])


class PeerRuleTable(unittest.TestCase):
    def test_peer_allowed_table(self):
        self.assertEqual(broker.peer_allowed("100.64.0.9", "100.86.82.16")[0], True)
        self.assertEqual(broker.peer_allowed("100.86.82.16", "100.86.82.16")[0], False)
        self.assertEqual(broker.peer_allowed("127.0.0.1", "100.86.82.16")[0], False)
        self.assertEqual(broker.peer_allowed(None, "100.86.82.16")[0], False)
        self.assertEqual(broker.peer_allowed("127.0.0.1", "127.0.0.1"), (True, "loopback-bound development instance"))


if __name__ == "__main__":
    unittest.main()
