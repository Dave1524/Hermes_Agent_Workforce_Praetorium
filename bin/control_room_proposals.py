#!/usr/bin/env python3
"""The Control Room's proposals seam (T5.3b): shape check, peer gate, actor, and the HTTP status
map over the git worker in bin/workflow_pr.py. Bound once in control_room_api.main() as
`RequestHandlerClass.proposals`; with nothing bound the T5.3 501 stub answers unchanged.

The peer rule is the same eight lines as control_room_control.peer_allowed, duplicated so this
module never imports T5.3a's file.
"""
from __future__ import annotations

import getpass
import ipaddress
import os
import pathlib
import re
import sys
from http import HTTPStatus
from typing import Any

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import workflow_pr  # noqa: E402

KINDS = ("schedule", "retire")
STAGES = ("preview", "submit", "list")
WORKFLOW_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
FORWARDED_KEYS = ("workflow_id", "kind", "stage", "reason", "preview_token", "proposed")
HTTP_STATUS_BY_CODE = {"unknown_workflow": 404, "peer_denied": 403, "worker_unavailable": 503, "failed": 500}
DEFAULT_ROOT = "~/agent-workforce/var/control-proposals"
DEFAULT_REMOTE = "https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium.git"


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


class ProposalsControl:
    def __init__(self, worker: workflow_pr.Worker) -> None:
        self.worker = worker

    @classmethod
    def from_env(cls) -> "ProposalsControl":
        root = pathlib.Path(os.environ.get("CONTROL_ROOM_PROPOSALS_ROOT") or DEFAULT_ROOT).expanduser()
        remote = os.environ.get("CONTROL_ROOM_PROPOSALS_REMOTE") or DEFAULT_REMOTE
        author = os.environ.get("CONTROL_ROOM_GIT_AUTHOR") or workflow_pr.DEFAULT_AUTHOR
        gh_repo = os.environ.get("CONTROL_ROOM_GH_REPO") or workflow_pr.DEFAULT_GH_REPO
        return cls(workflow_pr.Worker(root, remote, gh_repo, author, live=workflow_pr.live_trees()))


def validate_kind(body: dict[str, Any]) -> str | None:
    if body.get("kind") not in KINDS:
        return f"unknown_kind: kind must be one of {', '.join(KINDS)}"
    return None


def validate_shape(body: dict[str, Any]) -> str | None:
    problem = validate_kind(body)
    if problem:
        return problem
    if body.get("stage") not in STAGES:
        return f"unknown_stage: stage must be one of {', '.join(STAGES)}"
    workflow_id = body.get("workflow_id")
    if not isinstance(workflow_id, str) or not WORKFLOW_ID_RE.match(workflow_id):
        return "bad_request: workflow_id must match ^[a-z0-9][a-z0-9-]{0,63}$"
    return None


def stub_response(handler: Any, model: Any, body: dict[str, Any]) -> None:
    if model.workflow_detail(body["workflow_id"])[0] is None:
        handler._json(HTTPStatus.NOT_FOUND, {"error": "workflow not found"})
        return
    handler._json(HTTPStatus.NOT_IMPLEMENTED, {"status": "not_implemented", "error": "PR generator not wired (T5.3b)",
                                               "workflow_id": body["workflow_id"], "kind": body["kind"]})


def _actor(handler: Any) -> dict[str, Any]:
    remote = handler.client_address[0] if handler.client_address else None
    try:
        local = handler.connection.getsockname()[0]
    except OSError:
        local = None
    return {"kind": "screen", "remote": remote, "local": local,
            "label": f"{getpass.getuser()} via control-room from {remote or 'unknown'}"}


def _request(body: dict[str, Any]) -> dict[str, Any]:
    return {key: body[key] for key in FORWARDED_KEYS if key in body}


def _fresh_control(model: Any, workflow_id: str) -> dict[str, Any] | None:
    item = model.workflow_detail(workflow_id)[0]
    return item["control"] if item else None


def _status(response: dict[str, Any]) -> int:
    error = response.get("error")
    if error is None:
        return 200
    if isinstance(error, dict):
        return HTTP_STATUS_BY_CODE.get(error.get("code"), 400)
    return HTTP_STATUS_BY_CODE["failed"]


def _refusal(handler: Any, code: str, message: str, status: int) -> None:
    handler._json(status, {"error": {"code": code, "message": message, "choices": None, "diff": None}, "record": None})


def handle_post(handler: Any, proposals: ProposalsControl | None, model: Any) -> None:
    if handler.headers.get("X-Control-Room") != "1":
        handler._json(HTTPStatus.BAD_REQUEST, {"error": "X-Control-Room: 1 header required"})
        return
    body = handler._json_body()
    if body is None:
        handler._json(HTTPStatus.BAD_REQUEST, {"error": "body must be a JSON object"})
        return
    problem = validate_kind(body) if proposals is None else validate_shape(body)
    if problem:
        code, message = problem.split(": ", 1)
        _refusal(handler, code, message, HTTPStatus.BAD_REQUEST)
        return
    if proposals is None:
        stub_response(handler, model, body)
        return
    actor = _actor(handler)
    allowed, why = peer_allowed(actor["remote"], actor["local"])
    if not allowed:
        handler._json(HTTPStatus.FORBIDDEN, proposals.worker.refuse(_request(body), actor, "peer_denied", why)[1])
        return
    item, _ = model.workflow_detail(body["workflow_id"])
    if item is None:
        _refusal(handler, "unknown_workflow", "workflow not found", HTTPStatus.NOT_FOUND)
        return
    unavailable = proposals.worker.unavailable()
    if unavailable:
        _refusal(handler, "worker_unavailable", unavailable, HTTPStatus.SERVICE_UNAVAILABLE)
        return
    if body["stage"] == "list":
        handler._json(HTTPStatus.OK, proposals.worker.list(body["workflow_id"], body["kind"]))
        return
    stage = proposals.worker.preview if body["stage"] == "preview" else proposals.worker.submit
    _, response = stage(_request(body), actor, item)
    response["control"] = _fresh_control(model, body["workflow_id"])
    handler._json(_status(response), response)
