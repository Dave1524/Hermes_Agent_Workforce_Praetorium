# Brief: render agent-inbox proposals into the Notion page body
**Date:** 2026-08-31   **Verify:** `bash bin/verify.sh` (from `~/dev/agent-workforce`), then the live checks under **Test plan**

## The problem, as measured

Dave opened the Agent Inbox row *Knowledge Digest — week of 2026-08-10*
(`3be8d768-1ede-81dc-97a6-e52015df7658`), followed its `Box Link`, and got a GitHub 404.
Two separate facts, both verified 2026-08-31:

1. **Every one of the 81 rows in the Agent Inbox data source has an empty page body.**
   `GET /blocks/<page_id>/children` returns `{"results": []}` for all sampled rows.
   `agent_inbox_notion_sync.py` writes properties only — the richest of them is
   `Excerpt`, hard-capped at 280 characters. The proposal text has never been in Notion.
   Row census: `New 14, Approved 6, Rejected 42, Promoted 19`.

2. **The `Box Link` URL is not malformed and the file is not missing.**
   `gh api repos/Dave1524/obsidian-ai-os-boxsafe/contents/_inbox/agents/2026-08-16_knowledge-digest.md?ref=agents/inbox`
   returns `html_url` **byte-identical** to the stored `Box Link`
   (`…/blob/agents/inbox/_inbox/agents/2026-08-16_knowledge-digest.md`), size 3670,
   sha `97d68ca…`. The file is on `origin/agents/inbox`; local `HEAD` and
   `origin/agents/inbox` are both `f03c379`. The repo is **private**
   (`gh api … --jq .private` → `true`), and GitHub serves **404, not 403**, to any browser
   session without access.

So the 404 is *authentication*, not a broken path, and **there is no URL edit that fixes
it**. The link is a reference for a signed-in session; the proposal has to be readable in
Notion on its own. That is what this brief builds.

## Acceptance criteria

1. **Every Agent Inbox row whose proposal file exists on the box carries the full proposal
   markdown as native Notion blocks in its page body.** "Every kind" means every file in
   `~/agent-worktrees/inbox/_inbox/agents/*.md` regardless of producer — standing-research,
   m1-signal-scan, knowledge-digest, weekly-pre-assembly, bd-stall-radar,
   bd-followup-drafts, raw-ingest, and one-off proposals alike. No per-kind branching.

2. **Rendering fidelity (Dave's explicit choice — rich render).** The converter emits:
   - **Block level:** `# / ## / ###` → `heading_1/2/3`; `- ` / `* ` → `bulleted_list_item`;
     `N. ` → `numbered_list_item`; `> ` → `quote`; a line of three or more `-` → `divider`;
     a ```` ``` ```` fence → one `code` block (`language: "plain text"`, fence info string
     ignored — Notion rejects unknown languages); a GFM pipe table (header row +
     `| --- |` separator + body rows) → one `table` block with `table_row` children;
     everything else → `paragraph`. Blank lines are dropped, as today.
   - **Inline level, inside every block's `rich_text`:** `**bold**` → `annotations.bold`;
     `*italic*` / `_italic_` → `annotations.italic`; `` `code` `` →
     `annotations.code`; `[text](url)` → `text.link.url`; a bare `http(s)://…` (including
     the `<https://…>` angle-bracket form the research proposals use heavily) → an
     autolinked span. `[[wikilink]]` stays **plain text** — it is a vault-internal
     reference with no resolvable URL, and inventing one would be a fabricated link.
   - Measured corpus this must survive: 19 files, 49–424 lines, up to 36 KB; 104 table
     lines (largest contiguous table 14 rows, in `2026-08-18_standing-research.md`);
     82 code fences; ~1,900 bold spans; ~870 inline-code spans; 96 markdown links;
     236 bare URLs; longest single line 1,800 chars
     (`2026-08-13_standing-research.md`). No nested bullets and no YAML frontmatter
     appear in the corpus — do not build for either.

3. **Body writes are idempotent and crash-safe.** A completed body ends with a `divider`
   followed by a sentinel paragraph matching `^— synced from <filename> @ <ISO-8601> —$`.
   The sync then behaves as:
   - page has **no** children → write the body;
   - page has children **ending in the sentinel** → do nothing (no re-write, no stacking);
   - page has children **not** ending in the sentinel (a partial write from a crashed or
     rate-limited run) → delete all children and rewrite.
   The sentinel is deliberately the *last* thing written, so it can only exist if every
   preceding batch landed. Chosen over adding a `Body Synced` property because it needs no
   schema migration to the data source and doubles as visible provenance for Dave.

4. **The page opens with a provenance header** before the proposal text: one paragraph
   naming the source filename, the branch (`agents/inbox`), and the `Box Link` as a
   clickable link, plus a `divider`. This is what makes the page self-describing when the
   GitHub link 404s for an unauthenticated session.

5. **`--backfill-bodies` fills the existing backlog.** A run over the current state writes
   bodies for all rows whose file is present on disk — the 19 files now in
   `_inbox/agents/`, covering the 14 `New` + 6 `Approved` rows Dave still has to act on.
   Re-running it is a no-op (criterion 3).

6. **One converter owns markdown→blocks.** `bin/notion_markdown.py` is created as the
   single owner, and the two existing partial converters delegate to it:
   `notion_daily.blocks_from_markdown` and `ops_page_publish.markdown_to_blocks` lose their
   bodies and call the shared module. A third copy is the exact regression this repo's
   `CLAUDE.md` warns about; the new module is a strict superset of both (it must keep
   `notion_daily`'s numbered-list and `>`-quote handling and `ops_page_publish`'s fenced
   code handling). **Flagged consequence:** the daily-plan / EOD / ops pages will start
   rendering bold, inline code, links and tables instead of showing raw markdown. Same
   content, better rendering — but it is a visible change to Dave's morning briefing and
   should be called out when reporting, not discovered.

7. **Nothing else changes.** `--count` output, the CREATE property set (`Proposal`,
   `Status`, `Filename`, `Box Link`, `Excerpt`, `Source`, `Proposal Date`, `Notes`), the
   REFLECT pass, the `Processed At` backfill, the conflict surfacing, and the whole
   lifecycle report keep byte-identical behaviour. `agent_inbox_apply.py` — the
   Notion→box decision loop — is not touched: Notion is **already** Dave's tool for
   handling proposals (Rejected auto-applies inside the box-safe membrane, Approved is a
   Mac hand-off). Only readability was missing.

8. **The gate is green:** `bash bin/verify.sh` passes.

## Notion API constraints the implementation must respect

These are the ones that bite silently; none of them is enforced by a helpful error.

- **≤100 blocks per `PATCH /blocks/{id}/children`.** A 36 KB proposal is ~420 blocks — 5
  batches. Batch, do not send one array.
- **≤2000 chars per `rich_text[].text.content`.** Both existing `rt()` helpers chunk at
  1900; keep that number.
- **≤100 `rich_text` elements per block.** Inline splitting can exceed this on a long,
  heavily-marked line (the 1,800-char line is the worst case in the corpus). If a block's
  span list exceeds 100, merge the tail spans into one unannotated span rather than
  letting the request 400.
- **Table shape:** the `table` block carries `table_width`, `has_column_header: true`,
  `has_row_header: false`, and `children` = `table_row` blocks whose `cells` is a list of
  rich_text arrays **whose length equals `table_width` exactly** — pad short rows, truncate
  long ones. The `| --- |` separator row is consumed, never emitted. Nesting depth 2 in a
  single request is permitted, so a table plus its rows goes in one batch; count the table
  block and its rows against the 100-block budget conservatively.
- **Deleting children is one `DELETE /blocks/{block_id}` per block** — there is no bulk
  delete. Paginate `GET /blocks/{id}/children?page_size=100` to collect ids first.
  `notion_daily.replace_children` already does exactly this; reuse the shape.
- **`code` block `language` must be a value Notion knows.** Always emit `"plain text"`;
  the corpus's fence info strings are not validated against Notion's enum.

## Files to modify

- **`bin/agent_inbox_notion_sync.py`** — the main change.
  - Import the shared converter.
  - Add `write_body(api, page_id, filename, path, box_link)`: build provenance header +
    converted blocks + divider + sentinel; clear existing children when they are present
    without a sentinel; append in ≤100-block batches; return `"written" | "skipped" | "repaired"`.
  - Call it from the CREATE loop immediately after the `POST /pages` that makes the row, so
    every future proposal lands complete. Keep the row creation and the body write as two
    calls (a create carrying inline `children` is capped at 100 blocks and would silently
    truncate a long proposal).
  - Add `--backfill-bodies`: iterate rows whose `Filename` matches a file on disk and run
    the same `write_body`. Honour `--dry-run` (report the block count it *would* write, and
    write nothing).
  - Report body activity in the run summary next to `created` / `reflected` / `backfilled`,
    e.g. `bodies written this run: 3 (1,142 blocks)`.
  - `--count` must stay read-only and must not touch bodies — it is called frequently by
    `inbox_backlog_alert.sh` and `praetorium-status.sh`.
- **`bin/notion_daily.py`** — delete the body of `blocks_from_markdown` / `block_from_line`
  and delegate to `notion_markdown`. Keep `rt()` where other callers use it.
- **`bin/ops_page_publish.py`** — delete `markdown_to_blocks`, `code_block`, `heading`,
  `paragraph` and delegate to `notion_markdown`.

## Files to create

- **`bin/notion_markdown.py`** — the single markdown→Notion-blocks owner. Pure and
  offline: markdown string in, block dicts out, no HTTP, no token, no filesystem. Split
  along its two real seams so each is testable alone: a block-level scanner and an
  inline-span parser. Keep functions small; this is the file most at risk of becoming a
  god-file.
- **`tests/test_notion_markdown.py`** — offline unit tests, no network. Cover, at minimum:
  each block type; a table with a short row and a long row (padding/truncation); the four
  inline annotations; a `[text](url)` link and a bare/angle-bracket URL; a `[[wikilink]]`
  staying plain; the >100-span merge; the 1900-char chunk boundary; a code fence containing
  a line that *looks* like a heading or a table row (must stay verbatim inside the fence).
  Parameterise the block-type cases rather than writing one test each.
- **`tests/test_notion_markdown.sh`** — the `exec python3 tests/test_notion_markdown.py`
  driver, because `bin/verify.sh` only executes `tests/*.sh`. Copy the shape of
  `tests/test_notion_daily.sh`.
- **`tests/test_agent_inbox_body_sync.py`** — offline behaviour test with a `FakeNotion`
  HTTP seam, modelled on `tests/test_notion_daily.py`. Pin the contract that matters:
  (a) creating a row writes a body ending in the sentinel; (b) a second run over the same
  row writes **nothing** — no duplicate blocks, no second DELETE; (c) a row whose children
  lack the sentinel is cleared and rewritten; (d) batching never exceeds 100 children per
  request; (e) `--dry-run` issues zero writes; (f) `--count` issues zero writes and its
  stdout is unchanged.
- **`tests/test_agent_inbox_body_sync.sh`** — its driver.

## Test plan

Offline, in the gate:
- `bash bin/verify.sh` — must be green. It runs `bash -n` + `shellcheck -S error` over
  `bin/*.sh` and then every `tests/*.sh`, which now includes the two new drivers.

Live, by hand after the gate (these are the ones that prove the feature, and the gate
cannot see them):
1. `python3 bin/agent_inbox_notion_sync.py --backfill-bodies --dry-run` — expect a report
   naming 19 files and a plausible block count, and **zero** Notion writes.
2. `python3 bin/agent_inbox_notion_sync.py --backfill-bodies` — then re-read the page that
   started this:
   `GET /blocks/3be8d768-1ede-81dc-97a6-e52015df7658/children` must return a non-empty list
   ending in the sentinel paragraph.
3. Open that page in Notion and read it. Confirm by eye: headings are headings, the
   `## Contradictions flagged this week` section is legible, `[[05_knowledge/…]]` renders
   as plain text, and no raw `**` survives.
4. Spot-check the two hardest files rather than the easy one:
   `2026-08-18_standing-research.md` (the 14-row table) and
   `2026-08-13_standing-research.md` (the 1,800-char line).
5. Re-run `python3 bin/agent_inbox_notion_sync.py --backfill-bodies` — it must report
   0 bodies written and the pages must be unchanged (idempotency).
6. Confirm the unattended path still works end to end:
   `systemctl start agent-inbox-sync.service && cat ~/agent-workforce/logs/agent_inbox_pipeline.last`.
7. Sanity-check the migrated converters did not regress the daily jobs:
   `bash tests/test_notion_daily.sh` and `bash tests/test_ops_view.sh`.

## Out of scope / do not touch

- **"Fixing" the GitHub 404.** There is nothing to fix in the URL — it is GitHub's own
  canonical form for a file that exists. It 404s because the repo is private. Do not
  rewrite `BOX_LINK_BASE` to a commit-SHA permalink, a `raw.githubusercontent.com` URL, or
  anything else; every variant is equally gated, and a token-bearing URL must never be
  written into Notion. The link stays exactly as it is, as a reference.
- **Backfilling bodies for the 62 already-decided rows** (`Rejected` / `Promoted`) whose
  files were removed from `_inbox/agents/`. Their content is recoverable from the
  `agents/inbox` git history (`git log --diff-filter=D` then `git show <sha>^:<path>`), but
  they are archive, not Dave's queue. Follow-up if he wants it.
- **`source_for()` misclassification.** knowledge-digest, raw-ingest, bd-followup-drafts
  and one-off proposals all fall through to `research_analyst` — which is why the row in
  question is labelled `research_analyst` rather than a digest. Real, small, and a
  different change; it needs new `Source` select options
  (current options: `research_analyst, bd_stall_radar, weekly_pre_assembly, other,
  m1_signal_scan`). Do not fold it in.
- **`agent_inbox_apply.py`** and the approve/reject membrane. Working as designed.
- **Any vault write, any push to `main`, any run of `publish_boxsafe.sh`.**
- **`Excerpt` and the board view.** The 280-char excerpt stays as the list-view preview.

## Notes / preconditions

- **Verified state, 2026-08-31:** 19 `.md` files in `~/agent-worktrees/inbox/_inbox/agents/`;
  worktree `HEAD` == `origin/agents/inbox` == `f03c379`, clean; 81 Notion rows, all with
  empty bodies; data source `ecb52f8e-2125-416f-b08e-824a7416e561`, database
  `5297d8f6-9319-47d8-8077-9a1aea47ca7f`; schema as listed above, no `Body Synced` property
  (and none is needed — see criterion 3).
- **`agent-inbox-sync.service` runs the SOURCE checkout, not the deployed tree:**
  `ExecStart=/home/dave/dev/agent-workforce/bin/agent_inbox_pipeline.sh`,
  `WorkingDirectory=/home/dave/dev/agent-workforce`. So this change goes live on the next
  timer fire (every ~30 min) **without** `bin/deploy`. Only `ExecStopPost`
  (`deliver_inbox_sync.sh`) reads `~/agent-workforce/`, and this brief does not touch it.
  All three inbox scripts are currently in sync between source and deployed tree.
- **Commit immediately after editing.** `agent-workforce-auto-sync.timer` fires every 15
  minutes and sweeps any dirty tree to `origin/main` under a generic `Auto-sync:` message,
  which loses the message explaining why.
- **Notion access is REST-only.** Use `notion_rest.load_token()` (env, then
  `~/.config/agent-workforce/secrets.env`). Never a Notion MCP tool — Dave's standing rule,
  and the MCP linkifies `.md` filenames, which would break the exact-`Filename` dedup this
  sync depends on.
- **`pipefail` trap** (repo `CLAUDE.md`): never end a pipeline in `grep -q` or `head` in the
  new test drivers. Use `grep … >/dev/null`, or drop the pipe.
- The corpus has no nested bullets and no frontmatter today, but a future producer could
  emit either. Degrade to a flat `bulleted_list_item` / `paragraph` rather than raising —
  an unrenderable proposal is worse than an imperfectly rendered one.
