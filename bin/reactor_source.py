#!/usr/bin/env python3
"""The interface every reactor source implements, and the values that cross it.

A source names itself, lists the paths whose change should wake the reactor, observes its full
state at the pass's own instant (level-triggered: an event only wakes the loop, it never carries the work), plans from that
state with a pure function, and applies one action at a time. The reactor owns the budget —
`slots` free run units and the runs left under today's cap — and shares it across sources.

Error classes (design/contracts/board-reactor.md): `transient` is retried with backoff,
`poison` quarantines the one item it names, `permanent` stops the reactor with a non-zero exit.
"""
from __future__ import annotations

import dataclasses
import datetime as dt
import pathlib
from typing import Any, Protocol

CLASSES = ("transient", "poison", "permanent")


@dataclasses.dataclass(frozen=True)
class Budget:
    slots: int
    remaining_today: int | None


@dataclasses.dataclass(frozen=True)
class Action:
    verb: str
    item: str | None = None
    unit: str | None = None
    reason: str | None = None


@dataclasses.dataclass(frozen=True)
class Plan:
    actions: tuple[Action, ...] = ()
    wake_at: dt.datetime | None = None
    capped: bool = False


@dataclasses.dataclass(frozen=True)
class Outcome:
    ok: bool
    error_class: str | None = None
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.ok != (self.error_class is None) or (self.error_class and self.error_class not in CLASSES):
            raise ValueError(f"bad outcome: ok={self.ok} class={self.error_class}")


OK = Outcome(True)


class Source(Protocol):
    name: str

    def wake_paths(self) -> list[pathlib.Path]: ...

    def observe(self, now: dt.datetime) -> Any: ...

    def plan(self, state: Any, now: dt.datetime, budget: Budget) -> Plan: ...

    def apply(self, action: Action) -> Outcome: ...
