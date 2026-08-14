#!/usr/bin/env python3
"""
notion_rest.py — REST-based Notion I/O for the box agents (Augustus content workflow).

Why this exists: the hosted Notion MCP (https://mcp.notion.com, OAuth streamable-HTTP) keeps
dropping its long-lived stream mid-run, hanging unattended agents. This helper talks to the
Notion REST API with the "Praetorium" integration token (NOTION_API_TOKEN in secrets.env) over
plain request/response — no long-lived stream, nothing to stall on.

Target: data source "Content DB" (LinkedIn Content Planner) — the system of record since the
2026-08-14 migration off the Agent Content Inbox.
Reads the token itself from ~/.config/agent-workforce/secrets.env — no env injection needed.

Commands:
  board  [--status NAME] [--proposed-by NAME] [--json] [--max-rows N]
                                          List rows (Title + Status); optional filters.
  pitch  --angle .. --insight .. --evidence .. [--signal ..] [--type ..] [--body ..|--body-file F]
                                          Create a new pitch row (Status=Idea, Proposed by=Augustus).
  draft  --page PAGE_ID (--body ..|--body-file F) [--set-status Draft] [--force]
                                          Append draft text to a page body and set its Status.

All commands print a compact JSON result to stdout and exit non-zero on API error.
"""
import argparse, json, os, socket, sys, urllib.request, urllib.error

DATA_SOURCE_ID = "df18d768-1ede-82c1-9cf0-070ba3ef070e"
BOARD_NAME = "Content DB"
NOTION_VERSION = "2025-09-03"
API = "https://api.notion.com/v1"
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")

# NUC-46. buzz-agent@augustus runs codex-acp inside a bwrap mount namespace whose
# --tmpfs over ~/.config/agent-workforce replaces the credential directory, so on that
# path load_token() finds nothing and HTTPS is unreachable. He reaches Notion only
# through buzz-notion-broker.service, a host-namespace unit that owns the token and the
# write policy and answers one JSON line per connection on a 0600 unix socket.
#
# The transport is the only thing that differs. Every guard above this seam — the
# NUC-44 draft refusal and the --max-rows cap — runs before either path is chosen, so
# the two cannot diverge; tests/test_notion_rest_broker.py replays one case table
# through both to keep it that way.
BROKER_SOCKET_DEFAULT = "/run/user/%d/buzz-notion.sock" % os.getuid()

# Content DB's Status is a `status` property, not a `select`. The two are written and
# filtered with different JSON, and neither reports a shape error — a select-shaped write
# to a status property is rejected outright, while a select-shaped *read* just returns
# None, which reads as "no status" rather than as a bug.
PITCH_STATUS = "Idea"
DRAFTED_STATUS = "Draft"

# NUC-44. Two limits an agent used to be merely *asked* to respect, in
# profiles/augustus_content_task.md, and did not.
#
# Appending to a row that already carries a draft stacks two variant sets into one page:
# nothing in the board view shows it, and afterwards nobody can tell which paragraphs
# belong to which pass. This is an allowlist rather than the deny-list it replaced,
# because the deny-list's own comment predicted its failure mode — enumerating the known
# cases fails open on the next one, and Dave adds status options from the Notion UI
# (`Picked` arrived that way on 2026-08-14). An unrecognised status now refuses.
APPENDABLE_STATUSES = (PITCH_STATUS, "Picked")
DEFAULT_MAX_ROWS = 2  # per run; 0 = unlimited, which is what the machine callers pass


def find_token():
    """The HTTPS credential if one is reachable, else "". Never exits.

    Split from load_token so `--transport auto` can ask whether HTTPS is possible
    without the question itself being fatal inside augustus's namespace.
    """
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
        except (FileNotFoundError, PermissionError, OSError):
            pass
    return tok


def load_token():
    tok = find_token()
    if not tok:
        sys.exit("ERROR: NOTION_API_TOKEN not found in env or " + SECRETS)
    return tok


def broker_socket_path():
    return os.environ.get("BUZZ_NOTION_SOCKET") or BROKER_SOCKET_DEFAULT


def broker_call(tool, arguments, timeout=30):
    """One request per connection: the broker readline()s once, replies, and closes."""
    path = broker_socket_path()
    request = json.dumps({"tool": tool, "arguments": arguments}, separators=(",", ":"))
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as sock:
            sock.settimeout(timeout)
            sock.connect(path)
            sock.sendall(request.encode("utf-8") + b"\n")
            with sock.makefile("rb") as stream:
                raw = stream.readline()
    except OSError as e:
        sys.exit("Notion broker socket error on {} ({}): {}".format(path, tool, e))
    if not raw:
        sys.exit("Notion broker on {} closed the connection without a response "
                 "({})".format(path, tool))
    try:
        response = json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError) as e:
        sys.exit("Notion broker returned an unreadable response for {}: {}".format(tool, e))
    if not isinstance(response, dict) or "ok" not in response:
        sys.exit("Notion broker returned an unexpected response shape for {}: {}"
                 .format(tool, raw[:200]))
    if not response.get("ok"):
        sys.exit("Notion broker error on {}: {}".format(tool, response.get("error", "unknown")))
    return response.get("value")


def api_via_broker(method, path, token, payload=None, timeout=30):
    """The five REST calls this tool makes, expressed as the broker's tools.

    An unmapped path is an error rather than a pass-through: the broker deliberately
    exposes no raw REST surface, and inventing one here would put a hole in the policy
    it enforces outside augustus's namespace.
    """
    payload = payload or {}
    parts = path.strip("/").split("/")
    if method == "POST" and len(parts) == 3 and parts[0] == "data_sources" \
            and parts[2] == "query":
        args = {"data_source_id": parts[1], "page_size": payload.get("page_size", 100)}
        for key in ("filter", "start_cursor"):
            if payload.get(key) is not None:
                args[key] = payload[key]
        return broker_call("notion_query_data_source", args, timeout)
    if method == "GET" and len(parts) == 2 and parts[0] == "pages":
        return broker_call("notion_fetch", {"id": parts[1], "object_type": "page"}, timeout)
    if method == "PATCH" and len(parts) == 2 and parts[0] == "pages":
        return broker_call("notion_update_page",
                           {"page_id": parts[1], "properties": payload.get("properties", {})},
                           timeout)
    if method == "PATCH" and len(parts) == 3 and parts[0] == "blocks" \
            and parts[2] == "children":
        return broker_call("notion_append_blocks",
                           {"block_id": parts[1], "children": payload.get("children", [])},
                           timeout)
    if method == "POST" and len(parts) == 1 and parts[0] == "pages":
        args = {"parent": payload.get("parent"), "properties": payload.get("properties")}
        if payload.get("children") is not None:
            args["children"] = payload["children"]
        return broker_call("notion_create_page", args, timeout)
    sys.exit("notion_rest: no broker tool for {} {} — the broker exposes no raw REST "
             "and this must not invent one".format(method, path))


def resolve_transport(choice):
    """Deterministic, and never a silent fallback (criterion 2).

    `broker` that cannot find its socket is a hard error, not a quiet demotion to
    HTTPS: a run that reaches Notion by an unintended path is exactly the failure
    this seam exists to make visible.
    """
    if choice == "https":
        return "https"
    path = broker_socket_path()
    if choice == "broker":
        if not os.path.exists(path):
            sys.exit("--transport broker: no broker socket at {} — is "
                     "buzz-notion-broker.service running?".format(path))
        return "broker"
    if find_token():
        return "https"
    if os.path.exists(path):
        return "broker"
    return "https"  # no token and no socket: let load_token() raise the existing error


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
    sel = pv.get("status")
    return sel.get("name") if sel else None


def select_of(page, prop):
    pv = page.get("properties", {}).get(prop, {})
    sel = pv.get("select")
    return sel.get("name") if sel else None


def query_all(token, payload):
    """Every matching row, following Notion's cursor — not just the first page.

    Notion caps one query at 100 results and hides the rest behind `next_cursor`. Content
    DB passed 100 rows during the migration that made it the target (126 as of
    2026-08-14), so an unpaginated read returns a silent subset. content_board_digest.sh
    compares whole-board digests to decide whether augustus did anything, and a subset
    whose membership can shift between two reads is indistinguishable there from a real
    status change.
    """
    rows, cursor = [], None
    while True:
        page = dict(payload)
        if cursor:
            page["start_cursor"] = cursor
        res = api("POST", "/data_sources/{}/query".format(DATA_SOURCE_ID), token, page)
        rows.extend(res.get("results", []))
        cursor = res.get("next_cursor") if res.get("has_more") else None
        if not cursor:
            return rows


def cap_rows(rows, max_rows):
    """Hand back at most max_rows (0 = all), saying so on stderr when rows are dropped.

    The note goes to stderr, never stdout: --json output stays parseable, and a cap is
    never silent — a short list that looks like the whole board is how "handle max 2"
    turns into "there were only 2".
    """
    if not max_rows or max_rows <= 0 or len(rows) <= max_rows:
        return rows
    sys.stderr.write(
        "notion_rest: {} rows matched, returning {} — {} dropped by the per-run cap "
        "(--max-rows 0 for all)\n".format(len(rows), max_rows, len(rows) - max_rows))
    return rows[:max_rows]


def board_filter(status, proposed_by):
    clauses = []
    if status:
        clauses.append({"property": "Status", "status": {"equals": status}})
    if proposed_by:
        clauses.append({"property": "Proposed by", "select": {"equals": proposed_by}})
    if not clauses:
        return None
    return clauses[0] if len(clauses) == 1 else {"and": clauses}


def cmd_board(args, token):
    payload = {"page_size": 100}
    filt = board_filter(args.status, getattr(args, "proposed_by", None))
    if filt:
        payload["filter"] = filt
    rows = [{"id": p["id"], "angle": title_of(p), "status": status_of(p),
             "proposed_by": select_of(p, "Proposed by"),
             "url": p.get("url"), "last_edited": p.get("last_edited_time")}
            for p in query_all(token, payload)]
    rows = cap_rows(rows, getattr(args, "max_rows", DEFAULT_MAX_ROWS))
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        from collections import Counter
        counts = Counter(r["status"] for r in rows)
        print("{} — {} rows  {}".format(BOARD_NAME, len(rows), dict(counts)))
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
    # No pitch date is written: the inbox's `Pitched` date property has no counterpart on
    # Content DB, and Notion's own created_time already carries it.
    props = {
        "Title": {"title": rt(args.angle)},
        "Status": {"status": {"name": PITCH_STATUS}},
        "Proposed by": {"select": {"name": "Augustus"}},
        "POV": {"rich_text": rt(args.insight)},
        "Evidence": {"rich_text": rt(args.evidence)},
    }
    if args.signal:
        props["Topic"] = {"rich_text": rt(args.signal)}
    if args.type:
        props["Type"] = {"select": {"name": args.type}}
    payload = {"parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
               "properties": props}
    body = read_body(args)
    if body:
        payload["children"] = paragraph_blocks(body)
    res = api("POST", "/pages", token, payload)
    out = {"created": res["id"], "angle": args.angle, "status": PITCH_STATUS,
           "url": res.get("url")}
    print(json.dumps(out, indent=2))
    return out


def cmd_draft(args, token):
    body = read_body(args)
    if not body:
        sys.exit("draft: provide --body or --body-file")
    current = status_of(api("GET", "/pages/{}".format(args.page), token))
    # A page with no Status at all still appends: that is a schema surprise, not a
    # duplicate, and refusing it would turn a missing property into a silent no-op.
    if current is not None and current not in APPENDABLE_STATUSES and not args.force:
        sys.exit("draft: page {} is at Status={}, which is not one of {} — appending would "
                 "stack a second variant into the same body. Pass --force if that is what "
                 "you want.".format(args.page, current, "/".join(APPENDABLE_STATUSES)))
    api("PATCH", "/blocks/{}/children".format(args.page), token,
        {"children": paragraph_blocks(body)})
    result = {"page": args.page, "appended_chars": len(body)}
    if args.set_status:
        api("PATCH", "/pages/{}".format(args.page), token,
            {"properties": {"Status": {"status": {"name": args.set_status}}}})
        result["status"] = args.set_status
    print(json.dumps(result, indent=2))
    return result


def main(argv=None):
    # --transport is carried by a shared parent parser so it is accepted both before
    # and after the subcommand. default=SUPPRESS is load-bearing: without it the
    # subparser's own default overwrites a value given at the top level.
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--transport", choices=["https", "broker", "auto"],
                        default=argparse.SUPPRESS,
                        help="how to reach Notion (default auto: HTTPS when a token is "
                             "readable, else the Buzz broker socket)")

    p = argparse.ArgumentParser(description="REST Notion I/O for " + BOARD_NAME,
                                parents=[common])
    sub = p.add_subparsers(dest="cmd", required=True)

    b = sub.add_parser("board", help="list rows", parents=[common])
    b.add_argument("--status", help="filter by Status (Idea/Picked/Draft/Review/...)")
    b.add_argument("--proposed-by", help="filter by Proposed by (Dave/Augustus/Claudius)")
    b.add_argument("--json", action="store_true")
    b.add_argument("--max-rows", type=int, default=DEFAULT_MAX_ROWS,
                   help="cap rows handed to one run (default %d; 0 = all)" % DEFAULT_MAX_ROWS)

    pi = sub.add_parser("pitch", help="create a pitch row", parents=[common])
    pi.add_argument("--angle", required=True, help="Title")
    pi.add_argument("--insight", required=True, help="POV")
    pi.add_argument("--evidence", required=True)
    pi.add_argument("--signal", default="", help="Topic")
    pi.add_argument("--type", choices=["Text-only", "Single-image", "Multi-image", "Video",
                                       "Article", "Newsletter", "Document",
                                       "Celebrate an Occasion", "Polls"])
    pi.add_argument("--body")
    pi.add_argument("--body-file")

    d = sub.add_parser("draft", help="append draft text + set status on a page",
                       parents=[common])
    d.add_argument("--page", required=True)
    d.add_argument("--body")
    d.add_argument("--body-file")
    d.add_argument("--set-status", default=DRAFTED_STATUS)
    d.add_argument("--force", action="store_true",
                   help="append even when the page already carries a draft")

    args = p.parse_args(argv)
    transport = resolve_transport(getattr(args, "transport", "auto"))
    if transport == "broker":
        # Announced, never inferred — a run that reached Notion by the other path
        # should never have to be deduced from its effects afterwards.
        sys.stderr.write("notion_rest: transport=broker via {} (no HTTPS token in this "
                         "namespace)\n".format(broker_socket_path()))
        global api
        api = api_via_broker
        token = ""  # the broker owns the credential; asking for one here would hard-exit
    else:
        token = load_token()
    {"board": cmd_board, "pitch": cmd_pitch, "draft": cmd_draft}[args.cmd](args, token)


if __name__ == "__main__":
    main()
