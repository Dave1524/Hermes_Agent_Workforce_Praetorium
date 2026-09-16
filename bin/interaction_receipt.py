#!/usr/bin/env python3
"""One receipt per interactive Buzz turn, written by the harness's turn-end hook.

Claude Code agents run it as the `Stop` hook (buzz-team/agent-settings.json): the hook
payload arrives on stdin and names the transcript, and the turn is everything after the
last human prompt (bin/transcript_reader.py). Codex agents run it as `notify` with
`--codex-notify <json>`: the payload names the thread and turn, and the turn is read from
the rollout under $CODEX_HOME (bin/rollout_reader.py). Both produce a Turn that
bin/interaction_turn.py turns into the outcome — an accepted Buzz send is the artifact,
none is a decline — and one workflow_receipt under the agent's unit.

Three rules, all for the same reason — a hook that misbehaves damages the agent's turn:
never write to stdout (a Stop hook's stdout is read by the harness), never exit non-zero
(a failing Stop hook blocks the stop), never log or print an environment value (the
agent's process carries its Nostr key). The unit comes from INTERACTION_RECEIPT_UNIT or
from /proc/self/cgroup; a heartbeat prompt (~/.config/buzz-team/heartbeat.prompt) is not
a turn and gets no receipt. Claude Code sees the heartbeat verbatim; codex-acp hands it
over with the <base> layer prepended in the same user message, so the match is on the tail.
"""
from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import sys
from typing import Any

import interaction_turn
import rollout_reader
import transcript_reader
import workflow_receipt

UNIT_IN_CGROUP = re.compile(r"buzz-agent@([A-Za-z0-9_-]+)\.service")
CODEX_EVENT = "agent-turn-complete"
LOG_RELATIVE = pathlib.Path("agent-workforce") / "logs" / "interaction_receipt.log"
HEARTBEAT_RELATIVE = pathlib.Path(".config") / "buzz-team" / "heartbeat.prompt"
RECEIPTS_RELATIVE = pathlib.Path("agent-workforce") / "var" / "workflow-receipts"


class NoReceipt(Exception):
    """Ends the hook with one log line and no receipt; never an error."""


def home() -> pathlib.Path:
    return pathlib.Path(os.environ.get("HOME") or pathlib.Path.home())


def log(message: str) -> None:
    path = home() / LOG_RELATIVE
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(f"{interaction_turn.iso_seconds(workflow_receipt.iso_utc())} {message}\n")
    except OSError:
        pass


def unit_name() -> str:
    override = os.environ.get("INTERACTION_RECEIPT_UNIT", "").strip()
    if override:
        return override.removesuffix(".service")
    try:
        cgroup = pathlib.Path("/proc/self/cgroup").read_text(encoding="utf-8")
    except OSError:
        cgroup = ""
    match = UNIT_IN_CGROUP.search(cgroup)
    if not match:
        raise NoReceipt("no buzz-agent unit — no receipt")
    return f"buzz-agent@{match.group(1)}"


def heartbeat_text() -> str:
    path = os.environ.get("INTERACTION_RECEIPT_HEARTBEAT_FILE") or home() / HEARTBEAT_RELATIVE
    try:
        return pathlib.Path(path).read_text(encoding="utf-8").strip()
    except OSError:
        return ""


def refuse_heartbeat(prompt: str | None) -> None:
    heartbeat = heartbeat_text()
    if prompt is not None and heartbeat and prompt.strip().endswith(heartbeat):
        raise NoReceipt("heartbeat: no receipt")


def parse_json(raw: str, what: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except ValueError:
        raise NoReceipt(f"malformed {what} — no receipt") from None
    if not isinstance(payload, dict):
        raise NoReceipt(f"{what} is not an object — no receipt")
    return payload


def claude_turn(stdin: str) -> interaction_turn.Turn:
    payload = parse_json(stdin, "hook stdin")
    session, path = payload.get("session_id"), payload.get("transcript_path")
    if not isinstance(session, str) or not session or not isinstance(path, str) or not path:
        raise NoReceipt("hook stdin names no session or transcript — no receipt")
    transcript = pathlib.Path(path)
    if not transcript.is_file():
        raise NoReceipt(f"transcript not found: {transcript} — no receipt")
    turn = transcript_reader.read(transcript, session)
    refuse_heartbeat(turn.prompt)
    return turn


def codex_turn(raw: str) -> interaction_turn.Turn:
    payload = parse_json(raw, "codex notify payload")
    if payload.get("type") != CODEX_EVENT:
        raise NoReceipt(f"codex notify type is not {CODEX_EVENT} — no receipt")
    thread, turn_id = payload.get("thread-id"), payload.get("turn-id")
    if not isinstance(thread, str) or not thread or not isinstance(turn_id, str) or not turn_id:
        raise NoReceipt("codex notify names no thread or turn — no receipt")
    messages = payload.get("input-messages")
    first = messages[0] if isinstance(messages, list) and messages else None
    refuse_heartbeat(first if isinstance(first, str) else None)
    codex_home = pathlib.Path(os.environ.get("CODEX_HOME") or home() / ".codex")
    return rollout_reader.read(codex_home, thread, turn_id)


def build_receipt(unit: str, turn: interaction_turn.Turn) -> dict[str, Any]:
    terminal, uri = interaction_turn.interaction_outcome(turn)
    now = interaction_turn.iso_seconds(workflow_receipt.iso_utc())
    started = turn.started_at or now
    ended = turn.ended_at or now
    if workflow_receipt.parse_time(ended) < workflow_receipt.parse_time(started):
        ended = started
    receipt: dict[str, Any] = {
        "schema_version": workflow_receipt.SCHEMA_VERSION,
        "workflow_id": unit,
        "run_id": turn.run_id,
        "unit": unit,
        "agent": unit.partition("@")[2] or None,
        "model": turn.model,
        "vantage": "interaction",
        "started_at": started,
        "ended_at": ended,
        "terminal": terminal,
        "assertions": [],
        "usage": turn.usage or workflow_receipt.unavailable_usage(),
        "cost": workflow_receipt.unavailable_cost(),
        "next_action": {"actor": None, "action": None},
        "parent_run_id": None,
        "handoff": None,
    }
    if uri:
        receipt["artifact"] = {"uri": uri}
    return receipt


def receipt_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CONTROL_ROOM_RECEIPT_ROOT") or home() / RECEIPTS_RELATIVE)


def read_stdin() -> str:
    if sys.stdin is None or sys.stdin.isatty():
        return ""
    return sys.stdin.read()


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--codex-notify", metavar="JSON", default=None,
                        help="the payload Codex passes its notify command; without it the Claude Code Stop payload is read from stdin")
    return parser.parse_args(argv)


def main(argv: list[str]) -> int:
    try:
        args = parse_args(argv)
        unit = unit_name()
        turn = codex_turn(args.codex_notify) if args.codex_notify is not None else claude_turn(read_stdin())
        receipt = build_receipt(unit, turn)
        workflow_receipt.write(receipt, receipt_root())
        log(f"{unit} {turn.run_id} {receipt['terminal']['outcome']}")
    except NoReceipt as exc:
        log(str(exc))
    except SystemExit:
        log("not written: bad arguments")
    except Exception as exc:  # noqa: BLE001 — a Stop hook that raises blocks the agent's stop
        log(f"not written: {type(exc).__name__}: {exc}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
