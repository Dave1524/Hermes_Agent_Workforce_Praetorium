#!/usr/bin/env python3
"""bin/board_plan.py: the board source's pure plan, one table row per trigger and class.

The views are board.derive's shape, cut to the keys plan() reads; the questions rows derive a
real view from a synthetic ledger so the loop is tested through the function that owns it.
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "bin"))


def load(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / "bin" / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


board = load("board")
source = load("reactor_source")
board_plan = load("board_plan")

UTC = dt.timezone.utc
NOW = dt.datetime(2026, 10, 14, 10, 0, tzinfo=UTC)
FREE = source.Budget(slots=2, remaining_today=None)
CONFIG = board_plan.Config(cooldown=600, attempts=3)


def iso(moment: dt.datetime) -> str:
    return moment.isoformat().replace("+00:00", "Z")


def view(card_id="alpha", column="Backlog", wants="brief", **extra):
    base = {"id": card_id, "column": column, "wants": wants, "deleted": False, "scheduled": False,
            "due_at": None, "failed_streak": 0, "runs": [], "awaiting_answer": False,
            "fields": {"priority": "normal", "deadline": None}}
    base.update(extra)
    return base


def state(*views, active=(), memory=None, trash=None, trash_list=()):
    return board_plan.BoardState(views={v["id"]: v for v in views}, active=frozenset(active),
                                 memory=memory or {}, trash=trash or {}, trash_list=tuple(trash_list))


def plan(st, now=NOW, budget=FREE):
    return board_plan.plan(st, now, budget, CONFIG)


def verbs(result):
    return [(a.verb, a.item, a.unit, a.reason) for a in result.actions]


class Triggers(unittest.TestCase):
    def test_a_card_that_wants_a_brief_starts_its_brief_unit(self):
        self.assertEqual(verbs(plan(state(view()))), [("start", "alpha", "board-brief@alpha.service", "brief")])

    def test_an_approved_card_starts_its_work_unit(self):
        got = verbs(plan(state(view(column="Todo", wants="research"))))
        self.assertEqual(got, [("start", "alpha", "board-work@alpha.service", "research")])

    def test_nothing_wanted_is_nothing_planned(self):
        for column in ("Refine", "In Progress", "In Review", "Done", "Blocked"):
            with self.subTest(column):
                self.assertEqual(plan(state(view(column=column, wants=None))).actions, ())

    def test_a_scheduled_card_waits_and_sets_the_wake_to_its_minute(self):
        due = NOW + dt.timedelta(minutes=1)
        result = plan(state(view(column="Todo", wants=None, scheduled=True, due_at=due.isoformat())))
        self.assertEqual(result.actions, ())
        self.assertEqual(result.wake_at, due)

    def test_the_wake_is_the_earliest_due_time(self):
        soon, late = NOW + dt.timedelta(minutes=5), NOW + dt.timedelta(hours=3)
        result = plan(state(view("a", "Todo", None, scheduled=True, due_at=late.isoformat()),
                            view("b", "Todo", None, scheduled=True, due_at=soon.isoformat())))
        self.assertEqual(result.wake_at, soon)

    def test_a_card_whose_unit_is_running_is_not_started_again(self):
        for unit in ("board-brief@alpha.service", "board-work@alpha.service"):
            with self.subTest(unit):
                self.assertEqual(plan(state(view(), active=[unit])).actions, ())


class Budgeting(unittest.TestCase):
    def cards(self, n):
        return [view(f"c{i}") for i in range(n)]

    def test_at_most_the_free_slots_start(self):
        result = plan(state(*self.cards(5)), budget=source.Budget(slots=2, remaining_today=None))
        self.assertEqual([a.item for a in result.actions], ["c0", "c1"])

    def test_no_free_slot_starts_nothing_and_rechecks(self):
        result = plan(state(*self.cards(1)), budget=source.Budget(slots=0, remaining_today=None))
        self.assertEqual(result.actions, ())
        self.assertEqual(result.wake_at, NOW + dt.timedelta(seconds=board_plan.SLOT_RECHECK))

    def test_the_cap_edge_starts_exactly_what_is_left(self):
        result = plan(state(*self.cards(3)), budget=source.Budget(slots=5, remaining_today=1))
        self.assertEqual([a.item for a in result.actions], ["c0"])
        self.assertTrue(result.capped)

    def test_at_the_cap_nothing_starts_and_the_plan_says_capped(self):
        result = plan(state(*self.cards(1)), budget=source.Budget(slots=2, remaining_today=0))
        self.assertEqual(result.actions, ())
        self.assertTrue(result.capped)

    def test_under_the_cap_with_room_is_not_capped(self):
        self.assertFalse(plan(state(*self.cards(2)), budget=source.Budget(slots=2, remaining_today=2)).capped)

    def test_order_is_priority_then_deadline_then_id(self):
        cards = [view("b", fields={"priority": "normal", "deadline": None}),
                 view("a", fields={"priority": "low", "deadline": None}),
                 view("c", fields={"priority": "high", "deadline": None}),
                 view("d", fields={"priority": "normal", "deadline": "2026-10-20"})]
        result = plan(state(*cards), budget=source.Budget(slots=9, remaining_today=None))
        self.assertEqual([a.item for a in result.actions], ["c", "d", "b", "a"])

    def test_holds_and_stops_spend_no_budget(self):
        result = plan(state(view("x", failed_streak=3), view("y", deleted=True, wants=None),
                            active=["board-brief@y.service"]),
                      budget=source.Budget(slots=0, remaining_today=0))
        self.assertEqual(sorted(a.verb for a in result.actions), ["hold", "stop"])


class LoopProtection(unittest.TestCase):
    def test_cooldown_from_the_last_pick(self):
        picked = NOW - dt.timedelta(minutes=4)
        result = plan(state(view(runs=[{"ts": iso(picked)}])))
        self.assertEqual(result.actions, ())
        self.assertEqual(result.wake_at, picked + dt.timedelta(seconds=600))

    def test_cooldown_from_the_reactors_own_last_start(self):
        started = NOW - dt.timedelta(minutes=9, seconds=59)
        result = plan(state(view(), memory={"alpha": {"last_start": iso(started), "starts": 1}}))
        self.assertEqual(result.actions, ())

    def test_cooldown_over_to_the_second(self):
        started = NOW - dt.timedelta(minutes=10)
        result = plan(state(view(), memory={"alpha": {"last_start": iso(started), "starts": 1}}))
        self.assertEqual([a.verb for a in result.actions], ["start"])

    def test_three_failed_runs_quarantine_the_card(self):
        self.assertEqual(verbs(plan(state(view(failed_streak=3)))),
                         [("hold", "alpha", None, "poison-attempts")])

    def test_two_failed_runs_still_retry(self):
        self.assertEqual([a.verb for a in plan(state(view(failed_streak=2))).actions], ["start"])

    def test_three_starts_that_never_picked_quarantine_the_card(self):
        old = iso(NOW - dt.timedelta(hours=1))
        result = plan(state(view(), memory={"alpha": {"last_start": old, "starts": 3}}))
        self.assertEqual(verbs(result), [("hold", "alpha", None, "poison-start")])

    def test_a_transient_backoff_is_honoured(self):
        later = NOW + dt.timedelta(seconds=30)
        result = plan(state(view(), memory={"alpha": {"next_try": iso(later), "starts": 0}}))
        self.assertEqual(result.actions, ())
        self.assertEqual(result.wake_at, later)

    def test_a_blocked_card_is_never_held_again(self):
        self.assertEqual(plan(state(view(column="Blocked", wants=None, failed_streak=3))).actions, ())


class Settle(unittest.TestCase):
    def test_a_pick_after_the_last_start_resets_the_start_count(self):
        started = NOW - dt.timedelta(minutes=30)
        memory = {"alpha": {"last_start": iso(started), "starts": 2}}
        views = {"alpha": view(runs=[{"ts": iso(started + dt.timedelta(seconds=3))}])}
        self.assertEqual(board_plan.settle(memory, views)["alpha"]["starts"], 0)

    def test_no_pick_since_keeps_the_count(self):
        started = NOW - dt.timedelta(minutes=30)
        memory = {"alpha": {"last_start": iso(started), "starts": 2}}
        views = {"alpha": view(runs=[{"ts": iso(started - dt.timedelta(hours=1))}])}
        self.assertEqual(board_plan.settle(memory, views)["alpha"]["starts"], 2)

    def test_memory_of_a_card_gone_from_the_board_is_dropped(self):
        self.assertEqual(board_plan.settle({"gone": {"starts": 1}}, {}), {})

    def test_an_unblock_after_the_last_start_resets_the_start_count(self):
        started = NOW - dt.timedelta(minutes=30)
        memory = {"alpha": {"last_start": iso(started), "starts": 3}}
        views = {"alpha": view(unblocked_at=iso(started + dt.timedelta(minutes=5)))}
        self.assertEqual(board_plan.settle(memory, views)["alpha"]["starts"], 0)
        self.assertEqual(plan(state(views["alpha"], memory=board_plan.settle(memory, views))).actions[0].verb,
                         "start")

    def test_an_unblock_before_the_last_start_keeps_the_count(self):
        started = NOW - dt.timedelta(minutes=30)
        memory = {"alpha": {"last_start": iso(started), "starts": 3}}
        views = {"alpha": view(unblocked_at=iso(started - dt.timedelta(minutes=5)))}
        self.assertEqual(board_plan.settle(memory, views)["alpha"]["starts"], 3)

    def test_a_trashed_card_s_restore_memory_is_kept(self):
        memory = {"trash:alpha": {"failures": 1}, "trash:gone": {"failures": 1}}
        settled = board_plan.settle(memory, {}, frozenset({"alpha"}))
        self.assertEqual(settled, {"trash:alpha": {"failures": 1}})


class DeleteRestorePurge(unittest.TestCase):
    def test_a_deleted_card_with_a_run_is_stopped_first(self):
        result = plan(state(view(deleted=True, wants=None), active=["board-work@alpha.service"]))
        self.assertEqual(verbs(result), [("stop", "alpha", "board-work@alpha.service", "deleted")])

    def test_a_deleted_idle_card_moves_to_the_trash(self):
        self.assertEqual(verbs(plan(state(view(deleted=True, wants=None)))), [("trash", "alpha", None, "deleted")])

    def test_a_restored_card_in_the_trash_comes_back(self):
        result = plan(state(trash={"alpha": view(deleted=False, wants=None)}))
        self.assertEqual(verbs(result), [("restore", "alpha", None, "restored")])

    def test_a_refused_restore_backs_off(self):
        later = NOW + dt.timedelta(seconds=30)
        result = plan(state(trash={"alpha": view(deleted=False, wants=None)},
                            memory={"trash:alpha": {"next_try": iso(later), "failures": 1}}))
        self.assertEqual(result.actions, ())
        self.assertEqual(result.wake_at, later)

    def test_a_still_deleted_card_in_the_trash_stays(self):
        self.assertEqual(plan(state(trash={"alpha": view(deleted=True, wants=None)})).actions, ())

    def test_trash_past_its_window_is_purged(self):
        due = [{"id": "old", "purge_after": iso(NOW - dt.timedelta(seconds=1))},
               {"id": "kept", "purge_after": None},
               {"id": "new", "purge_after": iso(NOW + dt.timedelta(days=1))}]
        trash = {"old": view("old", deleted=True, wants=None), "new": view("new", deleted=True, wants=None)}
        self.assertEqual(verbs(plan(state(trash=trash, trash_list=due))), [("purge", "old", None, "expired")])


class Questions(unittest.TestCase):
    """The D7 loop, through board.derive on a synthetic ledger."""

    T0 = dt.datetime(2026, 10, 14, 8, 0, tzinfo=UTC)

    def ledger(self, *rows):
        events = [{"event": "created", "actor": "dave", "ts": iso(self.T0)},
                  {"event": "brief", "actor": "dave", "ts": iso(self.T0), "hash": "h1"}]
        for minutes, event, actor, kind, run_id in rows:
            row = {"event": event, "actor": actor, "ts": iso(self.T0 + dt.timedelta(minutes=minutes))}
            if kind:
                row["fields"] = {"kind": kind} if event == "note" else {"purpose": kind}
            if run_id:
                row.update(run_id=run_id, workflow="board-brief")
            events.append(row)
        return events

    def derived(self, events, receipts=None):
        card = {"id": "alpha", "owner": "claudius", "kind": "research", "title": "alpha",
                "priority": "normal"}
        return board.derive(card, events, [], receipts or {}, {}, NOW)

    def test_questions_posted_wait_for_dave(self):
        events = self.ledger((1, "picked", "run:r1", "brief", "r1"), (5, "note", "run:r1", "questions", None))
        v = self.derived(events, {"r1": {"terminal": {"outcome": "artifact"}}})
        self.assertTrue(v["awaiting_answer"])
        self.assertEqual(plan(state(v)).actions, ())

    def test_daves_answer_wakes_the_brief_run(self):
        events = self.ledger((1, "picked", "run:r1", "brief", "r1"), (5, "note", "run:r1", "questions", None),
                             (30, "note", "dave", "answer", None))
        v = self.derived(events, {"r1": {"terminal": {"outcome": "artifact"}}})
        self.assertEqual([a.unit for a in plan(state(v)).actions], ["board-brief@alpha.service"])

    def test_the_round_count_reaches_the_view(self):
        events = self.ledger((1, "picked", "run:r1", "brief", "r1"), (5, "note", "run:r1", "questions", None),
                             (30, "note", "dave", "answer", None), (41, "picked", "run:r2", "brief", "r2"),
                             (45, "note", "run:r2", "questions", None), (60, "note", "dave", "answer", None))
        receipts = {r: {"terminal": {"outcome": "artifact"}} for r in ("r1", "r2")}
        v = self.derived(events, receipts)
        self.assertEqual(v["question_rounds"], board.QUESTION_ROUNDS)
        self.assertEqual(v["wants"], "brief")


class TwoStrike(unittest.TestCase):
    def test_two_declines_block_through_derive_and_plan_leaves_it(self):
        t0 = dt.datetime(2026, 10, 14, 8, 0, tzinfo=UTC)
        events = [{"event": "created", "actor": "dave", "ts": iso(t0)},
                  {"event": "brief", "actor": "dave", "ts": iso(t0), "hash": "h1"}]
        for i, run in enumerate(("r1", "r2")):
            events.append({"event": "picked", "actor": f"run:{run}", "run_id": run, "workflow": "board-work",
                           "ts": iso(t0 + dt.timedelta(minutes=10 * (i + 1))), "fields": {"purpose": "research"}})
        decisions = [{"decision": "brief_approved", "card": "alpha", "brief_hash": "h1", "ts": iso(t0 + dt.timedelta(minutes=5))}]
        receipts = {r: {"terminal": {"outcome": "decline"}} for r in ("r1", "r2")}
        card = {"id": "alpha", "owner": "claudius", "kind": "research", "title": "alpha", "priority": "normal"}
        v = board.derive(card, events, decisions, receipts, {}, NOW)
        self.assertEqual((v["column"], v["blocked_cause"]), ("Blocked", "declined twice"))
        self.assertEqual(plan(state(v)).actions, ())


if __name__ == "__main__":
    unittest.main()
