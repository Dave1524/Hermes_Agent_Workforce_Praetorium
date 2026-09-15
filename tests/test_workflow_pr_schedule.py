#!/usr/bin/env python3
"""T5.3b — the schedule plan: an exact three-file diff (timer, manifest trigger, contract
trigger tokens), a description that names the timezone, the catch-up rule and when the change
takes effect, and the check bundle's schedule half. Pure over a checkout of the fixture remote.
"""
from __future__ import annotations

import datetime as dt
import pathlib
import shutil
import sys
import tempfile
import tomllib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "tests"))
from test_control_room_proposals import FIXTURES, NOW, FakeRunner, checkout, make_item, make_remote  # noqa: E402
import workflow_pr_checks as checks  # noqa: E402
import workflow_pr_record as record  # noqa: E402
import workflow_pr_schedule as sched  # noqa: E402

PID = "20260914T080000Z-schedule-alpha-abcdef"


def calendar_from_fixture(spec: str) -> list[dict]:
    return sched.systemd_analyze_calendar(spec)


class Planned(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="crp-sched-"))
        self.addCleanup(shutil.rmtree, self.tmp, True)
        make_remote(self.tmp)
        self.wt = checkout(self.tmp)
        self.before = {p: (self.wt / p).read_text() for p in ("systemd/alpha.timer", "design/agents/claudius.toml",
                                                               "design/contracts/alpha.md")}

    def plan(self, workflow_id="alpha", control_state="paused", **proposed):
        proposed.setdefault("on_calendar", ["Sun 07:00"])
        item = make_item(self.wt, workflow_id, control_state)
        return sched.plan_schedule(self.wt, item, proposed, now=NOW, pid=PID, tz={"name": "Europe/Amsterdam", "source": "timedatectl"},
                                   calendar_runner=calendar_from_fixture)

    def test_diff_is_exact(self):
        """(::schedule-diff-is-exact)"""
        plan = self.plan()
        self.assertEqual(sorted(plan.edits), ["design/agents/claudius.toml", "design/contracts/alpha.md", "systemd/alpha.timer"])
        timer_before = self.before["systemd/alpha.timer"].splitlines()
        timer_after = (self.wt / "systemd/alpha.timer").read_text().splitlines()
        changed = [(a, b) for a, b in zip(timer_before, timer_after) if a != b]
        self.assertEqual(changed, [("OnCalendar=Sun 09:00", "OnCalendar=Sun 07:00")])
        self.assertEqual(len(timer_before), len(timer_after))
        old = tomllib.loads(self.before["design/agents/claudius.toml"])
        new = tomllib.loads((self.wt / "design/agents/claudius.toml").read_text())
        for entry_old, entry_new in zip(old["workflows"], new["workflows"]):
            if entry_old["unit"] == "alpha":
                self.assertEqual(entry_new["trigger"], "Sun 07:00 (+5min jitter)")
                entry_new = {**entry_new, "trigger": entry_old["trigger"]}
            self.assertEqual(entry_old, entry_new)
        self.assertEqual({k: v for k, v in old.items() if k != "workflows"}, {k: v for k, v in new.items() if k != "workflows"})
        contract = (self.wt / "design/contracts/alpha.md").read_text()
        self.assertIn("`OnCalendar=Sun 07:00`", contract)
        self.assertNotIn("Sun 09:00", contract)
        self.assertEqual(contract.replace("Sun 07:00", "Sun 09:00"), self.before["design/contracts/alpha.md"])
        first = {p: (self.wt / p).read_bytes() for p in plan.edits}
        for path, text in self.before.items():
            (self.wt / path).write_text(text)
        self.plan()
        self.assertEqual({p: (self.wt / p).read_bytes() for p in plan.edits}, first)

    def test_describes_tz_and_catch_up(self):
        """(::schedule-describes-tz-and-catch-up)"""
        desc = self.plan().description
        self.assertEqual(desc["timezone"]["name"], "Europe/Amsterdam")
        self.assertFalse(desc["timezone"]["explicit_in_spec"])
        for side in ("current", "proposed"):
            self.assertEqual(len(desc[side]["next"]), 3)
            for entry in desc[side]["next"]:
                self.assertRegex(entry["local"], r"(CEST|CET)$")
                self.assertRegex(entry["utc"], r"UTC$")
        self.assertEqual(desc["current"]["on_calendar"], ["Sun 09:00"])
        self.assertEqual(desc["proposed"]["on_calendar"], ["Sun 07:00"])
        self.assertIn("resume", desc["catch_up"])
        self.assertIn("T5.3a", desc["catch_up"])
        self.assertIn("at resume", desc["takes_effect"])
        for path, text in self.before.items():
            (self.wt / path).write_text(text)
        desc = self.plan(persistent=False).description
        self.assertIn("no catch-up", desc["catch_up"])
        for path, text in self.before.items():
            (self.wt / path).write_text(text)
        desc = self.plan(control_state="active").description
        self.assertIn("restart alpha.timer", desc["takes_effect"])
        for path, text in self.before.items():
            (self.wt / path).write_text(text)
        desc = self.plan(on_calendar=["Wed 12:00 UTC"]).description
        self.assertTrue(desc["timezone"]["explicit_in_spec"])

    def test_refuses_bad_spec(self):
        """(::schedule-refuses-bad-spec)"""
        for bad in (["Sun 09:00=x"], ["S" * 90], ["Sun 09:00\nSun 10:00"], ["Sun [09:00]"], []):
            with self.assertRaises(record.Refused) as ctx:
                self.plan(on_calendar=bad)
            self.assertEqual(ctx.exception.code, "bad_request", bad)
        for path, text in self.before.items():
            self.assertEqual((self.wt / path).read_text(), text)
        plan = self.plan(on_calendar=["Funday 25:00"])
        results = checks.run_checks(self.wt, "schedule", plan.context(), FakeRunner())
        by_id = {c["id"]: c for c in results}
        self.assertEqual(by_id["schedule-parses"]["status"], "fail")
        self.assertIn("Funday 25:00", by_id["schedule-parses"]["output"])
        self.assertEqual(by_id["unit-verify"]["status"], "fail")
        self.assertNotIn("CPUAccounting", by_id["unit-verify"]["output"])
        self.assertIn("alpha.timer", by_id["unit-verify"]["output"])
        self.assertFalse(checks.submit_allowed(results, "schedule", acknowledge_pinned=False)[0])

    def test_collision_window(self):
        """(::schedule-collision-window)"""
        plan = self.plan(on_calendar=["Sun 07:20"])
        results = {c["id"]: c for c in checks.run_checks(self.wt, "schedule", plan.context(), FakeRunner())}
        self.assertEqual(results["schedule-collisions"]["status"], "pass", results["schedule-collisions"])
        for path, text in self.before.items():
            (self.wt / path).write_text(text)
        (self.wt / "systemd/beta.timer").write_text((self.wt / "systemd/beta.timer").read_text().replace("Mon-Fri 06:00", "Sun 07:20"))
        plan = self.plan(on_calendar=["Sun 07:00"])
        results = {c["id"]: c for c in checks.run_checks(self.wt, "schedule", plan.context(), FakeRunner())}
        self.assertEqual(results["schedule-collisions"]["status"], "warn")
        self.assertIn("beta.timer", results["schedule-collisions"]["output"])
        self.assertIn("agent_propose.sh", results["schedule-collisions"]["output"])

    def test_pinned_tests_named(self):
        """(::schedule-pinned-tests-named)"""
        plan = self.plan()
        runner = FakeRunner({"test_alpha_smoke.sh": (1, "  FAIL: alpha.timer must fire Sun 09:00\n")})
        results = checks.run_checks(self.wt, "schedule", plan.context(), runner)
        pinned = next(c for c in results if c["id"] == "pinned-tests")
        self.assertEqual(pinned["status"], "fail")
        self.assertIn("tests/test_alpha_smoke.sh", pinned["output"])
        self.assertIn("FAIL: alpha.timer must fire Sun 09:00", pinned["output"])
        self.assertNotIn("test_beta_smoke.sh", " ".join(" ".join(c) for c in runner.calls))
        allowed, blockers = checks.submit_allowed(results, "schedule", acknowledge_pinned=False)
        self.assertFalse(allowed)
        self.assertTrue(any("tests/test_alpha_smoke.sh" in b for b in blockers))
        allowed, blockers = checks.submit_allowed(results, "schedule", acknowledge_pinned=True)
        self.assertTrue(allowed, blockers)
        self.assertTrue(checks.draft_required(results, acknowledge_pinned=True))

    def test_multi_trigger(self):
        """(::schedule-multi-trigger)"""
        with self.assertRaises(record.Refused) as ctx:
            self.plan("gamma", on_calendar=["Tue 03:30"])
        self.assertEqual(ctx.exception.code, "trigger_required")
        self.assertEqual(ctx.exception.choices, ["gamma", "gamma-dispatch"])
        with self.assertRaises(record.Refused) as ctx:
            self.plan("gamma", on_calendar=["Tue 03:30"], trigger="sshd")
        self.assertEqual(ctx.exception.code, "bad_request")
        plan = self.plan("gamma", on_calendar=["Sat 22:00"], trigger="gamma-dispatch")
        self.assertEqual(sorted(plan.edits), ["design/agents/claudius.toml", "design/contracts/gamma.md", "systemd/gamma-dispatch.timer"])
        new = tomllib.loads((self.wt / "design/agents/claudius.toml").read_text())
        by_unit = {e["unit"]: e for e in new["workflows"]}
        self.assertEqual(by_unit["gamma"]["trigger"], "Tue 03:00")
        self.assertEqual(by_unit["gamma-dispatch"]["trigger"], "Sat 22:00")

    def test_randomized_and_persistent(self):
        """(::schedule-randomized-and-persistent)"""
        self.plan("beta", on_calendar=["Mon-Fri 06:30"], randomized_delay_sec="10min")
        lines = (self.wt / "systemd/beta.timer").read_text().splitlines()
        self.assertEqual(lines[lines.index("OnCalendar=Mon-Fri 06:30") + 1], "RandomizedDelaySec=10min")
        self.assertIn("Persistent=false", lines)
        self.plan(on_calendar=["Sun 09:00"], persistent=False)
        lines = (self.wt / "systemd/alpha.timer").read_text().splitlines()
        self.assertEqual(lines, [l.replace("Persistent=true", "Persistent=false") for l in self.before["systemd/alpha.timer"].splitlines()])
        (self.wt / "systemd/alpha.timer").write_text(self.before["systemd/alpha.timer"])
        self.plan(on_calendar=["Sun 09:00"], randomized_delay_sec=None, persistent=None)
        self.assertEqual((self.wt / "systemd/alpha.timer").read_text(), self.before["systemd/alpha.timer"])

    def test_not_a_timer_and_not_calendar(self):
        with self.assertRaises(record.Refused) as ctx:
            self.plan("buzz-agent@trajan")
        self.assertEqual(ctx.exception.code, "not_a_timer")
        with self.assertRaises(record.Refused) as ctx:
            self.plan("refresh")
        self.assertEqual(ctx.exception.code, "not_calendar_timer")


class Parsing(unittest.TestCase):
    def test_parse_and_render_timer(self):
        text = (FIXTURES / "repo" / "systemd" / "alpha.timer").read_text()
        parsed = sched.parse_timer(text)
        self.assertEqual(parsed["on_calendar"], ["Sun 09:00"])
        self.assertEqual(parsed["randomized_delay_sec"], "5min")
        self.assertTrue(parsed["persistent"])
        rendered = sched.render_timer(text, ["Sun 07:00", "Wed 12:00 UTC"], "5min", True)
        self.assertIn("OnCalendar=Sun 07:00\nOnCalendar=Wed 12:00 UTC\nRandomizedDelaySec=5min\nPersistent=true", rendered)
        self.assertIn("[Unit]\nDescription=alpha", rendered)

    def test_calendar_parsing_from_the_shim(self):
        elapses = sched.systemd_analyze_calendar("Sun 09:00")
        self.assertEqual(len(elapses), 3)
        self.assertEqual(elapses[0]["utc"], "Sun 2026-09-20 07:00:00 UTC")
        self.assertEqual(elapses[0]["local"], "Sun 2026-09-20 09:00:00 CEST")
        self.assertEqual(sched.utc_datetime(elapses[0]["utc"]), dt.datetime(2026, 9, 20, 7, tzinfo=dt.timezone.utc))
        with self.assertRaises(ValueError):
            sched.systemd_analyze_calendar("Funday 25:00")


if __name__ == "__main__":
    unittest.main()
