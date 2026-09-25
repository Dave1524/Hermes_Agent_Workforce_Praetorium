#!/usr/bin/env python3
"""Offline refusal cases for the protection gate, including missing installation access."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "bin"))
import main_protection as protection


class Protection(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((ROOT / "config/main-ruleset.json").read_text())

    def test_rules_are_required(self):
        # (::main-protection-rules)
        self.assertEqual(protection.ruleset_errors(self.config), [])
        for kind in protection.REQUIRED:
            with self.subTest(kind=kind):
                rules = [r for r in self.config["rules"] if r["type"] != kind]
                self.assertTrue(protection.rule_errors(rules))
        for change in ("approval", "stale", "context", "app"):
            with self.subTest(change=change):
                config = copy.deepcopy(self.config)
                pr, checks = config["rules"][:2]
                if change == "approval":
                    pr["parameters"]["required_approving_review_count"] = 0
                elif change == "stale":
                    pr["parameters"]["dismiss_stale_reviews_on_push"] = False
                else:
                    key = "context" if change == "context" else "integration_id"
                    checks["parameters"]["required_status_checks"][0][key] = "wrong"
                self.assertTrue(protection.ruleset_errors(config))

    def test_bypass_and_disabled_rulesets_are_refused(self):
        # (::main-protection-no-bypass)
        for field, value in (("bypass_actors", [{"actor_id": 5, "actor_type": "RepositoryRole"}]),
                             ("enforcement", "evaluate"), ("target", "tag"),
                             ("conditions", {"ref_name": {"include": ["refs/heads/other"], "exclude": []}})):
            with self.subTest(field=field):
                config = {**self.config, field: value}
                self.assertTrue(protection.ruleset_errors(config))

    def test_live_read_joins_effective_rules_and_installation(self):
        # (::main-protection-installation)
        effective = [{**rule, "ruleset_id": 42} for rule in self.config["rules"]]
        pages = [{"repositories": []}, {"repositories": [{"full_name": protection.REPO}]}]
        with patch.object(protection, "api", side_effect=[effective, self.config, pages]) as api:
            self.assertEqual(protection.live_errors(), [])
            self.assertTrue(api.call_args.kwargs["paginate"])
        with patch.object(protection, "api", side_effect=[effective, self.config, [{"repositories": []}]]):
            self.assertIn("App installation", " ".join(protection.live_errors()))
        with patch.object(protection, "api", side_effect=[[], pages]):
            self.assertIn("main lacks pull_request", protection.live_errors())
        with patch.object(protection, "api", side_effect=RuntimeError("API unavailable")):
            with self.assertRaisesRegex(RuntimeError, "API unavailable"):
                protection.live_errors()


if __name__ == "__main__":
    unittest.main()
