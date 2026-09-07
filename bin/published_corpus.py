#!/usr/bin/env python3
"""published_corpus.py — the one owner of "what is already live on vantagepointconsulting.nl".

Why this exists: on 2026-07-27 a queued brief (Q-2026-07-09-1) asked for a Dutch article
titled "Waarom lopen WMS-implementaties uit?" — a title the site had already published on
2026-07-08. No box content profile could see the live site: augustus is restricted to qmd +
notion_rest.py and explicitly forbidden web search, and claudius treats web research as
optional. The duplicate-check rule already existed in the vault's blog-engine skill, but it
is gated on reading webapp/lib/blog.ts and no box profile ever invoked it. This helper puts
that file one command away.

The corpus is read from the site repo's ORIGIN/MAIN, never the working tree: the box's
checkout sat on a feature branch (feat/ab-hero-cta-flag), eight commits behind, missing the
netcongestie article that was already live. Reading the working tree would answer "no
collision" for an article that exists — the exact failure this helper is meant to end.

ACQUISITION IS SPLIT FROM INTERROGATION, because one reader cannot acquire. augustus is
the only agent on the codex-acp harness and his bwrap namespace mounts a tmpfs over
~/.ssh; the site remote is `git@github-website:`, an ssh-config alias, so with no ssh
config the hostname does not resolve and his fetch fails every single time. From
2026-08-14 to 2026-09-06 he reported the corpus unreachable nine nights running while
the host, seconds later, fetched fine. The corpus is public data, so the fix is a
transport split like buzz-notion-broker.py — the host runs `snapshot`, the sandbox reads
the file — never a wider namespace, which would hand a credential to the agent's own
shell to solve a problem that needs no credential at all.

Commands:
  list                 Published corpus, one line per locale. What the profiles inject.
  check "<title>"      Rank the corpus by lexical overlap with a candidate title.
                       Exit 2 when overlap is high enough to call a collision.
  snapshot             Host-side capture to VP_CORPUS_SNAPSHOT, for readers that cannot
                       fetch. Refuses unless the fetch it just ran succeeded.

Lexical overlap catches TITLE REUSE, which is what actually went wrong. It does not catch an
adjacent angle under a different title — read the `list` output and judge that yourself.
"""
import argparse
import calendar
import json
import os
import re
import subprocess
import sys
import time
import unicodedata

SITE_REPO = os.path.expanduser(os.environ.get("VP_SITE_REPO", "~/dev/Vantage_Consulting_Website"))
BLOG_PATH = os.environ.get("VP_BLOG_PATH", "webapp/lib/blog.ts")
BLOG_REF = os.environ.get("VP_BLOG_REF", "origin/main")
MAX_LAG_HOURS = float(os.environ.get("VP_CORPUS_MAX_LAG_HOURS", "72"))
FETCH_TIMEOUT = int(os.environ.get("VP_CORPUS_FETCH_TIMEOUT", "90"))
COLLISION_THRESHOLD = float(os.environ.get("VP_CORPUS_COLLISION_THRESHOLD", "0.45"))
SNAPSHOT_PATH = os.path.expanduser(
    os.environ.get("VP_CORPUS_SNAPSHOT", "~/agent-workforce/var/published_corpus.json"))
SNAPSHOT_MAX_AGE_HOURS = float(os.environ.get("VP_CORPUS_SNAPSHOT_MAX_AGE_HOURS", "24"))
SNAPSHOT_STAMP = "%Y-%m-%dT%H:%M:%SZ"

STOPWORDS = {
    "de", "het", "een", "en", "van", "voor", "met", "bij", "aan", "op", "in", "te", "dat",
    "die", "der", "des", "om", "als", "naar", "over", "wat", "wie", "waarom", "wanneer",
    "hoe", "kies", "je", "of", "niet", "wel", "is", "zijn", "worden", "wordt", "kan",
    "the", "a", "an", "and", "of", "for", "with", "to", "in", "on", "at", "why", "when",
    "how", "what", "do", "does", "your", "you", "or", "is", "are", "be",
}


def _git(*args, check=True):
    return subprocess.run(["git", "-C", SITE_REPO, *args], capture_output=True,
                          text=True, check=check)


def _fetch():
    """Refresh origin/main. Offline is soft — we fall back to the last known ref."""
    try:
        subprocess.run(["git", "-C", SITE_REPO, "fetch", "origin", "main", "-q"],
                       capture_output=True, timeout=FETCH_TIMEOUT, check=True)
        return True
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return False


def _ref_age_hours():
    epoch = int(_git("log", "-1", "--format=%ct", BLOG_REF).stdout.strip())
    return (time.time() - epoch) / 3600.0


def _read_blog_ts():
    return _git("show", "{}:{}".format(BLOG_REF, BLOG_PATH)).stdout


def _require_repo():
    if not os.path.isdir(SITE_REPO):
        sys.exit("published_corpus: site repo not found at {} (set VP_SITE_REPO)".format(SITE_REPO))


def _ref_corpus():
    """(articles, tip age) from the on-disk ref. The only path that needs git to work."""
    try:
        return parse_articles(_read_blog_ts()), _ref_age_hours()
    except subprocess.CalledProcessError as e:
        sys.exit("published_corpus: cannot read {}:{} — {}".format(
            BLOG_REF, BLOG_PATH, (e.stderr or "").strip()[:200]))


def _snapshot_age_hours(payload):
    try:
        captured = calendar.timegm(time.strptime(payload["captured_at"], SNAPSHOT_STAMP))
    except (KeyError, TypeError, ValueError):
        return None
    return (time.time() - captured) / 3600.0


def _read_snapshot():
    """(payload, age, None) when the host snapshot is usable, (None, None, why) otherwise."""
    try:
        with open(SNAPSHOT_PATH) as fh:
            payload = json.load(fh)
    except (OSError, ValueError):
        return None, None, "no host snapshot at {}".format(SNAPSHOT_PATH)
    age = _snapshot_age_hours(payload)
    if age is None or not isinstance(payload.get("articles"), list):
        return None, None, "the host snapshot at {} is unusable (no captured_at or no articles)".format(
            SNAPSHOT_PATH)
    if age > SNAPSHOT_MAX_AGE_HOURS:
        return None, None, "the host snapshot at {} is stale ({:.1f}h old, max {:.0f}h)".format(
            SNAPSHOT_PATH, age, SNAPSHOT_MAX_AGE_HOURS)
    return payload, age, None


def _snapshot_freshness(payload, age):
    """The host's reading carried forward — a tip does not stop ageing inside a file."""
    at_capture = (payload.get("freshness") or {}).get("ref_age_hours") or 0.0
    return {"fetched": False, "source": "snapshot",
            "ref_age_hours": round(at_capture + age, 1),
            "captured_at": payload["captured_at"],
            "snapshot_age_hours": round(age, 1)}


def load_corpus():
    """Return (articles, freshness): live fetch, else host snapshot, else a ref still
    inside the lag window. Refuses rather than answer from anything older than that, and
    every path names itself in `source` — a fallback nobody can see is a silent one."""
    _require_repo()
    if _fetch():
        articles, age = _ref_corpus()
        return articles, {"fetched": True, "source": "origin", "ref_age_hours": round(age, 1)}
    payload, snapshot_age, no_snapshot = _read_snapshot()
    if payload is not None:
        return payload["articles"], _snapshot_freshness(payload, snapshot_age)
    articles, age = _ref_corpus()
    if age > MAX_LAG_HOURS:
        sys.exit("published_corpus: REFUSING — origin unreachable, {}, and {} is {:.0f}h old "
                 "(max {:.0f}h). A stale corpus answers 'no collision' for live articles."
                 .format(no_snapshot, BLOG_REF, age, MAX_LAG_HOURS))
    return articles, {"fetched": False, "source": "local-ref", "ref_age_hours": round(age, 1)}


def write_snapshot(articles, fresh):
    """Atomic: a reader in another namespace never opens a half-written corpus."""
    payload = {"captured_at": time.strftime(SNAPSHOT_STAMP, time.gmtime()),
               "freshness": fresh, "articles": articles}
    os.makedirs(os.path.dirname(SNAPSHOT_PATH) or ".", exist_ok=True)
    tmp = "{}.{}.tmp".format(SNAPSHOT_PATH, os.getpid())
    with open(tmp, "w") as fh:
        json.dump(payload, fh, indent=2)
    os.replace(tmp, SNAPSHOT_PATH)
    return payload


ARRAY_START = re.compile(r"export\s+const\s+blogArticles")
ID_RE = re.compile(r"^\s+id:\s*'([^']+)'")
PUBLISHED_RE = re.compile(r"^\s+publishedAt:\s*'([^']+)'")
UPDATED_RE = re.compile(r"^\s+updatedAt:\s*'([^']+)'")
LOCALE_RE = re.compile(r"^\s+(nl|en):\s*\{")
SLUG_RE = re.compile(r"^\s+slug:\s*'([^']+)'")
TITLE_RE = re.compile(r"^\s+title:\s*'(.*)',?\s*$")


def _set_locale_field(article, locale, field, value):
    if locale and not article["translations"].setdefault(locale, {}).get(field):
        article["translations"][locale][field] = value


def parse_articles(source):
    """Walk the typed blogArticles array. Shape is fixed by the blog_article_contract."""
    articles, article, locale, in_array = [], None, None, False
    for line in source.splitlines():
        if not in_array:
            in_array = bool(ARRAY_START.search(line))
            continue
        if line.rstrip() == "];":
            break
        m = ID_RE.match(line)
        if m:
            article = {"id": m.group(1), "publishedAt": None, "updatedAt": None,
                       "translations": {}}
            articles.append(article)
            locale = None
            continue
        if article is None:
            continue
        locale = _advance(article, line, locale)
    return articles


def _advance(article, line, locale):
    m = LOCALE_RE.match(line)
    if m:
        return m.group(1)
    for regex, key in ((PUBLISHED_RE, "publishedAt"), (UPDATED_RE, "updatedAt")):
        m = regex.match(line)
        if m and article[key] is None:
            article[key] = m.group(1)
            return locale
    for regex, key in ((SLUG_RE, "slug"), (TITLE_RE, "title")):
        m = regex.match(line)
        if m:
            _set_locale_field(article, locale, key, m.group(1).replace("\\'", "'"))
            return locale
    return locale


def _normalize(text):
    folded = unicodedata.normalize("NFKD", text.lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def tokens(text):
    words = re.split(r"[^a-z0-9]+", _normalize(text))
    return {w for w in words if len(w) > 2 and w not in STOPWORDS}


def similarity(a, b):
    ta, tb = tokens(a), tokens(b)
    if not ta or not tb:
        return 0.0
    if ta <= tb or tb <= ta:
        return 1.0
    return len(ta & tb) / len(ta | tb)


def entries(articles):
    """Flatten to one comparable record per published locale."""
    out = []
    for a in articles:
        for locale, t in sorted(a["translations"].items()):
            out.append({"id": a["id"], "locale": locale, "slug": t.get("slug", ""),
                        "title": t.get("title", ""), "publishedAt": a["publishedAt"],
                        "updatedAt": a["updatedAt"]})
    return out


def rank(candidate, rows):
    scored = [dict(r, score=round(max(similarity(candidate, r["title"]),
                                      similarity(candidate, r["slug"].replace("-", " "))), 3))
              for r in rows]
    return sorted(scored, key=lambda r: -r["score"])


def _provenance(fresh):
    """Which of the three paths answered. The reader acts on this, so it is never omitted."""
    source = fresh.get("source", "local-ref")
    if source == "origin":
        return "source=origin, fetched"
    if source == "snapshot":
        return "source=snapshot, captured on the host {} ({}h ago) — origin unreachable here".format(
            fresh["captured_at"], fresh["snapshot_age_hours"])
    return "source=local-ref, OFFLINE — origin unreachable and no host snapshot"


def _freshness_line(fresh):
    return "# corpus from {} ({}), tip age {}h".format(
        BLOG_REF, _provenance(fresh), fresh["ref_age_hours"])


def cmd_list(args, articles, fresh):
    rows = entries(articles)
    if args.json:
        print(json.dumps({"freshness": fresh, "articles": rows}, indent=2))
        return 0
    print(_freshness_line(fresh))
    print("# {} published articles ({} locale entries) — vantagepointconsulting.nl".format(
        len(articles), len(rows)))
    for r in rows:
        print("  [{}] {}  ({})  slug={}".format(
            r["locale"], r["title"], r["publishedAt"] or "?", r["slug"]))
    return 0


def cmd_check(args, articles, fresh):
    ranked = rank(args.candidate, entries(articles))
    hits = [r for r in ranked if r["score"] >= COLLISION_THRESHOLD]
    if args.json:
        print(json.dumps({"candidate": args.candidate, "freshness": fresh,
                          "collision": bool(hits), "nearest": ranked[:5]}, indent=2))
        return 2 if hits else 0
    print(_freshness_line(fresh))
    print('candidate: "{}"'.format(args.candidate))
    for r in ranked[:5]:
        print("  {:.2f}  [{}] {}  slug={}".format(r["score"], r["locale"], r["title"], r["slug"]))
    if hits:
        print("\nCOLLISION — this angle is already published. Per the blog-engine rule: either\n"
              "sharpen to a genuinely distinct angle, or make it an UPDATE to the existing\n"
              "article object (bump updatedAt), never a second post on the same query.")
        return 2
    print("\nCLEAR on title overlap. This check is lexical — it cannot see an adjacent angle\n"
          "under a different title. Read the `list` output before drafting.")
    return 0


def cmd_snapshot(args):
    """Acquire on the host for the namespaces that cannot. A snapshot written from
    anything but a live fetch would launder staleness forward with nothing downstream
    able to tell, so a failed fetch refuses rather than rewriting the file it already has."""
    _require_repo()
    if not _fetch():
        sys.exit("published_corpus: REFUSING to snapshot — origin unreachable. A snapshot is "
                 "only worth writing from a ref that was just refreshed; this one would hand "
                 "a stale corpus to every namespace that trusts it.")
    articles, age = _ref_corpus()
    fresh = {"fetched": True, "source": "origin", "ref_age_hours": round(age, 1)}
    write_snapshot(articles, fresh)
    print("# corpus snapshot at {} — {} articles, source=origin, tip age {}h".format(
        SNAPSHOT_PATH, len(articles), fresh["ref_age_hours"]))
    return 0


def main():
    p = argparse.ArgumentParser(description="Published corpus of vantagepointconsulting.nl")
    sub = p.add_subparsers(dest="cmd")
    ls = sub.add_parser("list", help="print the published corpus")
    ls.add_argument("--json", action="store_true")
    ck = sub.add_parser("check", help="rank the corpus against a candidate title")
    ck.add_argument("candidate")
    ck.add_argument("--json", action="store_true")
    sub.add_parser("snapshot", help="capture the corpus for readers that cannot fetch")
    args = p.parse_args()
    if not args.cmd:
        args.cmd, args.json = "list", False
    if args.cmd == "snapshot":
        sys.exit(cmd_snapshot(args))
    articles, fresh = load_corpus()
    handler = {"list": cmd_list, "check": cmd_check}[args.cmd]
    sys.exit(handler(args, articles, fresh))


if __name__ == "__main__":
    main()
