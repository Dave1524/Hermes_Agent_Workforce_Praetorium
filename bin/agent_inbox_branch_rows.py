#!/usr/bin/env python3
"""agent_inbox_branch_rows.py — git side + body composition for branch-shaped rows.

The Agent Inbox DB holds two row shapes. Inbox-file rows (Filename = *.md under
_inbox/agents/) are what agent_inbox_notion_sync.py creates and body-fills; branch-shaped
rows (Filename = agents/<date>-<slug>, a branch on the canonical vault clone, registered
by hand by interactive sessions) were structurally invisible to those globs and sat with
an empty body forever. This module owns everything git about them: qualifying the
Filename, resolving the branch tip, extracting the diff summary and added documents, and
composing the Notion body blocks. No Notion I/O here — the sync passes the blocks to its
own writer, so tests can exercise composition against a temp git repo without any HTTP.

Git access is best-effort by contract: the unattended unit must keep syncing inbox files
when the canonical remote is unreachable (the box holds no guaranteed canonical
credential), so every subprocess failure degrades to None instead of raising.
"""
import os
import re
import subprocess

import notion_markdown

CANONICAL_REPO = os.path.expanduser("~/dev/Obsidian_AI_Operating_System")
COMPARE_BASE = "https://github.com/Dave1524/Obsidian_AI_Operating_System/compare/main..."
BRANCH_ROW_RE = re.compile(r"^agents/\d{4}-\d{2}-\d{2}-[A-Za-z0-9._-]+$")
GIT_TIMEOUT = 60


def is_branch_row(filename):
    return bool(BRANCH_ROW_RE.match(filename or ""))


def _git(*args):
    try:
        proc = subprocess.run(["git", "-C", CANONICAL_REPO, *args],
                              capture_output=True, text=True, timeout=GIT_TIMEOUT,
                              env=dict(os.environ, GIT_TERMINAL_PROMPT="0"))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return proc.stdout if proc.returncode == 0 else None


def fetch_branches():
    """One fetch per run; on failure the local origin/agents/* refs stay the source."""
    _git("fetch", "-q", "origin", "+refs/heads/agents/*:refs/remotes/origin/agents/*")


def resolve_tip(branch):
    """(ref, sha12) for the branch tip, or None when no ref resolves."""
    for ref in ("origin/" + branch, branch):
        sha = _git("rev-parse", "--verify", "--quiet", ref)
        if sha and sha.strip():
            return ref, sha.strip()[:12]
    return None


def _diff_base():
    for ref in ("origin/main", "main"):
        if _git("rev-parse", "--verify", "--quiet", ref):
            return ref
    return None


def diff_stat(ref):
    base = _diff_base()
    out = _git("diff", "--stat=200", "%s...%s" % (base, ref)) if base else None
    return [line.strip() for line in (out or "").splitlines() if line.strip()]


def added_docs(ref):
    base = _diff_base()
    out = _git("diff", "--name-status", "--diff-filter=A",
               "%s...%s" % (base, ref)) if base else None
    return [line.split("\t", 1)[1] for line in (out or "").splitlines()
            if "\t" in line and line.split("\t", 1)[1].endswith(".md")]


def doc_text(ref, path):
    return _git("show", "%s:%s" % (ref, path)) or ""


def _bullet(text):
    return {"object": "block", "type": "bulleted_list_item",
            "bulleted_list_item": {"rich_text": notion_markdown.plain_rich_text(text)}}


def _heading(kind, spans):
    return {"object": "block", "type": kind, kind: {"rich_text": spans}}


def provenance_blocks(branch, box_link):
    link = box_link or COMPARE_BASE + branch
    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": "Source: branch "}},
        {"type": "text", "text": {"content": branch}, "annotations": {"code": True}},
        {"type": "text", "text": {"content": " of Obsidian_AI_Operating_System — "}},
        {"type": "text", "text": {"content": "view compare on GitHub",
                                  "link": {"url": link}}},
        {"type": "text",
         "text": {"content": " (private repo; the primary documents are below)."}},
    ]}}, notion_markdown.divider_block()]


def _changes_blocks(ref):
    head = _heading("heading_2",
                    notion_markdown.plain_rich_text("Changes in this proposal"))
    stat = diff_stat(ref)
    if not stat:
        note = {"object": "block", "type": "paragraph", "paragraph": {"rich_text":
                notion_markdown.plain_rich_text(
                    "No changes against main — the branch is fully merged.")}}
        return [head, note, notion_markdown.divider_block()]
    return [head] + [_bullet(line) for line in stat] + [notion_markdown.divider_block()]


def _doc_blocks(ref, path):
    head = _heading("heading_1", [{"type": "text", "text": {"content": path},
                                   "annotations": {"code": True}}])
    return ([head] + notion_markdown.blocks_from_markdown(doc_text(ref, path))
            + [notion_markdown.divider_block()])


def body_blocks(branch, ref, box_link):
    """The body WITHOUT its sentinel — the sync appends its own, keyed <branch>@<sha12>."""
    blocks = provenance_blocks(branch, box_link) + _changes_blocks(ref)
    for path in added_docs(ref):
        blocks += _doc_blocks(ref, path)
    return blocks
