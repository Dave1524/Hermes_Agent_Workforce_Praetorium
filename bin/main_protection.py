#!/usr/bin/env python3
"""Read back T8.2's main protection and App installation; never change GitHub state."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess

REPO = "Dave1524/Hermes_Agent_Workforce_Praetorium"
ROOT = Path(__file__).resolve().parent.parent
REQUIRED = {"pull_request", "required_status_checks", "deletion", "non_fast_forward"}


def rule_errors(rules: list[dict]) -> list[str]:
    errors = []
    for kind in sorted(REQUIRED):
        candidates = [rule for rule in rules if rule.get("type") == kind]
        if not candidates:
            errors.append(f"main lacks {kind}")
        elif kind == "pull_request" and not any(
            rule.get("parameters", {}).get("required_approving_review_count", 0) >= 1
            and rule.get("parameters", {}).get("dismiss_stale_reviews_on_push") is True
            for rule in candidates
        ):
            errors.append("main must require approval and dismiss stale reviews")
        elif kind == "required_status_checks" and not any(
            check.get("context") == "gate" and check.get("integration_id") == 15368
            for rule in candidates for check in rule.get("parameters", {}).get("required_status_checks", [])
        ):
            errors.append("main must require gate from GitHub Actions (15368)")
    return errors


def ruleset_errors(ruleset: dict) -> list[str]:
    errors = rule_errors(ruleset.get("rules", []))
    if ruleset.get("enforcement") != "active" or ruleset.get("target") != "branch":
        errors.append("protection must be an active branch ruleset")
    if ruleset.get("bypass_actors") != []:
        errors.append("protection must have no bypass actors")
    refs = ruleset.get("conditions", {}).get("ref_name", {})
    if not set(refs.get("include", [])).intersection({"~DEFAULT_BRANCH", "refs/heads/main", "~ALL"}) or refs.get("exclude") != []:
        errors.append("protection must include main with no exclusions")
    return errors


def api(command: list[str], endpoint: str, paginate: bool = False):
    args = [*command, "api", endpoint]
    if paginate:
        args.extend(["--paginate", "--slurp"])
    done = subprocess.run(args, text=True, capture_output=True, timeout=60)
    if done.returncode:
        raise RuntimeError(f"GitHub read failed: {endpoint} (exit {done.returncode})")
    return json.loads(done.stdout)


def live_errors() -> list[str]:
    # These are read-only calls. gh's human identity reads the rules; the wrapper proves
    # App access separately without handling a credential in this process.
    effective = api(["gh"], f"repos/{REPO}/rules/branches/main")
    errors = rule_errors(effective)
    ids = {rule.get("ruleset_id") for rule in effective if rule.get("type") in REQUIRED}
    protections = [api(["gh"], f"repos/{REPO}/rulesets/{rid}") for rid in ids if rid is not None]
    if not any(not ruleset_errors(ruleset) for ruleset in protections):
        errors.append("no active, non-bypassable ruleset covers all four requirements")
    try:
        pages = api([str(ROOT / "bin/gh_app.sh")], "/installation/repositories", paginate=True)
    except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
        return [*errors, f"App installation could not be verified: {exc}"]
    if not any(repo.get("full_name") == REPO for page in pages for repo in page.get("repositories", [])):
        errors.append(f"App installation does not include {REPO}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--live", action="store_true", help="read effective rules and the App installation")
    args = parser.parse_args()
    try:
        errors = ruleset_errors(json.loads((ROOT / "config/main-ruleset.json").read_text()))
        if args.live:
            errors.extend(live_errors())
    except (OSError, ValueError, TypeError, KeyError, RuntimeError, subprocess.TimeoutExpired) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f"  FAIL: main protection: {error}")
    if not errors:
        print("  ok: main protection " + ("and App access verified live" if args.live else "configuration is valid (live state not checked)"))
    return int(bool(errors))


if __name__ == "__main__":
    raise SystemExit(main())
