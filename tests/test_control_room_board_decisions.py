#!/usr/bin/env python3
"""The board seam's decision verbs (Dev Plan B9): POST /api/v1/control/board -> the broker.

The seam is driven over loopback HTTP; the broker is the real bin/control_broker.py handler called
in process with a temp ssh-keygen key, so a click is followed all the way to a signed line that
board.py derives from. Synthetic cards only."""

from __future__ import annotations

import contextlib
import dataclasses
import datetime as dt
import io
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))
sys.path.insert(0, str(ROOT / "tests"))

import board  # noqa: E402
import board_decision_sig as sig  # noqa: E402
import control_broker as broker  # noqa: E402
import control_room_board_writes as writes  # noqa: E402
import control_room_control as control  # noqa: E402
import test_control_room_board_writes as base  # noqa: E402
import workflow_receipt as wr  # noqa: E402

PAGE = "Findings.\n\n- Alpha holds.\n\n## Acceptance\n\nA: MET\n"
PAGE_HASH = board.text_hash(PAGE)
BRIEF = "# Brief: alpha-question\n\n## Question\n\nDoes the synthetic\nthing hold?\n"


class InProcessBroker:
    """Calls the real broker handler; `calls` keeps what the seam sent."""

    def __init__(self, cfg: broker.Config) -> None:
        self.cfg, self.calls = cfg, []
        self.clock = dt.datetime.now(dt.timezone.utc) + dt.timedelta(hours=1)

    def call(self, request: dict) -> dict:
        self.calls.append(request)
        self.clock += dt.timedelta(minutes=1)
        return broker.handle_board(request, dataclasses.replace(self.cfg, now=self.clock), actor={"kind": "screen", "remote": "100.64.0.1", "local": "100.64.0.9",
                                                             "label": "screen", "user": None, "peer": None})


class Down:
    def call(self, request: dict) -> dict:
        raise control.BrokerUnavailable("no socket")


class Saying:
    def __init__(self, response: dict) -> None:
        self.response, self.calls = response, []

    def call(self, request: dict) -> dict:
        self.calls.append(request)
        return self.response


class DecisionSeam(unittest.TestCase):
    def setUp(self):
        self.http = base.BoardSeamTest("test_header_and_shape_are_checked")
        self.http.setUp()
        self.addCleanup(self.http.tearDown)
        self.tmp, self.server, self.post, self.create = self.http.tmp, self.http.server, self.http.post, self.http.create
        base_dir = pathlib.Path(self.tmp.name)
        key = base_dir / "key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key)], check=True)
        self.signers = base_dir / "signers"
        self.signers.write_text(sig.allowed_signers_line(key.with_suffix(".pub").read_text()))
        allow = base_dir / "allowlist.json"
        allow.write_text(json.dumps({"schema": 1, "workflows": {}, "excluded": [], "board": {"verbs": list(board.DECISIONS)}}))
        stream = base_dir / "decisions"
        stream.mkdir(exist_ok=True)
        cfg = broker.Config(allowlist=allow, receipts=base_dir / "r", peer_uids=frozenset({0}), user_manager="x",
                            system_stamp_dir=base_dir, user_stamp_dir=base_dir, lock=base_dir / "lock",
                            board_dir=stream, board_key=key)
        self.broker = InProcessBroker(cfg)
        self.page = {"text": PAGE, "page_hash": PAGE_HASH, "published_hash": PAGE_HASH, "url": "https://notion.invalid/p"}
        self.seam = self.server.RequestHandlerClass.board
        self.seam.broker, self.seam.export = self.broker, lambda card: self.page
        self.stream = stream / "decisions.jsonl"

    def view(self):
        return board.view_of(pathlib.Path(self.tmp.name) / "board", "alpha-question")

    def decide(self, verb, **fields):
        return self.post({"verb": verb, "card": "alpha-question", **fields})

    def refine(self):
        self.create(brief=BRIEF)
        return self.view()["brief_hash"]

    def todo(self):
        self.assertEqual(self.decide("approve_brief", brief_hash=self.refine())[0], 200)

    def in_review(self):
        self.todo()
        with contextlib.redirect_stdout(io.StringIO()):
            code = board.main(["pick", "--owner", "claudius", "--run-id", "r1", "--workflow", "agent-proposal"])
        self.assertEqual(code, 0)
        data = {"schema_version": wr.SCHEMA_VERSION, "workflow_id": "agent-proposal", "run_id": "r1",
                "started_at": "2026-10-06T04:30:00Z", "ended_at": "2026-10-06T04:40:00Z",
                "terminal": {"outcome": "artifact", "reason": "fixture"}, "assertions": [],
                "usage": wr.unavailable_usage(), "cost": wr.unavailable_cost(),
                "artifact": {"uri": "board://alpha-question/page"},
                "card": {"id": "alpha-question", "workflow": "agent-proposal", "page": "p1", "page_hash": PAGE_HASH}}
        wr.write(data, pathlib.Path(self.tmp.name) / "receipts")
        self.assertEqual(self.view()["column"], "In Review")

    def records(self):
        return [json.loads(l) for l in self.stream.read_text().splitlines()] if self.stream.exists() else []

    def signed_since(self, before):
        return self.records()[before:]


class Moves(DecisionSeam):  # (::board-seam-moves)
    def test_the_popup_verbs_map_one_to_one_onto_the_brokers_decisions(self):
        self.assertEqual(sorted(writes.DECISION_MAP.values()), sorted(board.DECISIONS))
        self.assertEqual(set(writes.DECISION_MAP), set(writes.DECISION_VERBS))
        self.assertEqual((writes.DECISION_MAP["delete"], writes.DECISION_MAP["restore"]), ("deleted", "restored"))
        self.assertNotIn("withdraw", writes.DECISION_MAP)

    def test_every_move_the_board_offers_is_a_verb_the_seam_takes(self):
        offered = {move for moves in board.MOVES.values() for move in moves}
        self.assertEqual(set(writes.DECISION_VERBS) - offered, {"restore"})
        self.assertLessEqual(offered, set(writes.DECISION_VERBS))

    def test_a_move_the_column_does_not_offer_is_refused_and_the_broker_not_called(self):
        self.create()
        for verb in ("approve", "unblock", "block", "reject"):
            status, body = self.decide(verb, reason="r")
            self.assertEqual(status, 409, (verb, body))
            self.assertIn("not offered", body["error"])
        self.assertEqual(self.broker.calls, [])

    def test_an_unknown_verb_or_a_bad_card_is_400(self):
        self.create()
        self.assertEqual(self.post({"verb": "decide", "card": "alpha-question"})[0], 400)
        self.assertEqual(self.post({"verb": "approve", "card": "../x"})[0], 400)
        self.assertEqual(self.post({"verb": "approve", "card": "ghost"})[0], 404)

    def test_reasons_are_required_where_the_broker_requires_them(self):
        digest = self.refine()
        for verb in ("return_brief",):
            self.assertEqual(self.decide(verb, brief_hash=digest)[0], 400)
            self.assertEqual(self.decide(verb, brief_hash=digest, reason="  ")[0], 400)
        self.assertEqual(self.broker.calls, [])


class Flow(DecisionSeam):  # (::board-seam-decisions)
    def test_approving_a_brief_moves_refine_to_todo_through_a_signed_line(self):
        digest = self.refine()
        self.assertEqual(self.view()["column"], "Refine")
        status, body = self.decide("approve_brief", brief_hash=digest)
        self.assertEqual(status, 200, body)
        self.assertEqual((body["view"]["column"], body["card"]), ("Todo", "alpha-question"))
        record = self.records()[0]
        self.assertEqual((record["decision"], record["brief_hash"], record["remote"]), ("brief_approved", digest, "100.64.0.1"))
        self.assertEqual(sig.verify_stream(self.stream, self.signers), [])

    def test_returning_a_brief_carries_the_reason_and_goes_back_to_backlog(self):
        digest = self.refine()
        status, body = self.decide("return_brief", brief_hash=digest, reason="keep it local")
        self.assertEqual(status, 200, body)
        self.assertEqual((body["view"]["column"], self.records()[0]["reason"]), ("Backlog", "keep it local"))

    def test_block_and_unblock_round_trip(self):
        self.todo()
        self.assertEqual(self.decide("block", reason="waiting")[0], 200)
        self.assertEqual(self.view()["column"], "Blocked")
        self.assertEqual(self.decide("unblock")[0], 200)
        self.assertEqual(self.view()["column"], "Todo")

    def test_withdraw_is_gone_from_the_screen(self):
        self.todo()
        self.assertEqual(self.decide("withdraw", reason="not wanted")[0], 400)
        self.assertEqual(self.broker.calls[1:], [])

    def test_approve_in_review_hands_the_text_to_the_broker_and_waits_for_main(self):
        self.in_review()
        status, body = self.decide("approve", page_hash=PAGE_HASH)
        self.assertEqual(status, 200, body)
        record = self.records()[-1]
        self.assertEqual((record["decision"], record["page_hash"], record["text"]), ("approved", PAGE_HASH, PAGE))
        self.assertEqual((self.view()["column"], self.view()["approved_landing"]), ("In Review", True))
        self.assertEqual(sig.verify_stream(self.stream, self.signers), [])

    def test_request_changes_returns_the_card_to_todo_and_reject_closes_it(self):
        self.in_review()
        self.assertEqual(self.decide("request_changes", reason="answer line two")[0], 200)
        self.assertEqual(self.view()["column"], "Todo")

    def test_reject_in_review_is_done_rejected(self):
        self.in_review()
        self.assertEqual(self.decide("reject", reason="no note")[0], 200)
        self.assertEqual((self.view()["column"], self.view()["outcome"]), ("Done", "rejected"))


class Delete(DecisionSeam):  # (::board-seam-delete)
    def test_delete_takes_no_reason_signs_deleted_and_the_card_leaves_the_board(self):
        self.todo()
        status, body = self.decide("delete", reason="ignored", expect_rev=self.view()["rev"])
        self.assertEqual(status, 200, body)
        self.assertEqual((body["card"], body["view"]), ("alpha-question", None))
        record = self.records()[-1]
        self.assertEqual(record["decision"], "deleted")
        self.assertNotIn("reason", record)
        self.assertEqual({k for k in self.broker.calls[-1]}, {"v", "board_verb", "card", "actor"})
        self.assertNotIn("alpha-question", board.collect(pathlib.Path(self.tmp.name) / "board"))
        self.assertEqual(sig.verify_stream(self.stream, self.signers), [])

    def test_delete_is_offered_everywhere_but_in_review(self):
        self.in_review()
        status, body = self.decide("delete")
        self.assertEqual(status, 409, body)
        self.assertIn("not offered", body["error"])

    def test_a_stale_revision_refuses_the_delete(self):
        self.todo()
        status, _ = self.decide("delete", expect_rev=self.view()["rev"] - 1)
        self.assertEqual(status, 409)
        self.assertEqual(self.records()[1:], [])

    def test_restore_brings_a_deleted_card_back_before_and_after_the_trash(self):
        self.todo()
        self.decide("delete")
        status, body = self.decide("restore")
        self.assertEqual(status, 200, body)
        self.assertEqual(self.records()[-1]["decision"], "restored")
        self.assertEqual(body["view"]["column"], "Todo")
        self.decide("delete")
        self.assertTrue(board.trash_card(pathlib.Path(self.tmp.name) / "board", "alpha-question"))
        status, body = self.decide("restore")
        self.assertEqual(status, 200, body)
        self.assertEqual(self.records()[-1]["decision"], "restored")

    def test_restore_needs_a_deleted_card(self):
        self.todo()
        before = len(self.records())
        status, body = self.decide("restore")
        self.assertEqual(status, 409, body)
        self.assertIn("not deleted", body["error"])
        self.assertEqual(self.post({"verb": "restore", "card": "ghost"})[0], 404)
        self.assertEqual(self.signed_since(before), [])


class Stale(DecisionSeam):  # (::board-seam-stale)
    def test_a_brief_hash_that_is_not_the_current_one_is_refused(self):
        digest = self.refine()
        status, body = self.decide("approve_brief", brief_hash="0" * 64)
        self.assertEqual(status, 409, body)
        self.assertIn("stale", body["error"])
        self.assertEqual(body["view"]["brief_hash"], digest)
        self.assertEqual((self.broker.calls, self.records()), ([], []))

    def test_a_missing_hash_is_a_400(self):
        self.refine()
        self.assertEqual(self.decide("approve_brief")[0], 400)
        self.assertEqual(self.decide("return_brief", reason="r")[0], 400)

    def test_a_page_edited_since_the_popup_rendered_it_is_refused_and_nothing_is_signed(self):
        self.in_review()
        before = len(self.records())
        self.page = {**self.page, "text": PAGE + "\nEdited in Notion.\n"}
        status, body = self.decide("approve", page_hash=PAGE_HASH)
        self.assertEqual(status, 409, body)
        self.assertIn("stale", body["error"])
        self.assertEqual(self.signed_since(before), [])

    def test_approve_without_a_page_hash_or_an_exportable_page_is_refused(self):
        self.in_review()
        before = len(self.records())
        self.assertEqual(self.decide("approve")[0], 400)
        self.seam.export = lambda card: None
        self.assertEqual(self.decide("approve", page_hash=PAGE_HASH)[0], 409)
        self.assertEqual(self.signed_since(before), [])

    def test_a_stale_card_revision_is_refused(self):
        self.todo()
        status, body = self.decide("block", reason="r", expect_rev=self.view()["rev"] - 1)
        self.assertEqual(status, 409, body)
        self.assertEqual(self.records()[1:], [])


class BrokerFailures(DecisionSeam):  # (::board-seam-broker)
    def test_an_unreachable_broker_is_503_and_the_card_does_not_move(self):
        self.todo()
        self.seam.broker = Down()
        status, body = self.decide("block", reason="r")
        self.assertEqual(status, 503, body)
        self.assertIn("broker_unavailable", body["error"])
        self.assertEqual(self.view()["column"], "Todo")

    def test_no_broker_bound_is_503(self):
        self.todo()
        self.seam.broker = None
        self.assertEqual(self.decide("block", reason="r")[0], 503)

    def test_the_brokers_refusals_map_onto_http(self):
        self.todo()
        for code, status in (("not_allowlisted", 403), ("peer_denied", 403), ("hash_mismatch", 409),
                             ("reason_required", 400), ("bad_request", 400)):
            self.seam.broker = Saying({"result": "refused", "refusal": {"code": code, "message": f"m {code}"}})
            got, body = self.decide("block", reason="r")
            self.assertEqual((got, body["ok"]), (status, False), code)
            self.assertIn(code, body["error"])

    def test_a_failed_signing_is_502(self):
        self.todo()
        self.seam.broker = Saying({"result": "failed", "note": "signing failed: no key"})
        status, body = self.decide("block", reason="r")
        self.assertEqual(status, 502, body)
        self.assertIn("signing failed", body["error"])

    def test_the_seam_stamps_the_actor_from_the_connection_and_never_the_body(self):
        self.todo()
        self.decide("block", reason="r", actor={"remote": "10.0.0.1"})
        sent = self.broker.calls[-1]
        self.assertEqual(sent["actor"]["remote"], "127.0.0.1")
        self.assertEqual({k for k in sent} - {"v", "board_verb", "card", "reason", "actor"}, set())


if __name__ == "__main__":
    unittest.main()
