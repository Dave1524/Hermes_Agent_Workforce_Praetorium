# Brief: qmd / vault convergence fixes (Aurelian review follow-up)
**Date:** 2026-08-13   **Verify:** `bash bin/verify.sh` (from `~/dev/agent-workforce`), plus the per-item commands under **Test plan** — most items land outside this repo and the gate cannot see them.

## Provenance and one correction you must read first

These items come from Aurelian's box-side review of the vault-convergence criteria
(`~/OUTBOX/vault-convergence-criteria.md`, run 2026-08-13, verdict event `5ad20c8d`). Four of his
claims were independently re-verified before this brief was written; all four held exactly, including
line numbers and digests.

**One did not, and the brief supersedes it.** Aurelian's finding B3 said the eight MCP-disabled
runners "reach qmd not at all" while `bin/agent_propose.sh:201` "hard-blocks those same jobs on the
qmd daemon's health". Both halves are overstated:

1. `QMD_HEALTH_POLICY` defaults to **`warn`** (`bin/agent_propose.sh:197`). `grep -rn QMD_HEALTH_POLICY`
   across this repo *and* the deployed copy at `~/agent-workforce` finds it set nowhere else. Only a
   per-job override under `~/.config/agent-workforce/` (deny-listed, unreadable from an agent session)
   could set `block`. The hard-block path is **latent, not live** — no job is being blocked today.
2. The runners are not cut off from the vault. All four of the "zero qmd reference" jobs
   (`run_knowledge_digest_cc.sh:17`, `run_standing_research_cc.sh:16`, `run_raw_ingest_cc.sh:18`,
   `run_m1_signal_scan_cc.sh:12`) set `INBOX=$HOME/agent-worktrees/inbox` and `cd` into it before
   exec'ing `claude`. That directory **is a checkout of the vault** (`00_system/`, `01_identity/`,
   `03_projects/`, `05_knowledge/`, `06_resources/`, `08_skills/`). With `Read,Glob,Grep` on that cwd
   they read the vault directly. What they lack is *semantic retrieval* (`vec`/`hyde`), not access.

So F5 below is a small latent-trap fix, not the emergency B3 described. **Do not "restore retrieval"
to those eight runners** — MCP-disabling them was a deliberate toolset trim (2026-07-20) and
re-enabling it would re-inflate every prompt for jobs that work over a checked-out tree.

## Acceptance criteria

Done means all six hold, each proven by the command named in **Test plan** — not by inspection:

1. **F1** — `~/CLAUDE.md` contains no reference to `~/dev/vault-boxsafe`, and every project path it
   names resolves on disk.
2. **F2** — `/home/dave/agent-worktrees/inbox/.git` records a `gitdir:` that contains no symlinked
   path component, and `git -C /home/dave/agent-worktrees/inbox status` still succeeds.
3. **F3** — `/home/dave/.claude/jobs/95f52624/tmp/scratch/.qmd/` no longer exists, and a `qmd` CLI
   call made with cwd under `~/.claude/jobs/` resolves the global collection.
4. **F4** — `/home/dave/deploy-staging/config/qmd-index.yml` either matches the live config or is
   gone; it no longer advertises a superseded base as if it were promotable.
5. **F5** — the qmd/Brave health probes in `bin/agent_propose.sh` are skippable per job, the runners'
   `--strict-mcp-config` block carries a one-line reason, and `bash bin/verify.sh` is green.
6. **F6** — a written finding at `~/OUTBOX/qmd-doc-gap-2026-08-13.md` accounts for the 4-document
   delta (485 markdown files on disk vs 481 indexed), naming each missing file and why.

**State the degrade direction for every check you change.** This repo's `## Verification` block is
explicit that a check failing *closed* costs a rerun while one failing *open* has been certifying
nothing, and this repo has already shipped an overshooting fix on exactly that seam (the NUC-25
kanban wrapper, which made hard crashes print as benign declines with `exit 0`). Each item below
names its current direction; do not silently flip one.

## Files to modify

- `/home/dave/CLAUDE.md` — **F1.** Lines 16 and 30 route agents at `~/dev/vault-boxsafe/`, deleted
  2026-08-12 (`ls -ld` → no such file). Line 16 calls it "de-identified working copy of the vault
  (branch `agents`). See its `00_system/CLAUDE.md`"; line 30 contrasts it against `~/vault`. Rewrite
  both against the current layout as recorded in `~/dev/WORKSPACE.md:9-20`:
  `Obsidian_AI_Operating_System/` is the canonical clone (target state, single-repo decision);
  `obsidian-ai-os-boxsafe/` is the legacy box-safe mirror, still the live publish target and still
  what `~/vault` points at until cutover. Keep the "don't hand-edit `main` here" warning — it now
  applies to the boxsafe mirror. *Degrades open today:* an agent following line 16 to a nonexistent
  `00_system/CLAUDE.md` gets no project instructions and no error.
- `/home/dave/agent-worktrees/inbox/.git` — **F2.** Currently `gitdir: /home/dave/vault/.git/worktrees/inbox`.
  `~/vault` is a symlink to `~/dev/obsidian-ai-os-boxsafe`. Replace with the resolved path
  `gitdir: /home/dave/dev/obsidian-ai-os-boxsafe/.git/worktrees/inbox`. The reverse pointer
  (`~/dev/obsidian-ai-os-boxsafe/.git/worktrees/inbox/gitdir`) already holds an absolute real path and
  needs **no** change — verified. *Degrades closed at cutover:* repointing `~/vault` at the canonical
  repo breaks this worktree hard, because the canonical repo has no `.git/worktrees/` directory at
  all. Loud, but it takes `bin/agent_propose.sh` and the whole proposal pipeline with it.
- `bin/agent_propose.sh` — **F5.** The probes at lines 197-206 (`QMD_HEALTH_POLICY`,
  `BRAVE_HEALTH_POLICY`, both defaulting to `warn`) guard dependencies that eight of the eleven
  runners do not use. Add a per-job opt-out so a job that declares no retrieval need skips the probe
  entirely rather than logging a `WARN` about a daemon irrelevant to it. Keep `warn` as the default
  for jobs that *do* use qmd. **Do not make the default `block`** — that would convert an inert check
  into a fail-closed one across the fleet in a single commit. Preserve the existing
  `command -v … || return 0` early-returns in `qmd_healthy`/`brave_healthy`; they are what keeps the
  probe from failing closed on a box without `curl`/`ss`.
- `bin/run_knowledge_digest_cc.sh`, `bin/run_standing_research_cc.sh`, `bin/run_raw_ingest_cc.sh`,
  `bin/run_m1_signal_scan_cc.sh`, `bin/run_bd_followup_drafts_cc.sh`, `bin/run_daily_rhythm_cc.sh`,
  `bin/run_overnight_morning_report_cc.sh`, `bin/run_weekly_pre_assembly_cc.sh` — **F5.** Each carries
  `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` with no explanatory comment, which is why
  it reads as a regression to every reviewer who meets it. Add one line stating it is a deliberate
  toolset trim and that the job reaches the vault through its `cd "$INBOX"` cwd. This is the rare
  comment the standards allow — a non-inferable constraint, not a restatement of the code.
- `/home/dave/deploy-staging/config/qmd-index.yml` — **F4.** sha256 `66df263b…`, mtime 2026-07-06,
  byte-identical to the superseded base config while sitting in the staging tree that feeds the
  `qmd-mcp` unit. Nothing references it by path (`grep -rn 'qmd-index.yml'` over `bin/`, the repo
  `*.md`, `~/CLAUDE.md` and `~/dev/WORKSPACE.md` → zero hits). Either sync it to the live config or
  remove it; do not leave a promotable-looking file that promotes a stale base. While you are in
  there, the `10_archive/**` ignore rule is a no-op at the configured path (that folder exists only
  in the canonical tree) — leave it if you sync, since it is correct forward of cutover, but say so
  in the commit message.

## Files to create

- `~/OUTBOX/qmd-doc-gap-2026-08-13.md` — **F6.** The finding for the 485-on-disk vs 481-indexed
  delta. Must name the four files and the reason each is absent (ignore rule, size cap, parse
  failure, or symlink). `multi_get` is documented to skip files >10 KB, and the collection carries
  ignore globs — check both before concluding anything. If the cause is an ignore rule working as
  intended, say so and close it; a 4-document gap is only a bug if the documents were meant to be
  reachable.
- No test file. This repo's gate is a syntax + shellcheck sweep, not a unit suite (see below).

## Test plan

The repo gate is `bash bin/verify.sh` — bash syntax check plus error-severity shellcheck over every
script in `bin/`, plus any `tests/*.sh`. **It covers F5 only.** It cannot see F1-F4 or F6, which live
outside this repo. Each of those needs its own proof:

- **Gate (F5):** `bash bin/verify.sh` from the repo root, exit 0, shellcheck clean.
  Heed the repo's own pipefail warning: **never end a pipeline in an early-exiting reader while
  `pipefail` is on** — `grep -q`/`head` raise SIGPIPE 141. Each suite carries a `yes | grep -q y`
  canary for exactly this; if you add a check, add it inside an `assert()` (which scopes pipefail
  off) or restructure the pipeline.
- **F5 behavioural:** run `bin/agent_propose.sh` for one qmd-using job and one opted-out job with the
  daemon reachable, and confirm the opted-out job emits no qmd `WARN` line while the other still
  probes. Then assert **which branch ran** by grepping the log, not by exit code — a job that
  declines and a job that crashes can both exit 0 here.
- **F1:** `grep -c 'vault-boxsafe' ~/CLAUDE.md` → 0, then resolve every `~/dev/*` path the file names
  and confirm each exists.
- **F2:** `git -C /home/dave/agent-worktrees/inbox status --short` succeeds and
  `git -C /home/dave/agent-worktrees/inbox rev-parse --git-dir` returns a path under
  `~/dev/obsidian-ai-os-boxsafe`. Then re-run the check with `~/vault` temporarily unavailable to
  prove the symlink is no longer load-bearing — this is the whole point of the fix and the only test
  that actually exercises it.
- **F3:** `ls /home/dave/.claude/jobs/95f52624/tmp/scratch/.qmd/` → no such file, then run a `qmd`
  CLI query with cwd `/home/dave/.claude/jobs/` and confirm it reports the global collection's
  document count, not a scratch index's. Pass cwd explicitly — the CLI prefers a local `.qmd/index.yml`
  over the global one (`dist/collections.js:74-85`), which is the entire failure mode being removed.
- **F4:** `sha256sum` the staging file against the live config, or confirm its absence.
- **F6:** the finding file exists and names four specific paths, each with a cause. "Probably ignore
  rules" is not an answer.

## Out of scope / do not touch

- **`vault/`, `~/dev/obsidian-ai-os-boxsafe/` content, and `agent-worktrees/inbox/` document content.**
  F2 rewrites one git metadata file inside the worktree; it changes no vault document. Vault content
  is governed by its own `CLAUDE.md` and is out of scope for this repo per `~/CLAUDE.md`.
- **The de-identification question.** Run 1 of the review produced blob-OID evidence that 474 of 482
  shared paths in the box-safe mirror are byte-identical to the canonical vault, which sits badly
  against the "de-identified mirror" description in `~/CLAUDE.md`, `WORKSPACE.md` and the qmd server
  instructions. That is a content-policy finding for Dave, not a coding task. **Do not edit the
  mirror, do not re-run a de-identification pass, do not soften the wording to match.** Report only.
- `~/.config/agent-workforce/`, `~/.config/buzz-agents/`, `~/.ssh/` — deny-listed credentials. The
  per-job `.env` overrides that could set `QMD_HEALTH_POLICY=block` live there; F5 must work without
  reading them.
- **Do not re-enable MCP on the eight trimmed runners.** See the correction above.
- `~/.claude/settings.json`, the `buzz-agent@*` units, and any relay/identity operation. No keypairs,
  no relay registrations.
- The `check-loaded.sh:41` arithmetic bug — deny-listed path, Dave must fix it.

## Notes / preconditions

- Repo `~/dev/agent-workforce` at HEAD `a9f50ba`, working tree clean at brief time.
- **Commit immediately after editing.** A 15-minute auto-sync timer runs `git add -A` + commit + push
  to `origin/main`; anything uncommitted gets swept into a generic "Auto-sync" commit with unrelated
  WIP riding along. `git fetch origin` and diff the checked-out branch against `origin/main` before
  committing — local checkouts here can be silently merged-and-stale.
- **Nothing deploys automatically.** Editing `bin/*.sh` in this repo leaves systemd running the old
  code at `~/agent-workforce`. Deploy with `bin/deploy` (rsync + atomic rename, additive; `--dry-run`
  and `--prune` available) — never a manual `cp`. The deployed copy can carry uncommitted drift, so
  diff before deploying.
- F3 deletes a directory this agent workforce created as scratch litter on 2026-08-11
  (`index.yml` 360 B + `index.sqlite` 5.5 MB). It is not a user artifact. Look at it before removing
  it anyway.
- F2's forward pointer is the only symlinked one; the reverse pointer at
  `~/dev/obsidian-ai-os-boxsafe/.git/worktrees/inbox/gitdir` already reads
  `/home/dave/agent-worktrees/inbox/.git` — verified 2026-08-13, leave it alone.
- Runner MCP inventory, verified: MCP-disabled (8) — `run_bd_followup_drafts_cc.sh`,
  `run_daily_rhythm_cc.sh`, `run_knowledge_digest_cc.sh`, `run_m1_signal_scan_cc.sh`,
  `run_overnight_morning_report_cc.sh`, `run_raw_ingest_cc.sh`, `run_standing_research_cc.sh`,
  `run_weekly_pre_assembly_cc.sh`. Inherit `~/.claude.json` (3) — `run_daily_plan_cc.sh`,
  `run_eod_summary_cc.sh`, `run_content_via_buzz.sh`.
- qmd config propagation is **config → database → server**, not config → process: `qmd update` writes
  `global_context` into the index's `store_config` table, and the MCP server rebuilds instructions
  per session inside `createMcpServer`. So the usual mtime-vs-`ExecMainStartTimestamp` staleness test
  is a **false-FAIL generator for qmd specifically** — do not use it to judge whether a config edit
  took. Query the running daemon instead.
- Long-lived MCP *clients* cache server instructions from the initialize handshake, so an already-open
  session can report an older document count and older instruction text than the daemon serves. Judge
  by a fresh probe, never by what a running session's tool description says.
- The review that produced these items was **not deterministic across two byte-identical runs**: the
  verdict matched but one criterion flipped MET→NOT MET, one reason changed, and each run found a
  *different* stale config (run 1 the `deploy-staging` one, run 2 the `.claude/jobs` one) — both real,
  each run blind to the other. Treat this list as a floor, not a census. If you find a third shadow
  `.qmd/` while working, fix it and say so.
