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

Commands:
  list                 Published corpus, one line per locale. What the profiles inject.
  check "<title>"      Rank the corpus by lexical overlap with a candidate title.
                       Exit 2 when overlap is high enough to call a collision.

Lexical overlap catches TITLE REUSE, which is what actually went wrong. It does not catch an
adjacent angle under a different title — read the `list` output and judge that yourself.
"""
import argparse
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


def load_corpus():
    """Return (articles, freshness). Refuses rather than answer from a too-stale ref."""
    if not os.path.isdir(SITE_REPO):
        sys.exit("published_corpus: site repo not found at {} (set VP_SITE_REPO)".format(SITE_REPO))
    fetched = _fetch()
    try:
        age = _ref_age_hours()
        source = _read_blog_ts()
    except subprocess.CalledProcessError as e:
        sys.exit("published_corpus: cannot read {}:{} — {}".format(
            BLOG_REF, BLOG_PATH, (e.stderr or "").strip()[:200]))
    if not fetched and age > MAX_LAG_HOURS:
        sys.exit("published_corpus: REFUSING — origin unreachable and {} is {:.0f}h old "
                 "(max {:.0f}h). A stale corpus answers 'no collision' for live articles."
                 .format(BLOG_REF, age, MAX_LAG_HOURS))
    return parse_articles(source), {"fetched": fetched, "ref_age_hours": round(age, 1)}


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


def _freshness_line(fresh):
    state = "fetched" if fresh["fetched"] else "OFFLINE — last known ref"
    return "# corpus from {} ({}), tip age {}h".format(BLOG_REF, state, fresh["ref_age_hours"])


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


def main():
    p = argparse.ArgumentParser(description="Published corpus of vantagepointconsulting.nl")
    sub = p.add_subparsers(dest="cmd")
    ls = sub.add_parser("list", help="print the published corpus")
    ls.add_argument("--json", action="store_true")
    ck = sub.add_parser("check", help="rank the corpus against a candidate title")
    ck.add_argument("candidate")
    ck.add_argument("--json", action="store_true")
    args = p.parse_args()
    if not args.cmd:
        args.cmd, args.json = "list", False
    articles, fresh = load_corpus()
    handler = {"list": cmd_list, "check": cmd_check}[args.cmd]
    sys.exit(handler(args, articles, fresh))


if __name__ == "__main__":
    main()
