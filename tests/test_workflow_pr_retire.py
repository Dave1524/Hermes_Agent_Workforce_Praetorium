#!/usr/bin/env python3
"""T5.3b — the retirement plan: removal across every join, shared runners kept, a surface that
empties, the retention decision, two-trigger workflows, count literals vs pinned suites, the PR
body sections, the refusals, and the branch scan that fails closed.

Anchors: (::retire-removal-across-joins) (::retire-keeps-shared-runner) (::retire-empties-a-surface)
(::retire-needs-explicit-retention) (::retire-two-trigger-retires-both)
(::retire-count-literals-or-pinned) (::retire-pr-body-sections) (::retire-refusals)
(::residue-fails-closed-on-branch)
"""
from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys
import tomllib
import unittest

HERE = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "bin"))

from test_control_room_proposals import (  # noqa: E402
    ACTOR, FIXTURES, NOW, TempState, _git, checkout, gh_log, make_item, make_remote, make_worker, remote_heads)

import workflow_pr_body as body  # noqa: E402
import workflow_pr_retire as retire  # noqa: E402
import workflow_retire_residue as residue  # noqa: E402
from workflow_pr_record import Refused  # noqa: E402

PID = "20260914T080000Z-retire-alpha-abc123"
RETENTION = {"receipts": "archive", "notion": "keep", "inbox": "delete", "note": "the digest moved into weekly-pre-assembly"}


def proposed(**overrides) -> dict:
    out = {"reason": "the workflow was folded into weekly-pre-assembly", "artifact_retention": dict(RETENTION), "acknowledge_pinned_tests": False}
    out.update(overrides)
    return out


def retire_request(workflow_id="alpha", stage="preview", token=None, reason="the workflow was folded into weekly-pre-assembly", **extra) -> dict:
    prop = {"artifact_retention": dict(RETENTION), "acknowledge_pinned_tests": False, **extra}
    return {"workflow_id": workflow_id, "kind": "retire", "reason": reason, "stage": stage, "preview_token": token, "proposed": prop}


def worktree_diff(wt: pathlib.Path) -> str:
    _git(wt, "add", "-A", "-N")
    return subprocess.run(["git", "diff", "--no-color", "--binary", "-M", "HEAD"], cwd=wt, capture_output=True, text=True, check=True).stdout


def entries(manifest: pathlib.Path) -> list[dict]:
    return tomllib.loads(manifest.read_text())["workflows"]


class Removal(TempState):
    """(::retire-removal-across-joins) (::retire-keeps-shared-runner)"""

    def plan(self, wt: pathlib.Path, workflow_id="alpha", pid=PID, **overrides):
        item = make_item(wt, workflow_id)
        return retire.plan_retire(wt, item, proposed(**overrides), NOW, pid, {"runtime_root": str(FIXTURES / "runtime"), "etc_dir": str(FIXTURES / "etc"), "user_tree": str(FIXTURES / "user")})

    def test_removal_across_joins(self):
        wt = checkout(self.tmp)
        before_entries = entries(wt / "design/agents/claudius.toml")
        plan = self.plan(wt)
        manifest = wt / "design/agents/claudius.toml"
        text = manifest.read_text()
        after = entries(manifest)
        self.assertEqual(len(after), len(before_entries) - 1)
        self.assertEqual(after, [e for e in before_entries if e["unit"] != "alpha"])
        self.assertIn(f"# alpha retired 2026-09-14 via Control Room proposal {PID} (branch control-room/retire-alpha-20260914T080000Z): the workflow was folded into weekly-pre-assembly. Artifacts: receipts=archive notion=keep inbox=delete. Record: design/retired-workflows.toml.", text)
        surfaces = tomllib.loads(text)["surfaces"]["scheduled"]
        self.assertTrue(surfaces["present"])
        self.assertEqual(surfaces["governed_by"], "bin/run_beta_cc.sh, bin/run_gamma_cc.sh")
        self.assertNotIn("alpha\t", (wt / "config/fleet-units.tsv").read_text())
        self.assertNotIn("alpha.service", (wt / "bin/buzz_producers.tsv").read_text())
        self.assertEqual((wt / "bin/buzz_routes.env").read_text(), (FIXTURES / "repo/bin/buzz_routes.env").read_text())
        for relative in ("systemd/alpha.timer", "systemd/alpha.service", "bin/run_alpha_cc.sh", "profiles/alpha_task.md",
                         "profiles/alpha.env.example", "tests/test_alpha_smoke.sh", "design/contracts/alpha.md"):
            self.assertFalse((wt / relative).exists(), relative)
        self.assertTrue((wt / "systemd/archive/alpha.timer").is_file())
        self.assertTrue((wt / "systemd/archive/alpha.service").is_file())
        self.assertNotIn("test_alpha_smoke.sh", (wt / "tests/ci-expected-skips.txt").read_text())
        self.assertIn("test_other.sh", (wt / "tests/ci-expected-skips.txt").read_text())
        archived = (wt / "design/archive/contracts/alpha.md").read_text()
        self.assertTrue(archived.startswith(f"> RETIRED 2026-09-14 — Control Room proposal {PID}; the workflow no longer exists. Kept as history for T5.4's evidence.\n"))
        self.assertIn("## Trigger", archived)
        exclusions = tomllib.loads((wt / "design/deploy-exclusions.toml").read_text())["runtime_only"]
        mine = [e for e in exclusions if PID in e["why"]]
        self.assertEqual(sorted((e["tree"], e["path"]) for e in mine), [("profiles", "alpha.env.example"), ("profiles", "alpha_task.md"), ("systemd", "alpha.service"), ("systemd", "alpha.timer")])
        registry = tomllib.loads((wt / "design/retired-workflows.toml").read_text())["retired"]
        self.assertEqual(len(registry), 1)
        entry = registry[0]
        self.assertEqual(entry["id"], "alpha")
        self.assertEqual(entry["units"], ["alpha"])
        self.assertEqual(entry["pr"], "")
        self.assertEqual(entry["runners"], ["bin/run_alpha_cc.sh"])
        self.assertEqual(entry["profiles"], ["profiles/alpha_task.md", "profiles/alpha.env.example"])
        self.assertEqual(entry["contract"], "design/archive/contracts/alpha.md")
        self.assertEqual(entry["suites"], ["tests/test_alpha_smoke.sh"])
        self.assertEqual(entry["env_override"], "/home/dave/.config/agent-workforce/alpha.env")
        self.assertEqual(entry["run_markers"], ["/home/dave/logs/run-markers/alpha.service"])
        self.assertEqual(entry["artifact_retention"], RETENTION)
        self.assertEqual(entry["residue_cleared_on"], "")
        self.assertFalse(entry["env_removed_attested"])
        self.assertEqual(entry["proposal"], PID)
        views = (wt / "tests/test_control_room_views.py").read_text()
        self.assertIn("STANDING_ENTRIES = 4\n", views)
        self.assertIn("LOGICAL_WORKFLOWS = 3\n", views)
        self.assertIn("RETRY_BUDGET = 3  #", views)
        self.assertEqual((wt / "docs/runbook.md").read_text(), (FIXTURES / "repo/docs/runbook.md").read_text())
        source = plan.context()["residue"]["source"]
        self.assertEqual(source["verdict"], "clear", residue.render_w19_table(source))
        self.assertTrue(any(i["class"] == "prose" and i["path"] == "docs/runbook.md" for i in source["items"]))
        self.assertEqual(plan.context()["retention"], RETENTION)
        self.assertEqual(plan.context()["deleted"], ["tests/test_alpha_smoke.sh"])
        self.assertIn("tests/test_control_room_views.sh", plan.context()["pinned_extra"])
        second = checkout(self.tmp, "wt2")
        self.plan(second)
        self.assertEqual(worktree_diff(wt), worktree_diff(second))

    def test_keeps_shared_runner(self):
        wt = checkout(self.tmp)
        plan = self.plan(wt)
        self.assertTrue((wt / "bin/agent_propose.sh").is_file())
        self.assertIn("bin/agent_propose.sh: shared, kept — still exec'd by beta.service", plan.reviewer_attention)
        self.assertIn("bin/agent_propose.sh: shared, kept — still exec'd by beta.service", plan.description["shared_runners"])
        subjects = retire.subject_set(wt, make_item(wt, "beta"))
        propose = next(r for r in subjects["runners"] if r["path"] == "bin/agent_propose.sh")
        self.assertTrue(propose["owned"], subjects["runners"])

    def test_two_trigger_retires_both(self):
        """(::retire-two-trigger-retires-both)"""
        wt = checkout(self.tmp)
        plan = self.plan(wt, "gamma", pid="20260914T080000Z-retire-gamma-abc123")
        self.assertEqual(plan.units, ["gamma", "gamma-dispatch"])
        for unit in ("gamma", "gamma-dispatch"):
            self.assertTrue((wt / f"systemd/archive/{unit}.timer").is_file())
            self.assertTrue((wt / f"systemd/archive/{unit}.service").is_file())
            self.assertNotIn(f"{unit}.service", (wt / "bin/buzz_producers.tsv").read_text())
            self.assertNotIn(f"{unit}\t", (wt / "config/fleet-units.tsv").read_text())
        registry = tomllib.loads((wt / "design/retired-workflows.toml").read_text())["retired"]
        self.assertEqual(len(registry), 1)
        self.assertEqual(registry[0]["units"], ["gamma", "gamma-dispatch"])
        self.assertEqual(registry[0]["runners"], ["bin/run_gamma_cc.sh"])
        self.assertFalse((wt / "bin/run_gamma_cc.sh").exists())
        self.assertIn("STANDING_ENTRIES = 3\n", (wt / "tests/test_control_room_views.py").read_text())
        self.assertIn("LOGICAL_WORKFLOWS = 3\n", (wt / "tests/test_control_room_views.py").read_text())

    def test_empties_a_surface(self):
        """(::retire-empties-a-surface)"""
        wt = checkout(self.tmp)
        self.plan(wt, "refresh", pid="20260914T080000Z-retire-refresh-abc123")
        text = (wt / "design/agents/trajan.toml").read_text()
        surface = tomllib.loads(text)["surfaces"]["scheduled"]
        self.assertFalse(surface["present"])
        self.assertEqual(surface["retired"], "2026-09-14")
        self.assertEqual(surface["governed_by"], "")
        self.assertIn('present     = false\nretired     = "2026-09-14"\n', text)
        shutil.copy(HERE / "test_manifest_surfaces.sh", wt / "tests/test_manifest_surfaces.sh")
        done = subprocess.run(["bash", "tests/test_manifest_surfaces.sh"], cwd=wt, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        second = checkout(self.tmp, "wt2")
        self.plan(second, "alpha")
        self.plan(second, "beta", pid="20260914T080100Z-retire-beta-abc123")
        claudius = tomllib.loads((second / "design/agents/claudius.toml").read_text())
        self.assertTrue(claudius["surfaces"]["scheduled"]["present"])
        self.assertEqual(claudius["surfaces"]["scheduled"]["governed_by"], "bin/run_gamma_cc.sh")
        self.assertEqual([e["unit"] for e in claudius["workflows"]], ["gamma", "gamma-dispatch"])
        self.assertEqual(len(tomllib.loads((second / "design/retired-workflows.toml").read_text())["retired"]), 2)


class Retention(TempState):
    """(::retire-needs-explicit-retention) (::retire-refusals)"""

    def test_needs_explicit_retention(self):
        wt = checkout(self.tmp)
        item = make_item(wt, "alpha")
        with self.assertRaises(Refused) as refused:
            retire.plan_retire(wt, item, {"reason": "the workflow was folded into weekly-pre-assembly"}, NOW, PID)
        self.assertEqual(refused.exception.code, "retention_required")
        for missing in ("note", "inbox"):
            partial = {k: v for k, v in RETENTION.items() if k != missing}
            with self.assertRaises(Refused) as refused:
                retire.validate_retention({"artifact_retention": partial})
            self.assertEqual(refused.exception.code, "retention_required")
            self.assertIn(missing, refused.exception.message)
        with self.assertRaises(Refused) as refused:
            retire.validate_retention({"artifact_retention": {**RETENTION, "receipts": "delete"}})
        self.assertEqual(refused.exception.code, "bad_request")
        self.assertEqual(retire.validate_retention({"artifact_retention": dict(RETENTION)}), RETENTION)
        self.assertEqual(worktree_diff(wt), "")

    def test_refusals(self):
        wt = checkout(self.tmp)
        with self.assertRaises(Refused) as refused:
            retire.plan_retire(wt, make_item(wt, "buzz-agent@trajan"), proposed(), NOW, PID)
        self.assertEqual(refused.exception.code, "not_a_timer")
        manifest = wt / "design/agents/claudius.toml"
        manifest.write_text(manifest.read_text().replace('unit     = "beta"\nsurface  = "scheduled"\ntrigger  = "Mon-Fri 06:00"\nmodel    = "claude-opus-5"\nprofile  = "profiles/beta_task.md"\nrunner   = "bin/run_beta_cc.sh"\nroute    = "ops"\nweb      = false\ncontract = "design/contracts/beta.md"\nstatus   = "standing"', 'unit     = "beta"\nsurface  = "scheduled"\ntrigger  = "Mon-Fri 06:00"\nmodel    = "claude-opus-5"\nprofile  = "profiles/beta_task.md"\nrunner   = "bin/run_beta_cc.sh"\nroute    = "ops"\nweb      = false\ncontract = "design/contracts/beta.md"\nstatus   = "planned"'))
        self.assertIn('status   = "planned"', manifest.read_text())
        _git(wt, "commit", "-qam", "beta planned")
        with self.assertRaises(Refused) as refused:
            retire.plan_retire(wt, make_item(wt, "beta"), proposed(), NOW, PID)
        self.assertEqual(refused.exception.code, "not_standing")
        with self.assertRaises(Refused) as refused:
            retire.plan_retire(wt, make_item(wt, "alpha"), proposed(reason="x"), NOW, PID)
        self.assertEqual(refused.exception.code, "bad_request")
        self.assertEqual(worktree_diff(wt), "")
        spent = checkout(self.tmp, "spent")
        manifest = spent / "design/agents/claudius.toml"
        manifest.write_text(manifest.read_text().replace('contract = "design/contracts/alpha.md"\nstatus   = "standing"', 'contract = "design/contracts/alpha.md"\ncontract_exempt = "nekovri-shaped: every date fired"\nstatus   = "spent"'))
        item = make_item(spent, "alpha")
        self.assertEqual(item["lifecycle"], "spent")
        plan = retire.plan_retire(spent, item, proposed(), NOW, PID)
        self.assertEqual(plan.context()["subjects"]["contract"], "")
        self.assertTrue((spent / "design/contracts/alpha.md").is_file())
        self.assertEqual(tomllib.loads((spent / "design/retired-workflows.toml").read_text())["retired"][0]["contract"], "")


class ThroughTheWorker(TempState):
    """(::retire-count-literals-or-pinned) (::retire-pr-body-sections) (::residue-fails-closed-on-branch)"""

    def setUp(self) -> None:
        super().setUp()
        self.worker = make_worker(self.tmp, self.remote, runner=self.runner())

    @staticmethod
    def runner():
        def run(argv, cwd, env, timeout):
            if argv[:2] == ["bash", "bin/deploy"]:
                return 0, "dry-run:\n  [systemd] delete alpha.timer\n  [systemd] delete alpha.service\n  [profiles] delete alpha_task.md\n  [systemd] delete deferred.service\n", ""
            if argv[:1] == ["bash"] and argv[1].startswith("tests/"):
                done = subprocess.run(argv, cwd=cwd, env={**os.environ, **env}, capture_output=True, text=True, timeout=timeout)
                return done.returncode, done.stdout, done.stderr
            return 0, "ok\n", ""
        return run

    def check(self, response, check_id):
        return next(c for c in response["checks"] if c["id"] == check_id)

    def test_count_literals_or_pinned(self):
        rec, response = self.worker.preview(retire_request(), ACTOR)
        self.assertEqual(rec["stage"], "previewed", response)
        pinned = self.check(response, "pinned-tests")
        self.assertEqual(pinned["status"], "pass", pinned["output"])
        self.assertIn("tests/test_control_room_views.sh", pinned["output"])
        self.assertIn("+STANDING_ENTRIES = 4", response["diff"])
        self.assertTrue(response["submit_allowed"], response["submit_blockers"])
        self.assertFalse(rec["draft"])
        variant_tmp = self.tmp / "variant"
        variant_tmp.mkdir()
        remote, _ = make_remote(variant_tmp, variant="test_control_room_views.py")
        worker = make_worker(variant_tmp, remote, runner=self.runner())
        rec, response = worker.preview(retire_request(), ACTOR)
        self.assertEqual(rec["stage"], "previewed", response)
        pinned = self.check(response, "pinned-tests")
        self.assertEqual(pinned["status"], "fail")
        self.assertIn("tests/test_control_room_views.sh + tests/test_control_room_views.py", pinned["output"])
        self.assertFalse(response["submit_allowed"])
        self.assertTrue(any(b.startswith("checks_failed") for b in response["submit_blockers"]))
        rec, response = worker.submit(retire_request(stage="submit", token=rec["proposal_id"]), ACTOR)
        self.assertEqual(response["error"]["code"], "checks_failed")
        rec, response = worker.preview(retire_request(acknowledge_pinned_tests=True), ACTOR)
        self.assertTrue(response["submit_allowed"], response["submit_blockers"])
        self.assertTrue(rec["draft"])
        rec, response = worker.submit(retire_request(stage="submit", token=rec["proposal_id"], acknowledge_pinned_tests=True), ACTOR)
        self.assertEqual(rec["stage"], "submitted", response)
        self.assertTrue(response["pr"]["draft"])
        creates = [e for e in gh_log(variant_tmp) if e["call"] == "pr create"]
        self.assertIn("--draft", creates[0]["argv"])
        self.assertIn("Red on purpose until tests/test_control_room_views.sh", creates[0]["body"])

    def test_pr_body_sections(self):
        rec, response = self.worker.preview(retire_request(), ACTOR)
        self.assertEqual(rec["stage"], "previewed", response)
        text = body.body(rec)
        sections = ["## Decision evidence", "## Artifact retention", "## Removal", "## Residue (W19 class)", "## Checks", "## Reviewer attention", "## Land (Dave-only"]
        positions = [text.index(s) for s in sections]
        self.assertEqual(positions, sorted(positions))
        self.assertEqual(text.count("| # | residue | tree | has a check? | who clears it | how |"), 2)
        self.assertIn("bin/deploy --prune", text)
        self.assertIn("systemd/deferred.service", text.split("**which also deletes:**")[1].splitlines()[0])
        self.assertIn(f"sudo rm {FIXTURES / 'etc'}/alpha.timer", text)
        self.assertIn("/etc/systemd/system/alpha.timer", text)
        self.assertIn("ls -l /home/dave/.config/agent-workforce/alpha.env", text)
        self.assertIn("workflow_pr.py clear alpha --env-removed", text)
        self.assertNotIn("enable --now", text)
        self.assertNotIn("systemctl start", text)
        for key, value in RETENTION.items():
            self.assertIn(f"| {key} | {value} |", text)
        self.assertIn("unverifiable from an agent", text)
        self.assertEqual(rec["retention"], RETENTION)
        self.assertEqual(rec["residue"]["source"]["verdict"], "clear")
        self.assertEqual(rec["residue"]["live"]["verdict"], "residue")
        self.assertTrue(any(i["class"] == "installed" for i in rec["residue"]["live"]["items"]))
        self.assertEqual(body.title(rec), f"control-room(retire): alpha — retire alpha")

    def test_residue_fails_closed_on_branch(self):
        original = retire.plan_retire

        def sabotage(worktree, item, proposed_, now, pid, live=None):
            plan = original(worktree, item, proposed_, now, pid, live)
            shutil.copy(FIXTURES / "repo/systemd/alpha.timer", pathlib.Path(worktree) / "systemd/alpha.timer")
            plan._context["residue"]["source"] = residue.scan_source(pathlib.Path(worktree), plan.context()["subjects"])
            return plan
        retire.plan_retire = sabotage
        self.addCleanup(setattr, retire, "plan_retire", original)
        preview, response = self.worker.preview(retire_request(), ACTOR)
        self.assertEqual(preview["stage"], "previewed", response)
        self.assertFalse(response["submit_allowed"], response["submit_blockers"])
        self.assertTrue(any(b.startswith("residue_in_branch") for b in response["submit_blockers"]), response["submit_blockers"])
        rec, response = self.worker.submit(retire_request(stage="submit", token=preview["proposal_id"]), ACTOR)
        self.assertEqual(response["error"]["code"], "residue_in_branch", response)
        self.assertIn("systemd/alpha.timer", response["error"]["message"])
        self.assertEqual(rec["stage"], "refused")
        self.assertEqual(remote_heads(self.remote), ["main"])
        self.assertEqual([e for e in gh_log(self.tmp) if e["call"] == "pr create"], [])


if __name__ == "__main__":
    unittest.main()
