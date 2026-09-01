# Brief: Branch-row bodies for the Agent Inbox sync
**Date:** 2026-09-01   **Verify:** `bash bin/verify.sh` (repo root)

## Context — why this exists

`bin/agent_inbox_notion_sync.py` renders proposal markdown into the Notion page body
(since 2026-08-31, commits `611bf5c`/`a1a17fe`/`bcfb55d`), but both its CREATE path and
`--backfill-bodies` glob `~/agent-worktrees/inbox/_inbox/agents/*.md` only. The Agent Inbox
DB (data source `ecb52f8e-2125-416f-b08e-824a7416e561`) also contains **branch-shaped rows**:
Filename = `agents/<date>-<slug>` naming a branch on the canonical vault repo
(`~/dev/Obsidian_AI_Operating_System`), Box Link = a GitHub compare URL. Interactive sessions
register these by hand for proposals that live as canonical-repo branches rather than inbox
files. The sync is structurally blind to them, so they sit with an empty body forever and
look exactly like a regression of the body fix — which is what Dave reported on 2026-09-01
(rows `agents/2026-08-21-ugc-creator-brief`, `agents/2026-08-21-camping-trip-lessons`,
both hand-registered 2026-08-31 ~16:30 CEST, both bodyless while that night's inbox-file
proposal rendered fine at 95 blocks). Both were backfilled by a one-off script on 2026-09-01;
this brief makes the sync own that job.

## Acceptance criteria

- On every normal sync run (not `--count`), rows whose Filename matches
  `agents/<YYYY-MM-DD>-<slug>` (regex `^agents/\d{4}-\d{2}-\d{2}-[A-Za-z0-9._-]+$`) **and**
  Status = `New` get a rendered page body, sourced from the canonical repo clone at
  `~/dev/Obsidian_AI_Operating_System` (module-level constant, patchable in tests like
  `INBOX_DIR`).
- Body shape mirrors the inbox-file bodies (same `notion_markdown` converter, same
  crash-safety contract — sentinel is the LAST block, partial bodies are cleared and
  rewritten, writes go through the existing 100-block batching):
  1. provenance paragraph: "Source: branch `<branch>` of Obsidian_AI_Operating_System —
     view compare on GitHub (private repo; the primary documents are below)." The link is
     the row's existing Box Link URL when set, else
     `https://github.com/Dave1524/Obsidian_AI_Operating_System/compare/main...<branch>`;
  2. divider, then a "Changes in this proposal" heading + one bulleted item per line of
     `git diff --stat origin/main...<ref>`;
  3. divider, then for each markdown file **added** by the branch
     (`git diff --name-status --diff-filter=A origin/main...<ref>`, `*.md` only): an H1
     carrying the file path (code annotation) followed by
     `notion_markdown.blocks_from_markdown(git show <ref>:<path>)` and a divider;
  4. the sentinel paragraph.
- **Idempotency keys on the branch tip.** The sentinel's filename slot carries
  `<branch>@<12-char-tip-sha>`, reusing the existing sentinel format and `SENTINEL_RE`
  unchanged. Unmoved tip + current `FORMAT_VERSION` → skipped (one children GET, no
  writes). A moved tip or a converter bump re-renders.
- **Git access is best-effort and can never fail the run.** One
  `git fetch origin '+refs/heads/agents/*:refs/remotes/origin/agents/*'` per run, only
  when at least one qualifying row exists, with `GIT_TERMINAL_PROMPT=0` and a subprocess
  timeout; on fetch failure fall back to the existing local `origin/<branch>` ref. A branch
  with no resolvable ref prints a `!`-prefixed report line naming the branch and is
  skipped — never a crash, never `sys.exit` (the unattended unit must still sync inbox
  files when the canonical remote is unreachable; the box holds no guaranteed canonical
  credential).
- Branch rows' **properties are never written** — body only. Status lifecycle stays manual.
- New/branch rows with Status=New appear in the lifecycle report's "Pending review" /
  `[new]` sections (title from the row's Proposal property, date from Proposal Date) —
  today a New branch row is invisible in "ACTION NEEDED FROM YOU" because the report
  only surfaces `status == New and on_git` (see `main()`'s report loop).
- Report lines: branch bodies join the existing `bodies written this run` counters, plus
  one line per branch naming the outcome (`written`/`repaired`).
- `--dry-run` reports what would be written, writes nothing (including no fetch is fine
  to skip or keep — but no Notion writes). `--count` stays read-only, cheap, and free of
  any git subprocess (it is called frequently by `inbox_backlog_alert.sh` and
  `praetorium-status.sh`).
- `bash bin/verify.sh` green.

## Files to modify

- `bin/agent_inbox_notion_sync.py` — qualify branch rows after the CREATE/backfill passes;
  add the canonical-repo constant and branch-row loop; extend the lifecycle report per
  above. Reuse `write_body`/`batches`/`has_sentinel` — the body-composition and git-reading
  logic itself should NOT grow this file (see next section).

## Files to create

- `bin/agent_inbox_branch_rows.py` — sibling module owning the git side and the branch body
  composition: branch-name predicate, ref resolution + best-effort fetch, diff-stat and
  added-docs extraction, block assembly (provenance/changes/docs). No Notion I/O in this
  module — the sync passes its `call` in, or receives blocks back; keep the seam so tests
  can exercise composition against a temp git repo without any HTTP.
- `tests/test_agent_inbox_branch_rows.py` — offline behaviour test, same idiom as
  `tests/test_agent_inbox_body_sync.py` (importlib module load, `check()` harness,
  FakeNotion patched over `sync.api`, constants patched by attribute assignment). Build a
  real temp git repo fixture: `main` plus one `agents/<date>-<slug>` branch adding a
  markdown doc, with `origin/*` refs (clone or `git update-ref`).
- `tests/test_agent_inbox_branch_rows.sh` — driver so `bin/verify.sh` picks it up
  (`tests/*.sh` is the gate's discovery rule), mirroring
  `tests/test_agent_inbox_body_sync.sh`.

## Test plan

- **Render**: a New branch row + a resolvable branch with one added `.md` → body written;
  first block is the provenance paragraph, a diff-stat bullet list is present, the added
  doc's content is rendered, last block is a sentinel matching `SENTINEL_RE` whose
  filename slot is `<branch>@<sha12>`.
- **Idempotency**: second run with unmoved tip → `skipped`, zero DELETE/PATCH calls.
- **Tip move**: commit to the branch, run again → body re-rendered (old children deleted).
- **Repair**: pre-seed children without a sentinel → cleared and rewritten, outcome
  `repaired`.
- **Decided rows untouched**: a branch row with Status=Promoted/Rejected/Approved gets no
  children GET beyond the row query and no writes.
- **Unresolvable ref**: branch row naming a branch absent from the fixture repo → run
  completes, `!` report line, no crash, inbox-file sync still executed.
- **Report**: New branch row shows under "Pending review"; body counters include the
  branch body.
- **`--count` isolation**: `--count` performs no git subprocess (assert via patched
  subprocess seam or by pointing the canonical constant at a nonexistent path).
- **`--dry-run`**: no Notion writes recorded by FakeNotion.

## Out of scope / do not touch

- Status lifecycle for branch rows (REFLECT/approvals.tsv/Processed At) — stays manual;
  approvals.tsv slugs are inbox filenames and do not name branches.
- Creating branch rows. Registration stays a human/interactive act; this mode only renders
  bodies for rows that exist.
- Modified-file diffs in the body. Only **added** `.md` docs render in full; modified files
  appear in the diff-stat list only.
- `bin/agent_inbox_apply.py`, the timer/unit files, and the deployed tree
  (`~/agent-workforce`) — the unit's ExecStart runs the **source** checkout
  (`/home/dave/dev/agent-workforce/bin/agent_inbox_pipeline.sh`), so no deploy step is
  required for this to go live. Do not "fix" the stale deployed copy in this brief.
- The hand-backfill script (session scratchpad) — superseded by this feature, nothing to
  port.

## Notes / preconditions

- The two existing branch rows (page ids `3cd8d768-1ede-816b-8dcf-d862e0a85365`,
  `3cd8d768-1ede-8179-b2ef-d2351814705a`) already carry hand-written bodies whose sentinel
  filename slot is the bare branch name (no `@sha`). The new mode will see a sentinel
  mismatch and re-render each **once** — expected and desired (uniform sentinel identity).
- `sentinel_text()` / `SENTINEL_RE` need no change: the sha rides inside the filename slot
  (`(.+)` already matches it).
- `origin/main...<ref>` (three-dot) is the correct diff base; a fully-merged branch yields
  an empty diff — render provenance + an explanatory line rather than skipping, so the row
  still self-describes.
- `all_rows()` already returns every row each run; qualifying costs no extra queries. The
  per-run steady-state cost is one children GET per New branch row (sentinel check).
- Notion API errors go through the existing `api()` which `sys.exit`s — acceptable
  (matches inbox-file behaviour); only **git** failures must be non-fatal.
- The 15-min auto-sync timer sweeps dirty trees into generic commits — commit with a real
  message immediately after each green step.
