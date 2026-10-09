#!/usr/bin/env python3
"""The board write seam (B5): POST /api/v1/control/board over bin/control_room_board_writes.py.
Synthetic cards, temp roots, a loopback server."""

from __future__ import annotations

import importlib.util
import json
import os
import pathlib
import shutil
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("control_room_api", ROOT / "bin" / "control_room_api.py")
assert SPEC and SPEC.loader
api = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(api)
import board  # noqa: E402
import control_room_board_writes  # noqa: E402


class BoardSeamTest(unittest.TestCase):
    ENV = ("BOARD_ROOT", "CONTROL_ROOM_BOARD_ROOT", "BOARD_DECISIONS_ROOT", "CONTROL_ROOM_RECEIPT_ROOT")

    def setUp(self):
        import os
        self.tmp = tempfile.TemporaryDirectory()
        base = pathlib.Path(self.tmp.name)
        self.saved = {k: os.environ.pop(k, None) for k in self.ENV}
        self.saved_clone = os.environ.get("BOARD_CANONICAL_CLONE")
        os.environ["BOARD_ROOT"] = str(base / "board")
        os.environ["BOARD_DECISIONS_ROOT"] = str(base / "decisions")
        os.environ["CONTROL_ROOM_RECEIPT_ROOT"] = str(base / "receipts")
        os.environ["BOARD_CANONICAL_CLONE"] = str(base / "no-clone")
        (base / "board").mkdir()
        self.server = api.make_server("127.0.0.1", 0, api.ControlRoomReadModel(
            api.SourcePaths(base, base, base / "none")))
        self.server.RequestHandlerClass.board = control_room_board_writes.BoardControl.from_env()
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.base = f"http://127.0.0.1:{self.server.server_port}/api/v1/control/board"

    def tearDown(self):
        import os
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=3)
        for key, value in {**self.saved, "BOARD_CANONICAL_CLONE": self.saved_clone}.items():
            os.environ.pop(key, None)
            if value is not None:
                os.environ[key] = value
        self.tmp.cleanup()

    def post(self, body, header=True):
        headers = {"Content-Type": "application/json"}
        if header:
            headers["X-Control-Room"] = "1"
        request = urllib.request.Request(self.base, data=json.dumps(body).encode(), headers=headers, method="POST")
        try:
            with urllib.request.urlopen(request, timeout=3) as response:
                return response.status, json.load(response)
        except urllib.error.HTTPError as err:
            with err:
                return err.code, json.load(err)

    def create(self, **extra):
        body = {"verb": "create", "title": "Alpha question", "idea": "Does the synthetic thing hold?",
                "owner": "claudius", "scope": ["vault:05_knowledge"], **extra}
        return self.post(body)

    def test_verb_table_admits_four_and_stubs_decisions(self):
        self.assertEqual(control_room_board_writes.WRITE_VERBS, ("create", "brief", "note", "edit"))
        for verb in ("approve", "pick", "land", "delete"):
            status, body = self.post({"verb": verb, "card": "alpha-question"})
            self.assertIn(status, (400, 501), verb)
            self.assertFalse(body.get("ok"), verb)
        self.assertEqual(self.post({"verb": "approve_brief", "card": "alpha-question"})[0], 501)
        self.assertEqual(self.post({"verb": "pick"})[0], 400)

    def test_header_and_shape_are_checked(self):
        self.assertEqual(self.post({"verb": "create"}, header=False)[0], 400)
        self.assertEqual(self.post({"title": "x"})[0], 400)

    def test_create_acts_as_dave_and_returns_the_view(self):
        status, body = self.create(brief="# Question\nq\n", priority="high", tags=["a", "b"])
        self.assertEqual(status, 200, body)
        self.assertEqual(body["card"], "alpha-question")
        self.assertEqual(body["view"]["fields"]["priority"], "high")
        events = (pathlib.Path(self.tmp.name) / "board/cards/alpha-question/events.jsonl").read_text()
        self.assertEqual({json.loads(l)["actor"] for l in events.splitlines()}, {"dave"})
        self.assertEqual(self.create()[0], 422)

    def test_actor_in_the_body_is_ignored(self):
        status, body = self.create(actor="run:x")
        self.assertEqual(status, 200, body)
        events = (pathlib.Path(self.tmp.name) / "board/cards/alpha-question/events.jsonl").read_text()
        self.assertEqual(json.loads(events.splitlines()[0])["actor"], "dave")

    def test_brief_and_note_append_and_unchanged_brief_is_refused(self):
        self.create()
        status, body = self.post({"verb": "brief", "card": "alpha-question", "text": "# Question\nfirst\n"})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["view"]["brief_version"], 1)
        status, body = self.post({"verb": "brief", "card": "alpha-question", "text": "# Question\nfirst\n"})
        self.assertEqual((status, "unchanged" in body["error"]), (422, True))
        status, body = self.post({"verb": "note", "card": "alpha-question", "text": "keep it local"})
        self.assertEqual(status, 200, body)
        self.assertEqual(self.post({"verb": "note", "card": "alpha-question", "text": "  "})[0], 400)

    def test_edit_applies_and_stale_revision_is_refused(self):
        _, created = self.create()
        rev = created["view"]["rev"]
        status, body = self.post({"verb": "edit", "card": "alpha-question", "expect_rev": rev,
                                  "fields": {"priority": "low", "tags": ["x"]}})
        self.assertEqual(status, 200, body)
        self.assertEqual(body["view"]["fields"]["priority"], "low")
        self.assertEqual(body["view"]["rev"], rev + 1)
        status, body = self.post({"verb": "edit", "card": "alpha-question", "expect_rev": rev,
                                  "fields": {"priority": "high"}})
        self.assertEqual(status, 409, body)
        self.assertIn("stale", body["error"])
        self.assertEqual(body["view"]["fields"]["priority"], "low")

    def test_stale_brief_save_is_refused(self):
        _, created = self.create()
        self.post({"verb": "brief", "card": "alpha-question", "text": "# Question\nv1\n"})
        status, body = self.post({"verb": "brief", "card": "alpha-question", "text": "# Question\nv2\n",
                                  "expect_rev": created["view"]["rev"]})
        self.assertEqual(status, 409, body)

    def test_edit_refuses_locked_fields_and_bad_shapes(self):
        _, created = self.create()
        rev = created["view"]["rev"]
        for fields in ({"owner": "x"}, {"id": "y"}, {"kind": "dev"}, {"priority": "urgent"}, {}):
            status, _ = self.post({"verb": "edit", "card": "alpha-question", "expect_rev": rev, "fields": fields})
            self.assertIn(status, (400, 422), fields)
        self.assertEqual(self.post({"verb": "edit", "card": "alpha-question", "fields": {"title": "t"}})[0], 400)
        self.assertEqual(self.post({"verb": "edit", "card": "alpha-question", "expect_rev": "1", "fields": {"title": "t"}})[0], 400)

    def test_unknown_card_is_404_and_bad_id_is_400(self):
        self.assertEqual(self.post({"verb": "note", "card": "ghost", "text": "n"})[0], 404)
        self.assertEqual(self.post({"verb": "note", "card": "../x", "text": "n"})[0], 400)

    def test_unbound_seam_and_missing_root_are_503(self):
        self.server.RequestHandlerClass.board = None
        self.assertEqual(self.create()[0], 503)
        import os
        os.environ["BOARD_ROOT"] = str(pathlib.Path(self.tmp.name) / "absent")
        self.server.RequestHandlerClass.board = control_room_board_writes.BoardControl.from_env()
        status, body = self.create()
        self.assertEqual((status, body["error"].startswith("board_unavailable")), (503, True))

    def test_state_root_dropin_grants_the_board_root(self):
        text = (ROOT / "systemd" / "control-room.service.d" / "board.conf").read_text()
        self.assertIn("StateDirectory=control-room-board", text)
        self.assertIn("Environment=CONTROL_ROOM_BOARD_ROOT=/var/lib/control-room-board", text)

    def test_peer_rule(self):
        self.assertTrue(control_room_board_writes.peer_allowed("100.64.0.9", "100.64.0.2")[0])
        self.assertFalse(control_room_board_writes.peer_allowed("100.64.0.2", "100.64.0.2")[0])
        self.assertFalse(control_room_board_writes.peer_allowed("127.0.0.1", "100.64.0.2")[0])
        self.assertFalse(control_room_board_writes.peer_allowed(None, "100.64.0.2")[0])


class MissingCard(unittest.TestCase):
    def setUp(self):
        self.tmp = pathlib.Path(tempfile.mkdtemp(prefix="board-writes-"))
        self.saved = dict(os.environ)
        os.environ["BOARD_ROOT"] = str(self.tmp / "board")
        os.environ["BOARD_DECISIONS_ROOT"] = str(self.tmp / "decisions")
        os.environ["CONTROL_ROOM_RECEIPT_ROOT"] = str(self.tmp / "receipts")
        self.root = self.tmp / "board"
        self.root.mkdir()
        (self.tmp / "text.md").write_text("n")

    def tearDown(self):
        os.environ.clear()
        os.environ.update(self.saved)
        shutil.rmtree(self.tmp, ignore_errors=True)

    def test_writing_to_a_missing_card_is_a_refusal_not_a_crash(self):
        for call in (board.add_note, board.add_brief):
            with self.subTest(call.__name__), self.assertRaisesRegex(board.BoardError, "no such card"):
                call(self.root, "ghost", str(self.tmp / "text.md"), "dave")
        self.assertFalse((self.root / "cards" / "ghost").exists())


if __name__ == "__main__":
    unittest.main()
