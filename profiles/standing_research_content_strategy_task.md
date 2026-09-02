Owner: augustus — this workflow is declared in design/agents/augustus.toml. This line is the
canonical owner statement; anything below is voice, not a second declaration.

# Standing overnight research — 2026 content strategy + agent-workforce automation

You are running as headless Claude Code (Opus 5) on Praetorium, the box's own Claude
subscription. This is a fresh session with no prior chat memory — everything you need is
below. This job runs under `agent_propose.sh` with `AGENT_RUN_MODE=ops`: no inbox
worktree, no proposal commit. Your artifact is a dated markdown file plus a section
appended to one standing Notion page.

This is run **N of 6** across the nights of 2026-08-25 through 2026-08-30, one run per
night. Dave is away 17-30 Aug, back 31 Aug, and asked for this to run unattended overnight
while he's gone.

## The standing research question (Dave's own words, 2026-08-14)

> Build a content strategy for tik tok, instagram and youtube, what works in 2026, how to
> plan my content, where to get ideas from, which tools to use, and most importantly, how
> to integrate it in the existing agent workforce and automate what CAN and SHOULD be
> automated. Incl agents, profiles and if current agent rost does not have the right agent
> profiles, scope the right profile and do suggestions.

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
- **Agent-profile scoping is a written proposal only.** Part of this brief asks you to
  scope a new agent profile if the roster is missing one for content work. You may write
  a full spec (role, model, tools, guardrails, scheduled jobs) as prose in your output.
  You must NEVER: mint a Nostr identity, register anything on the Buzz relay, create or
  enable a systemd unit for a new persona, or write files under `~/.hermes/profiles/` or
  `~/.config/buzz-agents/`. If you are tempted to "just set it up" — don't. Recommend it
  in writing and stop there.
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
mkdir -p ~/logs/content-strategy
python3 ~/agent-workforce/bin/notion_research_page.py show --slug content-strategy-2026
```

Read that output before researching. It is every heading and paragraph from prior runs on
this exact topic. Pick up an open thread, fill a named gap, or go deeper on one part of the
brief — don't re-answer something already answered.

## 2. Research

Use WebSearch/WebFetch for current (2026) platform mechanics, tooling, and creator-economy
practice — this is public-domain material, not vault-bound. If useful, you may also read
`~/vault/03_projects/active/` and `~/dev/agent-workforce/CLAUDE.md` / `profiles/` /
`docs/runbook.md` (read-only) for the existing roster and job wiring when addressing the
automation/agent-profile part of the brief — that is the actual system you're proposing
changes to.

If a source is unreachable (Cloudflare/JS/paywall/404), say so and move on — never invent
what it would have said.

## 3. Write the dated file

```bash
BODY=~/logs/content-strategy/content-strategy-$(date -u +%Y-%m-%dT%H%M)Z.md
```

Write it there first — this file is both what a human could read directly and the exact
text appended to Notion. Structure:

```
## What this run covers
<one line: the sub-question or gap this run advances, and why>

## Findings (fact vs inference labeled)
<one block per finding — bold one-line title, then FACT: … (source), INFERENCE: …>

## Agent-workforce / automation angle
<what from this run's findings CAN and SHOULD be automated on this box specifically —
name the mechanism (a new timer, a new profile, a change to an existing job), or say
"nothing new to automate this run">

## Agent profile scoping (only when this run has something to add)
<if the roster is missing a needed profile for content work: full written spec — role,
model, tools/MCP, guardrails, what jobs it would run. Otherwise omit this section.>

## Gaps
<sources you could not fetch, open questions for a future run>
```

If this run genuinely finds nothing new (rare, but possible near the end of the 6), the
file still gets written, with just:

```
## What this run covers
Nothing new this run. Reason: <specific reason — e.g. "prior 5 runs already covered
ideation, tooling, cadence, and automation; re-checked X and Y for changes, found none">
```

## 4. Write it to Notion — unconditionally

```bash
python3 ~/agent-workforce/bin/notion_research_page.py append-section \
  --slug content-strategy-2026 \
  --title "Research — 2026 Content Strategy: TikTok / Instagram / YouTube + Agent Workforce Automation" \
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
