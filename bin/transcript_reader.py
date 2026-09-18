"""The Claude Code transcript's last turn: everything after the last human prompt.

A human prompt is a `user` record whose content is text — a string, or text blocks with no
tool_result — that is neither `isMeta` (the harness talking to itself) nor a sidechain. The
turn is every record after it: assistant messages carry the usage (one message can span
several records that share `message.id`, so usage is counted per id, last record wins) and
the tool calls; the `user` records that follow carry their results. Reuses
bin/skill_telemetry.py's record reader; its tool_use reader drops the block id a result is
matched by, so the tool_use blocks are walked here.
"""
from __future__ import annotations

import pathlib
from typing import Any

import interaction_turn
import skill_telemetry
import workflow_receipt

NAMESPACE_RE = skill_telemetry.parse_args(["-", "--namespace", skill_telemetry.DEFAULT_NAMESPACE])[1]


def _text_of(content: Any) -> str | None:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return None
    if any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
        return None
    texts = [b["text"] for b in content if isinstance(b, dict) and b.get("type") == "text" and isinstance(b.get("text"), str)]
    return "\n".join(texts) if texts else None


def is_human_prompt(record: dict[str, Any]) -> bool:
    if record.get("type") != "user" or record.get("isMeta") or record.get("isSidechain"):
        return False
    message = record.get("message")
    return isinstance(message, dict) and _text_of(message.get("content")) is not None


def _tool_results(record: dict[str, Any]) -> list[dict[str, Any]]:
    if record.get("type") != "user":
        return []
    message = record.get("message")
    content = message.get("content") if isinstance(message, dict) else None
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_result"]


def _result_text(block: dict[str, Any]) -> str:
    content = block.get("content")
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


def _sum_usage(by_message: dict[str, dict[str, Any]]) -> dict[str, Any] | None:
    if not by_message:
        return None
    counts = {"input_tokens": 0, "output_tokens": 0, "cache_creation_input_tokens": 0, "cache_read_input_tokens": 0}
    for usage in by_message.values():
        for key in counts:
            value = usage.get(key)
            counts[key] += value if isinstance(value, int) and not isinstance(value, bool) else 0
    cache = counts["cache_creation_input_tokens"] + counts["cache_read_input_tokens"]
    return interaction_turn.measured_usage(counts["input_tokens"], counts["output_tokens"], cache)


def read(path: pathlib.Path, session_id: str) -> interaction_turn.Turn:
    records = list(skill_telemetry.records(path))
    prompt_index = max((i for i, r in enumerate(records) if is_human_prompt(r)), default=None)
    if prompt_index is None:
        return interaction_turn.Turn(run_id=f"{session_id}-no-prompt", note="no human prompt in the transcript")
    prompt = records[prompt_index]
    turn = interaction_turn.Turn(run_id=f"{session_id}-{prompt.get('uuid')}", prompt=_text_of(prompt["message"]["content"]),
                                 started_at=interaction_turn.iso_seconds(prompt.get("timestamp")))
    usage_by_message: dict[str, dict[str, Any]] = {}
    pending: dict[str, str] = {}
    last_assistant: dict[str, Any] | None = None
    for record in records[prompt_index + 1:]:
        if record.get("isSidechain"):
            continue
        if record.get("type") == "assistant":
            last_assistant = record
            message = record.get("message") or {}
            if isinstance(message.get("usage"), dict):
                usage_by_message[str(message.get("id") or record.get("uuid"))] = message["usage"]
            turn.model = message.get("model") or turn.model
            for block in _tool_uses(message):
                command = block["input"].get("command")
                if block.get("name") == "Bash" and isinstance(command, str) and interaction_turn.is_send(command):
                    pending[str(block.get("id"))] = command
        for block in _tool_results(record):
            call_id = str(block.get("tool_use_id"))
            if call_id in pending:
                text = _result_text(block)
                turn.sends.append(interaction_turn.Send(call_id, not block.get("is_error"), interaction_turn.event_id_in(text)))
    if last_assistant is not None:
        turn.run_id = f"{session_id}-{last_assistant.get('uuid')}"
        turn.ended_at = interaction_turn.iso_seconds(last_assistant.get("timestamp"))
    turn.usage = _sum_usage(usage_by_message)
    turn.skills = _skills(records, prompt_index)
    return turn


def _skills(records: list[dict[str, Any]], prompt_index: int) -> dict[str, Any]:
    """Offered is the session's listing, which precedes the first prompt; invoked and read
    are this turn's own tool uses. A session of fifty turns is offered once."""
    offered: set[str] = set()
    for record in records:
        offered.update(filter(None, (skill_telemetry.unqualified(n, NAMESPACE_RE) for n in skill_telemetry.listing_names(record))))
    invoked: set[str] = set()
    read: set[str] = set()
    for record in records[prompt_index + 1:]:
        if record.get("isSidechain"):
            continue
        for name, tool_input in skill_telemetry.tool_uses(record):
            if name == "Skill" and isinstance(tool_input.get("skill"), str):
                invoked.add(skill_telemetry.unqualified(tool_input["skill"], NAMESPACE_RE))
            elif name == "Read" and isinstance(tool_input.get("file_path"), str):
                read.add(skill_telemetry.skill_from_path(tool_input["file_path"]))
    return workflow_receipt.measured_skills(offered, invoked - {None}, read - {None}, "transcript")


def _tool_uses(message: dict[str, Any]) -> list[dict[str, Any]]:
    content = message.get("content")
    if not isinstance(content, list):
        return []
    return [b for b in content if isinstance(b, dict) and b.get("type") == "tool_use" and isinstance(b.get("input"), dict)]
