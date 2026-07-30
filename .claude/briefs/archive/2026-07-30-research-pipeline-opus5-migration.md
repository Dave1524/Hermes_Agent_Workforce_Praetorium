# Brief: Research pipeline — Opus 5 migration + raw-ingest, contradiction-flagging, knowledge digest
**Date:** 2026-07-30   **Verify:** `bash bin/verify.sh` (from `~/dev/agent-workforce`)

## Why this exists (confirmed state, not assumption)

The standing research run is **hard-down and reporting success-shaped silence**.

`agent-proposal.timer` (Mon–Fri 04:30) → `bin/agent_propose.sh` → `bin/kanban_run_and_wait.sh`
→ claudius on `anthropic/claude-sonnet-5` via OpenRouter. Evidence:

- `~/agent-workforce/logs/cost.log`: last `task=standing outcome=PROPOSAL` was **2026-07-20**.
  Since then 8 consecutive `outcome=NOPROPOSAL memory=fallback` runs (07-21,22,23,24,27,28,29,30).
- `~/.hermes/profiles/claudius/logs/errors.log`: **6 × HTTP 402 `Insufficient credits`
  (`limit_source: openrouter_credits`) per run**, on exactly those dates and none on
  07-16/17/20 when it last produced. OpenRouter usage $42.11 against the $50/mo cap;
  the reserve-worst-case-`max_tokens` trap fires on the big research job while cheap jobs pass.
- `bin/agent_propose.sh:255` `PROVIDER_ERROR_RE` is `^`-anchored and scans only the last
  `AGENT_ERROR_TAIL_LINES` (5) of the attempt's **stdout**. The 402 goes to the hermes profile's
  own `errors.log`, never into `attempt_out`, so `run_ended_on_provider_error()` cannot see it
  on the kanban path. `AGENT_VERIFY_CMD` is unset for this job. Result: a credit-blocked run
  logs `OK: run completed, agent produced no proposal`.

Ten days of a dead research job reading as a clean decline. `bd-stall-radar` survives (it is a
`$0` Python kernel); `m1-signal-scan` and `weekly-pre-assembly` survive because they migrated to
headless Claude Code on 2026-07-24 — that migration is the proven template this brief follows.

## Acceptance criteria

1. **The standing research run executes on headless Claude Code pinned to Opus 5**, not
   hermes/claudius on OpenRouter. `agent-proposal.service` carries an `AGENT_JOB_OVERRIDES`
   pointing at a `standing_research.env` whose `AGENT_RUNTIME_CMD` is
   `bin/run_standing_research_cc.sh`, and no `hermes` invocation survives in the active wiring.
2. **A failed run can never again be logged as a clean decline.** All three CC research jobs set
   `AGENT_VERIFY_CMD` to `bin/proposal_or_decline.sh <slug>`, which passes only when EITHER the
   dated proposal file exists and is newer than `AGENT_RUN_STARTED_AT`, OR the run log tail
   carries an explicit `DECLINE:` sentinel the task profile emits on a deliberate no-proposal.
   A run that dies produces neither → `agent_propose.sh:286` records FAIL, not NOPROPOSAL.
3. **Mechanism A — ingest-time contradiction flagging.** Every research/ingest task profile
   instructs: when a new source contradicts an existing `05_knowledge/` claim, never silently
   supersede it — name both sides, cite both sources, and flag it in the proposal under a
   dedicated `## Contradictions` section. Today this only exists weekly, as
   `weekly_pre_assembly_cc_task.md`'s "flag, do not fix" line.
4. **Mechanism B — box-side raw ingestion.** A scheduled job diffs `~/vault/05_knowledge/raw/`
   against `~/vault/00_system/ingest_log.md` and, for sources present in `raw/` but absent from
   the log, emits ONE proposal containing the distillation, the `source:`/`updates:` frontmatter
   required by `00_system/update_protocol.md` § Source Ingestion, the `ingest_log.md` line to
   append, and any contradictions found. Nothing watches that folder today — ingestion is
   entirely Mac-side interactive.
5. **Mechanism C — 7-day knowledge digest.** A weekly job reports what the *knowledge base*
   learned in the last 7 days (git-log delta over `~/vault/05_knowledge/` and `11_entities/`),
   distinct from the existing *activity* digest (`weekly-pre-assembly`, daily-logs/Notion/
   open-loops driven). Under 500 words, pointers into notes rather than a re-summary, plus
   contradictions flagged this week, plus open questions added to `04_operations/open_loops.md`.
6. **All three are scheduled** and survive a reboot (`Persistent=true`), on a timer grid that
   does not collide with the existing units.
7. **`bash bin/verify.sh` is green** — `bash -n` + `shellcheck -S error` clean over every new
   script, and the four new `tests/*.sh` pass.

## Files to create

**Standing research (job 1 — replaces the claudius/OpenRouter path)**
- `bin/run_standing_research_cc.sh` — clone `bin/run_m1_signal_scan_cc.sh` exactly, changing:
  `TASK_FILE=$HOME/agent-workforce/profiles/standing_research_cc_task.md`, and
  `--model claude-opus-5` (pin the full name, not the `opus` alias — the alias silently rolls
  forward on the next model release; Dave asked for Opus 5 specifically). Keep
  `--permission-mode bypassPermissions --strict-mcp-config --mcp-config '{"mcpServers":{}}'`.
  `--allowedTools "Bash,Read,Write,Edit,Glob,Grep,WebSearch,WebFetch"` — this job does public
  web research, so unlike weekly-pre-assembly it keeps WebSearch/WebFetch.
- `profiles/standing_research_cc_task.md` — port `profiles/claudius_task.md` to the CC runtime
  using `profiles/m1_signal_scan_cc_task.md` as the structural model. Must carry over verbatim
  in substance: the `queue.md` → soonest-Deadline → standing-mission priority order; the
  `bin/published_corpus.py list|check` duplicate-title gate for website/blog items (exit 2 =
  already published → write a collision report, never the duplicate); FACT-vs-INFERENCE
  labelling; the one-proposal-per-run write boundary at `_inbox/agents/<RUN_DATE>_<slug>.md`;
  never-act-outward. Replaces the hermes-only bits: STEP 0 working memory (no hermes MEMORY
  store on the CC path — substitute reading `ls -1 _inbox/agents/` plus
  `_inbox/agents/_metrics/approvals.tsv` for what was already proposed) and STEP 5 (drop).
  Adds the **Mechanism A** contradiction block and the `DECLINE: <reason>` sentinel contract.
- `profiles/standing_research.env.example` — mirror `profiles/m1_signal_scan.env.example`
  including its revert-comment block:
  `AGENT_PROFILE=claude-opus`, `AGENT_TASK_SLUG=standing-research`, `AGENT_MAX_ATTEMPTS=2`,
  `AGENT_RUNTIME_CMD='~/agent-workforce/bin/run_standing_research_cc.sh'`,
  `AGENT_VERIFY_CMD='~/agent-workforce/bin/proposal_or_decline.sh standing-research'`,
  and the commented-out prior claudius/kanban wiring for revert.

**Raw ingestion (job 2 — Mechanism B)**
- `bin/run_raw_ingest_cc.sh` — same CC runner shape, `--model claude-opus-5`. Pre-flight with
  `bin/vault_sync_guard.sh check` and **refuse loudly (non-zero, print `REFUSING`) on a stale or
  dirty mirror** — an ingest built off a frozen mirror is worse than no ingest. Follow the
  `run_weekly_pre_assembly_cc.sh` guard idiom so `tests/rhythm_test_lib.sh` fixtures apply.
  Honor `VAULT_DIR` / `VAULT_SYNC_GUARD` / `CLAUDE_BIN` env overrides for testability.
  `--allowedTools "Bash,Read,Write,Edit,Glob,Grep"` — no web tools; this job reads local sources.
- `profiles/raw_ingest_cc_task.md` — same-day idempotency check first (`ls -1 _inbox/agents/ |
  grep raw-ingest`). Compute unprocessed sources: every file under `~/vault/05_knowledge/raw/`
  (excluding `README.md`) whose basename does not appear in `~/vault/00_system/ingest_log.md`.
  If none, print `DECLINE: no unprocessed sources in 05_knowledge/raw/` and write nothing.
  Otherwise take the oldest unprocessed source and emit ONE proposal
  `_inbox/agents/<RUN_DATE>_raw-ingest.md` with sections: `## Task`, `## Source`,
  `## Distillation (proposed 05_knowledge/ file + exact content)` — carrying `source:` and
  `updates:` frontmatter per `00_system/update_protocol.md` § Source Ingestion —
  `## Existing notes checked` (name the `00_system/knowledge_index.md` entries consulted, so the
  extend-don't-duplicate check is auditable rather than asserted), `## Contradictions`,
  `## Proposed ingest_log.md line`, `## Confidence & gaps`. `target: vault`.
- `profiles/raw_ingest.env.example` — `AGENT_PROFILE=claude-opus`, `AGENT_TASK_SLUG=raw-ingest`,
  `AGENT_MAX_ATTEMPTS=2`, runtime + `AGENT_VERIFY_CMD` pointing at the pair above.
- `systemd/raw-ingest.service` — copy `systemd/m1-signal-scan.service`; `Description=Raw source
  ingestion (05_knowledge/raw → distillation proposal)`,
  `Environment=AGENT_JOB_OVERRIDES=/home/dave/.config/agent-workforce/raw_ingest.env`.
  Add `OnFailure=agent-alert@%n.service` (m1's unit omits it; the standing-research unit has it).
- `systemd/raw-ingest.timer` — `OnCalendar=Tue..Sat 03:00`, `RandomizedDelaySec=5min`,
  `Persistent=true`. **03:00 is deliberate**: ahead of the 04:30 standing-research run, so
  research sees freshly-ingested knowledge the same morning.

**Knowledge digest (job 3 — Mechanism C)**
- `bin/run_knowledge_digest_cc.sh` — same shape, `--model claude-opus-5`, same
  `vault_sync_guard.sh check` refusal, `--allowedTools "Bash,Read,Write,Edit,Glob,Grep"`.
- `profiles/knowledge_digest_cc_task.md` — same-day idempotency guard. Compute the delta with
  `git -C ~/vault log --since='7 days ago' --name-only --pretty=format: -- 05_knowledge/ 11_entities/`
  (exact deltas, not mtime). Emit `_inbox/agents/<RUN_DATE>_knowledge-digest.md`, **under 500
  words**, sections: `## Task`, `## Most significant additions (3–5, each linking the note)`,
  `## Contradictions flagged this week`, `## Open questions` (new entries in
  `04_operations/open_loops.md` this week that are still unresolved), `## Unusually active topic`
  (one line — a topic accumulating notes fast is worth deliberate attention),
  `## Confidence & gaps`. State in the header that this is the *knowledge* digest and does not
  replace `weekly-pre-assembly` (the *activity* pre-read). If the 7-day delta is empty, print
  `DECLINE: no 05_knowledge/ or 11_entities/ changes in the last 7 days` and write nothing.
- `profiles/knowledge_digest.env.example` — `AGENT_PROFILE=claude-opus`,
  `AGENT_TASK_SLUG=knowledge-digest`, `AGENT_MAX_ATTEMPTS=2`, runtime + `AGENT_VERIFY_CMD`.
- `systemd/knowledge-digest.service` — as above,
  `Environment=AGENT_JOB_OVERRIDES=/home/dave/.config/agent-workforce/knowledge_digest.env`.
- `systemd/knowledge-digest.timer` — `OnCalendar=Sun 09:00`, `RandomizedDelaySec=5min`,
  `Persistent=true`. Sunday morning so it is waiting before Monday; clear of
  `weekly-pre-assembly` (Fri 22:00).

**Shared de-silencing helper**
- `bin/proposal_or_decline.sh` — `usage: proposal_or_decline.sh <slug>`. Exit 0 iff EITHER
  `$HOME/agent-worktrees/inbox/_inbox/agents/${RUN_DATE}_<slug>.md` exists and is
  `-newermt "@$AGENT_RUN_STARTED_AT"`, OR the tail of `$HOME/agent-workforce/logs/agent_run.log`
  (last `${AGENT_DECLINE_TAIL_LINES:-40}` lines) matches `^DECLINE:`. Else exit 1.
  Honor `AGENT_INBOX_DIR` / `AGENT_RUN_LOG` overrides for testability. Both `RUN_DATE` and
  `AGENT_RUN_STARTED_AT` are already exported by `agent_propose.sh` (lines 31, 264) — do not
  recompute them. Fail closed: a missing `AGENT_RUN_STARTED_AT` must exit 1, never 0.

**Tests** (co-located under `tests/`, sourcing `tests/rhythm_test_lib.sh` — helpers available:
`assert`, `env_value`, `make_vault_fixture`, `make_mock_claude`, `commit_at`, `smoke_suite`,
`$REPO_ROOT`, `$GUARD`, `$fail`). Offline by contract — mock `claude`, throwaway git fixtures,
never `~/vault`, never a real remote, never OpenRouter.
- `tests/test_standing_research_smoke.sh` — modelled on `tests/test_weekly_pre_assembly_smoke.sh`:
  env.example parses; `AGENT_PROFILE=claude-opus`; `AGENT_RUNTIME_CMD` resolves to an executable
  and points at `run_standing_research_cc.sh`; **`! grep -qE '^AGENT_RUNTIME_CMD=.*hermes'`**
  (the 402 fix); runner launches the mock claude with `--model claude-opus-5` and with
  `--strict-mcp-config` + empty `mcpServers`; task profile retains the `published_corpus.py`
  duplicate-title gate and the `## Contradictions` section; task profile emits the `DECLINE:`
  sentinel contract.
- `tests/test_raw_ingest_smoke.sh` — refuses (`REFUSING`, non-zero, mock claude never launched)
  on a `stale_behind` fixture; runs on `clean_current`; allowlist contains no `WebSearch|WebFetch`;
  task profile references both `05_knowledge/raw` and `00_system/ingest_log.md` (the
  unprocessed-source diff is the whole mechanism).
- `tests/test_knowledge_digest_smoke.sh` — same stale/current pair; task profile uses
  `git ... log --since` over `05_knowledge/` (not mtime); asserts the under-500-words instruction
  and the "does not replace weekly-pre-assembly" statement are present.
- `tests/test_proposal_or_decline.sh` — the four cases that matter, with a temp inbox + temp run
  log: (a) fresh dated proposal present → exit 0; (b) no proposal but `DECLINE:` in the log tail
  → exit 0; (c) neither → exit 1 (**this is the case that was silently passing for 10 days**);
  (d) a proposal file that predates `AGENT_RUN_STARTED_AT` → exit 1 (a stale artifact from an
  earlier run must not certify this one).

## Files to modify

- `systemd/agent-proposal.service` — add
  `Environment=AGENT_JOB_OVERRIDES=/home/dave/.config/agent-workforce/standing_research.env`
  above the existing `EnvironmentFile=`. Leave `agent-proposal.timer` (Mon–Fri 04:30) unchanged —
  the cadence is right; only the runtime moves. Update the `[Unit] Description` to name the
  Claude Code runtime.
- `CLAUDE.md` — extend the daily-rhythm section (or add a short "Research pipeline" section)
  naming the three jobs, their timers, and the one rule that is easy to get wrong: **these jobs
  write only `_inbox/agents/**`; every vault change they describe is a proposal for Mac-side
  promotion, never a direct write to `main`.**
- `docs/runbook.md` § Job wiring — add the three unit → env → runner → task-profile rows, matching
  the existing table format.

## Test plan

The gate is `bash bin/verify.sh`: `bash -n` + `shellcheck -S error` (must be clean) over every
script in `bin/`, then every `tests/*.sh`. What makes it meaningful for THIS feature:

- **The 402 regression cannot return silently** — `test_proposal_or_decline.sh` case (c) is a
  direct red-test for the ten-day failure: run produced nothing, no deliberate decline, must FAIL.
- **The migration is real, not cosmetic** — the `! grep hermes` assertion on the active
  `AGENT_RUNTIME_CMD` line fails if any revert comment is accidentally uncommented.
- **The model pin is asserted**, so an `opus` alias drifting to a future model is caught.
- **Stale-mirror refusal is asserted for both new vault-reading jobs** — a digest or ingest built
  off a frozen mirror is a confident wrong answer, the exact failure `vault_sync_guard.sh` exists
  to prevent.
- **Each task profile's load-bearing instruction is asserted by grep** (duplicate-title gate,
  ingest_log diff, git-log delta, contradiction section) — profiles are prompt text the gate
  cannot otherwise reach, and every one of these encodes a specific past failure.

Post-gate manual smoke (not part of `verify.sh`, run after deploy):
`sudo systemctl start raw-ingest.service` then check `logs/cost.log` shows
`profile=claude-opus task=raw-ingest` with a real outcome, and `logs/agent_propose.log` shows no
`SILENT-FAIL`.

## Out of scope / do not touch

- **`bin/agent_propose.sh` needs no change.** `AGENT_VERIFY_CMD` support already exists at
  line 286; this brief only supplies a verify command. Do not widen `PROVIDER_ERROR_RE` or touch
  the kanban path.
- **Do not delete the claudius/hermes path.** `bd-stall-radar` still runs under
  `profile=claudius`, and `augustus-content` / `overnight-morning-report` still use hermes.
  Keep the commented revert wiring in every `.env.example`.
- **Do not edit the vault.** `~/vault` is the live `main` checkout, Mac-published. Mechanism A's
  home is `00_system/update_protocol.md` § Source Ingestion — the box **cannot** write it. What
  this brief implements is the box-side half (the rule baked into the task profiles). Promoting
  the rule into `update_protocol.md` is a Mac-side action for Dave; note it in the runbook as a
  follow-up rather than attempting it.
- **No Obsidian Local REST API.** Rejected: the box runs no Obsidian, and the plugin path would
  couple every scheduled job to whether the Mac's Obsidian is awake and reachable over Tailscale.
  The git mirror + qmd is strictly more available.
- `~/agent-workforce/` (deployed copy) — never edit directly; it is produced by `bin/deploy`.
- OpenRouter top-up, marcus's `overnight-morning-report` provider failures (3/3 SILENT-FAIL on
  07-29 and 07-30), and `model=unknown` in `cost.log` for CC profiles (`agent_propose.sh:183`
  resolves the model from `~/.hermes/profiles/<profile>/config.yaml`, which does not exist for
  `claude-opus`/`claude-sonnet`) — all real, all separate follow-ups.

## Notes / preconditions

- **The runner is runtime-agnostic by design.** `agent_propose.sh` sources
  `$AGENT_JOB_OVERRIDES` (line 157) and execs `$AGENT_RUNTIME_CMD` (line 231) — swapping the
  brain requires no runner change. This is the documented NUC-32 migration path.
- **`--model claude-opus-5` is valid** on the installed CLI (Claude Code 2.1.220 at
  `/home/linuxbrew/.linuxbrew/bin/claude`; `--model` accepts an alias or a full model name).
- **CC runs cost `$0` in `cost.log`** (`cost_usd_delta=0.000000` for every `claude-sonnet` row) —
  the box subscription, not per-token OpenRouter. This is why the migration also fixes the budget
  exposure, and why the source article's Opus-vs-Fable per-token cost argument does not apply here.
- **Live `.env` files are outside git**, at `~/.config/agent-workforce/<name>.env`, mode 600,
  owned by dave. The repo holds only `.env.example`. After implementing, install all three live
  files and `chmod 600` them — nothing works until they exist, and
  `agent_propose.sh` `block_exit`s on `AGENT_JOB_OVERRIDES set but file missing`.
- **Nothing deploys automatically.** After the gate is green: commit, then `bin/deploy`
  (`--dry-run` first), then `sudo systemctl daemon-reload`, then
  `sudo systemctl enable --now raw-ingest.timer knowledge-digest.timer`. These are **system**
  units (`User=dave`), not `--user` units — do not use `systemctl --user` here (that scope is
  the hermes gateway only).
- **`agent-workforce-auto-sync.timer` fires every 15 minutes** and does `git add -A` + commit +
  push to `origin/main`. Commit immediately after editing, or the message is lost to a generic
  `Auto-sync:` commit and unrelated WIP rides along. `git fetch origin` and diff against
  `origin/main` before committing — this checkout can be silently merged-and-stale.
- Existing timer grid (avoid collisions): 01:30 augustus-content · 04:30 agent-proposal ·
  05:30 m1-signal-scan (Mon,Wed) · 06:00 daily-plan · 06:15 morning-report · 06:20 backlog-alert ·
  22:00 weekly-pre-assembly (Fri) · 22:15 eod-summary · 23:00 bd-stall-radar.
- **The de-silencing helper (`proposal_or_decline.sh`) was added beyond the literal request.**
  Without it the migration is unverifiable — a failed Opus run would again read as a clean
  decline and the next outage would be equally invisible. Cheap to strike if unwanted: drop the
  script, its test, and the `AGENT_VERIFY_CMD` line from the three `.env.example` files.
