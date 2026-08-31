#!/usr/bin/env python3
"""ops_page_publish.py — replace an existing Notion page's body with the ops snapshot (NUC-41).

Reads the composed snapshot (markdown) from stdin and writes it to the page named by
OPS_PAGE_ID, replacing the previous body so the page stays a single live pane. It NEVER
creates a page: an unset OPS_PAGE_ID is a hard refusal (Dave's gated finish). Token and
page id come from env or ~/.config/agent-workforce/secrets.env.

This path is only reachable once Dave has created the page and set OPS_PAGE_ID; the
overnight run leaves it dormant (no page, no write).
"""
import json, os, sys, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notion_markdown import blocks_from_markdown  # noqa: E402  — the shared converter

API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")


def from_secrets(key):
    if not os.path.exists(SECRETS):
        return ""
    val = ""
    for line in open(SECRETS):
        line = line.strip()
        if line.startswith(key + "="):
            val = line.split("=", 1)[1].strip().strip('"').strip("'")
    return val


def require(key):
    val = os.environ.get(key, "").strip() or from_secrets(key)
    if not val:
        sys.exit("REFUSED: {} not set — refusing to publish (no page is created).".format(key))
    return val


def api(method, path, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit("Notion API {} on {} {}: {}".format(e.code, method, path, e.read().decode()[:200]))
    except urllib.error.URLError as e:
        sys.exit("Notion API network error on {} {}: {}".format(method, path, e))


def clear_children(page_id, token):
    res = api("GET", "/blocks/{}/children?page_size=100".format(page_id), token)
    for block in res.get("results", []):
        api("DELETE", "/blocks/{}".format(block["id"]), token)


def append_children(page_id, blocks, token):
    for i in range(0, len(blocks), 100):
        api("PATCH", "/blocks/{}/children".format(page_id), token,
            {"children": blocks[i:i + 100]})


def main():
    token = require("NOTION_API_TOKEN")
    page_id = require("OPS_PAGE_ID")
    blocks = blocks_from_markdown(sys.stdin.read())
    clear_children(page_id, token)
    append_children(page_id, blocks, token)
    print("OK  published {} blocks -> page {}".format(len(blocks), page_id))


if __name__ == "__main__":
    main()
