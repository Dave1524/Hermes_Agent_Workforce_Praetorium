#!/usr/bin/env python3
"""sprint_board_counts.py — read-only Status tally of the NUC Sprint Board (NUC-41).

Queries the Sprint Board data source and prints a count per Status `select` value.
Read-only: it never writes to Notion. Reads NOTION_API_TOKEN from env or
~/.config/agent-workforce/secrets.env (same convention as the other box helpers).

Usage:
  sprint_board_counts.py            Human line: "To do=3  In progress=1  Done=12  (total 16)"
  sprint_board_counts.py --json     {"To do": 3, "In progress": 1, ...}

Exits non-zero (no token / API error) so callers can degrade to "unavailable".
"""
import json, os, sys, urllib.request, urllib.error

API = "https://api.notion.com/v1"
NOTION_VERSION = "2025-09-03"
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")
DATA_SOURCE_ID = os.environ.get(
    "SPRINT_BOARD_DS", "ff0e1f87-8238-412c-8db3-5e53c39fc6e7")
STATUS_ORDER = ["Backlog", "To do", "In progress", "Blocked", "Done"]


def load_token():
    tok = os.environ.get("NOTION_API_TOKEN", "").strip()
    if not tok and os.path.exists(SECRETS):
        for line in open(SECRETS):
            if line.strip().startswith("NOTION_API_TOKEN="):
                tok = line.split("=", 1)[1].strip().strip('"').strip("'")
    if not tok:
        sys.exit("ERROR: NOTION_API_TOKEN not found (env or secrets.env)")
    return tok


def query_page(token, cursor):
    payload = {"page_size": 100}
    if cursor:
        payload["start_cursor"] = cursor
    req = urllib.request.Request(
        "{}/data_sources/{}/query".format(API, DATA_SOURCE_ID),
        data=json.dumps(payload).encode(), method="POST",
        headers={"Authorization": "Bearer " + token,
                 "Notion-Version": NOTION_VERSION,
                 "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        sys.exit("Notion API {}: {}".format(e.code, e.read().decode()[:200]))
    except urllib.error.URLError as e:
        sys.exit("Notion API network error: {}".format(e))


def status_of(page):
    sel = page.get("properties", {}).get("Status", {}).get("select")
    return sel.get("name") if sel else "(none)"


def tally(token):
    counts, cursor = {}, None
    while True:
        res = query_page(token, cursor)
        for page in res.get("results", []):
            name = status_of(page)
            counts[name] = counts.get(name, 0) + 1
        if not res.get("has_more"):
            return counts
        cursor = res.get("next_cursor")


def ordered_items(counts):
    known = [(s, counts[s]) for s in STATUS_ORDER if s in counts]
    extra = [(s, counts[s]) for s in sorted(counts) if s not in STATUS_ORDER]
    return known + extra


def main():
    counts = tally(load_token())
    items = ordered_items(counts)
    if "--json" in sys.argv[1:]:
        print(json.dumps(dict(items)))
        return
    total = sum(n for _, n in items)
    body = "  ".join("{}={}".format(s, n) for s, n in items) or "(no cards)"
    print("{}  (total {})".format(body, total))


if __name__ == "__main__":
    main()
