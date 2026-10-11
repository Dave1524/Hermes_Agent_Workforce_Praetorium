#!/usr/bin/env python3
"""The board half of bin/control_broker.py (Dev Plan B9, spec §3.7 and §7 decisions 10 and 12).

Real `ssh-keygen` keys in a temp dir, the broker run as a subprocess on a pipe, synthetic cards only.
Each class carries the `::` anchor design/fleet-suites.toml declares for it.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import pathlib
import socket
import stat
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
BROKER = ROOT / "bin" / "control_broker.py"
NOW = "2026-10-10T08:00:00Z"
HASH_A = "a" * 64
HASH_B = "b" * 64
sys.path.insert(0, str(ROOT / "bin"))
import board  # noqa: E402
import board_decision_sig as sig  # noqa: E402
import control_broker as broker  # noqa: E402
import control_broker_allowlist as allowlist  # noqa: E402

PAGE = "# Findings\n\nThe synthetic thing holds.\n\n## Acceptance\n1. MET\n"


class BoardBox:
    def __init__(self, verbs: list[str] | None = None, board_section: bool = True) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.key = self.root / "board_signing_key"
        subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", "board-broker", "-f", str(self.key)], check=True)
        self.signers = self.root / "allowed_signers"
        self.signers.write_text(sig.allowed_signers_line(self.key.with_suffix(".pub").read_text()))
        data = {"schema": 1, "workflows": {}, "excluded": []}
        if board_section:
            data["board"] = {"verbs": list(broker.BOARD_VERBS if verbs is None else verbs)}
        self.allowlist = self.root / "allowlist.json"
        self.allowlist.write_text(json.dumps(data))
        self.stream_dir = self.root / "receipts" / "board"
        self.stream = self.stream_dir / "decisions.jsonl"

    def close(self) -> None:
        self.temp.cleanup()

    def argv(self, peer_uids: str | None = None, key: pathlib.Path | None = None) -> list[str]:
        return [sys.executable, str(BROKER), "--serve", "--allowlist", str(self.allowlist),
                "--receipts", str(self.root / "receipts"), "--board-dir", str(self.stream_dir),
                "--board-key", str(key or self.key), "--peer-uids", peer_uids or str(os.getuid()),
                "--lock", str(self.root / "lock"), "--now", NOW]

    def call(self, request: dict | bytes, **kwargs) -> dict:
        body = request if isinstance(request, bytes) else (json.dumps(request) + "\n").encode()
        done = subprocess.run(self.argv(**kwargs), input=body, capture_output=True, check=False, timeout=60)
        assert done.returncode == 0, done.stderr.decode()
        return json.loads(done.stdout.decode())

    def call_socket(self, request: dict, **kwargs) -> dict:
        ours, theirs = socket.socketpair(socket.AF_UNIX, socket.SOCK_STREAM)
        with ours, theirs:
            process = subprocess.Popen(self.argv(**kwargs), stdin=theirs, stdout=theirs, stderr=subprocess.PIPE)
            theirs.close()
            ours.sendall((json.dumps(request) + "\n").encode())
            ours.shutdown(socket.SHUT_WR)
            chunks = []
            while chunk := ours.recv(65536):
                chunks.append(chunk)
            _, stderr = process.communicate(timeout=60)
        assert process.returncode == 0, stderr.decode()
        return json.loads(b"".join(chunks).decode())

    def lines(self) -> list[dict]:
        return [json.loads(l) for l in self.stream.read_text().splitlines()] if self.stream.exists() else []


def board_req(verb: str, **fields) -> dict:
    return {"v": 1, "board_verb": verb, "card": "alpha-question", **fields}


VALID = {
    "brief_approved": {"brief_hash": HASH_A},
    "brief_returned": {"brief_hash": HASH_A, "reason": "keep it local"},
    "approved": {"page_hash": board.text_hash(PAGE), "text": PAGE},
    "changes_requested": {"reason": "answer the second line"},
    "rejected": {"reason": "not worth a note"},
    "blocked": {"reason": "waiting on a decision"},
    "unblocked": {},
}


class BoardCase(unittest.TestCase):
    def setUp(self) -> None:
        self.box = BoardBox()

    def tearDown(self) -> None:
        self.box.close()

    def assertRefused(self, response: dict, code: str) -> None:
        self.assertEqual(response["result"], "refused", response)
        self.assertEqual(response["refusal"]["code"], code, response["refusal"])
        self.assertEqual(self.box.lines(), [], "a refusal must write nothing")


class Verbs(BoardCase):  # (::broker-board-verbs)
    def test_the_vocabulary_is_boards_seven_decisions(self):
        self.assertEqual(broker.BOARD_VERBS, board.DECISIONS)
        self.assertEqual(set(VALID), set(board.DECISIONS))

    def test_each_verb_appends_one_record_with_what_it_was_given(self):
        for number, (verb, fields) in enumerate(VALID.items(), 1):
            response = self.box.call(board_req(verb, **fields))
            self.assertEqual(response["result"], "applied", response)
            lines = self.box.lines()
            self.assertEqual(len(lines), number)
            record = lines[-1]
            self.assertEqual((record["decision"], record["card"], record["ts"]), (verb, "alpha-question", NOW))
            for key, value in fields.items():
                self.assertEqual(record[key], value)
            if verb != "approved":
                self.assertNotIn("text", record)

    def test_board_reads_the_stream_the_broker_wrote(self):
        self.box.call(board_req("brief_approved", brief_hash=HASH_A))
        self.box.call(board_req("approved", **VALID["approved"]))
        os.environ["BOARD_DECISIONS_ROOT"] = str(self.box.stream_dir)
        self.addCleanup(os.environ.pop, "BOARD_DECISIONS_ROOT", None)
        read = board.read_decisions()
        self.assertEqual([d["decision"] for d in read], ["brief_approved", "approved"])
        self.assertEqual(board.text_hash(read[1]["text"]), read[1]["page_hash"])

    def test_the_hash_the_broker_checks_is_the_hash_board_signs(self):
        for text in (PAGE, PAGE + "  \n\n", PAGE.replace("\n", "\r\n"), "x"):
            self.assertEqual(broker.page_text_hash(text), board.text_hash(text))

    def test_an_approval_whose_text_does_not_hash_to_page_hash_is_refused(self):
        self.assertRefused(self.box.call(board_req("approved", page_hash=HASH_A, text=PAGE)), "hash_mismatch")

    def test_a_large_page_fits_and_a_large_workflow_request_does_not(self):
        big = "line of findings\n" * 8000
        response = self.box.call(board_req("approved", page_hash=board.text_hash(big), text=big))
        self.assertEqual(response["result"], "applied", response["refusal"])
        padded = {"workflow_id": "x", "action": "pause", "reason": "r" * 9000}
        self.assertEqual(self.box.call(padded)["refusal"]["code"], "bad_request")


class Signature(BoardCase):  # (::broker-board-signature)
    def setUp(self) -> None:
        super().setUp()
        for verb, fields in VALID.items():
            self.box.call(board_req(verb, **fields))

    def test_every_line_verifies_against_the_public_key(self):
        self.assertEqual(sig.verify_stream(self.box.stream, self.box.signers), [])
        self.assertEqual(subprocess.run([sys.executable, str(ROOT / "bin" / "board_decision_sig.py"), "verify",
                                         "--allowed-signers", str(self.box.signers), str(self.box.stream)]).returncode, 0)

    def test_changing_any_signed_field_breaks_the_line(self):
        for field, value in (("reason", "approved by someone else"), ("card", "other-card"), ("decision", "approved"),
                             ("ts", "2026-10-11T08:00:00Z"), ("page_hash", HASH_B), ("text", "tampered")):
            for record in self.box.lines():
                if field in record and record[field] != value:
                    self.assertFalse(sig.verify({**record, field: value}, self.box.signers), field)

    def test_a_record_without_a_signature_or_with_another_key_does_not_verify(self):
        record = self.box.lines()[0]
        self.assertFalse(sig.verify({k: v for k, v in record.items() if k != "sig"}, self.box.signers))
        other = BoardBox()
        self.addCleanup(other.close)
        self.assertFalse(sig.verify(record, other.signers))

    def test_the_signature_is_over_canonical_json_without_sig(self):
        record = self.box.lines()[0]
        reordered = dict(reversed(list(record.items())))
        self.assertEqual(sig.canonical(record), sig.canonical(reordered))
        self.assertNotIn(b'"sig"', sig.canonical(record))

    def test_a_missing_key_fails_and_writes_nothing(self):
        fresh = BoardBox()
        self.addCleanup(fresh.close)
        response = fresh.call(board_req("unblocked"), key=fresh.root / "absent")
        self.assertEqual(response["result"], "failed", response)
        self.assertEqual(fresh.lines(), [])


class Refusals(BoardCase):  # (::broker-board-refusals)
    def test_unknown_verb_card_and_keys_are_refused(self):
        self.assertRefused(self.box.call(board_req("decided")), "unknown_action")
        self.assertRefused(self.box.call(board_req("approved", **VALID["approved"], extra="x")), "bad_request")
        for card in ("", "Alpha", "../x", "a" * 64, 7):
            self.assertRefused(self.box.call({**board_req("unblocked"), "card": card}), "bad_request")

    def test_each_verb_needs_its_fields(self):
        needs = {"brief_approved": ["brief_hash"], "brief_returned": ["brief_hash", "reason"], "approved": ["page_hash", "text"],
                 "changes_requested": ["reason"], "rejected": ["reason"]}
        for verb, keys in needs.items():
            for key in keys:
                fields = {k: v for k, v in VALID[verb].items() if k != key}
                self.assertRefused(self.box.call(board_req(verb, **fields)), "bad_request")
        self.assertRefused(self.box.call(board_req("brief_approved", brief_hash="nothex")), "bad_request")
        self.assertRefused(self.box.call(board_req("rejected", reason="   ")), "reason_required")

    def test_fields_a_verb_does_not_take_are_refused(self):
        self.assertRefused(self.box.call(board_req("unblocked", text="x")), "bad_request")
        self.assertRefused(self.box.call(board_req("rejected", reason="r", brief_hash=HASH_A)), "bad_request")

    def test_a_verb_outside_the_allowlist_is_refused(self):
        narrow = BoardBox(verbs=["blocked"])
        self.addCleanup(narrow.close)
        self.assertEqual(narrow.call(board_req("approved", **VALID["approved"]))["refusal"]["code"], "not_allowlisted")
        self.assertEqual(narrow.call(board_req("blocked", reason="r"))["result"], "applied")
        bare = BoardBox(board_section=False)
        self.addCleanup(bare.close)
        self.assertEqual(bare.call(board_req("blocked", reason="r"))["refusal"]["code"], "not_allowlisted")
        self.assertEqual(bare.lines(), [])

    def test_a_bad_allowlist_board_section_is_refused(self):
        self.box.allowlist.write_text(json.dumps({"schema": 1, "workflows": {}, "excluded": [], "board": {"verbs": ["wipe"]}}))
        self.assertRefused(self.box.call(board_req("blocked", reason="r")), "allowlist_invalid")

    def test_a_peer_outside_the_allowed_uids_is_refused_on_a_socket(self):
        response = self.box.call_socket(board_req("blocked", reason="r"), peer_uids="99999")
        self.assertRefused(response, "peer_denied")

    def test_a_screen_request_from_the_screens_own_host_is_refused(self):
        actor = {"remote": "100.64.0.9", "local": "100.64.0.9", "label": "x"}
        self.assertRefused(self.box.call_socket({**board_req("blocked", reason="r"), "actor": actor}), "peer_denied")


class Stream(BoardCase):  # (::broker-board-stream)
    def test_the_stream_is_world_readable_and_root_written_only_by_the_broker(self):
        self.box.call(board_req("unblocked"))
        self.assertEqual(stat.S_IMODE(self.box.stream.stat().st_mode), 0o644)
        self.assertEqual(stat.S_IMODE(self.box.stream_dir.stat().st_mode), 0o755)

    def test_appends_accumulate_and_stay_valid_under_concurrency(self):
        with concurrent.futures.ThreadPoolExecutor(8) as pool:
            results = list(pool.map(lambda n: self.box.call(board_req("blocked", reason=f"reason {n}")), range(8)))
        self.assertEqual([r["result"] for r in results], ["applied"] * 8)
        self.assertEqual(len(self.box.lines()), 8)
        self.assertEqual(sig.verify_stream(self.box.stream, self.box.signers), [])

    def test_each_record_has_a_unique_id_and_how_it_arrived(self):
        for _ in range(3):
            self.box.call({**board_req("unblocked"), "actor": {"remote": "100.64.0.1", "local": "100.64.0.9", "label": "screen from 100.64.0.1"}})
        ids = [r["id"] for r in self.box.lines()]
        self.assertEqual(len(set(ids)), 3)
        self.assertEqual({r["via"] for r in self.box.lines()}, {"cli"})

    def test_the_broker_never_runs_board_py(self):
        self.assertNotRegex(BROKER.read_text(), r"(?m)^\s*(import|from)\s+board\b")


class AllowlistBoardRender(unittest.TestCase):  # (::broker-board-allowlist-render)
    def test_render_carries_the_seven_verbs_and_loads(self):
        rendered = allowlist.render(ROOT)
        self.assertEqual(rendered["board"], {"verbs": sorted(board.DECISIONS)})
        self.assertEqual(broker.Allowlist.load_data(rendered).board_verbs, sorted(board.DECISIONS))
        self.assertEqual(allowlist.dumps(rendered), allowlist.dumps(allowlist.render(ROOT)))


if __name__ == "__main__":
    unittest.main()
