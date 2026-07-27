# Brief: NUC-45 — Migrate daily plan + EOD summary from the Mac to Praetorium

**Date:** 2026-07-27   **Verify:** `bash bin/verify.sh` (run from `~/dev/agent-workforce`)

Move the two daily rhythm jobs off Mac launchd — where they silently no-op whenever the
laptop is asleep — onto the always-on box, under the existing `agent_propose.sh` guarded
runner. Notion becomes the durable morning/evening artifact; the canonical vault write
stays Mac-side (Dave-decision 2026-07-27).

---

## Investigation findings (established, not assumptions)

### The failure is real and quantified
Query of Daily Plans data source `3288d768-1ede-8190-ad5a-000b9710833e`, 2026-07-27:

| Date | Daily Plan | Generated at | EOD Summary |
|---|---|---|---|
| 07-27 Mon | **missing** | — | — |
| 07-26 Sun | — | — | **missing** |
| 07-25 Sat | — | — | **missing** |
| 07-24 Fri | **missing** | — | present |
| 07-23 Thu | present | **09:47** (late, manual) | present |
| 07-22 Wed | present | 06:00 | present |
| 07-21 Tue | present | 06:00 | present |
| 07-20 Mon | **missing** | — | present |
| 07-17 Fri | **missing** | — | present |

Three of the last seven weekdays had no morning plan; one was hand-run at 09:47. Nothing
at all has been written to either DB since 07-24. Same pattern in Daily Log
(`f184eddd-2793-4560-8d04-dcfbb8b55f85`): EOD rows for 07-21..07-24, then nothing.

### Notion is already fully reachable from the box — no sharing step needed
The `PraetoriumV2` REST integration (`NOTION_API_TOKEN` in
`~/.config/agent-workforce/secrets.env`) resolves **17 data sources**, including every
input and output both skills need. The memory note claiming "connected to 5 DBs" is stale.
Verified live 2026-07-27 (`Notion-Version: 2025-09-03`):

| Purpose | Data source id | Parent db id |
|---|---|---|
| **Daily Plans** (write target, morning) | `3288d768-1ede-8190-ad5a-000b9710833e` | `3288d768-1ede-81da-8cdc-df772d76a509` |
| **Daily Log** (write target, EOD) | `f184eddd-2793-4560-8d04-dcfbb8b55f85` | `a461c877-2715-4689-9ea6-2528bb0ca623` |
| Calendar Events (read) | `3288d768-1ede-81a4-927f-000b16612a75` | `3288d768-1ede-8105-a74a-f2b9f393596e` |
| Task Inbox (read + status write) | `4dbb4389-6c4a-4f57-b70f-10d899483c21` | `f464689b-2e1f-4bf9-bb14-7b6f2b4fbb1d` |
| Client Pipeline (read, BD chase queue) | `e5b6fe9a-f0d9-45b9-9320-d4f20c1f1e0e` | `d00500f0-b8ff-465e-8580-f8515449e15b` |

Schemas (read live, do not guess):
- **Daily Plans:** `Plan Title` (title, format `YYYY-MM-DD — Daily Plan`), `Plan Date`
  (date), `Status` (select, `Active`), `Generated At` (date, ISO w/ offset),
  `Events Count` (number), `Tasks Count` (number). Briefing body lives in page
  **blocks** — `heading_2` per section, `bulleted_list_item` / `numbered_list_item` per
  line, opening `quote` block for the one-line day framing.
- **Daily Log:** `Date` (title), `Type` (select, `EOD summary`), `Done`, `Remaining`,
  `Key insights`, `Focus areas` (all rich_text), `Tags` (multi_select).

Note both DBs are also used for EOD rows titled `— EOD Summary` in Daily Plans; keep that
convention rather than changing it.

### Vault sync is broken right now — this is the blocking precondition
`~/vault` (symlink → `~/dev/obsidian-ai-os-boxsafe`, branch `main`) is **7 commits /
4 days behind `origin/main`** (`1fec5b4` vs `f9d7085`, last publish 2026-07-25 13:00).

`qmd-refresh.service` runs `git pull --ff-only` every 30 min and aborts *every single run*:

```
error: Your local changes to the following files would be overwritten by merge:
        00_system/tools/agent_inbox.py
Aborting
```

The failure is **masked**: the ExecStart ends `|| echo "qmd-refresh: git pull failed
(offline?) — reindexing current tree"`, so the unit exits 0, `Finished` is logged, no
`OnFailure` fires, and qmd happily re-indexes the stale tree ("435 unchanged"). The
mirror has been silently frozen for four days while every health check reads green.

The local drift is **not junk** — `00_system/tools/agent_inbox.py` on the box is a
*newer* NUC-39 iteration than upstream (adds `DEFAULT_TARGET`, `_TARGET_LINE_RE`, and
`target:` auto-detection from the proposal body; upstream only has the `--target` flag).
This is box-side work that bypassed the membrane. Also untracked in the mirror:
`03_projects/active/ai_agent_workforce/local_inference_charter.md`, `opencode.json`,
`00_system/tools/__pycache__/`.

Missing upstream content includes `04_operations/current_priorities.md` (+42 lines),
`open_loops.md` (-64), three daily logs (07-23/24/25), and updated project status —
i.e. exactly the files the morning briefing reads. **A 06:00 job on this tree would
produce a confidently wrong plan.**

### Vault write-back on `main` is structurally impossible
`00_system/tools/publish_boxsafe.sh` "rebuilds the box repo working tree from ONLY the
included paths, then removes any excluded paths (default-deny: anything ... newly created
outside the list, never appears)". Anything the box writes into `~/vault` is deleted at
the next Mac publish (3×/day: 08:30, 13:00, 18:30). The box's `boxsafe_deploy` key is
scoped to `agents`-branch write only and cannot push `main` anyway.

**Decision (Dave, 2026-07-27): Notion-only from the box.** The vault `07_daily/logs/`
briefing section remains a Mac-side write, folded in by the interactive `eod-wrap`.
`publish_boxsafe.sh` is not touched.

### Runtime is proven — reuse the M1 pattern, do not invent one
- Headless Claude Code `2.1.220` at `/home/linuxbrew/.linuxbrew/bin/claude`, running on
  the box subscription (`$0` OpenRouter spend). `m1-signal-scan` ran 05:34→05:41 today
  and pushed a proposal — 7 min wall clock, 456 MB peak.
- `bin/run_m1_signal_scan_cc.sh` + `~/.config/agent-workforce/m1_signal_scan.env` is the
  working template: env override sets `AGENT_RUNTIME_CMD`, the script `exec`s `claude -p`
  with `--strict-mcp-config --mcp-config '{"mcpServers":{}}'` and an explicit
  `--allowedTools` list. `agent_propose.sh` owns lock, retry, cost, metrics.
- `AGENT_RUN_MODE=ops` (NUC-36) is the correct mode for both new jobs: lock / preflight /
  cost / scorecard only — no inbox worktree, no write-boundary, no proposal commit.
- `AGENT_VERIFY_CMD` is load-bearing and must be set. The overnight-morning-report
  learned this the hard way (2026-07-21): the runtime exits 0 when a provider error
  becomes the agent's final response, so exit code alone is not evidence anything was
  written. Use `-newermt "@$AGENT_RUN_STARTED_AT"` so yesterday's artifact cannot satisfy
  today's check.
- `bin/deliver_report.sh` (fail-soft, always exits 0) gives Discord delivery via
  `hermes send --to discord` as an `ExecStartPost`.

### What the box can and cannot see
**Can** (open-bubble posture ratified 2026-07-08, whole working vault mirrors):
`04_operations/{current_priorities,open_loops,daily_routines,wins_ledger,key_decisions}.md`,
`04_operations/fitness/{workout_schedule,workout_log}.md`,
`04_operations/health/symptom_log.md`, `05_knowledge/pattern_journal.md`,
`07_daily/logs/`, `03_projects/active/*/status.md` — all present in the mirror.

**Cannot:** `_confidential/` (never published, by construction), and the Mac's local git
activity / same-day uncommitted vault edits. The mirror lags up to ~5h even when healthy.

### AI Trading Bot repo is on the box but stale
`~/dev/AI_Trading_Bot` (branch `master`, remote `git@github.com:Dave1524/AI_Trading_Bot.git`)
is behind: `fetch --dry-run` shows `ee221d0..22a92b7 master`, `32f23fc..5fe17e1
hl-a1-honest-paper-costs`, and a new branch `hl-a3-allocator-net-tilt`. Untracked `_inbox/`.
The AITB backlog section reads "unmerged branch = the in-flight thread", so a stale fetch
reports the wrong ⭐ item. The job must `git fetch` (read-only) before scanning.

### GitHub connections — verified, no new credential needed
- `agent-workforce` → `~/.ssh/id_agent_workforce`, mapped as the default `Host github.com`.
- `obsidian-ai-os-boxsafe` → `github-boxsafe` alias →
  `~/.config/agent-workforce/keys/boxsafe_deploy` (read + `agents`-branch write only).
- `AI_Trading_Bot` → default `github.com` key; fetch confirmed working 2026-07-27.

Nothing to provision. The only git-side work is making the *pull* reliable (below).

---

## Acceptance criteria

1. On a weekday at 06:00 Europe/Amsterdam, with the Mac powered off, a Daily Plans row for
   today exists in Notion with `Status = Active`, `Generated At` within 15 min of the
   timer, and a populated block body — without manual intervention.
2. The same job re-run later the same day **updates that row in place**: no second row for
   the date, no duplicated blocks.
3. Both jobs **refuse and alert** rather than silently proceeding when `~/vault` is dirty
   or its `HEAD` is more than 24h behind `origin/main`. A stale-mirror run must never
   produce a confident plan. Refusal fires `OnFailure=agent-alert@` and reaches Discord.
4. `qmd-refresh` no longer masks a failed pull: a pull that aborts marks the unit failed
   and raises an alert, instead of logging `Finished` and re-indexing a frozen tree.
5. The current drift is resolved — `~/vault` fast-forwards to `origin/main` with the
   newer `agent_inbox.py` and the three untracked files **routed, not discarded**.
6. At the evening slot, an EOD Summary row exists in both Daily Plans (title
   `YYYY-MM-DD — EOD Summary`) and Daily Log (`Type = EOD summary`), reconstructed from
   box-visible evidence only, with every unevidenced claim marked `UNCONFIRMED`.
7. A later interactive `eod-wrap` from the Mac overwrites the box row in place rather than
   creating a duplicate.
8. Both jobs assert their artifact via `AGENT_VERIFY_CMD` tied to `$AGENT_RUN_STARTED_AT`;
   a run that writes nothing fails loudly and does not re-deliver a previous day's output.
9. Both timers are `Persistent=true` so a box reboot spanning the slot triggers a catch-up
   run.
10. `bash bin/verify.sh` is green.

## Files to create

- `bin/run_daily_plan_cc.sh` — headless Claude Code brain for the morning job. Mirrors
  `run_m1_signal_scan_cc.sh` in shape: resolve `CLAUDE_BIN`, `cd` to a working dir,
  `exec claude -p "$(cat profiles/daily_plan_task.md)"` with `--strict-mcp-config`,
  empty MCP config, explicit `--allowedTools`. Runs the vault-freshness gate before exec.
- `bin/run_eod_summary_cc.sh` — same shape for the evening job.
- `bin/notion_daily.py` — stdlib-only REST helper, sibling of `notion_rest.py`. Owns the
  date-keyed idempotent upsert against both data sources so neither task prompt hand-rolls
  curl: subcommands to find-or-create today's row, replace the page block body, and read
  the Task Inbox / Calendar / Client Pipeline inputs. This is the DRY seam — both jobs and
  any future Mac/box reconciliation go through it.
- `bin/vault_sync_guard.sh` — the fix for finding #3. Detects drift in `~/vault`, performs
  the `--ff-only` pull, and **exits non-zero on failure** so systemd marks it failed.
  Reports dirty-tree files by name rather than discarding them.
- `profiles/daily_plan_task.md` — the ported `morning-startup` instructions, box-flavoured:
  vault paths absolute against `~/vault`, Notion via `notion_daily.py`, AITB scan preceded
  by a `git fetch`, and the OVERNIGHT FROM PRAETORIUM section rewritten (the box *is*
  Praetorium — it reads its own journal/timers directly instead of SSH-ing to itself).
- `profiles/eod_summary_task.md` — evidence-only EOD: Notion Task Inbox and Client
  Pipeline deltas since morning, mirror commits, inbox proposals, `cost.log`, timer
  outcomes. Explicitly forbids inventing a brain dump; unevidenced → `UNCONFIRMED`.
- `profiles/daily_plan.env.example` / `profiles/eod_summary.env.example` — non-secret
  wiring templates (the live `.env` files are mode-600 under `~/.config/agent-workforce/`
  and never committed), following the `m1_signal_scan.env.example` precedent.
- `systemd/praetorium-daily-plan.service` / `.timer` — `OnCalendar=Mon..Fri 06:00`,
  `Persistent=true`, `RandomizedDelaySec` small (the 06:00 slot is user-visible),
  `OnFailure=agent-alert@%n.service`, `ExecStartPost=bin/deliver_report.sh`.
- `systemd/praetorium-eod-summary.service` / `.timer` — daily evening slot, placed before
  `bd-stall-radar` at 23:00 so the radar sees the day closed. Same failure wiring.
- `tests/test_daily_plan_smoke.sh`, `tests/test_eod_summary_smoke.sh`,
  `tests/test_notion_daily.sh`, `tests/test_vault_sync_guard.sh` — see test plan.
- `docs/briefs/` entry or `docs/runbook.md` section documenting the two new jobs alongside
  the existing ones.

## Files to modify

- `systemd/qmd-refresh.service` — replace the inline
  `git pull --ff-only || echo "... (offline?)"` with `bin/vault_sync_guard.sh`, and add
  `OnFailure=agent-alert@%n.service`. Keep genuine offline as a soft outcome; a *rejected*
  pull is a hard failure. This is the root-cause fix for the four-day silent freeze.
- `docs/runbook.md` — add both jobs: schedule, artifact path, verify command, what a
  failure looks like, how to re-run by hand.
- `CLAUDE.md` — register the two new jobs in whatever inventory it carries, so the next
  session does not rediscover them from `systemctl`.

## Test plan

The gate is `bash bin/verify.sh` = `bash -n` + `shellcheck -S error` over every script in
`bin/`, plus every `tests/*.sh`. New tests must be self-contained and must not make live
Notion writes or touch the real vault.

- `tests/test_vault_sync_guard.sh` — the highest-value test, because it encodes the bug
  that caused this migration to be needed. Against a throwaway git fixture:
  clean + behind → pulls, exit 0; **dirty + behind → exit non-zero and names the file**
  (today's masked failure, now red); clean + current → no-op, exit 0; unreachable remote →
  soft, exit 0 with a distinguishable message. Parameterize with a case table so a new
  branch can't be added without a case.
- `tests/test_notion_daily.py` behaviour driven from `tests/test_notion_daily.sh` — upsert
  idempotency against a stubbed HTTP layer: two consecutive upserts for the same date
  produce one create + one update, never two creates; block-body replacement is a replace,
  not an append. No network in the gate.
- `tests/test_daily_plan_smoke.sh` — the env override parses; `AGENT_RUNTIME_CMD` resolves;
  `AGENT_VERIFY_CMD` fails when no fresh artifact exists and passes when one is newer than
  `$AGENT_RUN_STARTED_AT` (assert with a deliberately stale fixture, mirroring the
  2026-07-21 regression); the freshness gate refuses on a stale vault fixture. Follow the
  shape of `tests/test_agent_propose_smoke.sh`.
- `tests/test_eod_summary_smoke.sh` — same env/verify shape, plus: an evidence set with a
  gap produces an `UNCONFIRMED` marker rather than a filled-in claim.

Post-merge manual verification (not gateable, do it explicitly):
`systemctl start praetorium-daily-plan.service` with the Mac off, then confirm the Notion
row, re-run to confirm in-place update, and confirm the Discord delivery landed.

## Out of scope / do not touch

- `00_system/tools/publish_boxsafe.sh` and anything else in the canonical vault — Mac-side,
  and this box holds no credential to canonical.
- Two-way vault sync / a box-owned preserved path in the mirror. Explicitly deferred by
  Dave's 2026-07-27 decision; revisit only if Notion-only proves insufficient.
- Writing `07_daily/logs/` from the box, on any branch. The vault briefing section stays a
  Mac-side write.
- Promoting or rejecting inbox proposals — still an interactive Mac judgment call.
- The `morning-startup` / `eod-wrap` SKILL.md files themselves. They stay the canonical
  interactive skills; the box task files are a port, not a replacement. Do not edit the
  vault copies from this box.
- `_confidential/`, `.confidential.img`, `ENCRYPTION_RECOVERY.md`, `~/.ssh/`,
  `~/.config/agent-workforce/` secrets.
- Weekend morning runs (the existing spec defers them; EOD stays daily to match the Mac).

## Notes / preconditions

- **Do the vault-drift resolution first.** Nothing else in this brief is trustworthy on a
  four-day-stale mirror. The newer `agent_inbox.py` must be routed to canonical via
  `agents/inbox` (or landed upstream from the Mac) before the mirror is fast-forwarded —
  do not `git checkout` it away. `local_inference_charter.md` is the stray flagged in the
  07-23 briefing and still unrouted.
- The deployed copy is `~/agent-workforce`, the source repo is `~/dev/agent-workforce`.
  Edit the source; deploy `bin/*.sh` with an atomic `mv` (never `cp` over a running
  script); systemd oneshots pick up the deployed copy fresh with no restart. The deployed
  tree can carry uncommitted drift — diff before overwriting.
- `agent-workforce-auto-sync.timer` does `git add -A` + commit + push to `origin/main`
  every 15 min. Commit immediately after editing or the message is lost to a generic
  "Auto-sync" and unrelated WIP rides along.
- Box timezone is `Europe/Amsterdam` (CEST); the `Generated At` write must carry the
  offset, matching the existing rows (`2026-07-23T09:47:00.000+02:00`).
- Default-tier policy (data_boundary.md, 2026-07-23): new jobs start at Tier 0/local.
  These two need frontier judgment over business content, so headless Claude Code on the
  box subscription is the right tier — and it keeps OpenRouter spend at $0 while that
  budget is paused.
- Mac-side decommission is Dave's, after ~1 week of clean box runs (mirrors the original
  spec's CoWork migration): unload `com.davehamelink.morning-startup.plist`, disable the
  `daily-eod-wrap` scheduled task, and update `04_operations/scheduled_jobs.md` +
  `daily_routines.md` in the canonical vault. Keep the Mac jobs running in parallel until
  then — a duplicate row is a cheaper failure than a missing plan.
- Create the Sprint Board card as **NUC-45** (`NUC-44` is the highest existing id).
