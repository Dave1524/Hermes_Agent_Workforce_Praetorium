#!/usr/bin/env python3
"""
Offline behaviour test for bin/notion_rest.py (NUC-44). Driven from
tests/test_notion_rest.sh so bin/verify.sh picks it up.

No network: the module-level `api` seam is replaced by FakeNotion, and `load_token`
is stubbed so the real secrets file is never read.

Three guards are pinned here, all of them "the tool refuses" rather than "the profile
markdown asks nicely":

  * draft must not append to a page that already carries a body. The check is an
    allowlist (Idea/Picked pass, everything else refuses), because Dave adds status
    options from the Notion UI and a deny-list fails open on the next one.
  * board caps how many rows a run is handed. "handle max 2" lived only in
    profiles/augustus_content_task.md, which is an instruction the model may ignore.
  * board follows Notion's cursor. Content DB passed 100 rows on 2026-08-14, so a
    single-page read returns a silent subset of a board the digest jobs hash whole.
"""
import contextlib
import importlib.util
import io
import json
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("notion_rest", ROOT / "bin" / "notion_rest.py")
nr = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nr)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


class FakeNotion:
    """The slice of the Notion REST surface notion_rest.py touches."""

    def __init__(self, pages=None):
        self.pages = pages or {}
        self.children = {}
        self.calls = []

    def __call__(self, method, path, token, payload=None, timeout=30):
        self.calls.append((method, path, payload))
        head = path.split("/")
        if method == "POST" and head[1] == "data_sources":
            return self._query(payload)
        if method == "POST" and head[1] == "pages":
            return {"id": "p-new", "url": "https://notion.so/p-new"}
        if method == "GET" and head[1] == "pages":
            return self.pages[head[2]]
        if method == "PATCH" and head[1] == "pages":
            self.pages[head[2]]["properties"].update(payload["properties"])
            return {"id": head[2]}
        if method == "PATCH" and head[1] == "blocks":
            self.children.setdefault(head[2], []).extend(payload["children"])
            return {"results": []}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def _matches(self, pg, clause):
        if "and" in clause:
            return all(self._matches(pg, c) for c in clause["and"])
        if clause.get("property") == "Status":
            return nr.status_of(pg) == clause["status"]["equals"]
        return nr.select_of(pg, clause["property"]) == clause["select"]["equals"]

    def _query(self, payload):
        payload = payload or {}
        rows = list(self.pages.values())
        flt = payload.get("filter")
        if flt:
            rows = [p for p in rows if self._matches(p, flt)]
        start = int(payload.get("start_cursor") or 0)
        size = payload.get("page_size") or 100
        window = rows[start:start + size]
        more = start + size < len(rows)
        return {"results": window,
                "has_more": more,
                "next_cursor": str(start + size) if more else None}

    def queries(self):
        return [c for c in self.calls if c[0] == "POST" and c[1].startswith("/data_sources/")]

    def appends(self, page_id):
        return self.children.get(page_id, [])

    def status_writes(self):
        return [c for c in self.calls if c[0] == "PATCH" and c[1].startswith("/pages/")]


def page(pid, angle, status, proposed_by="Augustus"):
    return {"id": pid, "url": "https://notion.so/" + pid, "last_edited_time": "2026-08-12T00:00:00Z",
            "properties": {"Title": {"type": "title",
                                     "title": [{"plain_text": angle}]},
                           "Proposed by": {"select": {"name": proposed_by}},
                           "Status": {"status": {"name": status}}}}


def run(argv, api):
    """Invoke the CLI; returns (exit_message_or_None, stdout, stderr).

    Pinned to --transport https: this suite replaces the `api` seam, which the broker
    transport bypasses, so an `auto` resolution against a live socket would leave the
    fake behind and write to the real board.
    """
    out, err = io.StringIO(), io.StringIO()
    msg = None
    nr.api = api
    nr.load_token = lambda: "test-token"
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            nr.main(["--transport", "https"] + argv)
    except SystemExit as e:
        msg = e.code
    return msg, out.getvalue(), err.getvalue()


print("--- draft: a page already at Draft is refused, not appended to ---")
api = FakeNotion({"p-draft": page("p-draft", "Cold-store grid capacity", "Draft")})
msg, out, err = run(["draft", "--page", "p-draft", "--body", "a second variant"], api)
check("refuses with a non-zero exit", bool(msg))
check("the refusal names the page's current status", "Draft" in str(msg))
check("the refusal names the escape hatch", "--force" in str(msg))
check("NOTHING was appended to the page body", api.appends("p-draft") == [])
check("and the Status was not rewritten", api.status_writes() == [])

print("--- draft: the guard is an allowlist, so an unforeseen status also refuses ---")
# A deny-list enumerating the known statuses fails open the first time Dave adds one
# from the Notion UI — `Picked` arrived that way on 2026-08-14. Every option outside
# APPENDABLE_STATUSES must refuse, including ones nobody has written down yet.
for status in ("Review", "Ready to Post", "Planned on Linkedin", "Posted", "Some Future Option"):
    api = FakeNotion({"p-x": page("p-x", "Cold-store grid capacity", status)})
    msg, out, err = run(["draft", "--page", "p-x", "--body", "a second variant"], api)
    check("refuses at Status={}".format(status), bool(msg) and status in str(msg))
    check("nothing appended at Status={}".format(status), api.appends("p-x") == [])

print("--- draft: --force is the deliberate override ---")
api = FakeNotion({"p-draft": page("p-draft", "Cold-store grid capacity", "Draft")})
msg, out, err = run(["draft", "--page", "p-draft", "--body", "an intentional rewrite",
                     "--force"], api)
check("exits clean", msg is None)
check("the body was appended", len(api.appends("p-draft")) == 1)

print("--- draft: the normal Picked -> Draft path is untouched ---")
api = FakeNotion({"p-picked": page("p-picked", "Cold-store grid capacity", "Picked")})
msg, out, err = run(["draft", "--page", "p-picked", "--body", "the draft"], api)
check("exits clean", msg is None)
check("the body was appended", len(api.appends("p-picked")) == 1)
check("Status advanced to Draft", nr.status_of(api.pages["p-picked"]) == "Draft")
check("the write is status-shaped, not select-shaped",
      api.status_writes()[0][2]["properties"]["Status"] == {"status": {"name": "Draft"}})
check("result JSON reports the page", json.loads(out)["page"] == "p-picked")

print("--- draft: an Idea row drafts without Dave having picked it first ---")
api = FakeNotion({"p-idea": page("p-idea", "Cold-store grid capacity", "Idea")})
msg, out, err = run(["draft", "--page", "p-idea", "--body", "the draft"], api)
check("exits clean", msg is None)
check("the body was appended", len(api.appends("p-idea")) == 1)

print("--- draft: a page whose status cannot be read is not blocked (fail-open by design) ---")
# The guard exists to stop variant-stacking on a row that already carries a body. A page
# with no Status property is a schema surprise, not a duplicate — refusing there would
# strand the run on something the operator cannot fix from the board. This is also the
# shape a select-shaped read of a status property returns, so the fail-open direction is
# what keeps a property-type mistake from presenting as a total outage.
api = FakeNotion({"p-bare": {"id": "p-bare", "properties": {}}})
msg, out, err = run(["draft", "--page", "p-bare", "--body", "the draft"], api)
check("exits clean", msg is None)
check("the body was appended", len(api.appends("p-bare")) == 1)

print("--- board: the per-run cap is enforced by the tool, not by the profile prose ---")
rows = {"p%d" % i: page("p%d" % i, "angle %d" % i, "Picked") for i in range(5)}
api = FakeNotion(dict(rows))
msg, out, err = run(["board", "--status", "Picked", "--json"], api)
check("exits clean", msg is None)
parsed = json.loads(out)
check("returns 2 rows by default (the 'handle max 2' cap)", len(parsed) == 2)
check("the drop is stated, never silent", "3" in err and "5" in err)
check("stderr points at the override", "--max-rows" in err)

print("--- board: --max-rows 0 means every row, for the machine callers ---")
api = FakeNotion(dict(rows))
msg, out, err = run(["board", "--status", "Picked", "--json", "--max-rows", "0"], api)
check("returns all 5 rows", len(json.loads(out)) == 5)
check("no truncation notice when nothing was dropped", err.strip() == "")

print("--- board: an explicit cap is honoured, and under-cap output stays quiet ---")
api = FakeNotion(dict(rows))
msg, out, err = run(["board", "--status", "Picked", "--json", "--max-rows", "3"], api)
check("returns 3 rows", len(json.loads(out)) == 3)

api = FakeNotion({"p0": page("p0", "angle 0", "Picked")})
msg, out, err = run(["board", "--status", "Picked", "--json"], api)
check("one row under the cap emits no notice", err.strip() == "")

print("--- board: the Status filter is status-shaped, not select-shaped ---")
api = FakeNotion({"p-a": page("p-a", "a", "Picked"), "p-b": page("p-b", "b", "Idea")})
msg, out, err = run(["board", "--status", "Picked", "--json", "--max-rows", "0"], api)
check("only the matching row comes back", [r["id"] for r in json.loads(out)] == ["p-a"])
check("the filter used the `status` key",
      api.queries()[0][2]["filter"] == {"property": "Status", "status": {"equals": "Picked"}})

print("--- board: --proposed-by separates the agent's rows from Dave's ---")
# STEP 3 of the nightly profile pitches only when it holds fewer than 3 open ideas.
# Since the 2026-08-14 merge the board also carries Dave's own — 32 of them that day —
# so counting every Idea row would hold the drafter permanently over the threshold and
# it would silently never pitch again.
mixed = {"d%d" % i: page("d%d" % i, "dave %d" % i, "Idea", "Dave") for i in range(4)}
mixed.update({"a%d" % i: page("a%d" % i, "augustus %d" % i, "Idea", "Augustus")
              for i in range(2)})
mixed["a-drafted"] = page("a-drafted", "already drafted", "Draft", "Augustus")
api = FakeNotion(dict(mixed))
msg, out, err = run(["board", "--status", "Idea", "--proposed-by", "Augustus", "--json",
                     "--max-rows", "0"], api)
parsed = json.loads(out)
check("returns only Augustus's open ideas", sorted(r["id"] for r in parsed) == ["a0", "a1"])
check("both clauses are sent, combined with `and`",
      api.queries()[0][2]["filter"] == {"and": [
          {"property": "Status", "status": {"equals": "Idea"}},
          {"property": "Proposed by", "select": {"equals": "Augustus"}}]})
check("each row reports who proposed it",
      all(r["proposed_by"] == "Augustus" for r in parsed))

api = FakeNotion(dict(mixed))
msg, out, err = run(["board", "--proposed-by", "Dave", "--json", "--max-rows", "0"], api)
check("--proposed-by alone is sent unwrapped",
      api.queries()[0][2]["filter"] == {"property": "Proposed by",
                                        "select": {"equals": "Dave"}})
check("returns Dave's 4 rows", len(json.loads(out)) == 4)

print("--- board: every page of a >100-row board is read, not just the first ---")
# Content DB held 126 rows the day it became the target. content_board_digest.sh hashes
# the whole board to decide whether augustus did anything overnight, so a silent subset
# there is indistinguishable from a real status change.
big = {"p%03d" % i: page("p%03d" % i, "angle %d" % i, "Idea") for i in range(126)}
api = FakeNotion(dict(big))
msg, out, err = run(["board", "--json", "--max-rows", "0"], api)
parsed = json.loads(out)
check("exits clean", msg is None)
check("returns all 126 rows", len(parsed) == 126)
check("no row is returned twice", len({r["id"] for r in parsed}) == 126)
check("it took more than one query", len(api.queries()) == 2)
check("the second query carried the cursor", api.queries()[1][2].get("start_cursor") == "100")

print("--- board: a board that fits in one page issues exactly one query ---")
api = FakeNotion({"p%d" % i: page("p%d" % i, "angle %d" % i, "Idea") for i in range(100)})
msg, out, err = run(["board", "--json", "--max-rows", "0"], api)
check("returns all 100 rows", len(json.loads(out)) == 100)
check("and does not chase a cursor that is not there", len(api.queries()) == 1)

print("--- pitch: writes Content DB's property names and its status shape ---")
api = FakeNotion({})
msg, out, err = run(["pitch", "--angle", "Cold-store grid capacity",
                     "--insight", "the grid is the constraint",
                     "--evidence", "vault: cold chain notes",
                     "--signal", "a client conversation",
                     "--type", "Text-only"], api)
check("exits clean", msg is None)
created = [c for c in api.calls if c[0] == "POST" and c[1] == "/pages"]
check("exactly one page was created", len(created) == 1)
props = created[0][2]["properties"]
check("the title lands on Title, not Angle", "Title" in props and "Angle" not in props)
check("Status is status-shaped at Idea", props["Status"] == {"status": {"name": "Idea"}})
check("Proposed by is stamped Augustus",
      props["Proposed by"] == {"select": {"name": "Augustus"}})
check("--insight lands on POV", props["POV"]["rich_text"][0]["text"]["content"]
      == "the grid is the constraint")
check("--signal lands on Topic", props["Topic"]["rich_text"][0]["text"]["content"]
      == "a client conversation")
check("--type lands on Type", props["Type"] == {"select": {"name": "Text-only"}})
check("no Pitched date is written — created_time already carries it",
      "Pitched" not in props)
check("none of the retired inbox property names survive",
      not {"Second-order insight", "Signal", "Format"} & set(props))
check("the result reports the pitch status", json.loads(out)["status"] == "Idea")

if failures:
    print("\n{} FAILED".format(len(failures)))
    raise SystemExit(1)
