#!/usr/bin/env python3
"""
notion_content_migrate.py — migrate Agent Content Inbox rows into the central Content DB.

Implements steps 1-2 of the Notion proposal "centralize agent content intake in the
LinkedIn Content Planner" (page 3bc8d768-1ede-814a-9d83-f4663d9e504e): add the two
missing Content DB properties, then copy every non-Rejected inbox row — properties AND
page body — into Content DB under the proposal's field mapping.

It does NOT do steps 3-5. The linked "Agent Intake" view, the freeze note and archiving
the old database are Notion UI operations with no REST equivalent (the API cannot create
or modify database views), and the proposal itself gates archiving on Dave confirming the
migrated rows first.

Nothing here is destructive: the source rows are read-only to this tool, every created
page is recorded in a ledger, and `rollback` archives exactly the pages in that ledger.

  plan     [--limit N]              Print the mapped plan. No writes at all.
  apply    [--limit N] [--ledger F] Create the target rows. Writes a ledger.
  rollback --ledger F               Archive every page the ledger records.

Re-running `apply` is safe: a source row whose title already exists in Content DB is
skipped, so a partial run resumes instead of duplicating.
"""
import argparse
import datetime
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion_rest as nr  # noqa: E402  (load_token/api/rt — one Notion transport, not two)

SOURCE_DS = "ab5eb999-e986-4a8b-9159-eb340196af9b"  # Agent Content Inbox
TARGET_DS = "df18d768-1ede-82c1-9cf0-070ba3ef070e"  # Content DB (LinkedIn Content Planner)
LEDGER_DEFAULT = os.path.expanduser("~/agent-workforce/var/notion_content_migration.json")

# Content DB `Status` is a status property, and status options CANNOT be created over the
# API — only selected. So every value on the right must already exist in the target, and
# ensure_schema() asserts that rather than discovering it mid-migration.
#
# Nothing maps into the Complete group. "Ready" on the inbox board is set by an agent
# after drafting; "Ready to Post" in the planner is Dave's editorial yes. Mapping one to
# the other would manufacture an approval he never gave, and Review -> Ready to Post is
# one click while the reverse is a wrong signal already acted on.
STATUS_MAP = {
    "Pitched": "Idea",
    "Picked": "Draft",
    "Drafted": "Review",
    "Ready": "Review",
    "Ready to post": "Ready to Post",
    "Published": "Posted",
}
SKIP_STATUSES = ("Rejected",)

FORMAT_MAP = {
    "LinkedIn post": "Text-only",
    "Article": "Article",
    "Carousel": "Document",
    "Other": None,
}

NEW_PROPERTIES = {
    "Proposed by": {"select": {"options": [{"name": n} for n in ("Dave", "Augustus", "Claudius")]}},
    "Evidence": {"rich_text": {}},
}

# Blocks the API can read but not create. None appear in today's 843-block corpus; the
# list exists so a body that grows one is dropped loudly instead of failing the create.
UNCREATABLE_BLOCKS = ("unsupported", "child_page", "child_database", "ai_block",
                      "link_preview", "template")

BLOCK_BATCH = 100  # Notion's per-request children cap


def query_all(data_source_id, token):
    rows, cursor = [], None
    while True:
        payload = {"page_size": 100}
        if cursor:
            payload["start_cursor"] = cursor
        res = nr.api("POST", "/data_sources/{}/query".format(data_source_id), token, payload)
        rows.extend(res.get("results", []))
        if not res.get("has_more"):
            return rows
        cursor = res["next_cursor"]


def text_of(page, prop):
    return "".join(t.get("plain_text", "") for t in
                   page.get("properties", {}).get(prop, {}).get("rich_text", []) or [])


def select_of(page, prop):
    sel = page.get("properties", {}).get(prop, {}).get("select")
    return sel.get("name") if sel else None


def date_of(page, prop):
    val = page.get("properties", {}).get(prop, {}).get("date")
    return val.get("start") if val else None


def normalise(title):
    return re.sub(r"[^a-z0-9]+", " ", (title or "").lower()).strip()


def clean_rich_text(items):
    """Rebuild a rich_text array as the create API accepts it.

    plain_text/href are derived fields on read; echoing them back is what turns a
    faithful copy into a 400.
    """
    out = []
    for item in items or []:
        if item.get("type") != "text":
            out.append({k: v for k, v in item.items() if k not in ("plain_text", "href")})
            continue
        text = {"content": item["text"]["content"]}
        if item["text"].get("link"):
            text["link"] = item["text"]["link"]
        out.append({"type": "text", "text": text,
                    "annotations": item.get("annotations", {})})
    return out


def clean_block(block):
    kind = block["type"]
    body = dict(block.get(kind) or {})
    if "rich_text" in body:
        body["rich_text"] = clean_rich_text(body["rich_text"])
    body.pop("children", None)
    return {"object": "block", "type": kind, kind: body}


def body_blocks(page_id, token):
    """The page body, flattened to creatable top-level blocks.

    The inbox corpus is flat (paragraph + heading_2 only), so nested children are
    reported rather than silently reshaped if that ever stops being true.
    """
    blocks, cursor = [], None
    while True:
        path = "/blocks/{}/children?page_size=100".format(page_id)
        if cursor:
            path += "&start_cursor=" + cursor
        res = nr.api("GET", path, token)
        for block in res.get("results", []):
            if block["type"] in UNCREATABLE_BLOCKS:
                sys.stderr.write("notion_content_migrate: dropped an uncreatable {} block "
                                 "from {}\n".format(block["type"], page_id))
                continue
            if block.get("has_children"):
                sys.stderr.write("notion_content_migrate: {} block in {} has children, "
                                 "which are NOT copied\n".format(block["type"], page_id))
            blocks.append(clean_block(block))
        if not res.get("has_more"):
            return blocks
        cursor = res["next_cursor"]


def provenance_blocks(page, today):
    lines = ["Migrated from the Agent Content Inbox on {}. Source row: {}".format(
        today, page.get("url", page["id"]))]
    lines.append("Original Status: {}".format(select_of(page, "Status")))
    pitched = date_of(page, "Pitched")
    if pitched:
        lines.append("Pitched: {}".format(pitched))
    notes = text_of(page, "Notes")
    if notes:
        lines.append("Notes: {}".format(notes))
    return [{"object": "block", "type": "heading_2",
             "heading_2": {"rich_text": nr.rt("Source")}},
            {"object": "block", "type": "paragraph",
             "paragraph": {"rich_text": nr.rt("\n".join(lines))}}]


def target_properties(page):
    props = {
        "Title": {"title": nr.rt(nr.title_of(page))},
        "Status": {"status": {"name": STATUS_MAP[select_of(page, "Status")]}},
    }
    posting = date_of(page, "Date")
    if posting:
        props["Posting Date"] = {"date": {"start": posting}}
    kind = FORMAT_MAP.get(select_of(page, "Format"))
    if kind:
        props["Type"] = {"select": {"name": kind}}
    for source, target in (("Signal", "Topic"), ("Second-order insight", "POV"),
                           ("Evidence", "Evidence")):
        value = text_of(page, source)
        if value:
            props[target] = {"rich_text": nr.rt(value)}
    proposed = select_of(page, "Proposed by")
    if proposed:
        props["Proposed by"] = {"select": {"name": proposed}}
    return props


def build_plan(token, limit):
    source = query_all(SOURCE_DS, token)
    existing = {normalise(nr.title_of(p)) for p in query_all(TARGET_DS, token)
                if nr.title_of(p).strip()}
    planned, skipped = [], []
    for page in sorted(source, key=lambda p: p["created_time"]):
        title = nr.title_of(page)
        status = select_of(page, "Status")
        if status in SKIP_STATUSES:
            skipped.append((title, "Status={} — left out of the active planner".format(status)))
        elif status not in STATUS_MAP:
            skipped.append((title, "unmapped Status={!r}".format(status)))
        elif normalise(title) in existing:
            skipped.append((title, "a Content DB row already carries this title"))
        else:
            planned.append(page)
    if limit:
        for page in planned[limit:]:
            skipped.append((nr.title_of(page), "beyond --limit {}".format(limit)))
        planned = planned[:limit]
    return planned, skipped


def ensure_schema(token, apply_changes):
    """Add the two proposal properties, and assert every value we are about to write exists.

    A `select` write silently CREATES an unknown option, so an unmapped Format would
    quietly grow the planner a new Type rather than failing. Checking first keeps the
    mapping table honest.
    """
    schema = nr.api("GET", "/data_sources/{}".format(TARGET_DS), token)["properties"]
    missing = {name: spec for name, spec in NEW_PROPERTIES.items() if name not in schema}
    if missing and apply_changes:
        nr.api("PATCH", "/data_sources/{}".format(TARGET_DS), token, {"properties": missing})
        schema = nr.api("GET", "/data_sources/{}".format(TARGET_DS), token)["properties"]

    statuses = {o["name"] for o in schema["Status"]["status"]["options"]}
    unknown = set(STATUS_MAP.values()) - statuses
    if unknown:
        sys.exit("Content DB has no Status option {} — status options cannot be created "
                 "over the API, add it in Notion first".format(sorted(unknown)))
    types = {o["name"] for o in schema["Type"]["select"]["options"]}
    unknown = {t for t in FORMAT_MAP.values() if t} - types
    if unknown:
        sys.exit("Content DB has no Type option {} — fix FORMAT_MAP rather than letting "
                 "the write invent one".format(sorted(unknown)))
    return sorted(missing), schema


def describe(page):
    return "  {:<8} -> {:<14} {:<10} {}".format(
        select_of(page, "Status"),
        STATUS_MAP[select_of(page, "Status")],
        date_of(page, "Date") or "-",
        nr.title_of(page)[:64])


def report_skips(skipped, verb):
    print("\n{} {} row(s)".format(verb, len(skipped)))
    for title, why in skipped:
        print("  {:<64} {}".format(title[:64], why))


def cmd_plan(args, token):
    added, _ = ensure_schema(token, apply_changes=False)
    planned, skipped = build_plan(token, args.limit)
    print("Content DB properties to add: {}".format(added or "none"))
    print("\nWould migrate {} row(s)   [inbox Status -> planner Status, Posting Date]".format(
        len(planned)))
    for page in planned:
        print(describe(page))
    report_skips(skipped, "Would skip")
    return {"planned": len(planned), "skipped": len(skipped)}


def create_row(page, token, today):
    payload = {"parent": {"type": "data_source_id", "data_source_id": TARGET_DS},
               "properties": target_properties(page)}
    created = nr.api("POST", "/pages", token, payload)
    blocks = body_blocks(page["id"], token) + provenance_blocks(page, today)
    for start in range(0, len(blocks), BLOCK_BATCH):
        nr.api("PATCH", "/blocks/{}/children".format(created["id"]), token,
               {"children": blocks[start:start + BLOCK_BATCH]})
    return {"source": page["id"], "source_title": nr.title_of(page),
            "source_status": select_of(page, "Status"), "created": created["id"],
            "created_url": created.get("url"), "blocks": len(blocks)}


def write_ledger(path, entries):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as handle:
        json.dump({"target_data_source": TARGET_DS, "entries": entries}, handle, indent=2)


def cmd_apply(args, token):
    today = datetime.date.today().isoformat()
    added, _ = ensure_schema(token, apply_changes=True)
    if added:
        print("added Content DB properties: {}".format(", ".join(added)))
    planned, skipped = build_plan(token, args.limit)
    # A row this run declined to migrate is reported by name. A count alone reads as
    # "covered everything" to whoever checks the board afterwards.
    report_skips(skipped, "skipped")
    entries = []
    try:
        for page in planned:
            entries.append(create_row(page, token, today))
            print("created {}  {}".format(entries[-1]["created"], entries[-1]["source_title"][:64]))
    finally:
        # The ledger is written even on a mid-run failure: a partial migration that
        # cannot be rolled back is the one outcome worth engineering against.
        write_ledger(args.ledger, entries)
    print("\nmigrated {} row(s), skipped {} — ledger: {}".format(
        len(entries), len(skipped), args.ledger))
    print("rollback with: {} rollback --ledger {}".format(sys.argv[0], args.ledger))
    return {"created": len(entries), "skipped": len(skipped)}


def cmd_rollback(args, token):
    with open(args.ledger) as handle:
        ledger = json.load(handle)
    for entry in ledger["entries"]:
        nr.api("PATCH", "/pages/{}".format(entry["created"]), token, {"archived": True})
        print("archived {}  {}".format(entry["created"], entry["source_title"][:64]))
    print("\narchived {} row(s) — the Agent Content Inbox was never modified".format(
        len(ledger["entries"])))
    return {"archived": len(ledger["entries"])}


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Migrate Agent Content Inbox rows into the central Content DB")
    sub = parser.add_subparsers(dest="cmd", required=True)

    plan = sub.add_parser("plan", help="print the mapped plan; no writes")
    plan.add_argument("--limit", type=int, default=0, help="only the first N rows (0 = all)")

    apply_cmd = sub.add_parser("apply", help="create the target rows")
    apply_cmd.add_argument("--limit", type=int, default=0)
    apply_cmd.add_argument("--ledger", default=LEDGER_DEFAULT)

    back = sub.add_parser("rollback", help="archive every page a ledger records")
    back.add_argument("--ledger", required=True)

    args = parser.parse_args(argv)
    token = nr.load_token()
    return {"plan": cmd_plan, "apply": cmd_apply, "rollback": cmd_rollback}[args.cmd](args, token)


if __name__ == "__main__":
    main()
