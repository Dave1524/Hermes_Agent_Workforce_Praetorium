#!/usr/bin/env python3
"""agent_inbox_apply.py — act on Dave's Notion decisions, WITHIN the box-safe membrane.

Closes the loop Notion -> box, respecting the one hard boundary (vault CLAUDE.md): the box
may read/write Notion freely (inside the bubble) but must NOT write the canonical vault —
canonical promotion is a Mac-side judgment write (quality + conflict-safety, not secrecy).

  REJECTED  -> fully automated here. Replicates agent_inbox.py's reject bookkeeping directly
               on the ~/agent-worktrees/inbox WORKTREE (agent_inbox.py itself only accepts a
               normal checkout, not a worktree): archive under .git/agent_inbox_archive/,
               git rm from _inbox/agents/, append the byte-identical approvals.tsv line
               (ts=..\tslug=..\tdecision=rejected — the scorecard greps these), commit, then
               push agents/inbox once with the boxsafe deploy key, then stamp the Notion row.
  APPROVED  -> NOT actioned (cannot write canonical). Surfaced as a Mac hand-off; after the
               Mac promote, the next sync flips Status -> Promoted in Notion automatically.

Membrane guards, mirroring agent_inbox.py: refuse unless HEAD is agents/inbox; only touch
_inbox/agents/; refuse if anything outside _inbox/agents/ is staged. Default is --dry-run.
Rejects are reversible (archived under .git/ + every removal is a git commit).
"""
import argparse, json, os, sys, subprocess, posixpath, urllib.request, urllib.error
from datetime import datetime, timezone, date

DATA_SOURCE_ID = "ecb52f8e-2125-416f-b08e-824a7416e561"
NOTION_VERSION = "2025-09-03"
API = "https://api.notion.com/v1"
INBOX_REPO = os.path.expanduser("~/agent-worktrees/inbox")
INBOX_BRANCH = "agents/inbox"
INBOX_DIR = "_inbox/agents"
APPROVALS_FILE = posixpath.join(INBOX_DIR, "_metrics", "approvals.tsv")
BOXSAFE_KEY = os.path.expanduser("~/.config/agent-workforce/keys/boxsafe_deploy")
BOXSAFE_URL = "git@github.com:Dave1524/obsidian-ai-os-boxsafe.git"
SECRETS = os.path.expanduser("~/.config/agent-workforce/secrets.env")
GIT_SSH = ("ssh -i %s -o IdentitiesOnly=yes -o BatchMode=yes "
           "-o StrictHostKeyChecking=accept-new" % BOXSAFE_KEY)


class MembraneViolation(Exception):
    pass


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
        sys.exit("Notion API %s on %s %s: %s" % (e.code, method, path, e.read().decode()[:300]))


def git(*args, env=None):
    r = subprocess.run(["git", "-C", INBOX_REPO] + list(args),
                       capture_output=True, text=True, env=env)
    if r.returncode != 0:
        raise RuntimeError("git %s failed: %s" % (" ".join(args), (r.stderr or r.stdout).strip()))
    return r.stdout


def ptext(row, name):
    pv = row["properties"].get(name, {})
    t = pv.get("type")
    if t == "rich_text":
        return "".join(x.get("plain_text", "") for x in pv["rich_text"])
    if t in ("select", "status"):
        return (pv.get(t) or {}).get("name")
    if t == "date":
        return (pv.get("date") or {}).get("start")
    return None


def query_status(token, status):
    rows, cur = [], None
    while True:
        payload = {"page_size": 100,
                   "filter": {"property": "Status", "select": {"equals": status}}}
        if cur:
            payload["start_cursor"] = cur
        d = api("POST", "/data_sources/%s/query" % DATA_SOURCE_ID, token, payload)
        rows += d.get("results", [])
        if not d.get("has_more"):
            break
        cur = d["next_cursor"]
    return rows


def assert_on_inbox_branch():
    br = git("rev-parse", "--abbrev-ref", "HEAD").strip()
    if br != INBOX_BRANCH:
        raise MembraneViolation("inbox worktree on '%s', not '%s' — refusing to act." % (br, INBOX_BRANCH))


def resolve_target(name):
    if "/" in name or name in ("", ".", "..") or not name.endswith(".md"):
        raise MembraneViolation("'%s' is not a bare inbox .md filename — refused" % name)
    rel = posixpath.normpath(posixpath.join(INBOX_DIR, name))
    if rel != INBOX_DIR and not rel.startswith(INBOX_DIR + "/"):
        raise MembraneViolation("'%s' resolves outside %s/ — refused" % (name, INBOX_DIR))
    return rel


def _git_common_dir():
    """Real shared git dir — the worktree's own .git is a file (gitdir pointer), not a dir."""
    out = git("rev-parse", "--git-common-dir").strip()
    if not os.path.isabs(out):
        out = os.path.abspath(os.path.join(INBOX_REPO, out))
    return out


def reject_one(name, reason):
    """Archive + git rm + approvals.tsv append + commit — byte-identical to agent_inbox.py."""
    rel = resolve_target(name)
    src = os.path.join(INBOX_REPO, rel)
    if not os.path.isfile(src):
        raise RuntimeError("no proposal '%s' in %s/ on the checked-out branch" % (name, INBOX_DIR))
    content = open(src, encoding="utf-8").read()
    # archive under the real git dir (never in the working tree → never publishable)
    arch_dir = os.path.join(_git_common_dir(), "agent_inbox_archive", "rejected")
    os.makedirs(arch_dir, exist_ok=True)
    header = "<!-- agent_inbox: rejected %s | reason: %s -->\n\n" % (name, reason)
    open(os.path.join(arch_dir, name), "w", encoding="utf-8").write(header + content)
    # remove + record outcome
    git("rm", "--quiet", rel)
    dest = os.path.join(INBOX_REPO, *APPROVALS_FILE.split("/"))
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with open(dest, "a", encoding="utf-8") as fh:
        fh.write("ts=%s\tslug=%s\tdecision=rejected\n" % (ts, name))
    git("add", APPROVALS_FILE)
    # membrane: nothing outside _inbox/agents/ may be staged
    staged = [p for p in git("diff", "--cached", "--name-only").split("\n") if p]
    outside = [p for p in staged if not p.startswith(INBOX_DIR + "/")]
    if outside:
        raise MembraneViolation("staged outside %s/: %s — refused" % (INBOX_DIR, ", ".join(outside)))
    git("commit", "--quiet", "-m", "inbox: reject %s — %s" % (name, reason))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="execute (default is dry-run)")
    args = ap.parse_args()
    do = args.apply
    token = load_token()
    if not os.path.isdir(INBOX_REPO):
        sys.exit("ERROR: inbox worktree %s not found" % INBOX_REPO)
    assert_on_inbox_branch()

    rejected = [r for r in query_status(token, "Rejected") if not ptext(r, "Processed At")]
    approved = [r for r in query_status(token, "Approved") if not ptext(r, "Processed At")]
    print("=== agent-inbox-apply (%s) ===" % ("APPLY" if do else "DRY-RUN"))
    print("Rejected to action: %d   Approved awaiting Mac: %d" % (len(rejected), len(approved)))

    did = []
    for r in rejected:
        fn = ptext(r, "Filename")
        if not fn:
            print("  ! row %s has no Filename — skipped" % r["id"]); continue
        print("  REJECT %s" % fn)
        if not do:
            continue
        try:
            reject_one(fn, "Rejected in Notion %s" % date.today().isoformat())
            did.append((r, fn))
        except Exception as e:
            print("    ! reject failed: %s" % e)

    if do and did:
        env = dict(os.environ, GIT_SSH_COMMAND=GIT_SSH)
        try:
            git("push", BOXSAFE_URL, "%s:%s" % (INBOX_BRANCH, INBOX_BRANCH), env=env)
            pushed = True
        except Exception as e:
            print("  ! push failed (rejects are committed locally): %s" % e); pushed = False
        sha = git("rev-parse", "--short", "HEAD").strip()
        today = date.today().isoformat()
        for r, fn in did:
            note = "Rejected via Notion %s; removed from agents/inbox @ %s (archived)%s." % (
                today, sha, "" if pushed else " [local only — push pending]")
            api("PATCH", "/pages/%s" % r["id"], token,
                {"properties": {"Processed At": {"date": {"start": today}},
                                "Notes": {"rich_text": [{"type": "text", "text": {"content": note[:1900]}}]}}})
            print("    done: %s (Notion stamped)" % fn)

    if approved:
        print("\n  APPROVED — do the canonical write on the Mac, then run there:")
        for r in approved:
            print("    (canonical write) then:  python3 00_system/tools/agent_inbox.py promote %s"
                  % ptext(r, "Filename"))
        print("  (the next sync flips these to Promoted in Notion automatically)")

    if not do:
        print("\n(dry-run — nothing changed. re-run with --apply to action rejects.)")


if __name__ == "__main__":
    main()
