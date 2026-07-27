#!/usr/bin/env python3
"""
notion_daily.py — date-keyed, idempotent Notion I/O for the Praetorium daily rhythm
jobs (NUC-45: praetorium-daily-plan, praetorium-eod-summary).

Notion is the durable artifact for both jobs; the canonical vault write stays Mac-side
(Dave-decision 2026-07-27). This helper is the single seam through which they read and
write it, so neither task prompt hand-rolls curl and both share ONE idempotency key —
the row title:

    <date> — Daily Plan    Daily Plans   (morning)
    <date> — EOD Summary   Daily Plans   (evening)
    <date>                 Daily Log     (evening, structured mirror)

Re-running a job for the same date updates that row and REPLACES its block body; it
never stacks a second row. That is also what lets the Mac's interactive eod-wrap
overwrite the box's row later the same day instead of duplicating it.

Every write drops a receipt JSON under --receipt-dir. AGENT_VERIFY_CMD asserts that
receipt is newer than $AGENT_RUN_STARTED_AT — the only proof the run reached Notion,
since the runtime exits 0 even when the agent wrote nothing.

  plan   --date D --body-file F [--events N] [--tasks N]
  eod    --date D --body-file F --done T --remaining T [--insights T] [--focus T] [--tags a,b]
  inputs [--date D]                          read-only: calendar + open tasks + pipeline
"""
import argparse
import datetime
import json
import os
import pathlib
import re
import sys
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notion_rest import load_token  # noqa: E402  — sibling helper owns the token rule

NOTION_VERSION = "2025-09-03"
API = "https://api.notion.com/v1"

DAILY_PLANS_DS = "3288d768-1ede-8190-ad5a-000b9710833e"
DAILY_LOG_DS = "f184eddd-2793-4560-8d04-dcfbb8b55f85"
CALENDAR_DS = "3288d768-1ede-81a4-927f-000b16612a75"
TASK_INBOX_DS = "4dbb4389-6c4a-4f57-b70f-10d899483c21"
CLIENT_PIPELINE_DS = "e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e"

PLAN_TITLE = "{} — Daily Plan"
EOD_TITLE = "{} — EOD Summary"
CLOSED_TASK_STATUSES = ("Done", "Parked")
NUMBERED_LINE = re.compile(r"^\d+\.\s+(.*)")


class NotionHttp:
    def __init__(self, token):
        self._token = token

    def call(self, method, path, payload=None):
        data = json.dumps(payload).encode() if payload is not None else None
        req = urllib.request.Request(API + path, data=data, method=method, headers={
            "Authorization": "Bearer " + self._token,
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                return json.loads(response.read().decode() or "{}")
        except urllib.error.HTTPError as e:
            body = e.read().decode(errors="replace")[:300]
            sys.exit("Notion API {} on {} {}: {}".format(e.code, method, path, body))
        except urllib.error.URLError as e:
            sys.exit("Notion API network error on {} {}: {}".format(method, path, e))


def rt(text):
    """rich_text array, chunked to Notion's per-object character limit."""
    text = text or ""
    chunks = [text[i:i + 1900] for i in range(0, len(text), 1900)]
    return [{"type": "text", "text": {"content": c}} for c in chunks] or \
           [{"type": "text", "text": {"content": ""}}]


def block(kind, text):
    return {"object": "block", "type": kind, kind: {"rich_text": rt(text)}}


def block_from_line(line):
    text = line.strip()
    for prefix, kind in (("### ", "heading_3"), ("## ", "heading_2"), ("# ", "heading_1"),
                         ("> ", "quote"), ("- ", "bulleted_list_item"),
                         ("* ", "bulleted_list_item")):
        if text.startswith(prefix):
            return block(kind, text[len(prefix):])
    numbered = NUMBERED_LINE.match(text)
    if numbered:
        return block("numbered_list_item", numbered.group(1))
    return block("paragraph", text)


def blocks_from_markdown(text):
    return [block_from_line(line) for line in (text or "").splitlines() if line.strip()]


def now_iso():
    """Local time WITH offset — matches the existing rows (2026-07-23T09:47:00.000+02:00)."""
    return datetime.datetime.now().astimezone().isoformat(timespec="milliseconds")


def query(api, data_source, payload=None):
    """Every page of the result. Notion caps a page at 100 rows and the Task Inbox is well
    past that (225 open on 2026-07-27) — one unpaginated call would put a wrong Tasks Count
    on the row and hide two thirds of the backlog from the briefing."""
    body = {"page_size": 100}
    body.update(payload or {})
    results, cursor = [], None
    while True:
        page_body = dict(body, start_cursor=cursor) if cursor else body
        page = api.call("POST", "/data_sources/{}/query".format(data_source), page_body)
        results += page.get("results", [])
        if not page.get("has_more"):
            return results
        cursor = page["next_cursor"]


def find_page(api, data_source, title_prop, title):
    page = api.call("POST", "/data_sources/{}/query".format(data_source),
                    {"page_size": 1,
                     "filter": {"property": title_prop, "title": {"equals": title}}})
    rows = page.get("results", [])
    return rows[0]["id"] if rows else None


def upsert_row(api, data_source, title_prop, title, props):
    page_id = find_page(api, data_source, title_prop, title)
    if page_id:
        api.call("PATCH", "/pages/" + page_id, {"properties": props})
        return page_id, "updated"
    created = api.call("POST", "/pages", {
        "parent": {"type": "data_source_id", "data_source_id": data_source},
        "properties": props,
    })
    return created["id"], "created"


def child_ids(api, page_id):
    ids, cursor = [], None
    while True:
        path = "/blocks/{}/children?page_size=100".format(page_id)
        if cursor:
            path += "&start_cursor=" + cursor
        page = api.call("GET", path)
        ids += [b["id"] for b in page.get("results", [])]
        if not page.get("has_more"):
            return ids
        cursor = page["next_cursor"]


def replace_children(api, page_id, blocks):
    for block_id in child_ids(api, page_id):
        api.call("DELETE", "/blocks/" + block_id)
    for i in range(0, len(blocks), 100):
        api.call("PATCH", "/blocks/{}/children".format(page_id), {"children": blocks[i:i + 100]})


def plain(prop):
    return "".join(t.get("plain_text", "")
                   for t in (prop.get("title") or prop.get("rich_text") or []))


def select_name(prop):
    return (prop.get("select") or {}).get("name")


def date_start(prop):
    return (prop.get("date") or {}).get("start")


def emit_receipt(directory, date, payload):
    target = pathlib.Path(os.path.expanduser(directory))
    target.mkdir(parents=True, exist_ok=True)
    receipt = target / "receipt-{}.json".format(date)
    receipt.write_text(json.dumps(payload, indent=2))
    payload["receipt"] = str(receipt)
    print(json.dumps(payload, indent=2))
    return payload


def read_body(path):
    with open(os.path.expanduser(path)) as f:
        return f.read()


def cmd_plan(args, api):
    props = {
        "Plan Title": {"title": rt(PLAN_TITLE.format(args.date))},
        "Plan Date": {"date": {"start": args.date}},
        "Status": {"select": {"name": args.status}},
        "Generated At": {"date": {"start": now_iso()}},
        "Events Count": {"number": args.events},
        "Tasks Count": {"number": args.tasks},
    }
    page_id, action = upsert_row(api, DAILY_PLANS_DS, "Plan Title",
                                 PLAN_TITLE.format(args.date), props)
    replace_children(api, page_id, blocks_from_markdown(read_body(args.body_file)))
    return emit_receipt(args.receipt_dir or "~/logs/daily-plan", args.date,
                        {"kind": "daily-plan", "date": args.date, "page": page_id,
                         "action": action, "title": PLAN_TITLE.format(args.date)})


def eod_log_props(args):
    props = {
        "Date": {"title": rt(args.date)},
        "Type": {"select": {"name": "EOD summary"}},
        "Done": {"rich_text": rt(args.done)},
        "Remaining": {"rich_text": rt(args.remaining)},
        "Key insights": {"rich_text": rt(args.insights)},
        "Focus areas": {"rich_text": rt(args.focus)},
    }
    tags = [t.strip() for t in (args.tags or "").split(",") if t.strip()]
    if tags:
        props["Tags"] = {"multi_select": [{"name": t} for t in tags]}
    return props


def cmd_eod(args, api):
    title = EOD_TITLE.format(args.date)
    plan_id, plan_action = upsert_row(api, DAILY_PLANS_DS, "Plan Title", title, {
        "Plan Title": {"title": rt(title)},
        "Plan Date": {"date": {"start": args.date}},
        "Generated At": {"date": {"start": now_iso()}},
    })
    replace_children(api, plan_id, blocks_from_markdown(read_body(args.body_file)))
    log_id, log_action = upsert_row(api, DAILY_LOG_DS, "Date", args.date, eod_log_props(args))
    return emit_receipt(args.receipt_dir or "~/logs/eod-summary", args.date,
                        {"kind": "eod-summary", "date": args.date, "title": title,
                         "page": plan_id, "action": plan_action,
                         "log_page": log_id, "log_action": log_action})


def task_filter(since):
    """Morning wants what is still open; EOD wants what MOVED today, closed rows included."""
    if since:
        return {"timestamp": "last_edited_time", "last_edited_time": {"on_or_after": since}}
    return {"and": [{"property": "Status", "select": {"does_not_equal": s}}
                    for s in CLOSED_TASK_STATUSES]}


def cmd_inputs(args, api):
    events = query(api, CALENDAR_DS, {"filter": {"property": "Date", "date": {"equals": args.date}}})
    tasks = query(api, TASK_INBOX_DS, {"filter": task_filter(args.since)})
    pipeline = query(api, CLIENT_PIPELINE_DS,
                     {"filter": {"property": "Stage", "select": {"does_not_equal": "Closed"}}})
    result = {
        "date": args.date,
        "events": [{"title": plain(p["properties"].get("Title", {})),
                    "type": select_name(p["properties"].get("Type", {})),
                    "workstream": select_name(p["properties"].get("Workstream", {})),
                    "minutes": p["properties"].get("Duration (min)", {}).get("number"),
                    "status": select_name(p["properties"].get("Status", {}))}
                   for p in events],
        "tasks": [{"title": plain(p["properties"].get("Task Title", {})),
                   "status": select_name(p["properties"].get("Status", {})),
                   "priority": select_name(p["properties"].get("Priority", {})),
                   "project": select_name(p["properties"].get("Project", {})),
                   "due": date_start(p["properties"].get("Due date", {}))}
                  for p in tasks],
        "pipeline": [{"client": plain(p["properties"].get("Client", {})),
                      "stage": select_name(p["properties"].get("Stage", {})),
                      "last_contact": date_start(p["properties"].get("Last contact", {}))}
                     for p in pipeline],
    }
    print(json.dumps(result, indent=2))
    return result


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Idempotent Notion I/O for the daily rhythm jobs")
    sub = parser.add_subparsers(dest="cmd", required=True)
    today = datetime.date.today().isoformat()

    plan = sub.add_parser("plan", help="upsert today's Daily Plans row + body")
    plan.add_argument("--date", default=today)
    plan.add_argument("--body-file", required=True)
    plan.add_argument("--events", type=int, default=0)
    plan.add_argument("--tasks", type=int, default=0)
    plan.add_argument("--status", default="Active", choices=["Draft", "Active", "Reviewed"])
    plan.add_argument("--receipt-dir")

    eod = sub.add_parser("eod", help="upsert today's EOD Summary in Daily Plans + Daily Log")
    eod.add_argument("--date", default=today)
    eod.add_argument("--body-file", required=True)
    eod.add_argument("--done", default="")
    eod.add_argument("--remaining", default="")
    eod.add_argument("--insights", default="")
    eod.add_argument("--focus", default="")
    eod.add_argument("--tags", default="")
    eod.add_argument("--receipt-dir")

    inputs = sub.add_parser("inputs", help="read calendar + tasks + pipeline (read-only)")
    inputs.add_argument("--date", default=today)
    inputs.add_argument("--since", help="ISO timestamp: return tasks EDITED since then "
                                        "(the day's deltas, closed rows included) "
                                        "instead of the open backlog")

    return parser.parse_args(argv)


def main(argv=None, api=None):
    args = parse_args(argv)
    api = api or NotionHttp(load_token())
    return {"plan": cmd_plan, "eod": cmd_eod, "inputs": cmd_inputs}[args.cmd](args, api)


if __name__ == "__main__":
    main()
