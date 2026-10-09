#!/usr/bin/env python3
"""The card's research page as the popup reads it: Notion export, and the brief's acceptance
lines paired with the page's MET / PARTLY / NOT MET answers (Dev Plan B4, spec §3.8, §3.7).

`export_page` shells out to bin/notion_research.py, the only Notion reader for card pages; the
Control Room never calls Notion itself. Reads only: `mark` and `publish` are never invoked here.
"""
from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys
import tempfile
from typing import Any, Callable

HERE = pathlib.Path(__file__).resolve().parent
ITEM = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+(\S.*)$")
VERDICT = re.compile(r"\b(NOT MET|PARTLY|MET)\b")
EXPORT_TIMEOUT = 25

Exporter = Callable[[str], "dict[str, Any] | None"]


class ExportError(Exception):
    pass


def export_page(card_id: str) -> dict[str, Any] | None:
    """{page, url, page_hash, published_hash, text}, or None when the card has no page."""
    with tempfile.TemporaryDirectory() as scratch:
        out = pathlib.Path(scratch) / "page.md"
        try:
            done = subprocess.run(
                [sys.executable, str(HERE / "notion_research.py"), "export", "--card", card_id,
                 "--if-exists", "--out", str(out)],
                capture_output=True, text=True, timeout=EXPORT_TIMEOUT, check=False, env=os.environ.copy())
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExportError(f"{type(exc).__name__}: {exc}") from exc
        if done.returncode != 0:
            lines = (done.stderr or done.stdout).strip().splitlines()
            raise ExportError(lines[-1] if lines else f"exit {done.returncode}")
        try:
            meta = json.loads(done.stdout)
        except ValueError as exc:
            raise ExportError("export printed no JSON") from exc
        if not meta.get("page"):
            return None
        return {"page": meta["page"], "url": meta.get("url"), "page_hash": meta.get("page_hash"),
                "published_hash": meta.get("published_hash") or None,
                "text": out.read_text(encoding="utf-8") if out.exists() else ""}


def section_items(text: str, heading: str) -> list[str]:
    items, inside = [], False
    for line in text.splitlines():
        if line.startswith("## "):
            inside = line[3:].strip().lower().startswith(heading)
        elif inside and (match := ITEM.match(line)):
            items.append(match.group(1).strip())
    return items


def acceptance(brief_text: str | None, page_text: str) -> list[dict[str, Any]]:
    lines = section_items(brief_text or "", "acceptance")
    answers = section_items(page_text, "acceptance")
    rows = []
    for index, line in enumerate(lines):
        answer = answers[index] if index < len(answers) else None
        verdict = VERDICT.search(answer) if answer else None
        rows.append({"line": line, "answer": verdict.group(1) if verdict else None, "note": answer})
    return rows
