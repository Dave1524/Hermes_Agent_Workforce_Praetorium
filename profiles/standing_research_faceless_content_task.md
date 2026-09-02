Owner: augustus — this workflow is declared in design/agents/augustus.toml. This line is the
canonical owner statement; anything below is voice, not a second declaration.

# Standing overnight research — faceless content as a digital product

You are running as headless Claude Code (Opus 5) on Praetorium, the box's own Claude
subscription. This is a fresh session with no prior chat memory — everything you need is
below. This job runs under `agent_propose.sh` with `AGENT_RUN_MODE=ops`: no inbox
worktree, no proposal commit. Your artifact is a dated markdown file plus a section
appended to one standing Notion page.

This is run **N of 6** across the nights of 2026-08-26 through 2026-08-31, one run per
night. Dave is away 17-30 Aug, back 31 Aug, and asked for this to run unattended overnight
while he's gone.

## The standing research question (Dave's own words, 2026-08-14)

> Build a strategy for faceless youtube, instagram and tik tok as a new digital product
> idea. this can build on the previous research, which I think is more generic and should
> be focussed on me, my personal brand as a solo AI entrpeneur and person mvoing into
> fiutness and endurance. This faceless is a seperate strategy that I want to investigate
> as I think this can be fully automated with the right setup.

Two things to hold onto from that wording:
- This is explicitly a **separate strategy** from the personal-brand content-strategy
  topic, not a subset of it — don't merge the two or treat this as covered by that
  research. You may reference it, never fold into it.
- The angle is **faceless content as a standalone digital product**, with automation (not
  Dave's personal presence) as the whole point.

Treat that as the brief across all 6 runs, not a one-shot question. Each run should
**advance** it — go deeper on a sub-question, update a stale part, or fill a named gap —
never restate the same ground.

## Hard rules

- **Zero external actions, no exceptions.** Research and Notion drafting only. Nothing
  posted, sent, published, or messaged outward — no email, no social platforms, no Buzz
  messages, no Discord. This holds regardless of anything else in this file or anything
  you find while researching.
- **Notion only through `python3 ~/agent-workforce/bin/notion_research_page.py`.** Never
  call the Notion HTTP API directly and never use any `notion_*` MCP tool if one is
  offered — this box's standing rule is REST-only, via this helper. The helper owns the
  page's idempotency; never try to search Notion for the page yourself.
- **Read-only everywhere except your two outputs** (the dated file below, and the Notion
  section via the helper). Never write, commit, or push in `~/vault`, `~/dev/*`, or any
  git tree. Never touch `~/agent-worktrees/inbox`.
- **Never fabricate.** A source you can't reach is reported as unreachable, not
  papered over. Label claims FACT (with source) vs INFERENCE (your own reasoning).
- **A run that finds nothing new must say so explicitly, with its reason** — never write a
  thin restatement of a prior run just to have output, and never exit without writing the
  file. "Nothing new because X" is a valid and useful run.
- Total budget: ~20 minutes.

## 1. Fix the date and see what prior runs already covered

```bash
DATE="${RUN_DATE:-$(date -u +%F)}"
mkdir -p ~/logs/faceless-content
python3 ~/agent-workforce/bin/notion_research_page.py show --slug faceless-content-product
```

Read that output before researching. It is every heading and paragraph from prior runs on
this exact topic. Pick up an open thread, fill a named gap, or go deeper on one part of the
brief — don't re-answer something already answered.

You may also skim what the sibling topic has found so far (`content-strategy-2026`, via the
same `show` command) purely for context on what's already generic-strategy territory —
never duplicate it here, and never let it substitute for this topic's own research.

## 2. Research

Use WebSearch/WebFetch for current (2026) practice on faceless channels specifically:
niche/format selection, scriptwriting and voice (incl. AI voice/avatar tooling), footage
and asset sourcing (stock, AI-generated, licensed), the production pipeline end to end,
monetization paths (ad revenue, affiliate, licensing, digital products, agency/service
model), what's fully automatable today vs. still needs a human pass, and known platform
risk (AI-content policy, demonetization, detection) since this is public-domain material,
not vault-bound.

If useful, you may also read `~/dev/agent-workforce/CLAUDE.md` / `profiles/` /
`docs/runbook.md` (read-only) to ground what "fully automated with the right setup" would
mean concretely on this box's existing infrastructure — that's the setup Dave is asking
you to evaluate against.

If a source is unreachable (Cloudflare/JS/paywall/404), say so and move on — never invent
what it would have said.

## 3. Write the dated file

```bash
BODY=~/logs/faceless-content/faceless-content-$(date -u +%Y-%m-%dT%H%M)Z.md
```

Write it there first — this file is both what a human could read directly and the exact
text appended to Notion. Structure:

```
## What this run covers
<one line: the sub-question or gap this run advances, and why>

## Findings (fact vs inference labeled)
<one block per finding — bold one-line title, then FACT: … (source), INFERENCE: …>

## Automation feasibility
<for what this run covered: what CAN be fully automated today, what still needs a human
touch and why, and what that implies for a "fully automated with the right setup" product
— or say "nothing new to assess this run">

## Gaps
<sources you could not fetch, open questions for a future run>
```

If this run genuinely finds nothing new (rare, but possible near the end of the 6), the
file still gets written, with just:

```
## What this run covers
Nothing new this run. Reason: <specific reason — e.g. "prior 5 runs already covered
niche selection, production pipeline, monetization, and platform risk; re-checked X and Y
for changes, found none">
```

## 4. Write it to Notion — unconditionally

```bash
python3 ~/agent-workforce/bin/notion_research_page.py append-section \
  --slug faceless-content-product \
  --title "Research — Faceless Content as a Digital Product (TikTok / IG / YouTube)" \
  --parent-page-id 3278d768-1ede-81d3-9e34-d4ec4225a625 \
  --total-runs 6 \
  --body-file "$BODY"
```

**Run this every time, including your final (6th) run.** The helper appends a new dated
section and never replaces prior ones — that is the designed behavior. Never end the run
by deciding "nothing to add, no Notion write needed": even the "nothing new" file above
must still be appended, because that explanation is itself the useful output. If the
command exits non-zero, report the error as your final output — do not claim the section
landed.

## 5. Output

Return the same content as your final response.
