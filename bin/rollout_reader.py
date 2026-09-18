"""The Codex rollout's one turn: the span between task_started and task_complete by turn_id.

The rollout lives at `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<thread-id>.jsonl` and is
found by globbing on the thread id, never on the date. Inside the span, a `function_call`
(the 0.145 app-server's `exec_command`, arguments JSON with `cmd`) or a `custom_tool_call`
(0.147's `exec`, a bare `input` string) whose command is a Buzz send
(interaction_turn.SEND_INVOCATION) is a Send, accepted when its output by `call_id` reports
`Process exited with code 0` or the relay's
`"accepted":true`. Usage is the turn's share of the thread total — the last `token_count`
inside the span minus the last one before it — so a turn of several model responses is not
reported as its final response alone. Codex spawns `notify` while it may still be writing
the rollout, so the file is re-read up to three times over two seconds until the span's
task_complete appears; usage is `unavailable` if it never does.

A `task_complete` carrying `error` is a turn the harness ended, not one the agent finished:
codex-acp still reports it upstream as a completed turn, and nothing is posted. Between
2026-09-07 and 09-10 forty of augustus's turns ended that way (`404 … The model gpt-5.5 does
not exist or you do not have access to it`, interleaved with `usage_limit_exceeded`), two of
them the nightly content run, and every layer outside this file read them as silence. The
error travels on the Turn so the receipt can name it.
"""
from __future__ import annotations

import json
import pathlib
import re
import time
from typing import Any

import interaction_turn
import skill_telemetry
import workflow_receipt

# Codex lists what it offers in a developer message: `- <name>: <description> (file: ...)`
# under `### Available skills`. A pointer tree mounted at $CODEX_HOME/skills/praetorium
# renders as praetorium-<owner>:<name>, which is the namespace cost.log already filters on.
SKILL_LINE = re.compile(r"^- (\S+): ", re.MULTILINE)
NAMESPACE_RE = skill_telemetry.parse_args(["-", "--namespace", skill_telemetry.DEFAULT_NAMESPACE])[1]

RETRIES = 3
RETRY_PAUSE_SECONDS = 1.0
USAGE_KEYS = ("input_tokens", "cached_input_tokens", "output_tokens", "total_tokens")


def rollout_path(codex_home: pathlib.Path, thread_id: str) -> pathlib.Path | None:
    matches = sorted(codex_home.glob(f"sessions/*/*/*/rollout-*-{thread_id}.jsonl"))
    return matches[-1] if matches else None


def _payload(record: dict[str, Any]) -> dict[str, Any]:
    payload = record.get("payload")
    return payload if isinstance(payload, dict) else {}


def _span(records: list[dict[str, Any]], turn_id: str) -> tuple[int | None, int | None]:
    start = end = None
    for index, record in enumerate(records):
        payload = _payload(record)
        if record.get("type") != "event_msg" or payload.get("turn_id") != turn_id:
            continue
        if payload.get("type") == "task_started" and start is None:
            start = index
        elif payload.get("type") == "task_complete" and start is not None:
            end = index
            break
    return start, end


def _command_of(payload: dict[str, Any]) -> str | None:
    if payload.get("type") == "custom_tool_call":
        return payload.get("input") if isinstance(payload.get("input"), str) else None
    if payload.get("type") != "function_call":
        return None
    arguments = payload.get("arguments")
    if isinstance(arguments, str):
        try:
            arguments = json.loads(arguments)
        except ValueError:
            return arguments
    if isinstance(arguments, dict):
        command = arguments.get("cmd") or arguments.get("command")
        return command if isinstance(command, str) else json.dumps(arguments)
    return None


def _output_text(payload: dict[str, Any]) -> str:
    output = payload.get("output")
    if isinstance(output, str):
        return output
    if isinstance(output, list):
        return "\n".join(b.get("text", "") for b in output if isinstance(b, dict))
    return ""


def _accepted(output: str) -> bool:
    return "exited with code 0" in output or '"accepted":true' in output.replace(" ", "")


def _totals(record: dict[str, Any]) -> dict[str, Any] | None:
    payload = _payload(record)
    if record.get("type") != "event_msg" or payload.get("type") != "token_count":
        return None
    info = payload.get("info")
    totals = info.get("total_token_usage") if isinstance(info, dict) else None
    return totals if isinstance(totals, dict) else None


def _usage(records: list[dict[str, Any]], start: int, end: int) -> dict[str, Any] | None:
    before = next((t for t in (_totals(r) for r in reversed(records[:start])) if t), {})
    after = next((t for t in (_totals(r) for r in reversed(records[start:end + 1])) if t), None)
    if after is None:
        return None
    counts = {}
    for key in USAGE_KEYS:
        now, then = after.get(key), before.get(key, 0)
        if not isinstance(now, int) or not isinstance(then, int):
            return None
        counts[key] = now - then
    return interaction_turn.measured_usage(counts["input_tokens"], counts["output_tokens"],
                                           counts["cached_input_tokens"], counts["total_tokens"])


def _sends(records: list[dict[str, Any]]) -> list[interaction_turn.Send]:
    pending: dict[str, str] = {}
    sends = []
    for record in records:
        payload = _payload(record)
        if record.get("type") != "response_item":
            continue
        command = _command_of(payload)
        if command is not None and interaction_turn.is_send(command):
            pending[str(payload.get("call_id"))] = command
        elif payload.get("type") in ("function_call_output", "custom_tool_call_output"):
            call_id = str(payload.get("call_id"))
            if call_id in pending:
                text = _output_text(payload)
                sends.append(interaction_turn.Send(call_id, _accepted(text), interaction_turn.event_id_in(text)))
    return sends


def _error(record: dict[str, Any] | None) -> str | None:
    error = _payload(record).get("error") if record is not None else None
    if not isinstance(error, dict):
        return None
    message = error.get("message")
    if not isinstance(message, str) or not message.strip():
        return None
    kind = error.get("codex_error_info")
    text = " ".join(message.split())
    return f"{kind}: {text}" if isinstance(kind, str) and kind else text


def _model(records: list[dict[str, Any]], turn_id: str) -> str | None:
    for record in records:
        payload = _payload(record)
        if record.get("type") == "turn_context" and payload.get("turn_id") == turn_id:
            return payload.get("model") if isinstance(payload.get("model"), str) else None
    return None


def _load_complete(path: pathlib.Path, turn_id: str) -> tuple[list[dict[str, Any]], int | None, int | None]:
    for attempt in range(RETRIES):
        records = list(skill_telemetry.records(path))
        start, end = _span(records, turn_id)
        if end is not None or attempt == RETRIES - 1:
            return records, start, end
        time.sleep(RETRY_PAUSE_SECONDS)
    return [], None, None


def read(codex_home: pathlib.Path, thread_id: str, turn_id: str) -> interaction_turn.Turn:
    turn = interaction_turn.Turn(run_id=f"{thread_id}-{turn_id}")
    path = rollout_path(codex_home, thread_id)
    if path is None:
        turn.note = "rollout not found"
        return turn
    records, start, end = _load_complete(path, turn_id)
    if start is None:
        turn.note = "turn not found in the rollout"
        return turn
    last = end if end is not None else len(records) - 1
    span = records[start:last + 1]
    turn.sends = _sends(span)
    turn.model = _model(records, turn_id)
    turn.started_at = interaction_turn.iso_seconds(records[start].get("timestamp"))
    turn.ended_at = interaction_turn.iso_seconds(records[end].get("timestamp")) if end is not None else None
    turn.usage = _usage(records, start, end) if end is not None else None
    turn.error = _error(records[end]) if end is not None else None
    for record in span:
        payload = _payload(record)
        if record.get("type") == "event_msg" and payload.get("type") == "user_message" and isinstance(payload.get("message"), str):
            turn.prompt = payload["message"]
            break
    turn.skills = _skills(records, span)
    return turn


def _offered(records: list[dict[str, Any]]) -> set[str]:
    offered: set[str] = set()
    for record in records:
        payload = _payload(record)
        if record.get("type") != "response_item" or payload.get("role") != "developer":
            continue
        for block in payload.get("content") or []:
            text = block.get("text") if isinstance(block, dict) else None
            if isinstance(text, str) and text.startswith("<skills_instructions>"):
                offered.update(filter(None, (skill_telemetry.unqualified(n, NAMESPACE_RE) for n in SKILL_LINE.findall(text))))
    return offered


def _skills(records: list[dict[str, Any]], span: list[dict[str, Any]]) -> dict[str, Any]:
    """Offered is the thread's developer listing; read is every SKILL.md a command in this
    turn names. Codex has no Skill tool, so invoked is always empty here."""
    read: set[str] = set()
    for record in span:
        command = _command_of(_payload(record))
        if command:
            read.update(skill_telemetry.skills_in_text(command))
    return workflow_receipt.measured_skills(_offered(records), set(), read, "rollout")
