#!/usr/bin/env python3
"""The board as a reactor source: observe the ledger and systemd, apply one action at a time.

The run units are system units (`board-brief@<id>.service`, `board-work@<id>.service`); the
reactor runs as dave and reaches them through the polkit rule the runbook installs. Starts and
stops are `--no-block`: the run's own receipt says how it ended, and a slot frees when the
receipt lands in a watched directory. systemctl failures are classed by what they say:
authorisation and a missing unit file never clear on retry (`permanent`), anything else is
`transient`. `$BOARD_SYSTEMCTL` replaces the binary for tests.
"""
from __future__ import annotations

import datetime as dt
import os
import pathlib
import subprocess
import sys
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import board  # noqa: E402
import board_plan  # noqa: E402
from reactor_source import OK, Action, Budget, Outcome, Plan  # noqa: E402

UNIT_PATTERNS = tuple(f"{prefix}@*.service" for prefix in board_plan.UNITS.values())
BUSY_STATES = {"active", "activating", "deactivating", "reloading"}
SYSTEMCTL_TIMEOUT = 30
PERMANENT_MARKERS = {
    "polkit-denied": ("access denied", "interactive authentication required", "not authorized"),
    "unit-missing": ("not found", "no such file", "does not exist"),
}


def systemctl() -> list[str]:
    return os.environ.get("BOARD_SYSTEMCTL", "systemctl").split()


def run_systemctl(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*systemctl(), *args], capture_output=True, text=True, timeout=SYSTEMCTL_TIMEOUT)


def classify(done: subprocess.CompletedProcess[str]) -> Outcome:
    if done.returncode == 0:
        return OK
    said = (done.stderr or done.stdout or "").lower()
    for reason, markers in PERMANENT_MARKERS.items():
        if any(marker in said for marker in markers):
            return Outcome(False, "permanent", reason)
    return Outcome(False, "transient", "systemctl-failed")


def active_units() -> frozenset[str]:
    done = run_systemctl("list-units", "--all", "--plain", "--no-legend", *UNIT_PATTERNS)
    outcome = classify(done)
    if not outcome.ok:
        raise SourceError(outcome)
    busy = set()
    for line in done.stdout.splitlines():
        cols = line.split()
        if len(cols) >= 3 and cols[2] in BUSY_STATES:
            busy.add(cols[0])
    return frozenset(busy)


class SourceError(Exception):
    def __init__(self, outcome: Outcome) -> None:
        super().__init__(f"{outcome.error_class}: {outcome.reason}")
        self.outcome = outcome


class BoardSource:
    name = "board"

    def __init__(self, root: pathlib.Path, receipt_root: pathlib.Path, config: board_plan.Config,
                 memory: dict[str, dict[str, Any]] | None = None) -> None:
        self.root, self.receipt_root, self.config = root, receipt_root, config
        self.memory = memory if memory is not None else {}

    def wake_paths(self) -> list[pathlib.Path]:
        cards = self.root / "cards"
        dirs = [self.root, cards, board.trash_root(self.root), board.decisions_file().parent]
        dirs += [self.receipt_root / prefix for prefix in board_plan.UNITS.values()]
        dirs += sorted(p for p in cards.iterdir() if p.is_dir()) if cards.is_dir() else []
        return dirs

    def observe(self, now: dt.datetime) -> board_plan.BoardState:
        """The ledger at `now`, without the canonical-main join the planner never reads."""
        try:
            decisions = board.read_decisions()
            views = board.collect(self.root, now, include_deleted=True, join_main=False, decisions=decisions)
            trash = board.trash_views(self.root, now, decisions)
            trash_list = tuple(board.trash_list(self.root, decisions))
        except (board.BoardError, OSError, ValueError) as exc:
            raise SourceError(Outcome(False, "transient", "ledger-unreadable")) from exc
        return board_plan.BoardState(views=views, active=active_units(),
                                     memory=board_plan.settle(self.memory, views, frozenset(trash)),
                                     trash=trash, trash_list=trash_list)

    def plan(self, state: board_plan.BoardState, now: dt.datetime, budget: Budget) -> Plan:
        return board_plan.plan(state, now, budget, self.config)

    def apply(self, action: Action) -> Outcome:
        try:
            return getattr(self, f"_{action.verb}")(action)
        except subprocess.TimeoutExpired:
            return Outcome(False, "transient", "systemctl-timeout")
        except board.BoardError as exc:
            return Outcome(False, "transient", _reason_of(exc))

    def _start(self, action: Action) -> Outcome:
        return classify(run_systemctl("start", "--no-block", str(action.unit)))

    def _stop(self, action: Action) -> Outcome:
        return classify(run_systemctl("stop", "--no-block", str(action.unit)))

    def _hold(self, action: Action) -> Outcome:
        board.hold_card(self.root, str(action.item), str(action.reason), "reactor")
        return OK

    def _trash(self, action: Action) -> Outcome:
        board.trash_card(self.root, str(action.item))
        return OK

    def _restore(self, action: Action) -> Outcome:
        board.restore_card(self.root, str(action.item))
        return OK

    def _purge(self, action: Action) -> Outcome:
        board.purge_card(self.root, str(action.item), dt.datetime.now().astimezone())
        return OK


def _reason_of(exc: board.BoardError) -> str:
    text = str(exc).lower()
    return "trash-conflict" if "trash" in text or "restore refused" in text else "ledger-refused"
