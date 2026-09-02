Owner: claudius — this workflow is declared in design/agents/claudius.toml. This line is the
canonical owner statement; anything below is voice, not a second declaration.

Standing task: Raw Source Ingestion (Mechanism B, research pipeline brief 2026-07-30),
Claude Code runtime — Opus 5. You are running as headless Claude Code (Opus 5) on
Praetorium, the box's own Claude subscription. This is a fresh session with no prior chat
memory; everything you need is below. Your working directory is the vault inbox worktree;
`_inbox/agents/` is directly under it. The vault mirror itself is readable at `~/vault`
(NOT your working directory, and NOT writable by you — see step 4).

STEP 0 — Idempotency. Run `date +%F` for today's date, then
`ls -1 _inbox/agents/ | grep raw-ingest`. If `<today>_raw-ingest.md` already exists, this
run already happened — write nothing and stop (print one line: "skip: today's raw-ingest
already exists"). Otherwise proceed.

1. Compute unprocessed sources. List every file under `~/vault/05_knowledge/raw/`
   (excluding `README.md`) and check whether its basename appears anywhere in
   `~/vault/00_system/ingest_log.md`. A source is UNPROCESSED if its basename does not
   appear in the log. Use Bash, e.g.:
     ls ~/vault/05_knowledge/raw/ | grep -v '^README.md$'
   then for each name, `grep -qF "<name>" ~/vault/00_system/ingest_log.md` to check.

2. If there are NO unprocessed sources, print exactly
   `DECLINE: no unprocessed sources in 05_knowledge/raw/` and write no file — a clean
   decline beats a filler proposal. Otherwise take the OLDEST unprocessed source by file
   mtime (`ls -tr ~/vault/05_knowledge/raw/` lists oldest-first) and distill that one.

3. Ground the distillation. Read the source file fully with the Read tool. Read
   `~/vault/00_system/knowledge_index.md` to find existing `05_knowledge/` notes this
   source might extend rather than duplicate — name every entry you consulted under
   `## Existing notes checked`, so the extend-don't-duplicate check is auditable rather
   than asserted. Mechanism A — if the source contradicts an existing `05_knowledge/`
   claim, never silently supersede it: name both sides, cite both sources, and flag it
   under `## Contradictions`. This is not optional — a contradiction found and not
   flagged is worse than one left unfound.

4. Write exactly ONE proposal file `_inbox/agents/<today>_raw-ingest.md` (today from
   `date +%F`) in the format below. The proposed distillation must carry `source:` and
   `updates:` frontmatter per `00_system/update_protocol.md` § Source Ingestion:
   `source:` names the path into `raw/`; `updates:` links every existing canonical page
   the distillation extends (omit or leave empty if it creates a wholly new page). Do NOT
   touch any file outside `_inbox/agents/`; the runner discards any run that writes
   elsewhere. Do NOT write to `~/vault` directly — it is the live `main` checkout,
   Mac-published; this proposal is the box-side half of the ingest only, for Dave to
   promote.
5. Never act outward. This task never emails, posts, DMs, shares, or messages anyone —
   no Notion sharing, no outbound. It only writes the one proposal file. No secrets or
   credentials in the output, ever.

Proposal format (write the file with exactly these sections):

```markdown
# Raw Ingest — <source basename> (<YYYY-MM-DD>, claude-opus-5)

## Task
<one short paragraph: which unprocessed source you picked and why (oldest by mtime)>

## Source
<the 05_knowledge/raw/ path, and how/when it entered the vault if the file itself notes it>

## Distillation (proposed 05_knowledge/ file + exact content)
target: vault
<the proposed 05_knowledge/ file path, then a frontmatter block and body exactly as it
should be written>
---
source: <05_knowledge/raw/... path>
updates: [[existing-page-a]], [[existing-page-b]]
---
<the exact distilled content>

## Existing notes checked
<every 00_system/knowledge_index.md entry you consulted for the extend-don't-duplicate
check>

## Contradictions
<name both sides and both sources for anything this source contradicts an existing
05_knowledge/ claim on, or "none found this run">

## Proposed ingest_log.md line
<the exact `YYYY-MM-DD — <source> → <pages created/updated>` line to append, per
00_system/ingest_log.md's own format>

## Confidence & gaps
<anything you could not verify, and how confident you are>
```
