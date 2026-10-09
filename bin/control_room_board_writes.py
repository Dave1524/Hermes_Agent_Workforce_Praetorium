#!/usr/bin/env python3
"""The Control Room's board seam (Dev Plan B5): shape check, peer gate, the verb table and the
HTTP status map over bin/board.py. Bound once in control_room_api.main() as
`RequestHandlerClass.board`. The actor is always `dave`; a body's actor is never read.

Admitted: create, brief, note, edit. Dave's decisions are the broker's (B9) and answer 501 here.
`pick`, `land`, `sweep` and every other verb are refused: 400.
"""
from __future__ import annotations

import argparse
import ipaddress
import os
import pathlib
import tempfile
from http import HTTPStatus
from typing import Any, Callable

import board

ACTOR = "dave"
WRITE_VERBS = ("create", "brief", "note", "edit")
DECISION_VERBS = ("approve_brief", "return_brief", "approve", "request_changes", "reject", "withdraw",
                  "block", "unblock")
EDIT_FIELDS = ("title", "idea", "scope", "priority", "tags", "research_on", "deadline")
CREATE_STRINGS = ("id", "title", "idea", "kind", "owner", "priority", "deadline", "research_on")


def _is_loopback(address: Any) -> bool:
    try:
        return ipaddress.ip_address(str(address).split("%")[0]).is_loopback
    except ValueError:
        return False


def peer_allowed(remote: Any, local: Any) -> tuple[bool, str]:
    if _is_loopback(local):
        return True, "loopback-bound development instance"
    if not remote:
        return False, "no peer address on a non-loopback screen"
    if _is_loopback(remote):
        return False, "loopback peer on a non-loopback screen"
    if remote == local:
        return False, "request from the screen's own host"
    return True, "peer accepted"


class Bad(Exception):
    pass


class BoardControl:
    def __init__(self, root: pathlib.Path) -> None:
        self.root = root

    @classmethod
    def from_env(cls) -> "BoardControl":
        return cls(board.board_root())

    def unavailable(self) -> str | None:
        return None if self.root.is_dir() else f"board_unavailable: {self.root} does not exist"


def _text(body: dict[str, Any], key: str) -> str:
    value = body.get(key)
    if not isinstance(value, str) or not value.strip():
        raise Bad(f"{key} must be a non-empty string")
    return value


def _strings(value: Any, name: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise Bad(f"{name} must be a list of strings")
    return value


def _rev(body: dict[str, Any], required: bool) -> int | None:
    value = body.get("expect_rev")
    if value is None and not required:
        return None
    if not isinstance(value, int) or isinstance(value, bool):
        raise Bad("expect_rev must be the integer revision the popup rendered")
    return value


def _card(body: dict[str, Any]) -> str:
    card = body.get("card")
    if not isinstance(card, str) or not board.SLUG.match(card):
        raise Bad("card must be a card id")
    return card


def _with_text(text: str, call: Callable[[str], Any]) -> Any:
    handle = tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8")
    with handle:
        handle.write(text)
    try:
        return call(handle.name)
    finally:
        os.unlink(handle.name)


def _create(root: pathlib.Path, body: dict[str, Any]) -> str:
    for key in CREATE_STRINGS + ("brief",):
        if body.get(key) is not None and not isinstance(body[key], str):
            raise Bad(f"{key} must be a string")
    args = argparse.Namespace(
        **{key: body.get(key) for key in CREATE_STRINGS}, scope=_strings(body.get("scope", []), "scope"),
        tags=_strings(body.get("tags", []), "tags"), brief=None, actor=ACTOR)
    args.kind, args.owner = args.kind or "research", args.owner or ""
    args.title, args.idea = args.title or "", args.idea or ""
    brief = body.get("brief")
    if not brief or not brief.strip():
        return board.create_card(root, args)

    def with_brief(path: str) -> str:
        args.brief = path
        return board.create_card(root, args)

    return _with_text(brief, with_brief)


def _edit_args(fields: Any) -> argparse.Namespace:
    if not isinstance(fields, dict) or not fields:
        raise Bad("fields must be a non-empty object")
    known = EDIT_FIELDS + board.LOCKED_FIELDS
    unknown = sorted(set(fields) - set(known))
    if unknown:
        raise Bad(f"unknown fields: {', '.join(unknown)}")
    values: dict[str, Any] = {name: None for name in known}
    for name, value in fields.items():
        if name == "tags":
            value = ",".join(_strings(value, "tags"))
        elif name == "scope":
            value = _strings(value, "scope")
        elif name in ("research_on", "deadline") and value is None:
            value = "none"
        elif not isinstance(value, str):
            raise Bad(f"{name} must be a string")
        values[name] = value
    return argparse.Namespace(**values)


def _apply(root: pathlib.Path, body: dict[str, Any]) -> str:
    verb = body["verb"]
    if verb == "create":
        return _create(root, body)
    card = _card(body)
    if verb == "brief":
        rev = _rev(body, False)
        _with_text(_text(body, "text"), lambda p: board.add_brief(root, card, p, ACTOR, rev))
        return card
    if verb == "note":
        _with_text(_text(body, "text"), lambda p: board.add_note(root, card, p, ACTOR))
        return card
    changes = board.parse_edit(_edit_args(body.get("fields")))
    board.edit_card(root, card, changes, _rev(body, True) or 0, ACTOR)
    return card


def _status(message: str) -> int:
    if message.startswith("stale"):
        return HTTPStatus.CONFLICT
    if message.startswith("no such card"):
        return HTTPStatus.NOT_FOUND
    return HTTPStatus.UNPROCESSABLE_ENTITY


def _refuse(handler: Any, status: int, message: str, view: Any = None) -> None:
    handler._json(status, {"ok": False, "error": message, "view": view})


def _view(root: pathlib.Path, card: Any) -> Any:
    try:
        return board.view_of(root, card) if isinstance(card, str) else None
    except board.BoardError:
        return None


def _peer_refusal(handler: Any) -> str | None:
    remote = handler.client_address[0] if handler.client_address else None
    try:
        local = handler.connection.getsockname()[0]
    except OSError:
        local = None
    allowed, why = peer_allowed(remote, local)
    return None if allowed else f"peer_denied: {why}"


def handle_post(handler: Any, control: BoardControl | None) -> None:
    if handler.headers.get("X-Control-Room") != "1":
        _refuse(handler, HTTPStatus.BAD_REQUEST, "X-Control-Room: 1 header required")
        return
    body = handler._json_body()
    verb = body.get("verb") if body is not None else None
    if body is None or not isinstance(verb, str):
        _refuse(handler, HTTPStatus.BAD_REQUEST, "body must be a JSON object with a verb")
        return
    if verb in DECISION_VERBS:
        _refuse(handler, HTTPStatus.NOT_IMPLEMENTED, "decisions go through the broker (B9)")
        return
    if verb not in WRITE_VERBS:
        _refuse(handler, HTTPStatus.BAD_REQUEST, f"verb must be one of {', '.join(WRITE_VERBS)}")
        return
    problem = "board_unavailable: seam not bound" if control is None else control.unavailable()
    if problem:
        _refuse(handler, HTTPStatus.SERVICE_UNAVAILABLE, problem)
        return
    denied = _peer_refusal(handler)
    if denied:
        _refuse(handler, HTTPStatus.FORBIDDEN, denied)
        return
    try:
        card = _apply(control.root, body)
    except Bad as exc:
        _refuse(handler, HTTPStatus.BAD_REQUEST, str(exc))
    except board.BoardError as exc:
        _refuse(handler, _status(str(exc)), str(exc), _view(control.root, body.get("card")))
    else:
        handler._json(HTTPStatus.OK, {"ok": True, "card": card, "view": _view(control.root, card)})
