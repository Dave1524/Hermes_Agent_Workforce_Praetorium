Standing task for the scheduled run (NUC-16 + NUC-21 working memory + NUC-22 fetch).

STEP 0 — Recall your own prior runs (working memory).
Your MEMORY section (injected above this task) holds compact records of your
previous runs: the questions you already researched, the proposals you filed, and
the gaps you flagged. Read it FIRST.
- If a question you would pick has already been proposed, do NOT re-propose it:
  either advance it (new angle, next step, updated data) or pick a different open
  question. Explicitly: if you already proposed X, advance X or pick something
  else — do not re-propose X.
- If a prior run flagged a gap you can now close, prefer that.
- If MEMORY is empty (first run), proceed fresh.

1. Use the qmd tools to read Dave's current priorities (04_operations/current_priorities.md),
   open loops (04_operations/open_loops.md), and the most recent daily log.
2. Pick the SINGLE highest-leverage open research question that vault context shows is blocking
   or accelerating active Vantage Point work AND that you have not already proposed (see STEP 0).
   If nothing qualifies, write no proposal — but STILL record the run in STEP 5.
3. Research it primarily using qmd-retrieved vault context. For public-domain facts you MAY also
   use web_search (Brave) and the browser fetch tools, but ONLY on public, de-identified URLs
   (see docs/data_boundary.md). If a web source cannot be fetched (Cloudflare/JS/paywall), skip it
   and note the gap — never fabricate page content. Label facts (with source) vs your inference.
4. Write at most one proposal file: _inbox/agents/YYYY-MM-DD_<slug>.md in the format defined in
   your SOUL.md. Do not touch any other file.

STEP 5 — Record this run to working memory (LAST, exactly once).
Call the `memory` tool once (action=add, target=memory). Append ONE compact
single-line entry, under ~700 characters, box-safe only (no client names, no
_confidential content), in this schema:
  [run:YYYY-MM-DD] task=<question picked, or "none">; findings=<1-2 key
  vault-sourced facts>; decisions=<assumptions/choices made>;
  proposal=<_inbox/agents/FILENAME.md, or "none: why">; gaps=<open questions for
  next run>
This is how your next run avoids repeating today's work. One entry per run.
