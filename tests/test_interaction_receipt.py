#!/usr/bin/env python3
"""bin/interaction_receipt.py: one receipt per interactive turn, from the transcript it left.

Two modes, one writer. The Claude Code Stop hook reads hook-stdin.json on stdin and the
transcript it names (tests/fixtures/receipt-wiring/transcript-*.jsonl); `--codex-notify`
reads the argv payload and the rollout under CODEX_HOME (tests/fixtures/interaction/). The
unit comes from INTERACTION_RECEIPT_UNIT here — under systemd it is read from
/proc/self/cgroup. Every case asserts the exit status is 0: a hook that fails would block
the agent's Stop. Anchors are the `::` comments; tests/test_interaction_receipt.sh is the
gate entry point.
"""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIX = ROOT / "tests" / "fixtures" / "receipt-wiring"
CODEX = ROOT / "tests" / "fixtures" / "interaction"
HOOK = ROOT / "bin" / "interaction_receipt.py"

SESSION = "5e5e5e5e-5e5e-4e5e-8e5e-5e5e5e5e5e5e"
EVENT = "e0" * 32
THREAD = "0a0a0a0a-0a0a-7a0a-8a0a-0a0a0a0a0a0a"
TURN1, TURN2 = "0b0b0b0b-0b0b-4b0b-8b0b-0b0b0b0b0b01", "0b0b0b0b-0b0b-4b0b-8b0b-0b0b0b0b0b02"


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


receipt = load("workflow_receipt")
api = load("control_room_api")
sys.path.insert(0, str(ROOT / "bin"))
import interaction_turn as turn  # noqa: E402 — a dataclass module must be imported, not exec'd


class Sandbox:
    def __init__(self, tmp: pathlib.Path) -> None:
        self.home = tmp / "home"
        self.receipts = tmp / "receipts"
        self.log = self.home / "agent-workforce" / "logs" / "interaction_receipt.log"
        for path in (self.home, self.receipts):
            path.mkdir(parents=True)

    def env(self, unit: str | None = "buzz-agent@marcus.service", **extra: str) -> dict[str, str]:
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
               "CONTROL_ROOM_RECEIPT_ROOT": str(self.receipts),
               "INTERACTION_RECEIPT_HEARTBEAT_FILE": str(FIX / "heartbeat.prompt"),
               "SECRET_PROBE": "must-never-appear"}
        if unit:
            env["INTERACTION_RECEIPT_UNIT"] = unit
        env.update(extra)
        return env

    def stop_hook(self, transcript: str | None, unit: str | None = "buzz-agent@marcus.service",
                  stdin: str | None = None) -> subprocess.CompletedProcess:
        if stdin is None:
            payload = json.loads((FIX / "hook-stdin.json").read_text())
            payload["transcript_path"] = str(FIX / transcript) if transcript else "/nonexistent/transcript.jsonl"
            stdin = json.dumps(payload)
        return subprocess.run([sys.executable, str(HOOK)], input=stdin, env=self.env(unit),
                              capture_output=True, text=True, cwd=str(ROOT))

    def codex_notify(self, payload: str, unit: str | None = "buzz-agent@augustus.service",
                     codex_home: str | None = str(CODEX)) -> subprocess.CompletedProcess:
        extra = {"CODEX_HOME": codex_home} if codex_home else {}
        return subprocess.run([sys.executable, str(HOOK), "--codex-notify", payload], stdin=subprocess.DEVNULL,
                              env=self.env(unit, **extra), capture_output=True, text=True, cwd=str(ROOT))

    def receipt_files(self) -> list[str]:
        return sorted(str(p.relative_to(self.receipts)) for p in self.receipts.rglob("*.json"))

    def read(self, relative: str) -> dict:
        return json.loads((self.receipts / relative).read_text())

    def log_text(self) -> str:
        return self.log.read_text() if self.log.exists() else ""

    def reads_back_valid(self, workflow_id: str, run_id: str) -> None:
        model = api.ControlRoomReadModel(api.SourcePaths(ROOT, self.home / "agent-workforce", self.receipts))
        valid, malformed, errors = model.receipts()
        assert (malformed, errors) == ([], []), (malformed, errors)
        assert run_id in {v["run_id"] for v in valid}, (run_id, valid)
        runs, status = model.list_runs(workflow_id)
        assert run_id in {r["id"] for r in runs}, (workflow_id, run_id, runs)
        assert status["errors"]["malformedReceipts"] == [], status["errors"]


class StopHookTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="interaction-receipt-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.box = Sandbox(self.tmp)

    def test_send_is_artifact(self):
        # (::interaction-send-is-artifact)
        done = self.box.stop_hook("transcript-send.jsonl")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "", "a Stop hook that prints can alter the agent's stop")
        run_id = f"{SESSION}-a-3"
        self.assertEqual(self.box.receipt_files(), [f"buzz-agent@marcus/{run_id}.json"])
        got = self.box.read(f"buzz-agent@marcus/{run_id}.json")
        self.assertEqual(receipt.validate(got), [])
        self.assertEqual(got["workflow_id"], "buzz-agent@marcus")
        self.assertEqual(got["unit"], "buzz-agent@marcus")
        self.assertEqual(got["agent"], "marcus")
        self.assertEqual(got["vantage"], "interaction")
        self.assertEqual(got["model"], "claude-opus-5")
        self.assertEqual(got["terminal"], {"outcome": "artifact", "reason": None})
        self.assertEqual(got["artifact"]["uri"], f"nostr:event:{EVENT}")
        self.assertEqual(got["started_at"], "2026-09-14T09:10:00Z")
        self.assertEqual(got["ended_at"], "2026-09-14T09:10:11Z")
        self.assertEqual(got["assertions"], [])
        self.assertEqual(got["cost"]["status"], "unavailable")
        # (::receipt-reads-back-valid)
        self.box.reads_back_valid("buzz-agent@marcus", run_id)
        self.assertIn(f"buzz-agent@marcus {run_id} artifact", self.box.log_text())
        self.assertNotIn("must-never-appear", self.box.log_text() + done.stdout + done.stderr)

    def test_silence_is_decline(self):
        # (::interaction-silence-is-decline)
        done = self.box.stop_hook("transcript-silent.jsonl")
        self.assertEqual(done.returncode, 0, done.stderr)
        got = self.box.read(f"buzz-agent@marcus/{SESSION}-a-2.json")
        self.assertEqual(receipt.validate(got), [])
        self.assertEqual(got["terminal"]["outcome"], "decline")
        self.assertIn("no message published to Buzz in this turn", got["terminal"]["reason"])
        self.assertNotIn("artifact", got)

    def test_heartbeat_writes_nothing(self):
        # (::interaction-heartbeat-no-receipt)
        done = self.box.stop_hook("transcript-heartbeat.jsonl")
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.box.receipt_files(), [])
        self.assertIn("heartbeat", self.box.log_text())

    def test_usage_is_summed_over_the_turn(self):
        # (::interaction-usage-summed) — three assistant messages after the prompt, one of them
        # split over two records that share message.id and usage (counted once); the earlier
        # turn's 900/90 never enters
        self.box.stop_hook("transcript-send.jsonl")
        got = self.box.read(f"buzz-agent@marcus/{SESSION}-a-3.json")
        self.assertEqual(got["usage"], {"status": "measured", "input_tokens": 1200 + 1300 + 1400,
                                        "output_tokens": 40 + 60 + 20,
                                        "cache_tokens": (300 + 5000) + 6500 + 7800,
                                        "total_tokens": 3900 + 120 + 19600})

    def test_send_is_a_command_not_a_mention(self):
        # (::interaction-send-is-a-command) — a grep or an echo that names the string is not a
        # send; the invocation must sit in command position, path prefix allowed
        for command in ('buzz messages send --channel c --content hi', 'cd ~ && buzz messages send --channel c',
                        '~/.local/bin/buzz messages send --channel c', 'out=$(buzz messages send --channel c)',
                        'buzz feed get --limit 5; buzz messages send --channel c'):
            self.assertTrue(turn.is_send(command), command)
        for command in ('grep -n "buzz messages send" ~/x.log', 'echo "buzz messages send"',
                        'buzz messages get --channel c', 'buzz messages sender'):
            self.assertFalse(turn.is_send(command), command)

    def test_never_blocks_stop(self):
        # (::interaction-never-blocks-stop)
        cases = {
            "malformed stdin": dict(transcript=None, stdin="{not json"),
            "empty stdin": dict(transcript=None, stdin=""),
            "missing transcript": dict(transcript=None),
            "no unit known": dict(transcript="transcript-send.jsonl", unit=None),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                done = self.box.stop_hook(**kwargs)
                self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")
                self.assertEqual(done.stdout, "")
        self.assertEqual(self.box.receipt_files(), [])
        self.assertEqual(len(self.box.log_text().splitlines()), len(cases))
        # an unwritable receipt root: still exit 0, one more log line, nothing on stdout
        root = self.tmp / "unwritable"
        root.mkdir()
        root.chmod(0o500)
        self.addCleanup(root.chmod, 0o700)
        payload = json.loads((FIX / "hook-stdin.json").read_text())
        payload["transcript_path"] = str(FIX / "transcript-send.jsonl")
        env = self.box.env()
        env["CONTROL_ROOM_RECEIPT_ROOT"] = str(root)
        done = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(payload), env=env,
                              capture_output=True, text=True, cwd=str(ROOT))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "")
        self.assertEqual(len(self.box.log_text().splitlines()), len(cases) + 1)
        self.assertIn("not written", self.box.log_text().splitlines()[-1])


class CodexNotifyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="interaction-receipt-"))
        self.addCleanup(shutil.rmtree, self.tmp, ignore_errors=True)
        self.box = Sandbox(self.tmp)
        self.payload = (CODEX / "codex-notify.json").read_text()
        self.silent = (CODEX / "codex-notify-silent.json").read_text()

    def test_send_is_artifact(self):
        # (::codex-notify-send-is-artifact)
        done = self.box.codex_notify(self.payload)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(done.stdout, "")
        run_id = f"{THREAD}-{TURN2}"
        self.assertEqual(self.box.receipt_files(), [f"buzz-agent@augustus/{run_id}.json"])
        got = self.box.read(f"buzz-agent@augustus/{run_id}.json")
        self.assertEqual(receipt.validate(got), [])
        self.assertEqual(got["unit"], "buzz-agent@augustus")
        self.assertEqual(got["agent"], "augustus")
        self.assertEqual(got["vantage"], "interaction")
        self.assertEqual(got["model"], "gpt-5.5")
        self.assertEqual(got["terminal"], {"outcome": "artifact", "reason": None})
        self.assertEqual(got["artifact"]["uri"], f"nostr:event:{EVENT}")
        self.assertEqual(got["started_at"], "2026-09-14T09:30:00Z")
        self.assertEqual(got["ended_at"], "2026-09-14T09:30:07Z")
        # (::receipt-reads-back-valid)
        self.box.reads_back_valid("buzz-agent@augustus", run_id)

    def test_silence_is_decline(self):
        # (::codex-notify-silence-is-decline)
        done = self.box.codex_notify(self.silent)
        self.assertEqual(done.returncode, 0, done.stderr)
        got = self.box.read(f"buzz-agent@augustus/{THREAD}-{TURN1}.json")
        self.assertEqual(receipt.validate(got), [])
        self.assertEqual(got["terminal"]["outcome"], "decline")
        self.assertIn("no message published to Buzz in this turn", got["terminal"]["reason"])
        self.assertEqual(got["usage"], {"status": "measured", "input_tokens": 2000, "output_tokens": 120,
                                        "cache_tokens": 1500, "total_tokens": 2120})

    def test_usage_from_rollout(self):
        # (::codex-notify-usage-from-rollout) — the turn's share of the thread total: the last
        # token_count inside the span minus the last one before it, so a two-response turn is
        # not reported as its final response alone
        self.box.codex_notify(self.payload)
        got = self.box.read(f"buzz-agent@augustus/{THREAD}-{TURN2}.json")
        self.assertEqual(got["usage"], {"status": "measured", "input_tokens": 4500, "output_tokens": 260,
                                        "cache_tokens": 3700, "total_tokens": 4760})
        self.assertEqual(got["cost"]["status"], "unavailable")

    def test_missing_rollout_is_unavailable(self):
        # (::codex-notify-missing-rollout-unavailable)
        payload = json.loads(self.payload)
        payload["thread-id"] = "0f0f0f0f-0f0f-7f0f-8f0f-0f0f0f0f0f0f"
        done = self.box.codex_notify(json.dumps(payload))
        self.assertEqual(done.returncode, 0, done.stderr)
        got = self.box.read(f"buzz-agent@augustus/{payload['thread-id']}-{TURN2}.json")
        self.assertEqual(receipt.validate(got), [])
        self.assertEqual(got["usage"]["status"], "unavailable")
        self.assertIsNone(got["usage"]["total_tokens"])
        self.assertEqual(got["terminal"]["outcome"], "decline")
        self.assertIn("rollout not found", got["terminal"]["reason"])

    def test_heartbeat_writes_nothing(self):
        # (::interaction-heartbeat-no-receipt) — input-messages[0] equal to the heartbeat file
        payload = json.loads(self.payload)
        payload["input-messages"] = [(FIX / "heartbeat.prompt").read_text()]
        done = self.box.codex_notify(json.dumps(payload))
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.box.receipt_files(), [])

    def test_never_fails(self):
        # (::codex-notify-never-fails)
        cases = {
            "malformed argument": dict(payload="{not json"),
            "wrong type": dict(payload=json.dumps({"type": "something-else"})),
            "no CODEX_HOME": dict(payload=self.payload, codex_home=None),
            "no unit known": dict(payload=self.payload, unit=None),
        }
        for name, kwargs in cases.items():
            with self.subTest(name):
                done = self.box.codex_notify(**kwargs)
                self.assertEqual(done.returncode, 0, f"{name}: {done.stderr}")
                self.assertEqual(done.stdout, "")
        # no CODEX_HOME still receipts the turn — the payload alone decides silence honestly
        self.assertEqual(self.box.receipt_files(), [f"buzz-agent@augustus/{THREAD}-{TURN2}.json"])
        self.assertEqual(self.box.read(f"buzz-agent@augustus/{THREAD}-{TURN2}.json")["usage"]["status"], "unavailable")
        self.assertEqual(len(self.box.log_text().splitlines()), len(cases))
        self.assertNotIn("must-never-appear", self.box.log_text())


if __name__ == "__main__":
    unittest.main()
