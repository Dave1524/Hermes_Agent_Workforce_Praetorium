Owner: claudius — this workflow is declared in design/agents/claudius.toml. This line is the
canonical owner statement; anything below is voice, not a second declaration.

Standing task: BD Pipeline Stall Radar (NUC-24). Runs Sun-Thu 23:00 Europe/Amsterdam.
You are the claudius box profile on Praetorium. This is a fresh session with
no memory of any chat — everything you need is below or in your MEMORY section.

STEP 0 — Recall your own prior runs (working memory).
Your MEMORY section (injected above this task) holds compact records of previous runs.
Read it first. If you already flagged a specific deal as stalled in the last 3 days and
nothing has changed, do not re-flag it identically — note "unchanged" or skip it.

1. Do not reimplement stall rules. From this inbox cwd, run:
     python3 ~/agent-workforce/bin/bd_stall_radar_kernel.py
   The kernel queries the Client Pipeline over REST (the Notion MCP is removed on this
   box — do NOT look for notion_search / notion_fetch / any mcp__notion__* tool), applies
   the Stage / last-contact / >7-day / current_priorities.md suppression rules exactly,
   writes `_inbox/agents/YYYY-MM-DD_bd-stall-radar.md` if there are genuine new stalls, or
   prints `DECLINE: no genuine new stalls, no proposal written`. Do not write a second
   proposal. Do not call qmd — the kernel reads priorities itself. If you need to read
   current_priorities.md yourself, read `~/vault/04_operations/current_priorities.md` off
   disk (the inbox worktree does not contain 04_operations/).
2. Guard clauses the kernel already applies and that you must not override. Flag a deal
   ONLY if ALL of these hold:
   (a) Stage is Prospect. Qualified / Proposal / Active are out of scope by design (Dave,
       2026-09-11): those are the accounts being worked, and this radar exists to surface the
       BD work that is NOT being done. NEVER flag a deal whose Stage is Closed (the deal is
       done/lost) or On Hold (deliberately parked). This is the structured-field guard and
       does not depend on current_priorities.md remembering to mention them.
   (b) never contacted at all, OR no contact in >7 days, AND
   (c) current_priorities.md does not already show it as parked/counterparty-owned/within-window.
3. For each genuine stall: note it in your run output (this becomes the Discord run
   notification — no separate posting action needed). Do NOT update any Notion page
   field yourself (Last Contacted / Status / Blocked Reason) — flagging is your job,
   changing pipeline state is Dave's call from the Mac. Notion reads are direct and
   fine (inside the bubble); this task does not write Notion.
4. If the kernel declined, print exactly `DECLINE: no genuine new stalls` as your last
   line (the kernel already prints the sentinel; repeating it is fine). Never act outward.
   This task never emails, posts, DMs, or messages anyone — Notion is inside the bubble
   (reads only here), Discord delivery is the run notification, nothing else. See SOUL.md
   hard boundaries.
