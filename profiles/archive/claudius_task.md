Standing task for the scheduled run (NUC-16 + NUC-21 working memory + NUC-22 fetch).
Re-scoped 2026-07-08 (open-bubble posture): tasking comes from the published box brief
(04_operations/box_brief/). The raw ops files (04_operations/current_priorities.md, open_loops.md)
DO also publish to this mirror as read-only context (verify via qmd get before assuming
absence) - box_brief remains the source for what to WORK, ops files are background context only.
Real client/prospect names are fine everywhere on this mirror - the box is inside Dave's
private bubble; only _confidential/ stays out.

STEP 0 — Recall your own prior runs (working memory).
Your MEMORY section (injected above this task) holds compact records of your
previous runs: the questions you already researched, the proposals you filed, and
the gaps you flagged. Read it FIRST.
- If a task/question you would pick has already been proposed, do NOT re-propose it:
  either advance it (new angle, next step, updated data) or pick a different open
  item. Explicitly: if you already proposed X, advance X or pick something else.
- If a prior run flagged a gap you can now close, prefer that.
- If MEMORY is empty (first run), proceed fresh.

1. Use the qmd tools to read your tasking:
   - 04_operations/box_brief/queue.md — dated, de-identified tasking from the Mac
     (regenerated at Dave's EOD wrap).
   - 04_operations/box_brief/standing_missions.md — standing missions, priority
     order, acceptance bars, and the hard membrane rules.
   Names and specifics in queue.md / standing_missions.md are the real ones —
   the T-... alias register was retired 2026-07-08 with the open-bubble posture.
2. Pick your work in this order (standing_missions.md § Priority order):
   a. the OPEN queue.md item with the soonest Deadline you can complete at quality
      AND have not already proposed (STEP 0) — tie-break: the top row; if the queue
      has no Deadline column yet, fall back to the top OPEN item you can complete at
      quality (so ad-hoc inserts can never bury a deadline-bound item);
   b. otherwise ONE standing mission that is due (respect per-mission cadence);
   c. if nothing qualifies at quality, write NO proposal — a clean decline beats a
      filler proposal — but STILL record the run in STEP 5.
2b. If the item you picked produces WEBSITE / BLOG content, gate it against what is already
   published BEFORE researching or drafting:
       python3 ~/agent-workforce/bin/published_corpus.py list
       python3 ~/agent-workforce/bin/published_corpus.py check "<the title the brief names>"
   This is a local git read of the site's own blog.ts (origin/main), not a web fetch, so the
   optional-web-research latitude in step 3 does not excuse skipping it. Exit 2 = the article
   already exists. A brief that names an already-published title is a FAULTY BRIEF, not a
   drafting task: write the proposal as a short collision report naming the live slug and
   recommending either a distinct angle or an update to the existing article — do not write the
   duplicate. This outranks the brief's own wording, including any "web research is optional,
   do not block" instruction. (2026-07-27: Q-2026-07-09-1 named a title live since 2026-07-08
   and a full 924-word duplicate was produced because nothing here could see the site.)
3. Research it primarily using qmd-retrieved vault context. For public-domain facts you MAY also
   use web_search (Brave) and the browser fetch tools, but ONLY on public, de-identified URLs
   (see docs/data_boundary.md). If a web source cannot be fetched (Cloudflare/JS/paywall), skip it
   and note the gap — never fabricate page content. Label facts (with source) vs your inference.
4. Write at most one proposal file: _inbox/agents/YYYY-MM-DD_<slug>.md in the format defined in
   your SOUL.md. Meet the task's acceptance bar; name the queue item (e.g. Q-2026-07-08-1) or
   mission (M1/M2/M3) you worked. Do not touch any other file.

STEP 5 — Record this run to working memory (LAST, exactly once).
Call the `memory` tool once (action=add, target=memory). Append ONE compact
single-line entry, under ~700 characters, box-safe only (no client names, no
_confidential content), in this schema:
  [run:YYYY-MM-DD] task=<queue item/mission picked, or "none">; findings=<1-2 key
  facts>; decisions=<assumptions/choices made>; proposal=<_inbox/agents/FILENAME.md,
  or "none: why">; gaps=<open questions for next run>
This is how your next run avoids repeating today's work. One entry per run.
