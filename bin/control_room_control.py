#!/usr/bin/env python3
"""Screen side of the T5.3a workflow controls: the Control Room's POST handler.

The screen runs as dave and never touches systemd itself. A POST to /api/v1/control/actions is
shape-checked, stamped with the requesting actor and forwarded over the root-owned broker socket
(bin/control_broker.py); the broker decides, acts, receipts, and the screen answers with that
receipt plus a *fresh* re-read of the workflow's control block — the state a viewer sees after a
click came from systemd, never from the click. `lastAction` on the page is the newest
non-preview receipt under the broker's receipts root, read here.

`peer_allowed` and `contract_retry_declaration` are duplicated in the broker / the allowlist
renderer on purpose: the root side imports nothing from this module.
"""
from __future__ import annotations

import getpass
import ipaddress
import json
import os
import pathlib
import re
import socket
import sys
from http import HTTPStatus
from typing import Any, Callable

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from control_broker import validate_receipt  # noqa: E402
from control_room_state import ACTION_IDS, RUNTIME_ACTION_IDS  # noqa: E402

CONTROL_ACTION_IDS = ACTION_IDS + tuple(action for action in RUNTIME_ACTION_IDS if action not in ACTION_IDS)

DEFAULT_SOCKET = "/run/control-room-broker.sock"
DEFAULT_RECEIPTS = "/var/lib/control-room/receipts"
BROKER_TIMEOUT_SECONDS = 60
HTTP_STATUS_BY_CODE = {"unknown_workflow": 404, "peer_denied": 403, "not_allowlisted": 403}
FORWARDED_KEYS = ("workflow_id", "action", "reason", "stage", "preview_token", "trigger", "confirm", "retry_of")
NOT_DECLARED = "contract declares no idempotent operation"


class BrokerUnavailable(Exception):
    """The socket is absent, refused the connection, or closed without a response."""


class BrokerTimeout(BrokerUnavailable):
    """The broker accepted the request and never answered within the timeout."""


def _is_loopback(address: Any) -> bool:
    try:
        return ipaddress.ip_address(str(address)).is_loopback
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


def _clean(cell: str) -> str:
    text = re.sub(r"`([^`]*)`", r"\1", cell)
    text = re.sub(r"\*\*([^*]+)\*\*", r"\1", text)
    return re.sub(r"\s+", " ", text).strip()


def _identity_section(text: str) -> str:
    match = re.search(r"^## Identity\s*$\n(.*?)(?=^## |\Z)", text, re.MULTILINE | re.DOTALL)
    return match.group(1) if match else ""


def contract_retry_declaration(text: str) -> tuple[bool, str | None]:
    for line in _identity_section(text).splitlines():
        cells = [_clean(cell) for cell in line.strip().strip("|").split("|")] if line.startswith("|") else []
        if len(cells) >= 2 and cells[0].lower() == "retry":
            first = re.match(r"[*`_]*([A-Za-z]+)", cells[1])
            return bool(first and first.group(1).lower() == "idempotent"), cells[1] or None
    return False, None


def retry_policy(repo: pathlib.Path | str) -> Callable[[dict[str, Any]], tuple[bool, str | None]]:
    root = pathlib.Path(repo)

    def declared(item: dict[str, Any]) -> bool | None:
        contract = item.get("contract") or {}
        relative = contract.get("path") if isinstance(contract, dict) else None
        if not relative:
            return None
        try:
            return contract_retry_declaration((root / relative).read_text(encoding="utf-8"))[0]
        except OSError:
            return None

    def policy(item: dict[str, Any]) -> tuple[bool, str | None]:
        idempotent = declared(item)
        if idempotent is None:
            return False, "contract unavailable"
        if not idempotent:
            return False, NOT_DECLARED
        if (item.get("control") or {}).get("state") == "running":
            return False, "a run is in progress"
        outcome = (item.get("lastRun") or {}).get("outcome")
        if outcome == "failed":
            return True, None
        return False, f"retry needs a failed last run (last run: {outcome or 'none'})"

    return policy


class BrokerClient:
    def __init__(self, socket_path: str, timeout: float = BROKER_TIMEOUT_SECONDS) -> None:
        self.socket_path, self.timeout = str(socket_path), timeout

    def call(self, request: dict[str, Any]) -> dict[str, Any]:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(self.timeout)
            try:
                connection.connect(self.socket_path)
                connection.sendall((json.dumps(request) + "\n").encode("utf-8"))
                connection.shutdown(socket.SHUT_WR)
                raw = self._drain(connection)
            except socket.timeout as exc:
                raise BrokerTimeout(f"broker at {self.socket_path} timed out after {self.timeout:g} s") from exc
            except OSError as exc:
                raise BrokerUnavailable(f"{self.socket_path}: {exc}") from exc
        try:
            response = json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise BrokerUnavailable(f"broker at {self.socket_path} closed without a JSON response") from exc
        if not isinstance(response, dict) or "result" not in response:
            raise BrokerUnavailable(f"broker at {self.socket_path} answered with no result")
        return response

    @staticmethod
    def _drain(connection: socket.socket) -> bytes:
        chunks = []
        while True:
            chunk = connection.recv(65536)
            if not chunk:
                return b"".join(chunks)
            chunks.append(chunk)


class ControlReceipts:
    def __init__(self, root: pathlib.Path | str) -> None:
        self.root = pathlib.Path(root)

    def last_action(self, logical_id: str) -> dict[str, Any] | None:
        newest = None
        for path in self._paths(logical_id):
            receipt = self._load(path)
            if receipt is None or receipt.get("result") == "previewed":
                continue
            if newest is None or str(receipt.get("completed_at")) > str(newest[1].get("completed_at")):
                newest = (path, receipt)
        return self._seam(*newest) if newest else None

    def _paths(self, logical_id: str) -> list[pathlib.Path]:
        try:
            return sorted((self.root / logical_id).glob("*.json"))
        except OSError:
            return []

    @staticmethod
    def _load(path: pathlib.Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            errors = validate_receipt(data)
        except (OSError, ValueError) as exc:
            errors = [f"{type(exc).__name__}: {exc}"]
        if errors:
            print(f"control_room_control: skipping malformed receipt {path}: {errors[0]}", file=sys.stderr)
            return None
        return data

    @staticmethod
    def _seam(path: pathlib.Path, receipt: dict[str, Any]) -> dict[str, Any]:
        links = receipt.get("links") or {}
        return {
            "action": receipt.get("action"),
            "actor": (receipt.get("actor") or {}).get("label"),
            "reason": receipt.get("reason"),
            "at": receipt.get("completed_at"),
            "result": receipt.get("result"),
            "before": (receipt.get("before") or {}).get("state"),
            "after": (receipt.get("after") or {}).get("state"),
            "receiptId": receipt.get("receipt_id"),
            "links": {"receipt": str(path), "run": links.get("run"), "previewReceipt": links.get("preview_receipt"),
                      "workflow": links.get("workflow"), "agent": links.get("agent")},
        }


class ControlRoomControl:
    def __init__(self, client: Any, receipts: ControlReceipts, retry_policy: Callable[[dict[str, Any]], tuple[bool, str | None]]) -> None:
        self.client, self.receipts, self.retry_policy = client, receipts, retry_policy

    @classmethod
    def from_env(cls, repo: pathlib.Path | str) -> "ControlRoomControl":
        socket_path = os.environ.get("CONTROL_ROOM_BROKER_SOCKET", DEFAULT_SOCKET)
        receipts = os.environ.get("CONTROL_ROOM_CONTROL_RECEIPTS", DEFAULT_RECEIPTS)
        return cls(BrokerClient(socket_path), ControlReceipts(receipts), retry_policy(repo))


def validate_shape(body: dict[str, Any]) -> str | None:
    if body.get("action") not in CONTROL_ACTION_IDS:
        return f"action must be one of {', '.join(CONTROL_ACTION_IDS)}"
    if not isinstance(body.get("workflow_id"), str) or not body["workflow_id"]:
        return "workflow_id must be a non-empty string"
    return None


def stub_response(handler: Any, model: Any, body: dict[str, Any]) -> None:
    if model.workflow_detail(body["workflow_id"])[0] is None:
        handler._json(HTTPStatus.NOT_FOUND, {"error": "workflow not found"})
        return
    handler._json(HTTPStatus.NOT_IMPLEMENTED, {"status": "not_implemented", "error": "control broker not wired (T5.3a)",
                                               "workflow_id": body["workflow_id"], "action": body["action"]})


def _actor(handler: Any) -> dict[str, Any]:
    remote = handler.client_address[0] if handler.client_address else None
    try:
        local = handler.connection.getsockname()[0]
    except OSError:
        local = None
    return {"kind": "screen", "remote": remote, "local": local,
            "label": f"{getpass.getuser()} via control-room from {remote or 'unknown'}"}


def _request(body: dict[str, Any], actor: dict[str, Any]) -> dict[str, Any]:
    request = {key: body[key] for key in FORWARDED_KEYS if key in body}
    request.update({"v": 1, "actor": actor})
    return request


def _status(response: dict[str, Any]) -> int:
    result = response.get("result")
    if result in ("applied", "previewed"):
        return 200
    if result == "refused":
        return HTTP_STATUS_BY_CODE.get((response.get("refusal") or {}).get("code"), 400)
    return 500


def _fresh_control(model: Any, workflow_id: str) -> dict[str, Any] | None:
    item = model.workflow_detail(workflow_id)[0]
    return item["control"] if item else None


def handle_post(handler: Any, control: ControlRoomControl | None, model: Any) -> None:
    if handler.headers.get("X-Control-Room") != "1":
        handler._json(HTTPStatus.BAD_REQUEST, {"error": "X-Control-Room: 1 header required"})
        return
    body = handler._json_body()
    if body is None:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
        return
    problem = validate_shape(body)
    if problem:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": problem})
        return
    if control is None:
        stub_response(handler, model, body)
        return
    try:
        response = control.client.call(_request(body, _actor(handler)))
    except BrokerTimeout as exc:
        handler._json(HTTPStatus.GATEWAY_TIMEOUT, {"error": f"control broker unreachable: {exc}", "receipt": None})
        return
    except BrokerUnavailable as exc:
        handler._json(HTTPStatus.BAD_GATEWAY, {"error": f"control broker unreachable: {exc}", "receipt": None})
        return
    payload: dict[str, Any] = {"receipt": response.get("receipt"), "control": _fresh_control(model, body["workflow_id"])}
    if response.get("result") == "previewed":
        payload["preview"] = response.get("preview")
    if response.get("result") == "refused":
        payload["error"] = (response.get("refusal") or {}).get("message") or "refused"
    elif response.get("result") not in ("applied", "previewed"):
        payload["error"] = "the broker's command failed; see receipt.commands"
    handler._json(_status(response), payload)
