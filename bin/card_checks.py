#!/usr/bin/env python3
"""The board-join checks of design/contracts/standing-research.md (Dev Plan B3), one verb each.

    card_checks.py page-names-card | published-is-this-run | acceptance-answered | pick-hash-matched

Run from a contract check block, which hands over exactly the executor's environment:
AGENT_CARD, AGENT_CARD_DIR and BOARD_ROOT. Exit 0 passes, 77 is "not applicable" (no card, or
the run wrote no page text), anything else prints the reason and fails. The wrapper
(agent_propose.sh) writes `pick.json` before the model and `published.json` after the publish.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys

NOT_APPLICABLE = 77
ITEM = re.compile(r"^\s*(?:[-*+]|\d+\.)\s+\S")
VERDICT = re.compile(r"\b(?:NOT MET|PARTLY|MET)\b")


class Fail(Exception):
    pass


class NotApplicable(Exception):
    pass


def environment() -> tuple[str, pathlib.Path, pathlib.Path]:
    card = os.environ.get("AGENT_CARD", "")
    if not card:
        raise NotApplicable("no card this run")
    directory = pathlib.Path(os.environ.get("AGENT_CARD_DIR", ""))
    if not (directory / "research.md").is_file():
        raise NotApplicable("no page text this run")
    return card, directory, pathlib.Path(os.environ.get("BOARD_ROOT", ""))


def read_json(path: pathlib.Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise Fail(f"{path.name} unreadable: {exc}")


def board_hash(text: str) -> str:
    """bin/board.py's text_hash, restated so a check does not import the ledger it audits."""
    return hashlib.sha256(text.replace("\r\n", "\n").replace("\r", "\n").rstrip().encode("utf-8")).hexdigest()


def section(text: str, heading: str) -> list[str]:
    lines, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith(heading)
        elif inside:
            lines.append(line)
    return lines


def page_names_card() -> None:
    card, directory, _ = environment()
    published = read_json(directory / "published.json")
    if published.get("card") != card or not published.get("page"):
        raise Fail(f"published.json names card {published.get('card')!r} and page "
                   f"{published.get('page')!r}, not {card!r} with a page")


def published_is_this_run() -> None:
    _, directory, _ = environment()
    want = board_hash((directory / "research.md").read_text(encoding="utf-8"))
    got = read_json(directory / "published.json").get("page_hash")
    if got != want:
        raise Fail(f"published hash {got} is not the hash of research.md ({want})")


def acceptance_answered() -> None:
    card, directory, root = environment()
    brief_hash = read_json(directory / "published.json").get("brief_hash")
    try:
        brief = (root / "cards" / card / "briefs" / f"{brief_hash}.md").read_text(encoding="utf-8")
    except OSError as exc:
        raise Fail(f"the brief {brief_hash!r} is not in the ledger: {exc}")
    asked = sum(1 for line in section(brief, "acceptance") if ITEM.match(line))
    research = (directory / "research.md").read_text(encoding="utf-8")
    answered = sum(1 for line in section(research, "acceptance")
                   if ITEM.match(line) and len(VERDICT.findall(line)) == 1)
    if asked == 0 or asked != answered:
        raise Fail(f"the brief has {asked} acceptance line(s) and research.md answers {answered}")


def pick_hash_matched() -> None:
    _, directory, _ = environment()
    picked = read_json(directory / "pick.json").get("brief_hash")
    published = read_json(directory / "published.json").get("brief_hash")
    if not picked or picked != published:
        raise Fail(f"picked on brief {picked!r}, published against {published!r}")


CHECKS = {"page-names-card": page_names_card, "published-is-this-run": published_is_this_run,
          "acceptance-answered": acceptance_answered, "pick-hash-matched": pick_hash_matched}


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if len(argv) != 1 or argv[0] not in CHECKS:
        print(f"usage: card_checks.py {' | '.join(CHECKS)}", file=sys.stderr)
        return 2
    try:
        CHECKS[argv[0]]()
    except NotApplicable as why:
        print(f"n/a: {why}")
        return NOT_APPLICABLE
    except Fail as why:
        print(why)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
