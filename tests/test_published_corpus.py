#!/usr/bin/env python3
"""Offline tests for bin/published_corpus.py + bin/brief_collision_check.py.

No network, no git: the blog.ts parse and the collision logic are exercised against a fixture
that mirrors the real typed `blogArticles` shape. The regression under test is 2026-07-27 —
a queued brief asked for an article title the site had already published, and nothing on the
box could see the corpus.
"""
import os
import sys

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

print("\n{} check(s) failed".format(len(failures)) if failures else "\nall checks passed")
sys.exit(1 if failures else 0)
