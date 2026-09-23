#!/usr/bin/env python3
"""Turns per agent in a window, split by what woke them — the reader behind the loop alarm.

Usage: turn_rate.py --receipts <root> [--window-min 60] [--now <iso>] <agent>...

One TSV line per agent named on the command line:

    <agent>\t<total>\t<self_scheduled>\t<unknown>\t<self-scheduled run ids, or ->\t<doubled, or ->

Counts every receipt under <root>/buzz-agent@<agent>/ whose ended_at falls inside the window.
A turn is `self_scheduled` when its receipt says origin = scheduled — the session's own cron
or /loop re-prompting it, no relay event behind it (bin/interaction_receipt.py); `unknown`
when the receipt predates the origin field and carries no handoff either. Owner turns and the
unknowns are counted and never alarmed on: fleet-turn-check.sh reads the self_scheduled
column. `doubled` names each relay event that woke this agent more than once in the window,
as `<event-prefix>x<turns>` — one mention answered twice by the box. Turns are counted by
distinct started_at, relay turns only: one prompt can end in two receipts, and a
self-scheduled fire still carries the last inbound event in its handoff; neither is a second
answer. fleet-turn-check.sh gate 6 reads the column. An agent with no receipt directory is a line of zeros, not an error — a fresh agent
has none yet. A receipt that does not parse is skipped and named on stderr; exit 0 regardless,
because a broken file is one file and the gate must still read the other four agents.
"""
from __future__ import annotations

import argparse
import collections
import datetime as dt
import json
import pathlib
import sys

SELF_SCHEDULED = "scheduled"
ORIGIN_RELAY = "relay"


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--receipts", required=True, type=pathlib.Path)
    parser.add_argument("--window-min", type=int, default=60)
    parser.add_argument("--now", default=None, help="ISO-8601 instant for tests; default: the clock")
    parser.add_argument("agents", nargs="+")
    return parser.parse_args(argv)


def parse_time(value: object) -> dt.datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=dt.timezone.utc)


def origin_of(receipt: dict) -> str:
    origin = receipt.get("origin")
    if isinstance(origin, str) and origin:
        return origin
    return ORIGIN_RELAY if receipt.get("handoff") else "unknown"


def receipts_in(directory: pathlib.Path, since: dt.datetime) -> list[dict]:
    if not directory.is_dir():
        return []
    found = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as exc:
            print(f"turn_rate: skipped {path.name}: {exc}", file=sys.stderr)
            continue
        ended = parse_time(data.get("ended_at")) if isinstance(data, dict) else None
        if ended is not None and ended >= since:
            found.append(data)
    return found


def event_of(receipt: dict) -> str | None:
    handoff = receipt.get("handoff")
    event = handoff.get("event") if isinstance(handoff, dict) else None
    return event if isinstance(event, str) and event else None


def doubled_events(receipts: list[dict]) -> str:
    starts: dict[str, set] = collections.defaultdict(set)
    for r in receipts:
        if event_of(r) and origin_of(r) == ORIGIN_RELAY:
            starts[event_of(r)].add(r.get("started_at"))
    return ",".join(f"{event[:12]}x{len(s)}" for event, s in sorted(starts.items()) if len(s) > 1) or "-"


def rate_line(agent: str, receipts: list[dict]) -> str:
    scheduled = [r for r in receipts if origin_of(r) == SELF_SCHEDULED]
    unknown = sum(1 for r in receipts if origin_of(r) == "unknown")
    ids = ",".join(str(r.get("run_id")) for r in scheduled) or "-"
    return f"{agent}\t{len(receipts)}\t{len(scheduled)}\t{unknown}\t{ids}\t{doubled_events(receipts)}"


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    now = parse_time(args.now) if args.now else dt.datetime.now(dt.timezone.utc)
    if now is None:
        print(f"turn_rate: --now is not an ISO-8601 instant: {args.now}", file=sys.stderr)
        return 2
    since = now - dt.timedelta(minutes=args.window_min)
    for agent in args.agents:
        print(rate_line(agent, receipts_in(args.receipts / f"buzz-agent@{agent}", since)))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
