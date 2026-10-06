#!/usr/bin/env python3
"""The agent_propose.sh time budget: one owner for the arithmetic the runner and the audit share.

usage:
  propose_budget.py check --attempts N --timeout-min T --retry-base S --retry-within W
                          --reserve R [--unit UNIT]
  propose_budget.py audit SYSTEMD_DIR PROFILES_DIR

A unit that runs agent_propose.sh is Type=oneshot, so its TimeoutStartSec covers preflight,
the whole attempt loop and the ExecStartPost delivery. Only a failure faster than
AGENT_RETRY_WITHIN_SECONDS is retried, so the worst case is (n-1) fast failures, their
backoff, one full attempt, and the reserve for preflight and delivery.

`check` prints one `key=value` line for the runner: budget=fit|misfit|unknown, the worst case,
the unit's limit and the seconds of it still left. Unknown (no unit, not activating, no
limit) never refuses a run. PROPOSE_BUDGET_LIMIT / PROPOSE_BUDGET_REMAINING replace the
systemctl read in fixtures.

`audit` reads every unit whose ExecStart runs the runner, pairs it with the committed
override example its AGENT_JOB_OVERRIDES names, and exits 1 on any unit the example cannot
fit, any missing example and any missing knob.
"""

import argparse
import os
import re
import subprocess
import sys
import time
from pathlib import Path

MARGIN_SECONDS = 60
KNOBS = ("AGENT_MAX_ATTEMPTS", "AGENT_TIMEOUT_MINUTES", "AGENT_RETRY_BASE_SECONDS",
         "AGENT_RETRY_WITHIN_SECONDS")
RUNNERS = ("agent_propose.sh", "content_change_dispatch.sh")
AUDIT_RESERVE_SECONDS = 180
_SPAN = re.compile(r"(\d+)\s*(us|ms|s|sec|min|m|h|d)?")
_UNIT_SECONDS = {None: 1, "s": 1, "sec": 1, "min": 60, "m": 60, "h": 3600, "d": 86400,
                 "ms": 0.001, "us": 0.000001}


def worst_case(attempts: int, timeout_s: int, retry_base: int, retry_within: int, reserve: int) -> int:
    retried = attempts - 1
    fast_failures = retried * min(retry_within, timeout_s)
    backoff = sum(retry_base * k * k for k in range(1, attempts))
    return fast_failures + backoff + timeout_s + reserve


def fits(worst: int, limit: float) -> bool:
    return worst + MARGIN_SECONDS <= limit


def parse_span(text: str) -> float | None:
    """A systemd time span ("20min", "1h 30min", "90") in seconds; None for infinity/empty."""
    text = text.strip()
    if not text or text == "infinity":
        return None
    parts = _SPAN.findall(text)
    if not parts:
        return None
    return sum(int(n) * _UNIT_SECONDS[u or None] for n, u in parts)


def _systemctl_show(unit: str) -> dict[str, str]:
    out = subprocess.run(
        ["systemctl", "show", unit, "-p", "TimeoutStartUSec", "-p", "ActiveState",
         "-p", "InactiveExitTimestampMonotonic"],
        capture_output=True, text=True, timeout=10, check=True,
    ).stdout
    return dict(line.split("=", 1) for line in out.splitlines() if "=" in line)


def unit_clock(unit: str) -> tuple[float | None, float | None]:
    """(limit, remaining) in seconds for the unit's current start job; None where unknowable."""
    if "PROPOSE_BUDGET_LIMIT" in os.environ or "PROPOSE_BUDGET_REMAINING" in os.environ:
        limit = os.environ.get("PROPOSE_BUDGET_LIMIT")
        remaining = os.environ.get("PROPOSE_BUDGET_REMAINING")
        return (float(limit) if limit else None, float(remaining) if remaining else None)
    if not unit:
        return None, None
    try:
        props = _systemctl_show(unit)
    except (OSError, subprocess.SubprocessError):
        return None, None
    limit = parse_span(props.get("TimeoutStartUSec", ""))
    started_us = int(props.get("InactiveExitTimestampMonotonic", "0") or 0)
    if limit is None or props.get("ActiveState") != "activating" or not started_us:
        return limit, None
    return limit, limit - (time.monotonic() - started_us / 1_000_000)


def check(args: argparse.Namespace) -> int:
    worst = worst_case(args.attempts, args.timeout_min * 60, args.retry_base, args.retry_within, args.reserve)
    limit, remaining = unit_clock(args.unit or "")
    state = "unknown" if limit is None else ("fit" if fits(worst, limit) else "misfit")
    fmt = lambda v: "unknown" if v is None else str(int(v))  # noqa: E731
    print(f"budget={state} worst={worst} limit={fmt(limit)} remaining={fmt(remaining)} "
          f"margin={MARGIN_SECONDS} unit={args.unit or 'none'}")
    return 0


def read_env_file(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        match = re.match(r"^([A-Z_][A-Z0-9_]*)=(.*)$", line.strip())
        if match:
            values[match.group(1)] = match.group(2).strip("'\"")
    return values


def read_unit(path: Path) -> dict[str, str]:
    unit = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line.startswith("ExecStart="):
            unit["exec"] = line.split("=", 1)[1]
        elif line.startswith("TimeoutStartSec="):
            unit["timeout"] = line.split("=", 1)[1]
        elif line.startswith("Environment=AGENT_JOB_OVERRIDES="):
            unit["overrides"] = line.split("=", 2)[2]
    return unit


def audit_unit(path: Path, profiles: Path) -> str | None:
    """None when the unit's committed budget fits, else what is wrong."""
    unit = read_unit(path)
    if "overrides" not in unit:
        return "runs the agent_propose runner but sets no AGENT_JOB_OVERRIDES — its budget is uncheckable"
    example = profiles / (Path(unit["overrides"]).name + ".example")
    if not example.is_file():
        return f"no committed example {example.name} for {unit['overrides']}"
    knobs = read_env_file(example)
    missing = [k for k in KNOBS if k not in knobs]
    if missing:
        return f"{example.name} does not set {', '.join(missing)}"
    limit = parse_span(unit.get("timeout", ""))
    if limit is None:
        return "no finite TimeoutStartSec"
    worst = worst_case(int(knobs["AGENT_MAX_ATTEMPTS"]), int(knobs["AGENT_TIMEOUT_MINUTES"]) * 60,
                       int(knobs["AGENT_RETRY_BASE_SECONDS"]), int(knobs["AGENT_RETRY_WITHIN_SECONDS"]),
                       AUDIT_RESERVE_SECONDS)
    if not fits(worst, limit):
        return (f"worst case {worst}s + {MARGIN_SECONDS}s margin exceeds TimeoutStartSec {int(limit)}s "
                f"({example.name})")
    print(f"ok: {path.name} worst={worst}s limit={int(limit)}s ({example.name})")
    return None


def audit(args: argparse.Namespace) -> int:
    units = sorted(p for p in Path(args.systemd_dir).glob("*.service")
                   if any(r in read_unit(p).get("exec", "") for r in RUNNERS))
    if not units:
        print(f"FAIL: no agent_propose units under {args.systemd_dir}")
        return 1
    failures = [(p, audit_unit(p, Path(args.profiles_dir))) for p in units]
    for path, problem in failures:
        if problem:
            print(f"FAIL: {path.name}: {problem}")
    return 1 if any(problem for _, problem in failures) else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="command", required=True)
    c = sub.add_parser("check")
    for flag in ("--attempts", "--timeout-min", "--retry-base", "--retry-within", "--reserve"):
        c.add_argument(flag, type=int, required=True)
    c.add_argument("--unit", default="")
    a = sub.add_parser("audit")
    a.add_argument("systemd_dir")
    a.add_argument("profiles_dir")
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    return check(args) if args.command == "check" else audit(args)


if __name__ == "__main__":
    sys.exit(main())
