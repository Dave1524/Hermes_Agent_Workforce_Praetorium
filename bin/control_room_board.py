#!/usr/bin/env python3
"""The Control Room's board reads (Dev Plan B4, spec §3.4, §3.6.9, §3.8).

Reads only. Every column, field rule and move comes from bin/board.py's derivation, which is the
one owner of them; this module joins it to the ledger's text and to the card's Notion page and
reshapes the result for the SPA. It writes nothing and keeps no copy of the editable-fields or
moves tables. The write seam is B5's and lives elsewhere.

Item vocabulary: camelCase keys; `fields`, `editable` and `locked` keep the ledger's own snake
names (research_on, ...) because they are the names a save is made in.
"""
from __future__ import annotations

import datetime as dt
import pathlib
from typing import Any, Callable

import board
import control_room_board_page as page

COLUMNS = list(board.COLUMNS)


class BoardReads:
    def __init__(self, clock: Callable[[], dt.datetime], export: page.Exporter | None = None,
                 root: pathlib.Path | None = None) -> None:
        self.clock = clock
        self.export = export or page.export_page
        self.root = root

    def _root(self) -> pathlib.Path:
        return self.root or board.board_root()

    def _views(self) -> dict[str, dict[str, Any]]:
        return board.collect(self._root(), self.clock())

    def cards(self) -> tuple[dict[str, Any], dict[str, Any]]:
        try:
            views = sorted(self._views().values(), key=lambda v: (COLUMNS.index(v["column"]), board._order_key(v)))
        except (board.BoardError, OSError, ValueError, KeyError) as exc:
            return {"columns": COLUMNS, "cards": []}, _status("unavailable", str(exc))
        return {"columns": COLUMNS, "cards": [summary(v) for v in views]}, _status("available")

    def card(self, card_id: str) -> tuple[dict[str, Any] | None, dict[str, Any]]:
        try:
            view = self._views().get(card_id)
            if view is None:
                return None, _status("available")
            return self._detail(view), _status("available")
        except (board.BoardError, OSError, ValueError, KeyError) as exc:
            return None, _status("unavailable", str(exc))

    def decisions(self) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        try:
            return board.unapplied(self._views(), board.read_decisions()), _status("available")
        except (board.BoardError, OSError, ValueError, KeyError) as exc:
            return [], _status("unavailable", str(exc))

    def _detail(self, view: dict[str, Any]) -> dict[str, Any]:
        root, card_id = self._root(), view["id"]
        _, events = board.read_card(root, card_id)
        decisions = [d for d in board.read_decisions() if d.get("card") == card_id]
        return {
            **summary(view),
            "fields": view["fields"], "rev": view["rev"], "editable": view["editable"],
            "moves": view["moves"], "locked": view["locked"],
            "brief": brief_block(root, view, events, decisions),
            "runs": [run_block(r) for r in view["runs"]],
            "activity": activity(events, decisions, view["runs"]),
            "research": self._research(view, brief_text_of(root, card_id, events)),
        }

    def _research(self, view: dict[str, Any], brief_text: str | None) -> dict[str, Any]:
        if not any(r["page"] for r in view["runs"]):
            return {"status": "none"}
        try:
            exported = self.export(view["id"])
        except page.ExportError as exc:
            return {"status": "unavailable", "reason": str(exc)}
        if exported is None:
            return {"status": "none"}
        published = exported.get("published_hash")
        return {"status": "available", "url": exported.get("url"), "text": exported["text"],
                "pageHash": exported.get("page_hash"), "publishedHash": published,
                "changed": None if not published else published != exported.get("page_hash"),
                "acceptance": page.acceptance(brief_text, exported["text"])}


def _status(state: str, error: str | None = None) -> dict[str, Any]:
    return {"board": state, "errors": {"board": [error] if error else []}}


def summary(view: dict[str, Any]) -> dict[str, Any]:
    fields = view["fields"]
    return {
        "id": view["id"], "title": fields["title"], "column": view["column"], "scheduled": view["scheduled"],
        "outcome": view["outcome"], "blockedCause": view["blocked_cause"],
        "approvedLanding": view["approved_landing"], "owner": view["owner"], "kind": view["kind"],
        "priority": fields["priority"], "tags": fields["tags"], "deadline": fields.get("deadline"),
        "researchOn": fields.get("research_on"), "briefVersion": view["brief_version"],
        "exceptions": [e["kind"] for e in view["exceptions"]],
    }


def run_block(run: dict[str, Any]) -> dict[str, Any]:
    return {"runId": run["run_id"], "workflow": run["workflow"], "ts": run["ts"], "purpose": run["purpose"],
            "outcome": run["outcome"], "page": run["page"], "void": run["void"]}


def briefs_of(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in board._ordered(events) if e.get("event") == "brief"]


def brief_text_of(root: pathlib.Path, card_id: str, events: list[dict[str, Any]]) -> str | None:
    briefs = briefs_of(events)
    if not briefs:
        return None
    path = board.card_dir(root, card_id) / "briefs" / f"{briefs[-1]['hash']}.md"
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def brief_block(root: pathlib.Path, view: dict[str, Any], events: list[dict[str, Any]],
                decisions: list[dict[str, Any]]) -> dict[str, Any] | None:
    briefs = briefs_of(events)
    if not briefs:
        return None
    last = briefs[-1]
    approvals = [d for d in decisions if d["decision"] == "brief_approved" and d.get("brief_hash") == last["hash"]]
    return {"text": brief_text_of(root, view["id"], events), "hash": last["hash"], "version": len(briefs),
            "by": last["actor"], "ts": last.get("ts"), "approved": view["brief_approved"],
            "approvedAt": board._latest(approvals)["ts"] if view["brief_approved"] and approvals else None,
            "current": view["brief_hash"] == last["hash"]}


def activity(events: list[dict[str, Any]], decisions: list[dict[str, Any]],
             runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    outcomes = {r["run_id"]: r for r in runs}
    rows, version = [], 0
    for event in board._ordered(events):
        kind, fields = event["event"], event.get("fields") or {}
        row = {"ts": event.get("ts"), "kind": kind, "actor": event["actor"], "runId": event.get("run_id"),
               "detail": None, "outcome": None}
        if kind == "brief":
            version += 1
            row["detail"] = f"v{version}"
        elif kind == "note":
            row["detail"] = fields.get("text")
        elif kind == "edited":
            row["detail"] = ", ".join(sorted(fields))
        elif kind == "picked":
            run = outcomes.get(event.get("run_id")) or {}
            row["detail"], row["outcome"] = fields.get("purpose", "research"), run.get("outcome")
        rows.append(row)
    rows += [{"ts": d.get("ts"), "kind": d["decision"], "actor": "dave", "runId": None,
              "detail": d.get("reason"), "outcome": None} for d in decisions]
    order = sorted(enumerate(rows), key=lambda pair: (board._t(pair[1]["ts"]), pair[0]), reverse=True)
    return [row for _, row in order]
