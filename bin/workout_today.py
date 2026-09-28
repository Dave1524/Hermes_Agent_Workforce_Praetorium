#!/usr/bin/env python3
"""workout_today.py — the day's row from Dave's workout schedule, for the daily plan.

    workout_today.py --date YYYY-MM-DD [--schedule PATH]

The schedule (`04_operations/fitness/workout_schedule.md`) has one week section per week,
each with a `| Day | Session | Detail | Status |` table whose first cell is `Mon 9/28`. The
daily plan used to read the whole 33 KB file and include training "only if today has a
slot", so rest days — and some training days — dropped out of the plan (09-17, 09-24, 09-25).
This hands it the one row, so there is always a line to write.

Output, one `key: value` per line: date, week, kind (training|rest), session, detail, status.
Exit: 0 found, 1 the schedule has no row for the date, 2 the schedule could not be read.
"""
import argparse
import datetime as dt
import re
import sys
from pathlib import Path

DEFAULT_SCHEDULE = Path.home() / "vault" / "04_operations" / "fitness" / "workout_schedule.md"
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
ROW = re.compile(r"^\|\s*\**\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun) (\d{1,2})/(\d{1,2})\s*\**\s*\|(.*)$")
REST = re.compile(r"^(rest|travel|fly)\b", re.IGNORECASE)


def plain(cell: str) -> str:
    text = re.sub(r"\[([^\]]+)\]\([^)]*\)", r"\1", cell)
    text = re.sub(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]", r"\1", text)
    return " ".join(text.replace("**", "").split())


def find_row(lines: list[str], day: dt.date):
    week = ""
    for line in lines:
        if line.startswith("### "):
            week = plain(line[4:])
            continue
        match = ROW.match(line)
        if not match or (int(match.group(2)), int(match.group(3))) != (day.month, day.day):
            continue
        cells = match.group(4).split("|")
        if len(cells) < 3:
            continue
        return week, match.group(1), plain(cells[0]), plain("|".join(cells[1:-2])), plain(cells[-2])
    return None


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--date", required=True, type=dt.date.fromisoformat)
    p.add_argument("--schedule", type=Path, default=DEFAULT_SCHEDULE)
    args = p.parse_args(argv)
    try:
        lines = args.schedule.read_text(encoding="utf-8").splitlines()
    except OSError as error:
        print(f"workout_today: cannot read {args.schedule}: {error}", file=sys.stderr)
        return 2
    label = f"{DAYS[args.date.weekday()]} {args.date.month}/{args.date.day}"
    row = find_row(lines, args.date)
    if row is None:
        print(f"workout_today: no row for {label} in {args.schedule}", file=sys.stderr)
        return 1
    week, row_day, session, detail, status = row
    print(f"date: {args.date.isoformat()} ({label})")
    if row_day != DAYS[args.date.weekday()]:
        print(f"note: the row is labelled {row_day}, but {args.date.isoformat()} is a {DAYS[args.date.weekday()]}")
    print(f"week: {week}")
    print(f"kind: {'rest' if REST.match(session) else 'training'}")
    print(f"session: {session}")
    print(f"detail: {detail}")
    print(f"status: {status}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
