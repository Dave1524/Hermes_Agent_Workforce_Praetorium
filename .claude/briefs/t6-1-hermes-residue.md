# Brief: T6.1 — Retire the Hermes residue

**Date:** 2026-09-14
**Verify:** `bash bin/verify.sh` from the repo root (includes `bin/check_deploy_drift.sh`). **Red on a
branch by construction** — this brief moves two units to `systemd/archive/`, edits one system unit's
`ExecStart`, deletes one user unit from source and disowns five deployed files, so the gate is green only
after § Land-time (needs sudo). Never assume green before it.

**Depends on:** T5.2 (executor wiring) — **lands first**; this brief rebases on it and re-anchors every
`bin/agent_propose.sh` edit by the quoted text, not by the pre-T5.2 line numbers cited here.

**Gates satisfied by this brief:**
- Task (Notion card, verbatim): *a grep for hermes across bin/ systemd/ profiles/ returns only
  historical notes; verify green.* Encoded as `tests/test_hermes_residue.sh` (§ Test plan) — mechanical,
  with an explicit allowlist.
- Plan DoD item 4 (2026-09-14): the same grep, "behind D4". § D4 names the one step that waits.
- Standing constraint: the twelve workflow timers are disabled since 2026-09-11 and stay so. **No step
  enables, starts or stops a timer.** Every test runs from fixtures. One hand-started
  `systemctl start local-tier-eval.service` is Dave's evidence-time run (§ Evidence), not development.
- Ship-dev-plan gate words for T6.1 (`.claude/workflows/ship-dev-plan.js:53`): "the changed unit ran
  once live and its journal output was read; base0 and leantest kept" — the changed unit is
  `brave-mcp.service` (§ Land-time step 4 reads its journal); base0 and leantest are kept.

## Inventory — every `hermes` hit in the gate set, with its disposition

`grep -rin hermes bin/ systemd/ profiles/` → **133 lines** (MEASURED 2026-09-14, pre-T5.2). graft's
index covers only the Python files (2 hits, both in `bin/bd_stall_radar_kernel.py`); the plain grep is
the exhaustive check and the test reproduces it. Dispositions: **retire** (delete the mechanism),
**reroute** (keep the mechanism, move it off `~/.hermes`), **historical** (a comment or prose line about
the past — inert, stays), **live** (a real dependency this task does not own — allowlisted with the
decision that retires it).

| File | Lines | What it is | Disposition |
|---|---|---|---|
| `bin/agent_propose.sh` | :249-266 | `profile_cfg`/`run_model` awk — resolves `model=` for cost.log from `~/.hermes/profiles/$run_profile/config.yaml`. Wrong for every live row: CC jobs read `unknown` (no `claude-opus` profile), and `augustus-content` logs `model=openai/gpt-5.5` from a profile the buzz-agent runtime never uses (MEASURED: last 5 cost.log rows) | **retire** → `run_model=unknown`; the receipt (T5.2) carries the measured model |
| `bin/agent_propose.sh` | :312-316, :471-503 | episodic store: `MEM_DIR`/`MEM_FILE`/`mem_before`, and the post-run "runner fallback entry" writer. It is what wrote `augustus` and `claudius` `MEMORY.md` on 2026-09-11 — a runner writing notes to itself; no runtime reads them (the `_cc_task.md` prompts say so and substitute `ls _inbox/agents`) | **retire** — `memory=na` on every run |
| `bin/agent_propose.sh` | :47-69, :376-377 | `key_usage()` + the `usage_before` snapshot — the OpenRouter shared-key spend probe for the Hermes runtime. 344 of 353 rows since 2026-08-01 read `cost_usd_delta=0.000000` (MEASURED) — the "frozen zero rendered as measured" the dev plan names | **retire** — `usage_before` stays `unknown`, `log_cost`'s existing unknown branch does the rest; record shape unchanged |
| `bin/agent_propose.sh` | :20, :83, :127, :323-328, :345-358, :409 | comments: Hermes cron origin, no-transcript runtimes, token accounting, `--max-turns` phantom flag, exit-0-on-provider-error, retry note | **historical** (comment lines; the mechanisms they explain still apply to any runtime) |
| `bin/bd_stall_radar_kernel.py` | :5, :49, :237-275 | `MEM_FILE = ~/.hermes/profiles/claudius/memories/MEMORY.md`; `recently_flagged()` reads its own `stalls_found=` entries back for the 3-day dedup window and appends one per run. **The one load-bearing reader of the store** — deleting the profile would silently drop dedup ("the same stall is flagged three nights running", contract :49) | **reroute** → repo-owned state file `~/agent-workforce/var/bd-stall-radar/flagged.jsonl` (`BD_STALL_RADAR_STATE` override) |
| `bin/apply_skills_allowlist.sh` | whole file | edits the live `~/.hermes/profiles/<p>/config.yaml` skill allowlists; its last reader was `hermes -p marcus` in `local_tier_eval.sh`, which this brief moves to `base0` (no skill index) | **retire** — delete; `docs/skills_allowlist.md` with it |
| `bin/consolidate_memory.sh` + `systemd/memory-consolidation.{service,timer}` | whole | nightly prune of the stores retired above; the contract's own retirement condition ("nothing writes what this prunes") is met by construction once the writer is gone. Timer already `disabled/inactive` (MEASURED) — not one of the twelve | **retire** — units → `systemd/archive/`, script + suite + manifest row + tsv row deleted, contract → `design/archive/contracts/` |
| `bin/praetorium-status.sh` | :133-142 | `profile : claudius qmd = …` probe of the claudius hermes config | **retire** the probe; keep the endpoint reachability lines |
| `bin/praetorium-status.sh` | :146 | `BRAVE_API_KEY` probe reads `~/.hermes/.env` | **reroute** → `$HOME/.config/agent-workforce/brave-mcp.env`, the file the daemon's unit actually loads |
| `bin/praetorium-status.sh` | :181-182 | `agent-browser (hermes-local)` runner branch | **retire** the `elif` |
| `bin/praetorium-status.sh` | :191-207 | "Working memory (all profiles)" section over `~/.hermes/profiles/*/memories` | **retire** the section |
| `bin/praetorium-status.sh` | :119-124, :171 | comments | **historical**; :123-124 reworded (the gateway unit will no longer be on disk) |
| `bin/local_tier_eval.sh` | :27, :129-130 | `hermes -t … -z … -p marcus -m "$model"` — the `local` alias (qwen3-64k, `custom:ollama_local`, temperature 0) lives in **marcus's** config.yaml; base0 has no alias block. So "keep base0 and leantest" is only sufficient after the alias moves | **reroute** → `-p base0`; alias block appended to base0's config.yaml at land (§ Land-time step 6, verbatim text in § Notes). **live** row in the allowlist (`retires_with = local-tier-eval`) |
| `bin/deliver.sh` | :13, :254-282 | `hermes_send()` — the Discord leg of every delivery (`hermes send --to discord`, resolved from `~/.hermes/hermes-agent/venv/bin/hermes`). Live and working: 358 `discord_result=ok` receipts, last 2026-09-11T07:00Z (MEASURED). Its retirement is the Discord cutover, gated on `bin/audit_buzz_dual_run.sh` — Dave's decision, and T5.3c's brief says "transport stays as is" | **live** — allowlisted, `retires_with = discord-cutover`. Not touched |
| `bin/overnight_pre_snapshot.sh` | :65-69 | `hermes mcp list` under "MCP servers" | **retire** the if/else block; the qmd/brave endpoint checks that follow stay |
| `bin/overnight_pre_snapshot.sh` | :2 | comment | **historical** |
| `bin/scorecard.sh` | :179-180 | `echo` into the scorecard artifact: "(hermes token accounting is unreliable…)" — not a comment, so it fails the mechanical rule | **retire** the clause from the emitted text (:8 comment stays historical) |
| `bin/proposal_or_decline.sh` :4-5, `bin/content_change_dispatch.sh` :105, `bin/run_standing_research_cc.sh` :3, `bin/run_weekly_pre_assembly_cc.sh` :7, `bin/run_overnight_morning_report_cc.sh` :4,:17,:21, `bin/run_m1_signal_scan_cc.sh` :4, `bin/run_content_via_buzz.sh` :3, `bin/check_deploy_drift.sh` :282 (the GitHub repo name) | comments | **historical** |
| `bin/fleet_eval_probes.json` | :110 | a probe's description string (JSON, not a comment) | **historical** — allowlist row |
| `systemd/brave-mcp.service` | :16 | `ExecStart=/home/dave/.hermes/bin/brave_mcp_launch.sh` — a 15-line launcher (log a line, `exec npx -y @brave/brave-search-mcp-server "$@"`) living in the hermes tree; the unit is `enabled` + `active` and serves the daemon fleet on :8766 | **reroute** → `bin/brave_mcp_launch.sh` in this repo; `ExecStart=/home/dave/agent-workforce/bin/brave_mcp_launch.sh …` |
| `systemd/brave-mcp.service` :4, `overnight-morning-report.service` :2, `agent-inbox-sync.service` :2, `agent-workforce-auto-sync.{service,timer}` :2, `overnight-pre-snapshot.service` :2 | comments | **historical** |
| `systemd/inbox-backlog-alert.service` | :7 | comment "delivery reuses the ~/.hermes credentials" — true, and it should say why | **historical**, reworded to name the Discord cutover |
| `systemd/user/hermes-gateway.service` | whole | the retired S3 gateway (D7, 2026-09-02): `disabled/inactive` in `~/.config/systemd/user/`, written by `hermes gateway install`, not by this repo. `hermes send` does not need it (receipts ok with it down since 09-02) | **retire** — delete from source; land removes the live and staging copies |
| `profiles/{standing_research,raw_ingest,m1_signal_scan,knowledge_digest,bd_followup_drafts,bd_stall_radar,weekly_pre_assembly,daily_plan,eod_summary,overnight_morning_report}.env.example` | the W1 `AGENT_OWNER` comment block | says `AGENT_OWNER` "keys the episodic memory store (~/.hermes/profiles/…)" — false after this brief | **reroute the sentence** (ten identical edits, § Files to modify) |
| `profiles/{m1_signal_scan,weekly_pre_assembly,standing_research}.env.example` "Previous runtime" blocks, `profiles/overnight_morning_report.env.example` :10 | commented-out `# AGENT_RUNTIME_CMD='… hermes -z …'` lines marked NOT A REVERT PATH; the smoke suites already assert no uncommented one | **historical** |
| `profiles/{m1_signal_scan,weekly_pre_assembly,standing_research,overnight_morning_report}_cc_task.md` | "NOT hermes/claudius on OpenRouter", "no hermes MEMORY store on this runtime" | prompt text asserting the retirement | **historical** — allowlist rows |
| `profiles/overnight_morning_report_cc_task.md` | :90-91 | instructs the model to check `~/.hermes/cron/jobs.json` for residual Hermes cron — a live instruction against a retired host | **retire** the two lines (+ smoke assertion :298-299) |
| `profiles/archive/**` | all | archived task files | **historical by construction** — the scan skips `*/archive/` |

Outside the gate set, edited because they describe the retired mechanism as live: `design/agents/*.toml`
`[surfaces.kanban]` (five), `design/agents/trajan.toml` memory-consolidation row, `design/agent-model.md`
§2/§3/§8.4, `design/contracts/{bd-stall-radar,bd-followup-drafts,raw-ingest,m1-signal-scan,standing-research,knowledge-digest,local-tier-eval}.md`,
`config/fleet-units.tsv`, `docs/runbook.md`, `CLAUDE.md` § Roster, `README.md:39`. Not edited:
`design/workflow-registry.md` (T6.4 freezes it), `design/archive/**`, `docs/dev-plan-2026-09.md`
(the tracker; the land note goes there at land, one line).

## Acceptance criteria

1. `tests/test_hermes_residue.sh` is green: every `hermes` hit (case-insensitive, recursive, `*/archive/`,
   `__pycache__` and `*.bak*` skipped) under `bin/ systemd/ profiles/` is either a comment line in a code
   file, an allowlisted prose line, or one of the pinned **live** rows; every allowlist row still matches
   a hit; the live set is exactly `bin/deliver.sh` (discord-cutover) and `bin/local_tier_eval.sh`
   (local-tier-eval); the checker fails on a fixture tree with one live hermes line.
   (`residue-code-line-is-comment-or-live`, `residue-prose-is-listed`, `residue-no-stale-row`,
   `residue-live-is-pinned`, `residue-canary-red`)
2. `bin/local_tier_eval.sh` runs `-p base0` and names no persona profile. (`residue-local-tier-on-base0`)
3. `bin/agent_propose.sh`: every run logs `model=unknown` and `memory=na`; a proposal-mode run creates
   nothing under `$HOME/.hermes` and honours no `RA_MEMORY_DIR`; `usage_before`/`usage_after`/
   `cost_usd_delta` are `unknown` on every row; the `schema=3` record keeps its keys; every existing
   smoke scenario's exit code and outcome are unchanged. (`propose-no-hermes-model`,
   `propose-no-episodic-store`, `propose-cost-delta-unknown`)
4. `bin/bd_stall_radar_kernel.py` dedups from `BD_STALL_RADAR_STATE` (default
   `~/agent-workforce/var/bd-stall-radar/flagged.jsonl`): a run recorded ≤3 days ago suppresses its
   names, an older one does not, an absent file yields no dedup and no error, and a run appends exactly
   one JSON line; nothing under `~/.hermes` is read or created. (`radar-dedup-reads-state`,
   `radar-dedup-window`, `radar-dedup-absent-is-empty`, `radar-dedup-appends-one-line`,
   `radar-dedup-never-touches-hermes`)
5. `bin/praetorium-status.sh`: Brave `key : set` when `brave-mcp.env` carries the key (and the value never
   reaches the report); no `claudius qmd` line; no `hermes-local` runner; no "Working memory" section;
   every other section's assertions unchanged. (`status-brave-key-from-brave-mcp-env`,
   `status-no-profile-probe`, `status-no-working-memory-section`)
6. `bin/brave_mcp_launch.sh` exists in source, is executable, logs one `launch pid=… key=set(len=N)|MISSING`
   line to `$LOG` and execs `npx -y @brave/brave-search-mcp-server "$@"` with the args passed through;
   `systemd/brave-mcp.service` `ExecStart` names it at the deployed path. (`brave-launcher-logs-and-execs`,
   `brave-unit-execs-repo-launcher`)
7. `systemd/archive/memory-consolidation.{service,timer}` exist; `systemd/memory-consolidation.*`,
   `systemd/user/hermes-gateway.service`, `bin/consolidate_memory.sh`, `bin/apply_skills_allowlist.sh`,
   `docs/skills_allowlist.md`, `tests/test_consolidate_memory.sh`, `tests/test_working_memory_status.sh`
   do not; `design/agents/trajan.toml` has no `memory-consolidation` row; `config/fleet-units.tsv` has no
   `memory-consolidation` row; `design/contracts/memory-consolidation.md` is at
   `design/archive/contracts/memory-consolidation.md` with a retirement header.
   `tests/test_workflow_coverage.py`, `test_fleet_ownership.sh`, `test_contract_schema.sh`,
   `test_manifest_surfaces.sh`, `test_deploy_drift.sh` green.
8. The five `[surfaces.kanban]` blocks carry `present = false`, `retired = "2026-09-02"`, one-line
   `notes`; no `governed_by`, `skills` or `board`. `design/agent-model.md` §3 and the §2 skills bullet say
   the profiles are deleted (T6.1) and point at `design/archive/hermes-profiles-2026-09-14.md` for the
   measured counts. (`kanban-block-carries-no-profile-fact` — added to `tests/test_manifest_surfaces.sh`)
9. Land (§ Land-time): `bash bin/verify.sh` green on `main`, drift clean; `brave-mcp.service` restarted
   from the repo launcher and its journal read; `memory-consolidation.timer` is no longer a unit;
   `systemctl --user list-unit-files hermes-gateway.service` reports none; `ls ~/.hermes/profiles/` is
   `base0 default leantest` plus `augustus` while D4 is undecided.
10. Evidence (Dave's moment): one `sudo systemctl start local-tier-eval.service` completes with 11 rows in
    that run's `results.psv` and `history.psv` grows by 11, on `base0`, with no OpenRouter call.

## Files to modify

- `bin/agent_propose.sh` (T6.1-owned regions only — § Seam):
  - delete `key_usage()` (from `key_usage() {` to its closing `}`); replace
    `usage_before=$(key_usage)` + the `log "cost: usage_before=…"` line with a two-line comment
    ("OpenRouter key probe retired T6.1 2026-09-14: the Hermes runtime was its only spender and its
    delta had read 0.000000 on 344 of 353 rows; usage is measured per run in the receipt (T5.2),
    cost.log keeps `unknown`"). `usage_before="unknown"` at :45 stays. **`log_cost` is not edited.**
  - replace the block from `# Deliberately still keyed on the RUNTIME:` through `run_model="${run_model:-unknown}"`
    with `run_model=unknown` and a two-line comment (model resolution from a hermes profile retired
    T6.1; the receipt carries the measured model; `unknown` here is honest, and it replaces a
    confidently wrong `openai/gpt-5.5` on augustus-content rows). The `run_owner=` line and the
    `log "mode: …"` line stay.
  - delete `MEM_DIR=`, `MEM_FILE=`, `mem_before="absent"` and the `[ -f "$MEM_FILE" ] && mem_before=…`
    line; **keep** the `if [ "$run_mode" = proposal ]; then … git checkout … git pull … fi` around it.
    Reword the NUC-21 comment above it to one line: episodic store retired T6.1.
  - delete from `mem_after="absent"; …` through the closing `fi` of the memory block (the
    `proposal_file=` line goes too — its only reader was the entry string; re-check after T5.2: if its
  `write_receipt` reads `$proposal_file`, keep that one line). `mem_status="na"` at :43,
    `mem_status=na` at :422 and :455 stay, so `log_cost` keeps emitting `memory=na`.
  - `:20` header comment: leave.
- `bin/bd_stall_radar_kernel.py` — replace `MEM_FILE` with
  `STATE_FILE = os.environ.get("BD_STALL_RADAR_STATE") or os.path.expanduser("~/agent-workforce/var/bd-stall-radar/flagged.jsonl")`;
  `recently_flagged(today)` reads JSONL rows `{"date": "YYYY-MM-DD", "run": "<iso ts>", "stalls": [names]}`
  and returns the union of `stalls` for rows within `DEDUP_WINDOW_DAYS`; the appender writes one such
  row under the same `fcntl.flock` on `STATE_FILE + ".lock"`, creating the directory; malformed rows
  are skipped with one `[warn]`. Docstring :5 reworded (historical). The kernel's stdout/sentinel
  behaviour is unchanged.
- `bin/praetorium-status.sh` — per the inventory: delete the `prof=`…`fi` probe and the `profile :`
  printf; `brave-mcp.env` path in the key probe; delete the `hermes-local` elif; delete the Working
  memory section (from `echo; echo "── Working memory` to the `fi` before `── Vault clone`); reword
  :123-124.
- `bin/local_tier_eval.sh` — `-p marcus` → `-p base0`; a comment naming why base0 carries the alias
  block (§ Notes). `HERMES=` stays.
- `bin/overnight_pre_snapshot.sh` — delete the `if command -v hermes … fi` block under `section "MCP servers"`.
- `bin/scorecard.sh` — :179-180: drop the "(hermes token accounting is unreliable, #4404/#20741)"
  clause from the emitted text; say cost.log's delta is `unknown` and receipts carry measured usage.
- `systemd/brave-mcp.service` — `ExecStart=/home/dave/agent-workforce/bin/brave_mcp_launch.sh --transport http --port 8766 --host 127.0.0.1`;
  header comment: launcher moved into the repo (T6.1).
- `systemd/inbox-backlog-alert.service` :7 — "delivery's Discord leg still resolves the hermes CLI
  (`bin/deliver.sh` `hermes_send`) until the Discord cutover; no OpenRouter key".
- `profiles/*.env.example` (the ten named in the inventory) — replace the four-line W1 block
  ("It keys the episodic memory store … there is no ~/.hermes/profiles/claude-opus/.") with:
  `# AGENT_OWNER names the owning persona (design/agents/<owner>.toml) — the owner= field of the run`
  `# log. Until T6.1 (2026-09-14) it also keyed a Hermes episodic store under ~/.hermes/profiles; that`
  `# store is retired and nothing on this runtime reads or writes one. AGENT_PROFILE still names the`
  `# RUNTIME and keys cost.log's profile= column (W1, 2026-09-02).`
- `profiles/overnight_morning_report_cc_task.md` — delete :90-91 (`Do **not** treat ~/.hermes/cron/jobs.json …`).
- `design/agents/{marcus,claudius,augustus,trajan,aurelian}.toml` `[surfaces.kanban]` → exactly
  `present = false`, `retired = "2026-09-02"` (comment: `# D7 retired the board; T6.1 (2026-09-14) retired the hermes profile it governed`),
  `notes = "<one line>"`. trajan's line: "Board retired 2026-09-02 (D7); profile deleted at T6.1 land.
  The allowlist it justified keeping (bin/apply_skills_allowlist.sh) is retired with its last reader
  (local-tier-eval → base0). Counts and history: design/archive/hermes-profiles-2026-09-14.md."
  augustus's line adds "profile deletion waits on D4". aurelian's: "No hermes profile ever existed for
  aurelian; the four persona profiles are deleted at T6.1 land — base0, leantest, default remain."
- `design/agents/trajan.toml` — delete the `[[workflows]] unit = "memory-consolidation"` entry.
- `design/agents/augustus.toml` :170 `why` — "D4: pin `only: [\"azure\"]` on the hermes profile or
  delete it (T6.1 deletes everything else; the profile is read by nothing after T6.1)".
- `design/agent-model.md` — §2 row S3 (:63): append "; profiles deleted 2026-09-14 (T6.1)". §2 skills
  bullet (:165-181): past tense; the counts move to the archive doc; "S3 was one caller, and it is not
  the last one: local_tier_eval.sh runs -p marcus" → "its last caller moved to base0 (T6.1), which has no
  skill index". §2 (:198-202) "not licence to delete" → "retired T6.1". §3 (:226-227) "across all four
  surfaces" → "across the three live surfaces (S3 and its hermes profiles retired: D7, then T6.1)".
  §8.4 (:757-761): "**CLOSED 2026-09-14 (T6.1):** deleted, with the last reader rerouted to base0."
- `design/contracts/bd-stall-radar.md` :49, :110 — the dedup input is
  `~/agent-workforce/var/bd-stall-radar/flagged.jsonl`; absent means no dedup (unchanged semantics).
- `design/contracts/{bd-followup-drafts:125,raw-ingest:99,m1-signal-scan:99,standing-research:108,knowledge-digest:88}.md`
  — replace the "writes one episodic line to ~/.hermes/…" bullet with "No episodic store (retired T6.1,
  2026-09-14); the per-run record is the receipt". `standing-research.md:43` "(no hermes MEMORY on this
  runtime)" stays (historical).
- `design/contracts/local-tier-eval.md` :15 — runner row: `hermes -p base0` (alias `local` on base0).
- `config/fleet-units.tsv` — drop the `memory-consolidation` row (then `tests/test_fleet_ownership.sh`
  must be green — it joins the tsv to the manifests in both directions).
- `design/fleet-suites.toml` — one `[[suite]]` for `tests/test_hermes_residue.sh`, `owner = "fleet"`,
  `asserts` = the six `residue-*` ids from § Test plan (copy the `test_contract_exec.sh` entry's shape).
- `tests/test_agent_propose_smoke.sh` — scenario 1: fixture no longer writes `.hermes/profiles/claudius/config.yaml`;
  assertions :135-136 → `model=unknown`; :143-144 deleted; new: `[ ! -e "$h1/.hermes" ]`
  (`propose-no-hermes-model`). Scenario 6 becomes `propose-no-episodic-store`: pre-create
  `$h6/.hermes/profiles/claudius/memories/` and export `RA_MEMORY_DIR=$h6/ra`; after the run neither
  holds a `MEMORY.md` and cost.log reads `memory=na`. New assertion on any scenario:
  `cost_usd_delta=unknown` and no `cost: usage_before=` log line (`propose-cost-delta-unknown`). Every
  other scenario's exit-code and outcome assertions unchanged.
- `tests/test_bd_stall_radar_kernel.py` — five dedup tests (criterion 4) over a temp `BD_STALL_RADAR_STATE`
  and a fake `HOME` whose `.hermes/` must stay absent after the run.
- `tests/test_praetorium_status.sh` — :458-463 fixture writes the key to
  `$root/home/.config/agent-workforce/brave-mcp.env` (absence-of-secret assertions unchanged); delete the
  `claudius qmd = unknown` assertion and the two profile scenarios (:496-510); add
  `! grep -q 'claudius qmd'` and `! grep -q 'Working memory'` over the report (`status-no-profile-probe`,
  `status-no-working-memory-section`).
- `tests/test_qmd_status.sh` — scenarios A/B keep exit-0, section header, endpoint reachable/unreachable;
  drop the three `profile =` assertions and scenario C's fixture config.
- `tests/test_brave_status.sh` — scenario 1 writes the key to `$h1/.config/agent-workforce/brave-mcp.env`
  (`status-brave-key-from-brave-mcp-env`); scenario 2 unchanged.
- `tests/test_fetch_status.sh` — fixture setup :50-51 no longer creates `.hermes/.env` (no assertion changes).
- `tests/test_overnight_morning_report_smoke.sh` — :298-299 becomes
  `! grep -q 'hermes/cron' "$TASK"` ("no instruction to inspect a retired host").
- `tests/test_manifest_surfaces.sh` — one assertion over the live manifests: no `[surfaces.kanban]` block
  carries `governed_by`, `skills` or `board` (`kanban-block-carries-no-profile-fact`).
- `tests/test_workflow_coverage.py` :360 comment — if T5.2's landed text carries a literal standing-row
  count, decrement it by one (memory-consolidation) and mark it MEASURED; same for
  `tests/test_receipt_coverage.py` if T5.2 pinned a count, and for T5.3's `STANDING_ENTRIES`/
  `LOGICAL_WORKFLOWS` in `tests/test_control_room_views.py` (−1 each; that suite pins the pair against the
  real manifests).
- `docs/runbook.md` — :22 column header `Hermes profile` → `Runtime`; :52-70 (the `AGENT_OWNER` store
  table and the consolidate paragraph) → one paragraph: `AGENT_OWNER` names the persona; the store is
  retired (T6.1); the `memory-consolidation.timer` row in the `| Unit | Role |` platform table (:184) removed, and the
  :442 rebuild-checklist and :487 § Agent working memory mentions reworded to past tense; :405-406 backup rows
  → one row "Hermes profiles kept: `~/.hermes/profiles/{base0,leantest}` (local-tier-eval) —
  `config.yaml` only"; :420 "Install Hermes" → append "(needed only for local-tier-eval and the Discord
  delivery leg)"; :461-466 "Web fetch: built-in Hermes browser toolset" → "retired with the Hermes
  runtime; CC runners use their own fetch".
- `CLAUDE.md` § Roster — replace the "Four Hermes profiles" table and the two bullets that follow it
  ("Most scheduled work no longer runs on these personas", "Augustus has no ZDR provider pin") with:
  personas are `design/agents/<name>.toml`; the model per scheduled job is the `--model` in its
  `bin/run_*_cc.sh`, per Buzz agent the unit's env; Hermes remains on this box for two things only —
  the `hermes` CLI as the Discord delivery leg (`bin/deliver.sh`, until the cutover) and profiles
  `base0`/`leantest` for `local-tier-eval`; the four persona profiles were deleted 2026-09-14 (T6.1),
  augustus's pending D4. Keep the "Vespasianus never built" and "Discord identities never built"
  bullets. The `ls ~/.hermes/profiles/` line's comment → "base0, leantest, default (+ augustus until D4)".
- `README.md` :39 — "project context for Claude/Hermes agents" → "project context for Claude agents"
  (:1 is the GitHub repo name — unchanged).

## Files to create

- `bin/brave_mcp_launch.sh` — the launcher, moved: `LOG="${BRAVE_MCP_LOG:-$HOME/agent-workforce/logs/brave_mcp.log}"`,
  one `launch pid=… key=set(len=N)|MISSING` line, `export PATH="/usr/bin:$PATH"`,
  `exec "${BRAVE_MCP_SERVER:-npx}" -y @brave/brave-search-mcp-server "$@"` (the two env overrides
  exist for the fixture test only; unset in production). Header: two lines of history (NUC-21; moved
  from `~/.hermes/bin` at T6.1) — comment lines, inert to the gate.
- `tests/test_brave_mcp_launch.sh` — fake server on `BRAVE_MCP_SERVER` records argv and env;
  asserts the log line (`key=set(len=5)` with a 5-char fixture key, `key=MISSING` without), argv
  passthrough (`--transport http --port 8766 --host 127.0.0.1` arrives verbatim), and that
  `systemd/brave-mcp.service`'s `ExecStart` names `/home/dave/agent-workforce/bin/brave_mcp_launch.sh`
  (`brave-launcher-logs-and-execs`, `brave-unit-execs-repo-launcher`).
- `tests/test_hermes_residue.sh` — gate entry point in the `tests/test_contract_exec.sh` shape
  (`set -uo pipefail`, `cd` to repo root, `yes | grep -q y` canary, `exec python3 tests/test_hermes_residue.py`).
- `tests/test_hermes_residue.py` — one concept: the residue rule. `scan(root, allowlist) -> findings`
  over `bin/ systemd/ profiles/` under `root`, skipping any path with an `archive` component,
  `__pycache__`, `*.bak*`; a hit is a line containing `hermes` case-insensitively. Code files
  (`.sh .py .service .timer .env.example .conf .toml .tsv`, and extension-less files) pass when the line
  matches `^\s*#` or a `live` row; prose files (`.md .json .txt`) pass only via a `historical` row. Rows
  are `path<TAB>class<TAB>anchor<TAB>retires_with_or_why` where `anchor` is a literal substring of the
  line. The live set is pinned as a literal in the test:
  `{"bin/deliver.sh": "discord-cutover", "bin/local_tier_eval.sh": "local-tier-eval"}`. Anchored ids per
  § Test plan; the canary runs `scan()` over the two fixture trees.
- `tests/fixtures/hermes-residue/allowlist.tsv` — expected rows after this brief lands (the checker
  makes the exact set self-correcting via `residue-no-stale-row`): `historical` — the five `_cc_task.md`
  prompt lines (`m1_signal_scan_cc_task.md` "NOT hermes/claudius", `weekly_pre_assembly_cc_task.md`
  "NOT hermes/claudius", `standing_research_cc_task.md` "NOT hermes/claudius" and "no hermes MEMORY store",
  `overnight_morning_report_cc_task.md` "NOT hermes/marcus") and `bin/fleet_eval_probes.json`
  "retired Discord/Hermes/Kanban design"; `live` — `bin/deliver.sh` anchors `hermes_send`, `HERMES_BIN`,
  `.hermes/hermes-agent/venv/bin/hermes`, `.hermes/hermes-agent/venv/bin/python`, `.local/bin/hermes`,
  `hermes_cli.main send`, `hermes send --to discord` (all `discord-cutover`); `bin/local_tier_eval.sh`
  anchors `HERMES_BIN`, `"$HERMES"` (both `local-tier-eval`).
- `tests/fixtures/hermes-residue/tree-red/bin/x.sh` (one uncommented `hermes send --to discord` line) +
  `tree-red/allowlist.tsv` (empty) → `scan()` must report it; `tree-green/bin/x.sh` (the same line
  commented) + empty allowlist → clean. Synthetic, no real content.
- `design/archive/hermes-profiles-2026-09-14.md` — the record: the four profiles' facts as of deletion
  (marcus `deepseek/deepseek-v4-flash` max_turns 24 skills 46; claudius `anthropic/claude-sonnet-5`
  skills 25, the only profile granted plugin-qmd; augustus `openai/gpt-5.5` skills 23, no ZDR pin — D4;
  trajan `deepseek/deepseek-v4-flash` skills 44), store sizes and last-write dates (augustus 09-11,
  claudius 09-11, marcus 09-09, trajan 07-20), what read them (nothing but the radar dedup, rerouted),
  what the allowlist did (0 of 11 cards ever set `skills`), where the backup tarball is (§ Land-time
  step 7), and the D4 status line to be filled at land.
- `design/archive/contracts/memory-consolidation.md` — the contract moved verbatim under a three-line
  header: retired 2026-09-14 (T6.1); reason (its input, the Hermes episodic store, is retired — the
  contract's own retirement condition); units at `systemd/archive/`.
- `systemd/archive/memory-consolidation.service`, `systemd/archive/memory-consolidation.timer` — `git mv`
  from `systemd/`, unchanged (the archive-exclusion rule in `tests/test_workflow_coverage.py:525-543`
  turns the ExecStart subject `consolidate_memory.sh` into `retired`; the suite that named it is deleted
  in the same commit, so the orphan rule has nothing to flag).

## Files to delete (source)

`bin/apply_skills_allowlist.sh`, `bin/consolidate_memory.sh`, `docs/skills_allowlist.md`,
`systemd/user/hermes-gateway.service`, `tests/test_consolidate_memory.sh`,
`tests/test_working_memory_status.sh`, `systemd/memory-consolidation.{service,timer}` (moved),
`design/contracts/memory-consolidation.md` (moved). Git history keeps every byte; the archive doc
names them.

## Implementation steps (TDD, in this order; branch `feat/t6-1-hermes-residue` off `main` after T5.2)

1. `tests/test_hermes_residue.py` + `.sh` + fixtures — red on the current tree (it names ~25 live
   lines); green only at step 9. Run it after every step below to watch the count fall.
2. `bin/brave_mcp_launch.sh` + `tests/test_brave_mcp_launch.sh` — red (no launcher) → green; then edit
   `systemd/brave-mcp.service`.
3. `bin/bd_stall_radar_kernel.py` — five red tests in `tests/test_bd_stall_radar_kernel.py` → green;
   `tests/test_bd_stall_radar_smoke.sh` and `test_bd_stall_radar_kernel.sh` stay green; contract lines.
4. `bin/agent_propose.sh` — the smoke-suite edits first (red), then the four deletions; run
   `tests/test_agent_propose_smoke.sh` plus the nine `test_*_smoke.sh` and (post-T5.2)
   `tests/test_propose_receipt.sh` — all green, no exit-code change.
5. `bin/praetorium-status.sh` — status suites (`test_praetorium_status.sh`, `test_qmd_status.sh`,
   `test_brave_status.sh`, `test_fetch_status.sh`) edited red → green; delete
   `tests/test_working_memory_status.sh`.
6. `bin/local_tier_eval.sh` `-p base0`; `bin/overnight_pre_snapshot.sh`; `bin/scorecard.sh`;
   `profiles/*.env.example` (ten); `profiles/overnight_morning_report_cc_task.md` + its smoke assertion;
   `systemd/inbox-backlog-alert.service` comment.
7. Retire memory-consolidation: `git mv` the two units to `systemd/archive/`; `git mv` the contract;
   delete script + suite; drop the trajan row and the tsv row; run `tests/test_workflow_coverage.py`,
   `test_fleet_ownership.sh`, `test_contract_schema.sh`, `test_deploy_drift.sh` — green (the drift
   check itself stays red until land; the *unit tests* of it are what must pass here).
8. Delete `bin/apply_skills_allowlist.sh`, `docs/skills_allowlist.md`, `systemd/user/hermes-gateway.service`;
   `[surfaces.kanban]` blocks + `tests/test_manifest_surfaces.sh` assertion; `design/agent-model.md`;
   remaining `design/contracts/*` lines; the archive record doc; `design/fleet-suites.toml` entry.
9. `tests/test_hermes_residue.sh` green. `docs/runbook.md`, `CLAUDE.md` § Roster, `README.md:39`.
   `bash bin/verify.sh`: every suite green; the only red is `check_deploy_drift.sh` naming exactly the
   files § Land-time handles (`source-only: brave_mcp_launch.sh`, `content differs: brave-mcp.service`,
   `runtime-only: bin/apply_skills_allowlist.sh`, `runtime-only: bin/consolidate_memory.sh`,
   `runtime-only: docs/skills_allowlist.md`, `runtime-only: systemd/memory-consolidation.*`,
   `runtime-only: systemd/user/hermes-gateway.service`, `live-only: hermes-gateway.service`,
   `live-only: memory-consolidation.*` in /etc). Any other drift line is a bug in this branch.
10. Commit; PR; then § Land-time when Dave says; then § Evidence at Dave's moment.

## Test plan (fixtures only; ids anchored `(::id)` in the `.py`, `# (::id)` in the `.sh`)

- `tests/test_hermes_residue.py`: `residue-code-line-is-comment-or-live`, `residue-prose-is-listed`,
  `residue-no-stale-row`, `residue-live-is-pinned`, `residue-local-tier-on-base0`, `residue-canary-red`.
- `tests/test_brave_mcp_launch.sh`: `brave-launcher-logs-and-execs`, `brave-unit-execs-repo-launcher`.
- `tests/test_bd_stall_radar_kernel.py`: `radar-dedup-reads-state`, `radar-dedup-window`,
  `radar-dedup-absent-is-empty`, `radar-dedup-appends-one-line`, `radar-dedup-never-touches-hermes`.
- `tests/test_agent_propose_smoke.sh`: `propose-no-hermes-model`, `propose-no-episodic-store`,
  `propose-cost-delta-unknown`; every existing scenario unchanged in exit code and outcome.
- `tests/test_praetorium_status.sh` / `test_brave_status.sh` / `test_qmd_status.sh`:
  `status-brave-key-from-brave-mcp-env`, `status-no-profile-probe`, `status-no-working-memory-section`.
- `tests/test_manifest_surfaces.sh`: `kanban-block-carries-no-profile-fact`.
- Existing suites that must stay green untouched: the nine `test_*_smoke.sh`, `test_contract_exec.sh`,
  `test_workflow_coverage.py`, `test_fleet_ownership.sh`, `test_contract_schema.sh`,
  `test_deploy_drift.sh`, `test_local_tier_eval_score.sh`, `test_buzz_deliver.sh` (its mock hermes
  proves `deliver.sh` is untouched), `test_buzz_adapters.sh`, and T5.2's suites.
- Fixture strategy: every new test builds its subject in a temp dir (`mktemp -d`), points the script
  at it through the env overrides this brief adds (`BD_STALL_RADAR_STATE`, `BRAVE_MCP_LOG`,
  `BRAVE_MCP_SERVER`, `HOME` for the status and propose suites — both already run under a fake `HOME`),
  and never reads `~/.hermes`, `~/.config/**` or a live unit. No test runs `hermes`, `systemctl`
  or `npx`.

## Seam with T5.2 (rebase rule)

T5.2 owns `write_receipt()`, `BIN_DIR`, `AGENT_USAGE_JSON`, the attempt loop and the exit blocks'
order. This brief edits only: `key_usage()` and its one call site (adjacent to T5.2's loop edit — re-anchor
on `usage_before=$(key_usage)`), the `profile_cfg` block, the `MEM_DIR` lines, and the memory block
(adjacent to T5.2's PROPOSAL/NOPROPOSAL `write_receipt` line — keep T5.2's line, delete the block above
it). Do not move `log_cost` or `block_exit`. `bin/run_record.sh` and cost.log's record shape are
untouched (values change to `unknown`; keys do not).

## Land-time (gate red until done; needs sudo; Dave triggers)

Order matters: the profile deletion (7) comes after everything that stopped reading them (1-6).

1. `bin/deploy` — ships `bin/brave_mcp_launch.sh`, the edited scripts, `profiles/`, `systemd/archive/`,
   `CLAUDE.md`, `README.md`, `docs/`. Exits non-zero on the unit diff; expected until step 3.
2. Targeted `rm` of the five disowned runtime copies (precedent `c96c54a`; `--prune` is T6.3's and
   cannot be aimed): `rm ~/agent-workforce/bin/apply_skills_allowlist.sh ~/agent-workforce/bin/consolidate_memory.sh ~/agent-workforce/docs/skills_allowlist.md ~/agent-workforce/systemd/memory-consolidation.service ~/agent-workforce/systemd/memory-consolidation.timer ~/agent-workforce/systemd/user/hermes-gateway.service`.
   No `deploy-exclusions.toml` entry (the check fails an entry that outlives its subject).
3. `sudo cp systemd/brave-mcp.service /etc/systemd/system/brave-mcp.service && sudo systemctl daemon-reload && sudo systemctl restart brave-mcp.service`
   — the one live restart; the daemon is `enabled`+`active` today and the Buzz fleet that reads it is
   stopped (MEASURED 2026-09-14), so the window is harmless. **This is the "changed unit ran once
   live".**
4. Read it: `journalctl -u brave-mcp.service -n 20` (no error, the npx server banner) and
   `tail -1 ~/agent-workforce/logs/brave_mcp.log` shows `launch pid=… key=set(len=N)`, and
   `curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8766/mcp` answers (any HTTP code; a
   refused connection is the failure). Then `bin/praetorium-status.sh` → "Research MCP (Brave)" reads
   `key : set`, `endpoint : up`.
5. `sudo rm /etc/systemd/system/memory-consolidation.service /etc/systemd/system/memory-consolidation.timer && sudo systemctl daemon-reload`
   (the timer is already `disabled/inactive`; nothing is stopped). The two `.bak*` siblings in /etc are
   ignored by the drift check — remove them too or leave them, Dave's call.
   `rm ~/.config/systemd/user/hermes-gateway.service && systemctl --user daemon-reload` (already
   `disabled/inactive`; user scope, no sudo).
6. **Before deleting marcus:** append the alias block (§ Notes, verbatim) to
   `~/.hermes/profiles/base0/config.yaml`. Check: `grep -c 'ollama_local' ~/.hermes/profiles/base0/config.yaml`
   ≥ 2. (Not a repo file; a documented one-time edit, the last of its kind.)
7. **Dave confirms, then:** `tar czf ~/OUTBOX/hermes-profiles-retired-$(date +%F).tgz -C ~/.hermes/profiles marcus claudius trajan`
   (the dirs hold `auth.json`, `state.db`, `sessions/` — outside every repo, mode 600 the tarball) and
   `rm -rf ~/.hermes/profiles/{marcus,claudius,trajan}`. `ls ~/.hermes/profiles/` → `augustus base0 default leantest`.
   Fill the archive doc's tarball path and D4 line.
7b. **Only when D4 = delete:** add `augustus` to the tarball and `rm -rf ~/.hermes/profiles/augustus`;
   `ls` → `base0 default leantest`; D4 closes. **When D4 = pin:** Dave sets `only: ["azure"]` in
   `~/.hermes/profiles/augustus/config.yaml`; the profile stays on disk, read by nothing.
8. `bash bin/verify.sh` — green; drift clean.
9. `~/CLAUDE.md` (box root, outside this repo, no sudo): § Buzz — the sentence "the Hermes profiles
   behind the timer fleet are owned by `~/dev/agent-workforce/CLAUDE.md` § Roster" → "the Hermes profiles
   were deleted 2026-09-14 (T6.1); § Roster there says what remains". One line.
10. Commit; push; one line in `docs/dev-plan-2026-09.md` T6.1 row: done, MEASURED `ls ~/.hermes/profiles/`,
    D4 state.

## Evidence (Dave's moment, not development)

`sudo systemctl start local-tier-eval.service` — the timer stays disabled; $0, Ollama only, no egress,
up to ~66 min (11 tasks × 6 min timeout). Proof: `journalctl -u local-tier-eval.service -n 30` shows
`local-tier eval starting` and 11 `-> PASS|FAIL` lines with no `profile not found`/`unknown alias`
error; `tail -11 ~/logs/local-tier-eval/history.psv` carries today's stamp and `local` in column 3.
Pass/fail counts are not the gate — the profile reroute is. If `-p base0` errors, the fallback is
step 6 done wrong (the alias block), not a reason to restore marcus.

## D4 (Augustus's ZDR pin) — executable with it undecided

Everything in this brief proceeds without D4. Exactly one step waits: **Land-time 7b**, the deletion of
`~/.hermes/profiles/augustus`. Until then `ls ~/.hermes/profiles/` reads `augustus base0 default leantest`,
`design/archive/hermes-profiles-2026-09-14.md` carries `D4: open`, and `tests/test_hermes_residue.sh`
is unaffected (it scans the repo, not `~/.hermes`). Nothing in the repo reads the augustus profile after
step 4 of § Implementation, so a pin decision keeps a file for a runtime that no longer exists — that is
the fact D4 decides on.

## Out of scope / do not touch

- `bin/agent_propose.sh` T5.2 regions (`write_receipt`, `BIN_DIR`, `AGENT_USAGE_JSON`, the attempt loop
  :378-414 (the `while`; :376-377 `usage_before=$(key_usage)` is this brief's), the exit blocks' order); `bin/cc_run.sh`, `bin/cc_envelope.py`, `bin/propose_receipt.py`,
  `bin/content_run_evidence.py`, `bin/receipt_sweep.py`, `bin/interaction_receipt.py`,
  `bin/contract_exec.py`, `bin/workflow_receipt.py`, every `bin/run_*_cc.sh`,
  `bin/content_change_dispatch.sh` (comment :105 is inert) — **T5.2**.
- `bin/control_room_api.py`, `bin/control_room_*.py`, `bin/control_room_ui/**`, `bin/control_room_serve.sh`,
  `systemd/control-room.service`, `design/benefit-ledger.toml` — **T5.3**; the broker and its unit —
  **T5.3a**; the PR generator — **T5.3b**. T5.3a also adds a `| Retry |` Identity row to
  `design/contracts/{knowledge-digest,standing-research,m1-signal-scan}.md`, which this brief edits at
  other lines — keep both.
- `bin/deliver.sh`, `bin/buzz_routes.env`, `bin/buzz_producers.tsv`, `bin/delivery_receipt.py`,
  `bin/delivery_common.sh`, `bin/buzz_publish.sh`, `bin/workflow_incidents.py`,
  `systemd/workflow-incidents.*` — **T5.3c**; `deliver.sh`'s `hermes_send` is the **Discord cutover**'s
  (`bin/audit_buzz_dual_run.sh` is its evidence), a Dave decision, and is allowlisted `live` here.
- `bin/run_standing_research_topic_cc.sh`, `run_content_strategy_cc.sh`, `run_faceless_content_cc.sh`,
  `bin/deploy --prune`, the eleven deferred exclusions — **T6.3**. `design/workflow-registry.md` — **T6.4**.
- `design/archive/**` (records), `profiles/archive/**`, `systemd/archive/**` contents other than the two
  units this brief adds; `config/job-overrides/archive/**`.
- Any timer enable/start/stop; the twelve paused units; `agent-workforce-auto-sync.timer`;
  `buzz-agent@*`; `qmd-mcp`; `~/.hermes/.env`, `~/.hermes/config.yaml`, `~/.hermes/profiles/default`,
  the `hermes` CLI and venv (the Discord leg and local-tier-eval still exec them).
- `~/.config/**` except the two documented land actions (step 5's user unit; step 6 is `~/.hermes`).
- `bin/audit_buzz_dual_run.sh`, `bin/deliver_report.sh`, `bin/deliver_proposal.sh`, `bin/run_record.sh`.

## Notes / preconditions

Decisions (each with its reason, once):
- **Retire the episodic store, do not reroute it.** Its only writer is the runner's fallback line, its only
  reader is the radar's private dedup (rerouted), the CC prompts already tell the model there is no store,
  and T5.1 receipts are the per-run record. trajan.toml said "retire the timer or repoint MEM_DIR; do not
  do both" — retire.
- **Retire memory-consolidation as a workflow, not just its timer.** A pruner whose input this brief
  deletes has met its own contract's retirement condition by construction; leaving it `standing` would be a
  row T5.4 cannot judge on evidence. Precedent for the mechanics: the six units in `systemd/archive/`.
- **Radar dedup gets a repo-owned JSONL state file.** The dedup is real (contract :49); `var/` is where run
  state lives (`content_picked.state`, `workflow-receipts/`); JSONL over the `§`-delimited Hermes format
  because nothing else speaks it now. The 3-day window has already expired since the 09-11 pause, so
  nothing is migrated.
- **`key_usage()` goes.** The T5.2 seam handed it to this brief; the probe measured a key the Hermes
  runtime spent and nothing else does, so its 0.000000 is the frozen-zero lie the plan names.
  `unknown` is what `log_cost` already writes when the probe is skipped — no new value, no reader change.
- **`model=unknown` in cost.log, not a new env knob.** The receipt has the measured model (T5.2); adding
  `AGENT_MODEL` would be a knob nobody sets. `unknown` replaces a confidently wrong value on augustus rows.
- **brave-mcp launcher moves into the repo rather than being inlined into `ExecStart`.** It logs whether
  the key reached the process, which is the one thing `praetorium-status.sh` reads back; a bare
  `ExecStart=npx …` would lose that.
- **`hermes-gateway.service` is deleted, not archived.** It was installed by `hermes gateway install`,
  not authored here; archiving it would feed the coverage test an ExecStart subject (`python`) that
  means nothing. Git history is the record.
- **`local-tier-eval` moves to base0; base0 receives marcus's alias block.** The alias carries
  temperature 0 and `reasoning_effort: none` — the determinism the t1 triple-run measures. Editing base0's
  config.yaml is a live-file action of the kind this brief retires, done once at land, documented here.
- **Two `live` rows, pinned.** The Discord leg and local-tier-eval are the whole of Hermes's remaining
  job on this box; the test names each with the decision that retires it so a third cannot arrive
  unnamed. The card's "only historical notes" is met for everything this task owns; the two live lines
  are owned by other decisions and the brief says so rather than rewording them past the grep.
- **The allowlist is small by construction.** Comment lines in code files are inert by rule (that is what
  "historical note" means and what the existing smoke suites already assert); the allowlist carries only
  prose lines, the JSON string and the live rows, and `residue-no-stale-row` self-clears it.
- **`overnight_morning_report_cc_task.md:90-91` is retired, not kept as history.** It is an instruction
  to inspect a host that no longer exists — a phantom-blocker generator, the shape the same file's smoke
  suite exists to prevent.
- **`profiles/*.env.example` commented-out `hermes -z` lines stay.** They are comments, marked NOT A
  REVERT PATH, asserted uncommented by the smoke suites, and two of them have no copy in
  `config/job-overrides/archive/`.
- **Docs outside the gate are updated where they state the retired mechanism as live** (runbook tables,
  CLAUDE.md roster, contracts' side-effect bullets), and left alone where they narrate history.

Verbatim alias block for base0 (`~/.hermes/profiles/base0/config.yaml`, land step 6; copied from
marcus's config.yaml, which is deleted in step 7 — this brief is the surviving copy):
```
# T6.1 (2026-09-14): moved here from ~/.hermes/profiles/marcus/config.yaml so
# bin/local_tier_eval.sh can run -p base0. Profile configs replace the global config
# rather than merging, so the aliases and providers must be declared per profile.
model_aliases:
  local:
    model: qwen3-64k
    provider: custom:ollama_local
    context_length: 65536
  local-big:
    model: gpt-oss-64k
    provider: custom:ollama_local_big
    context_length: 65536
custom_providers:
  - name: ollama_local_big
    base_url: http://localhost:11434/v1
    api_mode: chat_completions
    extra_body:
      reasoning_effort: high
      temperature: 0
  - name: ollama_local
    base_url: http://localhost:11434/v1
    api_mode: chat_completions
    extra_body:
      reasoning_effort: none
      temperature: 0
```

MEASURED 2026-09-14 (read-only): 133 `hermes` lines in the gate set; `~/.hermes/profiles/` =
`augustus base0 claudius default leantest marcus trajan` (marcus 165M, augustus 70M, claudius 60M,
trajan 37M — `auth.json`, `state.db`, `sessions/`, config backups; no key-named field in any config.yaml);
MEMORY.md last writes augustus/claudius 2026-09-11, marcus 09-09, trajan 07-20; `memory-consolidation.timer`
and `local-tier-eval.timer` `disabled/inactive`; `brave-mcp.service` `enabled/active` with
`ExecStart=/home/dave/.hermes/bin/brave_mcp_launch.sh`; `hermes-gateway.service` `disabled/inactive`,
file present in `~/.config/systemd/user/` and `~/agent-workforce/systemd/user/`; `~/.hermes/.env` holds
`DISCORD_BOT_TOKEN`, `DISCORD_HOME_CHANNEL`, `BRAVE_API_KEY`, `OPENROUTER_API_KEY` (names only);
delivery receipts: discord `ok` 358, `failed` 41, `skipped` 20, last ok 2026-09-11T07:00:41Z;
local-tier-eval last ran 2026-09-11T11:17 on `-p marcus -m local`; cost.log `cost_usd_delta`:
344 × `0.000000`, 5 × `unknown`, 3 real values, all since 2026-08-01; no `buzz-agent@*` instance loaded;
`~/.config/buzz-team/{verify-fleet,check-loaded}.sh` contain no `hermes`.

Preconditions: T5.2 merged to `main` (`bin/propose_receipt.py` present) before branching; `python3`
with `tomllib` (3.14 here); `tests/fixtures/contract-exec/` untouched; no credential is read by any
step in § Implementation — the one deny-listed path this brief names (`brave-mcp.env`) is read by
`praetorium-status.sh` at runtime as `dave`, and by tests only as a fixture path under a fake `HOME`.
