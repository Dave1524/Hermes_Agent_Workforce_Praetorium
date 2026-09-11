# Brief: T3.3 — Skill invocation telemetry: per run, which pointer skills were read
**Date:** 2026-09-11   **Verify:** `bash bin/verify.sh` from the repo root, after `bin/deploy` (this task edits `bin/`, so the drift gate is red on the branch until the deployed tree matches — see Notes)
**Notion:** [T3.3 — Skill invocation telemetry](https://app.notion.com/p/3d48d7681ede813f8c33e44bdc52fbf5) (card `3d48d768-1ede-813f-8c33-e44bdc52fbf5`, Status **Blocked** by T3.2, size S)
**Isolation:** `branch` — `feat/t3-3-skill-invocation-telemetry` off `main`, **after T3.2 merges** (see Preconditions). Not `current.md`: that file belonged to T7.2 (in flight in the shared checkout) when this was written.

Source of scope: `docs/dev-plan-2026-09.md:240-242` — "Invocation telemetry: per run, which pointer
skills were read, from run-log or transcript evidence, summarised by the scorecard. Gate: one week
of runs yields a per-skill count." The card's `Blocked By` is T3.2 (`3d48d768-1ede-8131-9758-d4cb9808ac1e`,
In Progress, worktree `.claude/worktrees/t3-2-skills`, branch `feat/t3-2-skills-field-joined`).

**Definition — decided here, not open.** A pointer skill was *read* by a run when the run's Claude
Code transcript shows either (a) a `Skill` tool call naming it, `praetorium-<owner>:<name>`, or
(b) a `Read` of its `SKILL.md` — the canonical `08_skills/<name>/SKILL.md` in the vault or the
pointer file itself under `skills/<owner>/skills/<name>/SKILL.md`. (a) is the pointer loaded;
(b) is the pointer followed (the pointer text says "Read the canonical file before acting"). Both
count, as one set per run. The transcript is the evidence, **located by session id**, never by
mtime: `bin/agent_propose.sh` mints the id per attempt and every Claude runner passes it as
`--session-id`. The record is one appended `cost.log` field set; the scorecard rolls it up.
**Nothing here reads the T3.2 manifest field** — offers are taken from the transcript's own
`skill_listing` record, so the digest shows offered-vs-invoked from live evidence and T3.2's
declaration can be cross-checked against it rather than assumed by it.

**Proven live 2026-09-11 (claude 2.1.268, `/home/linuxbrew/.linuxbrew/bin/claude`), two headless
haiku runs from `~/.claude/jobs/340fb085/tmp`, transcripts under
`~/.claude/projects/-home-dave--claude-jobs-340fb085-tmp/`:**
- `claude -p … --session-id 4c351116-7248-4b1e-9995-207c4cd2e8a8` persisted exactly
  `<that-uuid>.jsonl`; the project slug is the cwd with `/` → `-`, so look the file up as
  `$HOME/.claude/projects/*/<uuid>.jsonl` and never compute the slug.
- Run `61dc71af-3496-403a-a834-d5e55e3b2ddc` used the **real runner shape** —
  `--permission-mode dontAsk --allowedTools "Bash,Read,Write,Glob,Grep"` (no `Skill` in the list)
  with `--plugin-dir ~/agent-workforce/skills/claudius` — and still invoked
  `praetorium-claudius:meeting-prep` **and then read `/home/dave/vault/08_skills/meeting-prep/SKILL.md`**.
  So the offer is invocable as deployed; a zero in the digest will be a real zero.
- Record shapes, verbatim keys (the extractor parses these; it must not grep):
  - offer: `{"type":"attachment","attachment":{"type":"skill_listing","isInitial":true,"skillCount":27,"names":["finish",…,"praetorium-claudius:investment-research","praetorium-claudius:meeting-prep","praetorium-claudius:prospect-research",…]},"sessionId":"…","cwd":"…","timestamp":"…"}`
  - invocation: `{"type":"assistant","message":{"role":"assistant","content":[{"type":"tool_use","name":"Skill","input":{"skill":"praetorium-claudius:meeting-prep"}}]}}`; its result arrives as a `user` record whose `content[]` carries `{"type":"tool_result","content":"Launching skill: praetorium-claudius:meeting-prep"}`
  - canonical read: `{"type":"tool_use","name":"Read","input":{"file_path":"/home/dave/vault/08_skills/meeting-prep/SKILL.md"}}` (`~/vault` is a symlink; match `/08_skills/([^/]+)/SKILL\.md$` and `/skills/[^/]+/skills/([^/]+)/SKILL\.md$` on the path, nothing else)
- **The trap:** 23 of the 85 transcripts in `~/.claude/projects/-home-dave-agent-worktrees-inbox/`
  contain the string `"name":"Skill"`, and **none of them is an invocation** — it is the `Skill`
  tool's own schema, snapshotted into every transcript. Measured across the last 30 scheduled runs
  (2026-09-04 → 09-11): zero `Skill` tool_use blocks, zero `SKILL.md` reads. A grep-shaped
  extractor would report 23 false invocations; parse `message.content[].type == "tool_use"`.

## Acceptance criteria

1. **Session id per attempt.** `bin/agent_propose.sh` exports `AGENT_SESSION_ID="$(uuidgen)"`
   inside the attempt loop (`:325-338`), before `bash -lc "$run_cmd"`, so a retry gets a fresh id
   and the record carries the id of the attempt whose outcome it records. Each of the nine Claude
   runners passes `--session-id "${AGENT_SESSION_ID:-$(uuidgen)}"` in its `exec "$CLAUDE_BIN" -p`
   block — a hand-run runner still gets a valid uuid and never fails on the unset variable.
   `uuidgen` is `/usr/bin/uuidgen` on the box.
2. **Extractor.** New `bin/skill_telemetry.py` (python3, stdlib only, fail-loud): usage
   `skill_telemetry.py <transcript.jsonl> [--namespace praetorium-]`; prints exactly one line
   `offered=<csv|none> invoked=<csv|none> read=<csv|none>` where each csv is sorted, unique,
   unqualified pointer names (`meeting-prep`, not `praetorium-claudius:meeting-prep`), comma-joined
   with no spaces. `offered` = union over every `attachment.type == "skill_listing"` record of the
   `names` whose prefix matches `<namespace>[^:]*:`; `invoked` = `Skill` tool_use whose `input.skill`
   matches the same prefix; `read` = `Read` tool_use whose `input.file_path` matches either
   SKILL.md regex above. Blank or unparseable lines are skipped; a missing file exits 2 with a
   message on stderr; any other exception exits 1. No filesystem access besides the transcript.
3. **`cost.log` gains three keys**, appended to the existing `printf` in `log_cost()`
   (`bin/agent_propose.sh:99-101`), `schema=3` unchanged — the parser is key-based
   (`bin/scorecard.sh:36-45`, `bin/deliver_proposal.sh:42` `field`) and nothing in `bin/` branches
   on the schema value (grepped 2026-09-11):
   - `skills=<csv|none|unknown>` = sorted(invoked ∪ read)
   - `skills_offered=<csv|none|unknown>`
   - `skills_src=transcript|none`
   `unknown` ⇔ `skills_src=none` ⇔ no transcript was found for `AGENT_SESSION_ID` (BLOCKED and
   DEDUP records, the augustus/codex-acp path, a run whose `claude` never started, the smoke-test
   sandbox); `none` ⇔ transcript found and the list is empty. Lookup is the glob
   `$HOME/.claude/projects/*/$AGENT_SESSION_ID.jsonl`; the extractor is invoked as a sibling of the
   running script (`"$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/skill_telemetry.py"`, the
   `deliver_scorecard.sh:16` pattern) so the in-repo smoke test exercises the real path. Any
   extractor failure is fail-soft: `log "skills: telemetry failed (<reason>) — recording unknown"`
   and the three keys read `unknown unknown none`. On success one `log` line:
   `skills: offered=… invoked=… read=… src=transcript`. Names contain only `[a-z0-9-]`, so a
   comma-joined value survives the whitespace tokeniser at `scorecard.sh:39`.
4. **Scorecard.** `bin/scorecard.sh` counts, per pointer name and inside the same parse loop
   (`:29-96`, after the BLOCKED/DEDUP skip at `:52-58` so only real runs count, OPS included):
   runs that read it (7d / all-time) and runs that offered it (7d / all-time), using the existing
   `cutoff`/`ep` window (`:69`, `:82`); plus `unknown7d`/`unknown` = records with `skills_src=none`
   and `telemetry_records` = records carrying `skills=` at all. The digest (`:148-175`) gains
   - one Signal row after `Error runs (last 7d)`:
     `| Pointer skills read (last 7d) | <sum of 7d read-runs> run-read(s) across <k> skill(s); <n> of <runs7d> runs left no transcript evidence |`
   - a second table after the Signal table, before the legacy note:
     ```
     ## Pointer skills (T3.3)

     | Skill | Runs that read it (7d) | Runs that read it (all-time) | Runs offered it (7d) | Runs offered it (all-time) |
     |---|---|---|---|---|
     | <name> | … |          # one row per name seen in `skills=` or `skills_offered=`, sorted
     ```
     and, when `telemetry_records` is 0, the single line `_No skill telemetry recorded yet
     (records predate T3.3)._` instead of the table. A name that was read without being offered
     shows offered 0 — visible, not filtered. Idempotence (`:177-184`) and box-safety hold: names
     are the public `skills/` tree, the values are counts, no wall-clock field is added.
5. **Delivery.** `bin/deliver_scorecard.sh` `HEADLINE_ROWS` (`:20-26`) gains
   `'Pointer skills read (last 7d)'` so the Monday #ops rollup carries the number.
6. **Suites.** New `tests/test_skill_telemetry.sh`, claimed in `design/fleet-suites.toml` with
   `owner = "fleet"` and an anchored `asserts` list (template: the `test_pointer_skills.sh` entry,
   `:251-262`; W9 `asserts-anchored` is red until ids and anchors agree both ways). Ids:
   `telemetry-offer-from-listing`, `telemetry-invoked-from-skill-tool`,
   `telemetry-read-from-skill-md`, `telemetry-ignores-foreign-namespace`,
   `telemetry-schema-not-an-invocation`, `telemetry-missing-transcript-fails-loud`. Existing suites
   extended per the test plan. `bash bin/verify.sh` green after `bin/deploy`.
7. **Docs.** `docs/runbook.md:490-505` "Agent-run metrics & scorecard" block: replace the stale
   `schema=2` example with the live `schema=3` line plus the three keys and their vocabulary.
   `design/contracts/scorecard.md` § Outputs: the dated artifact now carries the per-skill table and
   the headline rows list the new row; one dated line, contract version stays 1 (the checks are
   unchanged). `design/agent-model.md:158` § "Skills are two mechanisms": a dated line saying
   invocation is now measured per run in `cost.log` and rolled up weekly, and where. `skills/README.md`:
   one line after the allocation table pointing at the digest for invocation counts.
   `docs/dev-plan-2026-09.md`: T3.3 row `:240-242` gains a `**DEPLOYED <date>, <sha>.**` paragraph
   in T3.1's style (`:230`) naming the calendar half of the gate (below); execution-order item 8
   (`:601`) and the "Startable today" line (`:606`) drop T3.3 / gain the next item.
8. **The gate has two halves; only the first closes at merge.** Repo half: verify green after
   deploy, with synthetic evidence proving counts. Calendar half (the card's wording): the first
   Monday digest produced after **seven days of scheduled runs on the deployed code** shows a row
   per offered skill with a count — which can only start once the fleet is un-paused
   (`~/OUTBOX/fleet-pause-2026-09-11.md`: all 24 system timers stopped and disabled since
   2026-09-11 12:05 CEST; Dave's call, not this task's). Record the deploy date in the dev-plan
   paragraph; set the Notion card to Done only when the digest excerpt is pasted under it. Until
   then "In Progress — deployed <date>, week starts at fleet resume".

## Files to modify

- `bin/agent_propose.sh` — `log_cost()` (`:71-102`): compute `skills`/`skills_offered`/`skills_src`
  from `AGENT_SESSION_ID` via the sibling extractor, fail-soft, and append the three keys to the
  `printf` at `:99-101`. Attempt loop (`:325-338`): `export AGENT_SESSION_ID="$(uuidgen)"` per
  iteration, before `bash -lc "$run_cmd"`; `log "run attempt … session=$AGENT_SESSION_ID"` so the
  id is in `agent_propose.log` next to the attempt. BLOCKED path (`:117-124`) calls `log_cost` with
  no session — it must read `skills=unknown skills_offered=unknown skills_src=none` without
  touching the extractor.
- `bin/run_m1_signal_scan_cc.sh:38`, `bin/run_bd_followup_drafts_cc.sh:42`, `bin/run_raw_ingest_cc.sh:42`,
  `bin/run_standing_research_cc.sh:48`, `bin/run_knowledge_digest_cc.sh:41`, `bin/run_bd_stall_radar_cc.sh:33`,
  `bin/run_overnight_morning_report_cc.sh:47`, `bin/run_daily_rhythm_cc.sh:52`,
  `bin/run_weekly_pre_assembly_cc.sh:47` — one continuation line
  `--session-id "${AGENT_SESSION_ID:-$(uuidgen)}" \` in the `exec "$CLAUDE_BIN" -p` block, placed
  after `--plugin-dir` and before `--allowedTools` in all nine (same shape in every file; the
  `runner-offers-owner-tree` and `runner-skills-guard` checks in `tests/test_pointer_skills.sh`
  read `--plugin-dir` and the guard line and are unaffected).
- `bin/scorecard.sh` — the four associative arrays and the `unknown`/`telemetry_records`
  counters in the parse loop (`:29-96`); the Signal row and the `## Pointer skills (T3.3)` table
  in the digest block (`:148-175`); header comment gains one line naming the new fields.
- `bin/deliver_scorecard.sh:20-26` — the new headline label.
- `tests/test_agent_propose_smoke.sh` — mock runner heredoc (`:35-43`) records `$AGENT_SESSION_ID` to
  `$home/session_ids.log` and, on `MOCK_WRITE_TRANSCRIPT=1`, writes the fixture transcript to
  `$home/.claude/projects/fixture/$AGENT_SESSION_ID.jsonl`; new scenario + asserts (test plan).
- `tests/test_scorecard.sh` — a fixture with the three keys; asserts on both tables (test plan).
- `tests/test_buzz_adapters.sh:166-187` — fixture digest gains the `Pointer skills read (last 7d)`
  row; one assert that it is carried.
- `design/fleet-suites.toml` — the `[[suite]]` entry for the new file (§6).
- `docs/runbook.md`, `design/contracts/scorecard.md`, `design/agent-model.md`, `skills/README.md`,
  `docs/dev-plan-2026-09.md` — §7.

## Files to create

- `bin/skill_telemetry.py` — the extractor (§2). One concept: transcript in, three name sets out.
  Executable, `#!/usr/bin/env python3`, no third-party imports, ~80 lines.
- `tests/test_skill_telemetry.sh` — fixtures written inline with heredocs in the **exact record
  shapes above** (one line per record; include a `"name":"Skill"` tool-schema line and a
  `shared:codex` invocation as negatives). Uses the repo `assert()` with the `yes | grep -q y`
  canary (CLAUDE.md § Verification). Scenarios: (a) listing + `Skill` invoke + canonical `Read` →
  `offered=investment-research,meeting-prep,prospect-research invoked=meeting-prep read=meeting-prep`;
  (b) listing only → `invoked=none read=none`; (c) `shared:codex` invoke and a `Read` of
  `/home/dave/vault/08_skills/meeting-prep/references/x.md` are ignored; (d) the schema line alone
  yields `invoked=none`; (e) a pointer-file read `…/skills/claudius/skills/meeting-prep/SKILL.md`
  counts as `read`; (f) duplicates collapse and output is sorted; (g) a missing path exits 2 and
  prints to stderr; (h) blank and malformed lines do not abort.

## Test plan

- `bash tests/test_skill_telemetry.sh` — the eight scenarios; every id in §6 anchored as
  `# (::<id>)` on its group's opening line.
- `bash tests/test_agent_propose_smoke.sh` — new scenario `MOCK_WRITE_TRANSCRIPT=1`: cost.log
  carries `skills=meeting-prep skills_offered=investment-research,meeting-prep,prospect-research
  skills_src=transcript`; `session_ids.log` holds one valid uuid. Existing NOPROPOSAL scenario
  additionally asserts `skills=unknown` and `skills_src=none` (sandbox has no transcript). The
  retry scenario (`MOCK_EXIT_CODE=1`, three attempts) asserts three **distinct** uuids in
  `session_ids.log`. BLOCKED scenario (`:180-182`) asserts `skills_src=none`. The line-125
  `schema=3` assert stays.
- `bash tests/test_scorecard.sh` — fixture: two records with `skills=meeting-prep
  skills_offered=investment-research,meeting-prep,prospect-research skills_src=transcript` (one
  inside 7d via `date -d '1 day ago'`, one dated 2026-07-13), one `skills=none skills_offered=…`
  record, one `skills=unknown skills_offered=unknown skills_src=none` record, one BLOCKED record
  carrying the keys (must not count). Assert: `meeting-prep` row `1 | 2 | 2 | 3`;
  `investment-research` row `0 | 0 | 2 | 3`; the Signal row reads `1 run-read(s) across 1 skill(s);
  1 of … runs left no transcript evidence`; a legacy-only cost.log prints the "No skill telemetry
  recorded yet" line; running twice leaves the digest byte-identical (`cmp`).
- `bash tests/test_buzz_adapters.sh` — the new headline row is carried into the #ops message.
- `python3 tests/test_workflow_coverage.py` — runner-join lines (`model-alias`, `runner-tools`,
  `runner-mcp`, `runner-join-counted`) byte-identical before and after the nine runner edits
  (`--session-id` is not a joined flag; diff the report to prove the parser did not choke on
  `$(uuidgen)`); `no-orphan-suite` green with the new suite claimed.
- `bash tests/test_pointer_skills.sh` — unchanged and green.
- shellcheck error-severity clean on the nine runners and `agent_propose.sh` (verify runs it).
- `bin/check_deploy_drift.sh` green after `bin/deploy`; then the full `bash bin/verify.sh`.
- Hand check, once, after deploy and fleet resume: the first scheduled run's `cost.log` line
  carries `skills_src=transcript`, and `ls ~/.claude/projects/*/<its AGENT_SESSION_ID>.jsonl`
  resolves — that is the link the whole task rests on.

## Out of scope / do not touch

- **T3.2's files** — `design/agents/*.toml`, `tests/test_workflow_coverage.py` skills join,
  `profiles/augustus_content_task.md`. This task reads nothing from the manifest `skills` field.
- **`bin/run_content_via_buzz.sh`, `bin/content_change_dispatch.sh`, `bin/content_moved.sh`** —
  modified in the shared checkout by T7.2 (in flight 2026-09-11). Augustus runs on codex-acp via
  Buzz and leaves no Claude transcript; they record `skills_src=none`, honestly. Recording
  heading-extraction as `skills_src=extraction` (read by construction, every run) is a follow-up.
- The five `buzz-agent@*` interactive sessions and trajan's platform timers — no `--plugin-dir`,
  nothing to measure.
- `--output-format`, the attempt log's content, `AGENT_VERIFY_CMD` and `deliver_proposal.sh`'s
  sentinel reads — the runner's stdout shape is unchanged.
- Transcript retention (`cleanupPeriodDays`) — the extractor runs at `log_cost` time, seconds after
  the run; `cost.log` is the durable record and the transcript may go.
- **The user-scope plugin leak**: every headless run is offered 27 skills including `finish`,
  `implement`, `plan-feature`, `ship` and `shared:*` from `~/.claude` plugins, not just the three
  pointers. Observed in every transcript checked; it is why the extractor filters on the namespace.
  A defect for its own card, not this one.
- `[surfaces.kanban] skills = 25` in the manifests — different key, retired surface.
- `~/.config/*`, the vault, Notion card prose. Setting the card's Status is a post-push courtesy
  (`notion_update_page` over `/run/user/1000/buzz-notion.sock`), not part of the gate.

## Notes / preconditions

- **Start after T3.2 merges** and branch from `main`. Mechanically T3.3 does not depend on T3.2
  (offers come from transcripts), but both touch `docs/dev-plan-2026-09.md`, `design/agent-model.md`
  and `skills/README.md`; the plan's execution order (`:601`) is "T3.2, then T3.3"; and the card is
  marked Blocked. On 2026-09-11 13:40 the T3.2 worktree was at `ed024bb` with no commits of its own.
- Repo state when written: `main` = `ed024bb`; the shared checkout was on
  `debug/t7-2-augustus-content-dispatch-reliability` with seven modified files and `current.md`
  owned by T7.2 — hence this brief lives only under its own name, on branch
  `docs/t3-3-skill-invocation-telemetry-brief`. Copy it to `current.md` when picking it up.
- The fleet is paused (all `buzz-agent@*` units and 24 system timers stopped + disabled,
  `~/OUTBOX/fleet-pause-2026-09-11.md`). Deploying is safe while paused; the week clock starts
  when Dave resumes.
- `~/.claude/projects/-home-dave-agent-worktrees-inbox/` holds the claudius runners' transcripts
  (cwd `$INBOX`); the marcus runners `cd "$WORKDIR"` (`run_daily_rhythm_cc.sh:45`,
  `run_overnight_morning_report_cc.sh:40`) so theirs land under another slug — the glob across
  `projects/*/` is what makes the lookup owner-agnostic.
- Transcripts are `-rw-------` owned by dave, same user as the timers; no permission work.
- `bin/agent_propose.sh` has no `BIN_DIR`; `refresh_scorecard` (`:104-113`) deliberately calls the
  **deployed** `$HOME/agent-workforce/bin/scorecard.sh`. The extractor is called sibling-relative
  instead so the smoke test's sandboxed `$HOME` still reaches it; say so in the comment.
- `log_cost` is also called from the BLOCKED path before any attempt ran, so `AGENT_SESSION_ID`
  must be treated as optional there.
- Definition of done per `docs/dev-plan-2026-09.md`: brief before code (this file), verify green,
  `bin/deploy` run, committed and pushed by hand. Order: edit → `bin/deploy --dry-run` →
  `bin/deploy` → `bash bin/verify.sh` → commit → push.
