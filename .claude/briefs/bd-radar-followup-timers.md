# Brief: wire bd-stall-radar + bd-followup-drafts to timers (owner: claudius)
**Date:** 2026-09-01   **Verify:** `bash bin/verify.sh`

Authorized by Dave's D1 decision §7.5 (design/workflow-registry.md, commit `ed568f8`):
"WIRE TO TIMERS". Both jobs are ~80% built and dormant — the work is closing the last
gaps, not greenfield.

## Current state (verified 2026-09-01, live box)
- `systemd/bd-stall-radar.{service,timer}` and `systemd/bd-followup-drafts.{service,timer}`
  exist in the repo, are NOT installed in /etc (`ls /etc/systemd/system/ | grep bd-` is
  empty). Timers: radar Sun–Thu 23:00, followup Sun–Thu 23:30 (one slot later, on purpose —
  the unit comments explain the flock-collision and radar-consumption reasoning; keep them).
- `bin/run_bd_followup_drafts_cc.sh` exists (Opus 5, headless CC, vault_sync_guard-gated,
  no MCP by design). There is NO `run_bd_stall_radar_cc.sh` — the radar has only the
  hermes-era invocation in `config/job-overrides/bd_stall_radar.env.example`, and hermes
  cron is retired. `config/job-overrides/bd_followup_drafts.env.example` does not exist.
- Task files `profiles/bd_stall_radar_task.md` and `profiles/bd_followup_drafts_cc_task.md`
  are current (REST-only Notion, correct data-source ids).

## Acceptance criteria
- `bash bin/verify.sh` green.
- `bin/run_bd_stall_radar_cc.sh` exists, follows the `run_m1_signal_scan_cc.sh` /
  `run_bd_followup_drafts_cc.sh` idiom (agent_propose.sh is the harness; this script is
  only the exec'd "brain").
- `systemd/bd-stall-radar.service` carries `OnFailure=agent-alert@%n.service` (currently
  MISSING; its sibling and every comparable job have it — without it a nightly failure is
  silent).
- Both `.env.example` files under `config/job-overrides/` describe the CC runtime and set
  `AGENT_PROFILE=claudius` — NOT a model-named profile. AGENT_PROFILE keys the episodic
  memory dir; a model-named profile silently logs `memory=no-store` (66 runs of m1 proved
  it), and the radar task DEPENDS on run-to-run memory ("do not re-flag ... last 3 days").
- Units installed to /etc, daemon-reloaded, and each service run ONCE live with its output
  checked (see Deployment order) — `Persistent=true` never re-fires a fired-and-failed
  slot, and `active`+`enabled` proves nothing about whether the run can produce output.
- Timers enabled iff the live-run probe passed.
- `design/workflow-registry.md` §4: flip both bd rows from "DECIDED: wire to timer" to
  wired + date once live.

## Files to create
- `bin/run_bd_stall_radar_cc.sh` — copy the shape of `run_m1_signal_scan_cc.sh`:
  `--model sonnet` (radar is read-and-flag, no drafting; followup keeps Opus),
  `--permission-mode bypassPermissions`, cd into `$HOME/agent-worktrees/inbox`, exec
  claude with `profiles/bd_stall_radar_task.md` as prompt. Tool surface:
  `Bash,Read,Write,Glob,Grep` (needs curl for Notion REST via Bash; no WebSearch).
  qmd: the task's step 2 says "qmd is the only way to read 04_operations/" — that was
  written for the hermes runtime. Do NOT wire an MCP config; instead amend the task file's
  step 2 to read `~/vault/04_operations/current_priorities.md` off disk (the symlink is
  the sanctioned live-mirror read path; `run_bd_followup_drafts_cc.sh` documents the same
  no-MCP-by-design choice) and declare `AGENT_MCP_DEPS=none` in the env example.
  No vault_sync_guard for the radar (it only flags inward; nothing leaves the box) —
  match what the unit already assumes.
- `config/job-overrides/bd_followup_drafts.env.example` —
  `AGENT_TASK_SLUG=bd-followup-drafts`, `AGENT_PROFILE=claudius`, `AGENT_MCP_DEPS=none`,
  `AGENT_RUNTIME_CMD=$HOME/agent-workforce/bin/run_bd_followup_drafts_cc.sh`.

## Files to modify
- `config/job-overrides/bd_stall_radar.env.example` — replace the hermes invocation with
  the CC runner (same four vars as above, slug `bd-stall-radar`, runtime
  `run_bd_stall_radar_cc.sh`). Keep the "non-secret wiring only" header comment.
- `systemd/bd-stall-radar.service` — add `OnFailure=agent-alert@%n.service` in [Unit].
- `profiles/bd_stall_radar_task.md` — step 2 qmd→disk-read amendment (above); leave every
  guard clause (Stage guard, parked-deal guard, no-Notion-writes rule) byte-intact.

## Deployment order (order is load-bearing)
1. Repo edits above; `bash bin/verify.sh`; commit IMMEDIATELY (auto-sync commits any dirty
   tree every 15 min with a generic message — it already grabbed one registry commit today).
2. `bin/deploy` — ExecStart points at `/home/dave/agent-workforce/` (deployed copy); a
   runner that exists only in the source repo makes the unit structurally incapable of
   running. Deploy never writes /etc, so step 3 is a separate act.
3. `sudo cp systemd/bd-stall-radar.{service,timer} systemd/bd-followup-drafts.{service,timer} /etc/systemd/system/ && sudo systemctl daemon-reload` (sudo is passwordless).
4. Env provisioning gate: the REAL override files live in `~/.config/agent-workforce/`
   (deny-listed — no Claude Code session can read or write there; do not try). A missing
   file is fatal-with-alert: agent_propose.sh `block_exit`s ("AGENT_JOB_OVERRIDES set but
   file missing"). Probe instead of peeking: `sudo systemctl start bd-stall-radar.service`,
   then read `journalctl -u bd-stall-radar.service` OUTPUT (never trust exit code alone).
   - block_exit missing-env → STOP. Leave both timers disabled; print for Dave:
     `! cp ~/dev/agent-workforce/config/job-overrides/bd_stall_radar.env.example ~/.config/agent-workforce/bd_stall_radar.env`
     (and the bd_followup_drafts twin), then re-run this step.
   - Real run → check it completed AND check delivery: route=bd receipt in
     `~/logs/delivery-receipts.jsonl` (or an explicit no-stalls/no-pack decline in the run
     output — a decline is a valid outcome, not a failure).
5. Repeat the single-run probe for bd-followup-drafts.service. Note: its
   vault_sync_guard.sh REFUSES on a stale vault mirror — with the sync outage only just
   repaired, a guard refusal is CORRECT behavior; report it, don't bypass it.
6. Only after both probes: `sudo systemctl enable --now bd-stall-radar.timer bd-followup-drafts.timer`, confirm with `systemctl list-timers | grep bd-`, update the registry rows,
   commit.

## Test plan
- `bash bin/verify.sh` (bash -n + shellcheck error-severity over bin/ and tests/) covers
  the new runner script.
- The two live single-run probes in Deployment order ARE the integration test — assert on
  journal output + delivery receipt, per the readiness-report trap (exit codes and
  timer-enabled state are not evidence).

## Out of scope / do not touch
- `.claude/briefs/current.md` — occupied by an in-flight Marcus brief (`d283038`).
- `~/.config/agent-workforce/**`, `~/.config/buzz-agents/**`, `~/.ssh/**` — deny-listed;
  the `!`-prefixed instructions to Dave are the only path.
- The two timers' OnCalendar values and their design comments.
- Task-file guard clauses (Stage/parked guards, no-Notion-writes, idempotency/carry-forward
  de-dup in the followup task).
- weekly-pre-assembly, m1-signal-scan, and every other timer.

## Notes / preconditions
- Owner claudius per §7.5; accountability persona, not runtime — the runtime is headless CC
  on the box subscription, same as every scheduled job since the OpenRouter pause.
- Both units ExecStartPre-touch `~/logs/run-markers/%n` and use DELIVERY_RUN_MARKER so
  "newest inbox match" is anchored to the run — keep that wiring intact.
- Radar Sonnet / followup Opus is a deliberate cost split; don't pin models in the unit
  files (model choice lives in the runner / env override).
