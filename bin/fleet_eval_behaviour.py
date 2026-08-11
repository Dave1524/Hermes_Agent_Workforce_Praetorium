#!/usr/bin/env python3
"""Tier 1 — behavioural conformance: did the fleet publish the way the route table says?

usage: fleet_eval_behaviour.py [--days N] [--routes FILE] [--receipts FILE] [--no-coverage]

Emits one `check|status|value|detail` row per assertion on stdout. Exit 1 on any FAIL.

MEASURED AGAINST EVIDENCE, NOT CONFIG. `check-team-kinds.py` already proves TEAM.md and
the route table agree, and `audit_buzz_dual_run.sh` already proves every expected timer
fire produced a receipt. Neither reads what kind, channel, notify slug or identity a
delivery actually carried — a producer can hand-roll a send that contradicts a route
table both gates certify as correct. This one starts from the receipts.

THE ROUTE TABLE IT READS IS THE DEPLOYED ONE, on purpose. Receipts are written by the
deployed `deliver.sh`, so the deployed table is the config those deliveries were made
under; checking them against an edited source copy would grade yesterday's traffic
against today's intent. Source-vs-deployed drift is its own assertion instead.

SCHEMA AWARENESS. `kind` and `notify` were added to the receipt on 2026-08-08T14:23Z.
Receipts written before that carry neither and are counted as `legacy` rather than
failed — a missing field is not a mismatch. The default 2-day window ages them out.
"""

import argparse
import datetime
import json
import re
import subprocess
import sys
from pathlib import Path

DEPLOYED_BIN = Path.home() / "agent-workforce/bin"
SOURCE_BIN = Path.home() / "dev/agent-workforce/bin"
DEFAULT_RECEIPTS = Path.home() / "logs/delivery-receipts.jsonl"
AUDIT_TIMEOUT_SECS = 120

LEGAL_KINDS = {"9", "45001"}
PUBLISHING_IDENTITY = "praetorium"
ROUTE_LINE = re.compile(r"^ROUTE_([a-z][a-z0-9_-]*?)(_kind|_notify)?=(\S*)$", re.MULTILINE)
UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
AGENT_LINE = re.compile(r"^AGENT_([a-z][a-z0-9_-]*)=(\S+)$", re.MULTILINE)


class Report:
    """Collects rows and owns the exit code, so no assertion can fail silently."""

    def __init__(self):
        self.rows = []
        self.failed = False

    def add(self, check, status, value="", detail=""):
        self.rows.append((check, status, str(value), detail))
        self.failed = self.failed or status == "FAIL"

    def emit(self):
        for row in self.rows:
            print("|".join(row))


def parse_routes(path):
    routes = {}
    for key, suffix, value in ROUTE_LINE.findall(path.read_text()):
        field = {None: "channel", "": "channel", "_kind": "kind", "_notify": "notify"}[suffix]
        routes.setdefault(key, {})[field] = value
    return routes


def parse_agents(path):
    return {slug for slug, _pubkey in AGENT_LINE.findall(path.read_text())}


def check_route_table(report, routes, agents):
    """A route is only usable if all three of its lines are present and legal."""
    problems = []
    for key, route in sorted(routes.items()):
        channel = route.get("channel", "")
        kind = route.get("kind", "9")
        notify = route.get("notify", "none")

        if not channel:
            problems.append(f"{key}: not configured (empty channel — deliver.sh will skip Buzz)")
        elif not UUID.match(channel):
            problems.append(f"{key}: channel {channel!r} is not a uuid")
        if kind not in LEGAL_KINDS:
            problems.append(f"{key}: kind {kind!r} is not one of {sorted(LEGAL_KINDS)}")
        if notify != "none" and notify not in agents:
            problems.append(f"{key}: notify {notify!r} resolves to no agent — the send is fatal")

    if problems:
        report.add("route-table", "FAIL", len(problems), "; ".join(problems))
    else:
        report.add("route-table", "PASS", len(routes), f"{len(routes)} routes, all three lines legal")


def check_deploy_drift(report, deployed, source):
    """An edited source table means nothing until bin/deploy has run."""
    if not source.is_file():
        report.add("route-table-deployed", "WARN", "", f"no source copy at {source} to compare")
        return
    if deployed.read_text() == source.read_text():
        report.add("route-table-deployed", "PASS", "", "deployed table matches source")
    else:
        report.add(
            "route-table-deployed", "FAIL", "",
            f"{source} differs from {deployed} — the running deliver.sh is on the old table. "
            f"Run `bin/deploy`.",
        )


def load_receipts(path, days):
    cutoff = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days)
    receipts = []
    for line in path.read_text().splitlines():
        if not line.strip():
            continue
        receipt = json.loads(line)
        stamped = datetime.datetime.strptime(receipt["ts"], "%Y-%m-%dT%H:%M:%SZ")
        if stamped.replace(tzinfo=datetime.timezone.utc) >= cutoff:
            receipts.append(receipt)
    return receipts


def _published(receipt):
    return receipt.get("buzz_attempted") and receipt.get("buzz_result") == "ok"


def _mismatches(receipt, route):
    """Only fields the receipt actually carries — an absent field is legacy, not wrong."""
    expected = {
        "channel": route.get("channel", ""),
        "kind": route.get("kind", "9"),
        "notify": route.get("notify", "none"),
        "identity": PUBLISHING_IDENTITY,
    }
    return [
        f"{field}={receipt[field]!r} but route says {want!r}"
        for field, want in expected.items()
        if receipt.get(field) is not None and str(receipt[field]) != want
    ]


def check_conformance(report, receipts, routes, days):
    published = [r for r in receipts if _published(r)]
    if not published:
        report.add(
            "receipt-conformance", "WARN", 0,
            f"no successful Buzz delivery in the last {days} days — nothing to certify. "
            f"That is itself worth a look: coverage below says whether a fire was missed.",
        )
        return

    legacy = [r for r in published if "kind" not in r]
    unknown, bad = [], []
    for receipt in published:
        route = routes.get(receipt.get("route", ""))
        if route is None:
            unknown.append(f"{receipt['ts']} {receipt['job']} route={receipt.get('route')!r}")
            continue
        for mismatch in _mismatches(receipt, route):
            bad.append(f"{receipt['ts']} {receipt['job']} route={receipt['route']}: {mismatch}")

    if unknown:
        report.add(
            "receipt-route-known", "FAIL", len(unknown),
            f"delivered to a route the table does not define: {'; '.join(unknown[:3])}",
        )
    else:
        report.add("receipt-route-known", "PASS", len(published), "every delivery names a defined route")

    if bad:
        report.add("receipt-conformance", "FAIL", len(bad), "; ".join(bad[:4]))
    else:
        report.add(
            "receipt-conformance", "PASS", len(published),
            f"{len(published)} deliveries over {days}d match channel/kind/notify/identity"
            + (f" ({len(legacy)} pre-2026-08-08 receipts carry no kind/notify)" if legacy else ""),
        )


def check_route_exercise(report, receipts, routes):
    """Which routes are actually carrying traffic — a silent route is a trend, not a fault."""
    used = {r.get("route") for r in receipts if _published(r)}
    idle = sorted(set(routes) - used)
    report.add(
        "route-exercise", "PASS", f"{len(used)}/{len(routes)}",
        f"idle in window: {', '.join(idle)}" if idle else "every route delivered",
    )


def receipt_era_days(path, ceiling):
    """How far back the receipt log can actually answer for.

    The audit's window is expected fires; its evidence is receipts. Point it at a day
    before the first receipt was ever written and every fire that day reports MISSING —
    33 of them on 2026-08-11, all of which are the log not existing yet rather than a
    delivery that failed. The audit is right; the question was unanswerable.
    """
    stamps = [json.loads(line)["ts"] for line in path.read_text().splitlines() if line.strip()]
    started = datetime.datetime.strptime(min(stamps), "%Y-%m-%dT%H:%M:%SZ")
    covered = (datetime.datetime.now(datetime.timezone.utc).date() - started.date()).days
    return max(1, min(ceiling, covered))


def check_coverage(report, receipts_path, ceiling=7):
    """Delegate; do not reimplement. The audit owns 'did every expected fire land?'.

    Reported, not gated. `audit_buzz_dual_run.sh` is already a gate with its own owner
    and its own dual-run clock — failing this suite on the same condition gives one
    problem two red lights and no new information, and a suite that is red every day for
    a known-flaky Discord leg is a suite nobody reads. What this suite contributes is
    conformance, which nothing else measures.
    """
    audit = DEPLOYED_BIN / "audit_buzz_dual_run.sh"
    if not audit.is_file():
        report.add("delivery-coverage", "FAIL", "", f"{audit} not found")
        return

    days = receipt_era_days(receipts_path, ceiling)
    result = subprocess.run(
        ["bash", str(audit), "--days", str(days)],
        capture_output=True, text=True, timeout=AUDIT_TIMEOUT_SECS,
    )
    summary = next((line for line in reversed(result.stdout.splitlines()) if line.strip()), "")
    status = "PASS" if result.returncode == 0 else "WARN"
    report.add(
        "delivery-coverage", status, result.returncode,
        f"{summary[:240]} (audit over {days}d, the receipt log's own age; it owns this gate)",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=2,
                        help="receipt window; 2 keeps pre-schema receipts out of it")
    parser.add_argument("--routes", type=Path, default=DEPLOYED_BIN / "buzz_routes.env")
    parser.add_argument("--agents", type=Path, default=DEPLOYED_BIN / "buzz_agents.env")
    parser.add_argument("--receipts", type=Path, default=DEFAULT_RECEIPTS)
    parser.add_argument("--no-coverage", action="store_true",
                        help="skip the audit_buzz_dual_run.sh delegation")
    args = parser.parse_args()

    report = Report()
    routes = parse_routes(args.routes)
    agents = parse_agents(args.agents)

    check_route_table(report, routes, agents)
    check_deploy_drift(report, args.routes, SOURCE_BIN / args.routes.name)

    receipts = load_receipts(args.receipts, args.days)
    check_conformance(report, receipts, routes, args.days)
    check_route_exercise(report, receipts, routes)

    if args.no_coverage:
        report.add("delivery-coverage", "SKIP", "", "--no-coverage")
    else:
        check_coverage(report, args.receipts)

    report.emit()
    return 1 if report.failed else 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, subprocess.TimeoutExpired) as error:
        print(f"behaviour|FAIL||{error}")
        sys.exit(1)
