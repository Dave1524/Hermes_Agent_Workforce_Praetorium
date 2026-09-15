#!/usr/bin/env python3
"""The incident notifier end to end (T5.3c), through the CLI with a fake transport.

Every case runs bin/incident_notify.py as a subprocess against fixture receipts, a fake
`systemctl` and the fake `deliver.sh` under tests/fixtures/incidents/. The gate this suite
carries: healthy runs stay silent, a persistent incident alerts once, recovery is visible,
the digest holds only unresolved incidents, and a delivery failure never fails the sweep.
"""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests" / "fixtures" / "incidents"
NOTIFY = ROOT / "bin" / "incident_notify.py"
LINK = "http://praetorium:8787/api/v1/incidents#{key}"

CONTRACT = """# Contract: {unit}

## Identity

| | |
|---|---|
| Unit | `{unit}.service` / `.timer` |
| Owner | **{owner}** |
| Surface | platform |

## Trigger

Daily.

## Inputs

`input.txt`.

## Outputs

- **Artifact:** one file.
- **Beneficiary:** Dave.
- **Next actor:** Dave.
- **Next action:** Review.
- **Benefit hypothesis:** visible.
- **Benefit signal:** Unknown.

## Decline conditions

None.

## Side effects

None.

## Acceptance checks

1. The artifact exists.

   ```check id=artifact-exists when=run
   [ -f "$AGENT_ATTEMPT_LOG" ]
   ```

## Known failure modes

None.
"""


def sha256_tree(root: pathlib.Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(root.rglob("*")) if p.is_file()}


class NotifierCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        root = pathlib.Path(self.temp.name)
        self.repo = root / "repo"
        self.runtime = root / "runtime"
        self.receipts = self.runtime / "var" / "workflow-receipts"
        self.state_dir = self.runtime / "var" / "incidents"
        self.home = root / "home"
        self.fake = root / "fake"
        self.systemd_state = root / "systemd-state"
        for path in (self.repo / "design" / "agents", self.repo / "design" / "contracts", self.receipts,
                     self.home, self.fake, self.systemd_state):
            path.mkdir(parents=True)
        self.receipts_log = self.home / "logs" / "delivery-receipts.jsonl"
        self.manifest("claudius", "knowledge-digest")
        self.manifest("marcus", "daily-plan")

    def tearDown(self):
        self.temp.cleanup()

    def manifest(self, owner: str, *units: str) -> None:
        body = f'name="{owner}"\n'
        for unit in units:
            body += (f'[[workflows]]\nunit="{unit}"\nsurface="scheduled"\ntrigger="daily"\nstatus="standing"\n'
                     f'contract="design/contracts/{unit}.md"\n')
            (self.repo / "design" / "contracts" / f"{unit}.md").write_text(CONTRACT.format(unit=unit, owner=owner))
        (self.repo / "design" / "agents" / f"{owner}.toml").write_text(body)

    def receipt(self, name: str, workflow: str = "knowledge-digest") -> pathlib.Path:
        target = self.receipts / workflow / name
        target.parent.mkdir(exist_ok=True)
        shutil.copy(FIXTURES / "receipts" / workflow / name, target)
        return target

    def sweep(self, *extra: str, now: str = "2026-09-14T03:05:00Z", routes: str = "routes.env",
              mode: str = "ok", tz: str = "UTC", deliver_bin: pathlib.Path | None = None,
              receipt_root: pathlib.Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess:
        env = {
            **os.environ, "TZ": tz, "HOME": str(self.home), "PATH": f"{FIXTURES / 'bin'}:{os.environ['PATH']}",
            "FAKE_DIR": str(self.fake), "FAKE_SYSTEMD_STATE": str(self.systemd_state), "FAKE_DELIVER_MODE": mode,
            "FAKE_EVENT_ID": "e1e1e1", "FAKE_CHANNEL": "0f1e2d3c-4b5a-4697-8877-665544332211",
        }
        argv = [sys.executable, str(NOTIFY), "--now", now, "--state-dir", str(self.state_dir),
                "--routes-file", str(FIXTURES / routes), "--deliver-bin", str(deliver_bin or FIXTURES / "bin" / "deliver.sh"),
                "--receipts-log", str(self.receipts_log), "--repo-root", str(self.repo),
                "--runtime-root", str(self.runtime), "--receipt-root", str(receipt_root or self.receipts),
                "--job", "workflow-incidents.service", "--link-template", LINK, *extra]
        return subprocess.run(argv, env=env, capture_output=True, text=True, timeout=timeout, check=False)

    def state(self) -> dict:
        return json.loads((self.state_dir / "state.json").read_text())

    def invocations(self) -> list[str]:
        path = self.fake / "argv.log"
        return [line for line in path.read_text().splitlines() if line.startswith("job=")] if path.exists() else []

    def messages(self) -> str:
        path = self.fake / "messages.log"
        return path.read_text() if path.exists() else ""

    def log(self) -> str:
        path = self.home / "logs" / "workflow-incidents.log"
        return path.read_text() if path.exists() else ""


class Notifier(NotifierCase):
    def test_healthy_and_declined_runs_are_silent(self):
        # (::notify-silence)
        self.receipt("synthetic-recovered.json")
        self.receipt("decline.json", "daily-plan")
        result = self.sweep()
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invocations(), [])
        self.assertEqual(self.state()["incidents"], {})
        self.assertIn("0 open, 0 sent", self.log())

    def test_failed_run_alerts_once_with_every_named_field(self):
        # (::notify-immediate)
        self.receipt("synthetic-failed.json")
        result = self.sweep()
        self.assertEqual(result.returncode, 0, result.stderr)
        calls = self.invocations()
        self.assertEqual(len(calls), 1)
        self.assertIn("job=workflow-incidents.service route=incidents subject=[incident] failed-assertion:knowledge-digest "
                      "DELIVER_DISCORD=0", calls[0])
        argv = (self.fake / "argv.log").read_text().splitlines()[0]
        self.assertIn("--job workflow-incidents.service --route incidents --runtime none", argv)
        body = self.messages()
        for line in (
            "workflow: knowledge-digest (unit knowledge-digest)",
            "agent: claudius",
            "failure: failed-assertion — failed checks: artifact-exists",
            "failed check: artifact-exists",
            "time: first seen 2026-09-14T03:04:00Z · run synthetic-failed-2026-09-14 · seen 1×",
            "required action: Check the knowledge-digest attempt log and re-run by hand",
            "incident: http://praetorium:8787/api/v1/incidents#failed-assertion:knowledge-digest",
            "evidence: knowledge-digest/synthetic-failed.json",
        ):
            self.assertIn(line, body)
        entry = self.state()["incidents"]["failed-assertion:knowledge-digest"]
        self.assertEqual(entry["notified_at"], "2026-09-14T03:05:00Z")
        self.assertEqual(entry["notify_event_id"], "e1e1e1")
        self.assertEqual(entry["notify_channel"], "0f1e2d3c-4b5a-4697-8877-665544332211")

    def test_persistent_incident_is_deduplicated(self):
        # (::notify-dedup)
        self.receipt("synthetic-failed.json")
        self.sweep()
        self.sweep(now="2026-09-14T03:10:00Z")
        self.assertEqual(len(self.invocations()), 1)
        second = json.loads((FIXTURES / "receipts" / "knowledge-digest" / "synthetic-failed.json").read_text())
        second["run_id"] = "synthetic-failed-2026-09-15"
        second["started_at"], second["ended_at"] = "2026-09-15T03:00:00Z", "2026-09-15T03:04:00Z"
        (self.receipts / "knowledge-digest" / "second.json").write_text(json.dumps(second))
        self.sweep(now="2026-09-15T03:05:00Z")
        self.assertEqual(len(self.invocations()), 1)
        entry = self.state()["incidents"]["failed-assertion:knowledge-digest"]
        self.assertEqual(entry["observations"], 2)
        self.assertEqual(entry["run_id"], "synthetic-failed-2026-09-15")

    def test_recovery_is_visible_once_and_points_at_the_alert(self):
        # (::notify-recovery)
        self.receipt("synthetic-failed.json")
        self.sweep()
        self.receipt("synthetic-recovered.json")
        self.sweep(now="2026-09-14T09:05:00Z")
        calls = self.invocations()
        self.assertEqual(len(calls), 2)
        self.assertIn("subject=[recovered] failed-assertion:knowledge-digest", calls[1])
        self.assertIn("open since 2026-09-14T03:04:00Z", self.messages())
        self.assertIn("resolved 2026-09-14T09:05:00Z", self.messages())
        self.assertIn("evidence: knowledge-digest/synthetic-recovered.json", self.messages())
        self.assertIn("alert: buzz://message?channel=0f1e2d3c-4b5a-4697-8877-665544332211&id=e1e1e1", self.messages())
        entry = self.state()["incidents"]["failed-assertion:knowledge-digest"]
        self.assertEqual(entry["resolved_at"], "2026-09-14T09:05:00Z")
        self.assertEqual(entry["recovery_notified_at"], "2026-09-14T09:05:00Z")
        self.sweep(now="2026-09-14T09:10:00Z")
        self.assertEqual(len(self.invocations()), 2)

    def test_daily_digest_lists_only_unresolved_incidents(self):
        # (::notify-digest)
        self.receipt("synthetic-failed.json")
        self.receipt("skipped.json", "daily-plan")
        self.manifest("trajan", "scorecard")
        stale = json.loads((FIXTURES / "receipts" / "daily-plan" / "skipped.json").read_text())
        stale["workflow_id"], stale["unit"], stale["run_id"] = "scorecard", "scorecard", "scorecard-1"
        (self.receipts / "scorecard").mkdir()
        (self.receipts / "scorecard" / "scorecard-1.json").write_text(json.dumps(stale))
        self.sweep(now="2026-09-14T06:05:00Z")
        self.assertEqual(len(self.invocations()), 3)
        (self.receipts / "scorecard" / "scorecard-1.json").unlink()
        state = self.state()
        state["last_digest_at"] = "2026-09-14T05:01:00Z"
        (self.state_dir / "state.json").write_text(json.dumps(state))
        self.sweep(now="2026-09-15T05:03:00Z", tz="Europe/Amsterdam")
        calls = self.invocations()
        self.assertEqual(len(calls), 5, calls)
        self.assertIn("subject=[recovered] incomplete-run:scorecard", calls[3])
        self.assertIn("subject=[incident digest] 2 unresolved", calls[4])
        digest = self.messages().split("\n")
        lines = [line for line in digest if line.startswith(("failed-assertion", "incomplete-run"))
                 and "— since" in line]
        self.assertEqual(len(lines), 2)
        self.assertTrue(lines[0].startswith("failed-assertion knowledge-digest — since 2026-09-14T03:04:00Z (seen 1×"))
        self.assertTrue(lines[1].startswith("incomplete-run daily-plan — since 2026-09-14T06:00:01Z"))
        self.assertIn(LINK.format(key="incomplete-run:daily-plan"), lines[1])
        self.assertNotIn("scorecard", "\n".join(lines))
        self.assertEqual(self.state()["last_digest_at"], "2026-09-15T05:03:00Z")
        self.sweep(now="2026-09-15T05:07:00Z", tz="Europe/Amsterdam")
        self.assertEqual(len(self.invocations()), 5)

    def test_empty_digest_is_never_sent_and_unsent_opens_are_marked(self):
        self.sweep(now="2026-09-15T05:03:00Z", tz="Europe/Amsterdam")
        self.assertEqual(self.invocations(), [])
        self.assertEqual(self.state()["last_digest_at"], "2026-09-15T05:03:00Z")
        self.receipt("synthetic-failed.json")
        self.sweep(now="2026-09-15T06:00:00Z", mode="failed")
        self.sweep("--digest", now="2026-09-15T06:05:00Z", mode="failed")
        self.assertIn("unsent (", self.messages())

    def test_unset_route_sends_nothing_and_keeps_state(self):
        # (::notify-route-precheck)
        self.receipt("synthetic-failed.json")
        result = self.sweep(routes="routes-unset.env")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.invocations(), [])
        self.assertIn("route 'incidents' has no channel UUID", self.log())
        entry = self.state()["incidents"]["failed-assertion:knowledge-digest"]
        self.assertIsNone(entry["notified_at"])
        self.assertEqual(entry["first_seen"], "2026-09-14T03:04:00Z")
        self.sweep(now="2026-09-14T03:10:00Z")
        self.sweep(now="2026-09-14T03:15:00Z")
        self.assertEqual(len(self.invocations()), 1)

    def test_delivery_failure_never_fails_the_sweep(self):
        # (::notify-delivery-isolation)
        self.receipt("synthetic-failed.json")
        before = sha256_tree(self.receipts)
        result = self.sweep(mode="failed")
        self.assertEqual(result.returncode, 0, result.stderr)
        entry = self.state()["incidents"]["failed-assertion:knowledge-digest"]
        self.assertIsNone(entry["notified_at"])
        self.assertEqual(entry["send_attempts"], 1)
        self.assertIn("outcome=failed", entry["last_send_error"])
        result = self.sweep(mode="crash", now="2026-09-14T03:10:00Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()["incidents"]["failed-assertion:knowledge-digest"]["send_attempts"], 2)
        started = time.monotonic()
        result = self.sweep("--deliver-timeout", "2", mode="hang", now="2026-09-14T03:15:00Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertLess(time.monotonic() - started, 10)
        self.assertEqual(self.state()["incidents"]["failed-assertion:knowledge-digest"]["send_attempts"], 3)
        result = self.sweep(deliver_bin=self.fake / "missing.sh", now="2026-09-14T03:20:00Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(self.state()["incidents"]["failed-assertion:knowledge-digest"]["send_attempts"], 4)
        self.sweep("--max-attempts", "4", now="2026-09-14T03:25:00Z")
        self.assertEqual(len(self.invocations()), 3)
        self.sweep("--max-attempts", "4", "--digest", now="2026-09-14T03:30:00Z")
        self.assertIn("unsent (", self.messages())
        self.assertEqual(sha256_tree(self.receipts), before)

    def test_notifier_is_outside_every_run_path(self):
        pattern = re.compile(r"incident_notify|deliver_incidents")
        checked = 0
        for path in sorted(ROOT.glob("systemd/*.service")):
            if path.name == "workflow-incidents.service":
                continue
            checked += 1
            self.assertIsNone(pattern.search(path.read_text()), path)
        for path in [*ROOT.glob("bin/run_*_cc.sh"), ROOT / "bin" / "agent_propose.sh", ROOT / "bin" / "contract_exec.py"]:
            checked += 1
            self.assertIsNone(pattern.search(path.read_text()), path)
        self.assertGreater(checked, 10)

    def test_flood_cap_defers_the_rest_to_the_next_sweep(self):
        # (::notify-flood-cap)
        units = [f"wf-{i:02d}" for i in range(12)]
        self.manifest("trajan", *units)
        failed = json.loads((FIXTURES / "receipts" / "knowledge-digest" / "synthetic-failed.json").read_text())
        for i, unit in enumerate(units):
            body = {**failed, "workflow_id": unit, "unit": unit, "run_id": f"{unit}-run",
                    "ended_at": f"2026-09-14T03:{i:02d}:30Z", "started_at": "2026-09-14T03:00:00Z"}
            (self.receipts / unit).mkdir()
            (self.receipts / unit / "run.json").write_text(json.dumps(body))
        self.sweep("--max-sends", "10")
        self.assertEqual(len(self.invocations()), 10)
        self.assertTrue(self.invocations()[0].endswith("failed-assertion:wf-00 DELIVER_DISCORD=0"))
        self.sweep("--max-sends", "10", now="2026-09-14T03:10:00Z")
        self.assertEqual(len(self.invocations()), 12)

    def test_degraded_source_closes_nothing(self):
        # (::notify-degraded-closes-nothing)
        self.receipt("synthetic-failed.json")
        self.sweep()
        not_a_dir = self.runtime / "not-a-dir"
        not_a_dir.write_text("x")
        result = self.sweep(now="2026-09-14T03:10:00Z", receipt_root=not_a_dir)
        self.assertEqual(result.returncode, 0, result.stderr)
        state = self.state()["incidents"]
        self.assertIsNone(state["failed-assertion:knowledge-digest"]["resolved_at"])
        self.assertIn("control-failure:incident-sweep:receipts", state)
        calls = self.invocations()
        self.assertEqual(len(calls), 2)
        self.assertIn("subject=[incident] control-failure:incident-sweep:receipts", calls[1])
        self.sweep(now="2026-09-14T03:15:00Z", receipt_root=not_a_dir)
        self.assertEqual(len(self.invocations()), 2)

    def test_dry_run_touches_neither_state_nor_transport(self):
        # (::notify-dry-run)
        self.receipt("synthetic-failed.json")
        self.sweep()
        self.receipt("synthetic-recovered.json")
        before = (self.state_dir / "state.json").read_bytes()
        result = self.sweep("--dry-run", now="2026-09-14T09:05:00Z")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("[recovered] failed-assertion:knowledge-digest", result.stdout)
        self.assertEqual(len(self.invocations()), 1)
        self.assertEqual((self.state_dir / "state.json").read_bytes(), before)

    def test_fixture_receipts_validate(self):
        sys.path.insert(0, str(ROOT / "bin"))
        import workflow_receipt  # noqa: E402
        for path in sorted((FIXTURES / "receipts").glob("*/*.json")):
            self.assertEqual(workflow_receipt.validate(json.loads(path.read_text())), [], path)


if __name__ == "__main__":
    unittest.main()
