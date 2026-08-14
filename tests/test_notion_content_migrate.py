#!/usr/bin/env python3
"""
Offline behaviour test for bin/notion_content_migrate.py. Driven from
tests/test_notion_content_migrate.sh so bin/verify.sh picks it up.

No network: the `api` seam inside notion_rest (which the migration imports) is replaced
by FakeNotion, and `load_token` is stubbed so the real secrets file is never read.

What is pinned here is the set of things that are cheap to get wrong and expensive to
discover afterwards, on a board Dave reads:

  * A `select` write CREATES an unknown option silently. An unmapped Format would grow
    the planner a junk Type and nobody would see it until the view looked wrong.
  * A `status` write CANNOT create an option. The same mistake on Status is a mid-run
    HTTP 400 with half the rows migrated.
  * Nothing may land in the Complete group. `Ready` on the inbox board is an agent
    saying "drafted"; `Ready to Post` in the planner is Dave saying "ship it".
  * A partial run must stay reversible — the ledger is the only record of what to undo.
"""
import contextlib
import importlib.util
import io
import json
import pathlib
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "notion_content_migrate", ROOT / "bin" / "notion_content_migrate.py")
mig = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(mig)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


TARGET_SCHEMA = {
    "Title": {"type": "title", "title": {}},
    "Status": {"type": "status", "status": {"options": [
        {"name": n} for n in ("Idea", "Draft", "Review", "Planned on Linkedin",
                              "Ready to Post", "Posted")]}},
    "Type": {"type": "select", "select": {"options": [
        {"name": n} for n in ("Text-only", "Article", "Document", "Video")]}},
    "Posting Date": {"type": "date", "date": {}},
    "Topic": {"type": "rich_text", "rich_text": {}},
    "POV": {"type": "rich_text", "rich_text": {}},
}


class FakeNotion:
    """The slice of the Notion REST surface the migration touches."""

    def __init__(self, source_rows, target_rows=None, schema=None, fail_create_at=None,
                 fail_append=False):
        self.rows = {mig.SOURCE_DS: source_rows, mig.TARGET_DS: target_rows or []}
        self.schema = json.loads(json.dumps(schema if schema is not None else TARGET_SCHEMA))
        self.bodies = {}
        self.created = []
        self.appended = {}
        self.archived = []
        self.calls = []
        self._fail_create_at = fail_create_at
        self._fail_append = fail_append

    def __call__(self, method, path, token, payload=None, timeout=30):
        self.calls.append((method, path, payload))
        head = path.split("?")[0].split("/")
        if method == "POST" and head[1] == "data_sources":
            return {"results": self.rows[head[2]], "has_more": False}
        if method == "GET" and head[1] == "data_sources":
            return {"properties": self.schema}
        if method == "PATCH" and head[1] == "data_sources":
            self.schema.update(payload["properties"])
            return {"properties": self.schema}
        if method == "GET" and head[1] == "blocks":
            return {"results": self.bodies.get(head[2], []), "has_more": False}
        if method == "PATCH" and head[1] == "blocks":
            if self._fail_append:
                raise SystemExit("Notion API 400 on PATCH /blocks/x/children: simulated")
            for child in payload["children"]:
                if any(v is None for v in child[child["type"]].values()):
                    raise SystemExit("Notion API 400: should be an object or `undefined`, "
                                     "instead was `null`")
            self.appended.setdefault(head[2], []).extend(payload["children"])
            return {"results": []}
        if method == "POST" and head[1] == "pages":
            return self._create(payload)
        if method == "PATCH" and head[1] == "pages":
            self.archived.append(head[2])
            return {"id": head[2]}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def _create(self, payload):
        if self._fail_create_at is not None and len(self.created) == self._fail_create_at:
            raise SystemExit("Notion API 400 on POST /pages: simulated")
        page_id = "new-{}".format(len(self.created))
        self.created.append(payload)
        return {"id": page_id, "url": "https://notion.so/" + page_id}

    def props_written(self, index):
        return self.created[index]["properties"]

    def writes(self):
        return [c for c in self.calls if c[0] in ("POST", "PATCH")
                and not c[1].startswith("/data_sources/")]


def source_row(pid, angle, status, **kw):
    props = {"Angle": {"type": "title", "title": [{"plain_text": angle}]},
             "Status": {"select": {"name": status}}}
    for name in ("Format", "Proposed by"):
        if kw.get(name):
            props[name] = {"select": {"name": kw[name]}}
    for name in ("Date", "Pitched"):
        if kw.get(name):
            props[name] = {"date": {"start": kw[name]}}
    for name in ("Signal", "Second-order insight", "Evidence", "Notes"):
        if kw.get(name):
            props[name] = {"rich_text": [{"plain_text": kw[name]}]}
    return {"id": pid, "url": "https://notion.so/" + pid,
            "created_time": kw.get("created_time", "2026-08-01T00:00:00Z"),
            "properties": props}


def target_row(title):
    return {"id": "t-" + title[:6], "properties": {
        "Title": {"type": "title", "title": [{"plain_text": title}]}}}


def para(text, href=None):
    item = {"type": "text", "text": {"content": text}, "annotations": {"bold": False},
            "plain_text": text, "href": href}
    if href:
        item["text"]["link"] = {"url": href}
    # `icon: null` is what the live API returns on every paragraph, and rejects on write.
    return {"object": "block", "id": "b1", "type": "paragraph", "created_time": "x",
            "last_edited_time": "x", "has_children": False, "archived": False,
            "parent": {"type": "page_id"}, "paragraph": {"rich_text": [item],
                                                         "color": "default", "icon": None}}


def run(argv, api):
    out, err = io.StringIO(), io.StringIO()
    msg, result = None, None
    mig.nr.api = api
    mig.nr.load_token = lambda: "test-token"
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            result = mig.main(argv)
    except SystemExit as e:
        msg = e.code
    return msg, result, out.getvalue(), err.getvalue()


def ledger_path():
    return str(pathlib.Path(tempfile.mkdtemp()) / "sub" / "ledger.json")


print("--- plan: reads everything, writes nothing ---")
api = FakeNotion([source_row("p1", "An angle", "Ready")])
msg, result, out, err = run(["plan"], api)
check("exits clean", msg is None)
check("plans the row", result["planned"] == 1)
check("no page, block or schema write happened", api.writes() == [] and api.created == [])
check("the two new properties are named in the output", "Evidence" in out and "Proposed by" in out)

print("--- Rejected rows are left out of the active planner ---")
api = FakeNotion([source_row("p1", "A rejected angle", "Rejected"),
                  source_row("p2", "A live angle", "Ready")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("exits clean", msg is None)
check("only the live row is created", len(api.created) == 1)
check("the created row is the live one",
      api.props_written(0)["Title"]["title"][0]["text"]["content"] == "A live angle")
check("the skip is stated with its reason", "Rejected" in out)

print("--- nothing an agent set lands in the planner's Complete group ---")
# Ready/Drafted mean "an agent finished a draft". Ready to Post / Posted mean Dave said
# yes. Mapping across that line manufactures an approval he never gave.
complete_group = ("Ready to Post", "Posted")
for status in ("Drafted", "Ready"):
    api = FakeNotion([source_row("p1", "Angle " + status, status)])
    msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
    written = api.props_written(0)["Status"]["status"]["name"]
    check("{} -> Review, not the Complete group".format(status),
          written == "Review" and written not in complete_group)

print("--- an unmapped Status is refused, never guessed at ---")
api = FakeNotion([source_row("p1", "An angle", "Some New Status")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("exits clean", msg is None)
check("the row is skipped, not created", api.created == [])
check("the unmapped status is named in the output", "Some New Status" in out)

print("--- a Status option missing from the target aborts BEFORE any row is created ---")
# Status options cannot be created over the API. Discovering that on row 9 of 17 leaves
# a half-migrated board; discovering it at startup costs nothing.
schema = json.loads(json.dumps(TARGET_SCHEMA))
schema["Status"]["status"]["options"] = [{"name": "Idea"}, {"name": "Draft"}]
api = FakeNotion([source_row("p1", "An angle", "Ready")], schema=schema)
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("refuses with a non-zero exit", bool(msg))
check("the missing option is named", "Review" in str(msg))
check("it says why it cannot self-heal", "cannot be created" in str(msg))
check("nothing was created", api.created == [])

print("--- an unknown Type is refused rather than silently invented ---")
# The select write would succeed and add the option. That is the failure mode this
# check exists for: a wrong Type is invisible until someone reads the planner.
schema = json.loads(json.dumps(TARGET_SCHEMA))
schema["Type"]["select"]["options"] = [{"name": "Text-only"}]
api = FakeNotion([source_row("p1", "An angle", "Ready")], schema=schema)
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("refuses with a non-zero exit", bool(msg))
check("the offending option is named", "Article" in str(msg))
check("nothing was created", api.created == [])

print("--- the two proposal properties are added, and only if missing ---")
api = FakeNotion([source_row("p1", "An angle", "Ready")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
patches = [c for c in api.calls if c[0] == "PATCH" and c[1].startswith("/data_sources/")]
check("exactly one schema patch", len(patches) == 1)
check("it adds both properties", set(patches[0][2]["properties"]) == {"Proposed by", "Evidence"})
check("it is additive — no existing property is in the patch",
      not set(patches[0][2]["properties"]) & set(TARGET_SCHEMA))

api = FakeNotion([source_row("p1", "An angle", "Ready")],
                 schema=dict(TARGET_SCHEMA, **{"Proposed by": {"type": "select",
                                                               "select": {"options": []}},
                                               "Evidence": {"type": "rich_text",
                                                            "rich_text": {}}}))
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("no schema patch when both already exist",
      [c for c in api.calls if c[0] == "PATCH" and c[1].startswith("/data_sources/")] == [])

print("--- the field mapping ---")
api = FakeNotion([source_row("p1", "The angle", "Pitched", Format="Carousel",
                             Date="2026-08-18", **{"Proposed by": "Augustus",
                                                   "Signal": "the signal",
                                                   "Second-order insight": "the insight",
                                                   "Evidence": "the evidence"})])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
props = api.props_written(0)
check("Angle -> Title", props["Title"]["title"][0]["text"]["content"] == "The angle")
check("Pitched -> Idea", props["Status"]["status"]["name"] == "Idea")
check("Date -> Posting Date", props["Posting Date"]["date"]["start"] == "2026-08-18")
check("Carousel -> Document", props["Type"]["select"]["name"] == "Document")
check("Signal -> Topic", props["Topic"]["rich_text"][0]["text"]["content"] == "the signal")
check("Second-order insight -> POV", props["POV"]["rich_text"][0]["text"]["content"] == "the insight")
check("Evidence -> Evidence", props["Evidence"]["rich_text"][0]["text"]["content"] == "the evidence")
check("Proposed by carries over", props["Proposed by"]["select"]["name"] == "Augustus")

print("--- a row with no Date gets no Posting Date, rather than a made-up one ---")
api = FakeNotion([source_row("p1", "The angle", "Pitched")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("no Posting Date key at all", "Posting Date" not in api.props_written(0))
check("no Type key when Format is absent", "Type" not in api.props_written(0))

print("--- Format=Other maps to nothing rather than inventing a Type ---")
api = FakeNotion([source_row("p1", "The angle", "Pitched", Format="Other")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("no Type is written", "Type" not in api.props_written(0))

print("--- the page body travels, and the drafts are the point ---")
# 15 of the 17 live rows carry a 2-7k-character draft in the body. A migration that
# moved only properties would land 17 empty rows and look like it worked.
api = FakeNotion([source_row("p1", "The angle", "Ready", Notes="a note", Pitched="2026-08-01")])
api.bodies["p1"] = [para("first paragraph"), para("linked", href="https://example.com")]
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
body = api.appended["new-0"]
check("both source blocks were copied", len(body) == 4)
check("the text survives verbatim",
      body[0]["paragraph"]["rich_text"][0]["text"]["content"] == "first paragraph")
check("the link survives",
      body[1]["paragraph"]["rich_text"][0]["text"]["link"]["url"] == "https://example.com")
check("read-only rich_text fields are stripped (they 400 on write)",
      "plain_text" not in body[0]["paragraph"]["rich_text"][0]
      and "href" not in body[0]["paragraph"]["rich_text"][0])
check("read-only block fields are stripped",
      set(body[0]) == {"object", "type", "paragraph"})
check("null-valued body keys are stripped (icon: null 400s the whole batch)",
      "icon" not in body[0]["paragraph"])
trailer = body[3]["paragraph"]["rich_text"][0]["text"]["content"]
check("a provenance trailer is appended", body[2]["type"] == "heading_2")
check("it records the source row", "notion.so/p1" in trailer)
check("it keeps the original Status", "Ready" in trailer)
check("it keeps Notes, which map to no target property", "a note" in trailer)
check("it keeps the Pitched date", "2026-08-01" in trailer)

print("--- block appends respect Notion's 100-per-request cap ---")
api = FakeNotion([source_row("p1", "The angle", "Ready")])
api.bodies["p1"] = [para("p%d" % i) for i in range(250)]
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
batches = [c for c in api.calls if c[0] == "PATCH" and c[1].startswith("/blocks/")]
check("every batch is within the cap", all(len(c[2]["children"]) <= 100 for c in batches))
check("all 252 blocks arrive", sum(len(c[2]["children"]) for c in batches) == 252)

print("--- re-running apply is safe: a title already in the planner is skipped ---")
# The idempotency key. Without it a second run after a partial failure doubles the board.
api = FakeNotion([source_row("p1", "An angle", "Ready")],
                 target_rows=[target_row("An angle")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("nothing is created", api.created == [])
check("the skip names the reason", "already carries this title" in out)

api = FakeNotion([source_row("p1", "An Angle!", "Ready")],
                 target_rows=[target_row("an angle")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("the match ignores case and punctuation", api.created == [])

print("--- an empty-titled planner row does not swallow every source row ---")
# The Content DB has two of these. Normalising a blank title to "" and matching on it
# would skip the entire migration and report success.
api = FakeNotion([source_row("p1", "An angle", "Ready")],
                 target_rows=[{"id": "t-blank", "properties": {
                     "Title": {"type": "title", "title": []}}}])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("the row is still migrated", len(api.created) == 1)

print("--- a mid-run failure still leaves a usable rollback ledger ---")
path = ledger_path()
api = FakeNotion([source_row("p%d" % i, "Angle %d" % i, "Ready",
                             created_time="2026-08-0%dT00:00:00Z" % (i + 1))
                  for i in range(4)], fail_create_at=2)
msg, result, out, err = run(["apply", "--ledger", path], api)
check("the failure is not swallowed", bool(msg))
ledger = json.load(open(path))
check("the ledger records the rows that DID land", len(ledger["entries"]) == 2)
check("it records both ends of each mapping",
      ledger["entries"][0]["source"] == "p0" and ledger["entries"][0]["created"] == "new-0")

print("--- a page created but not filled is STILL in the ledger ---")
# The page and its body are two API calls. Recording the ledger entry after both means a
# failed body append orphans a live row that rollback cannot find — which is how the
# first live run left an empty row on Dave's planner.
orphan_path = ledger_path()
api = FakeNotion([source_row("p1", "An angle", "Ready")], fail_append=True)
api.bodies["p1"] = [para("a draft")]
msg, result, out, err = run(["apply", "--ledger", orphan_path], api)
check("the failure is not swallowed", bool(msg))
check("the page was created", len(api.created) == 1)
orphan = json.load(open(orphan_path))
check("and it is recorded for rollback", len(orphan["entries"]) == 1)
check("with the id rollback needs", orphan["entries"][0]["created"] == "new-0")

print("--- rollback archives exactly the ledger, and nothing else ---")
api = FakeNotion([])
msg, result, out, err = run(["rollback", "--ledger", path], api)
check("exits clean", msg is None)
check("both created pages are archived", result["archived"] == 2)
check("archived by page id", api.archived == ["new-0", "new-1"])
check("every archive call sets archived=true",
      all(c[2] == {"archived": True} for c in api.calls if c[0] == "PATCH"))

print("--- rollback never touches the Agent Content Inbox ---")
# The source board is read-only to this tool, in both directions. Dave's own inbox rows
# are the fallback if anything about the migrated copies is wrong.
check("no source page id appears in the archive list",
      not any(a.startswith("p") for a in api.archived))
check("no write of any kind went to the source data source",
      not any(c[1].startswith("/data_sources/" + mig.SOURCE_DS) and c[0] == "PATCH"
              for c in api.calls))

print("--- the source rows are never modified by apply either ---")
api = FakeNotion([source_row("p1", "An angle", "Ready")])
msg, result, out, err = run(["apply", "--ledger", ledger_path()], api)
check("no PATCH to a source page",
      not any(c[0] == "PATCH" and c[1] == "/pages/p1" for c in api.calls))

print("--- --limit bounds a cautious first run, and says what it held back ---")
api = FakeNotion([source_row("p%d" % i, "Angle %d" % i, "Ready",
                             created_time="2026-08-0%dT00:00:00Z" % (i + 1))
                  for i in range(4)])
msg, result, out, err = run(["apply", "--limit", "2", "--ledger", ledger_path()], api)
check("only 2 rows are created", len(api.created) == 2)
check("the held-back rows are reported, never silently dropped",
      out.count("beyond --limit 2") == 2)

print("--- the canary: a pipeline condition that fails open would hide all of the above ---")
check("canary", True)

if failures:
    print("\n{} FAILED".format(len(failures)))
    raise SystemExit(1)
