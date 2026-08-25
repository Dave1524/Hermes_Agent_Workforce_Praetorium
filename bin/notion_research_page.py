#!/usr/bin/env python3
"""
notion_research_page.py — create-once, append-always Notion page for a standing
research topic (the two overnight jobs: 2026 content strategy, faceless content as a
digital product).

Each topic gets ONE Notion page with a new dated section appended every run — never a
new page per run, never a replace of prior content. A bare Notion page (not a database
row) has no reliable exact-title search via the API, so idempotency is owned locally:
STATE_FILE maps slug -> {page_id, run_count, ...}. Mirrors notion_daily.py's
"the helper owns the idempotency key" rule, just keyed on a local file instead of a
Notion-side query, because the target here is a page, not a database row.

Reads the Notion token via notion_rest.load_token() (env or
~/.config/agent-workforce/secrets.env) — no separate credential handling.

Commands:
  append-section --slug S --title T --parent-page-id P [--total-runs N]
                  (--body TEXT | --body-file F)
                  Ensure the page exists (creating it under --parent-page-id on first
                  call), then append one heading_2 + body section. Never replaces.
  show --slug S   Print every prior section's text (empty if the page doesn't exist
                  yet). Read this before researching so a run advances prior nights'
                  findings instead of re-covering them.
"""
import argparse
import datetime
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notion_rest import api, load_token, paragraph_blocks, rt  # noqa: E402

STATE_FILE = os.path.expanduser("~/agent-workforce/var/notion_research_pages.json")


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


def ensure_page(token, state, slug, title, parent_page_id):
    entry = state.get(slug)
    if entry:
        return entry
    payload = {
        "parent": {"type": "page_id", "page_id": parent_page_id},
        "properties": {"title": {"title": rt(title)}},
    }
    page = api("POST", "/pages", token, payload)
    entry = {"page_id": page["id"], "title": title, "url": page.get("url"), "run_count": 0}
    state[slug] = entry
    save_state(state)
    return entry


def append_children(token, page_id, blocks):
    for i in range(0, len(blocks), 100):
        api("PATCH", "/blocks/{}/children".format(page_id), token,
            {"children": blocks[i:i + 100]})


def cmd_append_section(args, token):
    state = load_state()
    entry = ensure_page(token, state, args.slug, args.title, args.parent_page_id)

    body = args.body
    if args.body_file:
        with open(args.body_file) as f:
            body = f.read()
    body = (body or "").strip()
    if not body:
        sys.exit("notion_research_page: refusing an empty section — a run that finds "
                 "nothing must still say so, in --body/--body-file, with the reason")

    run_number = entry["run_count"] + 1
    now = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    heading = "{} — Run {}/{}".format(now, run_number, args.total_runs)

    blocks = [{"object": "block", "type": "heading_2", "heading_2": {"rich_text": rt(heading)}}]
    blocks += paragraph_blocks(body)
    append_children(token, entry["page_id"], blocks)

    entry["run_count"] = run_number
    entry["last_run_utc"] = now
    state[args.slug] = entry
    save_state(state)

    print(json.dumps({
        "slug": args.slug,
        "page_id": entry["page_id"],
        "url": entry.get("url"),
        "run": "{}/{}".format(run_number, args.total_runs),
        "heading": heading,
    }, indent=2))


def fetch_section_text(token, page_id):
    lines = []
    cursor = None
    while True:
        path = "/blocks/{}/children".format(page_id)
        if cursor:
            path += "?start_cursor={}".format(cursor)
        res = api("GET", path, token)
        for block in res.get("results", []):
            btype = block.get("type")
            text = "".join(t.get("plain_text", "") for t in block.get(btype, {}).get("rich_text", []))
            if not text:
                continue
            lines.append(("\n## " if btype == "heading_2" else "") + text)
        cursor = res.get("next_cursor") if res.get("has_more") else None
        if not cursor:
            return "\n".join(lines)


def cmd_show(args, token):
    entry = load_state().get(args.slug)
    if not entry:
        print("(no page yet for slug={} — this will be the first run)".format(args.slug))
        return
    print(fetch_section_text(token, entry["page_id"]))


def main(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("append-section",
                        help="ensure the topic page exists, then append one dated section")
    a.add_argument("--slug", required=True, help="stable local key, e.g. content-strategy-2026")
    a.add_argument("--title", required=True, help="page title, used only on first creation")
    a.add_argument("--parent-page-id", required=True)
    a.add_argument("--total-runs", type=int, default=6)
    a.add_argument("--body")
    a.add_argument("--body-file")
    a.set_defaults(func=cmd_append_section)

    s = sub.add_parser("show", help="print every prior section's text for a slug")
    s.add_argument("--slug", required=True)
    s.set_defaults(func=cmd_show)

    args = p.parse_args(argv)
    token = load_token()
    args.func(args, token)


if __name__ == "__main__":
    main()
