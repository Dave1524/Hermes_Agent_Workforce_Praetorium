Standing task: Weekly Review Pre-Assembly (NUC-24). Runs Fri 22:00 Europe/Amsterdam.
You are the claudius box profile on Praetorium. This is a fresh session with
no memory of any chat — everything you need is below or in your MEMORY section.

STEP 0 — Recall your own prior runs (working memory).
Your MEMORY section (injected above this task) holds compact records of previous runs.
If a prior pre-assembly run this week already covered a day, do not redo it — build on it.

1. Use the qmd tool's `multi_get` (path-based, fast — NOT the slow semantic `query`) to
   fetch this week's daily logs: 07_daily/logs/YYYY-MM-DD.md for Monday through today.
   Skip any date qmd reports missing — Dave doesn't log every day.
2. Use qmd `get` to fetch 04_operations/open_loops.md and 04_operations/key_decisions.md
   for this week's decisions and open items. (Your working directory is the inbox
   worktree, which does NOT contain 04_operations/ or 07_daily/ directly — qmd is the
   only way to read them here.)
3. Query Notion over the REST API — the Notion MCP is removed on this box, so REST is the ONLY
   Notion path (do NOT look for any mcp__notion__* tool; they no longer exist). Load the token on the
   SAME shell line, then query the Task Inbox data source for items completed this week:
     set -a; source ~/.config/agent-workforce/secrets.env; set +a; \
     curl -s -X POST "https://api.notion.com/v1/data_sources/4dbb4389-6c4a-4f57-b70f-10d899483c21/query" \
       -H "Authorization: Bearer $NOTION_API_TOKEN" -H "Notion-Version: 2025-09-03" \
       -H "Content-Type: application/json" -d '{"page_size":100}' | jq '.results[].properties'
   Pull Task Inbox items completed this week, plus any Daily Log / Decisions DB entries you can find
   the same way (see the bundled `notion` skill for REST patterns). Notion reads are direct and fine
   (inside the bubble) — this task does not write Notion. If a query returns `"object":"error"`, note
   it and continue — do not loop or hang.
4. Assemble a DRAFT weekly-review pre-read (not the final review — Dave still does the
   real weekly-review skill Friday/Saturday):
   - This week's completions (from daily logs + Notion Task Inbox), 3-6 bullets.
   - This week's decisions (from key_decisions.md), 1 line each.
   - Top 3 unresolved open_loops.md items ranked by leverage (highest tier first).
   - One line noting anything that looks stale or contradicted (do not fix it — flag it).
5. Write exactly one proposal file _inbox/agents/YYYY-MM-DD_weekly-pre-assembly.md with
   the draft above, per your SOUL.md format. This is a pre-read for Dave's own weekly
   review, not a replacement for it — say so in the proposal's header. If the week has no
   daily logs at all (nothing to assemble), write NO proposal instead of a filler one.
6. Never act outward. This task never emails, posts, DMs, or messages anyone — Notion
   reads only here, Discord delivery is the run notification. See SOUL.md hard boundaries.

STEP 5 (LAST, exactly once) — Record this run to working memory.
Call the `memory` tool once (action=add, target=memory). One compact line, under
~700 characters, box-safe (no _confidential content — client names are fine):
  [run:YYYY-MM-DD] task=weekly-pre-assembly; days_covered=<list>; proposal=<filename or
  "none: why">; gaps=<anything you couldn't check>
