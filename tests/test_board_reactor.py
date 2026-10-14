#!/usr/bin/env python3
"""bin/board_reactor.py against a temp board: a fake systemctl, a temp receipt root, a fake NOTIFY_SOCKET.

The pass tests drive Reactor.run_pass in-process with an explicit clock; the daemon tests run
the real process and watch what it sends systemd and what it starts.
"""
from __future__ import annotations

import contextlib
import datetime as dt
import importlib.util
import io
import json
import os
import pathlib
import signal
import socket
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


board = load("board")
board_reactor = load("board_reactor")
sd_notify = load("sd_notify")
workflow_receipt = load("workflow_receipt")

FAKE_SYSTEMCTL = """#!/bin/sh
echo "$*" >> "$FAKE_DIR/systemctl.log"
case "$1" in
  list-units) cat "$FAKE_DIR/active" 2>/dev/null; exit 0 ;;
  is-active) cat "$FAKE_DIR/daemon" 2>/dev/null || echo inactive; exit 0 ;;
esac
if [ -s "$FAKE_DIR/fail" ]; then cat "$FAKE_DIR/fail" >&2; exit 1; fi
exit 0
"""


class Box(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="reactor-test-"))
        self.saved = dict(os.environ)
        self.fake = self.tmp / "fake"
        self.fake.mkdir()
        for name, body in (("systemctl", FAKE_SYSTEMCTL),):
            path = self.fake / name
            path.write_text(body)
            path.chmod(0o755)
        env = {"BOARD_ROOT": self.tmp / "board", "BOARD_DECISIONS_ROOT": self.tmp / "decisions",
               "CONTROL_ROOM_RECEIPT_ROOT": self.tmp / "receipts", "BOARD_CANONICAL_CLONE": self.tmp / "clone",
               "BOARD_SYSTEMCTL": self.fake / "systemctl",
               "BOARD_REACTOR_BROKER_RECEIPTS": self.tmp / "broker", "FAKE_DIR": self.fake}
        os.environ.update({k: str(v) for k, v in env.items()})
        for name in ("BOARD_REACTOR_MAX_RUNS", "BOARD_REACTOR_DAILY_CAP", "BOARD_REACTOR_COOLDOWN", "NOTIFY_SOCKET"):
            os.environ.pop(name, None)
        (self.tmp / "decisions").mkdir()
        (self.tmp / "board" / "cards").mkdir(parents=True)
        self.clock = dt.datetime.now(dt.timezone.utc)

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        subprocess.run(["rm", "-rf", str(self.tmp)], check=False)

    def create(self, card_id: str) -> None:
        brief = self.tmp / f"{card_id}.md"
        brief.write_text(f"A synthetic idea for {card_id}")
        with contextlib.redirect_stdout(io.StringIO()):
            code = board.main(["create", "--title", card_id, "--brief", str(brief), "--owner", "claudius",
                               "--scope", "vault:05_knowledge", "--actor", "dave"])
        self.assertEqual(code, 0)

    def decide(self, decision: str, card_id: str, **extra) -> None:
        ts = (dt.datetime.now(dt.timezone.utc) + dt.timedelta(seconds=1)).isoformat().replace("+00:00", "Z")
        with (self.tmp / "decisions" / "decisions.jsonl").open("a") as handle:
            handle.write(json.dumps({"ts": ts, "decision": decision, "card": card_id, **extra}) + "\n")

    def reactor(self):
        return board_reactor.Reactor(board.board_root(), board.receipt_root())

    def run_pass(self, minutes: float = 0, judge: bool = True):
        return self.reactor().run_pass(self.clock + dt.timedelta(minutes=minutes), judge)

    def calls(self, verb: str) -> list[str]:
        log = self.fake / "systemctl.log"
        lines = log.read_text().splitlines() if log.exists() else []
        return [line for line in lines if line.startswith(verb + " ")]

    def receipt_files(self) -> list[dict]:
        found = [json.loads(p.read_text()) for p in (self.tmp / "receipts" / "board-reactor").glob("*.json")]
        for receipt in found:
            self.assertEqual(workflow_receipt.validate(receipt), [], receipt)
        return sorted(found, key=lambda r: (r["ended_at"], r["run_id"]))

    def receipts(self) -> list[str]:
        return [f"{r['state_change']['evidence']} | {r['terminal']['outcome']}: {r['terminal']['reason']}"
                for r in self.receipt_files()]

    def state(self) -> dict:
        return json.loads((self.tmp / "board" / "reactor" / "state.json").read_text())

    def set_active(self, *units: str) -> None:
        (self.fake / "active").write_text("".join(f"{u} loaded active running x\n" for u in units))

    def fail_with(self, text: str) -> None:
        (self.fake / "fail").write_text(text)


class Pass(Box):
    def test_a_new_card_starts_its_brief_unit(self):
        self.create("alpha")
        self.run_pass()
        self.assertEqual(self.calls("start"), ["start --no-block board-brief@alpha.service"])
        self.assertEqual(self.state()["count"], 1)
        self.assertTrue((self.tmp / "board" / "reactor" / "heartbeat").is_file())

    def test_a_restart_with_state_on_disk_never_starts_twice(self):
        self.create("alpha")
        self.run_pass()
        self.run_pass(minutes=1)
        self.assertEqual(len(self.calls("start")), 1)

    def test_an_active_unit_is_never_started_again(self):
        self.create("alpha")
        self.set_active("board-brief@alpha.service")
        self.run_pass(minutes=30)
        self.assertEqual(self.calls("start"), [])

    def test_an_approved_brief_starts_the_work_unit(self):
        self.create("alpha")
        view = board.view_of(board.board_root(), "alpha")
        self.decide("brief_approved", "alpha", brief_hash=view["brief_hash"])
        self.run_pass()
        self.assertEqual(self.calls("start"), ["start --no-block board-work@alpha.service"])

    def test_n_bounds_the_starts(self):
        for name in ("a", "b", "c"):
            self.create(name)
        self.set_active("board-work@zzz.service")
        self.run_pass()
        self.assertEqual(len(self.calls("start")), 1)

    def test_ok_flips_once(self):
        self.create("alpha")
        self.run_pass()
        self.run_pass(minutes=1)
        self.assertEqual(len(self.receipts()), 1)
        self.assertIn("health=ok", self.receipts()[0])


    def test_the_pass_derives_at_its_own_now(self):
        tomorrow = (self.clock.astimezone(board.box_tz()) + dt.timedelta(days=1)).date().isoformat()
        brief = self.tmp / "alpha.md"
        brief.write_text("A synthetic idea for alpha")
        with contextlib.redirect_stdout(io.StringIO()):
            board.main(["create", "--title", "alpha", "--brief", str(brief), "--owner", "claudius",
                        "--scope", "vault:05_knowledge", "--actor", "dave", "--research-on", f"{tomorrow}T06:00"])
        view = board.view_of(board.board_root(), "alpha")
        self.decide("brief_approved", "alpha", brief_hash=view["brief_hash"])
        due = dt.datetime.fromisoformat(f"{tomorrow}T06:01").replace(tzinfo=board.box_tz())
        self.reactor().run_pass(due)
        self.assertEqual(self.calls("start"), ["start --no-block board-work@alpha.service"])

    def test_the_pass_never_joins_the_canonical_clone(self):
        self.create("alpha")
        self.decide("approved", "alpha")
        (self.tmp / "clone").mkdir()
        saved = board.load_main
        board.load_main = lambda *_a: (_ for _ in ()).throw(AssertionError("main joined"))
        try:
            self.run_pass()
        finally:
            board.load_main = saved

    def test_the_watchdog_is_fed_after_observing_and_after_each_action(self):
        for name in ("a", "b"):
            self.create(name)
        ticks = []
        self.reactor().run_pass(self.clock, tick=lambda: ticks.append(1))
        self.assertEqual(len(ticks), 3)


class ErrorClasses(Box):
    def test_a_half_written_card_is_transient_not_a_crash(self):
        self.create("alpha")
        (self.tmp / "board" / "cards" / "alpha" / "card.json").write_text("")
        _wake, lines = self.run_pass()
        self.assertIn("observe -> transient ledger-unreadable", lines)
        self.assertIn("health=transient reason=ledger-unreadable", self.receipts()[-1])

    def test_a_transient_start_backs_off_and_is_receipted(self):
        self.create("alpha")
        self.fail_with("Job for board-brief@alpha.service failed.")
        self.run_pass()
        entry = self.state()["cards"]["alpha"]
        self.assertEqual((entry["starts"], entry["failures"]), (1, 1))
        self.assertIn("next_try", entry)
        self.assertIn("health=transient reason=systemctl-failed", self.receipts()[-1])
        self.assertNotIn("| failed", self.receipts()[-1])

    def test_three_failed_starts_quarantine_the_card(self):
        os.environ["BOARD_REACTOR_COOLDOWN"] = "0"
        self.create("alpha")
        self.fail_with("Job for board-brief@alpha.service failed.")
        for minutes in (0, 10, 30):
            self.run_pass(minutes)
        self.run_pass(60)
        view = board.view_of(board.board_root(), "alpha")
        self.assertEqual((view["column"], view["blocked_cause"]), ("Blocked", "held: poison-start"))
        self.assertEqual(len(self.calls("start")), 3)

    def test_unauthorised_is_permanent(self):
        self.create("alpha")
        self.fail_with("Failed to start board-brief@alpha.service: Access denied")
        with self.assertRaises(board_reactor.Permanent) as caught:
            self.run_pass()
        self.assertEqual(caught.exception.reason, "polkit-denied")

    def test_a_flip_receipt_is_the_reactor_producer_s_own(self):
        self.create("alpha")
        self.run_pass()
        receipt = self.receipt_files()[0]
        self.assertEqual((receipt["workflow_id"], receipt["unit"], receipt["vantage"], receipt["agent"]),
                         ("board-reactor", "board-reactor.service", "run", "claudius"))
        self.assertEqual(receipt["terminal"], {"outcome": "artifact", "reason": None})
        self.assertEqual((receipt["usage"]["status"], receipt["cost"]["status"]), ("unavailable", "unavailable"))

    def test_two_flips_in_one_second_are_two_receipts(self):
        state = board_reactor.State(self.tmp / "board" / "reactor")
        board_reactor.record_health(state, "transient", "systemctl-failed", self.clock)
        board_reactor.record_health(state, "ok", None, self.clock)
        self.assertEqual(len(self.receipt_files()), 2)

    def test_permanent_is_receipted_failed_by_the_daemon_path(self):
        board_reactor.fail(self.reactor(), "inotify-limit")
        self.assertIn("| failed: permanent: inotify-limit", self.receipts()[-1])


class Cap(Box):
    def test_the_cap_starts_what_is_left_and_alerts_once(self):
        os.environ["BOARD_REACTOR_DAILY_CAP"] = "1"
        for name in ("a", "b"):
            self.create(name)
        wake, _ = self.run_pass()
        self.run_pass(minutes=1)
        self.assertEqual(len(self.calls("start")), 1)
        capped = [r for r in self.receipts() if "health=capped" in r]
        self.assertEqual(len(capped), 1)
        self.assertIn("| failed: capped: daily-cap", capped[0])
        self.assertEqual(wake, board_reactor.next_midnight(self.clock))

    def test_the_count_resets_at_local_midnight(self):
        os.environ["BOARD_REACTOR_DAILY_CAP"] = "1"
        self.create("a")
        self.run_pass()
        self.create("b")
        tomorrow = board_reactor.next_midnight(self.clock) + dt.timedelta(minutes=1)
        self.reactor().run_pass(tomorrow)
        self.assertEqual(len(self.calls("start")), 2)


class DeleteRestore(Box):
    def test_a_deleted_running_card_is_stopped_then_trashed(self):
        self.create("alpha")
        self.decide("deleted", "alpha")
        self.set_active("board-brief@alpha.service")
        self.run_pass()
        self.assertEqual(self.calls("stop"), ["stop --no-block board-brief@alpha.service"])
        self.assertTrue((self.tmp / "board" / "cards" / "alpha").is_dir())
        self.set_active()
        self.run_pass(minutes=1)
        self.assertTrue((self.tmp / "board" / "trash" / "alpha" / "card.json").is_file())

    def test_a_refused_restore_backs_off(self):
        self.create("alpha")
        self.decide("deleted", "alpha")
        self.run_pass()
        time.sleep(1.1)
        self.decide("restored", "alpha")
        (self.tmp / "board" / "cards" / "alpha").mkdir()
        card = (self.tmp / "board" / "trash" / "alpha" / "card.json").read_text()
        (self.tmp / "board" / "cards" / "alpha" / "card.json").write_text(card)
        before = self.reactor().run_pass(self.clock + dt.timedelta(minutes=1))
        entry = self.state()["cards"]["trash:alpha"]
        self.assertEqual(entry["failures"], 1)
        _wake, again = self.reactor().run_pass(self.clock + dt.timedelta(minutes=1, seconds=5))
        self.assertFalse([line for line in again if line.startswith("restore")], (before, again))

    def test_a_purge_removes_only_the_card_it_names(self):
        trash = self.tmp / "board" / "trash"
        for name in ("old", "older"):
            self.create(name)
            self.decide("deleted", name)
        self.run_pass()
        later = dt.datetime.now(dt.timezone.utc) + dt.timedelta(days=31)
        self.assertTrue(board.purge_card(board.board_root(), "old", later))
        self.assertEqual(sorted(p.name for p in trash.iterdir()), ["older"])
        self.assertFalse(board.purge_card(board.board_root(), "older", self.clock))

    def test_a_restore_brings_it_back(self):
        self.create("alpha")
        self.decide("deleted", "alpha")
        self.run_pass()
        time.sleep(1.1)
        self.decide("restored", "alpha")
        self.run_pass(minutes=1)
        self.assertTrue((self.tmp / "board" / "cards" / "alpha" / "card.json").is_file())


class Once(Box):
    def once(self) -> tuple[int, str]:
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = board_reactor.main(["--once"])
        return code, out.getvalue()

    def test_a_dead_daemon_is_receipted_permanent_and_the_pass_still_runs(self):
        self.create("alpha")
        code, _out = self.once()
        self.assertEqual(code, 0)
        self.assertIn("| failed: permanent: daemon-dead", self.receipts()[0])
        self.assertEqual(len(self.calls("start")), 1)
        self.assertEqual(len(self.receipts()), 1)

    def test_an_operator_stop_is_a_pause(self):
        self.create("alpha")
        broker = self.tmp / "broker" / "board-reactor"
        broker.mkdir(parents=True)
        for i, action in enumerate(("start", "stop")):
            (broker / f"{i}.json").write_text(json.dumps({"action": action, "result": "applied",
                                                          "completed_at": f"2026-10-14T0{i}:00:00Z"}))
        code, out = self.once()
        self.assertEqual(code, 0)
        self.assertIn("paused", out)
        self.assertEqual((self.calls("start"), self.receipts()), ([], []))

    def test_a_refused_stop_is_no_pause(self):
        broker = self.tmp / "broker" / "board-reactor"
        broker.mkdir(parents=True)
        (broker / "0.json").write_text(json.dumps({"action": "stop", "result": "refused",
                                                   "completed_at": "2026-10-14T00:00:00Z"}))
        self.assertFalse(board_reactor.operator_paused())

    def test_a_dead_daemon_keeps_its_own_permanent_reason_and_does_not_page_again(self):
        board_reactor.fail(self.reactor(), "polkit-denied")
        self.create("alpha")
        self.fail_with("Failed to start: Access denied")
        code, _out = self.once()
        self.assertEqual(code, 0)
        self.assertEqual(len(self.receipts()), 1)
        self.assertIn("permanent: polkit-denied", self.receipts()[-1])

    def test_a_new_permanent_fault_in_the_reconcile_pages(self):
        self.create("alpha")
        self.fail_with("Failed to start: Access denied")
        code, _out = self.once()
        self.assertEqual(code, 2)
        self.assertIn("permanent: polkit-denied", self.receipts()[-1])
        self.assertEqual(self.once()[0], 0)

    def test_a_live_daemon_is_not_judged_by_the_reconcile(self):
        (self.fake / "daemon").write_text("active\n")
        self.create("alpha")
        self.once()
        self.assertEqual(self.receipts(), [])
        self.assertEqual(len(self.calls("start")), 1)


class Units(Box):
    def test_the_run_templates_ask_board_py_for_the_card_under_the_reactor_s_root(self):
        for name in ("board-brief@.service", "board-work@.service", "board-reactor.service",
                     "board-reconcile.service"):
            text = (ROOT / "systemd" / name).read_text()
            self.assertNotIn("ConditionPathExists=/var/lib/control-room-board", text, name)
            self.assertIn("EnvironmentFile=-/home/dave/.config/agent-workforce/board_reactor.env", text, name)
            self.assertIn("ExecCondition=/home/dave/agent-workforce/bin/board.py exists", text, name)

    def test_exists_answers_for_the_root_and_a_card(self):
        self.create("alpha")
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(board.main(["exists"]), 0)
            self.assertEqual(board.main(["exists", "alpha"]), 0)
            self.assertEqual(board.main(["exists", "beta"]), 1)
            os.environ["BOARD_ROOT"] = str(self.tmp / "nowhere")
            self.assertEqual(board.main(["exists"]), 1)


class Notify(unittest.TestCase):
    def test_the_ping_interval_is_under_half_the_watchdog(self):
        self.assertLess(sd_notify.watchdog_interval({"WATCHDOG_USEC": "60000000"}), 30)

    def test_no_watchdog_for_another_pid(self):
        self.assertIsNone(sd_notify.watchdog_interval({"WATCHDOG_USEC": "60000000", "WATCHDOG_PID": "1"}))

    def test_no_socket_is_a_no_op(self):
        self.assertFalse(sd_notify.notify("READY=1", {}))


class Daemon(Box):
    def start_daemon(self, sock_path: pathlib.Path, watchdog_usec: int):
        env = dict(os.environ, NOTIFY_SOCKET=str(sock_path), WATCHDOG_USEC=str(watchdog_usec))
        return subprocess.Popen([sys.executable, str(ROOT / "bin" / "board_reactor.py")], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    def test_ready_then_a_new_card_starts_within_five_seconds_and_pings_keep_pace(self):
        sock_path = self.tmp / "notify.sock"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(str(sock_path))
        sock.settimeout(10)
        proc = self.start_daemon(sock_path, 600_000)
        try:
            self.assertIn("READY=1", sock.recv(4096).decode())
            self.create("alpha")
            began = time.monotonic()
            while not self.calls("start") and time.monotonic() - began < 5:
                time.sleep(0.05)
            self.assertEqual(self.calls("start"), ["start --no-block board-brief@alpha.service"])
            pings = []
            while len(pings) < 6:
                if "WATCHDOG=1" in sock.recv(4096).decode():
                    pings.append(time.monotonic())
            gaps = [b - a for a, b in zip(pings, pings[1:])]
            self.assertLess(max(gaps), 0.3, gaps)
        finally:
            proc.send_signal(signal.SIGTERM)
            _out, err = proc.communicate(timeout=10)
            self.assertEqual(proc.returncode, 0, err.decode())
            sock.close()

    def test_an_idle_daemon_pings_without_passing(self):
        sock_path = self.tmp / "notify.sock"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(str(sock_path))
        sock.settimeout(10)
        proc = self.start_daemon(sock_path, 300_000)
        try:
            self.assertIn("READY=1", sock.recv(4096).decode())
            pings = 0
            while pings < 12:
                pings += "WATCHDOG=1" in sock.recv(4096).decode()
            self.assertLessEqual(len(self.calls("list-units")), 2)
        finally:
            proc.send_signal(signal.SIGTERM)
            proc.communicate(timeout=10)
            sock.close()

    def test_a_permanent_error_exits_non_zero(self):
        self.fail_with("Failed to start: Access denied")
        self.create("alpha")
        sock_path = self.tmp / "notify.sock"
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM)
        sock.bind(str(sock_path))
        proc = self.start_daemon(sock_path, 0)
        try:
            _out, err = proc.communicate(timeout=15)
            self.assertEqual(proc.returncode, 2)
            self.assertIn("polkit-denied", err.decode())
        finally:
            sock.close()


if __name__ == "__main__":
    unittest.main()
