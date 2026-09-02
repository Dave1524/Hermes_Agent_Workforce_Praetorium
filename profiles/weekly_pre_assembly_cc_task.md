Owner: marcus — this workflow is declared in design/agents/marcus.toml. This line is the
canonical owner statement; anything below is voice, not a second declaration.

Standing task: Weekly Review Pre-Assembly (NUC-24), Claude Code runtime variant.
You are running as headless Claude Code (Sonnet) on Praetorium, the box's own
Claude subscription — NOT hermes/claudius on OpenRouter. This is a fresh session
with no prior chat memory; everything you need is below. Your working directory is
the vault inbox worktree; `_inbox/agents/` is directly under it.

Runs Fri 22:00 Europe/Amsterdam. You assemble a DRAFT pre-read for Dave's own weekly
review — you are not doing the review itself.

STEP 0 — Idempotency. Run `date +%F` for today's date, then
`ls -1 _inbox/agents/ | grep weekly-pre-assembly`. If `<today>_weekly-pre-assembly.md`
already exists, this run already happened — write nothing and stop (print one line:
"skip: today's pre-assembly already exists"). Otherwise proceed.

1. Read this week's daily logs directly from the vault mirror at `~/vault` (readable from
   here; your working directory is the inbox worktree, which does NOT contain 07_daily/ or
   04_operations/). Do NOT use `qmd multi-get` for these — every daily log now exceeds its
   10KB cap and it will return only SKIPPED notices. Compute the week and read what exists:
     mon=$(date -d 'last monday' +%F)
     for i in $(seq 0 6); do
       d=$(date -d "$mon +$i day" +%F)
       [ -f ~/vault/07_daily/logs/$d.md ] && echo "$d"
     done
   Read each file that exists with the Read tool. Dave does not log every day — skip
   missing dates silently, and note in the output which days had no log.

2. Read `~/vault/04_operations/open_loops.md` and `~/vault/04_operations/key_decisions.md`
   directly with the Read tool. Both are large (40-50KB); read them fully rather than
   grepping, so you rank against the whole list rather than the first match.

3. Query Notion over the REST API — the Notion MCP is removed on this box, so REST is the ONLY
   Notion path (do NOT look for any mcp__notion__* tool; they no longer exist). Load the token on the
   SAME shell line, then query the Task Inbox data source for items completed this week:
     set -a; source ~/.config/agent-workforce/secrets.env; set +a; \
     curl -s -X POST "https://api.notion.com/v1/data_sources/4dbb4389-6c4a-4f57-b70f-10d899483c21/query" \
       -H "Authorization: Bearer $NOTION_API_TOKEN" -H "Notion-Version: 2025-09-03" \
       -H "Content-Type: application/json" -d '{"page_size":100}' | jq '.results[].properties'
   Pull Task Inbox items completed this week, plus any Daily Log / Decisions DB entries you can find
   the same way. Notion reads are direct and fine (inside the bubble) — this task does not write
   Notion. If a query returns `"object":"error"`, note it as a gap and continue — do not loop or hang.

4. Assemble the DRAFT weekly-review pre-read:
   - This week's completions (from daily logs + Notion Task Inbox), 3-6 bullets.
   - This week's decisions (from key_decisions.md), 1 line each.
   - Top 3 unresolved open_loops.md items ranked by leverage (highest tier first).
   - One line noting anything that looks stale or contradicted (do not fix it — flag it).

5. Write exactly ONE proposal file `_inbox/agents/<today>_weekly-pre-assembly.md` (today from
   `date +%F`) in the format below. Say in the header that this is a pre-read, not a
   replacement for Dave's weekly-review skill. If the week has no daily logs at all (nothing
   to assemble), write NO file and print one line saying why — a clean decline beats a filler
   proposal. Do NOT touch any file outside `_inbox/agents/`; the runner discards any run that
   writes elsewhere.

6. Never act outward. This task never emails, posts, DMs, shares, or messages anyone —
   Notion reads only, Discord delivery is the run notification. No secrets or credentials
   in the output, ever.

Proposal format (write the file with exactly these sections):

```markdown
# Weekly Review Pre-Assembly — week of <Monday YYYY-MM-DD> (<YYYY-MM-DD>, claude-sonnet)

## Task
<one short paragraph: this is a DRAFT pre-read for Dave's own weekly review, not the
review itself; which days you covered and which had no log>

## This week's completions
<3-6 bullets, each tagged with its source: daily log date or Notion Task Inbox>

## This week's decisions
<one line each, from key_decisions.md; "none recorded this week" if empty>

## Top 3 open loops by leverage
target: vault
<numbered, highest tier first — item, why it is the highest-leverage one to move, and
what the next concrete step would be>

## Stale or contradicted
<one line flagging anything that looks out of date or in conflict — flag only, do not fix>

## Confidence & gaps
<days with no log, Notion queries that errored, anything you could not verify>
```
