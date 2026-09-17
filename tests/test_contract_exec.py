#!/usr/bin/env python3
"""Fixture suite for bin/contract_exec.py, the T5.1 contract executor.

Each test method carries the `::` anchor design/fleet-suites.toml declares for it, so the
W9 join in tests/test_workflow_coverage.py reads the ids from here, not from the wrapper.

The knowledge-digest scenarios run the LIVE design/contracts/knowledge-digest.md against a
sandbox: a git inbox worktree, a vault directory, a per-run attempt log and fake `systemctl`
and `journalctl` copied from tests/fixtures/contract-exec/bin/ onto the front of PATH. The
executor is driven as a subprocess with a parent environment that carries SECRET_PROBE, so
the environment rule is tested from outside rather than trusted from inside.
"""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "contract-exec"
EXECUTOR = ROOT / "bin" / "contract_exec.py"
SCHEMA_DOC = ROOT / "design" / "contract-schema.md"
ENVELOPE = FIXTURES / "claude-json-envelope.json"
BASH_OWN = {"_", "PWD", "SHLVL", "OLDPWD"}
UTC = dt.timezone.utc


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


checks = load("contract_checks")
receipt = load("workflow_receipt")
api = load("control_room_api")

KD_IDS = ["artifact-is-this-run", "decline-is-this-runs-own", "body-under-500-words",
          "names-weekly-pre-assembly", "write-boundary-held", "cited-paths-resolve",
          "not-lock-skipped", "timer-fired-this-week", "vault-guard-passed"]
KD_SWEEP = {"not-lock-skipped", "timer-fired-this-week"}

DIGEST = """# Knowledge digest {date}

This is the *knowledge* digest, a git-log delta over 05_knowledge/ and 11_entities/. It does
not replace weekly-pre-assembly, which is the activity pre-read.

- [[05_knowledge/note]] landed this week.

## Confidence & gaps

none
"""
RESEARCH = """# Standing research {date}

## Task
Weekly scan.

## Key findings (fact vs inference labeled)
**Rates moved** — {fact} the index closed up ([source](https://example.test/a)). {inference} the move is transient.

## Contradictions
none found this run

## Proposed vault change (target canonical file + exact content)
target: vault
- 05_knowledge/note.md: append one line.

## Confidence & gaps
medium
"""
GUARD_OK = "vault_sync_guard[check]: OK: mirror clean and current\n"
DECLINE = "DECLINE: no 05_knowledge/ or 11_entities/ changes in the last 7 days\n"


class Sandbox:
    """One run's worth of box state under a temp dir, plus the executor invocation."""

    def __init__(self, tmp: pathlib.Path):
        self.root = tmp
        self.home = tmp / "home"
        self.inbox = self.home / "agent-worktrees" / "inbox"
        self.vault = tmp / "vault"
        self.fakebin = tmp / "fakebin"
        self.state = self.fakebin / "state"
        self.receipts = tmp / "receipts"
        self.logs = tmp / "logs" / "last-attempt"
        self.run_date = "2026-09-11"
        self.started = int(dt.datetime(2026, 9, 11, 7, 20, tzinfo=UTC).timestamp())
        self.now = dt.datetime.fromtimestamp(self.started + 600, UTC)
        for path in (self.inbox / "_inbox" / "agents", self.vault / "05_knowledge",
                     self.state, self.receipts, self.logs):
            path.mkdir(parents=True)
        (self.vault / "05_knowledge" / "note.md").write_text("a note\n")
        for tool in ("systemctl", "journalctl"):
            shutil.copy(FIXTURES / "bin" / tool, self.fakebin / tool)
        (self.inbox / "_inbox" / "agents" / ".keep").write_text("")
        self.commits = 0
        self.git("init", "-q")
        self.commit("init")

    def git(self, *args):
        env = {"PATH": os.environ["PATH"], "HOME": str(self.home),
               "GIT_AUTHOR_NAME": "fixture", "GIT_AUTHOR_EMAIL": "fixture@example",
               "GIT_COMMITTER_NAME": "fixture", "GIT_COMMITTER_EMAIL": "fixture@example"}
        subprocess.run(["git", "-C", str(self.inbox), *args], check=True,
                       capture_output=True, env=env)

    def commit(self, message):
        """Stage everything and commit — each artifact write carries a unique marker line, so
        the artifact and any stray file written beside it always land in ONE commit, which is
        what check 5 (write-boundary-held) resolves by path."""
        self.commits += 1
        self.git("add", "-A")
        self.git("commit", "-q", "--allow-empty", "-m", f"{message} ({self.commits})")

    def attempt_log(self, unit="knowledge-digest"):
        return self.logs / f"{unit}.log"

    def write_attempt_log(self, text, unit="knowledge-digest", fresh=True):
        path = self.attempt_log(unit)
        path.write_text(text)
        stamp = self.started + 30 if fresh else self.started - 3600
        os.utime(path, (stamp, stamp))
        return path

    def write_artifact(self, body=None, fresh=True, stray=False, rel=None):
        rel = rel or f"_inbox/agents/{self.run_date}_knowledge-digest.md"
        path = self.inbox / rel
        text = body if body is not None else DIGEST.format(date=self.run_date)
        # The marker grows by one byte per write: every write gets the same forced mtime, and
        # git's index trusts matching stat data (size + mtime) without re-hashing, so an
        # equal-length change would be invisible to `git add` and the commit would miss it.
        path.write_text(f"{text}\n<!-- write {'.' * (self.commits + 1)} -->\n")
        stamp = self.started + 60 if fresh else self.started - 3600
        os.utime(path, (stamp, stamp))
        if stray:
            (self.inbox / "stray.txt").write_text(f"outside the boundary {self.commits + 1}\n")
        self.commit(f"add {rel}")
        return path

    def set_state(self, name, value):
        (self.state / name).write_text(value + "\n")

    def run(self, unit, vantage, *extra, env=None, schema_doc=None):
        cmd = [sys.executable, str(EXECUTOR), unit, "--vantage", vantage,
               "--repo-root", str(ROOT), "--manifest-dir", str(FIXTURES / "agents"),
               "--schema-doc", str(schema_doc or SCHEMA_DOC),
               "--receipt-root", str(self.receipts), "--attempt-log", str(self.attempt_log(unit)),
               "--inbox-worktree", str(self.inbox), "--vault", str(self.vault),
               "--home", str(self.home), "--now", self.now.isoformat(),
               "--run-started-at", str(self.started), "--run-date", self.run_date, *extra]
        parent = {"PATH": f"{self.fakebin}:{os.environ['PATH']}", "SECRET_PROBE": "leaked",
                  "HOME": os.environ.get("HOME", str(self.home))}
        parent.update(env or {})
        done = subprocess.run(cmd, capture_output=True, text=True, env=parent)
        written = None
        for line in done.stdout.splitlines():
            if line.startswith("receipt: "):
                written = json.loads(pathlib.Path(line[len("receipt: "):]).read_text())
        return done, written


def by_id(written):
    return {a["id"]: a for a in written["assertions"]}


class ContractExecTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.box = Sandbox(pathlib.Path(self.temp.name))

    def tearDown(self):
        self.temp.cleanup()

    def healthy_run(self, **kwargs):
        self.box.write_attempt_log(GUARD_OK + "digest written\n")
        self.box.write_artifact()
        return self.box.run("knowledge-digest", "run", "--artifact",
                            f"file://{self.box.inbox}/_inbox/agents/{self.box.run_date}_knowledge-digest.md",
                            **kwargs)

    def test_one_result_per_check(self):  # (::exec-one-result-per-check)
        done, written = self.healthy_run()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual([a["id"] for a in written["assertions"]], KD_IDS)
        for assertion in written["assertions"]:
            if assertion["id"] in KD_SWEEP:
                self.assertEqual(assertion["when"], "sweep")
                self.assertEqual(assertion["status"], "not_applicable")
                self.assertEqual(assertion["reason"], "vantage")
            else:
                self.assertEqual(assertion["when"], "run")
                self.assertNotEqual(assertion.get("reason"), "vantage")
            self.assertIn("output", assertion)
        self.box.set_state("LastTriggerUSec", f"@{int(time.time()) - 3600}")
        self.box.set_state("InvocationID", "deadbeef")
        self.box.set_state("journal.txt", "Started knowledge-digest.service")
        done, written = self.box.run("knowledge-digest", "sweep", "--state-change", "timer fired")
        self.assertEqual([a["id"] for a in written["assertions"]], KD_IDS)
        vantage_na = {a["id"] for a in written["assertions"] if a.get("reason") == "vantage"}
        self.assertEqual(vantage_na, set(KD_IDS) - KD_SWEEP)

    def test_env_is_schema_list(self):  # (::exec-env-is-schema-list)
        schema = checks.executor_environment(SCHEMA_DOC)
        self.assertIn("VAULT", schema)
        self.box.write_attempt_log("probe\n", unit="env-probe")
        done, written = self.box.run("env-probe", "run", "--artifact", "file:///probe")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        got = by_id(written)
        self.assertEqual(got["secret-probe"]["status"], "passed")
        self.assertEqual(got["sweep-only"]["status"], "not_applicable")
        dump = dict(line.split("=", 1) for line in got["env-dump"]["output"].splitlines() if "=" in line)
        self.assertEqual(set(dump) - BASH_OWN, set(schema) | {"PATH"})
        self.assertNotIn("SECRET_PROBE", dump)
        self.assertEqual(dump["SYSTEMCTL"], "systemctl --user")
        self.assertEqual(dump["JOURNALCTL"], "journalctl --user")
        self.assertEqual(dump["UNIT"], "env-probe")
        self.assertEqual(dump["VAULT"], str(self.box.vault.resolve()))
        self.assertEqual(dump["AGENT_INBOX_DIR"], f"{self.box.inbox}/_inbox/agents")
        self.assertEqual(dump["INBOX_WORKTREE"], str(self.box.inbox))
        self.assertEqual(dump["HOME"], str(self.box.home))
        self.assertEqual(dump["RUN_DATE"], self.box.run_date)
        self.assertEqual(dump["AGENT_RUN_STARTED_AT"], str(self.box.started))
        self.assertEqual(dump["AGENT_ATTEMPT_LOG"], str(self.box.attempt_log("env-probe")))

        self.box.set_state("LastTriggerUSec", f"@{int(time.time()) - 3600}")
        self.box.set_state("journal.txt", "")
        self.box.write_attempt_log(GUARD_OK)
        self.box.run("knowledge-digest", "sweep", "--state-change", "timer fired")
        calls = (self.box.state / "calls.log").read_text().splitlines()
        self.assertTrue(calls and all(c.startswith("system ") for c in calls), calls)

        trimmed = pathlib.Path(self.temp.name) / "schema-without-vault.md"
        trimmed.write_text("".join(ln for ln in SCHEMA_DOC.read_text().splitlines(True)
                                   if not ln.startswith("- `VAULT`")))
        self.assertNotIn("VAULT", checks.executor_environment(trimmed))
        done, written = self.box.run("env-probe", "run", "--artifact", "file:///probe",
                                     schema_doc=trimmed)
        dump = dict(line.split("=", 1) for line in by_id(written)["env-dump"]["output"].splitlines() if "=" in line)
        self.assertNotIn("VAULT", dump)
        self.assertEqual(set(dump) - BASH_OWN, set(checks.executor_environment(trimmed)) | {"PATH"})

    def test_artifact_is_this_run(self):  # (::exec-artifact-is-this-run)
        done, written = self.healthy_run()
        self.assertEqual(by_id(written)["artifact-is-this-run"]["status"], "passed")
        self.box.write_attempt_log(GUARD_OK)
        self.box.write_artifact(fresh=False)
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///stale")
        self.assertEqual(by_id(written)["artifact-is-this-run"]["status"], "failed")
        self.assertEqual(written["terminal"]["outcome"], "failed")

    def test_decline_is_own(self):  # (::exec-decline-is-own)
        self.box.write_attempt_log(GUARD_OK + DECLINE)
        done, written = self.box.run("knowledge-digest", "run")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(by_id(written)["decline-is-this-runs-own"]["status"], "passed")
        self.assertEqual(by_id(written)["artifact-is-this-run"]["status"], "not_applicable")
        self.assertEqual(written["terminal"]["outcome"], "decline")
        self.assertIn(DECLINE.strip(), written["terminal"]["reason"])

        self.box.write_attempt_log(GUARD_OK + DECLINE, fresh=False)
        done, written = self.box.run("knowledge-digest", "run")
        self.assertEqual(by_id(written)["decline-is-this-runs-own"]["status"], "failed")
        self.assertEqual(written["terminal"]["outcome"], "failed")

        self.box.write_attempt_log(GUARD_OK)
        self.box.write_attempt_log(GUARD_OK + DECLINE, unit="other-job")
        done, written = self.box.run("knowledge-digest", "run")
        self.assertEqual(by_id(written)["decline-is-this-runs-own"]["status"], "failed")
        self.assertEqual(written["terminal"]["outcome"], "failed")

    def test_write_boundary(self):  # (::exec-write-boundary)
        done, written = self.healthy_run()
        self.assertEqual(by_id(written)["write-boundary-held"]["status"], "passed")
        self.box.write_attempt_log(GUARD_OK)
        self.box.write_artifact(stray=True)
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x")
        self.assertEqual(by_id(written)["write-boundary-held"]["status"], "failed")

    def sweep(self, trigger, journal):
        self.box.set_state("LastTriggerUSec", trigger)
        self.box.set_state("InvocationID", "cafe0001")
        self.box.set_state("journal.txt", journal)
        self.box.write_attempt_log(GUARD_OK)
        done, written = self.box.run("knowledge-digest", "sweep", "--state-change", "swept")
        return by_id(written)

    def test_lock_skip(self):  # (::exec-lock-skip)
        recent = f"@{int(time.time()) - 3600}"
        got = self.sweep(recent, "Started knowledge-digest.service\nSKIP: previous run still active\n")
        self.assertEqual(got["not-lock-skipped"]["status"], "failed")
        got = self.sweep(recent, "Started knowledge-digest.service\n")
        self.assertEqual(got["not-lock-skipped"]["status"], "passed")
        got = self.sweep("n/a", "")
        self.assertEqual(got["not-lock-skipped"]["status"], "failed")
        self.assertIn("the timer has never fired", got["not-lock-skipped"]["output"])

    def test_timer_window(self):  # (::exec-timer-window)
        got = self.sweep(f"@{int(time.time()) - 3600}", "")
        self.assertEqual(got["timer-fired-this-week"]["status"], "passed")
        got = self.sweep(f"@{int(time.time()) - 10 * 86400}", "")
        self.assertEqual(got["timer-fired-this-week"]["status"], "failed")
        got = self.sweep("n/a", "")
        self.assertEqual(got["timer-fired-this-week"]["status"], "failed")

    def test_input_freshness(self):  # (::exec-input-freshness)
        done, written = self.healthy_run()
        self.assertEqual(by_id(written)["vault-guard-passed"]["status"], "passed")
        self.box.write_attempt_log("vault_sync_guard[check]: REFUSING to run: mirror is 3 days stale\n")
        self.box.write_artifact()
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x")
        self.assertEqual(by_id(written)["vault-guard-passed"]["status"], "failed")
        self.box.write_attempt_log("digest written, no guard line\n")
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x")
        self.assertEqual(by_id(written)["vault-guard-passed"]["status"], "failed")

    def test_outcome_is_exactly_one(self):  # (::exec-outcome-is-exactly-one)
        self.box.write_attempt_log(GUARD_OK + "nothing produced\n")
        done, written = self.box.run("knowledge-digest", "run")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(written["terminal"]["outcome"], "failed")
        self.assertTrue(written["terminal"]["reason"].startswith("neither artifact nor decline"),
                        written["terminal"])

        done, written = self.healthy_run()
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(written["terminal"], {"outcome": "artifact", "reason": None})
        self.assertTrue(all(a["status"] != "failed" for a in written["assertions"]))

        self.box.write_attempt_log(GUARD_OK)
        self.box.write_artifact(body="# title\n" + "word " * 600)
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x")
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(written["terminal"]["outcome"], "failed")
        self.assertIn("body-under-500-words", written["terminal"]["reason"])

        done, written = self.box.run("knowledge-digest", "run", "--skipped", "lock held")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(written["terminal"], {"outcome": "skipped", "reason": "lock held"})
        self.assertEqual(written["assertions"], [])

        self.assertIsInstance(written["terminal"]["outcome"], str)
        two = dict(written, terminal={"outcome": ["artifact", "decline"]})
        self.assertTrue(receipt.validate(two))
        none = dict(written, terminal={})
        self.assertTrue(receipt.validate(none))

    def test_receipt_validates(self):  # (::exec-receipt-validates)
        done, kd = self.healthy_run()
        self.box.write_attempt_log("probe\n", unit="logical-child")
        done, child = self.box.run("logical-child", "run", "--artifact", "file:///child")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(child["workflow_id"], "logical-parent")
        self.assertEqual(child["unit"], "logical-child")
        self.assertEqual(child["agent"], "fixture")
        self.assertEqual(kd["workflow_id"], "knowledge-digest")
        self.assertEqual(kd["model"], "claude-opus-5")
        for written in (kd, child):
            self.assertEqual(receipt.validate(written), [])
            path = self.box.receipts / written["workflow_id"] / f"{written['run_id']}.json"
            self.assertTrue(path.is_file(), path)
        model = api.ControlRoomReadModel(api.SourcePaths(ROOT, self.box.root, self.box.receipts))
        valid, malformed, errors = model.receipts()
        self.assertEqual(malformed, [])
        self.assertEqual(errors, [])
        self.assertEqual({v["run_id"] for v in valid}, {kd["run_id"], child["run_id"]})

        root = pathlib.Path(self.temp.name) / "partial"
        broken = dict(kd, extra={"a set is not JSON"})
        with self.assertRaises(TypeError):
            receipt.write(broken, root)
        self.assertEqual([p for p in root.rglob("*") if p.is_file()], [])
        with self.assertRaises(ValueError):
            receipt.write(dict(kd, terminal={}), root)
        self.assertEqual([p for p in root.rglob("*") if p.is_file()], [])

    def test_run_identity(self):  # (::exec-run-identity)
        done, written = self.healthy_run(env={"INVOCATION_ID": "abc123"})
        self.assertEqual(written["run_id"], "abc123")
        done, written = self.healthy_run()
        self.assertEqual(written["run_id"], f"knowledge-digest-{self.box.started}")
        self.sweep(f"@{int(time.time()) - 3600}", "")
        self.assertTrue((self.box.receipts / "knowledge-digest" / "cafe0001.json").is_file())
        self.assertEqual(written["started_at"], "2026-09-11T07:20:00Z")
        self.assertEqual(written["ended_at"], "2026-09-11T07:30:00Z")

    def test_usage_never_zero(self):  # (::exec-usage-never-zero)
        done, written = self.healthy_run()
        self.assertEqual(written["usage"], receipt.unavailable_usage())
        self.assertEqual(written["cost"], receipt.unavailable_cost())
        self.assertIsNone(written["usage"]["input_tokens"])
        self.assertIsNone(written["cost"]["amount"])

        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x",
                                     "--usage-json", str(ENVELOPE))
        self.assertEqual(written["usage"], {"status": "measured", "input_tokens": 10, "output_tokens": 92,
                                            "cache_tokens": 39997, "total_tokens": 40099})
        self.assertEqual(written["cost"], {"status": "measured", "amount": 0.0555477, "currency": "USD",
                                           "source": "claude-code", "confidence": "list"})
        self.assertEqual(written["model"], "claude-haiku-4-5-20251001")

        empty = pathlib.Path(self.temp.name) / "empty-usage.json"
        empty.write_text(json.dumps({"usage": {}, "total_cost_usd": 0.0}))
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x",
                                     "--usage-json", str(empty))
        self.assertEqual(written["usage"]["status"], "unavailable")
        self.assertEqual(written["model"], "claude-opus-5")
        serialised = json.dumps(written["usage"])
        self.assertNotIn("0", serialised.replace("unavailable", ""))

        for bad in ("", "{not json", '{"usage": "nope"}'):
            garbage = pathlib.Path(self.temp.name) / "garbage.json"
            garbage.write_text(bad)
            done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x",
                                         "--usage-json", str(garbage))
            self.assertEqual(written["usage"], receipt.unavailable_usage(), bad)
            self.assertEqual(written["cost"], receipt.unavailable_cost(), bad)
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x",
                                     "--usage-json", str(pathlib.Path(self.temp.name) / "missing.json"))
        self.assertEqual(written["usage"], receipt.unavailable_usage())

        usage, cost, model = receipt.usage_from_claude_code(json.loads(ENVELOPE.read_text()))
        self.assertEqual(usage["total_tokens"], 40099)
        self.assertEqual(cost["amount"], 0.0555477)
        self.assertEqual(model, "claude-haiku-4-5-20251001")
        two = json.loads(ENVELOPE.read_text())
        two["modelUsage"]["claude-sonnet-5"] = {"costUSD": 0.41, "costBasis": "list"}
        usage, cost, model = receipt.usage_from_claude_code(two)
        self.assertEqual(model, "claude-sonnet-5", "the costliest model, not the first key")
        self.assertEqual(cost["confidence"], "list")
        usage, cost, model = receipt.usage_from_claude_code(
            {"usage": {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0,
                       "cache_read_input_tokens": 0}})
        self.assertEqual(usage["total_tokens"], 0)
        self.assertEqual(cost, receipt.unavailable_cost())

    def test_next_action_from_contract(self):  # (::exec-next-action-from-contract)
        done, written = self.healthy_run()
        self.assertEqual(written["next_action"]["actor"], "Dave, from the Mac.")
        self.assertTrue(written["next_action"]["action"].startswith("read the digest and decide"))
        self.box.write_attempt_log("probe\n", unit="logical-child")
        done, written = self.box.run("logical-child", "run", "--artifact", "file:///child")
        self.assertEqual(written["next_action"], {"actor": None, "action": None})

    def research_run(self, fact, inference):
        rel = f"_inbox/agents/{self.box.run_date}_standing-research.md"
        self.box.write_attempt_log("research written\n", unit="agent-proposal")
        self.box.write_artifact(RESEARCH.format(date=self.box.run_date, fact=fact, inference=inference),
                                rel=rel)
        return self.box.run("agent-proposal", "run", "--artifact", f"file://{self.box.inbox}/{rel}")

    def test_claims_labelled_in_producer_form(self):  # (::exec-claims-labelled-producer-form)
        for fact, inference in (("FACT:", "INFERENCE:"), ("**FACT**", "**INFERENCE:**"), ("**FACT:**", "**INFERENCE**")):
            done, written = self.research_run(fact, inference)
            self.assertEqual(by_id(written)["claims-are-labelled"]["status"], "passed", (fact, written))
        done, written = self.research_run("", "")
        self.assertEqual(by_id(written)["claims-are-labelled"]["status"], "failed")
        self.assertEqual(written["terminal"]["outcome"], "failed")

    def test_failed_flag(self):  # (::exec-failed-flag)
        done, written = self.healthy_run()
        self.assertEqual(written["terminal"]["outcome"], "artifact")
        self.box.write_attempt_log(GUARD_OK + "digest written\n")
        self.box.write_artifact()
        done, written = self.box.run("knowledge-digest", "run", "--failed", "BLOCKED: guard refused",
                                     "--artifact", "file:///x")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(written["terminal"]["outcome"], "failed")
        self.assertTrue(written["terminal"]["reason"].startswith("BLOCKED: guard refused"),
                        written["terminal"])
        self.assertEqual([a["id"] for a in written["assertions"]], KD_IDS)
        self.assertEqual(receipt.validate(written), [])

    def test_decline_flag(self):  # (::exec-decline-flag)
        self.box.write_attempt_log("no sentinel here\n", unit="logical-child")
        done, written = self.box.run("logical-child", "run", "--decline", "dispatch: augustus declined")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(written["terminal"], {"outcome": "decline", "reason": "dispatch: augustus declined"})
        self.assertEqual(by_id(written)["attempt-log-exists"]["status"], "passed")
        self.assertEqual(receipt.validate(written), [])
        done, written = self.box.run("logical-child", "run", "--decline", "x", "--failed", "y")
        self.assertEqual(written["terminal"]["outcome"], "failed")
        self.assertTrue(written["terminal"]["reason"].startswith("y"), written["terminal"])

    def test_run_id_flag(self):  # (::exec-run-id-flag)
        done, written = self.healthy_run(env={"INVOCATION_ID": "abc123"})
        self.assertEqual(written["run_id"], "abc123")
        self.box.write_attempt_log(GUARD_OK + "digest written\n")
        self.box.write_artifact()
        done, written = self.box.run("knowledge-digest", "run", "--artifact", "file:///x",
                                     "--run-id", "abc123-draft", "--parent-run-id", "abc123",
                                     env={"INVOCATION_ID": "abc123"})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(written["run_id"], "abc123-draft")
        self.assertEqual(written["parent_run_id"], "abc123")
        self.assertTrue((self.box.receipts / "knowledge-digest" / "abc123-draft.json").is_file())
        self.box.set_state("InvocationID", "cafe0001")
        self.box.set_state("LastTriggerUSec", f"@{int(time.time()) - 3600}")
        done, written = self.box.run("knowledge-digest", "sweep", "--state-change", "timer fired",
                                     "--run-id", "explicit-sweep-id")
        self.assertEqual(written["run_id"], "explicit-sweep-id")

    def amend(self, run_id, *extra, seeded=False, unit="knowledge-digest"):
        """--amend as the sweep invokes it: no --run-started-at / --run-date unless `seeded`,
        so the executor reads the run's start back from the receipt."""
        cmd = [sys.executable, str(EXECUTOR), unit, "--vantage", "sweep", "--amend",
               "--run-id", run_id, "--sweep-run-id", "sweep-77", "--repo-root", str(ROOT),
               "--manifest-dir", str(FIXTURES / "agents"), "--schema-doc", str(SCHEMA_DOC),
               "--receipt-root", str(self.box.receipts), "--attempt-log", str(self.box.attempt_log("knowledge-digest")),
               "--inbox-worktree", str(self.box.inbox), "--vault", str(self.box.vault),
               "--home", str(self.box.home), "--now", (self.box.now + dt.timedelta(hours=22)).isoformat(), *extra]
        if seeded:
            cmd += ["--run-started-at", str(self.box.started), "--run-date", self.box.run_date]
        parent = {"PATH": f"{self.box.fakebin}:{os.environ['PATH']}", "SECRET_PROBE": "leaked",
                  "HOME": os.environ.get("HOME", str(self.box.home))}
        done = subprocess.run(cmd, capture_output=True, text=True, env=parent)
        path = self.box.receipts / unit / f"{run_id}.json"
        return done, json.loads(path.read_text()) if path.is_file() else None

    def test_amend_folds_sweep_checks_into_the_run_receipt(self):  # (::exec-amend-folds-sweep-checks)
        done, before = self.healthy_run(env={"INVOCATION_ID": "run-1"})
        self.assertEqual({a["id"]: a["status"] for a in before["assertions"] if a["id"] in KD_SWEEP},
                         {"not-lock-skipped": "not_applicable", "timer-fired-this-week": "not_applicable"})
        self.assertNotIn("swept", before)
        # the timer fired, no lock skip: both sweep checks pass, the run's own facts stand
        self.box.set_state("LastTriggerUSec", f"@{int(time.time()) - 3600}")
        self.box.set_state("journal.txt", "Started knowledge-digest.service\n")
        done, after = self.amend("run-1")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertIn("vantage=sweep amend", done.stdout)
        self.assertEqual(receipt.validate(after), [])
        self.assertEqual([a["id"] for a in after["assertions"]], KD_IDS)
        self.assertEqual({a["id"]: a["status"] for a in after["assertions"] if a["id"] in KD_SWEEP},
                         {"not-lock-skipped": "passed", "timer-fired-this-week": "passed"})
        self.assertEqual(after["swept"], {"at": "2026-09-12T05:30:00Z", "sweep_run_id": "sweep-77"})
        untouched = {k: v for k, v in after.items() if k not in ("assertions", "swept")}
        self.assertEqual(untouched, {k: v for k, v in before.items() if k != "assertions"})
        self.assertEqual([a for a in after["assertions"] if a["id"] not in KD_SWEEP],
                         [a for a in before["assertions"] if a["id"] not in KD_SWEEP])
        # the run's own start and date are read back from the receipt, not the sweep's clock
        self.box.write_attempt_log("probe\n", unit="env-probe")
        done, probe = self.box.run("env-probe", "run", "--artifact", "file:///probe", "--run-id", "probe-1")
        self.assertEqual(by_id(probe)["sweep-only"]["status"], "not_applicable")
        done, probe = self.amend("probe-1", unit="env-probe")
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(by_id(probe)["sweep-only"]["status"], "passed")
        self.assertEqual(by_id(probe)["sweep-only"]["output"], f"started={self.box.started} date={self.box.run_date}")
        # a second look is refused, and the receipt is byte-identical
        path = self.box.receipts / "knowledge-digest" / "run-1.json"
        bytes_before = path.read_bytes()
        done, again = self.amend("run-1")
        self.assertEqual(done.returncode, 2, done.stdout + done.stderr)
        self.assertIn("swept 2026-09-12T05:30:00Z", done.stderr)
        self.assertEqual(path.read_bytes(), bytes_before)

    def test_amend_turns_a_failed_sweep_check_into_a_failed_receipt(self):  # (::exec-amend-folds-sweep-checks)
        done, before = self.healthy_run(env={"INVOCATION_ID": "run-2"})
        self.assertEqual(before["terminal"], {"outcome": "artifact", "reason": None})
        self.box.set_state("LastTriggerUSec", f"@{int(time.time()) - 3600}")
        self.box.set_state("journal.txt", "Started knowledge-digest.service\nSKIP: previous run still active\n")
        done, after = self.amend("run-2", seeded=True)
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(by_id(after)["not-lock-skipped"]["status"], "failed")
        self.assertEqual(by_id(after)["timer-fired-this-week"]["status"], "passed")
        self.assertEqual(after["terminal"], {"outcome": "failed",
                                             "reason": "failed sweep checks: not-lock-skipped; run outcome was artifact"})
        self.assertEqual(after["artifact"], before["artifact"])
        self.assertEqual(receipt.validate(after), [])
        # a run that already failed keeps its reason first; a decline keeps its sentinel in the reason
        self.box.write_attempt_log(GUARD_OK + "nothing produced\n")
        done, failed = self.box.run("knowledge-digest", "run", "--run-id", "run-3")
        self.assertEqual(failed["terminal"]["outcome"], "failed")
        done, after = self.amend("run-3", seeded=True)
        self.assertEqual(done.returncode, 1)
        self.assertTrue(after["terminal"]["reason"].startswith("neither artifact nor decline"), after["terminal"])
        self.assertTrue(after["terminal"]["reason"].endswith("; failed sweep checks: not-lock-skipped"), after["terminal"])
        self.box.write_attempt_log(GUARD_OK + DECLINE)
        done, declined = self.box.run("knowledge-digest", "run", "--run-id", "run-4")
        self.assertEqual(declined["terminal"]["outcome"], "decline")
        done, after = self.amend("run-4", seeded=True)
        self.assertEqual(after["terminal"]["outcome"], "failed")
        self.assertIn("run outcome was decline: DECLINE:", after["terminal"]["reason"])

    def test_amend_refuses_what_it_does_not_owe(self):  # (::exec-amend-folds-sweep-checks)
        self.box.set_state("LastTriggerUSec", f"@{int(time.time()) - 3600}")
        self.box.set_state("journal.txt", "")
        cases = []
        done, _ = self.amend("never-written")
        cases.append(("no receipt", done))
        done, skipped = self.box.run("knowledge-digest", "run", "--skipped", "lock held", "--run-id", "skip-1")
        done, _ = self.amend("skip-1")
        cases.append(("a skip is not a run", done))
        done, failed = self.box.run("knowledge-digest", "run", "--run-id", "closed-1")
        path = self.box.receipts / "knowledge-digest" / "closed-1.json"
        path.write_text(json.dumps(receipt.close(failed, "Dave", "reviewed")))
        done, _ = self.amend("closed-1")
        cases.append(("closed by an operator", done))
        self.box.set_state("InvocationID", "cafe0002")
        self.box.write_attempt_log(GUARD_OK)
        done, swept = self.box.run("knowledge-digest", "sweep", "--state-change", "swept", "--run-id", "sweep-written")
        done, _ = self.amend("sweep-written")
        cases.append(("written by the sweep", done))
        for word, done in cases:
            self.assertEqual(done.returncode, 2, word)
            self.assertIn(word, done.stderr, word)
        self.assertEqual(json.loads(path.read_text())["closed"]["by"], "Dave")
        # --amend at vantage run, or without --run-id, is a usage error not a receipt
        done, _ = self.box.run("knowledge-digest", "run", "--amend", "--run-id", "x")
        self.assertEqual(done.returncode, 2)
        self.assertIn("never amends", done.stderr)
        done = subprocess.run([sys.executable, str(EXECUTOR), "knowledge-digest", "--vantage", "sweep", "--amend",
                               "--manifest-dir", str(FIXTURES / "agents"), "--receipt-root", str(self.box.receipts)],
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 2)
        self.assertIn("needs --run-id", done.stderr)

    def test_refuses_non_contract_rows(self):  # (::exec-refuses-non-contract-rows)
        for unit, word in (("always-on", "service"), ("spent-job", "contract_exempt"), ("no-such-unit", "no")):
            done, written = self.box.run(unit, "run", "--artifact", "file:///x")
            self.assertEqual(done.returncode, 2, unit)
            self.assertIn(word, done.stderr, unit)
            self.assertIsNone(written)
        self.assertEqual(list(self.box.receipts.rglob("*.json")), [])


if __name__ == "__main__":
    unittest.main()
