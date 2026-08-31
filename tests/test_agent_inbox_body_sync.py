#!/usr/bin/env python3
"""
Offline behaviour test for the proposal-body half of bin/agent_inbox_notion_sync.py.
Driven from tests/test_agent_inbox_body_sync.sh so bin/verify.sh picks it up.

No network: the HTTP seam (the module-level api()) is replaced by FakeNotion, and
INBOX_DIR / APPROVALS are pointed at a temp tree. What is pinned here is the reason
this code exists — every Agent Inbox row had an EMPTY Notion page body, so the only
readable copy of a proposal was behind a private-repo GitHub link that 404s for an
unauthenticated browser — plus the crash-safety contract of the sentinel: a body is
only ever considered complete when its last block is the sentinel, which is written
last and therefore cannot exist unless every preceding batch landed.
"""
import contextlib
import datetime
import importlib.util
import io
import os
import pathlib
import re
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("agent_inbox_notion_sync",
                                               ROOT / "bin" / "agent_inbox_notion_sync.py")
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


class FakeNotion:
    """The slice of the Notion REST surface agent_inbox_notion_sync.py touches.

    Signature matches the module-level api(method, path, token, payload=None) it
    replaces, so main() needs no injection hook beyond patching that one name.
    """

    def __init__(self):
        self.pages = {}
        self.children = {}
        self.calls = []
        self._seq = 0

    def _id(self, prefix):
        self._seq += 1
        return "{}-{}".format(prefix, self._seq)

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        head = path.split("?")[0].split("/")
        if method == "POST" and head[1] == "data_sources":
            return self._query(payload)
        if method == "POST" and path == "/pages":
            return self._create(payload)
        if method == "PATCH" and head[1] == "pages":
            self.pages[head[2]]["properties"].update(payload["properties"])
            return {"id": head[2]}
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

    def _create(self, payload):
        pid = self._id("page")
        self.pages[pid] = {"id": pid, "properties": payload["properties"]}
        return {"id": pid}

    def _query(self, payload):
        rows = [{"id": p["id"], "properties": self._readback(p["properties"])}
                for p in self.pages.values()]
        return {"results": rows, "has_more": False, "next_cursor": None}

    @staticmethod
    def _readback(props):
        """Notion echoes a WRITTEN property back with a 'type' discriminator and a
        flattened 'plain_text' on every span. prop_text() reads both, so a fake that
        replays the write shape verbatim silently reports every Filename as empty."""
        out = {}
        for name, value in props.items():
            kind = next(k for k in value if k != "type")
            if kind in ("title", "rich_text"):
                out[name] = {"type": kind, kind: [dict(s, plain_text=s["text"]["content"])
                                                  for s in value[kind]]}
            else:
                out[name] = dict(value, type=kind)
        return out

    # -- helpers the assertions read --
    def creates(self):
        return [c for c in self.calls if c[0] == "POST" and c[1] == "/pages"]

    def appends(self):
        return [c for c in self.calls if c[0] == "PATCH" and c[1].startswith("/blocks/")]

    def deletes(self):
        return [c for c in self.calls if c[0] == "DELETE"]

    def writes(self):
        return [c for c in self.calls
                if c[0] in ("PATCH", "DELETE") or (c[0] == "POST" and c[1] == "/pages")]

    def only_page(self):
        return list(self.pages)[0]

    def body(self, page_id):
        return self.children.get(page_id, [])

    def body_types(self, page_id):
        return [b["type"] for b in self.body(page_id)]

    def text_of(self, block):
        rich = block.get(block["type"], {}).get("rich_text", [])
        return "".join(s["text"]["content"] for s in rich)

    def body_text(self, page_id):
        return [self.text_of(b) for b in self.body(page_id)]


TODAY = datetime.date.today().isoformat()
FILENAME = TODAY + "_standing-research.md"
PROPOSAL = (
    "# Standing research — {d}\n"
    "\n"
    "First substantive line about **WMS/TMS** consolidation.\n"
    "\n"
    "## Findings\n"
    "- one finding with a [link](https://example.com/a)\n"
    "- another citing <https://example.com/b>\n"
    "\n"
    "| Claim | Source | Confidence |\n"
    "| --- | --- | --- |\n"
    "| a | b | high |\n"
    "\n"
    "```\n"
    "# this stays verbatim\n"
    "```\n"
    "\n"
    "## Contradictions flagged this week\n"
    "> none this week\n"
    "\n"
    "See [[05_knowledge/wms_tms_x]] for context.\n"
).format(d=TODAY)


@contextlib.contextmanager
def sandbox(files):
    tmp = tempfile.TemporaryDirectory()
    inbox = pathlib.Path(tmp.name) / "_inbox" / "agents"
    inbox.mkdir(parents=True)
    for name, text in files.items():
        (inbox / name).write_text(text, encoding="utf-8")
    old = (sync.INBOX_DIR, sync.APPROVALS, sync.api)
    sync.INBOX_DIR = str(inbox)
    sync.APPROVALS = str(inbox / "_metrics" / "approvals.tsv")
    fake = FakeNotion()
    sync.api = fake
    os.environ["NOTION_API_TOKEN"] = "test-token"
    try:
        yield fake
    finally:
        sync.INBOX_DIR, sync.APPROVALS, sync.api = old
        tmp.cleanup()


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sync.main(argv)
    return buf.getvalue()


print("--- (a) creating a row writes a body that ends in the sentinel ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    out = run([])
    check("exactly one row created", len(api.creates()) == 1)
    page = api.only_page()
    body = api.body(page)
    check("the page body is NOT empty (the whole point of this feature)", len(body) > 0)
    last = body[-1]
    check("the last block is the sentinel paragraph",
          last["type"] == "paragraph"
          and re.match(r"^— synced from %s @ \S+ —$" % re.escape(FILENAME),
                       api.text_of(last)) is not None)
    check("the sentinel is preceded by a divider", body[-2]["type"] == "divider")

    check("the body opens with a provenance paragraph naming the file",
          body[0]["type"] == "paragraph" and FILENAME in api.text_of(body[0]))
    check("the provenance paragraph names the branch",
          "agents/inbox" in api.text_of(body[0]))
    check("the provenance paragraph carries the Box Link as a clickable link",
          any((s["text"].get("link") or {}).get("url") == sync.BOX_LINK_BASE + FILENAME
              for s in body[0]["paragraph"]["rich_text"]))
    check("the provenance header is closed off with a divider",
          body[1]["type"] == "divider")

    types = api.body_types(page)
    check("the proposal renders as native blocks, not one paragraph",
          {"heading_1", "heading_2", "bulleted_list_item", "table", "code", "quote"}
          <= set(types))
    check("the table is a real Notion table with rows",
          [b for b in body if b["type"] == "table"][0]["table"]["table_width"] == 3)
    check("no raw ** survives into the rendered text",
          not any("**" in t for t in api.body_text(page)))
    check("the wikilink survives as plain text",
          any("[[05_knowledge/wms_tms_x]]" in t for t in api.body_text(page)))
    check("run summary reports the bodies it wrote",
          re.search(r"bodies written this run: 1 \(\d+ blocks\)", out) is not None)

    check("the row still carries the unchanged property set",
          set(api.pages[page]["properties"]) ==
          {"Proposal", "Status", "Filename", "Box Link", "Excerpt", "Source",
           "Proposal Date"})
    check("Box Link is untouched — it stays a reference, not a fix",
          api.pages[page]["properties"]["Box Link"]["url"] == sync.BOX_LINK_BASE + FILENAME)
    check("the row is created before its body is written",
          api.calls.index(api.creates()[0]) < api.calls.index(api.appends()[0]))

print("--- (b) a second pass over the same row writes nothing ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    run([])
    page = api.only_page()
    before = list(api.body(page))
    api.calls = []
    out = run(["--backfill-bodies"])
    check("no blocks were appended", api.appends() == [])
    check("no blocks were deleted", api.deletes() == [])
    check("the body is byte-identical to the first write", api.body(page) == before)
    check("the run summary reports no body writes",
          "bodies written this run" not in out)

print("--- (c) a partial body (no sentinel) is cleared and rewritten ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    run([])
    page = api.only_page()
    truncated = api.body(page)[:4]
    api.children[page] = truncated
    api.calls = []
    out = run(["--backfill-bodies"])
    check("every stale block was deleted", len(api.deletes()) == len(truncated))
    check("the body was rewritten to completion",
          re.match(r"^— synced from ", api.text_of(api.body(page)[-1])) is not None)
    check("no stale block survived the rewrite",
          all(b not in truncated for b in api.body(page)))
    check("the run summary reports the repair",
          re.search(r"bodies written this run: 1 \(\d+ blocks\)", out) is not None)

print("--- (d) batching never exceeds Notion's 100-children-per-request limit ---")
BIG = "\n\n".join("## Section %d\n- point %d" % (i, i) for i in range(120))
with sandbox({FILENAME: BIG}) as api:
    run([])
    page = api.only_page()
    sizes = [len(c[2]["children"]) for c in api.appends()]
    check("the proposal really is over one batch", len(api.body(page)) > 100)
    check("no request carries more than 100 children", max(sizes) <= 100)
    check("more than one batch was sent", len(sizes) > 1)
    check("no block was lost across batches", sum(sizes) == len(api.body(page)))

print("--- (e) --dry-run issues zero writes ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    out = run(["--dry-run"])
    check("nothing was created, appended or deleted", api.writes() == [])
    check("the dry run still names the file it would create", FILENAME in out)

with sandbox({FILENAME: PROPOSAL}) as api:
    run([])
    api.children = {}
    api.calls = []
    out = run(["--backfill-bodies", "--dry-run"])
    check("--backfill-bodies --dry-run writes nothing", api.writes() == [])
    check("--backfill-bodies --dry-run reports the block count it would write",
          re.search(r"bodies written this run: 1 \(\d+ blocks\) \(DRY\)", out) is not None)

print("--- (f) --count stays read-only and its stdout is unchanged ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    out = run(["--count"])
    check("--count writes nothing", api.writes() == [])
    check("--count touches no block endpoint",
          [c for c in api.calls if "/blocks/" in c[1]] == [])
    check("--count stdout is the two lines its callers parse",
          out == "PENDING_COUNT=1\nOLDEST_PENDING_DATE=%s\n" % TODAY)

print("--- backfill covers rows created before this feature existed ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    run([])
    page = api.only_page()
    api.children = {}
    api.calls = []
    out = run(["--backfill-bodies"])
    check("an empty legacy body is filled", len(api.body(page)) > 0)
    check("it needed no DELETE (there was nothing to clear)", api.deletes() == [])
    check("the filled body ends in the sentinel",
          re.match(r"^— synced from ", api.text_of(api.body(page)[-1])) is not None)

print("--- backfill is scoped to Status=New, the rows still awaiting review ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    run([])
    page = api.only_page()
    api.pages[page]["properties"]["Status"] = {"select": {"name": "Approved"}}
    api.children = {}
    api.calls = []
    out = run(["--backfill-bodies"])
    check("a decided row is not backfilled", api.body(page) == [] and api.appends() == [])
    check("and it is not reported as a body write", "bodies written" not in out)

print("--- a row whose file is gone from the box is left alone ---")
with sandbox({FILENAME: PROPOSAL}) as api:
    run([])
    page = api.only_page()
    os.remove(os.path.join(sync.INBOX_DIR, FILENAME))
    api.children = {}
    api.calls = []
    run(["--backfill-bodies"])
    check("no body is invented for a file that is no longer on disk",
          api.body(page) == [] and api.appends() == [])

raise SystemExit(1 if failures else 0)
