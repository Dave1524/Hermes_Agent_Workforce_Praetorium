#!/usr/bin/env python3
"""agent_inbox_notion_sync.py — deterministic box→Notion sync for the Agent Inbox DB.

Replaces the glm-5.2 LLM cron (agent-inbox-sync, jobs.json 98e6eb41f553) with a no-model
REST reconcile: an LLM was needlessly *executing* a fully-specified algorithm (and failing
on the exhausted OpenRouter budget). This is that algorithm, deterministic and free.

Direction: read-only on git, write-only on Notion (same contract as the old cron).
  1. CREATE: for every _inbox/agents/*.md proposal not yet in the DB (exact Filename match),
     create a row (Status=New; Proposal Date = file mtime; Source inferred; Excerpt + Box Link)
     and write the proposal markdown into the page body, so the proposal is readable in
     Notion itself rather than only behind the private-repo Box Link.
  1b. --backfill-bodies: the same body write for existing Status=New rows — the backlog
     still awaiting review. Decided rows are left alone; they have already been read.
  2. REFLECT: for DB rows whose proposal file is gone AND still New/Approved, read the
     box-safe approvals.tsv; if a promoted/rejected decision is recorded, set Status +
     Processed At so Notion mirrors what happened on the Mac. (Skipped if approvals.tsv absent.)

Token: NOTION_API_TOKEN from env or ~/.config/agent-workforce/secrets.env. Never the MCP
(it linkifies .md filenames and breaks exact-Filename dedup).
"""
import argparse, json, os, re, sys, glob, datetime, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import notion_markdown  # noqa: E402  — sibling module owns markdown -> Notion blocks

DATA_SOURCE_ID = "ecb52f8e-2125-416f-b08e-824a7416e561"
NOTION_VERSION = "2025-09-03"
API = "https://api.notion.com/v1"
INBOX_DIR = os.path.expanduser("~/agent-worktrees/inbox/_inbox/agents")
APPROVALS = os.path.join(INBOX_DIR, "_metrics", "approvals.tsv")
BOX_LINK_BASE = ("https://github.com/Dave1524/obsidian-ai-os-boxsafe/blob/"
                 "agents/inbox/_inbox/agents/")
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")
BRANCH = "agents/inbox"
BATCH = 100
SENTINEL_RE = re.compile(r"^— synced from (.+) @ (.+) —$")


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


def make_call(token):
    def call(method, path, payload=None):
        return api(method, path, token, payload)
    return call


def sentinel_text(filename):
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    return "— synced from %s @ %s —" % (filename, stamp)


def divider():
    return {"object": "block", "type": "divider", "divider": {}}


def provenance_blocks(filename, box_link):
    """Makes the page self-describing — the GitHub link 404s for a signed-out browser."""
    return [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": [
        {"type": "text", "text": {"content": "Source: "}},
        {"type": "text", "text": {"content": filename}, "annotations": {"code": True}},
        {"type": "text", "text": {"content": " on branch %s of obsidian-ai-os-boxsafe — "
                                             % BRANCH}},
        {"type": "text", "text": {"content": "view on GitHub", "link": {"url": box_link}}},
        {"type": "text", "text": {"content": " (private repo; the full text is below)."}},
    ]}}, divider()]


def body_blocks(filename, path, box_link):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError:
        text = ""
    sentinel = {"object": "block", "type": "paragraph",
                "paragraph": {"rich_text":
                              notion_markdown.plain_rich_text(sentinel_text(filename))}}
    return (provenance_blocks(filename, box_link)
            + notion_markdown.blocks_from_markdown(text)
            + [divider(), sentinel])


def batches(blocks):
    """A table's rows ride along inside it; charge them to the same 100-block budget."""
    out, current, weight = [], [], 0
    for b in blocks:
        cost = 1 + len((b.get("table") or {}).get("children", []))
        if current and weight + cost > BATCH:
            out.append(current)
            current, weight = [], 0
        current.append(b)
        weight += cost
    if current:
        out.append(current)
    return out


def child_blocks(call, page_id):
    out, cur = [], None
    while True:
        path = "/blocks/%s/children?page_size=100" % page_id
        if cur:
            path += "&start_cursor=" + cur
        d = call("GET", path)
        out += d.get("results", [])
        if not d.get("has_more"):
            return out
        cur = d["next_cursor"]


def block_plain(block):
    rich = (block.get(block.get("type")) or {}).get("rich_text", [])
    return "".join(s.get("plain_text") or s.get("text", {}).get("content", "") for s in rich)


def has_sentinel(children, filename):
    if not children:
        return False
    m = SENTINEL_RE.match(block_plain(children[-1]).strip())
    return bool(m) and m.group(1) == filename


def write_body(call, page_id, filename, path, box_link, dry_run=False):
    """Idempotent, crash-safe body write. Returns (written|repaired|skipped, blocks).

    The sentinel is the LAST block written, so it can only exist if every preceding
    batch landed — children without one are a partial write and get cleared, not
    appended to.
    """
    children = child_blocks(call, page_id)
    if has_sentinel(children, filename):
        return "skipped", 0
    blocks = body_blocks(filename, path, box_link)
    outcome = "repaired" if children else "written"
    if dry_run:
        return outcome, len(blocks)
    for child in children:
        call("DELETE", "/blocks/%s" % child["id"])
    for batch in batches(blocks):
        call("PATCH", "/blocks/%s/children" % page_id, {"children": batch})
    return outcome, len(blocks)


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
    """slug -> (decision, ts) for the most recent decision. slug == proposal filename.

    ts is the authoritative decision timestamp — the Mac-side promote pass (agent_inbox.py,
    outside this box's reach) sets Notion Status directly and does not always set
    Processed At, so this is also used to backfill that field (see main()).
    """
    out = {}
    if not os.path.exists(APPROVALS):
        return out
    for line in open(APPROVALS, encoding="utf-8"):
        parts = dict(p.split("=", 1) for p in line.strip().split("\t") if "=" in p)
        if parts.get("slug") and parts.get("decision"):
            out[parts["slug"]] = (parts["decision"], parts.get("ts"))
    return out


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="report only; no Notion writes")
    ap.add_argument("--backfill-bodies", action="store_true",
                     help="write the proposal markdown into the page body of every Status=New "
                          "row whose file is still on the box — the backlog Dave has yet to "
                          "review. Rows created before this existed have an EMPTY body, which "
                          "left the private-repo Box Link as the only copy — and that 404s for "
                          "a signed-out browser. A decided row (Approved/Promoted/Rejected) is "
                          "left alone: it has already been read. "
                          "Idempotent: a body already ending in the sentinel is left alone.")
    ap.add_argument("--count", action="store_true",
                     help="print PENDING_COUNT=N and OLDEST_PENDING_DATE=<date|none>, then exit. "
                          "Read-only (no CREATE/REFLECT, no writes even vs --dry-run) — for cheap, "
                          "frequent callers like inbox_backlog_alert.sh and praetorium-status.sh, "
                          "which used to raw-count *.md files on disk. That count included files "
                          "already decided in Notion but not yet cleared by the Mac-side promote "
                          "pass, so it overstated the real backlog (NUC-45 diagnosis, 2026-08-10).")
    args = ap.parse_args(argv)
    token = load_token()
    call = make_call(token)

    files = inbox_files()
    rows = all_rows(token)
    by_fn = {}
    for r in rows:
        fn = prop_text(r, "Filename")
        if fn:
            by_fn[fn] = r

    if args.count:
        pending_dates = []
        for fn in files:
            r = by_fn.get(fn)
            status = prop_text(r, "Status") if r else "New"
            if status == "New":
                pending_dates.append(mtime_date(os.path.join(INBOX_DIR, fn)))
        oldest = min(pending_dates) if pending_dates else None
        print("PENDING_COUNT=%d" % len(pending_dates))
        print("OLDEST_PENDING_DATE=%s" % (oldest or "none"))
        return

    created, reflected, decision_map = [], [], read_approvals()
    bodies, body_total = 0, 0

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
        box_link = BOX_LINK_BASE + fn
        if args.dry_run:
            created.append(fn + "  (DRY)")
            bodies += 1
            body_total += len(body_blocks(fn, path, box_link))
            continue
        page = api("POST", "/pages", token,
                   {"parent": {"type": "data_source_id", "data_source_id": DATA_SOURCE_ID},
                    "properties": props})
        created.append(fn)
        # Two calls, not inline children: a create carrying children is capped at 100
        # blocks and would silently truncate a long proposal.
        _, count = write_body(call, page["id"], fn, path, box_link)
        bodies += 1
        body_total += count

    # 1b) BACKFILL bodies for rows that predate the body sync, or whose write crashed
    if args.backfill_bodies:
        for fn in files:
            row = by_fn.get(fn)
            if not row or prop_text(row, "Status") != "New":
                continue
            outcome, count = write_body(call, row["id"], fn, os.path.join(INBOX_DIR, fn),
                                        BOX_LINK_BASE + fn, args.dry_run)
            if outcome != "skipped":
                bodies += 1
                body_total += count

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
        new_status = "Rejected" if dec[0] == "rejected" else "Promoted"
        if args.dry_run:
            reflected.append("%s -> %s (DRY)" % (fn, new_status))
            continue
        api("PATCH", "/pages/%s" % r["id"], token,
            {"properties": {"Status": {"select": {"name": new_status}},
                            "Processed At": {"date": {"start": today}}}})
        reflected.append("%s -> %s" % (fn, new_status))

    # 3) BACKFILL Processed At for rows the Mac-side promote pass already flipped to
    # Promoted/Rejected without stamping a timestamp — otherwise the lifecycle report
    # below silently drops them (NUC report bug, 2026-08-11: 13 of 24 Promoted rows from
    # the 10 Aug batch had no Processed At and landed in no bucket at all).
    backfilled, conflicts = [], []
    for fn, r in by_fn.items():
        status = prop_text(r, "Status")
        if status not in ("Promoted", "Rejected") or prop_text(r, "Processed At"):
            continue
        dec = decision_map.get(fn)
        if not dec or not dec[1]:
            continue
        dec_status = "Rejected" if dec[0] == "rejected" else "Promoted"
        if dec_status != status:
            # Notion status disagrees with the box's own decision record — don't guess
            # which is right, surface it instead (needs Dave to reconcile).
            conflicts.append("%s (Notion=%s, approvals.tsv=%s)" % (fn, status, dec[0]))
            continue
        proc_date = dec[1][:10]
        if args.dry_run:
            backfilled.append("%s -> %s (DRY)" % (fn, proc_date))
            continue
        api("PATCH", "/pages/%s" % r["id"], token,
            {"properties": {"Processed At": {"date": {"start": proc_date}}}})
        r["properties"]["Processed At"] = {"type": "date", "date": {"start": proc_date}}
        backfilled.append("%s -> %s" % (fn, proc_date))

    # --- lifecycle report (read-only over files/rows; no sync side effects) ---
    today_d = datetime.date.today()
    d7 = today_d - datetime.timedelta(days=7)
    d14 = today_d - datetime.timedelta(days=14)
    files_set = set(files)

    def parse_d(s):
        if not s:
            return None
        try:
            return datetime.date.fromisoformat(str(s)[:10])
        except ValueError:
            return None

    def fmt_d(d):
        return d.strftime("%a %d %b") if d else "?"

    def row_title(fn, r):
        path = os.path.join(INBOX_DIR, fn)
        if os.path.isfile(path):
            return title_and_excerpt(path)[0]
        t = prop_text(r, "Proposal") if r else None
        return t or fn

    def proposal_date(fn, r):
        path = os.path.join(INBOX_DIR, fn)
        if os.path.isfile(path):
            return parse_d(mtime_date(path))
        return parse_d(prop_text(r, "Proposal Date")) if r else None

    this_week, last_week_counts = [], {}
    pending_review, ready_promote = [], []

    seen = set(by_fn) | files_set
    for fn in sorted(seen):
        r = by_fn.get(fn)
        status = prop_text(r, "Status") if r else ("New" if fn in files_set else None)
        on_git = fn in files_set
        pdate = proposal_date(fn, r)
        proc = parse_d(prop_text(r, "Processed At")) if r else None
        title = row_title(fn, r)

        if status == "New" and on_git:
            pending_review.append((title, pdate))
            if pdate and pdate >= d7:
                this_week.append(("[new] → review in Notion", title, pdate))
        elif status == "Approved" and on_git and not proc:
            ready_promote.append((title, pdate))
            if pdate and pdate >= d7:
                this_week.append(("[approved] → promote needed", title, pdate))
        elif status in ("Promoted", "Rejected") and proc:
            tag = "[promoted]" if status == "Promoted" else "[rejected]"
            if proc >= d7:
                this_week.append((tag, title, proc))
            elif d14 <= proc < d7:
                last_week_counts[tag] = last_week_counts.get(tag, 0) + 1

    # --- headline: lifecycle summary instead of raw count ---
    promoted_this_week = sum(1 for tag, _, _ in this_week if tag == "[promoted]")
    rejected_this_week = sum(1 for tag, _, _ in this_week if tag == "[rejected]")
    new_this_week = len(pending_review)
    ready_count = len(ready_promote)
    parts = []
    if new_this_week:
        parts.append("%d pending review" % new_this_week)
    if ready_count:
        parts.append("%d ready to promote" % ready_count)
    if promoted_this_week:
        parts.append("%d promoted this week" % promoted_this_week)
    if rejected_this_week:
        parts.append("%d rejected this week" % rejected_this_week)
    if not parts:
        parts.append("all clear — no pending proposals")
    print("agent-inbox-sync: %s." % ", ".join(parts))
    if created:
        print("  created this run: %s" % ", ".join(created))
    if bodies:
        print("  bodies written this run: %d ({:,} blocks)%s".format(body_total)
              % (bodies, " (DRY)" if args.dry_run else ""))
    if reflected:
        print("  reflected this run: %s" % ", ".join(reflected))
    if backfilled:
        print("  backfilled Processed At this run: %s" % ", ".join(backfilled))
    if conflicts:
        print("  ! Notion/approvals.tsv status conflict, needs reconciliation: %s" % ", ".join(conflicts))
    if this_week:
        for tag, title, d in sorted(this_week, key=lambda x: x[2] or today_d, reverse=True):
            print("  %s  %s  (%s)" % (tag, title, fmt_d(d)))
    else:
        print("  (none)")

    print()
    print("LAST WEEK (7–14 days ago)")
    if last_week_counts:
        for tag in ("[promoted]", "[rejected]"):
            if tag in last_week_counts:
                print("  %s  %d" % (tag, last_week_counts[tag]))
    else:
        print("  (none)")

    print()
    print("ACTION NEEDED FROM YOU")
    print("  Pending review:")
    if pending_review:
        for title, d in sorted(pending_review, key=lambda x: x[1] or today_d, reverse=True):
            print("    • %s  (%s) — review in Notion" % (title, fmt_d(d)))
    else:
        print("    (none)")
    print("  Ready to promote:")
    if ready_promote:
        for title, d in sorted(ready_promote, key=lambda x: x[1] or today_d, reverse=True):
            print("    • %s  (%s) — promote from Mac" % (title, fmt_d(d)))
    else:
        print("    (none)")


if __name__ == "__main__":
    main()
