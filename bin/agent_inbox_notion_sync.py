#!/usr/bin/env python3
"""agent_inbox_notion_sync.py — deterministic box→Notion sync for the Agent Inbox DB.

Replaces the glm-5.2 LLM cron (agent-inbox-sync, jobs.json 98e6eb41f553) with a no-model
REST reconcile: an LLM was needlessly *executing* a fully-specified algorithm (and failing
on the exhausted OpenRouter budget). This is that algorithm, deterministic and free.

Direction: read-only on git, write-only on Notion (same contract as the old cron).
  1. CREATE: for every _inbox/agents/*.md proposal not yet in the DB (exact Filename match),
     create a row (Status=New; Proposal Date = file mtime; Source inferred; Excerpt + Box Link).
  2. REFLECT: for DB rows whose proposal file is gone AND still New/Approved, read the
     box-safe approvals.tsv; if a promoted/rejected decision is recorded, set Status +
     Processed At so Notion mirrors what happened on the Mac. (Skipped if approvals.tsv absent.)

Token: NOTION_API_TOKEN from env or ~/.config/agent-workforce/secrets.env. Never the MCP
(it linkifies .md filenames and breaks exact-Filename dedup).
"""
import argparse, json, os, sys, glob, datetime, urllib.request, urllib.error

DATA_SOURCE_ID = "ecb52f8e-2125-416f-b08e-824a7416e561"
NOTION_VERSION = "2025-09-03"
API = "https://api.notion.com/v1"
INBOX_DIR = os.path.expanduser("~/agent-worktrees/inbox/_inbox/agents")
APPROVALS = os.path.join(INBOX_DIR, "_metrics", "approvals.tsv")
BOX_LINK_BASE = ("https://github.com/Dave1524/obsidian-ai-os-boxsafe/blob/"
                 "agents/inbox/_inbox/agents/")
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")


def load_token():
    tok = os.environ.get("NOTION_API_TOKEN", "").strip()
    if not tok and os.path.exists(SECRETS):
        for line in open(SECRETS):
            line = line.strip()
            if line.startswith("NOTION_API_TOKEN="):
                v = line.split("=", 1)[1].strip().strip('"').strip("'")
                if v:
                    tok = v
    if not tok:
        sys.exit("ERROR: NOTION_API_TOKEN missing (env or %s)" % SECRETS)
    return tok


def api(method, path, token, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(API + path, data=data, method=method, headers={
        "Authorization": "Bearer " + token, "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        sys.exit("Notion API %s on %s %s: %s" % (e.code, method, path, body[:300]))


def rt(s):
    return [{"type": "text", "text": {"content": (s or "")[:1900]}}]


def source_for(fn):
    n = fn.lower()
    if "bd-stall-radar" in n or "bd_stall_radar" in n:
        return "bd_stall_radar"
    if "weekly-pre-assembly" in n or "weekly_pre_assembly" in n:
        return "weekly_pre_assembly"
    if "signal-scan" in n or "m1-signal" in n:
        return "m1_signal_scan"
    if n.startswith(tuple("0123456789")) and "seo" in n:
        return "other"
    return "research_analyst"


def title_and_excerpt(path):
    """H1 → title (drop a trailing ' (date, author)' stamp); first substantive line → excerpt."""
    title, excerpt = "", ""
    try:
        lines = open(path, encoding="utf-8").read().splitlines()
    except OSError:
        return os.path.basename(path), ""
    for ln in lines:
        s = ln.strip()
        if s.startswith("# ") and not title:
            title = s[2:].strip()
            # strip a trailing parenthetical stamp like "(2026-07-13, claudius)"
            if title.endswith(")") and "(" in title:
                head = title[:title.rfind("(")].rstrip()
                if head:
                    title = head
            continue
        if title and s and not s.startswith("#") and not s.startswith("---") \
                and not s.startswith(("- ", "* ", ">", "```", "|")):
            excerpt = s
            break
    if not title:
        title = os.path.basename(path)
    return title[:200], excerpt[:280]


def mtime_date(path):
    return datetime.date.fromtimestamp(os.path.getmtime(path)).isoformat()


def inbox_files():
    return sorted(os.path.basename(p) for p in glob.glob(os.path.join(INBOX_DIR, "*.md")))


def all_rows(token):
    rows, cur = [], None
    while True:
        payload = {"page_size": 100}
        if cur:
            payload["start_cursor"] = cur
        d = api("POST", "/data_sources/%s/query" % DATA_SOURCE_ID, token, payload)
        rows += d.get("results", [])
        if not d.get("has_more"):
            break
        cur = d["next_cursor"]
    return rows


def prop_text(row, name):
    pv = row["properties"].get(name, {})
    t = pv.get("type")
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in pv["rich_text"])
    if t in ("select", "status"):
        return (pv.get(t) or {}).get("name")
    if t == "date":
        return (pv.get("date") or {}).get("start")
    return None


def read_approvals():
    """slug -> decision (promoted|edited|rejected), last wins. slug == proposal filename."""
    out = {}
    if not os.path.exists(APPROVALS):
        return out
    for line in open(APPROVALS, encoding="utf-8"):
        parts = dict(p.split("=", 1) for p in line.strip().split("\t") if "=" in p)
        if parts.get("slug") and parts.get("decision"):
            out[parts["slug"]] = parts["decision"]
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only; no Notion writes")
    args = ap.parse_args()
    token = load_token()

    files = inbox_files()
    rows = all_rows(token)
    by_fn = {}
    for r in rows:
        fn = prop_text(r, "Filename")
        if fn:
            by_fn[fn] = r

    created, reflected, decision_map = [], [], read_approvals()

    # 1) CREATE rows for new proposal files
    for fn in files:
        if fn in by_fn:
            continue
        path = os.path.join(INBOX_DIR, fn)
        title, excerpt = title_and_excerpt(path)
        pdate = mtime_date(path)
        note = ""
        fpref = fn[:10]
        if fpref[:4].isdigit() and fpref != pdate:
            note = "Filename says %s but file mtime is %s." % (fpref, pdate)
        props = {
            "Proposal":      {"title": rt(title)},
            "Status":        {"select": {"name": "New"}},
            "Filename":      {"rich_text": rt(fn)},
            "Box Link":      {"url": BOX_LINK_BASE + fn},
            "Excerpt":       {"rich_text": rt(excerpt)},
            "Source":        {"select": {"name": source_for(fn)}},
            "Proposal Date": {"date": {"start": pdate}},
        }
        if note:
            props["Notes"] = {"rich_text": rt(note)}
        if args.dry_run:
            created.append(fn + "  (DRY)")
            continue
        api("POST", "/pages", token,
            {"parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
             "properties": props})
        created.append(fn)

    # 2) REFLECT Mac-side outcomes back into Notion (file gone + approvals.tsv decision)
    today = datetime.date.today().isoformat()
    for fn, r in by_fn.items():
        if fn in files:
            continue  # still pending, leave it
        status = prop_text(r, "Status")
        if status not in ("New", "Approved"):
            continue
        dec = decision_map.get(fn)
        if not dec:
            continue
        new_status = "Rejected" if dec == "rejected" else "Promoted"
        if args.dry_run:
            reflected.append("%s -> %s (DRY)" % (fn, new_status))
            continue
        api("PATCH", "/pages/%s" % r["id"], token,
            {"properties": {"Status": {"select": {"name": new_status}},
                            "Processed At": {"date": {"start": today}}}})
        reflected.append("%s -> %s" % (fn, new_status))

    print("agent-inbox-sync: %d proposal(s) on git, %d row(s) in Notion." % (len(files), len(rows)))
    print("  created: %s" % (", ".join(created) if created else "none (inbox clean)"))
    print("  reflected: %s" % (", ".join(reflected) if reflected else "none"))


if __name__ == "__main__":
    main()
