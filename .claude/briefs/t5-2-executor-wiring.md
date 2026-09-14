# Brief: T5.2 — executor wiring, every run path

**Date:** 2026-09-14
**Verify:** `bash bin/verify.sh` from the repo root (includes `bin/check_deploy_drift.sh`). **Red on a
branch by construction** — this brief adds `bin/` scripts and a system unit, so the gate is green only
after the land-time steps in § Land-time. Never assume green before them.

**Depends on:** T5.1 (`bin/contract_exec.py`, `bin/workflow_receipt.py` — done), T4.5
(`logical-workflow-reconciled` — done). **Lands before T6.1** (§ Seam for T6.1).

## Gate

- Task (Notion card, verbatim): every logical standing workflow emits a joined receipt within one
  cadence or interaction; 31 entries reconcile to 30 logical workflows; no success without artifact
  or state-change evidence.
- Plan DoD item 2: every standing run path calls the executor and writes a receipt; proven on
  fixtures, and on one hand-started `knowledge-digest.service` run when Dave picks the moment.
- Standing constraint: the twelve workflow timers are disabled since 2026-09-11 and stay so. **No
  step here enables a timer.** Every test runs from fixtures. The one live run is Dave's.

## Run-path classes — the decisions

| Class | Rows | Producer | Vantage | run_id | Evidence |
|---|---|---|---|---|---|
| S2 scheduled (`agent_propose.sh`) | 10 | `write_receipt` in `agent_propose.sh` → `bin/propose_receipt.py` → executor | `run` | `$INVOCATION_ID` | proposal file / report file / `^DECLINE:` / `--failed` reason |
| S4 buzz_dispatch: `augustus-content` | 1 (+1 trigger) | same path (`AGENT_TASK_SLUG=augustus-content`) | `run` | nightly: `$INVOCATION_ID`; via dispatch: `${parent}-draft` | `page=… from=Picked to=Draft` state change or `decline_event=` from the attempt log; handoff = relay event id |
| S4 trigger: `content-change-dispatch` | the second trigger | `content_change_dispatch.sh` calls the executor itself after the child returns | `run` | `$INVOCATION_ID` | `var/content_picked.state` advanced; `handoff` → child run id |
| Platform (Trajan) | 14 | `bin/receipt_sweep.py` under NEW `workflow-receipt-sweep.timer` — **ships DISABLED** | `sweep` | the unit's last `InvocationID` (executor default) | systemd's own record of the last run (`--state-change`) or `--failed Result=…`; contract sweep checks decide |
| Interactive (`buzz-agent@*`, `kind=service`) | 5 | claude-agent-acp (4): Claude Code `Stop` hook → `bin/interaction_receipt.py` → `workflow_receipt.write()`. codex-acp (augustus): Codex `notify` → `bin/interaction_receipt.py --codex-notify <json>` → the same writer | `interaction` | Claude: `<session_id>-<last assistant uuid>`; Codex: `<thread-id>-<turn-id>` from the payload | a `buzz messages send` tool call with an ok result = `artifact`; none = `decline` with an explicit reason |

Counts after land: 32 manifest entries → 31 logical (the sweep unit is a new standing row; the
reconciliation rule is structural, the "31 → 30" in the gate is the 2026-09-11 snapshot — record the
new pair as MEASURED in the land note). If T5.3 has landed, bump `STANDING_ENTRIES`/`LOGICAL_WORKFLOWS`
in `tests/test_control_room_views.py` by one each — its `::control-room-30-of-31` pins the pair against
the real manifests.

Usage: from the runtime's own output only — the Claude Code JSON envelope captured by `bin/cc_run.sh`.
`cost.log`'s `cost_usd_delta` / `tokens=unknown` is never mapped. Hermes-runtime runs carry
`usage.status = "unavailable"`. Interactive turns: tokens measured from the transcript (Claude) or the
Codex rollout's `token_count.info.last_token_usage` (augustus), cost `unavailable` (neither carries a
price).

## Acceptance criteria

1. `bin/agent_propose.sh` writes exactly one receipt on every exit path — flock SKIP, BLOCKED, DEDUP,
   FAIL, CRASHED, VIOLATION, OPS, PROPOSAL, NOPROPOSAL — with the outcome mapping in § Outcome map;
   receipt failure is logged and never changes the script's exit code. (`propose-receipt-every-exit`)
2. The nine active CC runners exec through `bin/cc_run.sh`; with `AGENT_USAGE_JSON` unset the
   invocation is byte-identical to today (hand runs and the smoke suites see no change); with it set,
   the envelope lands at `$AGENT_USAGE_JSON` atomically and stdout carries `.result` text so
   `^DECLINE:`, `PROVIDER_ERROR_RE`, `proposal_or_decline.sh`, contract checks and
   `deliver_proposal.sh` read what they read today. (`cc-run-result-passthrough`,
   `cc-run-envelope-captured`, `cc-run-garbage-is-unavailable`)
3. An S2 receipt on a CC run has `usage.status == "measured"` with the envelope's token counts and
   `cost` from `total_cost_usd`; `model` is the envelope's `modelUsage` key when present, else the
   manifest model. A hermes run has `usage.status == "unavailable"` and null tokens.
   (`propose-receipt-usage-from-envelope`)
4. `augustus-content`: one workflow, two triggers. Nightly run → one receipt at `$INVOCATION_ID`. Via
   dispatch → the tick writes a receipt for `content-change-dispatch` (run_id `$INVOCATION_ID`,
   `handoff.event = <child run id>`) and the child writes one for `augustus-content` (run_id
   `${INVOCATION_ID}-draft`, `parent_run_id = $INVOCATION_ID`). Both land under
   `var/workflow-receipts/augustus-content/` because `logical_workflow` folds them. Quiet and
   fail-soft ticks write nothing. (`dispatch-parent-child-ids`, `dispatch-quiet-tick-no-receipt`)
5. Child outcome from the attempt log: `content-board-transition-produced-draft … page=<p> from=Picked
   to=Draft` → `artifact` via `--state-change`; `owned-reply-evidences-decline … decline_event=<id>`
   → `decline` via `--decline`; a `trigger published … run_id=<event>` line → `handoff` (actor
   `praetorium`, recipient `augustus`, event `<id>`). Neither line → executor's own "neither" →
   `failed`. (`content-evidence-from-log`)
6. `bin/receipt_sweep.py` walks `config/fleet-units.tsv` rows `status=standing kind=timer` (26 today,
   itself excluded), skips a unit whose timer is inactive (logs `paused: <unit>`, no receipt), skips a
   unit whose last invocation already has a receipt at `<workflow_id>/<InvocationID>.json` (never
   overwrites), and for the rest runs the executor at `--vantage sweep` with systemd's record as
   evidence; exit 2 refusals are logged and skipped; the sweep ends by writing its own `run` receipt
   (`--state-change "swept N: M written, K paused, J refused"`). (`sweep-one-receipt-per-invocation`,
   `sweep-paused-writes-nothing`, `sweep-never-overwrites`, `sweep-self-receipt`)
7. `systemd/workflow-receipt-sweep.{service,timer}` exist in source, are installed at land with
   `daemon-reload` only, and `systemctl is-enabled workflow-receipt-sweep.timer` reads `disabled`
   after land. (`sweep-unit-ships-disabled`)
8. `bin/interaction_receipt.py` reads the Stop-hook stdin JSON, derives the unit from
   `/proc/self/cgroup` (`…/buzz-agent@<name>.service`, override `INTERACTION_RECEIPT_UNIT` for
   fixtures), reads the turn since the last human prompt from `transcript_path`, and writes a
   receipt via `workflow_receipt.write()` under `CONTROL_ROOM_RECEIPT_ROOT`. Heartbeat turns (prompt
   equal to the heartbeat file, override `INTERACTION_RECEIPT_HEARTBEAT_FILE`) write nothing. The
   hook always exits 0 — never 2 — and never reads, prints or logs any env value.
   (`interaction-send-is-artifact`, `interaction-silence-is-decline`,
   `interaction-heartbeat-no-receipt`, `interaction-usage-summed`, `interaction-never-blocks-stop`)
8b. The same script with `--codex-notify '<json>'` is augustus's path — Codex's documented `notify`
   setting (`docs/config.md`; `codex-rs/hooks/src/legacy_notify.rs`), which appends one JSON argument
   `{"type":"agent-turn-complete","thread-id","turn-id","cwd","client","input-messages",
   "last-assistant-message"}` and spawns fire-and-forget with all stdio null — so the script never
   reads stdin or prints in this mode, only logs. Unit from `/proc/self/cgroup` as in 8 (the wrapper's
   bwrap does not unshare cgroups). Rollout at
   `$CODEX_HOME/sessions/YYYY/MM/DD/rollout-<ts>-<thread-id>.jsonl` (`CODEX_HOME` is inherited from
   the unit; glob on the thread id, never on the date). The turn is the span between the
   `event_msg/task_started` and `event_msg/task_complete` whose `turn_id` matches; a
   `response_item/function_call` inside it whose arguments run `buzz messages send` with a matching
   `function_call_output` = `artifact`, none = `decline`. Usage = the last `event_msg/token_count`
   `info.last_token_usage` inside the span (`input_tokens`, `cached_input_tokens`, `output_tokens`,
   `reasoning_output_tokens`, `total_tokens`); the notify may race the final write, so re-read up to
   three times over two seconds and fall back to `usage.status = "unavailable"`, never 0. Heartbeat
   rule as in 8 using `input-messages[0]`. Run id `<thread-id>-<turn-id>`.
   (`codex-notify-send-is-artifact`, `codex-notify-silence-is-decline`,
   `codex-notify-usage-from-rollout`, `codex-notify-missing-rollout-unavailable`,
   `codex-notify-never-fails`)
9. `bin/contract_exec.py` gains `--failed REASON`, `--decline REASON`, `--run-id ID`; every
   existing `exec-*` test still passes. (`exec-failed-flag`, `exec-decline-flag`, `exec-run-id-flag`)
10. Coverage: a fixture test walks the 31 standing rows (32 after land) and proves each maps to
    exactly one producer class and that the set of producible `workflow_id`s equals the logical set.
    (`receipt-coverage-every-standing-row`)
11. Every receipt any producer writes validates with `workflow_receipt.validate()` and reads back
    `valid` through `control_room_api.workflows()` / `runs()` — asserted in each producer's suite,
    not in a separate one. (`receipt-reads-back-valid`)
12. Evidence run (Dave's moment, § Evidence): one `sudo systemctl start knowledge-digest.service`
    yields `~/agent-workforce/var/workflow-receipts/knowledge-digest/<INVOCATION_ID>.json` with
    `usage.status == "measured"`, nine assertions, `terminal.outcome` ∈ {artifact, decline}.

## Files to modify

- `bin/contract_exec.py` — three additive flags (criterion 9). `--failed` forces `failed` and
  prepends the reason; checks still run. `--decline` sets the decline branch without a `^DECLINE:`
  line. `--run-id` overrides `INVOCATION_ID`/derived ids. Nothing else changes.
- `bin/agent_propose.sh` — see § Seam for T6.1 for the exact regions. Adds `BIN_DIR`, exports
  `AGENT_USAGE_JSON`, adds `write_receipt()`, calls it at every exit.
- `bin/run_knowledge_digest_cc.sh`, `bin/run_standing_research_cc.sh`, `bin/run_raw_ingest_cc.sh`,
  `bin/run_m1_signal_scan_cc.sh`, `bin/run_bd_stall_radar_cc.sh`, `bin/run_bd_followup_drafts_cc.sh`,
  `bin/run_daily_rhythm_cc.sh`, `bin/run_overnight_morning_report_cc.sh`,
  `bin/run_weekly_pre_assembly_cc.sh` — the `exec "$CLAUDE_BIN" …` line becomes
  `exec "$BIN_DIR/cc_run.sh" "$CLAUDE_BIN" …` (all flags unchanged; `BIN_DIR` already exists in each).
  `run_standing_research_topic_cc.sh` is retired — untouched (T6.3 prunes it).
- `bin/content_change_dispatch.sh` — export `AGENT_RECEIPT_UNIT=augustus-content`,
  `AGENT_RUN_ID=${INVOCATION_ID}-draft`, `AGENT_PARENT_RUN_ID=$INVOCATION_ID` before the in-process
  `agent_propose.sh` call; after the existing cost.log/snapshot verification, call the executor for
  its own tick receipt (criterion 4). Belt-and-braces failure branches pass `--failed "<reason>"`.
- `buzz-team/agent-settings.json` — add `hooks.Stop` → `python3 "$HOME/agent-workforce/bin/interaction_receipt.py"`
  (`timeout` 20). The file is already adopted in `buzz-team/MANIFEST.toml`; no manifest edit.
- `~/.config/codex-agents/augustus/config.toml` (augustus's `CODEX_HOME`, outside the repo and not
  deploy-managed — a land-time step, listed under § Land-time) — add
  `notify = ["python3", "/home/dave/agent-workforce/bin/interaction_receipt.py", "--codex-notify"]`.
  Read at app-server start, so it takes effect when augustus is next started. Not `hooks.json`: Codex's
  lifecycle hooks (`Stop`) need persisted trust that only the TUI grants or a root-owned
  `/etc/codex/config.toml` managed layer supplies, and an untrusted hook is skipped silently —
  MEASURED 2026-09-14 (`-c hooks.stop=…` never fired under `codex exec`, with or without
  `--dangerously-bypass-hook-trust`). `notify` needs no trust and fired on the exact augustus harness
  (codex-acp 1.1.9 → bundled codex 0.145.0 app-server, `client:"@agentclientprotocol/codex-acp"`).
- `design/agents/trajan.toml` — new `[[workflows]]` row `workflow-receipt-sweep`, `surface="platform"`,
  `status="standing"`, `trigger="daily 05:50"`, `contract="design/contracts/workflow-receipt-sweep.md"`,
  `suite=["tests/test_receipt_sweep.sh"]`, `route="ops"`, `in_repo=true`, `alerted=true`.
- `config/fleet-units.tsv` — row `workflow-receipt-sweep	system	standing	trajan	timer`.
- `design/fleet-suites.toml` — `[[suite]]` entries, `owner="fleet"`, for `tests/test_cc_run.sh`,
  `tests/test_propose_receipt.sh`, `tests/test_interaction_receipt.sh`, `tests/test_receipt_coverage.sh`,
  each with the anchored ids from § Test plan.
- `tests/test_contract_exec.py` — three new tests for the flags.
- `tests/test_agent_propose_smoke.sh` — new scenarios (§ Test plan).
- `tests/test_content_change_dispatch.sh` — scenario (b) also asserts the two receipts and their ids.
- `tests/test_workflow_coverage.py` — comment at :360 "31 entries are 30 workflows" → "32 … 31".
- `docs/runbook.md` § Job wiring — one table row for `workflow-receipt-sweep` (disabled at ship) and
  one sentence under § Deploy ordering naming its install; § S1 — one sentence naming the Stop hook.
- `CLAUDE.md` § Where things live, receipts bullet — one sentence: the four producers
  (`agent_propose.sh` / `content_change_dispatch.sh` / `receipt_sweep.py` / `interaction_receipt.py`).

## Files to create

- `bin/cc_run.sh` — `cc_run.sh <claude-bin> <args…>`. `AGENT_USAGE_JSON` unset → `exec "$@"`. Set →
  run `"$@" --output-format json` into a temp file, `cc_envelope.py <tmp> "$AGENT_USAGE_JSON"`, exit
  with claude's status.
- `bin/cc_envelope.py` — one concept: split an envelope. Valid JSON with `result` → print `result`
  (newline-terminated) and rename the file atomically to the target; anything else → print the raw
  bytes, remove any stale target, exit 0 (usage becomes `unavailable`, never a fake).
- `bin/propose_receipt.py` — one concept: an `agent_propose.sh` outcome → executor argv (§ Outcome
  map). Reads `AGENT_RECEIPT_UNIT`/`DELIVERY_JOB`, `AGENT_RUN_ID`/`INVOCATION_ID`,
  `AGENT_PARENT_RUN_ID`, `AGENT_USAGE_JSON`, `AGENT_ATTEMPT_LOG`, `AGENT_RUN_STARTED_AT`,
  `AGENT_TASK_SLUG`, `AGENT_INBOX_DIR`, `INBOX_WORKTREE`, `REPORT_DIR`, `REPORT_GLOB`;
  `CONTRACT_EXEC` overrides the executor path for fixtures. Runs the executor as a subprocess, echoes
  its stdout, exits with its status.
- `bin/content_run_evidence.py` — one concept: parse a `run_content_via_buzz.sh` attempt log into
  `{state_change, decline_reason, handoff_event}` (criterion 5). Imported by `propose_receipt.py`.
- `bin/receipt_sweep.py` — criterion 6. Imports `contract_exec` (manifest row, repo-root fallback)
  and `workflow_receipt.receipt_path`. `--tsv`, `--receipt-root`, `--now`, `SYSTEMCTL` env for
  fixtures. Logs to `~/agent-workforce/logs/receipt_sweep.log`.
- `bin/interaction_receipt.py` — criteria 8 and 8b (one CLI, two readers: `transcript_reader` for the
  Claude JSONL, `rollout_reader` for the Codex rollout; both feed one `interaction_outcome()` so the
  artifact/decline rule is written once). Reuses `skill_telemetry.records()` / `tool_uses()`.
  Logs to `~/agent-workforce/logs/interaction_receipt.log`.
- `tests/fixtures/interaction/codex-notify.json` (the argv payload) and
  `tests/fixtures/interaction/sessions/2026/09/14/rollout-…-<thread-id>.jsonl` — one real one-turn
  rollout (`session_meta`, `turn_context`, `task_started`, a `function_call`/`function_call_output`
  pair for `buzz messages send`, `token_count`, `task_complete`), plus a silent variant with no
  function call. Point `CODEX_HOME` at `tests/fixtures/interaction` in the tests.
- `systemd/workflow-receipt-sweep.service` — `Type=oneshot`, `User=dave`,
  `Environment=XDG_RUNTIME_DIR=/run/user/1000` (precedent `fleet-turn-check.service`; needed for the
  user-scope `buzz-pr-watch` row), `ExecStart=/home/dave/agent-workforce/bin/receipt_sweep.py`,
  `OnFailure=agent-alert@%n.service`.
- `systemd/workflow-receipt-sweep.timer` — `OnCalendar=*-*-* 05:50` (before daily-plan 06:00 and
  morning-report 06:15 so the morning read sees yesterday's receipts), `Persistent=true`,
  `[Install] WantedBy=timers.target`. **Not enabled by any step.**
- `design/contracts/workflow-receipt-sweep.md` — light contract, section set of
  `design/contracts/scorecard.md`; one `run` check `swept-this-run` (a `swept` line newer than
  `AGENT_RUN_STARTED_AT` in the sweep log) and one `sweep` check `timer-fired-within-window` (48h).
  Must pass `tests/test_contract_schema.sh`.
- Tests: `tests/test_cc_run.sh`; `tests/test_propose_receipt.py` + `.sh`;
  `tests/test_content_run_evidence.py` (run by `test_propose_receipt.sh`); `tests/test_receipt_sweep.py`
  + `.sh`; `tests/test_interaction_receipt.py` + `.sh`; `tests/test_receipt_coverage.py` + `.sh`. Each
  `.sh` is the gate entry point in the shape of `tests/test_contract_exec.sh`; anchors live in the `.py`.
- Fixtures under `tests/fixtures/receipt-wiring/`: `claude-envelope.json` (copy of T5.1's, plus an
  `is_error` variant), `claude-garbage.txt`, `attempt-content-draft.log`, `attempt-content-decline.log`,
  `attempt-decline.log`, `transcript-send.jsonl`, `transcript-silent.jsonl`,
  `transcript-heartbeat.jsonl`, `heartbeat.prompt`, `hook-stdin.json`, `bin/systemctl` (fake:
  answers `show <unit>.timer -p ActiveState`, `show <unit>.service -p InvocationID,ExecMainExitTimestamp,Result,ExecMainStatus`
  from a table in `sweep-state.tsv`), `fleet-units.tsv` (a five-row subset). All synthetic — the
  repo is public; no real transcript line, event id or page id.

## Outcome map (`propose_receipt.py`)

| `agent_propose.sh` exit | Executor argv | Terminal outcome |
|---|---|---|
| flock SKIP (:198) | `--skipped "previous run still active (flock)"` | skipped |
| DEDUP | `--skipped "dedup: today's proposal already exists"` | skipped |
| BLOCKED (`block_exit`) | `--failed "BLOCKED: <reason>"` | failed |
| FAIL / CRASHED | `--failed "<outcome>: rc=<rc> <last DECLINE-free line of attempt log>"` | failed |
| VIOLATION | `--failed "VIOLATION: wrote outside _inbox/agents"` | failed |
| OPS with `REPORT_DIR`+`REPORT_GLOB` | `--artifact <newest match newer than AGENT_RUN_STARTED_AT>`; none → no evidence | artifact / failed |
| OPS, task `augustus-content` | from `content_run_evidence.py` (criterion 5) | artifact / decline / failed |
| PROPOSAL | `--artifact "$INBOX_WORKTREE/_inbox/agents/<RUN_DATE>_<slug>.md"` | artifact (checks may still fail it) |
| NOPROPOSAL | no evidence flag; executor reads `^DECLINE:` from `AGENT_ATTEMPT_LOG` | decline / failed ("neither") |

Always: `--usage-json "$AGENT_USAGE_JSON"` when the file exists; `--run-id`, `--parent-run-id` when
the env is set. Unit: `AGENT_RECEIPT_UNIT` > `${DELIVERY_JOB%.service}` > log `no unit known — no
receipt` and exit 0 (a hand run outside systemd writes nothing; that is the correct answer, not a
failure).

## Implementation steps (TDD, in this order)

1. `contract_exec.py` flags — red tests in `tests/test_contract_exec.py`, then green.
2. `cc_envelope.py` + `cc_run.sh` — `tests/test_cc_run.sh` with a fake claude script that prints the
   fixture envelope / garbage / exits 1 with `is_error`.
3. `content_run_evidence.py` — `tests/test_content_run_evidence.py` from the two attempt-log fixtures.
4. `propose_receipt.py` — `tests/test_propose_receipt.py` with `CONTRACT_EXEC` pointed at a recording
   stub (asserts argv) and once at the real executor against T5.1's fixture manifest (asserts a valid
   receipt reads back through `control_room_api`).
5. `agent_propose.sh` — `write_receipt()` + calls; new scenarios in `tests/test_agent_propose_smoke.sh`:
   the mock runtime writes an envelope to `$AGENT_USAGE_JSON`; one scenario per exit path asserts one
   receipt with the mapped outcome; a scenario with the receipt adapter broken (`CONTRACT_EXEC=/bin/false`)
   asserts the exit code is unchanged.
6. Nine runners → `cc_run.sh`. Run the nine smoke suites unchanged — they must stay green.
7. `content_change_dispatch.sh` — extend scenario (b).
8. `receipt_sweep.py` + unit + timer + contract + manifest row + tsv row — `tests/test_receipt_sweep.py`
   over the fake `systemctl`: active timer with new invocation → one receipt; second sweep → none;
   inactive timer → `paused`; `Result=failed` → `failed` receipt; service row → refused, skipped.
   Then `tests/test_fleet_ownership.sh`, `tests/test_workflow_coverage.py`, `tests/test_contract_schema.sh`
   green.
9. `interaction_receipt.py` + settings hook — `tests/test_interaction_receipt.py` over the three
   transcripts with `hook-stdin.json` on stdin and the unit override; then the `--codex-notify` cases
   over the fixture rollouts with `CODEX_HOME` pointed at the fixture tree.
10. `tests/test_receipt_coverage.py`, fleet-suites entries, runbook and CLAUDE.md lines.
11. Land (§ Land-time), then evidence (§ Evidence) when Dave says.

## Test plan (fixtures only, ids anchored `(::id)`)

- `tests/test_contract_exec.py`: `exec-failed-flag`, `exec-decline-flag`, `exec-run-id-flag`.
- `tests/test_cc_run.sh`: `cc-run-result-passthrough`, `cc-run-envelope-captured`,
  `cc-run-garbage-is-unavailable`, `cc-run-unset-is-exec` (with `AGENT_USAGE_JSON` unset the fake
  claude sees no `--output-format`).
- `tests/test_propose_receipt.py`: `propose-receipt-every-exit` (parametrised over the nine outcomes),
  `propose-receipt-usage-from-envelope`, `propose-receipt-no-unit-no-receipt`, `receipt-reads-back-valid`.
- `tests/test_content_run_evidence.py`: `content-evidence-from-log` (draft, decline, neither).
- `tests/test_agent_propose_smoke.sh`: `propose-writes-receipt-on-exit` (per path),
  `propose-receipt-failure-keeps-exit-code`.
- `tests/test_content_change_dispatch.sh`: `dispatch-parent-child-ids`, `dispatch-quiet-tick-no-receipt`.
- `tests/test_receipt_sweep.py`: `sweep-one-receipt-per-invocation`, `sweep-paused-writes-nothing`,
  `sweep-never-overwrites`, `sweep-self-receipt`, `sweep-unit-ships-disabled` (the timer file has an
  `[Install]` section and no test or script enables it — grep `enable.*workflow-receipt-sweep` over
  `bin/ tests/ systemd/` is empty).
- `tests/test_interaction_receipt.py`: `interaction-send-is-artifact`, `interaction-silence-is-decline`,
  `interaction-heartbeat-no-receipt`, `interaction-usage-summed`, `interaction-never-blocks-stop`
  (malformed stdin, missing transcript, unwritable root → exit 0, one log line);
  `codex-notify-send-is-artifact`, `codex-notify-silence-is-decline`, `codex-notify-usage-from-rollout`
  (the five token fields equal the fixture's `last_token_usage`, status `measured`),
  `codex-notify-missing-rollout-unavailable` (receipt still written, `usage.status == "unavailable"`,
  outcome `decline` with reason `rollout not found`), `codex-notify-never-fails` (malformed JSON
  argument, unset `CODEX_HOME` → exit 0, one log line).
- `tests/test_receipt_coverage.py`: `receipt-coverage-every-standing-row`.
- Existing suites that must stay green untouched: the nine `test_*_smoke.sh`, `test_contract_exec.sh`,
  `test_fleet_ownership.sh`, `test_manifest_surfaces.sh`, `test_workflow_coverage.py`,
  `test_contract_schema.sh`, `test_fleet_guards.sh::connector-deny`.

## Land-time (gate red until done; needs sudo)

1. `bin/deploy` — ships the new `bin/` scripts and stages `systemd/`. It exits non-zero while the
   new unit is missing from `/etc`; that is expected until step 2.
2. `sudo cp systemd/workflow-receipt-sweep.service systemd/workflow-receipt-sweep.timer /etc/systemd/system/ && sudo systemctl daemon-reload`
   — **no `enable`, no `start`.** `systemctl is-enabled workflow-receipt-sweep.timer` must read `disabled`.
3. `bin/deploy_buzz_team.sh` — ships `agent-settings.json`. Fleet gates apply
   (`~/.config/buzz-team/verify-fleet.sh`, `check-loaded.sh`). The five agents are stopped today
   (MEASURED 2026-09-14: `systemctl --user list-units 'buzz-agent@*'` lists nothing), so the hook
   loads when they are next started — not a step here.
3b. Append to `~/.config/codex-agents/augustus/config.toml` (outside the repo; no sudo):
   `notify = ["python3", "/home/dave/agent-workforce/bin/interaction_receipt.py", "--codex-notify"]`
   — then `grep -c '^notify' ~/.config/codex-agents/augustus/config.toml` reads 1. Loads when
   augustus is next started, like step 3.
4. `bash bin/verify.sh` — green.
5. Commit; push. Record MEASURED: manifest count 32 → 31 logical, timer `disabled`.

## Evidence (Dave's moment, not development)

`sudo systemctl start knowledge-digest.service` — the timer stays disabled. Proof:
`cat ~/agent-workforce/var/workflow-receipts/knowledge-digest/$(systemctl show knowledge-digest.service -p InvocationID --value).json`
shows `usage.status == "measured"`, nine assertions, one terminal outcome;
`python3 bin/control_room_api.py` lists the run. Optional cheap check of the hook path, no agent
needed: `CONTROL_ROOM_RECEIPT_ROOT=$(mktemp -d) claude -p 'say ok' --model claude-haiku-4-5-20251001 --settings buzz-team/agent-settings.json`
then `ls` that root — proves the Stop hook fires under `claude -p`; firing under claude-agent-acp is
verified when the agents are next started. The Codex half has the same cheap check, no agent needed:
`CONTROL_ROOM_RECEIPT_ROOT=$(mktemp -d) INTERACTION_RECEIPT_UNIT=buzz-agent@augustus.service codex exec --skip-git-repo-check -C /tmp -m gpt-5.5 -c 'model_reasoning_effort="low"' -c 'notify=["python3","bin/interaction_receipt.py","--codex-notify"]' 'Reply with exactly the word ok' </dev/null`
then `ls` that root (uses Dave's own `~/.codex` auth and rollout dir; ~14k tokens on gpt-5.5).
Firing under codex-acp was proven 2026-09-14 by driving one ACP turn with `CODEX_CONFIG` carrying the
same `notify`; it is re-verified for free the first time augustus answers after his config change.

## Seam for T6.1

T5.2 touches these regions of `bin/agent_propose.sh` and nothing else in it:

- new `BIN_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"` and `write_receipt() { … }` placed
  between `log_cost()` (:118) and `block_exit()` (:169); `block_exit` gains one call line.
- `export AGENT_USAGE_JSON="${AGENT_USAGE_JSON:-$LOG_DIR/last-attempt/$run_task.usage.json}"` beside
  `export AGENT_ATTEMPT_LOG` (:245); a per-attempt `rm -f "$AGENT_USAGE_JSON"` beside the attempt-log
  truncation in the loop (:378-414 — the `while` is at :378; `usage_before=$(key_usage)` and its log
  line at :376-377 are T6.1's, not the loop's).
- one `write_receipt <OUTCOME>` line at: flock SKIP (:198), DEDUP (:420-426), FAIL/CRASHED (:428-447),
  OPS (:450-458), VIOLATION (:461-468), PROPOSAL/NOPROPOSAL after `log_cost` (:505-521).

T6.1 (Hermes residue) owns `profile_cfg`/`run_model` awk (:252-266), `MEM_DIR` and the memory block
(:312-321, :471-503), `key_usage()` (:47-69) with its call site `usage_before=$(key_usage)` (:376-377),
the `proposal_file=` line (:474 — so `write_receipt` must not read `$proposal_file`; derive the proposal
path from `$proposal_changes`/`$run_proposal`) and the hermes comments; it must not move `log_cost`,
`block_exit`, the attempt loop, or the exit blocks' order. T5.2 lands first; T6.1 rebases on it.
Also untouched by T5.2 and free for T6.1: `bin/run_record.sh`, `cost.log`'s record shape.

## Out of scope / do not touch

- Control Room view / broker / PR files — T5.3, T5.3a, T5.3b. `bin/control_room_api.py` is read
  here only (criterion 11); the `latestOutput` join (newest receipt *with* an artifact, so a decline
  or a sweep never blanks a stale artifact) is noted for T5.3, not changed.
- `bin/deliver.sh`, `bin/buzz_routes.env` — T5.3c.
- `bin/apply_skills_allowlist.sh`, `docs/skills_allowlist.md`, `bin/consolidate_memory.sh`,
  `bin/praetorium-status.sh`, `systemd/memory-consolidation.service` — T6.1.
- `bin/run_standing_research_topic_cc.sh`, `run_content_strategy_cc.sh`, `run_faceless_content_cc.sh`
  — retired; T6.3.
- `bin/deliver_proposal.sh`, `bin/deliver_report.sh`, `bin/proposal_or_decline.sh`, `bin/run_record.sh`
  — read what they read today; unchanged.
- Any timer enable/start; the twelve paused units; `agent-workforce-auto-sync.timer`.
- Cadence-miss detection (an active timer that stops firing) — a reader's question (Control Room
  health, T5.3/T5.4), not a writer's.

## Notes / preconditions

Decisions (each with its reason, once):
- **Wrapper, not `--output-format json` in the runners.** Five readers parse runner stdout as text;
  the wrapper keeps them unchanged and makes usage a side file.
- **Last attempt's envelope only.** The retry loop truncates per attempt; summing measured with
  missing is neither, so earlier attempts' spend stays in `cost.log`.
- **Adapter in Python, hook in shell.** `propose_receipt.py` is new logic (Python per standard);
  `cc_run.sh` sits in a shell exec chain.
- **Unit from `DELIVERY_JOB`.** Every unit already sets `DELIVERY_JOB=%n`; no unit file edit.
- **BLOCKED/DEDUP are not success.** BLOCKED → `failed` (produced nothing, not by design); DEDUP and
  flock → `skipped` (by design). Control Room renders both as incidents; that is the point.
- **Dispatch child id `${INVOCATION_ID}-draft`.** Parent and child share one systemd invocation; two
  receipts need two ids and the fold puts both under one workflow directory.
- **Sweep timer over a post-run hook for platform rows.** Their contracts carry only `when=sweep`
  checks; a post-run hook would receipt nothing. One receipt per invocation, never overwritten, so
  a sweep can never shadow a run-path receipt and a paused fleet writes nothing.
- **Sweep row is `standing`, timer disabled.** Same posture as the twelve paused timers; `dormant`
  means no owning suite, and this one has one. The new timer forces a manifest row anyway
  (`test_workflow_coverage.py` unit side).
- **Sweep reads `config/fleet-units.tsv`, executor reads manifests.** The deployed tree has no
  `design/`; the tsv is its materialised projection and the executor already falls back to
  `~/dev/agent-workforce`.
- **Interactive = per-turn Stop hook, vantage `interaction`.** A faked cadence would be a lie;
  `validate()` does not restrict `vantage`. Silence is `decline` with the reason spelled out: the
  transcript cannot tell deliberate sibling silence from the no-auto-publish failure.
- **augustus (codex-acp) = Codex `notify`, the same script, the same writer.** Codex has two official
  turn-end mechanisms: lifecycle hooks (`hooks.json`, `Stop`, stdin payload with `transcript_path`)
  and the older `notify` config value (argv payload with `thread-id`). Hooks are the go-forward API
  but are gated on persisted trust — granted in the TUI or by a root-owned managed layer — and a
  headless agent can do neither without sudo and a box-wide config; untrusted hooks are skipped
  silently. `notify` is documented, trust-free, per-`CODEX_HOME`, and MEASURED 2026-09-14 to fire
  under both `codex exec` and codex-acp 1.1.9's bundled 0.145 app-server. The payload lacks usage, but
  `thread-id` names the rollout, and the rollout carries per-turn `last_token_usage` and every tool
  call — strictly more than the Claude transcript gives. Revisit if a Codex release drops
  `legacy_notify.rs`; the reader seam (`rollout_reader`) is the only thing that would change.
  `receipt-coverage` therefore has no `interaction:unhooked` class: all five interactive rows are hooked.
- **Hook writes via `workflow_receipt.write()` directly.** The executor refuses `kind=service` rows
  by schema rule; the hook is the second writer of the one shape.
- **If the Stop hook does not fire under claude-agent-acp** (unverifiable with the fleet stopped),
  the fallback is a transcript sweep inside `receipt_sweep.py` over `~/.claude/projects/-home-dave/*.jsonl`
  newer than the last sweep — not built now.
- **`usage` never from `cost.log`.** `tokens=unknown` and the OpenRouter key delta are the two
  numbers the plan forbids.

MEASURED 2026-09-14 (read-only): every workflow and platform timer `disabled/inactive` except
`qmd-refresh.timer`; `agent-workforce-auto-sync.timer` disabled; no `buzz-agent@*` instance loaded;
`~/agent-workforce/var/workflow-receipts/` does not exist; `~/logs/run-markers/` holds markers for
the 14 marker-stamping units; `jq` 1.8.1 present (unused — envelope parsing is Python).

Preconditions: T5.1's fixture manifest (`tests/fixtures/contract-exec/agents/fixture.toml`) and fake
`systemctl` are reusable by import, not by edit. No credential is read anywhere: the hook must not
touch `~/.config/buzz-agents/**` or print env; tests never read a real transcript.
