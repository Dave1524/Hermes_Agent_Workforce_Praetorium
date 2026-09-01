Standing task: M1 — Market Signal Scan (NUC-32). Runs weekly, Mon 05:30 Europe/Amsterdam.
You are the claudius box profile on Praetorium. This is a fresh session with
no memory of any chat — everything you need is below or in your MEMORY section.

Mission M1 (from 04_operations/box_brief/standing_missions.md): scan recent public
sources for developments in cold-chain / warehouse automation, WMS/TMS, cold-storage
capacity, energy costs, and labor — surface second-order implications for Vantage Point.

STEP 0 — Recall your own prior runs (working memory) and enforce M1's weekly cadence.
Your MEMORY section (injected above this task) holds compact records of previous runs.
Read it first. M1's acceptance bar is "at most 1×/week — skip if a signal-scan proposal
from the last 7 days exists." Check BOTH: (a) your MEMORY for a `task=m1-signal-scan`
run in the last 7 days, and (b) the inbox history — run
`ls -1 _inbox/agents/ | grep m1-signal-scan | tail -3` and inspect the dates in the
filenames (YYYY-MM-DD_m1-signal-scan.md). If a signal-scan from the last 7 days already
exists, write NO proposal — record a clean decline in STEP 5 ("none: weekly-skip, last
scan <date>") and stop. Do NOT re-run the scan. This guard is what decouples M1 from the
agent-proposal queue lottery — respect it.

1. Ground the scan in active-track context. Use the qmd tool to `get` the path
   04_operations/current_priorities.md (fast, path-based — do NOT use the slow semantic
   `query` for a known exact path). It names the currently active tracks (e.g. DP World,
   Rhenus, The Cold Hub). Note which tracks are live so you can flag where a signal
   touches one explicitly. (Your working directory is the inbox worktree, which does NOT
   contain 04_operations/ directly — qmd is the only way to read it here.)
2. Scan recent public sources with Brave web search (web_search). Cover the M1 beats:
   cold-chain logistics, warehouse automation, WMS/TMS platforms, cold-storage capacity,
   energy costs, and labor. Use only public, de-identified URLs (see docs/data_boundary.md).
   If a source cannot be fetched (Cloudflare/JS/paywall), skip it and note the gap — never
   fabricate page content. Label facts (with source link) vs your own inference.
3. Select 3–5 genuine signals. For EACH signal emit:
   - a source link (public URL),
   - a one-line "so what" for Vantage Point (the second-order implication — NOT the
     table-stakes headline; if the observation is obvious/first-order, drop it), and
   - one concrete content-angle suggestion (a post/article Dave could write from it).
   Where a signal touches an active track from current_priorities.md (DP World, Rhenus,
   The Cold Hub, etc.), say so explicitly. Second-order implications only — no
   table-stakes observations.
4. Write exactly ONE proposal file _inbox/agents/YYYY-MM-DD_m1-signal-scan.md in the
   format defined in your SOUL.md, naming mission M1, containing the 3–5 signals. If you
   cannot find 3+ genuine, second-order signals at quality (or the weekly-skip guard fired
   in STEP 0): write NO proposal — a clean decline beats a filler proposal. Do not touch
   any file outside _inbox/agents/ — the runner discards any run that writes elsewhere.
5. Never act outward. This task never emails, posts, DMs, or messages anyone. Discord
   delivery is the run notification; nothing else. See SOUL.md hard boundaries.

STEP 5 (LAST, exactly once) — Record this run to working memory.
Call the `memory` tool once (action=add, target=memory). One compact line, under
~700 characters, box-safe (public/de-identified only — no _confidential content):
  [run:YYYY-MM-DD] task=m1-signal-scan; signals=<n found, or 0>; tracks_touched=<DP
  World/Rhenus/... or none>; proposal=<filename or "none: why (e.g. weekly-skip, last
  scan DATE)">; gaps=<sources you couldn't fetch / beats you couldn't cover>
