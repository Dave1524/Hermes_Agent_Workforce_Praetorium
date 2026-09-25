#!/usr/bin/env python3
"""codex_turn_error.py — why a codex-acp turn failed, read from Codex's own log.

A turn that Codex refuses reaches buzz-acp only as `-32603 Internal error`, fires no
`notify` hook (so there is no interaction receipt), and posts nothing. The one record of the
cause is the `Turn error: …` line Codex writes to `$CODEX_HOME/logs_2.sqlite`. On 2026-09-18
and again from 2026-09-24 that line said the plan was over its usage limit, while every
consumer on the box reported "Internal error", "ERRORED" or "no reply".

    codex_turn_error.py last --codex-home DIR --since EPOCH
        The newest turn error at or after EPOCH.
    codex_turn_error.py blocking --codex-home DIR [--now EPOCH] [--lookback-hours N]
        A usage-limit refusal whose retry time is still ahead, with no successful model
        request logged after it (credits bought early clear the block on the next turn).
    codex_turn_error.py classify TEXT
        The class of one error text.

Output (last, blocking), one tab-separated line:
    <class> <retry-at|-> <retry-epoch|0> <error-at> <message>
Classes: quota-exhausted, model-unavailable, harness-error.
Exit: 0 found, 1 none, 2 the log could not be read. Opens the database read-only.
"""
import argparse
import re
import sqlite3
import sys
import time
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

TURN_ERROR = "Turn error:"
SAMPLED = "post sampling token usage"
MESSAGE_CHARS = 300
BUSY_MS = 5000


def classify(text: str) -> str:
    if "usage limit" in text:
        return "quota-exhausted"
    if "does not exist or you do not have access" in text or "model_not_found" in text:
        return "model-unavailable"
    return "harness-error"


def _local(epoch: float) -> str:
    return datetime.fromtimestamp(epoch).astimezone().strftime("%Y-%m-%d %H:%M %Z")


def _absolute_retry(raw: str) -> float | None:
    cleaned = re.sub(r"(\d+)(st|nd|rd|th)\b", r"\1", raw)
    for fmt in ("%b %d, %Y %I:%M %p", "%B %d, %Y %I:%M %p"):
        try:
            return datetime.strptime(cleaned, fmt).astimezone().timestamp()
        except ValueError:
            continue
    return None


def _time_only_retry(raw: str, error_epoch: float) -> float | None:
    try:
        clock = datetime.strptime(raw, "%I:%M %p").time()
    except ValueError:
        return None
    at = datetime.combine(datetime.fromtimestamp(error_epoch).date(), clock).astimezone()
    if at.timestamp() < error_epoch:
        at += timedelta(days=1)
    return at.timestamp()


def retry_epoch(message: str, error_epoch: float) -> float | None:
    """Codex prints the reset in the process's local time: `Sep 26th, 2026 11:14 AM`, or
    only `10:32 AM` when it falls on the same day."""
    match = re.search(r"try again at (.+?)\.?\s*$", message)
    if not match:
        return None
    raw = match.group(1).strip()
    return _absolute_retry(raw) or _time_only_retry(raw, error_epoch)


def _connect(codex_home: Path) -> sqlite3.Connection:
    db = codex_home / "logs_2.sqlite"
    if not db.is_file():
        raise sqlite3.OperationalError(f"no Codex log at {db}")
    con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=BUSY_MS / 1000)
    con.execute(f"PRAGMA busy_timeout = {BUSY_MS}")
    return con


def newest_turn_error(con: sqlite3.Connection, since: float):
    return con.execute(
        "SELECT ts, ts_nanos, feedback_log_body FROM logs "
        "WHERE ts >= ? AND feedback_log_body LIKE ? "
        "ORDER BY ts DESC, ts_nanos DESC, id DESC LIMIT 1",
        (int(since), f"%{TURN_ERROR}%"),
    ).fetchone()


def sampled_after(con: sqlite3.Connection, ts: int, ts_nanos: int) -> bool:
    return con.execute(
        "SELECT 1 FROM logs WHERE (ts > ? OR (ts = ? AND ts_nanos > ?)) "
        "AND feedback_log_body LIKE ? LIMIT 1",
        (ts, ts, ts_nanos, f"%{SAMPLED}%"),
    ).fetchone() is not None


def describe(row) -> tuple[str, float | None, float, str]:
    ts, ts_nanos, body = row
    error_epoch = ts + ts_nanos / 1e9
    message = body[body.rindex(TURN_ERROR) + len(TURN_ERROR):].strip()
    return classify(message), retry_epoch(message, error_epoch), error_epoch, message


def render(kind: str, retry: float | None, error_epoch: float, message: str) -> str:
    flat = " ".join(message.split())[:MESSAGE_CHARS]
    retry_at = _local(retry) if retry else "-"
    return "\t".join([kind, retry_at, str(int(retry or 0)), _local(error_epoch), flat])


def cmd_last(args) -> int:
    with closing(_connect(args.codex_home)) as con:
        row = newest_turn_error(con, args.since)
    if not row:
        return 1
    print(render(*describe(row)))
    return 0


def cmd_blocking(args) -> int:
    now = args.now if args.now is not None else time.time()
    with closing(_connect(args.codex_home)) as con:
        row = newest_turn_error(con, now - args.lookback_hours * 3600)
        if not row:
            return 1
        kind, retry, error_epoch, message = describe(row)
        if kind != "quota-exhausted" or not retry or retry <= now:
            return 1
        if sampled_after(con, row[0], row[1]):
            return 1
    print(render(kind, retry, error_epoch, message))
    return 0


def cmd_classify(args) -> int:
    print(classify(args.text))
    return 0


def parse_args(argv):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    sub = p.add_subparsers(dest="command", required=True)
    last = sub.add_parser("last")
    last.add_argument("--codex-home", type=Path, required=True)
    last.add_argument("--since", type=float, required=True)
    block = sub.add_parser("blocking")
    block.add_argument("--codex-home", type=Path, required=True)
    block.add_argument("--now", type=float)
    block.add_argument("--lookback-hours", type=float, default=48)
    cls = sub.add_parser("classify")
    cls.add_argument("text")
    return p.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    handlers = {"last": cmd_last, "blocking": cmd_blocking, "classify": cmd_classify}
    try:
        return handlers[args.command](args)
    except sqlite3.Error as error:
        print(f"codex_turn_error: the Codex log could not be read: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
