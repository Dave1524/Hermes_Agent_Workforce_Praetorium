#!/usr/bin/env python3
"""The board source's plan: what to start, stop, hold, trash, restore and purge, from state alone.

Pure: no clock, no disk, no systemd. The reactor and the reconcile both call it on the views
board.py derives, the run units systemd reports active, and the reactor's own per-card memory.
A card is started only when it wants a run, none of its units is active, its cooldown has run
out and no transient backoff is pending; three void runs (the ledger's failed streak) or three
starts that never reached a pick quarantine it with a `held` reason instead; an unblock clears
both counts. A refused restore backs off like a refused start. Deletion stops a
running card before it is trashed. Starts spend the budget in board order; nothing else does.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import os
import sys
from typing import Any, Mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from reactor_source import Action, Budget, Plan  # noqa: E402

UNITS = {"brief": "board-brief", "research": "board-work"}
PRIORITIES = ("high", "normal", "low")
SLOT_RECHECK = 30


@dataclasses.dataclass(frozen=True)
class Config:
    cooldown: int = 600
    attempts: int = 3


@dataclasses.dataclass(frozen=True)
class BoardState:
    views: Mapping[str, Mapping[str, Any]]
    active: frozenset[str] = frozenset()
    memory: Mapping[str, Mapping[str, Any]] = dataclasses.field(default_factory=dict)
    trash: Mapping[str, Mapping[str, Any]] = dataclasses.field(default_factory=dict)
    trash_list: tuple[Mapping[str, Any], ...] = ()


def unit_for(wants: str, card_id: str) -> str:
    return f"{UNITS[wants]}@{card_id}.service"


def card_units(card_id: str) -> list[str]:
    return [f"{prefix}@{card_id}.service" for prefix in UNITS.values()]


def parse(value: Any) -> dt.datetime | None:
    if not value:
        return None
    return dt.datetime.fromisoformat(str(value).replace("Z", "+00:00"))


def last_pick(view: Mapping[str, Any]) -> dt.datetime | None:
    runs = view.get("runs") or []
    return parse(runs[-1].get("ts")) if runs else None


def trash_key(card_id: str) -> str:
    return f"trash:{card_id}"


def settle(memory: Mapping[str, Mapping[str, Any]], views: Mapping[str, Mapping[str, Any]],
           trashed: frozenset[str] = frozenset()) -> dict[str, dict[str, Any]]:
    """Memory after observation: a pick or an unblock newer than the last start clears the count."""
    settled = {}
    for key, entry in memory.items():
        if key in views:
            settled[key] = _settled_starts(dict(entry), views[key])
        elif key.startswith("trash:") and key.removeprefix("trash:") in trashed:
            settled[key] = dict(entry)
    return settled


def _settled_starts(entry: dict[str, Any], view: Mapping[str, Any]) -> dict[str, Any]:
    started = parse(entry.get("last_start"))
    cleared = [t for t in (last_pick(view), parse(view.get("unblocked_at"))) if t]
    if started and cleared and max(cleared) >= started:
        entry["starts"] = 0
    return entry


def order_key(view: Mapping[str, Any]) -> tuple[Any, ...]:
    fields = view.get("fields") or {}
    priority = fields.get("priority") if fields.get("priority") in PRIORITIES else "normal"
    return (PRIORITIES.index(priority), fields.get("deadline") or "9999-12-31", view["id"])


def _deleted(card_id: str, active: frozenset[str]) -> list[Action]:
    running = [unit for unit in card_units(card_id) if unit in active]
    if running:
        return [Action("stop", card_id, unit, "deleted") for unit in running]
    return [Action("trash", card_id, None, "deleted")]


def _quarantine(view: Mapping[str, Any], entry: Mapping[str, Any], config: Config) -> str | None:
    if view.get("failed_streak", 0) >= config.attempts:
        return "poison-attempts"
    if entry.get("starts", 0) >= config.attempts:
        return "poison-start"
    return None


def _ready_at(view: Mapping[str, Any], entry: Mapping[str, Any], config: Config) -> dt.datetime | None:
    stamps = [t for t in (last_pick(view), parse(entry.get("last_start"))) if t]
    cooled = max(stamps) + dt.timedelta(seconds=config.cooldown) if stamps else None
    backoff = parse(entry.get("next_try"))
    return max((t for t in (cooled, backoff) if t), default=None)


class _Planner:
    def __init__(self, state: BoardState, now: dt.datetime, config: Config) -> None:
        self.state, self.now, self.config = state, now, config
        self.actions: list[Action] = []
        self.queue: list[Action] = []
        self.wakes: list[dt.datetime] = []

    def card(self, view: Mapping[str, Any]) -> None:
        card_id = view["id"]
        if view.get("deleted"):
            self.actions += _deleted(card_id, self.state.active)
            return
        if view.get("scheduled") and view.get("due_at"):
            self.wakes.append(parse(view["due_at"]))
        wants = view.get("wants")
        if wants not in UNITS or any(u in self.state.active for u in card_units(card_id)):
            return
        self.wanted(view, wants)

    def wanted(self, view: Mapping[str, Any], wants: str) -> None:
        entry = self.state.memory.get(view["id"], {})
        reason = _quarantine(view, entry, self.config)
        if reason:
            self.actions.append(Action("hold", view["id"], None, reason))
            return
        ready = _ready_at(view, entry, self.config)
        if ready and self.now < ready:
            self.wakes.append(ready)
            return
        self.queue.append(Action("start", view["id"], unit_for(wants, view["id"]), wants))

    def trash(self) -> None:
        for card_id, view in sorted(self.state.trash.items()):
            if not view.get("deleted"):
                self.restore(card_id)
        for row in self.state.trash_list:
            expires = parse(row.get("purge_after"))
            if expires and expires <= self.now and self.state.trash.get(row["id"], {}).get("deleted", True):
                self.actions.append(Action("purge", row["id"], None, "expired"))

    def restore(self, card_id: str) -> None:
        backoff = parse(self.state.memory.get(trash_key(card_id), {}).get("next_try"))
        if backoff and self.now < backoff:
            self.wakes.append(backoff)
            return
        self.actions.append(Action("restore", card_id, None, "restored"))

    def spend(self, budget: Budget) -> bool:
        room = budget.slots if budget.remaining_today is None else min(budget.slots, budget.remaining_today)
        room = max(room, 0)
        capped = budget.remaining_today is not None and len(self.queue) > budget.remaining_today
        if len(self.queue) > room and budget.slots <= room:
            self.wakes.append(self.now + dt.timedelta(seconds=SLOT_RECHECK))
        self.actions += self.queue[:room]
        return capped


def plan(state: BoardState, now: dt.datetime, budget: Budget, config: Config = Config()) -> Plan:
    planner = _Planner(state, now, config)
    for view in sorted(state.views.values(), key=order_key):
        planner.card(view)
    planner.trash()
    capped = planner.spend(budget)
    return Plan(tuple(planner.actions), min(planner.wakes, default=None), capped)
