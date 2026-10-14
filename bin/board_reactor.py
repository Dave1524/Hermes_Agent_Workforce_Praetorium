#!/usr/bin/env python3
"""The board reactor: a supervised daemon, and the same pass once for the reconcile timer.

    board_reactor.py            # board-reactor.service (Type=notify, WatchdogSec=60)
    board_reactor.py --once     # board-reconcile.service, every 5 min

Level-triggered: an inotify event, a due time or the 5-minute resync only wakes the loop; each
pass observes the whole board, plans with the pure board_plan.plan and applies the actions. A
pass runs under `$BOARD_ROOT/reactor/lock`, so the daemon and the reconcile never apply at once,
and its memory (per-card starts, backoff, the day's run count) is `reactor/state.json`, written
atomically. `reactor/heartbeat` is touched every pass.

Budget: at most `BOARD_REACTOR_MAX_RUNS` (2) run units at once and `BOARD_REACTOR_DAILY_CAP` (24)
starts per box-local day; `BOARD_REACTOR_COOLDOWN` (600 s) between runs of one card.

Errors: a `transient` start is retried with backoff and counts toward the card's start limit;
`poison` is the planner's `held` quarantine; `permanent` (systemctl unauthorised, a unit file
missing, the inotify watch limit) ends the daemon with exit 2 and the reason on stderr.

Receipts (workflow `board-reactor`): written only when the reactor's health flips — `ok`,
`transient`, `capped` or `permanent`, with its reason code. `--once` with the daemon down and
not paused from the Control Room receipts it `permanent daemon-dead`; with the daemon paused
(the latest applied broker action on `board-reactor` is a stop) it does nothing.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import pathlib
import signal
import subprocess
import sys
import time
from typing import Any, Callable, Iterator

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board  # noqa: E402
import board_plan  # noqa: E402
import board_source  # noqa: E402
import inotify_watch  # noqa: E402
import reactor_receipt  # noqa: E402
import sd_notify  # noqa: E402
from reactor_source import Budget, Outcome  # noqa: E402

UNIT = "board-reactor"
RESYNC = 300
BACKOFF_BASE, BACKOFF_MAX = 30, 900
SEVERITY = ("ok", "transient", "capped", "permanent")


class Permanent(Exception):
    def __init__(self, reason: str) -> None:
        super().__init__(reason)
        self.reason = reason


def env_int(name: str, default: int) -> int:
    value = os.environ.get(name, "").strip()
    return int(value) if value.isdigit() else default


def box_now() -> dt.datetime:
    return dt.datetime.now(board.box_tz())


def iso(moment: dt.datetime) -> str:
    return moment.astimezone(dt.timezone.utc).isoformat().replace("+00:00", "Z")


def next_midnight(now: dt.datetime) -> dt.datetime:
    local = now.astimezone(board.box_tz())
    return dt.datetime.combine(local.date() + dt.timedelta(days=1), dt.time(), board.box_tz())


def backoff(failures: int) -> int:
    return min(BACKOFF_BASE * 2 ** max(failures - 1, 0), BACKOFF_MAX)


# --- state ----------------------------------------------------------------------------------
class State:
    def __init__(self, directory: pathlib.Path) -> None:
        self.directory = directory
        self.path = directory / "state.json"
        self.data: dict[str, Any] = {"day": None, "count": 0, "cards": {}, "health": None}

    def load(self) -> "State":
        try:
            loaded = json.loads(self.path.read_text())
        except (OSError, ValueError):
            loaded = {}
        if isinstance(loaded, dict):
            self.data.update({k: v for k, v in loaded.items() if k in self.data})
        return self

    def save(self) -> None:
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.data, indent=1, sort_keys=True) + "\n")
        os.replace(temp, self.path)

    def runs_today(self, now: dt.datetime) -> int:
        today = now.astimezone(board.box_tz()).date().isoformat()
        if self.data["day"] != today:
            self.data["day"], self.data["count"] = today, 0
        return int(self.data["count"])


@contextlib.contextmanager
def locked(directory: pathlib.Path) -> Iterator[None]:
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "lock").open("a") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


# --- receipts -------------------------------------------------------------------------------
def write_receipt(health: str, reason: str | None, now: dt.datetime, detail: str) -> str:
    """Write the flip's receipt; a receipt never changes the reactor's course."""
    try:
        reactor_receipt.write(health, reason, now, board.receipt_root(), detail)
    except (OSError, ValueError) as exc:
        return f"receipt: errored {exc}"
    return f"receipt: written {health}"


def record_health(state: State, health: str, reason: str | None, now: dt.datetime, detail: str = "") -> str | None:
    current = {"class": health, "reason": reason}
    if state.data.get("health") == current:
        return None
    state.data["health"] = current
    return write_receipt(health, reason, now, detail)


# --- one pass -------------------------------------------------------------------------------
class Reactor:
    def __init__(self, root: pathlib.Path, receipt_root: pathlib.Path) -> None:
        self.root = root
        self.state_dir = root / "reactor"
        self.max_runs = env_int("BOARD_REACTOR_MAX_RUNS", 2)
        self.daily_cap = env_int("BOARD_REACTOR_DAILY_CAP", 24)
        self.config = board_plan.Config(cooldown=env_int("BOARD_REACTOR_COOLDOWN", 600), attempts=3)
        self.receipt_root = receipt_root

    def run_pass(self, now: dt.datetime, judge: bool = True,
                 tick: Callable[[], Any] = lambda: None) -> tuple[dt.datetime | None, list[str]]:
        """One observe/plan/apply; `judge=False` leaves the health verdict to the caller.

        `tick` runs after the observation and after each action: the daemon feeds the watchdog
        with it, since one pass can hold several 30 s systemctl calls.
        """
        with locked(self.state_dir):
            state = State(self.state_dir).load()
            try:
                return self._pass(state, now, judge, tick)
            finally:
                state.save()
                (self.state_dir / "heartbeat").write_text(iso(now) + "\n")

    def _pass(self, state: State, now: dt.datetime, judge: bool,
              tick: Callable[[], Any]) -> tuple[dt.datetime | None, list[str]]:
        source = board_source.BoardSource(self.root, self.receipt_root, self.config, state.data["cards"])
        try:
            observed = source.observe(now)
        except board_source.SourceError as exc:
            return self._fail(state, exc.outcome, now)
        tick()
        state.data["cards"] = {k: dict(v) for k, v in observed.memory.items()}
        busy = len(observed.active)
        budget = Budget(max(self.max_runs - busy, 0), max(self.daily_cap - state.runs_today(now), 0))
        plan = source.plan(observed, now, budget)
        worst, reason, lines = "ok", None, []
        for action in plan.actions:
            outcome = source.apply(action)
            lines.append(f"{action.verb} {action.item} {action.unit or ''} -> "
                         f"{'ok' if outcome.ok else outcome.error_class + ' ' + str(outcome.reason)}".strip())
            self._remember(state, action, outcome, now)
            tick()
            if outcome.error_class == "permanent":
                raise Permanent(str(outcome.reason))
            if outcome.error_class == "transient" and worst == "ok":
                worst, reason = "transient", outcome.reason
        if plan.capped:
            worst, reason = "capped", "daily-cap"
        wake = plan.wake_at
        if plan.capped:
            wake = min(t for t in (wake, next_midnight(now)) if t)
        if not judge:
            return wake, lines
        note = record_health(state, worst, reason, now, f"runs_today={state.data['count']}/{self.daily_cap}")
        return wake, lines + ([note] if note else [])

    def _remember(self, state: State, action: Any, outcome: Outcome, now: dt.datetime) -> None:
        if action.verb == "restore":
            self._remember_restore(state, str(action.item), outcome, now)
        if action.verb != "start":
            return
        entry = state.data["cards"].setdefault(str(action.item), {"starts": 0})
        entry["starts"] = int(entry.get("starts", 0)) + 1
        entry["last_start"] = iso(now)
        if outcome.ok:
            entry.pop("next_try", None)
            entry.pop("failures", None)
            state.data["count"] = int(state.data["count"]) + 1
            return
        entry["failures"] = int(entry.get("failures", 0)) + 1
        entry["next_try"] = iso(now + dt.timedelta(seconds=backoff(entry["failures"])))

    def _remember_restore(self, state: State, card_id: str, outcome: Outcome, now: dt.datetime) -> None:
        key = board_plan.trash_key(card_id)
        if outcome.ok:
            state.data["cards"].pop(key, None)
            return
        entry = state.data["cards"].setdefault(key, {})
        entry["failures"] = int(entry.get("failures", 0)) + 1
        entry["next_try"] = iso(now + dt.timedelta(seconds=backoff(entry["failures"])))

    def _fail(self, state: State, outcome: Outcome, now: dt.datetime) -> tuple[dt.datetime | None, list[str]]:
        if outcome.error_class == "permanent":
            raise Permanent(str(outcome.reason))
        note = record_health(state, "transient", outcome.reason, now)
        return now + dt.timedelta(seconds=BACKOFF_BASE), [f"observe -> transient {outcome.reason}"] + ([note] if note else [])

    def health(self) -> dict[str, Any] | None:
        return State(self.state_dir).load().data.get("health")

    def record_permanent(self, reason: str, now: dt.datetime) -> str | None:
        with locked(self.state_dir):
            state = State(self.state_dir).load()
            note = record_health(state, "permanent", reason, now)
            state.save()
            return note


# --- the reconcile's view of the daemon -----------------------------------------------------
def daemon_active() -> bool:
    try:
        done = board_source.run_systemctl("is-active", f"{UNIT}.service")
    except subprocess.TimeoutExpired:
        return False
    return done.stdout.strip() in ("active", "activating", "reloading")


def broker_receipts() -> pathlib.Path:
    return pathlib.Path(os.environ.get("BOARD_REACTOR_BROKER_RECEIPTS") or "/var/lib/control-room/receipts") / UNIT


def operator_paused() -> bool:
    """The latest applied broker action on the reactor is a stop: Dave paused it."""
    latest = None
    for path in broker_receipts().glob("*.json"):
        try:
            data = json.loads(path.read_text())
        except (OSError, ValueError):
            continue
        if data.get("result") != "applied" or data.get("action") not in ("start", "stop", "restart"):
            continue
        if latest is None or str(data.get("completed_at")) > str(latest.get("completed_at")):
            latest = data
    return bool(latest and latest["action"] == "stop")


def once(reactor: Reactor) -> int:
    now = box_now()
    if daemon_active():
        return report(reactor, now, "reconcile: daemon active", judge=False)
    if operator_paused():
        print("reconcile: paused from the Control Room; no pass")
        return 0
    known = reactor.health() or {}
    if known.get("class") == "permanent":
        print(f"reconcile: daemon down on its own permanent reason {known.get('reason')}")
    else:
        note = reactor.record_permanent("daemon-dead", now)
        print(f"reconcile: daemon down and not paused{'; ' + note if note else ''}")
    return report(reactor, now, "reconcile: pass for the daemon", judge=False)


def report(reactor: Reactor, now: dt.datetime, header: str, judge: bool) -> int:
    try:
        _wake, lines = reactor.run_pass(now, judge)
    except Permanent as exc:
        note = reactor.record_permanent(exc.reason, now)
        if note is None:
            print(f"{header}; still permanent {exc.reason}, already receipted and alerted")
            return 0
        print(f"{header}; permanent {exc.reason}; {note}", file=sys.stderr)
        return 2
    print("\n".join([header, *lines]))
    return 0


# --- the daemon -----------------------------------------------------------------------------
def timeout_until(wake: dt.datetime | None, now: dt.datetime) -> float:
    limit = float(RESYNC)
    if wake is not None:
        limit = min(limit, max((wake - now).total_seconds(), 0.0))
    return limit


def idle(watcher: inotify_watch.Watcher, wake: dt.datetime | None, ping_every: float | None) -> None:
    """Until a change, the wake or the resync; a watchdog timeout only pings, it never passes."""
    until = time.monotonic() + timeout_until(wake, box_now())
    while (left := until - time.monotonic()) > 0:
        if watcher.wait(min(left, ping_every) if ping_every else left):
            return
        sd_notify.ping()


def daemon(reactor: Reactor) -> int:
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    ping_every = sd_notify.watchdog_interval()
    source = board_source.BoardSource(reactor.root, reactor.receipt_root, reactor.config)
    try:
        with inotify_watch.Watcher() as watcher:
            watcher.sync(source.wake_paths())
            sd_notify.ready("watching the board")
            while True:
                now = box_now()
                sd_notify.ping()
                wake, lines = reactor.run_pass(now, tick=sd_notify.ping)
                for line in lines:
                    print(line, flush=True)
                watcher.sync(source.wake_paths())
                sd_notify.ping(f"pass at {iso(now)}; next wake {iso(wake) if wake else 'on change'}")
                idle(watcher, wake, ping_every)
    except inotify_watch.WatchLimit:
        return fail(reactor, "inotify-limit")
    except Permanent as exc:
        return fail(reactor, exc.reason)


def fail(reactor: Reactor, reason: str) -> int:
    note = reactor.record_permanent(reason, box_now())
    print(f"permanent: {reason}{'; ' + note if note else ''}", file=sys.stderr, flush=True)
    sd_notify.notify(f"STATUS=permanent: {reason}")
    return 2


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    p.add_argument("--once", action="store_true", help="one reconcile pass (board-reconcile.service)")
    args = p.parse_args(argv)
    reactor = Reactor(board.board_root(), board.receipt_root())
    return once(reactor) if args.once else daemon(reactor)


if __name__ == "__main__":
    sys.exit(main())
