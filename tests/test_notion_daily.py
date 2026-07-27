#!/usr/bin/env python3
"""
Offline behaviour test for bin/notion_daily.py (NUC-45). Driven from
tests/test_notion_daily.sh so bin/verify.sh picks it up.

No network: the HTTP seam is replaced by FakeNotion. What is pinned here is the
idempotency contract the 06:00 job depends on — a second run of the same date
UPDATES the row it already wrote and REPLACES its body, instead of stacking a
second row and a second copy of the briefing.
"""
import importlib.util
import json
import pathlib
import re
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("notion_daily", ROOT / "bin" / "notion_daily.py")
nd = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(nd)

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


class FakeNotion:
    """The slice of the Notion REST surface notion_daily.py actually touches.

    Title filters are evaluated (that is the idempotency key under test); select and
    date filters are not — those queries are asserted on their payload instead.
    """

    def __init__(self):
        self.pages = {}
        self.children = {}
        self.calls = []
        self._seq = 0

    def _id(self, prefix):
        self._seq += 1
        return "{}-{}".format(prefix, self._seq)

    def call(self, method, path, payload=None):
        self.calls.append((method, path, payload))
        head = path.split("/")
        if method == "POST" and head[1] == "data_sources":
            return self._query(head[2], payload)
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
        self.pages[pid] = {"id": pid, "_ds": payload["parent"]["data_source_id"],
                           "properties": payload["properties"]}
        return {"id": pid}

    def _query(self, dsid, payload):
        rows = [p for p in self.pages.values() if p["_ds"] == dsid]
        payload = payload or {}
        flt = payload.get("filter") or {}
        if "title" in flt:
            rows = [p for p in rows
                    if self._title(p, flt["property"]) == flt["title"]["equals"]]
        size = payload.get("page_size", 100)
        start = int(payload.get("start_cursor") or 0)
        window = rows[start:start + size]
        has_more = start + size < len(rows)
        return {"results": [{"id": p["id"], "properties": p["properties"]} for p in window],
                "has_more": has_more,
                "next_cursor": str(start + size) if has_more else None}

    def seed_tasks(self, dsid, count):
        for i in range(count):
            self._create({"parent": {"data_source_id": dsid},
                          "properties": {"Task Title": {"title": [
                              {"type": "text", "text": {"content": "task %d" % i},
                               "plain_text": "task %d" % i}]}}})

    @staticmethod
    def _title(page, prop):
        return "".join(t["text"]["content"]
                       for t in page["properties"].get(prop, {}).get("title", []))

    # ── helpers the assertions read ──
    def rows(self, dsid):
        return [p for p in self.pages.values() if p["_ds"] == dsid]

    def creates(self):
        return [c for c in self.calls if c[0] == "POST" and c[1] == "/pages"]

    def updates(self):
        return [c for c in self.calls if c[0] == "PATCH" and c[1].startswith("/pages/")]

    def deletes(self):
        return [c for c in self.calls if c[0] == "DELETE"]

    def body_text(self, page_id):
        return [b[b["type"]]["rich_text"][0]["text"]["content"]
                for b in self.children.get(page_id, [])]

    def body_types(self, page_id):
        return [b["type"] for b in self.children.get(page_id, [])]


def body_file(tmp, text):
    p = pathlib.Path(tmp) / "body.md"
    p.write_text(text)
    return str(p)


DATE = "2026-07-27"
PLAN_V1 = "> first framing\n\n## Calendar\n- 09:00 standup\n\n## Focus\n1. ship NUC-45\n"
PLAN_V2 = "> rewritten framing\n\n## Calendar\n- 11:00 moved\n"

print("--- plan: first run creates, second run updates in place ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    nd.main(["plan", "--date", DATE, "--body-file", body_file(tmp, PLAN_V1),
             "--events", "3", "--tasks", "7", "--receipt-dir", tmp], api=api)
    check("first run creates exactly one page", len(api.creates()) == 1)
    check("first run issues no page update", len(api.updates()) == 0)
    page_id = api.rows(nd.DAILY_PLANS_DS)[0]["id"]
    props = api.rows(nd.DAILY_PLANS_DS)[0]["properties"]

    check("title is '<date> — Daily Plan'",
          FakeNotion._title({"properties": props}, "Plan Title") == DATE + " — Daily Plan")
    check("Status is Active", props["Status"]["select"]["name"] == "Active")
    check("Plan Date is the run date", props["Plan Date"]["date"]["start"] == DATE)
    check("Events Count / Tasks Count are numbers",
          props["Events Count"]["number"] == 3 and props["Tasks Count"]["number"] == 7)
    check("Generated At carries a UTC offset (matches existing rows)",
          bool(re.search(r"[+-]\d{2}:\d{2}$", props["Generated At"]["date"]["start"])))

    check("body renders block types, not paragraphs",
          api.body_types(page_id) == ["quote", "heading_2", "bulleted_list_item",
                                      "heading_2", "numbered_list_item"])

    # Second run, same date, different content.
    nd.main(["plan", "--date", DATE, "--body-file", body_file(tmp, PLAN_V2),
             "--events", "2", "--tasks", "5", "--receipt-dir", tmp], api=api)
    check("second run creates NO second page (acceptance criterion 2)",
          len(api.creates()) == 1)
    check("second run updates the existing page", len(api.updates()) == 1)
    check("still exactly one row for the date", len(api.rows(nd.DAILY_PLANS_DS)) == 1)
    check("second run deleted the old blocks before writing",
          len(api.deletes()) == 5)
    check("body was REPLACED, not appended",
          api.body_text(page_id) == ["rewritten framing", "Calendar", "11:00 moved"])
    check("counts were refreshed on update",
          api.rows(nd.DAILY_PLANS_DS)[0]["properties"]["Events Count"]["number"] == 2)

    receipt = pathlib.Path(tmp) / ("receipt-%s.json" % DATE)
    check("receipt written (this is what AGENT_VERIFY_CMD asserts)", receipt.exists())
    data = json.loads(receipt.read_text())
    check("receipt records the action", data.get("action") == "updated")
    check("receipt records the page id", data.get("page") == page_id)

print("--- eod: writes both data sources, idempotent on re-run ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    args = ["eod", "--date", DATE, "--body-file", body_file(tmp, "## Done\n- shipped\n"),
            "--done", "shipped NUC-45", "--remaining", "deploy",
            "--insights", "UNCONFIRMED: no evidence of client contact",
            "--focus", "Praetorium", "--tags", "AI,Operations", "--receipt-dir", tmp]
    nd.main(list(args), api=api)
    check("creates one Daily Plans EOD row", len(api.rows(nd.DAILY_PLANS_DS)) == 1)
    check("creates one Daily Log row", len(api.rows(nd.DAILY_LOG_DS)) == 1)

    plan_props = api.rows(nd.DAILY_PLANS_DS)[0]["properties"]
    check("Daily Plans EOD title is '<date> — EOD Summary'",
          FakeNotion._title({"properties": plan_props}, "Plan Title") == DATE + " — EOD Summary")
    log_props = api.rows(nd.DAILY_LOG_DS)[0]["properties"]
    check("Daily Log title is the bare date",
          FakeNotion._title({"properties": log_props}, "Date") == DATE)
    check("Daily Log Type is 'EOD summary'", log_props["Type"]["select"]["name"] == "EOD summary")
    check("Daily Log carries Done / Remaining",
          log_props["Done"]["rich_text"][0]["text"]["content"] == "shipped NUC-45")
    check("Daily Log tags become multi_select",
          [t["name"] for t in log_props["Tags"]["multi_select"]] == ["AI", "Operations"])

    nd.main(list(args), api=api)
    check("re-run adds no Daily Plans row (criterion 7: Mac overwrites in place)",
          len(api.rows(nd.DAILY_PLANS_DS)) == 1)
    check("re-run adds no Daily Log row", len(api.rows(nd.DAILY_LOG_DS)) == 1)
    check("re-run updated both rows", len(api.updates()) == 2)

print("--- inputs: read-only, queries the three input sources ---")
with tempfile.TemporaryDirectory() as tmp:
    api = FakeNotion()
    out = nd.main(["inputs", "--date", DATE], api=api)
    queried = [c[1].split("/")[2] for c in api.calls if c[0] == "POST" and "query" in c[1]]
    check("queries calendar, task inbox, client pipeline",
          set(queried) == {nd.CALENDAR_DS, nd.TASK_INBOX_DS, nd.CLIENT_PIPELINE_DS})
    check("writes nothing (read-only)", api.creates() == [] and api.updates() == [])
    check("returns the three input groups",
          set(out) == {"date", "events", "tasks", "pipeline"})
    cal_payload = next(c[2] for c in api.calls if c[1].startswith("/data_sources/" + nd.CALENDAR_DS))
    check("calendar query is scoped to the date",
          cal_payload["filter"]["date"]["equals"] == DATE)
    task_payload = next(c[2] for c in api.calls
                        if c[1].startswith("/data_sources/" + nd.TASK_INBOX_DS))
    check("without --since the morning job gets the OPEN backlog",
          [f["select"]["does_not_equal"] for f in task_payload["filter"]["and"]]
          == list(nd.CLOSED_TASK_STATUSES))

    api = FakeNotion()
    nd.main(["inputs", "--date", DATE, "--since", DATE + "T00:00:00+02:00"], api=api)
    task_payload = next(c[2] for c in api.calls
                        if c[1].startswith("/data_sources/" + nd.TASK_INBOX_DS))
    check("with --since the EOD job gets the day's deltas, closed rows included",
          task_payload["filter"]["last_edited_time"]["on_or_after"] == DATE + "T00:00:00+02:00")

print("--- inputs: pages past the 100-row cap ---")
with tempfile.TemporaryDirectory() as tmp:
    # The live Task Inbox held 225 open rows on 2026-07-27; a single unpaginated query
    # reported 100 of them, which would have put a wrong Tasks Count on the Notion row
    # and silently hidden two thirds of the backlog from the briefing.
    api = FakeNotion()
    api.seed_tasks(nd.TASK_INBOX_DS, 225)
    out = nd.main(["inputs", "--date", DATE], api=api)
    check("returns every open task, not just the first page", len(out["tasks"]) == 225)
    task_queries = [c for c in api.calls if c[1].startswith("/data_sources/" + nd.TASK_INBOX_DS)]
    check("followed the cursor across 3 pages", len(task_queries) == 3)
    check("later pages carry start_cursor", task_queries[1][2].get("start_cursor") == "100")
    check("no truncation is silent — titles survive paging",
          out["tasks"][-1]["title"] == "task 224")

print("--- markdown rendering ---")
check("chunks rich_text over Notion's 2000-char object limit",
      len(nd.rt("x" * 4000)) == 3)
check("blank lines are dropped", len(nd.blocks_from_markdown("a\n\n\nb")) == 2)
check("'### ' renders heading_3", nd.blocks_from_markdown("### x")[0]["type"] == "heading_3")

raise SystemExit(1 if failures else 0)
