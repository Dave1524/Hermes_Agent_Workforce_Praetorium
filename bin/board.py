#!/usr/bin/env python3
"""Agent board ledger: the one place that knows a card's shape, its verbs and its column.

Card ledger for the agent board pilot (Dev Plan Phase B, increment I1). The runner wrappers,
the Control Room seam and the Buzz bridge family all call this file; nothing re-implements a
rule. A card is a directory under $BOARD_ROOT; its column is never stored, it is derived.

LAYOUT under $BOARD_ROOT (BOARD_ROOT, else CONTROL_ROOM_BOARD_ROOT, else /var/lib/control-room-board)
  cards/<id>/card.json          the human fields at create; never rewritten
  cards/<id>/events.jsonl       append-only, one object per line: ts, event, actor, run_id?,
                                workflow?, hash?, reason?, fields?
  cards/<id>/briefs/<hash>.md   every brief text ever recorded, named by its hash
  runs/<run_id>/card.md         the per-run scratch `pick` renders; the wrappers add the rest
  trash/<id>/                   a deleted card, moved whole; restored within 30 days, then purged

A card is a title and a brief: `create` records its text as brief v1 by the creator, and the id
is the slug of the title. A `brief` run (`pick --column backlog`) answers v1 with questions for
Dave (a `questions` note) or with v2; his answer, a note, wakes the next round.

EVENTS (the ledger holds only these): created, brief, picked, note, edited, held. Run outcomes
are not events; a `picked` names its run and the run's receipt says what happened. `held` is the
board reactor's quarantine of a card it cannot run (a reason code); it blocks until `unblocked`.

ACTORS (closed): dave, mac:claude, run:<run_id>, buzz:<agent>, reactor.
  create  dave, mac:claude, buzz:*                                brief  any, by column
  note    any but reactor (questions: run:* only)                 edit   dave, mac:claude only
  pick    run:* only                                              hold   reactor only

DECISIONS are not ledger events. The nine verbs only Dave may take (brief_approved,
brief_returned, approved, changes_requested, rejected, blocked, unblocked, deleted, restored)
live in the broker's root-owned stream; derive() trusts a decision from there and nowhere else.
A decision-shaped event in the ledger is a forged-decision exception and moves nothing. Stream:
BOARD_DECISIONS_ROOT (default /var/lib/control-room/receipts/board)/decisions.jsonl, one object
per line: ts, decision, card, brief_hash?, page_hash?, text? (an approval's approved text, which
`land` writes and refuses unless it hashes to page_hash), reason?.

`board.py land [--card ID]` and `sweep` (bin/board_land.py) apply an approval as one note on
agents/<date>-card-<id> and close the loop; they write no ledger event, since Done is the join.

HASHING: sha256 of the text with CRLF turned to LF and trailing whitespace stripped. A brief
approval, `pick` and the receipt all carry it; an artifact approval hashes the page text alike.

COLUMNS, each derived: Backlog, Refine, Todo, In Progress, In Review, Done, Blocked. A card whose
latest of deleted/restored is `deleted` is in no column. `research_on` is YYYY-MM-DD (00:00) or
YYYY-MM-DDTHH:MM in BOARD_TZ (default Europe/Amsterdam); a Todo card is scheduled until then. Receipts
are read from CONTROL_ROOM_RECEIPT_ROOT (else ~/agent-workforce/var/workflow-receipts), canonical
main from BOARD_CANONICAL_CLONE (else ~/dev/Obsidian_AI_Operating_System, origin/main).
BOARD_PICK_TIMEOUT_SECONDS bounds a pick without a receipt (default 3600).

`board.py template --kind research` prints the brief skeleton, the single owner of the
required headings; `validate-brief` checks a file against it.
"""
from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import zoneinfo
from typing import Any, Iterator, Mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_receipt as wr  # noqa: E402

COLUMNS = ("Backlog", "Refine", "Todo", "In Progress", "In Review", "Done", "Blocked")
EVENTS = ("created", "brief", "picked", "note", "edited", "held")
DECISIONS = ("brief_approved", "brief_returned", "approved", "changes_requested",
             "rejected", "blocked", "unblocked", "deleted", "restored")
KIND_OWNERS = {"research": ("claudius",)}
PRIORITIES = ("high", "normal", "low")
RESERVED_IDS = ("decisions", "new", "trash")
NOTE_KINDS = ("questions", "answer")
STRIKE_LIMIT = 2
QUESTION_ROUNDS = 2
TRASH_DAYS = 30
MAX_TEXT = 60000
RESEARCH_NOTE_DIR = "05_knowledge/research"

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ACTOR = re.compile(r"^(dave|mac:claude|reactor|run:[A-Za-z0-9._-]+|buzz:[a-z0-9-]+)$")
SCOPE = re.compile(r"^(vault:[^\s]+|repo:[A-Za-z0-9._-]+)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T([01]\d|2[0-3]):[0-5]\d$")
REASON_CODE = re.compile(r"^[a-z][a-z0-9-]{1,40}$")

BRIEF_HEADINGS = ("Question", "Why", "Scope in / out", "Sources", "Acceptance", "Size",
                  "Questions for Dave")
ACCEPTANCE_RANGE = (3, 5)

_ALL_BUT_DONE = frozenset(COLUMNS) - {"Done"}
_NOT_RUNNING = _ALL_BUT_DONE - {"In Progress"}
_BRIEFABLE = frozenset({"Backlog", "Refine", "Todo", "Blocked"})
EDITABLE: dict[str, frozenset[str]] = {
    "title": _ALL_BUT_DONE, "tags": _ALL_BUT_DONE, "priority": _ALL_BUT_DONE,
    "research_on": _NOT_RUNNING, "deadline": _NOT_RUNNING,
    "scope": _BRIEFABLE, "brief": _BRIEFABLE,
    "notes": frozenset(COLUMNS),
}
UNTIL_FIRST_RUN = ("scope",)
LOCKED_FIELDS = ("id", "owner", "kind")
MOVES: dict[str, tuple[str, ...]] = {
    "Backlog": ("delete",),
    "Refine": ("approve_brief", "return_brief", "delete"),
    "Todo": ("block", "delete"),
    "In Progress": ("delete",),
    "In Review": ("approve", "request_changes", "reject"),
    "Blocked": ("unblock", "delete"),
    "Done": ("delete",),
}


class BoardError(Exception):
    """A refusal: printed to stderr, exit 1, nothing written."""


# --- roots --------------------------------------------------------------------------------
def board_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("BOARD_ROOT") or os.environ.get("CONTROL_ROOM_BOARD_ROOT")
                        or "/var/lib/control-room-board")


def decisions_file() -> pathlib.Path:
    root = os.environ.get("BOARD_DECISIONS_ROOT") or "/var/lib/control-room/receipts/board"
    return pathlib.Path(root) / "decisions.jsonl"


def receipt_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CONTROL_ROOM_RECEIPT_ROOT")
                        or pathlib.Path.home() / "agent-workforce" / "var" / "workflow-receipts")


def canonical_clone() -> pathlib.Path:
    return pathlib.Path(os.environ.get("BOARD_CANONICAL_CLONE")
                        or pathlib.Path.home() / "dev" / "Obsidian_AI_Operating_System")


def pick_timeout() -> int:
    return int(os.environ.get("BOARD_PICK_TIMEOUT_SECONDS") or 3600)


def box_tz() -> zoneinfo.ZoneInfo:
    return zoneinfo.ZoneInfo(os.environ.get("BOARD_TZ") or "Europe/Amsterdam")


def trash_root(root: pathlib.Path) -> pathlib.Path:
    return root / "trash"


def card_dir(root: pathlib.Path, card_id: str) -> pathlib.Path:
    if not SLUG.match(card_id):
        raise BoardError(f"not a card id: {card_id!r}")
    return root / "cards" / card_id


# --- hashing and text ---------------------------------------------------------------------
def normalise(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n").rstrip()


def text_hash(text: str) -> str:
    return hashlib.sha256(normalise(text).encode("utf-8")).hexdigest()


def read_text_file(path: str) -> str:
    text = pathlib.Path(path).read_text(encoding="utf-8")
    if not normalise(text):
        raise BoardError(f"{path} is empty")
    if len(text) > MAX_TEXT:
        raise BoardError(f"{path} is over {MAX_TEXT} characters")
    return text


# --- ledger io ----------------------------------------------------------------------------
def read_jsonl(path: pathlib.Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise BoardError(f"{path}:{number}: {exc}") from exc
        if not isinstance(row, dict):
            raise BoardError(f"{path}:{number}: not an object")
        rows.append(row)
    return rows


@contextlib.contextmanager
def card_lock(directory: pathlib.Path) -> Iterator[None]:
    if not (directory / "card.json").exists():
        raise BoardError(f"no such card: {directory.name}")
    with open(directory / ".lock", "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def now_utc() -> dt.datetime:
    return wr.utc_now().replace(microsecond=0)


def append_event(directory: pathlib.Path, event: str, actor: str, **extra: Any) -> dict[str, Any]:
    if event not in EVENTS:
        raise BoardError(f"not a ledger event: {event}")
    if not ACTOR.match(actor):
        raise BoardError(f"not an actor: {actor!r}")
    row = {"ts": wr.iso_utc(now_utc()), "event": event, "actor": actor,
           **{k: v for k, v in extra.items() if v is not None}}
    with open(directory / "events.jsonl", "a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, sort_keys=True) + "\n")
        handle.flush()
        os.fsync(handle.fileno())
    return row


def read_card(root: pathlib.Path, card_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    directory = card_dir(root, card_id)
    if not (directory / "card.json").exists():
        raise BoardError(f"no such card: {card_id}")
    card = json.loads((directory / "card.json").read_text(encoding="utf-8"))
    return card, read_jsonl(directory / "events.jsonl")


def card_ids(root: pathlib.Path) -> list[str]:
    cards = root / "cards"
    return sorted(p.name for p in cards.iterdir() if (p / "card.json").exists()) if cards.is_dir() else []


def read_decisions() -> list[dict[str, Any]]:
    return [d for d in read_jsonl(decisions_file()) if d.get("decision") in DECISIONS]


def read_receipt(workflow: str, run_id: str) -> dict[str, Any] | None:
    try:
        path = wr.receipt_path(receipt_root(), {"workflow_id": workflow, "run_id": run_id})
        receipt = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    return receipt if not wr.validate(receipt) else None


def load_main(clone: pathlib.Path, ids: list[str]) -> dict[str, str]:
    """card id -> content hash of its note on origin/main; absent when not there or unreadable."""
    found: dict[str, str] = {}
    for card_id in ids:
        shown = subprocess.run(
            ["git", "-C", str(clone), "show", f"origin/main:{RESEARCH_NOTE_DIR}/{card_id}.md"],
            capture_output=True, text=True, check=False)
        match = re.search(r"^content:\s*([0-9a-f]{64})\s*$", shown.stdout, re.M) if shown.returncode == 0 else None
        if match:
            found[card_id] = match.group(1)
    return found


# --- derivation ---------------------------------------------------------------------------
def _t(value: Any) -> dt.datetime:
    parsed = wr.parse_time(value)
    return parsed if parsed is not None else dt.datetime.min.replace(tzinfo=dt.timezone.utc)


def _ordered(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for _, r in sorted(enumerate(rows), key=lambda pair: (_t(pair[1].get("ts")), pair[0]))]


def effective_fields(card: Mapping[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    fields = {k: card.get(k) for k in ("title", "scope", "deadline", "research_on", "priority", "tags")}
    for event in _ordered(events):
        if event.get("event") == "edited":
            for name, change in (event.get("fields") or {}).items():
                fields[name] = change.get("new") if isinstance(change, dict) else change
    fields["priority"] = fields.get("priority") or "normal"
    fields["tags"] = fields.get("tags") or []
    return fields


def _latest(rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    return _ordered(rows)[-1] if rows else None


def _brief_state(events: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    ordered = _ordered(events)
    briefs = [e for e in ordered if e.get("event") == "brief"]
    recorded = {b.get("hash") for b in briefs}
    state: dict[str, Any] = {"hash": None, "version": len(briefs), "by": None, "approved": False,
                             "recorded": recorded}
    if not briefs:
        return state
    last = briefs[-1]
    state["version"], state["by"] = len(briefs), last.get("actor")
    after_last = ordered[ordered.index(last) + 1:]
    voided = any(e.get("event") == "edited" and set(e.get("fields") or {}) & set(UNTIL_FIRST_RUN)
                 for e in after_last)
    verdicts = [d for d in decisions if d["decision"] in ("brief_approved", "brief_returned")
                and d.get("brief_hash") == last.get("hash")]
    verdict = _latest(verdicts)
    if voided or (verdict and verdict["decision"] == "brief_returned"):
        return state
    state["hash"] = last.get("hash")
    state["approved"] = bool(verdict and verdict["decision"] == "brief_approved")
    return state


def _runs(events: list[dict[str, Any]], receipts: Mapping[str, Any]) -> list[dict[str, Any]]:
    runs = []
    for pick in (e for e in _ordered(events) if e.get("event") == "picked"):
        receipt = receipts.get(pick.get("run_id"))
        outcome = ((receipt or {}).get("terminal") or {}).get("outcome")
        page = ((receipt or {}).get("card") or {}).get("page")
        purpose = (pick.get("fields") or {}).get("purpose", "research")
        void = outcome in ("failed", "skipped") or (outcome == "artifact" and purpose == "research" and not page)
        runs.append({"run_id": pick.get("run_id"), "workflow": pick.get("workflow"), "ts": pick.get("ts"),
                     "purpose": purpose, "outcome": outcome, "page": page, "void": void})
    return runs


def _strike_times(rows: list[dict[str, Any]]) -> list[str]:
    return [r["ts"] for r in _ordered(rows)[STRIKE_LIMIT - 1:]]


def _holds(events: list[dict[str, Any]]) -> list[tuple[str, str]]:
    return [(e["ts"], f"held: {(e.get('fields') or {}).get('reason', 'unknown')}") for e in events
            if e.get("event") == "held" and e.get("actor") == "reactor"]


def _blocks(decisions, runs, recorded, fields, today, approved_landing, holds=()):
    returns = [d for d in decisions if d["decision"] == "brief_returned" and d.get("brief_hash") in recorded]
    changes = [d for d in decisions if d["decision"] == "changes_requested"]
    declines = [r for r in runs if r["outcome"] == "decline"]
    triggers = [(ts, "returned twice") for ts in _strike_times(returns)]
    triggers += [(ts, "changes requested twice") for ts in _strike_times(changes)]
    triggers += [(ts, "declined twice") for ts in _strike_times(declines)]
    triggers += [(d["ts"], "blocked by Dave") for d in decisions if d["decision"] == "blocked"]
    triggers += list(holds)
    if fields.get("deadline") and today > dt.date.fromisoformat(fields["deadline"]) and not approved_landing:
        triggers.append((fields["deadline"] + "T23:59:59Z", "deadline passed"))
    unblocks = [_t(d["ts"]) for d in decisions if d["decision"] == "unblocked"]
    since = max(unblocks) if unblocks else None
    live = [(ts, cause) for ts, cause in triggers if since is None or _t(ts) > since]
    return max(live, key=lambda pair: _t(pair[0]))[1] if live else None


def _flow(brief, runs, decisions, now, timeout):
    """Column of a card that is neither Done nor Blocked, and what it is waiting on."""
    if brief["hash"] is None:
        return {"column": "Backlog"}
    if not brief["approved"]:
        return {"column": "Refine"}
    live = [r for r in runs if r["purpose"] == "research" and not r["void"] and r["outcome"] != "decline"]
    last = live[-1] if live else None
    if last is None:
        return {"column": "Todo"}
    if last["outcome"] is None:
        stale = (now - _t(last["ts"])).total_seconds() > timeout
        return {"column": "In Progress", "stale_pick": last["run_id"] if stale else None}
    since = _t(last["ts"])
    after = [d for d in decisions if d["decision"] in ("approved", "changes_requested") and _t(d["ts"]) > since]
    verdict = _latest(after)
    if verdict and verdict["decision"] == "changes_requested":
        return {"column": "Todo"}
    return {"column": "In Review", "approved": verdict}


def _since_unblock(decisions: list[dict[str, Any]]) -> dt.datetime | None:
    unblocks = [_t(d["ts"]) for d in decisions if d["decision"] == "unblocked"]
    return max(unblocks) if unblocks else None


def _iso_or_none(moment: dt.datetime | None) -> str | None:
    return wr.iso_utc(moment) if moment else None


def failed_streak(runs: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> int:
    """Void runs at the tail of the card's runs, counted from the latest unblock."""
    since = _since_unblock(decisions)
    streak = 0
    for run in runs:
        if since is not None and _t(run["ts"]) <= since:
            continue
        streak = streak + 1 if run["void"] else 0
    return streak


def _is_human(actor: Any) -> bool:
    return isinstance(actor, str) and (actor in ("dave", "mac:claude") or actor.startswith("buzz:"))


def _note_kind(event: Mapping[str, Any]) -> str | None:
    return (event.get("fields") or {}).get("kind")


def human_inputs(events: list[dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dt.datetime]:
    """What a brief run answers: the card, Dave's first text, his notes, a new scope, a return."""
    times, agent_wrote = [], False
    for event in _ordered(events):
        kind, actor = event.get("event"), event.get("actor")
        if kind == "brief" and not _is_human(actor):
            agent_wrote = True
        human_brief = kind == "brief" and _is_human(actor) and not agent_wrote
        human_note = kind == "note" and _is_human(actor) and _note_kind(event) in (None, "answer")
        rescoped = kind == "edited" and "scope" in (event.get("fields") or {})
        if kind == "created" or human_brief or human_note or rescoped:
            times.append(_t(event.get("ts")))
    times += [_t(d["ts"]) for d in decisions if d["decision"] == "brief_returned"]
    return times


def _questions(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [e for e in _ordered(events) if e.get("event") == "note" and _note_kind(e) == "questions"
            and str(e.get("actor", "")).startswith("run:")]


def _brief_wants(column, brief, runs, events, decisions) -> dict[str, Any]:
    asked = _questions(events)
    state = {"wants": None, "awaiting_answer": False, "question_rounds": len(asked)}
    if column not in ("Backlog", "Refine") or brief["approved"]:
        return state
    inputs = human_inputs(events, decisions)
    latest_input = max(inputs) if inputs else None
    if asked and (latest_input is None or _t(asked[-1]["ts"]) > latest_input):
        state["awaiting_answer"] = True
    answered = [_t(r["ts"]) for r in runs if r["purpose"] == "brief" and not r["void"]]
    answered += [_t(e.get("ts")) for e in events if e.get("event") == "brief" and str(e.get("actor", "")).startswith("run:")]
    if not answered or (latest_input is not None and latest_input > max(answered)):
        state["wants"] = "brief"
    return state


def _deletion(decisions: list[dict[str, Any]]) -> dict[str, Any]:
    last = _latest([d for d in decisions if d["decision"] in ("deleted", "restored")])
    deleted = bool(last and last["decision"] == "deleted")
    return {"deleted": deleted, "deleted_at": last["ts"] if deleted else None}


def due_at(research_on: str) -> dt.datetime:
    moment = dt.datetime.fromisoformat(research_on if "T" in research_on else research_on + "T00:00")
    return moment.replace(tzinfo=box_tz())


def derive(card: Mapping[str, Any], events: list[dict[str, Any]], decisions: list[dict[str, Any]],
           receipts: Mapping[str, Any], main: Mapping[str, str], now: dt.datetime,
           timeout: int = 3600) -> dict[str, Any]:
    """The one pure function behind every column. Decisions come from the broker's stream only."""
    mine = [d for d in decisions if d.get("card") == card["id"]]
    fields = effective_fields(card, events)
    brief = _brief_state(events, mine)
    runs = _runs(events, receipts)
    exceptions = [{"kind": "forged-decision", "event": e.get("event")} for e in events
                  if e.get("event") in DECISIONS]
    exceptions += [{"kind": "forged-hold", "actor": e.get("actor")} for e in events
                   if e.get("event") == "held" and e.get("actor") != "reactor"]
    flow = _flow(brief, runs, mine, now, timeout)
    approval = flow.get("approved")
    approved_hash = (approval or {}).get("page_hash")
    rejection = _latest([d for d in mine if d["decision"] == "rejected"])
    block = _blocks(mine, runs, brief["recorded"], fields, now.date(), bool(approval), _holds(events))
    column, outcome = flow["column"], None
    if rejection:
        column = "Done"
        outcome = "rejected" if _flow(brief, runs, [d for d in mine if d is not rejection], now, timeout)["column"] == "In Review" else "withdrawn"
    elif approval and approved_hash and main.get(card["id"]) == approved_hash:
        column, outcome = "Done", "merged"
    elif block:
        column = "Blocked"
    if flow.get("stale_pick") and column == "In Progress":
        exceptions.append({"kind": "stale-pick", "run_id": flow["stale_pick"]})
    due = due_at(fields["research_on"]) if fields.get("research_on") else None
    scheduled = bool(due and now < due and column == "Todo")
    landing = column == "In Review" and bool(approval)
    has_run = any(r["purpose"] == "research" for r in runs)
    deletion = _deletion(mine)
    wants = _brief_wants(column, brief, runs, events, mine)
    if column == "Todo" and not scheduled:
        wants["wants"] = "research"
    if deletion["deleted"]:
        wants["wants"] = None
    return {
        **deletion, **wants, "due_at": due.isoformat() if due else None,
        "failed_streak": failed_streak(runs, mine), "unblocked_at": _iso_or_none(_since_unblock(mine)),
        "id": card["id"], "column": column, "scheduled": scheduled, "outcome": outcome,
        "blocked_cause": block if column == "Blocked" else None, "approved_landing": landing,
        "approved_hash": approved_hash, "fields": fields, "owner": card["owner"], "kind": card["kind"],
        "brief_hash": brief["hash"], "brief_version": brief["version"], "brief_by": brief["by"],
        "brief_approved": brief["approved"], "rev": len(events), "runs": runs, "has_research_run": has_run,
        "editable": editable_fields(column, has_run), "moves": [] if landing else list(MOVES[column]),
        "locked": list(LOCKED_FIELDS), "exceptions": exceptions,
    }


def editable_fields(column: str, has_research_run: bool) -> list[str]:
    return sorted(name for name, columns in EDITABLE.items() if column in columns
                  and not (has_research_run and name in UNTIL_FIRST_RUN))


def receipts_for(events: list[dict[str, Any]]) -> dict[str, Any]:
    return {e.get("run_id"): read_receipt(e.get("workflow", ""), e.get("run_id", ""))
            for e in events if e.get("event") == "picked"}


def fresh_view(root: pathlib.Path, card_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Derivation under the card's lock, without the canonical-main join (no verb needs it)."""
    card, events = read_card(root, card_id)
    view = derive(card, events, read_decisions(), receipts_for(events), {}, dt.datetime.now().astimezone(),
                  pick_timeout())
    return view, events


# --- collection ---------------------------------------------------------------------------
def collect(root: pathlib.Path, now: dt.datetime | None = None, include_deleted: bool = False,
            join_main: bool = True, decisions: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    now = now or dt.datetime.now().astimezone()
    decisions = read_decisions() if decisions is None else decisions
    main = _main_join(decisions) if join_main else {}
    views = {}
    for card_id in card_ids(root):
        card, events = read_card(root, card_id)
        view = derive(card, events, decisions, receipts_for(events), main, now, pick_timeout())
        if include_deleted or not view["deleted"]:
            views[card_id] = view
    return views


def _main_join(decisions: list[dict[str, Any]]) -> dict[str, str]:
    approved = sorted({d["card"] for d in decisions if d["decision"] == "approved"})
    return load_main(canonical_clone(), approved) if approved and canonical_clone().is_dir() else {}


def card_exists(root: pathlib.Path, card_id: str | None) -> bool:
    return (card_dir(root, card_id) / "card.json").is_file() if card_id else root.is_dir()


def view_of(root: pathlib.Path, card_id: str) -> dict[str, Any]:
    views = collect(root)
    if card_id not in views:
        raise BoardError(f"no such card: {card_id}")
    return views[card_id]


def _order_key(view: dict[str, Any]) -> tuple[Any, ...]:
    rank = PRIORITIES.index(view["fields"]["priority"])
    return (rank, view["fields"].get("deadline") or "9999-12-31", view["id"])


PURPOSE_OF = {"backlog": "brief", "todo": "research"}


def _eligible(view: Mapping[str, Any], column: str) -> bool:
    if column in PURPOSE_OF:
        return view["wants"] == PURPOSE_OF[column]
    return view["column"] == column.replace("-", " ").title() and not view["scheduled"]


def candidates(views: Mapping[str, dict[str, Any]], column: str, owner: str | None,
               kind: str | None, card: str | None = None) -> list[dict[str, Any]]:
    rows = [v for v in views.values() if _eligible(v, column) and (card is None or v["id"] == card)
            and (owner is None or v["owner"] == owner) and (kind is None or v["kind"] == kind)]
    return sorted(rows, key=_order_key)


# --- verbs: writers -----------------------------------------------------------------------
def require_actor(actor: str, allowed: tuple[str, ...], verb: str) -> None:
    if not ACTOR.match(actor):
        raise BoardError(f"not an actor: {actor!r}")
    if not any(actor == a or (a.endswith("*") and actor.startswith(a[:-1])) for a in allowed):
        raise BoardError(f"{actor} may not {verb}")


def check_date(value: str | None, name: str) -> str | None:
    if value in (None, "", "none"):
        return None
    if not DATE.match(value):
        raise BoardError(f"{name} is not YYYY-MM-DD: {value!r}")
    try:
        dt.date.fromisoformat(value)
    except ValueError as exc:
        raise BoardError(f"{name} is not a date: {value!r}") from exc
    return value


def check_research_on(value: str | None) -> str | None:
    if value in (None, "", "none"):
        return None
    if not (DATE.match(value) or DATETIME.match(value)):
        raise BoardError(f"research date is not YYYY-MM-DD or YYYY-MM-DDTHH:MM: {value!r}")
    try:
        due_at(value)
    except ValueError as exc:
        raise BoardError(f"research date is not a time: {value!r}") from exc
    return value


def check_dates_agree(research_on: str | None, deadline: str | None) -> None:
    if research_on and deadline and research_on[:10] > deadline:
        raise BoardError(f"research date {research_on} is after the deadline {deadline}")


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:63]


def _write_whole(path: pathlib.Path, text: str) -> None:
    """A reader woken by the create never sees a half-written file."""
    temp = path.with_name(f".{path.name}.tmp")
    temp.write_text(text, encoding="utf-8")
    os.replace(temp, path)


def create_card(root: pathlib.Path, args: argparse.Namespace) -> str:
    require_actor(args.actor, ("dave", "mac:claude", "buzz:*"), "create")
    if args.kind not in KIND_OWNERS:
        raise BoardError(f"kind {args.kind!r} is not a pilot kind: {', '.join(KIND_OWNERS)}")
    if args.owner not in KIND_OWNERS[args.kind]:
        raise BoardError(f"{args.owner!r} has no runner for kind {args.kind}")
    if not args.scope or any(not SCOPE.match(s) for s in args.scope):
        raise BoardError("scope is one or more of vault:<dir> / repo:<name>")
    if not args.title.strip():
        raise BoardError("a card needs a title")
    if not args.brief:
        raise BoardError("a card needs a brief: its text is brief v1")
    priority = args.priority or "normal"
    if priority not in PRIORITIES:
        raise BoardError(f"priority is one of {', '.join(PRIORITIES)}")
    research_on, deadline = check_research_on(args.research_on), check_date(args.deadline, "deadline")
    check_dates_agree(research_on, deadline)
    card_id = slugify(args.title)
    if card_id in RESERVED_IDS:
        raise BoardError(f"{card_id!r} is reserved: the board API routes on it")
    directory = card_dir(root, card_id)
    if (trash_root(root) / card_id).exists():
        raise BoardError(f"card exists in the trash: {card_id}; restore it or choose another title")
    brief_text = read_text_file(args.brief)
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise BoardError(f"card exists: {card_id}") from exc
    (directory / "briefs").mkdir()
    card = {"id": card_id, "title": args.title.strip(), "kind": args.kind,
            "owner": args.owner, "scope": args.scope, "deadline": deadline, "research_on": research_on,
            "priority": priority, "tags": args.tags or [], "created": wr.iso_utc(now_utc())}
    _write_whole(directory / "card.json", json.dumps(card, indent=2, sort_keys=True) + "\n")
    with card_lock(directory):
        append_event(directory, "created", args.actor)
        record_brief(directory, brief_text, args.actor, None)
    return card_id


def record_brief(directory: pathlib.Path, text: str, actor: str, run_id: str | None,
                 fields: dict[str, Any] | None = None) -> str:
    digest = text_hash(text)
    (directory / "briefs" / f"{digest}.md").write_text(normalise(text) + "\n", encoding="utf-8")
    append_event(directory, "brief", actor, hash=digest, run_id=run_id, fields=fields)
    return digest


def brief_columns(actor: str) -> frozenset[str]:
    if actor.startswith("run:"):
        return frozenset({"Backlog", "Refine"})
    return frozenset({"Backlog", "Refine"}) if actor.startswith("buzz:") else _BRIEFABLE


def add_brief(root: pathlib.Path, card_id: str, path: str, actor: str, expect_rev: int | None = None) -> str:
    require_actor(actor, ("dave", "mac:claude", "buzz:*", "run:*"), "write a brief")
    text, directory = read_text_file(path), card_dir(root, card_id)
    with card_lock(directory):
        view, events = fresh_view(root, card_id)
        if expect_rev is not None and len(events) != expect_rev:
            raise BoardError(f"stale: card is at revision {len(events)}, you saved {expect_rev}")
        run_id = actor[4:] if actor.startswith("run:") else None
        earlier = [e for e in events if e.get("event") == "brief" and run_id and e.get("run_id") == run_id]
        if earlier:
            return earlier[0]["hash"]
        if view["column"] not in brief_columns(actor):
            raise BoardError(f"{actor} may not write a brief on a card in {view['column']}")
        digest = text_hash(text)
        if any(d["decision"] == "brief_returned" and d.get("card") == card_id and d.get("brief_hash") == digest
               for d in read_decisions()):
            raise BoardError("this text was already returned; write a new brief")
        if digest == view["brief_hash"]:
            raise BoardError("the brief is unchanged")
        return record_brief(directory, text, actor, run_id)


def add_note(root: pathlib.Path, card_id: str, path: str, actor: str, kind: str | None = None) -> None:
    require_actor(actor, ("dave", "mac:claude", "buzz:*", "run:*"), "add a note")
    if kind is not None and kind not in NOTE_KINDS:
        raise BoardError(f"a note kind is one of {', '.join(NOTE_KINDS)}")
    if (kind == "questions") != actor.startswith("run:") and kind is not None:
        raise BoardError(f"{actor} may not write a {kind} note")
    text, directory = read_text_file(path), card_dir(root, card_id)
    fields = {"text": normalise(text), **({"kind": kind} if kind else {})}
    with card_lock(directory):
        read_card(root, card_id)
        append_event(directory, "note", actor, fields=fields, run_id=actor[4:] if actor.startswith("run:") else None)


def hold_card(root: pathlib.Path, card_id: str, reason: str, actor: str) -> bool:
    """The reactor's quarantine; False when the card is already held for a reason no unblock lifted."""
    require_actor(actor, ("reactor",), "hold")
    if not REASON_CODE.match(reason):
        raise BoardError(f"not a reason code: {reason!r}")
    directory = card_dir(root, card_id)
    with card_lock(directory):
        view, _ = fresh_view(root, card_id)
        if view["column"] == "Blocked" and str(view["blocked_cause"]).startswith("held: "):
            return False
        append_event(directory, "held", actor, fields={"reason": reason})
        return True


def edit_card(root: pathlib.Path, card_id: str, changes: dict[str, Any], expect_rev: int, actor: str) -> list[str]:
    require_actor(actor, ("dave", "mac:claude"), "edit")
    refused = [name for name in changes if name in LOCKED_FIELDS]
    if refused:
        raise BoardError(f"{', '.join(refused)} cannot be edited")
    directory = card_dir(root, card_id)
    with card_lock(directory):
        view, events = fresh_view(root, card_id)
        if len(events) != expect_rev:
            raise BoardError(f"stale: card is at revision {len(events)}, you saved {expect_rev}")
        current = view["fields"]
        diff = {k: {"old": current[k], "new": v} for k, v in changes.items() if current[k] != v}
        if not diff:
            raise BoardError("nothing changed")
        for name in diff:
            if name not in view["editable"]:
                raise BoardError(f"{name} cannot be edited on a card in {view['column']}"
                                 + (" after its first research run" if name in UNTIL_FIRST_RUN and view["has_research_run"] else ""))
        merged = {**current, **{k: d["new"] for k, d in diff.items()}}
        check_dates_agree(merged.get("research_on"), merged.get("deadline"))
        append_event(directory, "edited", actor, fields=diff)
        return sorted(diff)


def parse_edit(args: argparse.Namespace) -> dict[str, Any]:
    changes: dict[str, Any] = {}
    for name in LOCKED_FIELDS:
        if getattr(args, name, None) is not None:
            changes[name] = getattr(args, name)
    simple = {"title": args.title}
    changes.update({k: v.strip() for k, v in simple.items() if v is not None})
    if args.scope is not None:
        if any(not SCOPE.match(s) for s in args.scope):
            raise BoardError("scope is one or more of vault:<dir> / repo:<name>")
        changes["scope"] = args.scope
    if args.priority is not None:
        if args.priority not in PRIORITIES:
            raise BoardError(f"priority is one of {', '.join(PRIORITIES)}")
        changes["priority"] = args.priority
    if args.tags is not None:
        changes["tags"] = [t for t in args.tags.split(",") if t]
    if args.research_on is not None:
        changes["research_on"] = check_research_on(args.research_on)
    if args.deadline is not None:
        changes["deadline"] = check_date(args.deadline, "deadline")
    if not changes:
        raise BoardError("name at least one field to edit")
    return changes


# --- verbs: pick --------------------------------------------------------------------------
def first_brief_text(directory: pathlib.Path, events: list[dict[str, Any]]) -> str | None:
    briefs = [e for e in _ordered(events) if e.get("event") == "brief"]
    if not briefs:
        return None
    try:
        return normalise((directory / "briefs" / f"{briefs[0]['hash']}.md").read_text(encoding="utf-8"))
    except OSError:
        return None


def _note_lines(events: list[dict[str, Any]]) -> list[str]:
    lines = []
    for event in (e for e in _ordered(events) if e.get("event") == "note"):
        label = f"{event.get('ts')} {event.get('actor')}" + (f" ({_note_kind(event)})" if _note_kind(event) else "")
        lines += ["", f"### {label}", "", str((event.get("fields") or {}).get("text", ""))]
    return lines


def _round_line(view: Mapping[str, Any]) -> str:
    used = view.get("question_rounds", 0)
    if used >= QUESTION_ROUNDS:
        return f"question rounds used: {used} of {QUESTION_ROUNDS}; no rounds left: write the brief"
    return f"question round {used + 1} of {QUESTION_ROUNDS}"


def render_card_md(view: Mapping[str, Any], brief_text: str | None, decisions: list[dict[str, Any]],
                   v1_text: str | None = None, events: list[dict[str, Any]] | None = None,
                   purpose: str | None = None) -> str:
    fields = view["fields"]
    mine = [d for d in decisions if d.get("card") == view["id"]]
    returned = [d.get("reason", "") for d in reversed(_ordered(mine)) if d["decision"] == "brief_returned"]
    changes = _latest([d for d in mine if d["decision"] == "changes_requested"])
    parts = [f"# {fields['title']}", f"id: {view['id']}", f"owner: {view['owner']}  kind: {view['kind']}",
             f"scope: {', '.join(fields['scope'])}", f"deadline: {fields.get('deadline') or 'none (standing)'}"]
    if purpose == "brief":
        parts.append(_round_line(view))
    if v1_text and v1_text != brief_text:
        parts += ["", f"## Brief v1 (by {view.get('brief_v1_by') or 'the creator'})", "", v1_text]
    if returned:
        parts += ["", "## Returned reasons (newest first)", ""] + [f"- {r}" for r in returned]
    if brief_text:
        parts += ["", "## Approved brief" if view["brief_approved"] else "## Brief", "", brief_text]
    notes = _note_lines(events or [])
    if notes:
        parts += ["", "## Notes (oldest first)"] + notes
    if changes and view["has_research_run"] and view["column"] == "Todo":
        parts += ["", "## Dave's note after a request for changes", "", changes.get("reason", "")]
    return "\n".join(parts) + "\n"


def pick_card(root: pathlib.Path, args: argparse.Namespace) -> str | None:
    require_actor(f"run:{args.run_id}", ("run:*",), "pick")
    purpose = PURPOSE_OF[args.column]
    views = collect(root)
    for view in views.values():
        for run in view["runs"]:
            if run["run_id"] == args.run_id:
                return view["id"]
    for view in candidates(views, args.column, args.owner, args.kind, getattr(args, "card", None)):
        directory = card_dir(root, view["id"])
        with card_lock(directory):
            fresh, events = fresh_view(root, view["id"])
            decisions = read_decisions()
            if not _eligible(fresh, args.column):
                continue
            brief_text = None
            if fresh["brief_hash"]:
                brief_text = (directory / "briefs" / f"{fresh['brief_hash']}.md").read_text(encoding="utf-8")
                if text_hash(brief_text) != fresh["brief_hash"]:
                    print(f"exception: pick-hash-mismatch {view['id']}", file=sys.stderr)
                    continue
            scratch = root / "runs" / args.run_id
            scratch.mkdir(parents=True, exist_ok=True)
            card_md = render_card_md(fresh, normalise(brief_text) if brief_text else None, decisions,
                                     first_brief_text(directory, events), events, purpose)
            (scratch / "card.md").write_text(card_md, encoding="utf-8")
            append_event(directory, "picked", f"run:{args.run_id}", run_id=args.run_id,
                         workflow=args.workflow, hash=fresh["brief_hash"], fields={"purpose": purpose})
            return view["id"]
    return None


# --- brief template -----------------------------------------------------------------------
def template(kind: str) -> str:
    if kind != "research":
        raise BoardError(f"no template for kind {kind!r}")
    hints = {
        "Question": "The research question, sharpened from the idea.",
        "Why": "The decision or project it feeds, read from the card's scope.",
        "Scope in / out": "What the run covers and what it leaves alone.",
        "Sources": "Vault paths to read first; web query lines, de-identified (docs/data_boundary.md).",
        "Acceptance": "- Three to five checkable statements, one per line, each answerable from the artifact alone.",
        "Size": "Fits one run, or a proposed split into cards for Dave to create.",
        "Questions for Dave": "What the vault does not say and this run needs. Write none if there are none.",
    }
    body = "".join(f"\n## {h}\n\n{hints[h]}\n" for h in BRIEF_HEADINGS)
    return f"# Brief: <card id>\n{body}"


def validate_brief(text: str, card_id: str) -> list[str]:
    problems = []
    lines = normalise(text).split("\n")
    if not lines or lines[0].strip() != f"# Brief: {card_id}":
        problems.append(f"first line is not '# Brief: {card_id}'")
    sections = {m.group(1).strip(): [] for m in map(re.compile(r"^## (.+)$").match, lines) if m}
    current = None
    for line in lines:
        match = re.match(r"^## (.+)$", line)
        current = match.group(1).strip() if match else current
        if current in sections and not match:
            sections[current].append(line)
    problems += [f"missing heading: ## {h}" for h in BRIEF_HEADINGS if h not in sections]
    problems += [f"empty section: ## {h}" for h in BRIEF_HEADINGS if h in sections and not "".join(sections[h]).strip()]
    if "Acceptance" in sections:
        count = sum(1 for line in sections["Acceptance"] if re.match(r"^\s*(?:[-*]|\d+[.)])\s+\S", line))
        low, high = ACCEPTANCE_RANGE
        if not low <= count <= high:
            problems.append(f"acceptance has {count} lines, wanted {low} to {high}")
    return problems


# --- reads and CLI ------------------------------------------------------------------------
def emit(value: Any, as_json: bool, plain: str) -> None:
    print(json.dumps(value, indent=2, sort_keys=True) if as_json else plain)


def show_text(root: pathlib.Path, view: dict[str, Any]) -> str:
    brief, directory = None, card_dir(root, view["id"])
    if view["brief_hash"]:
        brief = (directory / "briefs" / f"{view['brief_hash']}.md").read_text(encoding="utf-8")
    _, events = read_card(root, view["id"])
    text = render_card_md(view, normalise(brief) if brief else None, read_decisions(),
                          first_brief_text(directory, events), events)
    state = f"\n## State\n\ncolumn: {view['column']}" + (f" ({view['blocked_cause']})" if view["blocked_cause"] else "")
    return text + state + (f"\noutcome: {view['outcome']}" if view["outcome"] else "") + "\n"


def unapplied(views: Mapping[str, dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Approvals not yet on main, a deleted card's included: the Mac still owes the merge or its undo."""
    return [d for d in decisions if d["decision"] == "approved"
            and (d.get("card") not in views or views[d["card"]]["column"] != "Done")]


# --- trash --------------------------------------------------------------------------------
def _deleted_at(decisions: list[dict[str, Any]], card_id: str) -> str | None:
    return _deletion([d for d in decisions if d.get("card") == card_id])["deleted_at"]


def trash_card(root: pathlib.Path, card_id: str) -> bool:
    """Move a deleted card whole into the trash; False when it is not on the board."""
    source, target = card_dir(root, card_id), trash_root(root) / card_id
    if not (source / "card.json").exists():
        return False
    if target.exists():
        raise BoardError(f"the trash already holds {card_id}")
    trash_root(root).mkdir(parents=True, exist_ok=True)
    with card_lock(source):
        os.rename(source, target)
    return True


def restore_card(root: pathlib.Path, card_id: str) -> bool:
    """Move a trashed card back; False when the trash does not hold it."""
    source, target = trash_root(root) / card_dir(root, card_id).name, card_dir(root, card_id)
    if not (source / "card.json").exists():
        return False
    if target.exists():
        raise BoardError(f"a card {card_id} is on the board again; restore refused")
    with card_lock(source):
        os.rename(source, target)
    return True


def trash_list(root: pathlib.Path, decisions: list[dict[str, Any]] | None = None) -> list[dict[str, Any]]:
    decisions, rows = read_decisions() if decisions is None else decisions, []
    trash = trash_root(root)
    for directory in sorted(trash.iterdir()) if trash.is_dir() else []:
        if not (directory / "card.json").exists():
            continue
        card = json.loads((directory / "card.json").read_text(encoding="utf-8"))
        fields = effective_fields(card, read_jsonl(directory / "events.jsonl"))
        deleted = _deleted_at(decisions, directory.name)
        purge = wr.iso_utc(_t(deleted) + dt.timedelta(days=TRASH_DAYS)) if deleted else None
        rows.append({"id": directory.name, "title": fields["title"], "deleted_at": deleted, "purge_after": purge})
    return sorted(rows, key=lambda r: _t(r["deleted_at"]), reverse=True)


def trash_views(root: pathlib.Path, now: dt.datetime | None = None,
                decisions: list[dict[str, Any]] | None = None) -> dict[str, dict[str, Any]]:
    """Each trashed card derived as it stood, for closing its page; never a board listing."""
    now, views = now or dt.datetime.now().astimezone(), {}
    decisions = read_decisions() if decisions is None else decisions
    trash = trash_root(root)
    for directory in sorted(trash.iterdir()) if trash.is_dir() else []:
        if (directory / "card.json").exists():
            card = json.loads((directory / "card.json").read_text(encoding="utf-8"))
            events = read_jsonl(directory / "events.jsonl")
            views[directory.name] = derive(card, events, decisions, receipts_for(events), {}, now, pick_timeout())
    return views


def purge_trash(root: pathlib.Path, now: dt.datetime) -> list[str]:
    """Remove trash past the retention; a trashed card with no deletion on record is kept."""
    return sorted(row["id"] for row in trash_list(root) if _purge_row(root, row, now))


def purge_card(root: pathlib.Path, card_id: str, now: dt.datetime) -> bool:
    """Remove one trashed card past the retention; False when it is not due or not there."""
    return any(_purge_row(root, row, now) for row in trash_list(root) if row["id"] == card_id)


def _purge_row(root: pathlib.Path, row: Mapping[str, Any], now: dt.datetime) -> bool:
    if not row["purge_after"] or now < _t(row["purge_after"]):
        return False
    shutil.rmtree(trash_root(root) / row["id"])
    return True


# --- migration ----------------------------------------------------------------------------
def _migrated(events: list[dict[str, Any]]) -> bool:
    return any((e.get("fields") or {}).get("migrated") == "idea" or
               (e.get("event") == "note" and _note_kind(e) == "idea") for e in events)


def migrate_idea(root: pathlib.Path) -> list[str]:
    """Each card's `idea` into brief v1 (no brief yet) or an `idea` note beside its briefs; once."""
    done = []
    for card_id in card_ids(root):
        directory = card_dir(root, card_id)
        with card_lock(directory):
            card, events = read_card(root, card_id)
            idea = str(card.get("idea") or "").strip()
            if not idea or _migrated(events):
                continue
            if any(e.get("event") == "brief" for e in events):
                append_event(directory, "note", "dave", fields={"text": idea, "kind": "idea"})
            else:
                creator = next((e["actor"] for e in events if e.get("event") == "created"), "dave")
                record_brief(directory, idea, creator if _is_human(creator) else "dave", None, {"migrated": "idea"})
            done.append(card_id)
    return done


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="board.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb", required=True)

    def verb(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        return sub.add_parser(name, **kwargs)

    create = verb("create", help="create a card: the title names it, the brief file is brief v1")
    create.add_argument("--title", required=True)
    create.add_argument("--kind", default="research")
    create.add_argument("--owner", required=True)
    create.add_argument("--scope", action="append", required=True)
    create.add_argument("--deadline")
    create.add_argument("--research-on", dest="research_on")
    create.add_argument("--priority")
    create.add_argument("--tags", type=lambda s: [t for t in s.split(",") if t])
    create.add_argument("--brief", help="the brief text's file; required")
    create.add_argument("--actor", required=True)
    lst = verb("list", help="cards, optionally filtered")
    lst.add_argument("--owner")
    lst.add_argument("--kind")
    lst.add_argument("--column")
    lst.add_argument("--json", action="store_true")
    for name in ("show", "status"):
        one = verb(name, help="a card as text (show) or its column (status)")
        one.add_argument("card")
        one.add_argument("--json", action="store_true")
    nxt = verb("next", help="the id of the top card in a column, or nothing")
    nxt.add_argument("--column", required=True)
    nxt.add_argument("--owner")
    nxt.add_argument("--kind")
    decisions = verb("decisions", help="the broker's decisions; --unapplied: approvals not yet on main")
    decisions.add_argument("--unapplied", action="store_true")
    tpl = verb("template", help="print the brief skeleton")
    tpl.add_argument("--kind", required=True)
    vb = verb("validate-brief", help="exit 1 naming the missing heading or the acceptance-line count")
    vb.add_argument("file")
    vb.add_argument("--card", required=True)
    for name in ("brief", "note"):
        w = verb(name, help=f"record a {name} from a file")
        w.add_argument("card")
        w.add_argument("--from-file", dest="file", required=True)
        w.add_argument("--actor", required=True)
        if name == "note":
            w.add_argument("--kind", choices=NOTE_KINDS)
    hold = verb("hold", help="the reactor's quarantine: block a card with a reason code until unblocked")
    hold.add_argument("card")
    hold.add_argument("--reason", required=True)
    hold.add_argument("--actor", required=True)
    verb("migrate-idea", help="once: each card's idea into brief v1, or a note beside its briefs")
    pick = verb("pick", help="before the model: take the top card wanting a run (backlog: brief, todo: research)")
    pick.add_argument("--owner", required=True)
    pick.add_argument("--kind", default="research")
    pick.add_argument("--column", default="todo", choices=tuple(PURPOSE_OF))
    pick.add_argument("--card", help="this card only")
    pick.add_argument("--run-id", required=True)
    pick.add_argument("--workflow", required=True)
    edit = verb("edit", help="change a card's fields; refused for agents and for stale revisions")
    edit.add_argument("card")
    edit.add_argument("--expect-rev", type=int, required=True)
    edit.add_argument("--actor", required=True)
    for name in ("title", "priority", "tags", "research-on", "deadline", "id", "owner", "kind"):
        edit.add_argument(f"--{name}", dest=name.replace("-", "_"))
    edit.add_argument("--scope", action="append")
    land = verb("land", help="write each unlanded approval as one note on agents/<date>-card-<id>")
    land.add_argument("--card")
    verb("sweep", help="land, fetch main, mark pages, raise the card exceptions")
    exists = verb("exists", help="exit 0 when the board root (or this card on it) exists: the run units' ExecCondition")
    exists.add_argument("card", nargs="?")
    return parser


def run(args: argparse.Namespace) -> int:
    root = board_root()
    handlers = {
        "create": lambda: print(create_card(root, args)),
        "brief": lambda: print(add_brief(root, args.card, args.file, args.actor)),
        "note": lambda: add_note(root, args.card, args.file, args.actor, args.kind),
        "hold": lambda: print("held" if hold_card(root, args.card, args.reason, args.actor) else "already held"),
        "migrate-idea": lambda: print("\n".join(migrate_idea(root))),
        "edit": lambda: print("edited: " + ", ".join(edit_card(root, args.card, parse_edit(args), args.expect_rev, args.actor))),
        "template": lambda: print(template(args.kind), end=""),
    }
    if args.verb in handlers:
        handlers[args.verb]()
        return 0
    if args.verb in ("land", "sweep"):
        import board_land
        lines = board_land.land(root, args.card)[0] if args.verb == "land" else board_land.sweep(root)
        print("\n".join(lines))
    elif args.verb == "pick":
        picked = pick_card(root, args)
        print(picked or "", end="\n" if picked else "")
    elif args.verb == "exists":
        return 0 if card_exists(root, args.card) else 1
    elif args.verb == "validate-brief":
        problems = validate_brief(read_text_file(args.file), args.card)
        print("\n".join(problems) if problems else "ok")
        return 1 if problems else 0
    elif args.verb == "list":
        rows = [v for v in collect(root).values() if (not args.owner or v["owner"] == args.owner)
                and (not args.kind or v["kind"] == args.kind)
                and (not args.column or v["column"].lower().replace(" ", "-") == args.column)]
        rows.sort(key=lambda v: (COLUMNS.index(v["column"]), _order_key(v)))
        emit(rows, args.json, "\n".join(f"{v['id']}\t{v['column']}\t{v['fields']['priority']}\t{v['fields']['title']}" for v in rows))
    elif args.verb in ("show", "status"):
        view = view_of(root, args.card)
        plain = show_text(root, view) if args.verb == "show" else view["column"]
        emit(view, args.json, plain)
    elif args.verb == "next":
        rows = candidates(collect(root), args.column, args.owner, args.kind)
        print(rows[0]["id"] if rows else "", end="\n" if rows else "")
    elif args.verb == "decisions":
        rows = read_decisions()
        rows = unapplied(collect(root), rows) if args.unapplied else rows
        print("\n".join(json.dumps(r, sort_keys=True) for r in rows))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return run(args)
    except BoardError as exc:
        print(f"board: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
