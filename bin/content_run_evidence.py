#!/usr/bin/env python3
"""What a run_content_via_buzz.sh attempt log evidences, for the augustus-content receipt.

    content_run_evidence.py <attempt-log>        # prints the three facts as JSON

Three log lines carry the run's evidence, each named after the contract check or the step it
records: `content-board-transition-produced-draft … page=<p> from=Picked to=Draft` is the
state change, `owned-reply-evidences-decline … decline_event=<id>` is the owned decline, and
`trigger published … run_id=<event>` is the handoff to augustus. A line carrying `failed`
after the check name is a diagnosis of a failure and never evidence — naming a failure must
not make it pass. A missing or unreadable log evidences nothing.
"""
from __future__ import annotations

import json
import pathlib
import re
import sys

STATE_CHANGE = re.compile(r"content-board-transition-produced-draft run_id=\S+ entry_point=\S+ "
                          r"(?P<evidence>page=\S+ from=Picked to=Draft)\s*$", re.MULTILINE)
DECLINE = re.compile(r"owned-reply-evidences-decline run_id=\S+ entry_point=\S+ "
                     r"decline_event=(?P<event>\S+)\s*$", re.MULTILINE)
HANDOFF = re.compile(r"trigger published to .* run_id=(?P<event>\S+) entry_point=\S+\s*$", re.MULTILINE)


def read(path: pathlib.Path) -> dict[str, str | None]:
    try:
        text = path.read_text(errors="replace")
    except OSError:
        text = ""
    state_change = STATE_CHANGE.search(text)
    decline = DECLINE.search(text)
    handoff = HANDOFF.search(text)
    return {
        "state_change": state_change.group("evidence") if state_change else None,
        "decline_reason": f"augustus declined: decline_event={decline.group('event')}" if decline else None,
        "handoff_event": handoff.group("event") if handoff else None,
    }


if __name__ == "__main__":
    print(json.dumps(read(pathlib.Path(sys.argv[1]))))
