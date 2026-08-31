#!/usr/bin/env python3
"""notion_markdown.py — the single markdown -> Notion blocks converter for this repo.

Two seams, each usable alone: a block-level scanner (blocks_from_markdown) and an
inline-span parser (rich_text). Pure and offline — markdown in, block dicts out; no
HTTP, no token, no filesystem.

It exists because there were two partial converters (notion_daily, ops_page_publish),
neither of which rendered inline marks or tables, and agent_inbox_notion_sync needed a
third. Both now delegate here.

The four Notion limits encoded below all fail silently or with an unhelpful 400:
rich_text content is capped at 2000 chars, a block at 100 rich_text elements, a
table_row's cells must number exactly table_width, and an unknown code language is
rejected outright.
"""
import re

FORMAT_VERSION = 3
CHUNK = 1900
MAX_SPANS = 100
MAX_HEADING = 3
CODE_LANGUAGE = "plain text"

INLINE = re.compile(
    r"(?P<code>`[^`\n]+`)"
    r"|(?P<wiki>\[\[[^\]\n]*\]\])"
    r"|(?P<link>\[[^\]\n]*\]\([^)\s]+\))"
    r"|(?P<autolink><https?://[^>\s]+>)"
    r"|(?P<bolditalic>\*\*\*(?=\S)[^\n]*?(?<=\S)\*\*\*)"
    r"|(?P<bold>\*\*(?=\S)[^\n]*?(?<=\S)\*\*)"
    r"|(?P<istar>\*(?=[^\s*])[^\n]*?(?<=[^\s*])\*(?!\*))"
    r"|(?P<iunder>(?<![A-Za-z0-9_])_(?=[^\s_])[^_\n]+(?<=[^\s_])_(?![A-Za-z0-9_]))"
    r"|(?P<url>https?://[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'\"])"
)
HEADING = re.compile(r"^(#{1,6})\s+(.*)$")
NUMBERED = re.compile(r"^\d+\.\s+(.*)$")
DIVIDER = re.compile(r"^-{3,}$")
FENCE = re.compile(r"^(`{3,})")
SEPARATOR_CELL = re.compile(r"^:?-+:?$")
CONTINUING = ("paragraph", "bulleted_list_item", "numbered_list_item", "quote")


def _span(content, annotations=None, link=None):
    text = {"content": content}
    if link:
        text["link"] = {"url": link}
    span = {"type": "text", "text": text}
    if annotations:
        span["annotations"] = dict(annotations)
    return span


def _marked(annotations, name):
    return dict(annotations or {}, **{name: True})


def _expand(match, annotations, link):
    kind, raw = match.lastgroup, match.group()
    if kind == "code":
        return [_span(raw[1:-1], _marked(annotations, "code"), link)]
    if kind == "wiki":
        return [_span(raw, annotations, link)]
    if kind == "link":
        split = raw.rindex("](")
        return _spans(raw[1:split], annotations, raw[split + 2:-1])
    if kind == "autolink":
        return [_span(raw[1:-1], annotations, raw[1:-1])]
    if kind == "url":
        return [_span(raw, annotations, raw)]
    if kind == "bolditalic":
        return _spans(raw[3:-3], _marked(_marked(annotations, "bold"), "italic"), link)
    if kind == "bold":
        return _spans(raw[2:-2], _marked(annotations, "bold"), link)
    return _spans(raw[1:-1], _marked(annotations, "italic"), link)


def _spans(text, annotations=None, link=None):
    out, pos = [], 0
    for match in INLINE.finditer(text):
        if match.start() > pos:
            out.append(_span(text[pos:match.start()], annotations, link))
        out.extend(_expand(match, annotations, link))
        pos = match.end()
    if pos < len(text):
        out.append(_span(text[pos:], annotations, link))
    return [s for s in out if s["text"]["content"]]


def _chunked(spans):
    out = []
    for span in spans:
        content = span["text"]["content"]
        if len(content) <= CHUNK:
            out.append(span)
            continue
        for i in range(0, len(content), CHUNK):
            out.append(dict(span, text=dict(span["text"], content=content[i:i + CHUNK])))
    return out


def _fit(spans):
    """Merge the tail into one unannotated span rather than letting the request 400."""
    spans = _chunked(spans)
    if len(spans) <= MAX_SPANS:
        return spans
    for keep in range(MAX_SPANS - 1, -1, -1):
        merged = _chunked([_span("".join(s["text"]["content"] for s in spans[keep:]))])
        if keep + len(merged) <= MAX_SPANS:
            return spans[:keep] + merged
    return spans[:MAX_SPANS]


def rich_text(text):
    return _fit(_spans(text or "")) or [_span("")]


def plain_rich_text(text):
    """Chunk only — for content that must survive verbatim, such as a code fence."""
    return _chunked([_span(text or "")])[:MAX_SPANS]


def text_block(kind, text):
    return {"object": "block", "type": kind, kind: {"rich_text": rich_text(text)}}


def divider_block():
    return {"object": "block", "type": "divider", "divider": {}}


def opening_block(text):
    """(kind, text) when the line opens a block; None when it may continue the one above."""
    head = HEADING.match(text)
    if head:
        return "heading_%d" % min(len(head.group(1)), MAX_HEADING), head.group(2)
    if text.startswith(("- ", "* ", "+ ")):
        return "bulleted_list_item", text[2:]
    numbered = NUMBERED.match(text)
    if numbered:
        return "numbered_list_item", numbered.group(1)
    if text.startswith(">"):
        return "quote", text[1:].lstrip()
    return None


def _code_block(text):
    return {"object": "block", "type": "code",
            "code": {"language": CODE_LANGUAGE, "rich_text": plain_rich_text(text)}}


def _split_row(line):
    text = line.strip()
    if text.startswith("|"):
        text = text[1:]
    if text.endswith("|"):
        text = text[:-1]
    return [cell.strip() for cell in text.split("|")]


def _is_separator(line):
    if "|" not in line:
        return False
    cells = _split_row(line)
    return bool(cells) and all(SEPARATOR_CELL.match(c) for c in cells)


def _table_row(cells, width):
    fitted = (list(cells) + [""] * width)[:width]
    return {"object": "block", "type": "table_row",
            "table_row": {"cells": [rich_text(c) for c in fitted]}}


def _consume_table(lines, start):
    header = _split_row(lines[start])
    rows, i = [header], start + 2
    while i < len(lines) and lines[i].strip() and "|" in lines[i]:
        rows.append(_split_row(lines[i]))
        i += 1
    width = len(header)
    block = {"object": "block", "type": "table",
             "table": {"table_width": width, "has_column_header": True,
                       "has_row_header": False,
                       "children": [_table_row(r, width) for r in rows]}}
    return block, i


def _consume_fence(lines, start):
    closer = re.compile(r"^`{%d,}\s*$" % len(FENCE.match(lines[start].strip()).group(1)))
    body, i = [], start + 1
    while i < len(lines) and not closer.match(lines[i].strip()):
        body.append(lines[i])
        i += 1
    return _code_block("\n".join(body)), min(i + 1, len(lines))


def _flushed(blocks, pending):
    if pending:
        kind, parts = pending
        blocks.append(text_block(kind, " ".join(parts)))
    return None


def blocks_from_markdown(md):
    """Markdown to Notion blocks, joining a hard-wrapped paragraph back into one block.

    The proposals this renders are wrapped at ~90 columns, so a bold span or a link
    routinely opens on one line and closes on the next. A line-per-block scanner leaves
    both halves unmatched and prints the markers literally.
    """
    lines = (md or "").splitlines()
    blocks, pending, i = [], None, 0
    while i < len(lines):
        text = lines[i].strip()
        if not text:
            pending = _flushed(blocks, pending)
            i += 1
        elif FENCE.match(text):
            pending = _flushed(blocks, pending)
            block, i = _consume_fence(lines, i)
            blocks.append(block)
        elif "|" in text and i + 1 < len(lines) and _is_separator(lines[i + 1]):
            pending = _flushed(blocks, pending)
            block, i = _consume_table(lines, i)
            blocks.append(block)
        elif DIVIDER.match(text):
            pending = _flushed(blocks, pending)
            blocks.append(divider_block())
            i += 1
        else:
            pending = _opened(blocks, pending, text)
            i += 1
    _flushed(blocks, pending)
    return blocks


def _opened(blocks, pending, text):
    opening = opening_block(text)
    if not opening:
        if pending:
            pending[1].append(text)
            return pending
        return ("paragraph", [text])
    kind, content = opening
    if kind == "quote" and not content:
        return _flushed(blocks, pending)
    if pending and pending[0] == "quote" == kind:
        pending[1].append(content)
        return pending
    pending = _flushed(blocks, pending)
    if kind in CONTINUING:
        return (kind, [content])
    blocks.append(text_block(kind, content))
    return None
