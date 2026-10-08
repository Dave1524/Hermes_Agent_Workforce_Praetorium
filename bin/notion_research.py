#!/usr/bin/env python3
"""
notion_research.py — the card's page in the Notion Research database (Dev Plan B3, spec §3.7).

A research run writes one file, `research.md`. The wrapper (agent_propose.sh) publishes it here as
the card's page; the agent never holds a Notion credential and never calls Notion. One page per
card, keyed by the `Card` property: the first run creates it, every later run replaces its body,
and Notion's page history keeps each version. Same idempotency shape as notion_daily.py, keyed by
card instead of date.

  publish --card ID --from-file F [--title T] [--run-id R]   create or rewrite; prints page + hash
  export  --card ID [--out F] [--if-exists]                  the page as it stands, as markdown
  mark    --card ID --state published|merged|rejected [--path P]

`page_hash` is the board's text hash (board.text_hash): of the file for publish, of the exported
text for export. Both are the hash an approval carries.

The database id is NOTION_RESEARCH_DS, from the environment or secrets.env beside the token. The
property names below are this module's contract with the database Dave shares (D9).
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from board import SLUG, text_hash  # noqa: E402  — the ledger's hash and card-id rule
from notion_daily import NotionHttp, child_ids, plain, replace_children, rt  # noqa: E402
from notion_markdown import blocks_from_markdown  # noqa: E402
from notion_rest import SECRETS, load_token  # noqa: E402

DS_VARIABLE = "NOTION_RESEARCH_DS"
TITLE, CARD, RUN, VERSION, PUBLISHED, STATE, VAULT_PATH = (
    "Name", "Card", "Run", "Version", "Published", "State", "Vault path")
STATES = ("published", "merged", "rejected")


def data_source():
    value = os.environ.get(DS_VARIABLE, "").strip()
    if not value:
        try:
            with open(SECRETS) as f:
                for line in f:
                    if line.strip().startswith(DS_VARIABLE + "="):
                        value = line.split("=", 1)[1].strip().strip('"').strip("'") or value
        except OSError:
            pass
    if not value:
        sys.exit("ERROR: {} not set in the environment or {} (D9: the Research database id)"
                 .format(DS_VARIABLE, SECRETS))
    return value


def card_id(value):
    if not SLUG.match(value or ""):
        sys.exit("ERROR: not a card id: {!r}".format(value))
    return value


def find_page(api, ds, card):
    found = api.call("POST", "/data_sources/{}/query".format(ds), {
        "page_size": 1, "filter": {"property": CARD, "rich_text": {"equals": card}}})
    rows = found.get("results", [])
    return rows[0] if rows else None


def next_version(row):
    current = ((row or {}).get("properties", {}).get(VERSION) or {}).get("number") or 0
    return int(current) + 1


def canonical(api, text):
    return blocks_to_markdown(api, blocks_from_markdown(text))


def publish_props(api, args, text, version):
    return {
        TITLE: {"title": rt(args.title or args.card)},
        CARD: {"rich_text": rt(args.card)},
        RUN: {"rich_text": rt(args.run_id or "")},
        VERSION: {"number": version},
        PUBLISHED: {"rich_text": rt(text_hash(canonical(api, text)))},
        STATE: {"rich_text": rt("published")},
    }


def read_text(path):
    with open(os.path.expanduser(path)) as f:
        return f.read()


def cmd_publish(args, api):
    ds, text = data_source(), read_text(args.from_file)
    row = find_page(api, ds, args.card)
    props = publish_props(api, args, text, next_version(row))
    if row:
        api.call("PATCH", "/pages/" + row["id"], {"properties": props})
        page_id, url, action = row["id"], row.get("url"), "updated"
    else:
        created = api.call("POST", "/pages", {
            "parent": {"type": "data_source_id", "data_source_id": ds}, "properties": props})
        page_id, url, action = created["id"], created.get("url"), "created"
    replace_children(api, page_id, blocks_from_markdown(text))
    return emit({"card": args.card, "page": page_id, "url": url, "action": action,
                 "version": props[VERSION]["number"],
                 "page_hash": text_hash(canonical(api, text))})


def spans_to_markdown(spans):
    out = []
    for span in spans:
        text, marks = span.get("text", {}).get("content", ""), span.get("annotations") or {}
        link = (span.get("text", {}).get("link") or {}).get("url")
        if marks.get("code"):
            text = "`{}`".format(text)
        if marks.get("bold"):
            text = "**{}**".format(text)
        if marks.get("italic"):
            text = "*{}*".format(text)
        if link and link != text:
            text = "[{}]({})".format(text, link)
        out.append(text)
    return "".join(out)


def rows_of(api, block):
    table = block.get("table", {})
    kids = table.get("children")
    if kids is None:
        kids = api.call("GET", "/blocks/{}/children?page_size=100".format(block["id"])).get("results", [])
    return [[spans_to_markdown(c) for c in k["table_row"]["cells"]] for k in kids]


def table_to_markdown(rows):
    width = len(rows[0])
    lines = ["| " + " | ".join(r) + " |" for r in rows]
    lines.insert(1, "| " + " | ".join(["---"] * width) + " |")
    return "\n".join(lines)


def block_to_markdown(api, block, number):
    kind = block["type"]
    body = block.get(kind, {})
    text = spans_to_markdown(body.get("rich_text", []))
    if kind.startswith("heading_"):
        return "#" * int(kind[-1]) + " " + text
    if kind == "bulleted_list_item":
        return "- " + text
    if kind == "numbered_list_item":
        return "{}. {}".format(number, text)
    if kind == "quote":
        return "> " + text
    if kind == "code":
        return "```\n{}\n```".format("".join(s["text"]["content"] for s in body.get("rich_text", [])))
    if kind == "divider":
        return "---"
    if kind == "table":
        return table_to_markdown(rows_of(api, block))
    return text


def blocks_to_markdown(api, blocks):
    parts, number, previous = [], 0, None
    for block in blocks:
        number = number + 1 if block["type"] == "numbered_list_item" else 0
        rendered = block_to_markdown(api, block, number)
        listy = block["type"] in ("bulleted_list_item", "numbered_list_item")
        same = previous == block["type"]
        parts.append(("\n" if listy and same else "\n\n") + rendered if parts else rendered)
        previous = block["type"]
    return "".join(parts) + "\n"


def page_blocks(api, page_id):
    blocks, cursor = [], None
    while True:
        path = "/blocks/{}/children?page_size=100".format(page_id) + ("&start_cursor=" + cursor if cursor else "")
        page = api.call("GET", path)
        blocks += page.get("results", [])
        if not page.get("has_more"):
            return blocks
        cursor = page["next_cursor"]


def cmd_export(args, api):
    row = find_page(api, data_source(), args.card)
    if not row:
        if args.if_exists:
            return emit({"card": args.card, "page": None})
        sys.exit("ERROR: no page for card {} in the Research database".format(args.card))
    text = blocks_to_markdown(api, page_blocks(api, row["id"]))
    if args.out:
        with open(os.path.expanduser(args.out), "w") as f:
            f.write(text)
    else:
        sys.stdout.write(text)
    return emit({"card": args.card, "page": row["id"], "url": row.get("url"), "page_hash": text_hash(text),
                 "published_hash": plain(row["properties"].get(PUBLISHED, {}))}, to_stderr=not args.out)


def cmd_mark(args, api):
    row = find_page(api, data_source(), args.card)
    if not row:
        sys.exit("ERROR: no page for card {} in the Research database".format(args.card))
    props = {STATE: {"rich_text": rt(args.state)}}
    if args.path:
        props[VAULT_PATH] = {"rich_text": rt(args.path)}
    api.call("PATCH", "/pages/" + row["id"], {"properties": props})
    return emit({"card": args.card, "page": row["id"], "state": args.state, "path": args.path})


def emit(result, to_stderr=False):
    print(json.dumps(result, indent=2), file=sys.stderr if to_stderr else sys.stdout)
    return result


def parse_args(argv):
    parser = argparse.ArgumentParser(description="The card's page in the Notion Research database")
    sub = parser.add_subparsers(dest="cmd", required=True)
    pub = sub.add_parser("publish", help="create or rewrite the card's page from a file")
    pub.add_argument("--card", required=True)
    pub.add_argument("--from-file", required=True)
    pub.add_argument("--title")
    pub.add_argument("--run-id")
    exp = sub.add_parser("export", help="the page as it stands, as markdown")
    exp.add_argument("--card", required=True)
    exp.add_argument("--out")
    exp.add_argument("--if-exists", action="store_true", help="no page is not an error")
    mark = sub.add_parser("mark", help="set the page's state and vault path")
    mark.add_argument("--card", required=True)
    mark.add_argument("--state", required=True, choices=STATES)
    mark.add_argument("--path")
    args = parser.parse_args(argv)
    card_id(args.card)
    return args


def main(argv=None, api=None):
    args = parse_args(argv)
    data_source()
    api = api or NotionHttp(load_token())
    return {"publish": cmd_publish, "export": cmd_export, "mark": cmd_mark}[args.cmd](args, api)


if __name__ == "__main__":
    main()
