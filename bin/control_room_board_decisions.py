#!/usr/bin/env python3
"""The board seam's decision verbs (Dev Plan B9, spec §3.7, §3.8, §7 decision 10).

Dave's decisions are the broker's, never a ledger event. This module is the screen side of that
fork: it checks a popup's decision against the card as it stands now (the move is offered in its
column, the brief or page hash is the one the popup rendered, the revision is current), maps each
popup verb onto one broker verb, and forwards. It signs nothing and writes nothing; board.py
derives the result from the stream the broker wrote.

`delete` takes no reason and is offered wherever the board offers it (everywhere but In Review).
`restore` is never a column move: it is taken on a deleted card, on the board or in the trash, and
the reactor moves a trashed card back. An approval carries the page text the seam read just now,
which the broker keeps beside the signature.
"""
from __future__ import annotations

import pathlib
from http import HTTPStatus
from typing import Any, Callable

import board
import control_room_board_page as page
from control_room_control import BrokerUnavailable

DECISION_MAP = {
    "approve_brief": "brief_approved", "return_brief": "brief_returned", "approve": "approved",
    "request_changes": "changes_requested", "reject": "rejected",
    "block": "blocked", "unblock": "unblocked", "delete": "deleted", "restore": "restored",
}
BRIEF_HASHED = ("approve_brief", "return_brief")
REASONED = ("return_brief", "request_changes", "reject")
REFUSAL_STATUS = {
    "bad_request": HTTPStatus.BAD_REQUEST, "reason_required": HTTPStatus.BAD_REQUEST,
    "unknown_action": HTTPStatus.BAD_REQUEST, "peer_denied": HTTPStatus.FORBIDDEN,
    "not_allowlisted": HTTPStatus.FORBIDDEN, "hash_mismatch": HTTPStatus.CONFLICT,
}
Exporter = Callable[[str], "dict[str, Any] | None"]


class Refused(Exception):
    def __init__(self, status: int, message: str) -> None:
        super().__init__(message)
        self.status, self.message = status, message


def _stale(what: str) -> Refused:
    return Refused(HTTPStatus.CONFLICT, f"stale: {what}; reload the card")


def _string(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Refused(HTTPStatus.BAD_REQUEST, f"{key} must be a non-empty string")
    return value


def _check_move(view: dict[str, Any], verb: str, body: dict[str, Any]) -> None:
    if verb not in view["moves"]:
        raise Refused(HTTPStatus.CONFLICT, f"{verb} is not offered in {view['column']}")
    rev = body.get("expect_rev")
    if rev is None:
        return
    if not isinstance(rev, int) or isinstance(rev, bool):
        raise Refused(HTTPStatus.BAD_REQUEST, "expect_rev must be the integer revision the popup rendered")
    if rev != view["rev"]:
        raise _stale(f"card revision {rev} is now {view['rev']}")


def _page_fields(card: str, body: dict[str, Any], export: Exporter) -> dict[str, str]:
    rendered = _string(body, "page_hash")
    try:
        exported = export(card)
    except page.ExportError as exc:
        raise Refused(HTTPStatus.SERVICE_UNAVAILABLE, f"page_unavailable: {exc}") from exc
    if not exported or not exported.get("text"):
        raise Refused(HTTPStatus.CONFLICT, "the card has no page to approve")
    if board.text_hash(exported["text"]) != rendered:
        raise _stale("the page changed since the popup rendered it")
    return {"page_hash": rendered, "text": exported["text"]}


def _check_restorable(root: pathlib.Path, card: str) -> None:
    if any(row["id"] == card for row in board.trash_list(root)):
        return
    view = board.collect(root, include_deleted=True).get(card)
    if view is None:
        raise Refused(HTTPStatus.NOT_FOUND, f"no such card: {card}")
    if not view["deleted"]:
        raise Refused(HTTPStatus.CONFLICT, f"{card} is not deleted; nothing to restore")


def broker_request(root: pathlib.Path, body: dict[str, Any], export: Exporter, card: str) -> dict[str, Any]:
    verb = body["verb"]
    if verb == "restore":
        _check_restorable(root, card)
        return {"v": 1, "board_verb": DECISION_MAP[verb], "card": card}
    view = board.view_of(root, card)
    _check_move(view, verb, body)
    request: dict[str, Any] = {"v": 1, "board_verb": DECISION_MAP[verb], "card": card}
    if verb in BRIEF_HASHED:
        request["brief_hash"] = _string(body, "brief_hash")
        if request["brief_hash"] != view["brief_hash"]:
            raise _stale("the brief changed since the popup rendered it")
    if verb in REASONED:
        request["reason"] = _string(body, "reason")
    elif verb == "block" and isinstance(body.get("reason"), str) and body["reason"].strip():
        request["reason"] = body["reason"]
    if verb == "approve":
        request.update(_page_fields(card, body, export))
    return request


def forward(broker: Any, request: dict[str, Any], actor: dict[str, Any]) -> None:
    if broker is None:
        raise Refused(HTTPStatus.SERVICE_UNAVAILABLE, "broker_unavailable: the board broker is not bound")
    try:
        response = broker.call({**request, "actor": actor})
    except BrokerUnavailable as exc:
        raise Refused(HTTPStatus.SERVICE_UNAVAILABLE, f"broker_unavailable: {exc}") from exc
    result = response.get("result")
    if result == "applied":
        return
    refusal = response.get("refusal") or {}
    if result == "refused":
        code = refusal.get("code", "refused")
        raise Refused(REFUSAL_STATUS.get(code, HTTPStatus.UNPROCESSABLE_ENTITY), f"{code}: {refusal.get('message')}")
    raise Refused(HTTPStatus.BAD_GATEWAY, f"broker failed: {response.get('note') or result}")
