#!/usr/bin/env python3
"""
notion_rest.py — REST-based Notion I/O for the box agents (Augustus content workflow).

Why this exists: the hosted Notion MCP (https://mcp.notion.com, OAuth streamable-HTTP) keeps
dropping its long-lived stream mid-run, hanging unattended agents. This helper talks to the
Notion REST API with the "Praetorium" integration token (NOTION_API_TOKEN in secrets.env) over
plain request/response — no long-lived stream, nothing to stall on.

Target: data source "Agent Content Inbox" (LinkedIn Content Planner).
Reads the token itself from ~/.config/agent-workforce/secrets.env — no env injection needed.

Commands:
  board  [--status NAME] [--json]         List rows (Angle + Status); optional status filter.
  pitch  --angle .. --insight .. --evidence .. [--signal ..] [--format ..] [--body ..|--body-file F]
                                          Create a new pitch row (Status=Pitched, Proposed by=Augustus).
  draft  --page PAGE_ID (--body ..|--body-file F) [--set-status Drafted]
                                          Append draft text to a page body and set its Status.

All commands print a compact JSON result to stdout and exit non-zero on API error.
"""
import argparse, json, os, sys, datetime, urllib.request, urllib.error

DATA_SOURCE_ID = "ab5eb999-e986-4a8b-9159-eb340196af9b"
NOTION_VERSION = "2025-09-03"
API = "https://api.notion.com/v1"
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")


def load_token():
    tok = os.environ.get("NOTION_API_TOKEN", "").strip()
    if not tok:
        try:
            with open(SECRETS) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("NOTION_API_TOKEN="):
                        v = line.split("=", 1)[1].strip().strip('"').strip("'")
                        if v:
                            tok = v  # last non-empty assignment wins
        except FileNotFoundError:
            pass
    if not tok:
        sys.exit("ERROR: NOTION_API_TOKEN not found in env or " + SECRETS)
    return tok


def api(method, path, token, payload=None, timeout=30):
    url = API + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            j = json.loads(body)
            msg = j.get("message", body)
        except Exception:
            msg = body
        sys.exit("Notion API {} on {} {}: {}".format(e.code, method, path, msg[:300]))
    except urllib.error.URLError as e:
        sys.exit("Notion API network error on {} {}: {}".format(method, path, e))


def rt(s):
    """rich_text array, chunked to Notion's 2000-char-per-object limit."""
    s = s or ""
    return [{"type": "text", "text": {"content": s[i:i + 1900]}} for i in range(0, len(s), 1900)] or \
           [{"type": "text", "text": {"content": ""}}]


def title_of(page):
    for pv in page.get("properties", {}).values():
        if pv.get("type") == "title":
            return "".join(t.get("plain_text", "") for t in pv.get("title", []))
    return ""


def status_of(page):
    pv = page.get("properties", {}).get("Status", {})
    sel = pv.get("select")
    return sel.get("name") if sel else None


def cmd_board(args, token):
    payload = {"page_size": 100}
    if args.status:
        payload["filter"] = {"property": "Status", "select": {"equals": args.status}}
    res = api("POST", "/data_sources/{}/query".format(DATA_SOURCE_ID), token, payload)
    rows = [{"id": p["id"], "angle": title_of(p), "status": status_of(p),
             "url": p.get("url")} for p in res.get("results", [])]
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        from collections import Counter
        counts = Counter(r["status"] for r in rows)
        print("Agent Content Inbox — {} rows  {}".format(
            len(rows), dict(counts)))
        for r in rows:
            print("  [{}] {}  ({})".format(r["status"], r["angle"][:70], r["id"]))
    return rows


def paragraph_blocks(text):
    blocks = []
    for para in text.split("\n\n"):
        para = para.strip("\n")
        if para == "":
            continue
        blocks.append({"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": rt(para)}})
    return blocks or [{"object": "block", "type": "paragraph",
                       "paragraph": {"rich_text": rt(text)}}]


def read_body(args):
    if getattr(args, "body_file", None):
        with open(args.body_file) as f:
            return f.read()
    return getattr(args, "body", None) or ""


def cmd_pitch(args, token):
    today = datetime.date.today().isoformat()
    props = {
        "Angle": {"title": rt(args.angle)},
        "Status": {"select": {"name": "Pitched"}},
        "Proposed by": {"select": {"name": "Augustus"}},
        "Second-order insight": {"rich_text": rt(args.insight)},
        "Evidence": {"rich_text": rt(args.evidence)},
        "Pitched": {"date": {"start": today}},
    }
    if args.signal:
        props["Signal"] = {"rich_text": rt(args.signal)}
    if args.format:
        props["Format"] = {"select": {"name": args.format}}
    payload = {"parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
               "properties": props}
    body = read_body(args)
    if body:
        payload["children"] = paragraph_blocks(body)
    res = api("POST", "/pages", token, payload)
    out = {"created": res["id"], "angle": args.angle, "status": "Pitched", "url": res.get("url")}
    print(json.dumps(out, indent=2))
    return out


def cmd_draft(args, token):
    body = read_body(args)
    if not body:
        sys.exit("draft: provide --body or --body-file")
    api("PATCH", "/blocks/{}/children".format(args.page), token,
        {"children": paragraph_blocks(body)})
    result = {"page": args.page, "appended_chars": len(body)}
    if args.set_status:
        api("PATCH", "/pages/{}".format(args.page), token,
            {"properties": {"Status": {"select": {"name": args.set_status}}}})
        result["status"] = args.set_status
    print(json.dumps(result, indent=2))
    return result


def main():
    p = argparse.ArgumentParser(description="REST Notion I/O for the Agent Content Inbox")
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("board", help="list rows")
    b.add_argument("--status", help="filter by Status (Pitched/Picked/Drafted/...)")
    b.add_argument("--json", action="store_true")

    pi = sub.add_parser("pitch", help="create a pitch row")
    pi.add_argument("--angle", required=True)
    pi.add_argument("--insight", required=True, help="Second-order insight")
    pi.add_argument("--evidence", required=True)
    pi.add_argument("--signal", default="")
    pi.add_argument("--format", choices=["LinkedIn post", "Carousel", "Article", "Other"])
    pi.add_argument("--body")
    pi.add_argument("--body-file")

    d = sub.add_parser("draft", help="append draft text + set status on a page")
    d.add_argument("--page", required=True)
    d.add_argument("--body")
    d.add_argument("--body-file")
    d.add_argument("--set-status", default="Drafted")

    args = p.parse_args()
    token = load_token()
    {"board": cmd_board, "pitch": cmd_pitch, "draft": cmd_draft}[args.cmd](args, token)


if __name__ == "__main__":
    main()
