#!/usr/bin/env python3
"""
Offline behaviour test for bin/notion_publish_doc.py. Driven from
tests/test_notion_publish_doc.sh so bin/verify.sh picks it up.

No network: the HTTP seam is the `api` callable, replaced here by FakeNotion. What is
pinned is the contract a re-publish depends on — the second run REPLACES the body of
the page it already created, rather than minting a second page or appending a second
copy underneath the first. That is the difference between this helper and
notion_research_page.py, and it is invisible until the second run.
"""
import importlib.util
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "notion_publish_doc", ROOT / "bin" / "notion_publish_doc.py")
npd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(npd)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


class FakeNotion:
    """The slice of the Notion REST surface this helper touches."""

    def __init__(self):
        self.pages = {}
        self.children = {}
        self.calls = []
        self._next = 0

    def _id(self, prefix):
        self._next += 1
        return "{}-{:04d}".format(prefix, self._next)

    def __call__(self, method, path, payload=None):
        self.calls.append((method, path.split("?")[0], payload))
        if method == "POST" and path == "/pages":
            page_id = self._id("page")
            self.pages[page_id] = payload
            self.children[page_id] = []
            return {"id": page_id, "url": "https://notion.example/" + page_id}
        if method == "GET" and path.startswith("/blocks/"):
            page_id = path.split("/")[2]
            return {"results": [{"id": b} for b in self.children.get(page_id, [])],
                    "has_more": False, "next_cursor": None}
        if method == "PATCH" and path.startswith("/blocks/"):
            page_id = path.split("/")[2]
            for block in payload["children"]:
                self.children.setdefault(page_id, []).append(self._id("block"))
                self.pages.setdefault(page_id + ":blocks", []).append(block)
            return {}
        if method == "DELETE" and path.startswith("/blocks/"):
            block_id = path.split("/")[2]
            for page_id, blocks in self.children.items():
                if block_id in blocks:
                    blocks.remove(block_id)
            return {}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def blocks_of(self, page_id):
        return self.pages.get(page_id + ":blocks", [])


def publish(api, tmp, slug, title, body):
    body_file = tmp / (slug + ".md")
    body_file.write_text(body)
    npd.main(["publish", "--slug", slug, "--title", title,
              "--parent-page-id", "parent-123", "--body-file", str(body_file)], api=api)


MD_ONE = "# Overview\n\nFirst body.\n\n| a | b |\n| --- | --- |\n| 1 | 2 |\n"
MD_TWO = "# Overview\n\nSecond body, replacing the first.\n"

with tempfile.TemporaryDirectory() as d:
    tmp = pathlib.Path(d)
    npd.STATE_FILE = str(tmp / "state.json")
    api = FakeNotion()

    print("--- first publish: creates the page under the parent ---")
    publish(api, tmp, "fleet-overview", "Fleet Overview", MD_ONE)
    created = [c for c in api.calls if c[0] == "POST" and c[1] == "/pages"]
    check("creates exactly one page", len(created) == 1)
    check("under the parent page id given",
          created[0][2]["parent"] == {"type": "page_id", "page_id": "parent-123"})
    check("with the title given",
          created[0][2]["properties"]["title"]["title"][0]["text"]["content"] == "Fleet Overview")

    page_id = json.loads((tmp / "state.json").read_text())["fleet-overview"]["page_id"]
    kinds = [b["type"] for b in api.blocks_of(page_id)]
    check("renders markdown as blocks, not one literal paragraph", "heading_1" in kinds)
    check("renders a markdown table as a table block", "table" in kinds)

    print("--- second publish: replaces the body in place ---")
    before = len(api.blocks_of(page_id))
    publish(api, tmp, "fleet-overview", "Fleet Overview", MD_TWO)
    created = [c for c in api.calls if c[0] == "POST" and c[1] == "/pages"]
    check("does not mint a second page", len(created) == 1)
    deleted = [c for c in api.calls if c[0] == "DELETE"]
    check("deletes every block the first publish wrote", len(deleted) == before)
    check("the live page holds only the second body's blocks",
          len(api.children[page_id]) == len(blocks := npd.blocks_from_markdown(MD_TWO)))
    check("and the second body is what was written",
          "Second body" in json.dumps(api.blocks_of(page_id)[-len(blocks):]))

    state = json.loads((tmp / "state.json").read_text())["fleet-overview"]
    check("publish_count tracks both runs", state["publish_count"] == 2)
    check("page_id is stable across publishes", state["page_id"] == page_id)

    print("--- a body that would publish an empty page is refused ---")
    empty = tmp / "empty.md"
    empty.write_text("   \n\n  ")
    try:
        npd.main(["publish", "--slug", "empty-doc", "--title", "Empty",
                  "--parent-page-id", "parent-123", "--body-file", str(empty)], api=api)
        check("refuses an empty body", False)
    except SystemExit as e:
        check("refuses an empty body", "refusing an empty body" in str(e))
    check("and no page was created for it", "empty-doc" not in
          json.loads((tmp / "state.json").read_text()))

    print("--- chunking: a body over the per-request block cap is split ---")
    big = "\n\n".join("Paragraph {}.".format(i) for i in range(250))
    api2 = FakeNotion()
    npd.STATE_FILE = str(tmp / "state2.json")
    publish(api2, tmp, "big-doc", "Big", big)
    patches = [c for c in api2.calls if c[0] == "PATCH"]
    check("splits into more than one PATCH", len(patches) > 1)
    check("no request exceeds the 100-block cap",
          all(len(c[2]["children"]) <= npd.BLOCKS_PER_REQUEST for c in patches))

print()
if failures:
    print("FAILED ({}):".format(len(failures)))
    for f in failures:
        print("  - " + f)
    raise SystemExit(1)
print("  all notion_publish_doc tests passed")
