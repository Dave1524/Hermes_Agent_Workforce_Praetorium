"""One interactive turn as both readers report it, and the one rule that decides its outcome.

`transcript_reader` (Claude Code JSONL) and `rollout_reader` (Codex rollout) each produce a
Turn; `interaction_outcome()` is written once so the artifact/decline rule cannot drift
between the two harnesses. A Send is any tool call the turn made through the buzz CLI's
send subcommand (SEND_INVOCATION names it) and whether its result was accepted — the relay's
`{"accepted":true,"event_id":…}` reply names the artifact, a nostr event id. Nothing here
invokes the transport; bin/deliver.sh stays the one script that does.
"""
from __future__ import annotations

import dataclasses
import re
from typing import Any

import workflow_receipt

# The transport this reads for is `buzz messages send`. In command position only — at the
# start, after a shell separator, `exec` or `$(`, with an optional path prefix — so a grep or
# an echo that mentions the string is not a send.
SEND_INVOCATION = re.compile(r"(?:^|[;&|(\n]\s*|\bexec\s+|\$\(\s*)(?:[\w~./-]*/)?buzz\s+messages\s+send\b")
EVENT_ID = re.compile(r'"event_id"\s*:\s*"([0-9a-f]{64})"')
SILENCE = ("no message published to Buzz in this turn — deliberate silence or a reply that "
           "never published; the transcript cannot tell which")


@dataclasses.dataclass
class Send:
    call_id: str
    accepted: bool
    event_id: str | None


@dataclasses.dataclass
class Turn:
    run_id: str
    prompt: str | None = None
    sends: list[Send] = dataclasses.field(default_factory=list)
    usage: dict[str, Any] | None = None
    model: str | None = None
    started_at: str | None = None
    ended_at: str | None = None
    note: str | None = None


def is_send(command: str) -> bool:
    return SEND_INVOCATION.search(command) is not None


def event_id_in(output: str) -> str | None:
    match = EVENT_ID.search(output)
    return match.group(1) if match else None


def measured_usage(input_tokens: int, output_tokens: int, cache_tokens: int,
                   total_tokens: int | None = None) -> dict[str, Any]:
    total = input_tokens + output_tokens + cache_tokens if total_tokens is None else total_tokens
    return {"status": "measured", "input_tokens": input_tokens, "output_tokens": output_tokens,
            "cache_tokens": cache_tokens, "total_tokens": total}


def iso_seconds(stamp: str | None) -> str | None:
    parsed = workflow_receipt.parse_time(stamp)
    return workflow_receipt.iso_utc(parsed.replace(microsecond=0)) if parsed else None


def interaction_outcome(turn: Turn) -> tuple[dict[str, Any], str | None]:
    """(terminal, artifact uri). An accepted send is the artifact; attempts that were all
    refused are a failure, not silence; no attempt is a decline with the reason spelled out."""
    accepted = [s for s in turn.sends if s.accepted]
    if accepted:
        last = accepted[-1]
        uri = f"nostr:event:{last.event_id}" if last.event_id else f"buzz:messages/send#{last.call_id}"
        return {"outcome": "artifact", "reason": None}, uri
    if turn.sends:
        return {"outcome": "failed", "reason": f"{len(turn.sends)} Buzz send attempt(s), none accepted"}, None
    reason = f"{turn.note} — no Buzz send evidenced" if turn.note else SILENCE
    return {"outcome": "decline", "reason": reason}, None
