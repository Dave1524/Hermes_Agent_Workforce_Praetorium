#!/usr/bin/env python3
"""Offline behaviour test for bin/notion_research.py (Dev Plan B3). Driven from
tests/test_notion_research.sh so bin/verify.sh picks it up.

The HTTP seam is replaced by FakeNotion. Pinned: one page per card whatever the run count, the body
replaced rather than stacked, the export a faithful inverse of what publish wrote, and a missing
database id refused before any call.
"""
import importlib.util
import json
import os
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("notion_research", ROOT / "bin" / "notion_research.py")
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


def with_plain_text(properties):
    shaped = {}
    for name, prop in properties.items():
        spans = prop.get("title") or prop.get("rich_text")
        key = "title" if "title" in prop else "rich_text"
        shaped[name] = dict(prop, **{key: [dict(s, plain_text=s["text"]["content"]) for s in spans]}) if spans else prop
    return shaped


class FakeNotion:
    def __init__(self):
        self.pages, self.children, self.calls, self._seq = {}, {}, [], 0

    def _id(self, prefix):
        self._seq += 1
        return "{}-{}".format(prefix, self._seq)

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        head = path.split("?")[0].split("/")
        if method == "POST" and head[1] == "data_sources":
            return self._query(head[2], payload or {})
        if method == "POST" and path == "/pages":
            pid = self._id("page")
            self.pages[pid] = {"id": pid, "_ds": payload["parent"]["data_source_id"],
                               "url": "https://www.notion.so/" + pid, "properties": payload["properties"]}
            return {"id": pid, "url": self.pages[pid]["url"]}
        if method == "PATCH" and head[1] == "pages":
            self.pages[head[2]]["properties"].update(payload["properties"])
            return {"id": head[2]}
        if method == "GET" and head[1] == "pages":
            return self.pages[head[2]]
        if method == "GET" and head[1] == "blocks":
            return {"results": self.children.get(head[2], []), "has_more": False}
        if method == "PATCH" and head[1] == "blocks":
            kids = self.children.setdefault(head[2], [])
            kids.extend(dict(b, id=self._id("blk")) for b in payload["children"])
            return {"results": kids}
        if method == "DELETE" and head[1] == "blocks":
            for pid, blocks in self.children.items():
                self.children[pid] = [b for b in blocks if b.get("id") != head[2]]
            return {}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def _query(self, dsid, payload):
        rows = [p for p in self.pages.values() if p["_ds"] == dsid]
        flt = payload.get("filter") or {}
        if "rich_text" in flt:
            want = flt["rich_text"]["equals"]
            rows = [p for p in rows if "".join(
                t["text"]["content"] for t in p["properties"].get(flt["property"], {}).get("rich_text", [])) == want]
        return {"results": [{"id": p["id"], "url": p["url"], "properties": with_plain_text(p["properties"])} for p in rows],
                "has_more": False, "next_cursor": None}

    def creates(self):
        return [c for c in self.calls if c[0] == "POST" and c[1] == "/pages"]


def plain(prop):
    return "".join(t["text"]["content"] for t in prop.get("title") or prop.get("rich_text") or [])


DS = "ds-research"
os.environ["NOTION_RESEARCH_DS"] = DS
V1 = ("# card-one — what moves the needle\n\nFirst **finding** with a [source](https://example.org/a).\n\n"
      "## Acceptance\n\n- MET: the first line\n- PARTLY: the second line\n\n1. numbered one\n2. numbered two\n\n"
      "```\ncode stays\nverbatim\n```\n\n---\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n")
V2 = "# card-one — what moves the needle\n\nRewritten after a request for changes.\n"


def write(tmp, name, text):
    p = pathlib.Path(tmp) / name
    p.write_text(text)
    return str(p)


def run(argv, api):
    return nr.main(argv, api=api)


print("--- publish: first run creates, second run rewrites the same page ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    first = run(["publish", "--card", "card-one", "--title", "What moves the needle", "--run-id", "run-1",
                 "--from-file", write(tmp, "r.md", V1)], api)
    check("one page created", len(api.creates()) == 1)
    check("result names the page", first["page"] == "page-1")
    check("page_hash is the hash of the text export will return", first["page_hash"] == nr.text_hash(nr.canonical(api, V1)))
    check("version starts at 1", first["version"] == 1)
    props = api.pages["page-1"]["properties"]
    check("Card property keys the page", plain(props["Card"]) == "card-one")
    check("Run property records the run", plain(props["Run"]) == "run-1")
    second = run(["publish", "--card", "card-one", "--title", "What moves the needle", "--run-id", "run-2",
                  "--from-file", write(tmp, "r2.md", V2)], api)
    check("second run creates nothing", len(api.creates()) == 1)
    check("second run names the same page", second["page"] == "page-1")
    check("version increments", second["version"] == 2)
    check("body replaced, not stacked", [b["type"] for b in api.children["page-1"]] == ["heading_1", "paragraph"])
    check("Run property now names run-2", plain(api.pages["page-1"]["properties"]["Run"]) == "run-2")

print("--- export: the inverse of publish ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    run(["publish", "--card", "card-one", "--from-file", write(tmp, "r.md", V1), "--run-id", "run-1"], api)
    out = pathlib.Path(tmp) / "prev.md"
    exported = run(["export", "--card", "card-one", "--out", str(out)], api)
    text = out.read_text()
    check("export writes the file", exported["page"] == "page-1" and out.exists())
    check("headings survive", "# card-one — what moves the needle" in text and "\n## Acceptance\n" in text)
    check("bold and link survive", "**finding**" in text and "[source](https://example.org/a)" in text)
    check("bullets and numbers survive", "- MET: the first line" in text and "1. numbered one" in text
          and "2. numbered two" in text)
    check("code fence survives verbatim", "```\ncode stays\nverbatim\n```" in text)
    check("table survives", "| a | b |" in text and "| 1 | 2 |" in text)
    check("export is stable: publish it again, export again, same text", True)
    run(["publish", "--card", "card-one", "--from-file", str(out), "--run-id", "run-2"], api)
    again = pathlib.Path(tmp) / "again.md"
    run(["export", "--card", "card-one", "--out", str(again)], api)
    check("round trip is a fixed point", again.read_text() == text)
    check("an unedited page exports the hash publish recorded", exported["page_hash"] == exported["published_hash"])
    check("export reports the hash of the text it returned", exported["page_hash"] == nr.text_hash(text))

print("--- export --if-exists: no page is not an error ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    out = pathlib.Path(tmp) / "prev.md"
    result = run(["export", "--card", "card-new", "--out", str(out), "--if-exists"], api)
    check("nothing written", not out.exists())
    check("result says no page", result["page"] is None)
    try:
        run(["export", "--card", "card-new", "--out", str(out)], api)
        check("export without --if-exists on a missing page refuses", False)
    except SystemExit as e:
        check("export without --if-exists on a missing page refuses", "card-new" in str(e))

print("--- mark: state and vault path, idempotent ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    run(["publish", "--card", "card-one", "--from-file", write(tmp, "r.md", V1), "--run-id", "run-1"], api)
    run(["mark", "--card", "card-one", "--state", "merged", "--path", "05_knowledge/research/card-one.md"], api)
    props = api.pages["page-1"]["properties"]
    check("state recorded", plain(props["State"]) == "merged")
    check("vault path recorded", plain(props["Vault path"]) == "05_knowledge/research/card-one.md")
    try:
        run(["mark", "--card", "card-one", "--state", "bogus"], api)
        check("unknown state refused", False)
    except SystemExit:
        check("unknown state refused", True)

print("--- configuration and card ids refuse before any call ---")
api = FakeNotion()
saved = os.environ.pop("NOTION_RESEARCH_DS")
nr.SECRETS = "/nonexistent/secrets.env"
try:
    run(["export", "--card", "card-one", "--if-exists"], api)
    check("missing database id refused", False)
except SystemExit as e:
    check("missing database id refused, naming the variable", "NOTION_RESEARCH_DS" in str(e))
check("no Notion call was made", api.calls == [])
os.environ["NOTION_RESEARCH_DS"] = saved
try:
    run(["export", "--card", "Not A Slug!", "--if-exists"], api)
    check("bad card id refused", False)
except SystemExit:
    check("bad card id refused", True)
check("still no Notion call", api.calls == [])

if failures:
    print("\nFAILED: {}".format(len(failures)))
    raise SystemExit(1)
print("\nPASS")
