#!/usr/bin/env python3
"""bin/board_land.py: land, sweep, Done by join with main, the card exceptions (Dev Plan B6).

Beside tests/test_board.py (which a ship rail keeps closed to edits). Synthetic cards only; the
canonical vault is a temporary bare repository plus a clone of it, never the real remote."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import subprocess
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "tests"))

import board  # noqa: E402
import board_land  # noqa: E402
import workflow_incidents as wi  # noqa: E402
from test_board import FixtureBox  # noqa: E402

TEXT = "Findings.\n\n- Alpha holds.\n\n## Acceptance\n\nA: MET\n"
BRIEF = ("# Brief: alpha-card\n\n## Question\n\nDoes the synthetic\nthing hold?\n\n## Why\n\nBecause.\n")
HASH = board.text_hash(TEXT)
GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]


def sh(*argv, cwd=None):
    return subprocess.run(argv, cwd=cwd, capture_output=True, text=True, check=True).stdout


class LandBox(FixtureBox):
    def setUp(self):
        super().setUp()
        for name, value in (("CONTROL_ROOM_INCIDENT_ROOT", str(self.tmp / "incidents")),
                            ("GIT_CONFIG_GLOBAL", "/dev/null"), ("GIT_CONFIG_NOSYSTEM", "1"),
                            ("BOARD_NOTION_MARK_CMD", f"{sys.executable} {self.tmp / 'mark.py'}")):
            os.environ[name] = value
        (self.tmp / "mark.py").write_text(
            "import sys\nopen(%r, 'a').write(' '.join(sys.argv[1:]) + '\\n')\n" % str(self.tmp / "marks.log"))
        self.origin = self.tmp / "origin.git"
        seed = self.tmp / "seed"
        sh("git", "init", "-q", "--bare", "-b", "main", str(self.origin))
        sh("git", "init", "-q", "-b", "main", str(seed))
        (seed / "05_knowledge").mkdir()
        (seed / "05_knowledge" / "own.md").write_text("Dave's own note\n")
        sh(*GIT, "-C", str(seed), "add", "-A")
        sh(*GIT, "-C", str(seed), "commit", "-q", "-m", "seed")
        sh("git", "-C", str(seed), "push", "-q", str(self.origin), "main")
        sh("git", "clone", "-q", str(self.origin), str(self.tmp / "clone"))
        self.clone = self.tmp / "clone"

    def reviewed(self, card_id: str = "alpha-card", text: str = TEXT, signed: str = HASH, **extra) -> None:
        self.assertEqual(self.create(card_id, "--tags", "synthetic,alpha")[0], 0)
        digest = self.write_brief(card_id, BRIEF)
        self.decide("brief_approved", card_id, brief_hash=digest)
        self.cli("pick", "--owner", "claudius", "--run-id", "r1", "--workflow", "agent-proposal")
        self.receipt("r1", "artifact", page="0a1b2c3d-page")
        self.decide("approved", card_id, page_hash=signed, text=text, **extra)

    def approval_date(self) -> str:
        return json.loads((self.tmp / "decisions" / "decisions.jsonl").read_text().splitlines()[-1])["ts"][:10]

    def branches(self) -> list[str]:
        return [b.split("refs/heads/")[1] for b in sh("git", "-C", str(self.origin), "show-ref").splitlines()
                if "refs/heads/" in b]

    def marks(self) -> list[str]:
        path = self.tmp / "marks.log"
        return path.read_text().splitlines() if path.exists() else []

    def merge_branch(self, branch: str) -> None:
        sh("git", "-C", str(self.origin), "update-ref", "refs/heads/main", f"refs/heads/{branch}")

    def open_incidents(self) -> set[str]:
        items, _ = wi.load_declared(board_land.incident_root())
        return {i["key"] for i in items if i["resolved_at"] is None}


class Landing(LandBox):  # (::board-land)
    def test_an_approval_lands_as_one_note_on_a_card_branch_cut_from_main(self):
        self.reviewed()
        code, out, err = self.cli("land")
        self.assertEqual(code, 0, err)
        branch = f"agents/{self.approval_date()}-card-alpha-card"
        self.assertEqual(sorted(self.branches()), sorted([branch, "main"]))
        self.assertIn(f"landed alpha-card {branch}", out)
        added = sh("git", "-C", str(self.origin), "diff", "--name-status", f"main..{branch}").split()
        self.assertEqual(added, ["A", "05_knowledge/research/alpha-card.md"])
        note = sh("git", "-C", str(self.origin), "show", f"{branch}:05_knowledge/research/alpha-card.md")
        front, body = note.split("---\n")[1], note.split("---\n", 2)[2]
        self.assertEqual(board.text_hash(body), HASH)
        for line in ("type: research", "card: alpha-card", 'title: "Title of alpha-card"',
                     'question: "Does the synthetic thing hold?"', 'tags: ["synthetic", "alpha"]',
                     f"approved: {self.approval_date()}", "notion: https://www.notion.so/0a1b2c3dpage",
                     "run: r1", f"content: {HASH}"):
            self.assertIn(line, front.splitlines())
        self.assertRegex(front, r"brief: [0-9a-f]{64}")

    def test_landing_leaves_no_worktree_no_event_and_is_idempotent(self):
        self.reviewed()
        before = (self.tmp / "board/cards/alpha-card/events.jsonl").read_text()
        self.cli("land")
        again = self.cli("land")
        self.assertEqual(again[1].strip(), "")
        self.assertEqual((self.tmp / "board/cards/alpha-card/events.jsonl").read_text(), before)
        self.assertEqual(sh("git", "-C", str(self.clone), "worktree", "list").count("\n"), 1)
        self.assertEqual(len([b for b in self.branches() if "card-" in b]), 1)

    def test_an_existing_remote_branch_is_not_pushed_over(self):
        self.reviewed()
        self.cli("land")
        (self.tmp / "board/cards/alpha-card/landed.json").unlink()
        self.assertEqual(self.cli("land")[0], 0)
        self.assertEqual(len([b for b in self.branches() if "card-" in b]), 1)
        self.assertTrue((self.tmp / "board/cards/alpha-card/landed.json").exists())

    def test_text_that_does_not_hash_to_the_signed_hash_lands_nothing_and_raises(self):
        self.reviewed(text=TEXT + "tampered\n")
        out = self.cli("sweep")[1]
        self.assertEqual([b for b in self.branches() if "card-" in b], [])
        self.assertIn("exception land-refused alpha-card", out)
        self.assertEqual(len(self.open_incidents()), 1)

    def test_an_approval_with_no_text_or_no_clone_raises_instead_of_failing_the_run(self):
        self.reviewed()
        decisions = self.tmp / "decisions" / "decisions.jsonl"
        rows = [json.loads(line) for line in decisions.read_text().splitlines()]
        without = [{k: v for k, v in r.items() if k != "text"} for r in rows]
        decisions.write_text("".join(json.dumps(r) + "\n" for r in without))
        self.assertIn("exception land-refused alpha-card", self.cli("sweep")[1])
        decisions.write_text("".join(json.dumps(r) + "\n" for r in rows))
        os.environ["BOARD_CANONICAL_CLONE"] = str(self.tmp / "nowhere")
        self.assertIn("exception land-refused alpha-card", self.cli("sweep")[1])

    def test_a_failed_push_raises_land_refused(self):
        self.reviewed()
        sh("git", "-C", str(self.clone), "remote", "set-url", "origin", str(self.tmp / "gone.git"))
        self.assertIn("exception land-refused alpha-card", self.cli("sweep")[1])

    def test_a_card_not_in_review_or_not_approved_does_not_land(self):
        self.assertEqual(self.create("quiet-card")[0], 0)
        self.reviewed("alpha-card")
        self.decide("rejected", "alpha-card")
        self.cli("land")
        self.assertEqual([b for b in self.branches() if "card-" in b], [])
        self.assertEqual(self.cli("land", "--card", "nope-card")[0], 1)


class Closing(LandBox):  # (::board-done-join)
    def test_done_is_the_join_with_main_and_the_sweep_marks_the_page_merged(self):
        self.reviewed()
        self.cli("sweep")
        self.assertEqual(self.column(), "In Review")
        branch = f"agents/{self.approval_date()}-card-alpha-card"
        self.merge_branch(branch)
        out = self.cli("sweep")[1]
        self.assertEqual(self.column(), "Done")
        self.assertIn("marked alpha-card merged", out)
        self.assertEqual(self.marks(), ["mark --card alpha-card --state merged --path 05_knowledge/research/alpha-card.md"])
        self.cli("sweep")
        self.assertEqual(len(self.marks()), 1)
        self.assertEqual(self.open_incidents(), set())

    def test_a_note_merged_with_another_hash_stays_in_review(self):
        self.reviewed()
        self.cli("land")
        wrong = self.tmp / "wrong"
        sh("git", "clone", "-q", str(self.origin), str(wrong))
        sh("git", "-C", str(wrong), "checkout", "-q", "-b", "w", "origin/main")
        notes = wrong / board.RESEARCH_NOTE_DIR
        notes.mkdir(parents=True)
        (notes / "alpha-card.md").write_text("---\ncontent: " + "e" * 64 + "\n---\nother\n")
        sh(*GIT, "-C", str(wrong), "add", "-A")
        sh(*GIT, "-C", str(wrong), "commit", "-q", "-m", "other")
        sh("git", "-C", str(wrong), "push", "-q", "origin", "w:main")
        self.cli("sweep")
        self.assertEqual(self.column(), "In Review")

    def test_a_rejection_marks_the_page_rejected_and_lands_nothing(self):
        self.reviewed()
        self.cli("land")
        self.decide("rejected", "alpha-card", reason="no")
        self.assertEqual(self.cli("sweep")[0], 0)
        self.assertEqual(self.column(), "Done")
        self.assertEqual(self.marks(), ["mark --card alpha-card --state rejected"])

    def test_a_failed_mark_is_retried_by_the_next_sweep(self):
        self.reviewed()
        self.decide("rejected", "alpha-card")
        good = os.environ["BOARD_NOTION_MARK_CMD"]
        os.environ["BOARD_NOTION_MARK_CMD"] = f"{sys.executable} -c 'raise SystemExit(1)'"
        self.assertNotIn("marked", self.cli("sweep")[1])
        os.environ["BOARD_NOTION_MARK_CMD"] = good
        self.assertIn("marked alpha-card rejected", self.cli("sweep")[1])


def now_at(days_ago: int) -> dt.datetime:
    return dt.datetime(2026, 10, 9, 12, 0, tzinfo=dt.timezone.utc) - dt.timedelta(days=days_ago)


class Exceptions(LandBox):  # (::board-card-exceptions)
    def kinds(self, view, events=(), landed=None, now=None):
        return [e["kind"] for e in board_land.card_exceptions(view, list(events), landed, now or now_at(0))]

    def view(self, events, decisions=(), receipts=None):
        from test_board import CARD
        return board.derive(CARD, events, list(decisions), receipts or {}, {}, now_at(0))

    def test_refine_stale_after_three_working_days_not_over_a_weekend(self):
        brief = {"ts": "2026-10-05T09:00:00Z", "event": "brief", "actor": "run:b", "hash": "a" * 64}
        created = {"ts": "2026-10-05T08:00:00Z", "event": "created", "actor": "dave"}
        view = self.view([created, brief])
        self.assertEqual(view["column"], "Refine")
        self.assertIn("refine-stale", self.kinds(view, [created, brief], now=dt.datetime(2026, 10, 8, 9, tzinfo=dt.timezone.utc)))
        self.assertNotIn("refine-stale", self.kinds(view, [created, brief], now=dt.datetime(2026, 10, 7, 9, tzinfo=dt.timezone.utc)))
        friday = {**brief, "ts": "2026-10-02T09:00:00Z"}
        self.assertNotIn("refine-stale", self.kinds(view, [created, friday], now=dt.datetime(2026, 10, 6, 9, tzinfo=dt.timezone.utc)))

    def test_review_stale_and_merge_stale(self):
        self.reviewed()
        views = board.collect(self.tmp / "board")
        view = views["alpha-card"]
        later = dt.datetime.now().astimezone() + dt.timedelta(days=5)
        self.assertIn("review-stale", self.kinds({**view, "approved_landing": False}, now=later))
        landed = {"ts": "2026-10-09T10:00:00Z", "branch": "agents/x-card-alpha-card"}
        self.assertIn("merge-stale", self.kinds(view, landed=landed, now=dt.datetime(2026, 10, 9, 12, 1, tzinfo=dt.timezone.utc)))
        self.assertNotIn("merge-stale", self.kinds(view, landed=landed, now=dt.datetime(2026, 10, 9, 11, tzinfo=dt.timezone.utc)))
        self.assertNotIn("merge-stale", self.kinds(view, landed=None, now=later))

    def test_the_block_causes_map_to_their_exception_kinds(self):
        for cause, kind in board_land.BLOCK_KINDS.items():
            with self.subTest(cause=cause):
                self.assertEqual(self.kinds({"id": "x", "exceptions": [], "blocked_cause": cause, "column": "Blocked",
                                             "approved_landing": False, "runs": []}), [kind])

    def test_forged_and_stale_pick_pass_through_one_per_card_and_kind(self):
        self.assertEqual(self.create()[0], 0)
        with open(self.tmp / "board/cards/alpha-card/events.jsonl", "a") as handle:
            handle.write(json.dumps({"ts": "2026-10-09T09:00:00Z", "event": "approved", "actor": "dave"}) + "\n")
            handle.write(json.dumps({"ts": "2026-10-09T09:01:00Z", "event": "approved", "actor": "dave"}) + "\n")
        out = self.cli("sweep")[1]
        self.assertEqual(out.count("exception forged-decision alpha-card"), 1)
        self.assertEqual(len(self.open_incidents()), 1)

    def test_an_exception_is_declared_once_and_resolved_when_the_condition_clears(self):
        self.reviewed()
        card_dir = self.tmp / "board/cards/alpha-card"
        (card_dir / "landed.json").write_text(json.dumps({"ts": "2020-01-01T00:00:00Z", "branch": "agents/x", "page_hash": HASH}))
        self.assertIn("exception merge-stale alpha-card", self.cli("sweep")[1])
        self.cli("sweep")
        items, errors = wi.load_declared(board_land.incident_root())
        self.assertEqual((len(items), errors), (1, []))
        self.assertEqual((items[0]["class"], items[0]["severity"], items[0]["agent"]), ("board-exception", "medium", "claudius"))
        self.assertIn("Dave", items[0]["required_action"])
        self.decide("rejected", "alpha-card")
        self.assertIn("resolved", self.cli("sweep")[1])
        self.assertEqual(self.open_incidents(), set())


if __name__ == "__main__":
    unittest.main()
