Standing task for the scheduled run (NUC-16 + NUC-21 working memory + NUC-22 fetch).
Re-scoped 2026-07-08: tasking now comes from the published box brief
(04_operations/box_brief/), not from Mac-only ops files (which are never on this box).

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
   Aliases (T-...) are deliberately unresolvable on this box — work the task as
   stated; client specifics re-attach Mac-side at promotion time.
2. Pick your work in this order (standing_missions.md § Priority order):
   a. the top OPEN queue.md item you can complete at quality AND have not already
      proposed (STEP 0);
   b. otherwise ONE standing mission that is due (respect per-mission cadence);
   c. if nothing qualifies at quality, write NO proposal — a clean decline beats a
      filler proposal — but STILL record the run in STEP 5.
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
