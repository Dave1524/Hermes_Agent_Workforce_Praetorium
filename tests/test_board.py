#!/usr/bin/env python3
"""bin/board.py: the card ledger, its derivation and its verbs. Synthetic cards only; the
broker's stream, the receipts and canonical main are fixtures built here."""

from __future__ import annotations

import contextlib
import datetime as dt
import io
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import board  # noqa: E402
import workflow_receipt as wr  # noqa: E402

NOW = dt.datetime(2026, 10, 6, 12, 0, tzinfo=dt.timezone.utc)
CARD = {"id": "alpha-card", "title": "Alpha question", "idea": "Does the synthetic thing hold?",
        "kind": "research", "owner": "claudius", "scope": ["vault:05_knowledge"],
        "deadline": None, "research_on": None, "priority": None, "tags": []}
BRIEF_A, BRIEF_B, PAGE = "a" * 64, "b" * 64, "c" * 64


def at(day: int, hour: int = 9) -> str:
    return f"2026-10-{day:02d}T{hour:02d}:00:00Z"


def ev(event: str, ts: str, actor: str = "dave", **extra) -> dict:
    return {"ts": ts, "event": event, "actor": actor, **extra}


def dec(decision: str, ts: str, card: str = "alpha-card", **extra) -> dict:
    return {"ts": ts, "decision": decision, "card": card, **extra}


def pick(ts: str, run: str, purpose: str = "research") -> dict:
    return ev("picked", ts, f"run:{run}", run_id=run, workflow="agent-proposal", fields={"purpose": purpose})


def rcpt(outcome: str, page: str | None = "page-1") -> dict:
    block = {"card": {"id": "alpha-card", "page": page, "page_hash": PAGE}} if page else {}
    return {"terminal": {"outcome": outcome}, **block}


def derive(events, decisions=(), receipts=None, main=None, card=None, now=NOW, timeout=3600):
    return board.derive(card or CARD, list(events), list(decisions), receipts or {}, main or {}, now, timeout)


CREATED = ev("created", at(1))
BRIEF = ev("brief", at(2), "run:b1", hash=BRIEF_A, run_id="b1")
APPROVE = dec("brief_approved", at(3), brief_hash=BRIEF_A)
PICK = pick(at(5), "r1")


class Columns(unittest.TestCase):  # (::board-derive-columns)
    def test_every_column_is_derived_from_events_decisions_and_receipts(self):
        landed = {"alpha-card": PAGE}
        cases = {
            "Backlog": dict(events=[CREATED]),
            "Refine": dict(events=[CREATED, BRIEF]),
            "Todo": dict(events=[CREATED, BRIEF], decisions=[APPROVE]),
            "In Progress": dict(events=[CREATED, BRIEF, pick(at(6, 11), "r1")], decisions=[APPROVE]),
            "In Review": dict(events=[CREATED, BRIEF, PICK], decisions=[APPROVE], receipts={"r1": rcpt("artifact")}),
            "Done": dict(events=[CREATED, BRIEF, PICK], decisions=[APPROVE, dec("approved", at(6), page_hash=PAGE)],
                         receipts={"r1": rcpt("artifact")}, main=landed),
            "Blocked": dict(events=[CREATED, BRIEF], decisions=[APPROVE, dec("blocked", at(4))]),
        }
        for column, kwargs in cases.items():
            with self.subTest(column=column):
                self.assertEqual(derive(**kwargs)["column"], column)

    def test_a_returned_brief_or_an_edited_idea_sends_the_card_back_to_backlog(self):
        returned = derive([CREATED, BRIEF], [dec("brief_returned", at(3), brief_hash=BRIEF_A, reason="narrow it")])
        edited = derive([CREATED, BRIEF, ev("edited", at(4), fields={"idea": {"old": "x", "new": "y"}})], [APPROVE])
        self.assertEqual((returned["column"], edited["column"]), ("Backlog", "Backlog"))

    def test_a_title_edit_leaves_an_approved_brief_standing(self):
        view = derive([CREATED, BRIEF, ev("edited", at(4), fields={"title": {"old": "x", "new": "y"}})], [APPROVE])
        self.assertEqual((view["column"], view["fields"]["title"]), ("Todo", "y"))

    def test_a_research_date_ahead_is_scheduled_and_today_is_not(self):
        for research_on, scheduled in (("2026-10-07", True), ("2026-10-06", False), ("2026-10-01", False)):
            with self.subTest(research_on=research_on):
                view = derive([CREATED, BRIEF], [APPROVE], card={**CARD, "research_on": research_on})
                self.assertEqual((view["column"], view["scheduled"]), ("Todo", scheduled))

    def test_an_approval_waits_in_review_until_its_hash_is_on_main(self):
        decisions = [APPROVE, dec("approved", at(6), page_hash=PAGE)]
        base = dict(events=[CREATED, BRIEF, PICK], decisions=decisions, receipts={"r1": rcpt("artifact")})
        landing = derive(**base, main={"alpha-card": "d" * 64})
        merged = derive(**base, main={"alpha-card": PAGE})
        self.assertEqual((landing["column"], landing["approved_landing"], landing["moves"]), ("In Review", True, []))
        self.assertEqual((merged["column"], merged["outcome"]), ("Done", "merged"))

    def test_a_rejection_is_done_and_reads_withdrawn_outside_review(self):
        reviewed = derive([CREATED, BRIEF, PICK], [APPROVE, dec("rejected", at(6), reason="no")],
                          {"r1": rcpt("artifact")})
        early = derive([CREATED], [dec("rejected", at(2), reason="changed my mind")])
        self.assertEqual((reviewed["column"], reviewed["outcome"]), ("Done", "rejected"))
        self.assertEqual((early["column"], early["outcome"]), ("Done", "withdrawn"))

    def test_changes_requested_returns_the_card_to_todo_for_the_next_pick(self):
        view = derive([CREATED, BRIEF, PICK], [APPROVE, dec("changes_requested", at(6), reason="cite more")],
                      {"r1": rcpt("artifact")})
        self.assertEqual(view["column"], "Todo")


class Strikes(unittest.TestCase):  # (::board-strikes)
    def test_a_second_return_blocks_and_a_first_does_not(self):
        one = dec("brief_returned", at(3), brief_hash=BRIEF_A)
        two = dec("brief_returned", at(5), brief_hash=BRIEF_B)
        events = [CREATED, BRIEF, ev("brief", at(4), hash=BRIEF_B)]
        self.assertEqual(derive(events, [one])["column"], "Refine")
        view = derive(events, [one, two])
        self.assertEqual((view["column"], view["blocked_cause"]), ("Blocked", "returned twice"))

    def test_two_requests_for_changes_or_two_declines_block(self):
        second = pick(at(7), "r2")
        changes = derive([CREATED, BRIEF, PICK, second], [APPROVE, dec("changes_requested", at(6)),
                         dec("changes_requested", at(8))], {"r1": rcpt("artifact"), "r2": rcpt("artifact")})
        declines = derive([CREATED, BRIEF, PICK, second], [APPROVE], {"r1": rcpt("decline", None), "r2": rcpt("decline", None)})
        self.assertEqual(changes["blocked_cause"], "changes requested twice")
        self.assertEqual(declines["blocked_cause"], "declined twice")
        one_decline = derive([CREATED, BRIEF, PICK], [APPROVE], {"r1": rcpt("decline", None)})
        self.assertEqual(one_decline["column"], "Todo")

    def test_a_passed_deadline_blocks_a_dated_card_and_only_unblocked_lifts_it(self):
        dated = {**CARD, "deadline": "2026-10-05"}
        self.assertEqual(derive([CREATED, BRIEF], [APPROVE], card=dated)["blocked_cause"], "deadline passed")
        edit = ev("edited", at(6), fields={"title": {"old": "x", "new": "y"}})
        self.assertEqual(derive([CREATED, BRIEF, edit], [APPROVE], card=dated)["column"], "Blocked")
        lifted = derive([CREATED, BRIEF], [APPROVE, dec("unblocked", at(6, 10))], card=dated)
        self.assertEqual(lifted["column"], "Todo")

    def test_a_new_deadline_saved_with_unblock_stays_unblocked(self):
        later = ev("edited", at(6, 10), fields={"deadline": {"old": "2026-10-05", "new": "2026-10-20"}})
        view = derive([CREATED, BRIEF, later], [APPROVE, dec("unblocked", at(6, 10))], card={**CARD, "deadline": "2026-10-05"})
        self.assertEqual(view["column"], "Todo")

    def test_an_edit_never_lifts_a_block_and_a_later_strike_blocks_again(self):
        blocked = [dec("blocked", at(4)), dec("unblocked", at(5))]
        self.assertEqual(derive([CREATED, BRIEF], [APPROVE, *blocked])["column"], "Todo")
        again = derive([CREATED, BRIEF], [APPROVE, *blocked, dec("blocked", at(6))])
        self.assertEqual(again["column"], "Blocked")
        edit = ev("edited", at(7), fields={"tags": {"old": [], "new": ["x"]}})
        self.assertEqual(derive([CREATED, BRIEF, edit], [APPROVE, *blocked, dec("blocked", at(6))])["column"], "Blocked")


class Trust(unittest.TestCase):  # (::board-decisions-trust)
    def test_a_decision_shaped_ledger_event_is_forged_and_moves_nothing(self):
        view = derive([CREATED, BRIEF, ev("brief_approved", at(3), hash=BRIEF_A)])
        self.assertEqual(view["column"], "Refine")
        self.assertEqual(view["exceptions"], [{"kind": "forged-decision", "event": "brief_approved"}])

    def test_an_approval_naming_another_brief_or_another_card_moves_nothing(self):
        stale = dec("brief_approved", at(3), brief_hash=BRIEF_B)
        other = dec("brief_approved", at(3), card="beta-card", brief_hash=BRIEF_A)
        self.assertEqual(derive([CREATED, BRIEF], [stale, other])["column"], "Refine")

    def test_a_later_return_of_the_same_hash_overrides_its_approval(self):
        view = derive([CREATED, BRIEF], [APPROVE, dec("brief_returned", at(4), brief_hash=BRIEF_A)])
        self.assertEqual(view["column"], "Backlog")

    def test_derivation_does_not_depend_on_the_order_events_arrive_in(self):
        events = [CREATED, BRIEF, PICK]
        forward = derive(events, [APPROVE], {"r1": rcpt("artifact")})
        backward = derive(events[::-1], [APPROVE], {"r1": rcpt("artifact")})
        self.assertEqual(forward["column"], backward["column"])


class Picks(unittest.TestCase):  # (::board-void-pick)
    def test_a_failed_or_skipped_run_voids_the_pick_without_a_strike(self):
        for outcome in ("failed", "skipped"):
            with self.subTest(outcome=outcome):
                twice = derive([CREATED, BRIEF, PICK, pick(at(7), "r2")], [APPROVE],
                               {"r1": rcpt(outcome, None), "r2": rcpt(outcome, None)})
                self.assertEqual(twice["column"], "Todo")

    def test_an_artifact_that_names_no_page_is_void_not_in_review(self):
        self.assertEqual(derive([CREATED, BRIEF, PICK], [APPROVE], {"r1": rcpt("artifact", None)})["column"], "Todo")

    def test_a_pick_past_the_timeout_without_a_receipt_is_a_stale_pick_still_in_progress(self):
        view = derive([CREATED, BRIEF, pick(at(6, 9), "r1")], [APPROVE], now=NOW, timeout=3600)
        self.assertEqual(view["column"], "In Progress")
        self.assertEqual(view["exceptions"], [{"kind": "stale-pick", "run_id": "r1"}])

    def test_a_brief_run_never_moves_the_column_but_its_declines_count(self):
        runs = [pick(at(2, 10), "b1", "brief"), pick(at(2, 11), "b2", "brief")]
        declined = {"b1": rcpt("decline", None), "b2": rcpt("decline", None)}
        self.assertEqual(derive([CREATED, runs[0]], receipts={})["column"], "Backlog")
        self.assertEqual(derive([CREATED, *runs], receipts=declined)["blocked_cause"], "declined twice")


class Moves(unittest.TestCase):  # (::board-fields-and-moves)
    def test_each_column_offers_its_fields_and_moves_from_the_one_table(self):
        expected = {
            "Backlog": ["withdraw"], "Refine": ["approve_brief", "return_brief", "withdraw"],
            "Todo": ["block", "withdraw"], "In Progress": [], "In Review": ["approve", "request_changes", "reject"],
            "Blocked": ["unblock", "withdraw"], "Done": [],
        }
        for column, moves in expected.items():
            with self.subTest(column=column):
                self.assertEqual(list(board.MOVES[column]), moves)

    def test_in_progress_allows_only_labels_and_notes(self):
        self.assertEqual(board.editable_fields("In Progress", True), ["notes", "priority", "tags", "title"])

    def test_idea_and_scope_close_after_the_first_research_run(self):
        self.assertIn("idea", board.editable_fields("Todo", False))
        self.assertNotIn("idea", board.editable_fields("Todo", True))
        self.assertNotIn("scope", board.editable_fields("Blocked", True))

    def test_done_allows_notes_only_and_the_view_locks_owner_kind_and_id(self):
        self.assertEqual(board.editable_fields("Done", True), ["notes"])
        self.assertEqual(derive([CREATED])["locked"], ["id", "owner", "kind"])


class FixtureBox(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="board-test-"))
        self.saved = dict(os.environ)
        for name, sub in (("BOARD_ROOT", "board"), ("BOARD_DECISIONS_ROOT", "decisions"),
                          ("CONTROL_ROOM_RECEIPT_ROOT", "receipts"), ("BOARD_CANONICAL_CLONE", "clone")):
            os.environ[name] = str(self.tmp / sub)
        (self.tmp / "decisions").mkdir()
        self.briefs = self.tmp / "files"
        self.briefs.mkdir()
        self.clock = 0

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        subprocess.run(["rm", "-rf", str(self.tmp)], check=False)

    def cli(self, *argv: str) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = board.main(list(argv))
        return code, out.getvalue(), err.getvalue()

    def file(self, name: str, text: str) -> str:
        path = self.briefs / name
        path.write_bytes(text.encode())
        return str(path)

    def create(self, card_id: str = "alpha-card", *extra: str, actor: str = "dave") -> tuple[int, str, str]:
        return self.cli("create", "--id", card_id, "--title", f"Title of {card_id}", "--idea", "A synthetic idea",
                        "--owner", "claudius", "--scope", "vault:05_knowledge", "--actor", actor, *extra)

    def write_brief(self, card_id: str = "alpha-card", text: str = "first brief", actor: str = "dave") -> str:
        code, out, err = self.cli("brief", card_id, "--from-file", self.file("b.md", text), "--actor", actor)
        self.assertEqual(code, 0, err)
        return out.strip()

    def decide(self, decision: str, card_id: str = "alpha-card", **extra) -> None:
        self.clock += 1
        ts = wr.iso_utc(wr.utc_now() + dt.timedelta(minutes=10 + self.clock))
        with open(self.tmp / "decisions" / "decisions.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps({"ts": ts, "decision": decision, "card": card_id, **extra}) + "\n")

    def receipt(self, run_id: str, outcome: str, page: str | None = None, workflow: str = "agent-proposal") -> None:
        data = {"schema_version": wr.SCHEMA_VERSION, "workflow_id": workflow, "run_id": run_id,
                "started_at": "2026-10-06T04:30:00Z", "ended_at": "2026-10-06T04:40:00Z",
                "terminal": {"outcome": outcome, "reason": "fixture"}, "assertions": [],
                "usage": wr.unavailable_usage(), "cost": wr.unavailable_cost()}
        if outcome == "artifact":
            data["artifact"] = {"uri": "board://alpha-card/page"}
        if page:
            data["card"] = {"id": "alpha-card", "workflow": workflow, "page": page, "page_hash": PAGE}
        wr.write(data, self.tmp / "receipts")

    def column(self, card_id: str = "alpha-card") -> str:
        return self.cli("status", card_id)[1].strip()

    def approved_card(self, card_id: str = "alpha-card", *extra: str) -> str:
        self.assertEqual(self.create(card_id, *extra)[0], 0)
        digest = self.write_brief(card_id)
        self.decide("brief_approved", card_id, brief_hash=digest)
        return digest


class Creating(FixtureBox):  # (::board-create-rules)
    def test_create_lands_in_backlog_and_writes_one_created_event(self):
        self.assertEqual(self.create()[0], 0)
        events = (self.tmp / "board/cards/alpha-card/events.jsonl").read_text().splitlines()
        self.assertEqual([json.loads(e)["event"] for e in events], ["created"])
        self.assertEqual(self.column(), "Backlog")

    def test_create_with_a_brief_lands_in_refine(self):
        code, _, err = self.create("alpha-card", "--brief", self.file("b.md", "text"))
        self.assertEqual((code, self.column()), (0, "Refine"), err)

    def test_refusals(self):
        self.assertEqual(self.create()[0], 0)
        cases = {
            "duplicate id": self.create(),
            "owner without a runner": self.cli("create", "--id", "x", "--title", "t", "--idea", "i", "--owner", "marcus",
                                               "--scope", "vault:a", "--actor", "dave"),
            "kind not in the pilot": self.cli("create", "--id", "y", "--kind", "dev", "--title", "t", "--idea", "i",
                                              "--owner", "claudius", "--scope", "vault:a", "--actor", "dave"),
            "bad scope": self.cli("create", "--id", "z", "--title", "t", "--idea", "i", "--owner", "claudius",
                                  "--scope", "somewhere", "--actor", "dave"),
            "research date after deadline": self.create("w", "--research-on", "2026-11-02", "--deadline", "2026-11-01"),
            "buzz with a brief": self.create("v", "--brief", self.file("b.md", "t"), actor="buzz:claudius"),
            "a run creating": self.create("u", actor="run:r1"),
            "not an id": self.create("Bad Id"),
            "an id the board API routes on": self.create("decisions"),
        }
        for name, (code, _, err) in cases.items():
            with self.subTest(name):
                self.assertEqual(code, 1)
                self.assertTrue(err.startswith("board: "), err)

    def test_the_owner_table_names_a_persona_manifest_in_the_source_tree(self):
        for owners in board.KIND_OWNERS.values():
            for owner in owners:
                self.assertTrue((ROOT / "design" / "agents" / f"{owner}.toml").exists(), owner)


class Briefs(FixtureBox):  # (::board-brief-hashing)
    def test_the_hash_ignores_line_endings_and_trailing_whitespace_only(self):
        base = board.text_hash("# Brief\n\nline one\nline two")
        self.assertEqual(board.text_hash("# Brief\r\n\r\nline one\r\nline two\r\n\r\n  "), base)
        self.assertNotEqual(board.text_hash("# Brief\n\nline one\nline  two"), base)

    def test_a_brief_is_stored_under_its_hash_and_recorded_with_it(self):
        self.assertEqual(self.create()[0], 0)
        digest = self.write_brief(text="body\r\n")
        stored = self.tmp / "board/cards/alpha-card/briefs" / f"{digest}.md"
        self.assertEqual((digest, stored.read_text()), (board.text_hash("body"), "body\n"))
        self.assertEqual(self.column(), "Refine")

    def test_a_brief_whose_hash_was_returned_is_refused_and_an_unchanged_one_too(self):
        self.assertEqual(self.create()[0], 0)
        digest = self.write_brief()
        self.assertEqual(self.cli("brief", "alpha-card", "--from-file", self.file("b.md", "first brief"), "--actor", "dave")[0], 1)
        self.decide("brief_returned", brief_hash=digest, reason="again")
        code, _, err = self.cli("brief", "alpha-card", "--from-file", self.file("b.md", "first brief"), "--actor", "dave")
        self.assertEqual(code, 1)
        self.assertIn("already returned", err)
        self.assertEqual(self.write_brief(text="a new one"), board.text_hash("a new one"))

    def test_a_run_writes_a_brief_once_per_run_and_only_into_backlog(self):
        self.assertEqual(self.create()[0], 0)
        first = self.write_brief(actor="run:b1")
        self.assertEqual(self.write_brief(text="a different file", actor="run:b1"), first)
        code, _, err = self.cli("brief", "alpha-card", "--from-file", self.file("c.md", "later"), "--actor", "run:b2")
        self.assertEqual(code, 1, err)

    def test_who_may_brief_which_column(self):
        self.assertEqual(self.create()[0], 0)
        self.write_brief(actor="buzz:claudius")
        self.assertEqual(self.cli("brief", "alpha-card", "--from-file", self.file("c.md", "dave edit"), "--actor", "dave")[0], 0)
        self.decide("brief_approved", brief_hash=board.text_hash("dave edit"))
        self.assertEqual(self.column(), "Todo")
        for actor, code in (("buzz:claudius", 1), ("run:b9", 1), ("mac:claude", 0)):
            with self.subTest(actor):
                self.assertEqual(self.cli("brief", "alpha-card", "--from-file", self.file("d.md", f"by {actor}"), "--actor", actor)[0], code)


class Edits(FixtureBox):  # (::board-edit-rules)
    def rev(self, card_id: str = "alpha-card") -> str:
        return str(json.loads(self.cli("status", card_id, "--json")[1])["rev"])

    def edit(self, *argv: str, actor: str = "dave", rev: str | None = None):
        return self.cli("edit", "alpha-card", "--expect-rev", rev or self.rev(), "--actor", actor, *argv)

    def test_only_dave_and_the_mac_may_edit(self):
        self.assertEqual(self.create()[0], 0)
        for actor, code in (("dave", 0), ("mac:claude", 0), ("run:r1", 1), ("buzz:claudius", 1)):
            with self.subTest(actor):
                self.assertEqual(self.edit("--title", f"by {actor}", actor=actor)[0], code)

    def test_id_owner_and_kind_are_refused(self):
        self.assertEqual(self.create()[0], 0)
        for flag, value in (("--id", "other"), ("--owner", "marcus"), ("--kind", "dev")):
            with self.subTest(flag):
                code, _, err = self.edit(flag, value)
                self.assertEqual(code, 1)
                self.assertIn("cannot be edited", err)

    def test_a_stale_revision_and_a_no_op_are_refused(self):
        self.assertEqual(self.create()[0], 0)
        stale = self.rev()
        self.assertEqual(self.edit("--title", "New")[0], 0)
        code, _, err = self.edit("--title", "Newer", rev=stale)
        self.assertEqual(code, 1)
        self.assertIn("stale", err)
        self.assertEqual(self.edit("--title", "New")[0], 1)

    def test_an_edit_records_the_old_value(self):
        self.assertEqual(self.create()[0], 0)
        self.edit("--title", "Renamed", "--priority", "high")
        last = json.loads((self.tmp / "board/cards/alpha-card/events.jsonl").read_text().splitlines()[-1])
        self.assertEqual(last["fields"]["title"], {"old": "Title of alpha-card", "new": "Renamed"})
        self.assertEqual(last["fields"]["priority"]["new"], "high")

    def test_a_new_idea_voids_a_brief_and_a_new_scope_too(self):
        for flag, value in (("--idea", "A different idea"), ("--scope", "vault:04_operations")):
            with self.subTest(flag):
                self.approved_card("card-" + flag[2:])
                code, _, err = self.cli("edit", "card-" + flag[2:], "--expect-rev", "2", "--actor", "dave", flag, value)
                self.assertEqual((code, self.column("card-" + flag[2:])), (0, "Backlog"), err)

    def test_the_research_date_must_not_follow_the_deadline_in_either_order(self):
        self.assertEqual(self.create("alpha-card", "--deadline", "2026-12-01")[0], 0)
        self.assertEqual(self.edit("--research-on", "2026-12-02")[0], 1)
        self.assertEqual(self.edit("--research-on", "2026-11-20")[0], 0)
        self.assertEqual(self.edit("--deadline", "2026-11-01")[0], 1)
        self.assertEqual(self.edit("--research-on", "none")[0], 0)

    def test_the_research_date_holds_the_pick_back(self):
        self.approved_card("alpha-card", "--research-on", "2999-01-01")
        view = json.loads(self.cli("status", "alpha-card", "--json")[1])
        self.assertEqual((view["column"], view["scheduled"]), ("Todo", True))
        self.assertEqual(self.cli("next", "--column", "todo", "--owner", "claudius")[1], "")

    def test_a_running_card_takes_only_labels_and_an_edit_never_lifts_a_block(self):
        self.approved_card()
        self.cli("pick", "--owner", "claudius", "--run-id", "r1", "--workflow", "agent-proposal")
        self.assertEqual(self.column(), "In Progress")
        self.assertEqual(self.edit("--research-on", "2026-12-01")[0], 1)
        self.assertEqual(self.edit("--tags", "a,b")[0], 0)
        self.receipt("r1", "failed")
        self.decide("blocked")
        self.assertEqual(self.edit("--deadline", "2999-01-01")[0], 0)
        self.assertEqual(self.column(), "Blocked")

    def test_idea_is_closed_after_the_first_research_run(self):
        self.approved_card()
        self.cli("pick", "--owner", "claudius", "--run-id", "r1", "--workflow", "agent-proposal")
        self.receipt("r1", "decline")
        self.assertEqual(self.column(), "Todo")
        self.assertEqual(self.edit("--idea", "Another idea")[0], 1)


class ActorVerbs(FixtureBox):  # (::board-actor-verbs)
    def test_the_actor_vocabulary_is_closed(self):
        self.assertEqual(self.create()[0], 0)
        for actor in ("claude", "run:", "buzz:", "root", "dave "):
            with self.subTest(actor):
                code, _, err = self.cli("note", "alpha-card", "--from-file", self.file("n.md", "n"), "--actor", actor)
                self.assertEqual(code, 1, err)

    def test_notes_are_open_to_every_actor_and_appended_in_any_column(self):
        self.assertEqual(self.create()[0], 0)
        for actor in ("dave", "mac:claude", "run:r1", "buzz:claudius"):
            with self.subTest(actor):
                self.assertEqual(self.cli("note", "alpha-card", "--from-file", self.file("n.md", f"by {actor}"), "--actor", actor)[0], 0)
        events = [json.loads(e) for e in (self.tmp / "board/cards/alpha-card/events.jsonl").read_text().splitlines()]
        self.assertEqual([e["event"] for e in events], ["created"] + ["note"] * 4)

    def test_pick_is_a_run_verb_and_no_ledger_verb_writes_a_decision(self):
        parser = board.build_parser()
        verbs = parser._subparsers._group_actions[0].choices
        self.assertFalse({"approve", "decide", "return", "block", "unblock", "reject"} & set(verbs))
        for event in board.EVENTS:
            self.assertNotIn(event, board.DECISIONS)
        with self.assertRaises(board.BoardError):
            board.append_event(self.tmp, "brief_approved", "dave")


class Picking(FixtureBox):  # (::board-pick)
    PICK = ("pick", "--owner", "claudius", "--workflow", "agent-proposal")

    def pick(self, run_id: str, *extra: str):
        return self.cli(*self.PICK, "--run-id", run_id, *extra)

    def test_the_top_card_is_the_highest_priority_then_the_earliest_deadline(self):
        self.approved_card("low-card", "--priority", "low")
        self.approved_card("late-card", "--deadline", "2999-06-01")
        self.approved_card("early-card", "--deadline", "2999-01-01")
        self.approved_card("high-card", "--priority", "high")
        order = []
        for run in ("r1", "r2", "r3", "r4"):
            order.append(self.pick(run)[1].strip())
        self.assertEqual(order, ["high-card", "early-card", "late-card", "low-card"])
        self.assertEqual(self.pick("r5")[1], "")

    def test_pick_is_idempotent_per_run_id_and_writes_the_run_card(self):
        self.approved_card()
        first = self.pick("r1")[1]
        self.assertEqual(self.pick("r1")[1], first)
        events = (self.tmp / "board/cards/alpha-card/events.jsonl").read_text().splitlines()
        self.assertEqual(len([e for e in events if '"picked"' in e]), 1)
        text = (self.tmp / "board/runs/r1/card.md").read_text()
        self.assertIn("## Approved brief", text)
        self.assertIn("first brief", text)
        self.assertIn("A synthetic idea", text)

    def test_a_pick_passes_over_a_card_that_is_not_in_todo_or_is_scheduled(self):
        self.assertEqual(self.create("backlog-card")[0], 0)
        self.assertEqual(self.create("refine-card", "--brief", self.file("b.md", "x"))[0], 0)
        self.approved_card("later-card", "--research-on", "2999-01-01")
        self.assertEqual(self.pick("r1")[1], "")

    def test_a_pick_refuses_a_brief_text_that_no_longer_hashes_to_its_approval(self):
        digest = self.approved_card()
        (self.tmp / f"board/cards/alpha-card/briefs/{digest}.md").write_text("tampered\n")
        code, out, err = self.pick("r1")
        self.assertEqual((code, out), (0, ""))
        self.assertIn("pick-hash-mismatch", err)

    def test_a_voided_pick_returns_the_card_to_the_next_run(self):
        self.approved_card()
        self.pick("r1")
        self.receipt("r1", "skipped")
        self.assertEqual(self.pick("r2")[1].strip(), "alpha-card")

    def test_a_request_for_changes_reaches_the_next_run_card(self):
        self.approved_card()
        self.pick("r1")
        self.receipt("r1", "artifact", page="page-1")
        self.assertEqual(self.column(), "In Review")
        self.decide("changes_requested", reason="cite the second source")
        self.assertEqual(self.column(), "Todo")
        self.pick("r2")
        self.assertIn("cite the second source", (self.tmp / "board/runs/r2/card.md").read_text())

    def test_the_brief_run_picks_from_backlog_and_reads_the_returned_reasons(self):
        self.assertEqual(self.create()[0], 0)
        digest = self.write_brief()
        self.decide("brief_returned", brief_hash=digest, reason="keep it local")
        code, out, err = self.pick("b1", "--column", "backlog")
        self.assertEqual((code, out.strip()), (0, "alpha-card"), err)
        self.assertIn("keep it local", (self.tmp / "board/runs/b1/card.md").read_text())
        self.assertEqual(self.column(), "Backlog")

    def test_a_pick_is_refused_to_anyone_who_is_not_a_run(self):
        self.assertEqual(self.cli(*self.PICK, "--run-id", "bad id!")[0], 1)


class Reads(FixtureBox):  # (::board-reads-and-main)
    def test_list_next_status_show_and_decisions(self):
        self.approved_card("alpha-card")
        self.assertEqual(self.create("beta-card")[0], 0)
        self.assertEqual(self.cli("next", "--column", "backlog", "--owner", "claudius")[1].strip(), "beta-card")
        listing = self.cli("list", "--column", "todo")[1]
        self.assertEqual(listing.split("\t")[:2], ["alpha-card", "Todo"])
        shown = self.cli("show", "alpha-card")[1]
        self.assertIn("column: Todo", shown)
        self.assertIn("first brief", shown)
        self.assertEqual(len(self.cli("decisions")[1].strip().splitlines()), 1)

    def test_a_decision_shaped_event_in_the_ledger_file_is_reported_not_obeyed(self):
        self.assertEqual(self.create()[0], 0)
        self.write_brief()
        with open(self.tmp / "board/cards/alpha-card/events.jsonl", "a", encoding="utf-8") as handle:
            handle.write(json.dumps(ev("brief_approved", at(3))) + "\n")
        view = json.loads(self.cli("status", "alpha-card", "--json")[1])
        self.assertEqual((view["column"], view["exceptions"][0]["kind"]), ("Refine", "forged-decision"))

    def test_done_is_a_join_with_origin_main_and_unapplied_lists_the_rest(self):
        digest = self.approved_card()
        self.pick = lambda run: self.cli("pick", "--owner", "claudius", "--run-id", run, "--workflow", "agent-proposal")
        self.pick("r1")
        self.receipt("r1", "artifact", page="page-1")
        self.decide("approved", page_hash=PAGE)
        self.assertEqual(self.column(), "In Review")
        self.assertEqual(len(self.cli("decisions", "--unapplied")[1].strip().splitlines()), 1)
        self.build_clone(note_hash=PAGE)
        self.assertEqual(self.column(), "Done")
        self.assertEqual(self.cli("decisions", "--unapplied")[1].strip(), "")
        self.assertTrue(digest)

    def test_a_note_on_main_with_another_hash_is_not_done(self):
        self.approved_card()
        self.cli("pick", "--owner", "claudius", "--run-id", "r1", "--workflow", "agent-proposal")
        self.receipt("r1", "artifact", page="page-1")
        self.decide("approved", page_hash=PAGE)
        self.build_clone(note_hash="e" * 64)
        self.assertEqual(self.column(), "In Review")

    def test_load_main_reads_only_origin_main_and_only_a_matching_front_matter_line(self):
        self.build_clone(note_hash=PAGE)
        clone = self.tmp / "clone"
        self.assertEqual(board.load_main(clone, ["alpha-card", "absent-card"]), {"alpha-card": PAGE})
        self.assertEqual(board.load_main(self.tmp / "nowhere", ["alpha-card"]), {})

    def build_clone(self, note_hash: str) -> None:
        clone = self.tmp / "clone"
        clone.mkdir(exist_ok=True)
        notes = clone / board.RESEARCH_NOTE_DIR
        notes.mkdir(parents=True, exist_ok=True)
        (notes / "alpha-card.md").write_text(f"---\ntype: research\ncard: alpha-card\ncontent: {note_hash}\n---\nbody\n")
        git = ["git", "-C", str(clone), "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run([*git, "init", "-q", "-b", "main"], check=True)
        subprocess.run([*git, "add", "-A"], check=True)
        subprocess.run([*git, "commit", "-q", "-m", "note"], check=True)
        subprocess.run([*git, "update-ref", "refs/remotes/origin/main", "HEAD"], check=True)


class Template(FixtureBox):  # (::board-template)
    def filled(self, card_id: str = "alpha-card") -> str:
        text = self.cli("template", "--kind", "research")[1].replace("<card id>", card_id)
        return text.replace("- Three to five checkable statements, one per line, each answerable from the artifact alone.",
                            "- First statement.\n- Second statement.\n- Third statement.")

    def validate(self, text: str, card_id: str = "alpha-card") -> tuple[int, str]:
        code, out, _ = self.cli("validate-brief", self.file("t.md", text), "--card", card_id)
        return code, out

    def test_the_filled_template_passes_every_heading_check(self):
        self.assertEqual(self.validate(self.filled()), (0, "ok\n"))

    def test_every_template_heading_is_a_heading_validate_brief_requires(self):
        template = self.cli("template", "--kind", "research")[1]
        for heading in board.BRIEF_HEADINGS:
            with self.subTest(heading):
                self.assertIn(f"## {heading}\n", template)
                code, out = self.validate(self.filled().replace(f"## {heading}\n", ""))
                self.assertEqual(code, 1)
                self.assertIn(f"missing heading: ## {heading}", out)

    def test_acceptance_must_have_three_to_five_lines(self):
        for count, ok in ((2, False), (3, True), (5, True), (6, False)):
            with self.subTest(count=count):
                lines = "\n".join(f"- statement {i}" for i in range(count))
                text = self.filled().replace("- First statement.\n- Second statement.\n- Third statement.", lines)
                code, out = self.validate(text)
                self.assertEqual(code == 0, ok)
                if not ok:
                    self.assertIn(f"acceptance has {count} lines", out)

    def test_the_brief_must_name_its_card_and_no_template_for_other_kinds(self):
        code, out = self.validate(self.filled("beta-card"))
        self.assertEqual(code, 1)
        self.assertIn("# Brief: alpha-card", out)
        self.assertEqual(self.cli("template", "--kind", "dev")[0], 1)


class Help(FixtureBox):  # (::board-help)
    def test_help_is_the_mechanism_document(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            board.main(["--help"])
        text = out.getvalue()
        for needle in ("cards/<id>/events.jsonl", "runs/<run_id>/card.md", "ACTORS", "DECISIONS are not ledger events",
                       "HASHING", "board.py template --kind research", *board.COLUMNS, *board.DECISIONS):
            with self.subTest(needle):
                self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
