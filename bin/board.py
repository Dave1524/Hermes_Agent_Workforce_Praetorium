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

EVENTS (the ledger holds only these): created, brief, picked, note, edited. Run outcomes are
not events; a `picked` names its run and the run's receipt says what happened.

ACTORS (closed): dave, mac:claude, run:<run_id>, buzz:<agent>.
  create  dave, mac:claude, buzz:*  (buzz: never with a brief)    brief  any, by column
  note    any                                                     edit   dave, mac:claude only
  pick    run:* only

DECISIONS are not ledger events. The seven verbs only Dave may take (brief_approved,
brief_returned, approved, changes_requested, rejected, blocked, unblocked) live in the broker's
root-owned stream; derive() trusts a decision from there and nowhere else. A decision-shaped
event in the ledger is a forged-decision exception and moves nothing. Stream:
BOARD_DECISIONS_ROOT (default /var/lib/control-room/receipts/board)/decisions.jsonl, one object
per line: ts, decision, card, brief_hash?, page_hash?, text? (an approval's approved text, which
`land` writes and refuses unless it hashes to page_hash), reason?.

`board.py land [--card ID]` and `sweep` (bin/board_land.py) apply an approval as one note on
agents/<date>-card-<id> and close the loop; they write no ledger event, since Done is the join.

HASHING: sha256 of the text with CRLF turned to LF and trailing whitespace stripped. A brief
approval, `pick` and the receipt all carry it; an artifact approval hashes the page text alike.

COLUMNS, each derived: Backlog, Refine, Todo, In Progress, In Review, Done, Blocked. Receipts
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
import subprocess
import sys
from typing import Any, Iterator, Mapping

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import workflow_receipt as wr  # noqa: E402

COLUMNS = ("Backlog", "Refine", "Todo", "In Progress", "In Review", "Done", "Blocked")
EVENTS = ("created", "brief", "picked", "note", "edited")
DECISIONS = ("brief_approved", "brief_returned", "approved", "changes_requested",
             "rejected", "blocked", "unblocked")
KIND_OWNERS = {"research": ("claudius",)}
PRIORITIES = ("high", "normal", "low")
STRIKE_LIMIT = 2
MAX_TEXT = 60000
RESEARCH_NOTE_DIR = "05_knowledge/research"

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
ACTOR = re.compile(r"^(dave|mac:claude|run:[A-Za-z0-9._-]+|buzz:[a-z0-9-]+)$")
SCOPE = re.compile(r"^(vault:[^\s]+|repo:[A-Za-z0-9._-]+)$")
DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")

BRIEF_HEADINGS = ("Question", "Why", "Scope in / out", "Sources", "Acceptance", "Size",
                  "Questions for Dave")
ACCEPTANCE_RANGE = (3, 5)

_ALL_BUT_DONE = frozenset(COLUMNS) - {"Done"}
_NOT_RUNNING = _ALL_BUT_DONE - {"In Progress"}
_BRIEFABLE = frozenset({"Backlog", "Refine", "Todo", "Blocked"})
EDITABLE: dict[str, frozenset[str]] = {
    "title": _ALL_BUT_DONE, "tags": _ALL_BUT_DONE, "priority": _ALL_BUT_DONE,
    "research_on": _NOT_RUNNING, "deadline": _NOT_RUNNING,
    "idea": _BRIEFABLE, "scope": _BRIEFABLE, "brief": _BRIEFABLE,
    "notes": frozenset(COLUMNS),
}
UNTIL_FIRST_RUN = ("idea", "scope")
LOCKED_FIELDS = ("id", "owner", "kind")
MOVES: dict[str, tuple[str, ...]] = {
    "Backlog": ("withdraw",),
    "Refine": ("approve_brief", "return_brief", "withdraw"),
    "Todo": ("block", "withdraw"),
    "In Progress": (),
    "In Review": ("approve", "request_changes", "reject"),
    "Blocked": ("unblock", "withdraw"),
    "Done": (),
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
    fields = {k: card.get(k) for k in ("title", "idea", "scope", "deadline", "research_on",
                                       "priority", "tags")}
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
        void = outcome in ("failed", "skipped") or (outcome == "artifact" and not page)
        runs.append({"run_id": pick.get("run_id"), "workflow": pick.get("workflow"), "ts": pick.get("ts"),
                     "purpose": (pick.get("fields") or {}).get("purpose", "research"),
                     "outcome": outcome, "page": page, "void": void})
    return runs


def _strike_times(rows: list[dict[str, Any]]) -> list[str]:
    return [r["ts"] for r in _ordered(rows)[STRIKE_LIMIT - 1:]]


def _blocks(decisions, runs, recorded, fields, today, approved_landing):
    returns = [d for d in decisions if d["decision"] == "brief_returned" and d.get("brief_hash") in recorded]
    changes = [d for d in decisions if d["decision"] == "changes_requested"]
    declines = [r for r in runs if r["outcome"] == "decline"]
    triggers = [(ts, "returned twice") for ts in _strike_times(returns)]
    triggers += [(ts, "changes requested twice") for ts in _strike_times(changes)]
    triggers += [(ts, "declined twice") for ts in _strike_times(declines)]
    triggers += [(d["ts"], "blocked by Dave") for d in decisions if d["decision"] == "blocked"]
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
    flow = _flow(brief, runs, mine, now, timeout)
    approval = flow.get("approved")
    approved_hash = (approval or {}).get("page_hash")
    rejection = _latest([d for d in mine if d["decision"] == "rejected"])
    block = _blocks(mine, runs, brief["recorded"], fields, now.date(), bool(approval))
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
    scheduled = bool(fields.get("research_on") and now.date() < dt.date.fromisoformat(fields["research_on"])
                     and column == "Todo")
    landing = column == "In Review" and bool(approval)
    has_run = any(r["purpose"] == "research" for r in runs)
    return {
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
def collect(root: pathlib.Path, now: dt.datetime | None = None) -> dict[str, dict[str, Any]]:
    now = now or dt.datetime.now().astimezone()
    decisions = read_decisions()
    approved = sorted({d["card"] for d in decisions if d["decision"] == "approved"})
    main = load_main(canonical_clone(), approved) if approved and canonical_clone().is_dir() else {}
    views = {}
    for card_id in card_ids(root):
        card, events = read_card(root, card_id)
        views[card_id] = derive(card, events, decisions, receipts_for(events), main, now, pick_timeout())
    return views


def view_of(root: pathlib.Path, card_id: str) -> dict[str, Any]:
    views = collect(root)
    if card_id not in views:
        raise BoardError(f"no such card: {card_id}")
    return views[card_id]


def _order_key(view: dict[str, Any]) -> tuple[Any, ...]:
    rank = PRIORITIES.index(view["fields"]["priority"])
    return (rank, view["fields"].get("deadline") or "9999-12-31", view["id"])


def candidates(views: Mapping[str, dict[str, Any]], column: str, owner: str | None,
               kind: str | None) -> list[dict[str, Any]]:
    wanted = column.replace("-", " ").title()
    rows = [v for v in views.values() if v["column"] == wanted and not v["scheduled"]
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
    dt.date.fromisoformat(value)
    return value


def check_dates_agree(research_on: str | None, deadline: str | None) -> None:
    if research_on and deadline and research_on > deadline:
        raise BoardError(f"research date {research_on} is after the deadline {deadline}")


def slugify(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")[:63]


def create_card(root: pathlib.Path, args: argparse.Namespace) -> str:
    require_actor(args.actor, ("dave", "mac:claude", "buzz:*"), "create")
    if args.brief and args.actor.startswith("buzz:"):
        raise BoardError(f"{args.actor} creates into Backlog only: no brief")
    if args.kind not in KIND_OWNERS:
        raise BoardError(f"kind {args.kind!r} is not a pilot kind: {', '.join(KIND_OWNERS)}")
    if args.owner not in KIND_OWNERS[args.kind]:
        raise BoardError(f"{args.owner!r} has no runner for kind {args.kind}")
    if not args.scope or any(not SCOPE.match(s) for s in args.scope):
        raise BoardError("scope is one or more of vault:<dir> / repo:<name>")
    if not args.title.strip() or not args.idea.strip():
        raise BoardError("a card needs a title and an idea")
    priority = args.priority or "normal"
    if priority not in PRIORITIES:
        raise BoardError(f"priority is one of {', '.join(PRIORITIES)}")
    research_on, deadline = check_date(args.research_on, "research date"), check_date(args.deadline, "deadline")
    check_dates_agree(research_on, deadline)
    card_id = args.id or slugify(args.title)
    directory = card_dir(root, card_id)
    brief_text = read_text_file(args.brief) if args.brief else None
    directory.parent.mkdir(parents=True, exist_ok=True)
    try:
        directory.mkdir()
    except FileExistsError as exc:
        raise BoardError(f"card exists: {card_id}") from exc
    (directory / "briefs").mkdir()
    card = {"id": card_id, "title": args.title.strip(), "idea": args.idea.strip(), "kind": args.kind,
            "owner": args.owner, "scope": args.scope, "deadline": deadline, "research_on": research_on,
            "priority": priority, "tags": args.tags or [], "created": wr.iso_utc(now_utc())}
    (directory / "card.json").write_text(json.dumps(card, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with card_lock(directory):
        append_event(directory, "created", args.actor)
        if brief_text:
            record_brief(directory, brief_text, args.actor, None)
    return card_id


def record_brief(directory: pathlib.Path, text: str, actor: str, run_id: str | None) -> str:
    digest = text_hash(text)
    (directory / "briefs" / f"{digest}.md").write_text(normalise(text) + "\n", encoding="utf-8")
    append_event(directory, "brief", actor, hash=digest, run_id=run_id)
    return digest


def brief_columns(actor: str) -> frozenset[str]:
    if actor.startswith("run:"):
        return frozenset({"Backlog"})
    return frozenset({"Backlog", "Refine"}) if actor.startswith("buzz:") else _BRIEFABLE


def add_brief(root: pathlib.Path, card_id: str, path: str, actor: str) -> str:
    require_actor(actor, ("dave", "mac:claude", "buzz:*", "run:*"), "write a brief")
    text, directory = read_text_file(path), card_dir(root, card_id)
    with card_lock(directory):
        view, events = fresh_view(root, card_id)
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


def add_note(root: pathlib.Path, card_id: str, path: str, actor: str) -> None:
    require_actor(actor, ("dave", "mac:claude", "buzz:*", "run:*"), "add a note")
    text, directory = read_text_file(path), card_dir(root, card_id)
    with card_lock(directory):
        read_card(root, card_id)
        append_event(directory, "note", actor, fields={"text": normalise(text)},
                     run_id=actor[4:] if actor.startswith("run:") else None)


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
    simple = {"title": args.title, "idea": args.idea}
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
    for flag, name in ((args.research_on, "research_on"), (args.deadline, "deadline")):
        if flag is not None:
            changes[name] = check_date(flag, name)
    if not changes:
        raise BoardError("name at least one field to edit")
    return changes


# --- verbs: pick --------------------------------------------------------------------------
def render_card_md(view: Mapping[str, Any], brief_text: str | None, decisions: list[dict[str, Any]]) -> str:
    fields = view["fields"]
    mine = [d for d in decisions if d.get("card") == view["id"]]
    returned = [d.get("reason", "") for d in reversed(_ordered(mine)) if d["decision"] == "brief_returned"]
    changes = _latest([d for d in mine if d["decision"] == "changes_requested"])
    parts = [f"# {fields['title']}", f"id: {view['id']}", f"owner: {view['owner']}  kind: {view['kind']}",
             f"scope: {', '.join(fields['scope'])}", f"deadline: {fields.get('deadline') or 'none (standing)'}",
             "", "## Idea", "", fields["idea"]]
    if returned:
        parts += ["", "## Returned reasons (newest first)", ""] + [f"- {r}" for r in returned]
    if brief_text:
        parts += ["", "## Approved brief" if view["brief_approved"] else "## Brief", "", brief_text]
    if changes and view["has_research_run"] and view["column"] == "Todo":
        parts += ["", "## Dave's note after a request for changes", "", changes.get("reason", "")]
    return "\n".join(parts) + "\n"


def pick_card(root: pathlib.Path, args: argparse.Namespace) -> str | None:
    require_actor(f"run:{args.run_id}", ("run:*",), "pick")
    purpose = "brief" if args.column == "backlog" else "research"
    views = collect(root)
    for view in views.values():
        for run in view["runs"]:
            if run["run_id"] == args.run_id:
                return view["id"]
    for view in candidates(views, args.column, args.owner, args.kind):
        directory = card_dir(root, view["id"])
        with card_lock(directory):
            fresh, _ = fresh_view(root, view["id"])
            decisions = read_decisions()
            if fresh["column"] != view["column"] or fresh["scheduled"]:
                continue
            brief_text = None
            if fresh["brief_hash"]:
                brief_text = (directory / "briefs" / f"{fresh['brief_hash']}.md").read_text(encoding="utf-8")
                if text_hash(brief_text) != fresh["brief_hash"]:
                    print(f"exception: pick-hash-mismatch {view['id']}", file=sys.stderr)
                    continue
            scratch = root / "runs" / args.run_id
            scratch.mkdir(parents=True, exist_ok=True)
            (scratch / "card.md").write_text(render_card_md(fresh, normalise(brief_text) if brief_text else None, decisions),
                                             encoding="utf-8")
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
    brief = None
    if view["brief_hash"]:
        brief = (card_dir(root, view["id"]) / "briefs" / f"{view['brief_hash']}.md").read_text(encoding="utf-8")
    text = render_card_md(view, normalise(brief) if brief else None, read_decisions())
    state = f"\n## State\n\ncolumn: {view['column']}" + (f" ({view['blocked_cause']})" if view["blocked_cause"] else "")
    return text + state + (f"\noutcome: {view['outcome']}" if view["outcome"] else "") + "\n"


def unapplied(views: Mapping[str, dict[str, Any]], decisions: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [d for d in decisions if d["decision"] == "approved" and d.get("card") in views
            and views[d["card"]]["column"] != "Done"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="board.py", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="verb", required=True)

    def verb(name: str, **kwargs: Any) -> argparse.ArgumentParser:
        return sub.add_parser(name, **kwargs)

    create = verb("create", help="create a card in Backlog (with --brief, also a brief)")
    create.add_argument("--id")
    create.add_argument("--title", required=True)
    create.add_argument("--idea", required=True)
    create.add_argument("--kind", default="research")
    create.add_argument("--owner", required=True)
    create.add_argument("--scope", action="append", required=True)
    create.add_argument("--deadline")
    create.add_argument("--research-on", dest="research_on")
    create.add_argument("--priority")
    create.add_argument("--tags", type=lambda s: [t for t in s.split(",") if t])
    create.add_argument("--brief")
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
    pick = verb("pick", help="before the model: take the top card of a column, write its run card.md")
    pick.add_argument("--owner", required=True)
    pick.add_argument("--kind", default="research")
    pick.add_argument("--column", default="todo", choices=("todo", "backlog"))
    pick.add_argument("--run-id", required=True)
    pick.add_argument("--workflow", required=True)
    edit = verb("edit", help="change a card's fields; refused for agents and for stale revisions")
    edit.add_argument("card")
    edit.add_argument("--expect-rev", type=int, required=True)
    edit.add_argument("--actor", required=True)
    for name in ("title", "idea", "priority", "tags", "research-on", "deadline", "id", "owner", "kind"):
        edit.add_argument(f"--{name}", dest=name.replace("-", "_"))
    edit.add_argument("--scope", action="append")
    land = verb("land", help="write each unlanded approval as one note on agents/<date>-card-<id>")
    land.add_argument("--card")
    verb("sweep", help="land, fetch main, mark pages, raise the card exceptions")
    return parser


def run(args: argparse.Namespace) -> int:
    root = board_root()
    handlers = {
        "create": lambda: print(create_card(root, args)),
        "brief": lambda: print(add_brief(root, args.card, args.file, args.actor)),
        "note": lambda: add_note(root, args.card, args.file, args.actor),
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
