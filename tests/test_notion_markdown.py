#!/usr/bin/env python3
"""
Offline unit test for bin/notion_markdown.py — the single markdown -> Notion blocks
converter. Driven from tests/test_notion_markdown.sh so bin/verify.sh picks it up.

Pure and offline by construction: the module under test does no HTTP, reads no token
and touches no filesystem, so there is nothing to stub. What is pinned here is the
rendering contract the agent-inbox proposal bodies depend on, plus the four Notion
limits that fail silently rather than with a helpful error (2000-char rich_text,
100 rich_text elements per block, exact table_width, known code languages).
"""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("notion_markdown",
                                               ROOT / "bin" / "notion_markdown.py")
nm = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nm)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


def spans(block):
    return block[block["type"]]["rich_text"]


def plain(block):
    return "".join(s["text"]["content"] for s in spans(block))


def marks(text):
    """name -> annotations dict, for every annotated span in a one-line render."""
    out = {}
    for s in spans(nm.blocks_from_markdown(text)[0]):
        out[s["text"]["content"]] = s.get("annotations", {})
    return out


def link_of(text, content):
    for s in spans(nm.blocks_from_markdown(text)[0]):
        if s["text"]["content"] == content:
            return (s["text"].get("link") or {}).get("url")
    return "<no such span: %r>" % content


print("--- block level: one case per markdown construct ---")
BLOCK_CASES = [
    ("# Title", "heading_1", "Title"),
    ("## Section", "heading_2", "Section"),
    ("### Sub", "heading_3", "Sub"),
    ("#### Deeper than Notion goes", "heading_3", "Deeper than Notion goes"),
    ("- item", "bulleted_list_item", "item"),
    ("* item", "bulleted_list_item", "item"),
    ("    - nested in the source", "bulleted_list_item", "nested in the source"),
    ("1. first", "numbered_list_item", "first"),
    ("12. twelfth", "numbered_list_item", "twelfth"),
    ("> quoted", "quote", "quoted"),
    ("just a line", "paragraph", "just a line"),
    ("| a | b | no separator follows", "paragraph", "| a | b | no separator follows"),
]
for src, kind, text in BLOCK_CASES:
    got = nm.blocks_from_markdown(src)
    ok = len(got) == 1 and got[0]["type"] == kind and plain(got[0]) == text
    check("{!r} -> {} {!r}".format(src, kind, text), ok)

for src in ("---", "-----", "  ---  "):
    got = nm.blocks_from_markdown(src)
    check("{!r} -> divider".format(src),
          len(got) == 1 and got[0]["type"] == "divider" and got[0]["divider"] == {})

check("blank lines are dropped", len(nm.blocks_from_markdown("a\n\n\nb")) == 2)
check("empty markdown yields no blocks", nm.blocks_from_markdown("") == [])
check("every block carries object=block",
      all(b["object"] == "block"
          for b in nm.blocks_from_markdown("# h\n- b\n> q\n---\ntext")))

print("--- hard-wrapped source: a paragraph is its lines, not one block per line ---")
WRAPPED = ("The proposals on this box are hard-wrapped, so a paragraph arrives as\n"
           "several source lines and a **span opens on one line and closes on\n"
           "the next**.\n"
           "\n"
           "A blank line still starts a new paragraph.\n")
wrapped = nm.blocks_from_markdown(WRAPPED)
check("wrapped lines join into one paragraph", len(wrapped) == 2)
check("joined on a space, not a newline",
      plain(wrapped[0]).startswith("The proposals on this box are hard-wrapped, so a "
                                   "paragraph arrives as several source lines"))
check("a span wrapping a line break renders, leaving no literal markers",
      "**" not in plain(wrapped[0]))
check("and renders as one bold span",
      any(s.get("annotations", {}).get("bold") and
          s["text"]["content"] == "span opens on one line and closes on the next"
          for s in spans(wrapped[0])))
check("a blank line still separates paragraphs",
      plain(wrapped[1]) == "A blank line still starts a new paragraph.")

check("a link wrapping a line break survives",
      nm.rich_text("see [the vendor\nprofile](https://example.com/x)".replace("\n", " "))
      == nm.rich_text("see [the vendor profile](https://example.com/x)"))

LAZY = "- a bullet that runs past the\n  wrap column\n- second bullet\n"
lazy = nm.blocks_from_markdown(LAZY)
check("a wrapped bullet continues the same list item",
      [b["type"] for b in lazy] == ["bulleted_list_item", "bulleted_list_item"])
check("and carries the continuation text",
      plain(lazy[0]) == "a bullet that runs past the wrap column")

check("a heading never absorbs the line below it",
      [b["type"] for b in nm.blocks_from_markdown("## Heading\nbody text")]
      == ["heading_2", "paragraph"])
for closer in ("# next", "- item", "> quote", "---", "```\ncode\n```"):
    got = nm.blocks_from_markdown("open paragraph\n" + closer)
    check("{!r} closes the paragraph above it".format(closer.split("\n")[0]),
          got[0]["type"] == "paragraph" and plain(got[0]) == "open paragraph")

print("--- tables: width is exact, short rows pad, long rows truncate ---")
TABLE = ("| Claim | Source | Confidence |\n"
         "| --- | --- | --- |\n"
         "| a | b |\n"
         "| a | b | c | d |\n")
tbl = nm.blocks_from_markdown(TABLE)
check("a GFM table renders as one block", len(tbl) == 1 and tbl[0]["type"] == "table")
t = tbl[0]["table"]
check("table_width comes from the header row", t["table_width"] == 3)
check("has_column_header true, has_row_header false",
      t["has_column_header"] is True and t["has_row_header"] is False)
rows = t["children"]
check("the | --- | separator is consumed, not emitted", len(rows) == 3)
check("children are table_row blocks",
      all(r["type"] == "table_row" and r["object"] == "block" for r in rows))
check("every row has exactly table_width cells",
      [len(r["table_row"]["cells"]) for r in rows] == [3, 3, 3])
check("header cells carry their text",
      ["".join(s["text"]["content"] for s in c) for c in rows[0]["table_row"]["cells"]]
      == ["Claim", "Source", "Confidence"])
check("a short row is padded with empty cells",
      ["".join(s["text"]["content"] for s in c) for c in rows[1]["table_row"]["cells"]]
      == ["a", "b", ""])
check("a long row is truncated to table_width",
      ["".join(s["text"]["content"] for s in c) for c in rows[2]["table_row"]["cells"]]
      == ["a", "b", "c"])
check("cells are rich_text arrays, and are inline-parsed",
      nm.blocks_from_markdown("| **h** |\n| --- |\n")[0]["table"]["children"][0]
      ["table_row"]["cells"][0][0]["annotations"]["bold"] is True)
check("a table with a header and no body rows still renders",
      len(nm.blocks_from_markdown("| a | b |\n| --- | --- |\n")[0]["table"]["children"]) == 1)
check("text after a table resumes normal block scanning",
      [b["type"] for b in nm.blocks_from_markdown(TABLE + "\nafter\n")] == ["table", "paragraph"])

print("--- code fences: verbatim, never re-scanned, always a known language ---")
FENCE = ("```python\n"
         "# not a heading\n"
         "| a | b |\n"
         "| --- | --- |\n"
         "- not a bullet\n"
         "**not bold**\n"
         "```\n")
fenced = nm.blocks_from_markdown(FENCE)
check("a fence renders as exactly one code block",
      len(fenced) == 1 and fenced[0]["type"] == "code")
check("language is always 'plain text' (Notion rejects unknown enum values)",
      fenced[0]["code"]["language"] == "plain text")
check("fence content is verbatim — headings, table rows and bullets survive",
      plain(fenced[0]) == "# not a heading\n| a | b |\n| --- | --- |\n"
                          "- not a bullet\n**not bold**")
check("fence content is NOT inline-parsed",
      all("annotations" not in s for s in spans(fenced[0])))
check("blank lines inside a fence are preserved",
      plain(nm.blocks_from_markdown("```\na\n\nb\n```")[0]) == "a\n\nb")
check("an unclosed fence still emits its content",
      [b["type"] for b in nm.blocks_from_markdown("```\nx\n")] == ["code"])
check("text after a fence resumes normal block scanning",
      [b["type"] for b in nm.blocks_from_markdown(FENCE + "\n## after\n")]
      == ["code", "heading_2"])

print("--- inline: the four annotations ---")
check("**bold** sets annotations.bold", marks("**loud**")["loud"].get("bold") is True)
check("*italic* sets annotations.italic", marks("*soft*")["soft"].get("italic") is True)
check("_italic_ sets annotations.italic", marks("_soft_")["soft"].get("italic") is True)
check("`code` sets annotations.code", marks("`ls -l`")["ls -l"].get("code") is True)
check("markers are stripped from the rendered text",
      plain(nm.blocks_from_markdown("a **b** c `d` e")[0]) == "a b c d e")
check("unannotated spans carry no annotations key",
      "annotations" not in spans(nm.blocks_from_markdown("plain")[0])[0])
check("nested marks compose (bold containing code)",
      marks("**a `b` c**")["b"].get("bold") is True
      and marks("**a `b` c**")["b"].get("code") is True)

print("--- inline: underscores in vault paths are NOT italic ---")
for src in ("see 05_knowledge/wms_tms_x.md",
            "05_knowledge/foo_bar and 11_entities/baz_qux"):
    b = nm.blocks_from_markdown(src)[0]
    check("{!r} stays plain".format(src),
          plain(b) == src and all("annotations" not in s for s in spans(b)))

print("--- inline: links ---")
check("[text](url) links the text",
      link_of("see [the doc](https://example.com/d) now", "the doc")
      == "https://example.com/d")
check("[text](url) drops the markdown syntax",
      plain(nm.blocks_from_markdown("see [the doc](https://example.com/d) now")[0])
      == "see the doc now")
check("a marked link text keeps both the mark and the link",
      marks("[**bold link**](https://example.com/x)")["bold link"].get("bold") is True
      and link_of("[**bold link**](https://example.com/x)", "bold link")
      == "https://example.com/x")
check("<https://…> autolinks and loses the angle brackets",
      link_of("ref <https://example.com/a> end", "https://example.com/a")
      == "https://example.com/a")
check("a bare http(s) URL autolinks",
      link_of("ref https://example.com/b end", "https://example.com/b")
      == "https://example.com/b")
check("a bare URL keeps the surrounding text",
      plain(nm.blocks_from_markdown("ref https://example.com/b end")[0])
      == "ref https://example.com/b end")
check("trailing punctuation is not swallowed into the URL",
      link_of("see https://example.com/b.", "https://example.com/b")
      == "https://example.com/b")

print("--- inline: [[wikilink]] stays plain (no resolvable URL exists) ---")
WIKI = "see [[05_knowledge/wms_tms_x]] for context"
wb = nm.blocks_from_markdown(WIKI)[0]
check("wikilink text is preserved verbatim, brackets included", plain(wb) == WIKI)
check("wikilink is not linked", all(not s["text"].get("link") for s in spans(wb)))
check("wikilink is not italicised by its underscores",
      all("annotations" not in s for s in spans(wb)))

print("--- Notion limits: 1900-char chunking and the 100-span cap ---")
check("plain_rich_text chunks over the 2000-char object limit",
      len(nm.plain_rich_text("x" * 4000)) == 3)
check("no chunk exceeds the limit",
      max(len(s["text"]["content"]) for s in nm.plain_rich_text("x" * 4000)) <= 1900)
check("chunking is lossless",
      "".join(s["text"]["content"] for s in nm.plain_rich_text("x" * 4000)) == "x" * 4000)
check("a 1900-char string is a single span", len(nm.plain_rich_text("x" * 1900)) == 1)
check("1901 chars splits in two", len(nm.plain_rich_text("x" * 1901)) == 2)
check("rich_text chunks a long unmarked line too",
      len(nm.rich_text("y" * 4000)) == 3)
check("an annotated span longer than the limit keeps its annotation on every chunk",
      all(s.get("annotations", {}).get("bold") is True
          for s in nm.rich_text("**" + "z" * 4000 + "**")))

MANY = " ".join("**b%d**" % i for i in range(150))
capped = nm.rich_text(MANY)
check("a heavily-marked line is capped at 100 rich_text elements", len(capped) <= 100)
check("capping merges the tail rather than dropping it",
      "".join(s["text"]["content"] for s in capped)
      == " ".join("b%d" % i for i in range(150)))
LONG_MARKED = " ".join("**%s**" % ("w" * 60) for _ in range(40))
check("the corpus worst case (long, heavily marked line) also fits",
      len(nm.rich_text(LONG_MARKED)) <= 100)
check("every block's rich_text respects the cap",
      all(len(spans(b)) <= 100 for b in nm.blocks_from_markdown(MANY + "\n# " + MANY)))

print("--- degradation: a proposal must never fail to render ---")
check("an unterminated table separator degrades to paragraphs",
      [b["type"] for b in nm.blocks_from_markdown("| --- | --- |")] == ["paragraph"])
check("a lone '|' is a paragraph",
      nm.blocks_from_markdown("|")[0]["type"] == "paragraph")
check("an unmatched ** is left as literal text",
      plain(nm.blocks_from_markdown("a ** b")[0]) == "a ** b")
check("None renders as no blocks", nm.blocks_from_markdown(None) == [])

raise SystemExit(1 if failures else 0)
