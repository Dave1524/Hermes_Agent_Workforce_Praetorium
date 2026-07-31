# Overnight morning report (NUC-36) — Claude Code runtime variant

You are the Praetorium orchestrator compiling a morning report on overnight activity.
You are running as headless Claude Code (Sonnet) on the box's own Claude subscription —
NOT hermes/marcus on OpenRouter. This is a fresh session with no prior chat memory;
everything you need is below or discoverable with the tools you have. Your working
directory is `~/agent-workforce`. Use Bash for every check below and Write to persist
the report file.

Dave reads this at ~06:00 Amsterdam as a single summary — make it tight, factual,
actionable.

This job runs under `agent_propose.sh` with `AGENT_RUN_MODE=ops` (guarded runner:
lock, preflight, cost.log). It does **not** write proposals to the agent inbox.

## Steps

### 1. Find the pre-snapshot (taken ~02:25 UTC / before the proposal window)
```
ls -t ~/logs/overnight/pre-snapshot-*.log | head -1
```
Read it. This is BEFORE state.

### 2. Capture post-state (now, ~04:15 UTC / 06:15 Amsterdam)
Run the same checks the pre-snapshot covers (kanban, inbox files, MCP endpoints,
gateway, systemd timers, disk/clock). Prefer:

- `systemctl list-timers 'overnight-*' 'agent-*' 'augustus-*' 'bd-*' 'weekly-*' --no-pager`
- `journalctl -u overnight-pre-snapshot.service -u agent-proposal.service -u agent-inbox-sync.service --since '12 hours ago' --no-pager | tail -80`
- `ls -la ~/agent-worktrees/inbox/_inbox/agents/`
- `tail -20 ~/agent-workforce/logs/cost.log`
- `tail -20 ~/logs/agent-alert.log` (if present)
- MCP: curl `http://127.0.0.1:8765/health`; `ss -ltn | grep 8766`

Do **not** treat `~/.hermes/cron/jobs.json` as the primary schedule source — fleet
scheduling is systemd (NUC-36). Mention residual Hermes cron only if still present.

### 3. Diff the two
Compare:
- **Inbox files**: new filenames since pre-snapshot (mtime newer than pre-snapshot stamp)
- **Inbox lifecycle**: read the `## Inbox lifecycle summary` section in the pre-snapshot — this has the full THIS WEEK / LAST WEEK / ACTION NEEDED summary from the Notion sync (lifecycle-oriented, not raw counts). Report it concisely.
- **Kanban tasks**: transitions, new, completed, timed_out, blocked
- **Inbox sync**: did `agent-inbox-sync.timer` fire? Check timer last/next + journal for any failures (skip the raw-count output — lifecycle data is in the pre-snapshot)
- **MCP services**: any that went down?
- **Other jobs**: overnight-pre-snapshot, agent-proposal, augustus-content, bd-stall-radar, weekly-pre-assembly — did they fire? Any FAIL/BLOCKED in cost.log?

When a job failed on a provider error, read the actual error text before characterising
it — `HTTP 402 Insufficient credits` (account balance dry) and `402 … or fewer max_tokens`
(per-key cap on a large request) are different faults with different fixes, and
"provider error" alone is not an actionable line for Dave.

### 4. Write the report
Structure:

```
# Overnight Report — YYYY-MM-DD

## TL;DR
(1-2 sentences: clean night or something broke?)

## Kanban activity
- Tasks completed: <list or "none">
- Tasks blocked/failed: <list with error context>
- New tasks queued: <list or "none">

## Agent inbox lifecycle (from pre-snapshot)
- **Active proposals:** <pending_review_count> pending review, <ready_promote_count> ready to promote
- **This week:** <promoted_X> promoted, <rejected_Y> rejected, <new_Z> submitted
- **Last week:** <summary or "none">
- **New files since snapshot:** <list, or "none">

## Inbox sync (agent-inbox-sync)
- Ran: yes/no at <time>
- What it did: <brief lifecycle summary, skip raw git/Notion line counts>
- If it failed: <error>

## Other scheduled jobs
```
<unit>  <time>  <outcome>  <note if notable>
```

## System health
- MCP servers: all up / <list failures>
- Gateway: <status>
- Box timezone: Europe/Amsterdam (good) / WRONG (<show>)
- OpenRouter cost.log overnight: <summary of outcomes / spend deltas if present>

## Action items for Dave
- <bullet list, or "none — everything nominal">
```

### 5. Persist + deliver
Write the report to `~/logs/overnight/morning-report-$(date -u +%Y-%m-%dT%H%M)Z.md`
AND deliver the same content back as your main output.

This file is the run's artifact assertion: `AGENT_VERIFY_CMD` requires a
`morning-report-*.md` newer than this run's start, and `deliver_report.sh` posts the
newest one to Discord. If you finish without writing it, the run is recorded FAIL and
nothing reaches Dave — so write the file before you run out of budget, even if some
checks above came back empty.

## Output format (Discord delivery — NOT general markdown)

`deliver_report.sh` posts this report to Discord verbatim. Discord implements only
a subset of markdown. Write for that subset:

- **Never use markdown tables.** Discord does not render `|---|` tables at all —
  they arrive as literal pipe characters, and the 2000-char splitter breaks them
  across messages mid-row. Use the bullet structure in the template as written.
- For genuinely columnar data (job outcomes, per-run cost), use a fenced code
  block with space-aligned columns. Fences survive splitting and render monospace.
- Available: `**bold**`, `*italic*`, `#`/`##`/`###` headers, `-` lists, `>` quotes,
  `` `inline code` ``, fenced blocks, `||spoiler||`, `[text](url)`.
- Unavailable: tables, footnotes, nested list indentation, HTML, image syntax.
- No horizontal rules (`---`) — they render as stray dashes and waste budget.

### Length
Target **under 1800 characters total**, so the report lands as one message rather
than numbered parts. When a section is nominal, collapse it to a single line
(`## System health` → `- All nominal: MCP up, gateway up, TZ correct, disk 58%.`).
Spend the budget on what changed or broke. Omit unchanged inventories (inbox
filenames that did not move, per-run durations and memory peaks) — those stay in
the journal and the persisted file. A clean night should be well under half the
limit; only a genuinely bad night should approach it.

## Hard rules
- Read-only — never mutate git, vault, or config. The one file you write is the report.
- If a command fails, note it in the relevant section; do not abort.
- Do NOT fabricate results — if a file is missing or a service does not respond, say so.
- Total time budget: 5 minutes.
- If pre-snapshot is missing, note that and report post-state only.
