#!/usr/bin/env python3
"""
notion_publish_doc.py — publish one markdown document as a standalone Notion page.

Create-once by slug, replace-body on every later run: re-publishing updates the page
in place instead of stacking a second copy or minting a second page. A bare Notion page
has no reliable exact-title lookup through the API, so the idempotency key is owned
locally in STATE_FILE — the same reason and the same shape as notion_research_page.py,
which owns *append*-shaped pages. This one owns *replace*-shaped ones.

Body rendering goes through notion_markdown.blocks_from_markdown, so headings, tables
and code fences arrive as Notion blocks. notion_research_page.py uses paragraph_blocks
and would deliver this document as literal markdown text in a wall of paragraphs.

Commands:
  publish --slug S --title T --parent-page-id P --body-file F
  show    --slug S
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notion_markdown import blocks_from_markdown  # noqa: E402  — the shared converter
from notion_rest import api as rest_api, load_token, rt  # noqa: E402

STATE_FILE = os.path.expanduser("~/agent-workforce/var/notion_published_docs.json")
BLOCKS_PER_REQUEST = 100


def load_state():
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2, sort_keys=True)
    os.replace(tmp, STATE_FILE)


def ensure_page(api, state, slug, title, parent_page_id):
    entry = state.get(slug)
    if entry:
        return entry
    page = api("POST", "/pages", {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": {"title": rt(title)}},
    })
    entry = {"page_id": page["id"], "title": title, "url": page.get("url"), "publish_count": 0}
    state[slug] = entry
    save_state(state)
    return entry


def child_ids(api, page_id):
    ids, cursor = [], None
    while True:
        path = "/blocks/{}/children?page_size=100".format(page_id)
        if cursor:
            path += "&start_cursor=" + cursor
        page = api("GET", path)
        ids += [b["id"] for b in page.get("results", [])]
        cursor = page.get("next_cursor")
        if not page.get("has_more"):
            return ids


def replace_children(api, page_id, blocks):
    for block_id in child_ids(api, page_id):
        api("DELETE", "/blocks/" + block_id)
    for i in range(0, len(blocks), BLOCKS_PER_REQUEST):
        api("PATCH", "/blocks/{}/children".format(page_id),
            {"children": blocks[i:i + BLOCKS_PER_REQUEST]})


def read_body(path):
    with open(path) as f:
        return f.read().strip()


def cmd_publish(args, api):
    body = read_body(args.body_file)
    if not body:
        sys.exit("notion_publish_doc: refusing an empty body — an empty page is "
                 "indistinguishable from a failed publish once it is in Notion")

    state = load_state()
    entry = ensure_page(api, state, args.slug, args.title, args.parent_page_id)
    replace_children(api, entry["page_id"], blocks_from_markdown(body))

    entry["publish_count"] += 1
    entry["last_published_utc"] = datetime.datetime.now(
        datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    state[args.slug] = entry
    save_state(state)
    print(json.dumps({"slug": args.slug, "page_id": entry["page_id"],
                      "url": entry.get("url"), "publish": entry["publish_count"]}))


def cmd_show(args, _api):
    entry = load_state().get(args.slug)
    if not entry:
        sys.exit("notion_publish_doc: no page published under slug " + args.slug)
    print(json.dumps(entry, indent=2, sort_keys=True))


def parse_args(argv):
    p = argparse.ArgumentParser(description="publish a markdown file as a Notion page")
    sub = p.add_subparsers(dest="cmd", required=True)

    pub = sub.add_parser("publish", help="create or replace the page for this slug")
    pub.add_argument("--slug", required=True)
    pub.add_argument("--title", required=True)
    pub.add_argument("--parent-page-id", required=True)
    pub.add_argument("--body-file", required=True)
    pub.set_defaults(func=cmd_publish)

    show = sub.add_parser("show", help="print the recorded page for this slug")
    show.add_argument("--slug", required=True)
    show.set_defaults(func=cmd_show)

    return p.parse_args(argv)


def main(argv=None, api=None):
    args = parse_args(argv)
    if api is None:
        token = load_token()

        def api(method, path, payload=None):
            return rest_api(method, path, token, payload)
    args.func(args, api)


if __name__ == "__main__":
    main()
