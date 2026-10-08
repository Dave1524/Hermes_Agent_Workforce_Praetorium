#!/usr/bin/env python3
"""bin/card_checks.py: each board-join check passes on a clean card run, fails for the one
defect it names, and is n/a without a card or without page text. Also runs the four through the
LIVE contract's check blocks, so a block that stops calling its verb is caught here."""

from __future__ import annotations

import hashlib
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))

import contract_exec  # noqa: E402

BRIEF = "# Brief: card-one\n\n## Question\n\nq\n\n## Acceptance\n\n- one\n- two\n\n## Size\n\nx\n"
RESEARCH = "# card-one — q\n\nfindings, MET in passing\n\n## Acceptance\n\n- MET: one, because x\n- PARTLY: two, because y\n\n## Sources\n\n- s\n"
VERBS = ("page-names-card", "published-is-this-run", "acceptance-answered", "pick-hash-matched")


def board_hash(text: str) -> str:
    return hashlib.sha256(text.rstrip().encode()).hexdigest()


class CardChecks(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = pathlib.Path(self.temp.name)
        self.card = self.root / "runs" / "r1"
        briefs = self.root / "cards" / "card-one" / "briefs"
        self.card.mkdir(parents=True)
        briefs.mkdir(parents=True)
        self.brief_hash = "a" * 64
        (briefs / f"{self.brief_hash}.md").write_text(BRIEF)
        self.write_run(RESEARCH)

    def tearDown(self):
        self.temp.cleanup()

    def write_run(self, research, page_hash=None, picked=None, published_brief=None):
        (self.card / "research.md").write_text(research)
        (self.card / "pick.json").write_text(json.dumps({"brief_hash": picked or self.brief_hash}))
        (self.card / "published.json").write_text(json.dumps({
            "card": "card-one", "page": "page-1", "page_hash": page_hash or board_hash(research),
            "brief_hash": published_brief or self.brief_hash}))

    def env(self, **extra):
        env = {"PATH": os.environ["PATH"], "AGENT_CARD": "card-one", "AGENT_CARD_DIR": str(self.card),
               "BOARD_ROOT": str(self.root)}
        env.update(extra)
        return {k: v for k, v in env.items() if v is not None}

    def verb(self, name, **extra):
        done = subprocess.run([sys.executable, str(ROOT / "bin" / "card_checks.py"), name],
                              capture_output=True, text=True, env=self.env(**extra))
        return done.returncode, done.stdout.strip()

    def test_a_clean_run_passes_all_four(self):
        for name in VERBS:
            self.assertEqual(self.verb(name), (0, ""), name)

    def test_not_applicable_without_a_card_or_page_text(self):
        for name in VERBS:
            self.assertEqual(self.verb(name, AGENT_CARD=None)[0], 77, name)
        (self.card / "research.md").unlink()
        for name in VERBS:
            self.assertEqual(self.verb(name)[0], 77, name)

    def test_each_check_fails_for_its_own_defect(self):
        self.write_run(RESEARCH, page_hash="c" * 64)
        self.assertEqual(self.verb("published-is-this-run")[0], 1)
        self.assertEqual(self.verb("page-names-card")[0], 0)
        self.write_run(RESEARCH)
        (self.card / "published.json").write_text(json.dumps({"card": "other", "page": "p"}))
        self.assertEqual(self.verb("page-names-card")[0], 1)
        self.write_run(RESEARCH.replace("- PARTLY: two", "- two"))
        self.assertEqual(self.verb("acceptance-answered")[0], 1)
        self.write_run(RESEARCH.replace("- MET: one", "- MET and NOT MET: one"))
        self.assertEqual(self.verb("acceptance-answered")[0], 1, "two verdicts on a line answer nothing")
        self.write_run(RESEARCH, published_brief="d" * 64)
        self.assertEqual(self.verb("pick-hash-matched")[0], 1)
        (self.card / "published.json").unlink()
        for name in ("page-names-card", "published-is-this-run", "pick-hash-matched"):
            code, out = self.verb(name)
            self.assertEqual(code, 1, name)
            self.assertIn("published.json unreadable", out)

    def test_findings_prose_does_not_count_as_an_answer(self):
        self.write_run(RESEARCH.replace("## Acceptance", "## Verdicts"))
        self.assertEqual(self.verb("acceptance-answered")[0], 1)

    def test_the_live_contract_calls_each_verb(self):
        text = (ROOT / "design" / "contracts" / "standing-research.md").read_text()
        checks = {c["id"]: c for c in contract_exec.declared_checks(text)}
        home = self.root / "home"
        (home / "agent-workforce").mkdir(parents=True)
        (home / "agent-workforce" / "bin").symlink_to(ROOT / "bin")
        env = {**self.env(), "HOME": str(home)}
        for name in VERBS:
            result = contract_exec.run_check(checks[name], env, "run", self.root)
            self.assertEqual(result["status"], "passed", (name, result))
        (self.card / "research.md").write_text(RESEARCH.replace("- PARTLY: two", "- two"))
        result = contract_exec.run_check(checks["acceptance-answered"], env, "run", self.root)
        self.assertEqual(result["status"], "failed")
        env["AGENT_CARD"] = ""
        for name in VERBS:
            self.assertEqual(contract_exec.run_check(checks[name], env, "run", self.root)["status"], "not_applicable")


if __name__ == "__main__":
    unittest.main()
