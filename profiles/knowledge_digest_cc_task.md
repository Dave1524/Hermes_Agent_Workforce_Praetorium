Standing task: Knowledge Digest (Mechanism C, research pipeline brief 2026-07-30), Claude
Code runtime — Opus 5. You are running as headless Claude Code (Opus 5) on Praetorium,
the box's own Claude subscription. This is a fresh session with no prior chat memory.
Your working directory is the vault inbox worktree; `_inbox/agents/` is directly under
it. The vault mirror itself is readable at `~/vault` (NOT your working directory, and NOT
writable by you).

This is the *knowledge* digest — what the knowledge base itself learned this week — and
does not replace `weekly-pre-assembly` (the *activity* pre-read, driven by daily
logs/Notion/open_loops). State this distinction in the header of your proposal.

STEP 0 — Idempotency. Run `date +%F` for today's date, then
`ls -1 _inbox/agents/ | grep knowledge-digest`. If `<today>_knowledge-digest.md` already
exists, this run already happened — write nothing and stop (print one line: "skip:
today's knowledge-digest already exists"). Otherwise proceed.

1. Compute the 7-day delta with an exact git-log diff, NOT file mtimes (mtimes are
   unreliable across a re-clone or resync):
     git -C ~/vault log --since='7 days ago' --name-only --pretty=format: -- 05_knowledge/ 11_entities/
   Deduplicate the resulting path list. If it is EMPTY, print exactly
   `DECLINE: no 05_knowledge/ or 11_entities/ changes in the last 7 days` and write no
   file — a clean decline beats a filler proposal. Otherwise continue.

2. For each changed path, read the current file with the Read tool (skip any path that no
   longer exists — it may have been renamed or removed within the window; note that in
   Confidence & gaps rather than erroring). Use `git -C ~/vault log --since='7 days ago'
   -- <path>` to see what changed and when.

3. Also check for contradictions flagged this week: `git -C ~/vault log --since='7 days
   ago' -p -- 05_knowledge/` and look for any commit whose diff or message names a
   contradiction (e.g. added text referencing conflicting sources, or a note in a proposal
   that was promoted). This is a report of contradictions already flagged elsewhere, not a
   new contradiction search — you are not re-deriving Mechanism A here.

4. Read `~/vault/04_operations/open_loops.md` and identify entries added or materially
   updated in the last 7 days (cross-reference with
   `git -C ~/vault log --since='7 days ago' -p -- 04_operations/open_loops.md`) that are
   still unresolved (no closing note).

5. Write exactly ONE proposal file `_inbox/agents/<today>_knowledge-digest.md` (today from
   `date +%F`) in the format below. Keep the body UNDER 500 WORDS — this is a pointer
   digest into notes, not a re-summary of their content. Do NOT touch any file outside
   `_inbox/agents/`; the runner discards any run that writes elsewhere. Do NOT write to
   `~/vault` directly.
6. Never act outward. This task never emails, posts, DMs, shares, or messages anyone — no
   Notion sharing, no outbound. It only writes the one proposal file. No secrets or
   credentials in the output, ever.

Proposal format (write the file with exactly these sections; total body under 500 words):

```markdown
# Knowledge Digest — week of <Monday YYYY-MM-DD> (<YYYY-MM-DD>, claude-opus-5)

## Task
This is the KNOWLEDGE digest (what the knowledge base learned this week via a
05_knowledge/ + 11_entities/ git-log delta) — it does not replace weekly-pre-assembly,
which is the activity pre-read. <one line naming how many paths changed>

## Most significant additions (3-5, each linking the note)
<numbered list — each item names the file (as a vault-relative link) and one line on why
it matters, not a re-summary of its content>

## Contradictions flagged this week
<contradictions found in this week's 05_knowledge/ commits, or "none flagged this week">

## Open questions
<new 04_operations/open_loops.md entries from this week that are still unresolved, or
"none added this week">

## Unusually active topic
<one line — a topic accumulating notes faster than usual is worth deliberate attention,
or "nothing unusual this week">

## Confidence & gaps
<paths that could not be read, anything ambiguous in the delta, and how confident you are>
```
