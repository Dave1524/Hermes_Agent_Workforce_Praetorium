#!/usr/bin/env python3
"""
Offline behaviour test for bin/notion_rest.py (NUC-44). Driven from
tests/test_notion_rest.sh so bin/verify.sh picks it up.

No network: the module-level `api` seam is replaced by FakeNotion, and `load_token`
is stubbed so the real secrets file is never read.

Two guards are pinned here, both of them "the tool refuses" rather than "the profile
markdown asks nicely":

  * draft must not append to a page already at Status=Drafted. Six rows on the board
    were Drafted when this landed, and a re-run stacks a second variant into the same
    body — invisible in the board view, and unpickable apart afterwards.
  * board caps how many rows a run is handed. "handle max 2" lived only in
    profiles/augustus_content_task.md, which is an instruction the model may ignore.
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
        if method == "GET" and head[1] == "pages":
            return self.pages[head[2]]
        if method == "PATCH" and head[1] == "pages":
            self.pages[head[2]]["properties"].update(payload["properties"])
            return {"id": head[2]}
        if method == "PATCH" and head[1] == "blocks":
            self.children.setdefault(head[2], []).extend(payload["children"])
            return {"results": []}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def _query(self, payload):
        rows = list(self.pages.values())
        flt = (payload or {}).get("filter") or {}
        if "select" in flt:
            want = flt["select"]["equals"]
            rows = [p for p in rows if nr.status_of(p) == want]
        return {"results": rows}

    def appends(self, page_id):
        return self.children.get(page_id, [])

    def status_writes(self):
        return [c for c in self.calls if c[0] == "PATCH" and c[1].startswith("/pages/")]


def page(pid, angle, status):
    return {"id": pid, "url": "https://notion.so/" + pid, "last_edited_time": "2026-08-12T00:00:00Z",
            "properties": {"Angle": {"type": "title",
                                     "title": [{"plain_text": angle}]},
                           "Status": {"select": {"name": status}}}}


def run(argv, api):
    """Invoke the CLI; returns (exit_message_or_None, stdout, stderr)."""
    out, err = io.StringIO(), io.StringIO()
    msg = None
    nr.api = api
    nr.load_token = lambda: "test-token"
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            nr.main(argv)
    except SystemExit as e:
        msg = e.code
    return msg, out.getvalue(), err.getvalue()


print("--- draft: a page already at Drafted is refused, not appended to ---")
api = FakeNotion({"p-drafted": page("p-drafted", "Cold-store grid capacity", "Drafted")})
msg, out, err = run(["draft", "--page", "p-drafted", "--body", "a second variant"], api)
check("refuses with a non-zero exit", bool(msg))
check("the refusal names the page's current status", "Drafted" in str(msg))
check("the refusal names the escape hatch", "--force" in str(msg))
check("NOTHING was appended to the page body", api.appends("p-drafted") == [])
check("and the Status was not rewritten", api.status_writes() == [])

print("--- draft: the guard covers every status that already carries a body ---")
# Enumerating only the reported case (Drafted) would fail open the first time a run
# reached a Ready or Published row, where a stacked variant is strictly worse.
for status in ("Ready", "Published"):
    api = FakeNotion({"p-x": page("p-x", "Cold-store grid capacity", status)})
    msg, out, err = run(["draft", "--page", "p-x", "--body", "a second variant"], api)
    check("refuses at Status={}".format(status), bool(msg) and status in str(msg))
    check("nothing appended at Status={}".format(status), api.appends("p-x") == [])

print("--- draft: --force is the deliberate override ---")
api = FakeNotion({"p-drafted": page("p-drafted", "Cold-store grid capacity", "Drafted")})
msg, out, err = run(["draft", "--page", "p-drafted", "--body", "an intentional rewrite",
                     "--force"], api)
check("exits clean", msg is None)
check("the body was appended", len(api.appends("p-drafted")) == 1)

print("--- draft: the normal Picked -> Drafted path is untouched ---")
api = FakeNotion({"p-picked": page("p-picked", "Cold-store grid capacity", "Picked")})
msg, out, err = run(["draft", "--page", "p-picked", "--body", "the draft"], api)
check("exits clean", msg is None)
check("the body was appended", len(api.appends("p-picked")) == 1)
check("Status advanced to Drafted", nr.status_of(api.pages["p-picked"]) == "Drafted")
check("result JSON reports the page", json.loads(out)["page"] == "p-picked")

print("--- draft: a page whose status cannot be read is not blocked (fail-open by design) ---")
# The guard exists to stop variant-stacking on a KNOWN-Drafted row. A page with no
# Status property is a schema surprise, not a duplicate — refusing there would strand
# the run on something the operator cannot fix from the board.
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

if failures:
    print("\n{} FAILED".format(len(failures)))
    raise SystemExit(1)
