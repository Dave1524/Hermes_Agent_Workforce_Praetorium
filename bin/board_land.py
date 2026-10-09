#!/usr/bin/env python3
"""Apply and closure for the agent board (Dev Plan B6, spec §3.7 and §3.6.8).

    board.py land  [--card ID]    write each unlanded approval as one note on a card branch
    board.py sweep                fetch main, land, mark pages merged or rejected, raise exceptions

`land` takes the approved text from the broker's stream (decision field `text`), refuses it unless
it hashes to the signed `page_hash`, writes `05_knowledge/research/<id>.md` on
`agents/<date>-card-<id>` cut from a fresh `origin/main` in a throwaway worktree of the canonical
clone, and pushes as whoever the clone's credential helper is (the App). It never writes an event:
Done is the join with `main` (board.derive). A landed card keeps `cards/<id>/landed.json`.

Exceptions go to the incident stream as class `board-exception`, one per card and kind, resolved
when the condition clears. BOARD_NOTION_MARK_CMD overrides the notion_research.py command prefix.
"""
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import re
import shlex
import subprocess
import sys
import tempfile
from typing import Any

import board
import workflow_incidents as wi
import workflow_receipt as wr

INCIDENT_CLASS = "board-exception"
INCIDENT_WORKFLOW = "board-sweep"
STALE_WORKING_DAYS = 3
MERGE_STALE = dt.timedelta(hours=2)
BLOCK_KINDS = {"returned twice": "double-return", "changes requested twice": "double-changes",
               "declined twice": "double-decline", "deadline passed": "expired"}
ACTIONS = {
    "stale-pick": "A pick has no receipt past its timeout; check the run's unit and attempt log.",
    "double-return": "Dave: the brief was returned twice; rewrite the idea or unblock the card.",
    "double-changes": "Dave: changes were requested twice; reject the card or unblock it.",
    "double-decline": "Dave: the research run declined twice; read the declines, then edit or unblock.",
    "expired": "Dave: the deadline passed; move the date or leave the card Blocked.",
    "refine-stale": "Dave: a brief has waited in Refine for three working days; approve, edit or return it.",
    "review-stale": "Dave: a finished page has waited in In Review for three working days; decide it.",
    "land-refused": "The approved text was not landed; read the issue, then re-approve or fix the push.",
    "merge-stale": "Dave: an approved note has not reached main in two watcher cycles; run the Mac merge pass.",
    "forged-decision": "A decision-shaped event is in a card ledger and moved nothing; inspect events.jsonl.",
}


class Refused(Exception):
    """An approval that cannot land; becomes a land-refused exception."""


def incident_root() -> pathlib.Path:
    return pathlib.Path(os.environ.get("CONTROL_ROOM_INCIDENT_ROOT")
                        or pathlib.Path.home() / "agent-workforce" / "var" / "incidents")


def git(clone: pathlib.Path, *args: str, check: bool = True) -> subprocess.CompletedProcess:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    done = subprocess.run(["git", "-C", str(clone), *args], capture_output=True, text=True, env=env, check=False)
    if check and done.returncode:
        raise Refused(f"git {args[0]} failed: {(done.stderr or done.stdout).strip()[:300]}")
    return done


def marker(root: pathlib.Path, card_id: str, name: str) -> pathlib.Path:
    return board.card_dir(root, card_id) / f"{name}.json"


def read_marker(root: pathlib.Path, card_id: str, name: str) -> dict[str, Any] | None:
    try:
        return json.loads(marker(root, card_id, name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def write_marker(root: pathlib.Path, card_id: str, name: str, **data: Any) -> None:
    data["ts"] = wr.iso_utc(board.now_utc())
    marker(root, card_id, name).write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")


def approval_for(view: dict[str, Any], decisions: list[dict[str, Any]]) -> dict[str, Any]:
    mine = [d for d in decisions if d.get("card") == view["id"] and d["decision"] == "approved"
            and d.get("page_hash") == view["approved_hash"]]
    return board._latest(mine) or {}


def brief_question(root: pathlib.Path, view: dict[str, Any]) -> str:
    path = board.card_dir(root, view["id"]) / "briefs" / f"{view['brief_hash']}.md"
    match = re.search(r"^## Question\s*\n(.*?)(?=^## |\Z)", path.read_text(encoding="utf-8"), re.M | re.S)
    return " ".join(match.group(1).split()) if match else ""


def page_url(view: dict[str, Any]) -> tuple[str, str]:
    live = [r for r in view["runs"] if not r["void"] and r["page"]]
    if not live:
        raise Refused("no run of this card published a page")
    page = live[-1]["page"]
    return (page if page.startswith("http") else "https://www.notion.so/" + page.replace("-", "")), live[-1]["run_id"]


def render_note(root: pathlib.Path, view: dict[str, Any], approval: dict[str, Any]) -> str:
    text = approval.get("text")
    if not isinstance(text, str) or board.text_hash(text) != approval.get("page_hash"):
        raise Refused("the approved text is missing or does not hash to the signed page_hash")
    url, run_id = page_url(view)
    lines = {"type": "research", "card": view["id"], "title": json.dumps(view["fields"]["title"]),
             "question": json.dumps(brief_question(root, view)), "tags": json.dumps(view["fields"]["tags"]),
             "approved": approval["ts"][:10], "notion": url, "run": run_id,
             "brief": view["brief_hash"], "content": approval["page_hash"]}
    front = "\n".join(f"{k}: {v}" for k, v in lines.items())
    return f"---\n{front}\n---\n{board.normalise(text)}\n"


def branch_for(card_id: str, approval: dict[str, Any]) -> str:
    return f"agents/{approval['ts'][:10]}-card-{card_id}"


def has_remote_branch(clone: pathlib.Path, card_id: str) -> bool:
    listed = git(clone, "ls-remote", "--heads", "origin", f"refs/heads/agents/*-card-{card_id}").stdout
    return bool(listed.strip())


def commit_identity(clone: pathlib.Path) -> list[str]:
    if git(clone, "config", "user.email", check=False).stdout.strip():
        return []
    return ["-c", "user.name=praetorium-vault-writer[bot]", "-c", "user.email=praetorium@users.noreply.invalid"]


def push_note(clone: pathlib.Path, card_id: str, note: str, branch: str) -> str:
    git(clone, "fetch", "-q", "origin", "main")
    work = pathlib.Path(tempfile.mkdtemp(prefix=f"board-land-{card_id}-"))
    try:
        git(clone, "worktree", "add", "-q", "--detach", str(work), "origin/main")
        target = work / board.RESEARCH_NOTE_DIR / f"{card_id}.md"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(note, encoding="utf-8")
        git(work, "add", f"{board.RESEARCH_NOTE_DIR}/{card_id}.md")
        git(work, *commit_identity(clone), "commit", "-q", "-m",
            f"research({card_id}): the approved note\n\nLanded from the board; Dave's approval is the only human step.")
        git(work, "push", "-q", "origin", f"HEAD:refs/heads/{branch}")
        return git(work, "rev-parse", "HEAD").stdout.strip()
    finally:
        git(clone, "worktree", "remove", "--force", str(work), check=False)
        git(clone, "worktree", "prune", check=False)


def land_card(root: pathlib.Path, view: dict[str, Any], decisions: list[dict[str, Any]]) -> str | None:
    card_id = view["id"]
    approval = approval_for(view, decisions)
    with board.card_lock(board.card_dir(root, card_id)):
        done = read_marker(root, card_id, "landed")
        if done and done.get("page_hash") == view["approved_hash"]:
            return None
        note = render_note(root, view, approval)
        clone = board.canonical_clone()
        if not clone.is_dir():
            raise Refused(f"no canonical clone at {clone}")
        branch = branch_for(card_id, approval)
        sha = "" if has_remote_branch(clone, card_id) else push_note(clone, card_id, note, branch)
        write_marker(root, card_id, "landed", branch=branch, sha=sha, page_hash=view["approved_hash"])
        return f"landed {card_id} {branch} {sha[:12]}".rstrip()


def landable(views: dict[str, dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    return [v for v in views.values() if v["approved_landing"] and v["approved_hash"]
            and (only is None or v["id"] == only)]


def land(root: pathlib.Path, only: str | None = None) -> tuple[list[str], list[dict[str, str]]]:
    if only:
        board.read_card(root, only)
    decisions, views = board.read_decisions(), board.collect(root)
    landed: list[str] = []
    raised: list[dict[str, str]] = []
    for view in landable(views, only):
        try:
            line = land_card(root, view, decisions)
        except Refused as exc:
            raised.append({"card": view["id"], "kind": "land-refused", "issue": str(exc)})
            continue
        landed += [line] if line else []
    return landed, raised


# --- sweep --------------------------------------------------------------------------------
def working_days_between(since: dt.datetime, now: dt.datetime) -> int:
    day, count = since.date(), 0
    while day < now.date():
        day += dt.timedelta(days=1)
        count += day.weekday() < 5
    return count


def card_exceptions(view: dict[str, Any], events: list[dict[str, Any]], landed: dict[str, Any] | None,
                    now: dt.datetime) -> list[dict[str, str]]:
    found = [{"kind": e["kind"], "issue": f"{e['kind']} on {view['id']}"} for e in view["exceptions"]]
    cause = BLOCK_KINDS.get(view["blocked_cause"] or "")
    if cause:
        found.append({"kind": cause, "issue": f"{view['id']} is Blocked: {view['blocked_cause']}"})
    if view["column"] == "Refine":
        briefs = [board._t(e["ts"]) for e in events if e.get("event") == "brief"]
        if briefs and working_days_between(max(briefs), now) >= STALE_WORKING_DAYS:
            found.append({"kind": "refine-stale", "issue": f"{view['id']} has waited in Refine since {max(briefs):%Y-%m-%d}"})
    if view["column"] == "In Review" and not view["approved_landing"] and view["runs"]:
        since = board._t(view["runs"][-1]["ts"])
        if working_days_between(since, now) >= STALE_WORKING_DAYS:
            found.append({"kind": "review-stale", "issue": f"{view['id']} has waited in In Review since {since:%Y-%m-%d}"})
    if view["approved_landing"] and landed and now - board._t(landed["ts"]) >= MERGE_STALE:
        found.append({"kind": "merge-stale", "issue": f"{view['id']} landed on {landed.get('branch')} and is not on main"})
    return found


def notion_mark(card_id: str, state: str, path: str | None) -> bool:
    prefix = shlex.split(os.environ.get("BOARD_NOTION_MARK_CMD") or "")
    prefix = prefix or [sys.executable, str(pathlib.Path(__file__).with_name("notion_research.py"))]
    argv = [*prefix, "mark", "--card", card_id, "--state", state] + (["--path", path] if path else [])
    return subprocess.run(argv, capture_output=True, text=True, check=False).returncode == 0


def mark_pages(root: pathlib.Path, views: dict[str, dict[str, Any]]) -> list[str]:
    marked = []
    for view in views.values():
        state = {"merged": "merged", "rejected": "rejected"}.get(view["outcome"] or "")
        if view["column"] != "Done" or not state or not any(r["page"] for r in view["runs"]):
            continue
        if (read_marker(root, view["id"], "marked") or {}).get("state") == state:
            continue
        path = f"{board.RESEARCH_NOTE_DIR}/{view['id']}.md" if state == "merged" else None
        if notion_mark(view["id"], state, path):
            write_marker(root, view["id"], "marked", state=state)
            marked.append(f"marked {view['id']} {state}")
    return marked


def publish(raised: list[dict[str, str]], owners: dict[str, str]) -> list[str]:
    state, lines, current = incident_root(), [], set()
    for item in raised:
        incident = {"class": INCIDENT_CLASS, "workflow_id": INCIDENT_WORKFLOW, "id": f"{item['kind']}:{item['card']}",
                    "agent": owners.get(item["card"]), "issue": item["issue"],
                    "required_action": ACTIONS[item["kind"]], "evidence": [f"board://{item['card']}"]}
        wi.declare(state, incident)
        current.add(wi.key(INCIDENT_CLASS, INCIDENT_WORKFLOW, incident["id"]))
        lines.append(f"exception {item['kind']} {item['card']}")
    open_items, _ = wi.load_declared(state)
    for old in open_items:
        if old["class"] == INCIDENT_CLASS and old.get("resolved_at") is None and old["key"] not in current:
            wi.resolve_declared(state, old["key"])
            lines.append(f"resolved {old['key']}")
    return lines


def sweep(root: pathlib.Path) -> list[str]:
    clone = board.canonical_clone()
    if clone.is_dir():
        git(clone, "fetch", "-q", "origin", "main", check=False)
    landed, raised = land(root)
    views, now = board.collect(root), dt.datetime.now().astimezone()
    for view in views.values():
        _, events = board.read_card(root, view["id"])
        raised += [{"card": view["id"], **e} for e in card_exceptions(view, events, read_marker(root, view["id"], "landed"), now)]
    unique = list({(r["card"], r["kind"]): r for r in raised}.values())
    owners = {v["id"]: v["owner"] for v in views.values()}
    return landed + mark_pages(root, views) + publish(unique, owners)
