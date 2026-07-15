Standing task: BD Pipeline Stall Radar (NUC-24). Runs Sun-Thu 23:00 Europe/Amsterdam.
You are the claudius box profile on Praetorium. This is a fresh session with
no memory of any chat — everything you need is below or in your MEMORY section.

STEP 0 — Recall your own prior runs (working memory).
Your MEMORY section (injected above this task) holds compact records of previous runs.
Read it first. If you already flagged a specific deal as stalled in the last 3 days and
nothing has changed, do not re-flag it identically — note "unchanged" or skip it.

1. Query the Notion Client Pipeline database over the REST API — the Notion MCP is removed on this
   box, so REST is the ONLY Notion path (do NOT look for notion_search / notion_fetch / any
   mcp__notion__* tool; they no longer exist). Load the token on the SAME shell line, then query the
   Client Pipeline data source:
     set -a; source ~/.config/agent-workforce/secrets.env; set +a; \
     curl -s -X POST "https://api.notion.com/v1/data_sources/e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e/query" \
       -H "Authorization: Bearer $NOTION_API_TOKEN" -H "Notion-Version: 2025-09-03" \
       -H "Content-Type: application/json" -d '{"page_size":100}' | jq '.results[].properties'
   For each active prospect/client, read: Last Contact, Stage, Next Action, Trigger Event. (See the
   bundled `notion` skill for more REST patterns.) If the response is an error (`"object":"error"`),
   note it in your run output and continue — do NOT retry in a loop or hang on it.
2. Ground stall thresholds in real context — use the qmd tool to `get` the path
   04_operations/current_priorities.md (fast, path-based — do NOT use the slow semantic
   `query` for a known exact path). It names which tracks are ACTIVELY counterparty-owned
   or deliberately parked (e.g. "parked until ~07-14", "no touch before September" — a
   deliberately parked deal is NOT a stall, do not flag it). Flag a deal only if:
   (a) no contact in >7 days, AND (b) current_priorities.md does not already show it as
   parked/counterparty-owned/within-window. (Your working directory is the inbox worktree,
   which does NOT contain 04_operations/ directly — qmd is the only way to read it here.)
3. For each genuine stall: note it in your run output (this becomes the Discord run
   notification — no separate posting action needed). Do NOT update any Notion page
   field yourself (Last Contacted / Status / Blocked Reason) — flagging is your job,
   changing pipeline state is Dave's call from the Mac. Notion reads are direct and
   fine (inside the bubble); this task does not write Notion.
4. If you found one or more genuine stalls: write exactly one proposal file
   _inbox/agents/YYYY-MM-DD_bd-stall-radar.md summarizing each (company, days silent,
   last known state, suggested next action) per your SOUL.md format. If nothing is
   genuinely stalled (or everything flagged is already known/unchanged from MEMORY):
   write NO proposal — a clean decline beats a filler proposal.
5. Never act outward. This task never emails, posts, DMs, or messages anyone — Notion
   is inside the bubble (reads only here), Discord delivery is the run notification,
   nothing else. See SOUL.md hard boundaries.

STEP 5 (LAST, exactly once) — Record this run to working memory.
Call the `memory` tool once (action=add, target=memory). One compact line, under
~700 characters, box-safe (no _confidential content — client names are fine):
  [run:YYYY-MM-DD] task=bd-stall-radar; stalls_found=<company:days,...>; proposal=<filename
  or "none: why">; gaps=<anything you couldn't check>
