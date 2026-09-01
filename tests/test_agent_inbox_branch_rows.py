#!/usr/bin/env python3
"""
Offline behaviour test for the branch-row body mode of bin/agent_inbox_notion_sync.py.
Driven from tests/test_agent_inbox_branch_rows.sh so bin/verify.sh picks it up.

No network: the HTTP seam (the module-level api()) is replaced by FakeNotion, and the
canonical vault clone is a real temporary git repository. What is pinned here is the row
shape the inbox-file sync is structurally blind to — Filename naming an agents/<date>-<slug>
branch on the canonical repo, hand-registered by interactive sessions — plus the two
contracts specific to it: idempotency keys on the branch TIP (sentinel filename slot is
<branch>@<sha12>, so a moved tip re-renders), and git access is best-effort (an
unresolvable branch is reported and skipped; the inbox-file sync still runs).
"""
import contextlib
import datetime
import io
import importlib.util
import os
import pathlib
import re
import subprocess
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("agent_inbox_notion_sync",
                                               ROOT / "bin" / "agent_inbox_notion_sync.py")
sync = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(sync)
branch = sync.agent_inbox_branch_rows

failures = []


def check(desc, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", desc))
    if not cond:
        failures.append(desc)


class FakeNotion:
    """The slice of the Notion REST surface agent_inbox_notion_sync.py touches.

    Signature matches the module-level api(method, path, token, payload=None) it
    replaces, so main() needs no injection hook beyond patching that one name.
    """

    def __init__(self):
        self.pages = {}
        self.children = {}
        self.calls = []
        self._seq = 0

    def _id(self, prefix):
        self._seq += 1
        return "{}-{}".format(prefix, self._seq)

    def __call__(self, method, path, token, payload=None):
        self.calls.append((method, path, payload))
        head = path.split("?")[0].split("/")
        if method == "POST" and head[1] == "data_sources":
            return self._query(payload)
        if method == "POST" and path == "/pages":
            return self._create(payload)
        if method == "PATCH" and head[1] == "pages":
            self.pages[head[2]]["properties"].update(payload["properties"])
            return {"id": head[2]}
        if method == "GET" and head[1] == "blocks":
            return {"results": self.children.get(head[2], []), "has_more": False}
        if method == "PATCH" and head[1] == "blocks":
            kids = self.children.setdefault(head[2], [])
            kids.extend(dict(b, id=self._id("blk")) for b in payload["children"])
            return {"results": kids}
        if method == "DELETE" and head[1] == "blocks":
            for pid, blocks in self.children.items():
                self.children[pid] = [b for b in blocks if b.get("id") != head[2]]
            return {}
        raise AssertionError("unexpected call: {} {}".format(method, path))

    def _create(self, payload):
        pid = self._id("page")
        self.pages[pid] = {"id": pid, "properties": payload["properties"]}
        return {"id": pid}

    def _query(self, payload):
        rows = [{"id": p["id"], "properties": self._readback(p["properties"])}
                for p in self.pages.values()]
        return {"results": rows, "has_more": False, "next_cursor": None}

    @staticmethod
    def _readback(props):
        """Notion echoes a WRITTEN property back with a 'type' discriminator and a
        flattened 'plain_text' on every span. prop_text() reads both, so a fake that
        replays the write shape verbatim silently reports every Filename as empty."""
        out = {}
        for name, value in props.items():
            kind = next(k for k in value if k != "type")
            if kind in ("title", "rich_text"):
                out[name] = {"type": kind, kind: [dict(s, plain_text=s["text"]["content"])
                                                  for s in value[kind]]}
            else:
                out[name] = dict(value, type=kind)
        return out

    # -- helpers the assertions read --
    def creates(self):
        return [c for c in self.calls if c[0] == "POST" and c[1] == "/pages"]

    def appends(self):
        return [c for c in self.calls if c[0] == "PATCH" and c[1].startswith("/blocks/")]

    def deletes(self):
        return [c for c in self.calls if c[0] == "DELETE"]

    def writes(self):
        return [c for c in self.calls
                if c[0] in ("PATCH", "DELETE") or (c[0] == "POST" and c[1] == "/pages")]

    def block_reads(self):
        return [c for c in self.calls if "/blocks/" in c[1]]

    def page_patches(self):
        return [c for c in self.calls if c[0] == "PATCH" and c[1].startswith("/pages/")]

    def body(self, page_id):
        return self.children.get(page_id, [])

    def text_of(self, block):
        rich = block.get(block["type"], {}).get("rich_text", [])
        return "".join(s["text"]["content"] for s in rich)

    def body_text(self, page_id):
        return [self.text_of(b) for b in self.body(page_id)]


TODAY = datetime.date.today().isoformat()
BRANCH_NAME = "agents/2026-08-21-ugc-creator-brief"
DOC_PATH = "03_projects/incubation/ugc_creator_business.md"
ROW_TITLE = "Incubation — scoped research brief for the UGC creator business model"
BOX_LINK = ("https://github.com/Dave1524/Obsidian_AI_Operating_System/compare/main..."
            + BRANCH_NAME)
DOC_MD = (
    "# UGC creator business model\n"
    "\n"
    "Scoped **research brief** for the incubation track.\n"
    "\n"
    "## Questions\n"
    "- creator sourcing funnel\n"
    "- platform take-rate benchmarks\n"
)
FILENAME = TODAY + "_standing-research.md"
PROPOSAL = "# Standing research — %s\n\nFirst substantive line.\n" % TODAY

GIT_ENV = dict(os.environ, GIT_AUTHOR_NAME="test", GIT_AUTHOR_EMAIL="t@t",
               GIT_COMMITTER_NAME="test", GIT_COMMITTER_EMAIL="t@t",
               GIT_CONFIG_NOSYSTEM="1", GIT_TERMINAL_PROMPT="0")


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], check=True,
                          capture_output=True, text=True, env=GIT_ENV).stdout


def sync_origin_ref(repo):
    git(repo, "update-ref", "refs/remotes/origin/" + BRANCH_NAME,
        "refs/heads/" + BRANCH_NAME)


def tip12(repo):
    return git(repo, "rev-parse", "origin/" + BRANCH_NAME).strip()[:12]


def make_canonical(parent):
    """main + one agents/<date>-<slug> branch adding a markdown doc, with origin/* refs
    (update-ref stands in for a fetch — the fixture has no reachable remote, which also
    exercises the best-effort fetch path on every run)."""
    repo = pathlib.Path(parent) / "canonical"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    (repo / "README.md").write_text("# Canonical vault fixture\n", encoding="utf-8")
    git(repo, "add", "README.md")
    git(repo, "commit", "-qm", "root")
    git(repo, "checkout", "-qb", BRANCH_NAME)
    doc = repo / DOC_PATH
    doc.parent.mkdir(parents=True)
    doc.write_text(DOC_MD, encoding="utf-8")
    git(repo, "add", DOC_PATH)
    git(repo, "commit", "-qm", "add doc")
    git(repo, "checkout", "-q", "main")
    git(repo, "update-ref", "refs/remotes/origin/main", "refs/heads/main")
    sync_origin_ref(repo)
    return repo


@contextlib.contextmanager
def sandbox(repo, files=None):
    tmp = tempfile.TemporaryDirectory()
    inbox = pathlib.Path(tmp.name) / "_inbox" / "agents"
    inbox.mkdir(parents=True)
    for name, text in (files or {}).items():
        (inbox / name).write_text(text, encoding="utf-8")
    old = (sync.INBOX_DIR, sync.APPROVALS, sync.api, branch.CANONICAL_REPO)
    sync.INBOX_DIR = str(inbox)
    sync.APPROVALS = str(inbox / "_metrics" / "approvals.tsv")
    fake = FakeNotion()
    sync.api = fake
    branch.CANONICAL_REPO = str(repo)
    os.environ["NOTION_API_TOKEN"] = "test-token"
    try:
        yield fake
    finally:
        sync.INBOX_DIR, sync.APPROVALS, sync.api, branch.CANONICAL_REPO = old
        tmp.cleanup()


def seed_branch_row(api, name, status="New", box_link=None, title=ROW_TITLE,
                    pdate=TODAY):
    pid = api._id("page")
    props = {
        "Proposal":      {"title": [{"type": "text", "text": {"content": title}}]},
        "Status":        {"select": {"name": status}},
        "Filename":      {"rich_text": [{"type": "text", "text": {"content": name}}]},
        "Excerpt":       {"rich_text": []},
        "Source":        {"select": {"name": "other"}},
        "Proposal Date": {"date": {"start": pdate}},
    }
    if box_link:
        props["Box Link"] = {"url": box_link}
    api.pages[pid] = {"id": pid, "properties": props}
    return pid


def run(argv):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        sync.main(argv)
    return buf.getvalue()


REPO_TMP = tempfile.TemporaryDirectory()
REPO = make_canonical(REPO_TMP.name)

print("--- (a) a New branch row gets a rendered body keyed to the branch tip ---")
with sandbox(REPO) as api:
    pid = seed_branch_row(api, BRANCH_NAME, box_link=BOX_LINK)
    out = run([])
    body = api.body(pid)
    check("the page body is NOT empty", len(body) > 0)
    check("no row was created for it (registration stays a human act)",
          api.creates() == [])
    check("the row's properties were never written", api.page_patches() == [])

    check("the body opens with a provenance paragraph naming the branch",
          body[0]["type"] == "paragraph" and BRANCH_NAME in api.text_of(body[0]))
    check("the provenance paragraph carries the row's Box Link as the compare link",
          any((s["text"].get("link") or {}).get("url") == BOX_LINK
              for s in body[0]["paragraph"]["rich_text"]))
    check("the provenance header is closed off with a divider",
          body[1]["type"] == "divider")

    check("a 'Changes in this proposal' heading is present",
          any(b["type"] == "heading_2"
              and api.text_of(b) == "Changes in this proposal" for b in body))
    check("a diff-stat bullet names the added doc",
          any(b["type"] == "bulleted_list_item"
              and "ugc_creator_business.md" in api.text_of(b) for b in body))
    check("the added doc gets an H1 carrying its path",
          any(b["type"] == "heading_1" and api.text_of(b) == DOC_PATH for b in body))
    check("the doc content is rendered as native blocks",
          any(b["type"] == "bulleted_list_item"
              and "creator sourcing funnel" in api.text_of(b) for b in body))
    check("no raw ** survives into the rendered text",
          not any("**" in t for t in api.body_text(pid)))

    sha = tip12(REPO)
    m = sync.SENTINEL_RE.match(api.text_of(body[-1]))
    check("the last block is a sentinel whose filename slot is <branch>@<sha12>",
          m is not None and m.group(1) == BRANCH_NAME + "@" + sha)
    check("the sentinel carries the current render version",
          m is not None and m.group(3) == str(sync.notion_markdown.FORMAT_VERSION))
    check("the sentinel is preceded by a divider", body[-2]["type"] == "divider")

    check("branch bodies join the run counters",
          re.search(r"bodies written this run: 1 \(\d+ blocks\)", out) is not None)
    check("one report line names the branch and the outcome",
          re.search(r"branch %s: written" % re.escape(BRANCH_NAME), out) is not None)
    check("the headline counts the branch row as pending review",
          "1 pending review" in out)
    check("the row title shows under Pending review", ROW_TITLE in out)
    check("the row appears in this week's [new] items", "[new]" in out)

    print("--- (b) a second pass with an unmoved tip writes nothing ---")
    before = list(api.body(pid))
    api.calls = []
    out = run([])
    check("no blocks were appended", api.appends() == [])
    check("no blocks were deleted", api.deletes() == [])
    check("the body is byte-identical to the first write", api.body(pid) == before)
    check("the run summary reports no body writes",
          "bodies written this run" not in out)

    print("--- (c) a moved tip re-renders the body ---")
    git(REPO, "checkout", "-q", BRANCH_NAME)
    (REPO / DOC_PATH).write_text(DOC_MD + "\nAppended after review.\n", encoding="utf-8")
    git(REPO, "commit", "-aqm", "revise doc")
    git(REPO, "checkout", "-q", "main")
    sync_origin_ref(REPO)
    stale = list(api.body(pid))
    api.calls = []
    out = run([])
    check("every stale block was deleted", len(api.deletes()) == len(stale))
    new_sha = tip12(REPO)
    check("the tip really moved", new_sha != sha)
    m = sync.SENTINEL_RE.match(api.text_of(api.body(pid)[-1]))
    check("the new sentinel carries the new tip sha",
          m is not None and m.group(1) == BRANCH_NAME + "@" + new_sha)
    check("the new content is in the body",
          any("Appended after review." in t for t in api.body_text(pid)))
    check("the report names the outcome as repaired",
          re.search(r"branch %s: repaired" % re.escape(BRANCH_NAME), out) is not None)

    print("--- (d) a partial body (no sentinel) is cleared and rewritten ---")
    truncated = api.body(pid)[:3]
    api.children[pid] = truncated
    api.calls = []
    out = run([])
    check("every stale block was deleted", len(api.deletes()) == len(truncated))
    check("the body was rewritten to completion",
          sync.SENTINEL_RE.match(api.text_of(api.body(pid)[-1])) is not None)
    check("the repair is reported",
          re.search(r"branch %s: repaired" % re.escape(BRANCH_NAME), out) is not None)

print("--- (e) a decided branch row is left entirely alone ---")
with sandbox(REPO) as api:
    seed_branch_row(api, BRANCH_NAME, status="Approved")
    out = run([])
    check("no block endpoint was touched at all", api.block_reads() == [])
    check("nothing was written", api.writes() == [])

print("--- (f) an unresolvable branch is reported and skipped, not fatal ---")
with sandbox(REPO, {FILENAME: PROPOSAL}) as api:
    seed_branch_row(api, "agents/2026-08-30-branch-that-does-not-exist")
    out = run([])
    check("the run completes and flags the branch with a ! line",
          "! branch agents/2026-08-30-branch-that-does-not-exist" in out)
    check("the inbox-file sync still executed", len(api.creates()) == 1)
    inbox_pid = [p for p in api.pages if api.children.get(p)][0]
    check("the inbox file still got its body",
          sync.SENTINEL_RE.match(api.text_of(api.body(inbox_pid)[-1])) is not None)

print("--- (g) --dry-run renders the report but writes nothing ---")
with sandbox(REPO) as api:
    seed_branch_row(api, BRANCH_NAME)
    out = run(["--dry-run"])
    check("nothing was created, appended or deleted", api.writes() == [])
    check("the dry run still reports the branch body it would write",
          re.search(r"branch %s: written .*\(DRY\)" % re.escape(BRANCH_NAME), out)
          is not None)
    check("the dry-run body count is flagged DRY",
          re.search(r"bodies written this run: 1 \(\d+ blocks\) \(DRY\)", out) is not None)

print("--- (h) --count stays read-only and runs no git subprocess ---")
with sandbox("/nonexistent/canonical-clone", {FILENAME: PROPOSAL}) as api:
    seed_branch_row(api, BRANCH_NAME)

    def _boom(*args, **kwargs):
        raise AssertionError("git subprocess during --count")
    old_git = branch._git
    branch._git = _boom
    try:
        out = run(["--count"])
    finally:
        branch._git = old_git
    check("--count writes nothing", api.writes() == [])
    check("--count stdout is the two lines its callers parse",
          out == "PENDING_COUNT=1\nOLDEST_PENDING_DATE=%s\n" % TODAY)

print("--- composition: fallback compare link and the fully-merged branch ---")
old_repo = branch.CANONICAL_REPO
branch.CANONICAL_REPO = str(REPO)
try:
    blocks = branch.body_blocks(BRANCH_NAME, "origin/" + BRANCH_NAME, None)
    spans = blocks[0]["paragraph"]["rich_text"]
    check("without a Box Link the provenance falls back to the compare URL",
          any((s["text"].get("link") or {}).get("url")
              == branch.COMPARE_BASE + BRANCH_NAME for s in spans))
    merged = branch.body_blocks(BRANCH_NAME, "origin/main", None)
    texts = ["".join(s["text"]["content"]
                     for s in b.get(b["type"], {}).get("rich_text", []))
             for b in merged]
    check("a fully-merged branch still self-describes instead of being skipped",
          any("merged" in t for t in texts))
finally:
    branch.CANONICAL_REPO = old_repo

print("--- the branch-name predicate is anchored ---")
check("a real branch row qualifies", branch.is_branch_row(BRANCH_NAME))
check("an inbox filename does not", not branch.is_branch_row(FILENAME))
check("a nested path does not",
      not branch.is_branch_row("agents/2026-08-21-x/evil"))
check("empty does not", not branch.is_branch_row(""))

REPO_TMP.cleanup()
raise SystemExit(1 if failures else 0)
