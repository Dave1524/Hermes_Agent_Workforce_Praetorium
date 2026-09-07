#!/usr/bin/env python3
"""Offline tests for bin/published_corpus.py + bin/brief_collision_check.py.

No network, no git: the blog.ts parse and the collision logic are exercised against a fixture
that mirrors the real typed `blogArticles` shape. The regression under test is 2026-07-27 —
a queued brief asked for an article title the site had already published, and nothing on the
box could see the corpus.

The second regression is 2026-08-14 to 2026-09-06: the gate existed by then, but the one
agent it was written for could not run it. `_fetch` / `_ref_age_hours` / `_read_blog_ts` are
stubbed as the git seam, so acquisition is exercised with no repo, no network and no clock
dependency beyond `time.time()`.
"""
import json
import os
import shutil
import sys
import tempfile
import time

BIN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "bin")
sys.path.insert(0, os.path.abspath(BIN))

import brief_collision_check as gate  # noqa: E402
import published_corpus as corpus  # noqa: E402

FIXTURE = """
export const blogArticles: BlogArticle[] = [
  {
    id: 'grid-congestion-critical-path-cold-storage',
    category: 'cold-chain',
    publishedAt: '2026-07-27',
    updatedAt: '2026-07-27',
    featured: true,
    translations: {
      nl: {
        slug: 'netcongestie-kritieke-pad-koelhuizen',
        title: 'Waarom bepaalt netcongestie steeds vaker de openingsdatum van een koelhuis?',
        excerpt: 'iets',
        seoTitle: 'Netcongestie | Vantage Point Consulting',
        sections: [
          {
            heading: 'Een kop die geen title is',
            body: ['tekst'],
          },
        ],
      },
      en: {
        slug: 'grid-congestion-cold-store-critical-path',
        title: 'Why does grid congestion increasingly determine when a cold store can open?',
        excerpt: 'something',
        seoTitle: 'Grid congestion | Vantage Point Consulting',
      },
    },
  },
  {
    id: 'wms-implementations-run-late',
    category: 'warehouse-automation',
    publishedAt: '2026-07-08',
    updatedAt: '2026-07-24',
    featured: true,
    translations: {
      nl: {
        slug: 'waarom-lopen-wms-implementaties-uit',
        title: 'Waarom lopen WMS-implementaties uit?',
        excerpt: 'iets',
      },
      en: {
        slug: 'why-do-wms-implementations-run-late',
        title: 'Why do WMS implementations run late?',
        excerpt: 'something',
      },
    },
  },
];

export function getArticleBySlug(locale: Locale, slug: string) {
  return blogArticles.find((article) => article.translations[locale].slug === slug);
}
"""

QUEUE = """# Praetorium Task Queue

| Priority | Task ID | Deadline | Task | Acceptance bar | Status |
|---|---|---|---|---|---|
| P2 | Q-2026-07-09-1 | (none) | **Website content — draft Dutch insights-hub article: \
"Waarom lopen WMS-implementaties uit?"** From the audit. | Full NL draft. | OPEN |
| P1 | Q-2026-07-08-1 | 2026-07-14 | **Orchestration-layer product landscape.** Map vendors. \
| 5-8 players. | OPEN |
| P3 | Q-2026-06-01-9 | (none) | **Old thing** "Waarom lopen WMS-implementaties uit?" | bar | DONE |
"""

failures = []


def check(label, cond):
    print("  {}: {}".format("ok" if cond else "FAIL", label))
    if not cond:
        failures.append(label)


print("--- blog.ts parsing ---")
articles = corpus.parse_articles(FIXTURE)
check("finds both articles", len(articles) == 2)
check("does not treat getArticleBySlug as an article",
      all(a["id"] != "getArticleBySlug" for a in articles))
check("keeps publishedAt", articles[1]["publishedAt"] == "2026-07-08")
check("keeps updatedAt", articles[1]["updatedAt"] == "2026-07-24")

rows = corpus.entries(articles)
check("flattens to one row per locale", len(rows) == 4)
nl_wms = [r for r in rows if r["slug"] == "waarom-lopen-wms-implementaties-uit"]
check("parses the NL WMS title", nl_wms and nl_wms[0]["title"] == "Waarom lopen WMS-implementaties uit?")
check("seoTitle never mistaken for title",
      all("Vantage Point Consulting" not in r["title"] for r in rows))
check("section heading never mistaken for title",
      all(r["title"] != "Een kop die geen title is" for r in rows))

print("--- collision scoring ---")
check("identical title collides",
      corpus.similarity("Waarom lopen WMS-implementaties uit?",
                        "Waarom lopen WMS-implementaties uit?") >= corpus.COLLISION_THRESHOLD)
check("unrelated title does not collide",
      corpus.similarity("Wat kost een palletpositie?",
                        "Waarom lopen WMS-implementaties uit?") < corpus.COLLISION_THRESHOLD)
check("case and punctuation folded",
      corpus.similarity("waarom lopen wms implementaties uit",
                        "Waarom lopen WMS-implementaties uit?") >= corpus.COLLISION_THRESHOLD)
ranked = corpus.rank("Waarom lopen WMS-implementaties uit?", rows)
check("ranks the exact match first", ranked[0]["slug"] == "waarom-lopen-wms-implementaties-uit")

print("--- queue parsing + gate ---")
items = gate.parse_open_items(QUEUE)
check("reads only OPEN rows", len(items) == 2)
check("skips the DONE row", all(i["task_id"] != "Q-2026-06-01-9" for i in items))
check("keeps the task id", items[0]["task_id"] == "Q-2026-07-09-1")
check("pulls the quoted title",
      "Waarom lopen WMS-implementaties uit?" in gate.candidate_titles(items[0]["task"]))

collisions = gate.evaluate(items, rows)
check("flags the historical brief", len(collisions) == 1)
check("names the offending brief", collisions and collisions[0]["task_id"] == "Q-2026-07-09-1")
check("points at the live slug",
      collisions and collisions[0]["published"]["slug"] == "waarom-lopen-wms-implementaties-uit")
check("clean queue yields no collision", gate.evaluate(gate.parse_open_items(
    QUEUE.replace('"Waarom lopen WMS-implementaties uit?"', '"Hoe kies je een koelhuislocatie?"')),
    rows) == [])

print("--- corpus acquisition: the host fetches, the sandbox reads ---")
# augustus is the only agent on codex-acp and his bwrap namespace mounts a tmpfs over
# ~/.ssh. The site remote is an ssh-config alias, so with no ssh config the hostname does
# not resolve and his fetch failed every night from 2026-08-14 to 2026-09-06 — while the
# host fetched fine seconds later. The corpus is public data, so acquisition and
# interrogation split: the host writes a snapshot, the sandbox reads it. Nothing here
# touches git or the network; _fetch / _ref_age_hours / _read_blog_ts are the seam.
WORK = tempfile.mkdtemp(prefix="published-corpus-test.")
corpus.SITE_REPO = WORK
corpus.SNAPSHOT_PATH = os.path.join(WORK, "published_corpus.json")
corpus.SNAPSHOT_MAX_AGE_HOURS = 24.0


def stub_git(fetched, ref_age_hours):
    corpus._fetch = lambda: fetched
    corpus._ref_age_hours = lambda: ref_age_hours
    corpus._read_blog_ts = lambda: FIXTURE


def write_snapshot(captured_hours_ago, ref_age_hours=644.5):
    captured = time.gmtime(time.time() - captured_hours_ago * 3600)
    with open(corpus.SNAPSHOT_PATH, "w") as fh:
        json.dump({"captured_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", captured),
                   "freshness": {"fetched": True, "source": "origin",
                                 "ref_age_hours": ref_age_hours},
                   "articles": corpus.parse_articles(FIXTURE)}, fh)


def drop_snapshot():
    if os.path.exists(corpus.SNAPSHOT_PATH):
        os.remove(corpus.SNAPSHOT_PATH)


def attempt_load():
    """(articles, freshness), refusal_message — exactly one of the two is None."""
    try:
        return corpus.load_corpus(), None
    except SystemExit as exc:
        return None, str(exc.code)


# THE REGRESSION. Fetch impossible, local ref far past the lag window, host snapshot fresh.
# Before the split this refused, and augustus improvised three different behaviours over
# nine nights — including ten posts drafted with the duplicate-title gate not running.
stub_git(False, 999.0)
write_snapshot(1.0)
loaded, refusal = attempt_load()
check("a namespace that cannot fetch still loads the corpus", loaded is not None)
snapshot_fresh = loaded[1] if loaded else {}
check("and says the answer came from the host snapshot",
      snapshot_fresh.get("source") == "snapshot")
check("and carries the captured articles, not an empty corpus",
      bool(loaded) and len(loaded[0]) == 2)
check("and states when the snapshot was taken",
      "captured_at" in snapshot_fresh and snapshot_fresh.get("snapshot_age_hours") is not None)
# The tip is fixed in time, so its age grows with the wall clock: 644.5h at capture, one
# hour ago, is 645.5h now. Reading it off the unreachable local ref (999h here) would be
# answering a different question with the same key.
check("and ages the host's tip reading forward rather than re-deriving it locally",
      abs(snapshot_fresh.get("ref_age_hours", 0) - 645.5) < 0.2)
check("and keeps `fetched` false — content_state.sh reads it and this was not a fetch",
      snapshot_fresh.get("fetched") is False)

stub_git(False, 999.0)
write_snapshot(30.0)
loaded, refusal = attempt_load()
check("a snapshot past its max age is refused, never used", loaded is None)
check("and the refusal names the snapshot as the stale part",
      bool(refusal) and "stale" in refusal.lower() and "snapshot" in refusal.lower())

drop_snapshot()
stub_git(False, 999.0)
loaded, refusal = attempt_load()
check("no snapshot and a ref past the lag window still refuses", loaded is None)
check("and the refusal says the snapshot was absent, not stale",
      bool(refusal) and "no host snapshot" in refusal.lower())
check("and still names the lag ceiling it enforced",
      bool(refusal) and "{:.0f}h".format(corpus.MAX_LAG_HOURS) in refusal)

drop_snapshot()
stub_git(False, 10.0)
loaded, refusal = attempt_load()
check("a ref inside the lag window answers with no snapshot at all", loaded is not None)
check("and names the local ref as the source",
      bool(loaded) and loaded[1].get("source") == "local-ref")
local_fresh = loaded[1] if loaded else {}

stub_git(True, 644.5)
loaded, refusal = attempt_load()
origin_fresh = loaded[1] if loaded else {}
check("a live fetch is sourced origin", origin_fresh.get("source") == "origin")
check("and content_state.sh's two keys are both still there",
      origin_fresh.get("fetched") is True and origin_fresh.get("ref_age_hours") == 644.5)

print("--- the snapshot subcommand: the host's own honesty check ---")
drop_snapshot()
stub_git(True, 644.5)
check("snapshot exits 0 on a live fetch", corpus.cmd_snapshot(None) == 0)
payload = json.load(open(corpus.SNAPSHOT_PATH))
check("the snapshot records when it was captured", bool(payload.get("captured_at")))
check("the snapshot carries the parsed articles", len(payload.get("articles", [])) == 2)
check("the snapshot carries the freshness the host measured",
      payload.get("freshness", {}).get("source") == "origin")
check("the write is atomic — no temp file is left beside it",
      [n for n in os.listdir(WORK) if n.endswith(".tmp")] == [])

# A snapshot written from anything but a live fetch would launder staleness forward
# indefinitely: the sandbox would trust it, and nothing downstream could tell.
drop_snapshot()
stub_git(False, 1.0)
try:
    snapshot_rc = corpus.cmd_snapshot(None)
except SystemExit as exc:
    snapshot_rc = exc.code
check("a failed fetch never produces a snapshot", snapshot_rc != 0)
check("and leaves no file behind for the sandbox to trust",
      not os.path.exists(corpus.SNAPSHOT_PATH))

print("--- provenance is in the header augustus reads ---")
# The `# corpus from ...` line is the only place a reader learns whether the gate ran
# against origin, a snapshot, or a ref nothing could refresh. A fallback that does not
# say so is a silent fallback.
for mode, fresh in (("origin", origin_fresh), ("snapshot", snapshot_fresh),
                    ("local-ref", local_fresh)):
    line = corpus._freshness_line(fresh)
    check("the {} header names its source".format(mode), "source=" + mode in line)
    check("the {} header still states the tip age".format(mode), "tip age" in line)

shutil.rmtree(WORK, ignore_errors=True)


print("\n{} check(s) failed".format(len(failures)) if failures else "\nall checks passed")
sys.exit(1 if failures else 0)
