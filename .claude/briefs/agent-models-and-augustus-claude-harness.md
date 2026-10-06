# Brief: pin agent models to 5.5, and move augustus from codex-acp to claude-agent-acp
**Date:** 2026-10-06   **Verify:** `bash bin/verify.sh` (repo); after land: `~/.config/buzz-team/verify-fleet.sh` and `~/.config/buzz-team/check-loaded.sh`

Requested by Dave in the trajan DM on 2026-10-06: "set the model sonnet 5.5 for all agents except
yours and marcus. Move Augustus also on the sonnet 5.5 model and therefore the acp", and then
"Yours and Marcus should be on Opus 5.5".

## Acceptance criteria
- Every buzz-agent session runs its target model, read from that agent's first new session
  transcript after the restart (method under Notes):

  | agent    | today (measured 2026-10-06)          | target              |
  |----------|--------------------------------------|---------------------|
  | marcus   | `claude-opus-5-5` via `opus[1m]`     | `claude-opus-5-5`   |
  | trajan   | `claude-opus-5-5` via `opus[1m]`     | `claude-opus-5-5`   |
  | claudius | `claude-sonnet-5-5` via `sonnet`     | `claude-sonnet-5-5` |
  | aurelian | `claude-opus-5-5` via `opus[1m]`     | `claude-sonnet-5-5` |
  | augustus | `gpt-5.5` on codex-acp, effort high  | `claude-sonnet-5-5` on claude-agent-acp |

- Every `model.conf` sets `BUZZ_ACP_MODEL` to a full model ID. No alias, no `[1m]` suffix: both
  5.5 models report a 1M context window without it.
- augustus runs `/usr/local/bin/claude-agent-acp` through `claude-agent-wrapper.sh`, with a
  rendered `agent-settings-augustus.json`: the same secret-path denies, connector denies and Stop
  receipt hook as the other four. His skills come from `skills/augustus` by `--plugin-dir`.
- `design/agents/augustus.toml` declares `harness = "claude-agent-acp"`, and every gate that keys
  off the declared harness agrees with the live unit: `verify-fleet.sh` `EXPECT_HARNESS`,
  `fleet_capabilities.py check`, and `tests/test_fleet_guards.sh`.
- The content runner reads augustus's Codex log only while his live unit runs codex-acp. A Codex
  quota error in that log can no longer block or explain a dispatch to a Claude augustus.
- After land: `verify-fleet.sh` PASS, `check-loaded.sh` clean for all five agents.
  augustus's first heartbeat completes, and his first content turn writes an interaction receipt
  under `var/workflow-receipts/buzz-agent@augustus/`. The next `fleet-turn-check` run is green.
- Rollback restores today's state with no rebuild (see Land-time steps).

## Decisions (approved by Dave, 2026-10-06)
Dave authorized updating this plan and building it in Codex after reviewing these defaults.
1. **augustus's containment.** Use the same boundary as the other Claude agents: the
   rendered settings deny-list, root-installed `managed-settings.json` secret-path denies,
   connector restrictions, charter and Stop receipt hook. Remove his bwrap namespace.
   This deliberately gives up the stronger filesystem isolation; settings denies do not
   provide equivalent protection against shell commands. Keep his Codex setup for rollback.
2. **aurelian on Sonnet.** Move him to Sonnet 5.5, following "all agents except yours and
   marcus". Rewrite his `model.conf` comment to cite this decision. Check his first reviews
   for quality and report a clear regression to Dave before restoring Opus.
3. **Scheduled runners.** Leave their model pins unchanged. Their model migration needs a
   separate brief; the 11 runner scripts are outside this change.

Implementation and review happen on `feat/augustus-claude-harness` from `origin/main`.
Deployment follows the repository's approval and merge process; live acceptance checks
are recorded after deployment, never inferred from passing source tests.

## Files to modify
- `design/agents/augustus.toml`
  - `harness = "claude-agent-acp"`; `tools = "claude-code-builtins"`; `tools_deny = []`;
    `bridge_tools` unchanged. No `plugins`: the coding-standards plugin is for builders and
    reviewers; like claudius, Augustus declares none.
  - Header comment, `[surfaces.interactive].notes` and the `buzz-agent@augustus` workflow entry:
    drop the codex-acp / bwrap / `$CODEX_HOME` claims; `skills_mechanism = "acp-wrapper"`.
  - `[[must_not]]` "send email…": cite the strict settings file and
    `tests/test_fleet_guards.sh::connector-deny`, worded like claudius.toml.
  - `[[must_not]]` "own any workflow requiring git fetch": remove under approved decision 1 (the capability returns).
- `buzz-team/agent-settings-augustus.json` — new, RENDERED by `python3 bin/fleet_capabilities.py
  render`. Never hand-written.
- `buzz-team/MANIFEST.toml` — an `agent-settings-augustus.json` row shaped like the four existing
  `agent-settings-<name>.json` rows.
- `buzz-team/verify-fleet.sh` — `EXPECT_HARNESS[augustus]=claude-agent-acp`. The codex-only
  branches (gates 5, 9 in-namespace, 15 codex skills link) then skip him by construction. Leave
  gate 16 alone: it guards Dave's interactive Codex.
- `buzz-team/fleet-turn-check.sh` — the gate 1 scope comment (`:69`) now covers augustus.
  `codex_cause` stays: it is window-bound and names nothing once his Codex log stops growing.
- `bin/run_content_via_buzz.sh` — gate both Codex reads, the pre-flight `blocking` (`:95`) and the
  post-run `codex_refusal` (`:385-405`), on augustus's live harness.
  - Read the harness from `systemctl --user show buzz-agent@augustus -p Environment --value`. Use
    `grep -o 'BUZZ_ACP_AGENT_COMMAND=[^ ]*'` only: that property also carries `BUZZ_AUTH_TAG`, so
    never log or echo the whole value.
  - Add a test seam (for example `CONTENT_AUGUSTUS_HARNESS`) so the suite never calls systemctl.
  - Unknown or unreadable harness: log one line saying so and skip the Codex reads. A missed
    reason code is recoverable; a false `quota-exhausted` block is a missed run.
- `tests/test_fleet_guards.sh` + `design/fleet-suites.toml`
  - Retire `augustus-no-claude-connectors` and `augustus-no-fetch` (`fleet-suites.toml:44,49`).
  - Add `augustus-harness-matches-manifest`: no `buzz-agent@augustus.service.d/*.conf` sets
    `BUZZ_ACP_AGENT_COMMAND`, so he inherits the template's claude-agent-acp, and the manifest
    declares the same harness.
  - `::enforced-has-test` must stay green against the edited must_not entries.
- `tests/test_fleet_capabilities.sh` — augustus now has a settings file and a MANIFEST row (`:179`
  loop, `:236` "no codex agent has a settings file", `:245` codex-side comment).
- Docs, only the lines this makes false:
  - `design/agent-model.md` `:61`, `:210`, `:364-365`, `:605`
  - `design/workflow-registry.md` `:69`; `design/eval-spec.md` and
    `design/open-decisions.md` current containment descriptions
  - `design/contracts/buzz-interactive.md` `:28`
  - `design/contracts/augustus-content.md` (executor row `:22`; keep the dated Codex incident
    history as history)
  - comment-only mentions in `bin/notion_rest.py:32`, `bin/published_corpus.py:18`,
    `buzz-team/buzz-team-mcp.py:8`, `buzz-team/buzz-notion-broker.py:5-6` where they state
    augustus's current harness

## Files to create
- `buzz-team/agent-settings-augustus.json` (rendered, see above)
- New cases in `tests/test_run_content_via_buzz.sh`, including the systemctl extraction,
  failed-read fallback, and auth-tag log exclusion. The `blocking` stub returns a live quota block:
  with harness=claude the run dispatches and records no `quota-exhausted`; with harness=codex it
  refuses exactly as today; with harness unknown it dispatches and logs the unknown.

## Order of work
1. Worktree from **origin/main**, branch `feat/augustus-claude-harness`. Local main is 1 ahead
   with Marcus's unpushed `46a891b` brief commit, which is not part of this work.
2. `tests/test_fleet_capabilities.sh`: expect augustus's settings file and MANIFEST row (red). Then
   flip `design/agents/augustus.toml`, run `fleet_capabilities.py render`, and add the MANIFEST row
   (green; `fleet_capabilities.py check` clean).
3. `tests/test_fleet_guards.sh` and `design/fleet-suites.toml`: retire the two augustus ids, add
   `augustus-harness-matches-manifest`, and edit the must_not entries. `::enforced-has-test` green.
4. `tests/test_run_content_via_buzz.sh`: the three harness cases (red). Then gate the Codex reads in
   `bin/run_content_via_buzz.sh` (green). Mutation check: remove the gate and the claude case goes
   red.
5. `buzz-team/verify-fleet.sh` `EXPECT_HARNESS`; `fleet-turn-check.sh` comment;
   `bash -n` / shellcheck through the gate.
6. Doc lines.
7. `bash bin/verify.sh` on the final head. Record `git rev-parse HEAD` beside the result.

## Test plan
- `tests/test_fleet_capabilities.sh`: render matches committed; augustus has a settings file with
  the base denies and the Stop hook, and no `enabledPlugins`.
- `tests/test_fleet_guards.sh`: `connector-deny` covers all five; `augustus-harness-matches-manifest`;
  `enforced-has-test`.
- `tests/test_run_content_via_buzz.sh`: the three harness cases; every existing case unchanged.
- `tests/test_fleet_turn_check.sh`, `tests/test_codex_turn_error.sh`: unchanged and green; the Codex
  classifier stays for rollback and for Dave's interactive Codex.
- Expected reds on the PR head, before land:
  - `check_deploy_drift.sh`, for the undeployed files;
  - Augustus settings presence and `augustus-harness-matches-manifest`, which read
    deployed settings and live drop-ins and turn green at land steps 2 and 4;
  - the known in-cgroup false fails in `test_interaction_receipt.py`.

  Anything else red is a defect.

## Land-time steps
Run after Dave merges, in this order. All box-side files are hand-edited; none is in the repo.
1. `cp -p` every `~/.config/systemd/user/buzz-agent@*.service.d/*.conf` to `*.bak-2026-10-06`.
   Also back up `~/CLAUDE.md`.
2. Deploy from a clean checkout of the merged `origin/main` head. The primary checkout has
   an unrelated unpushed commit: preserve it and reconcile its branch before trying a
   fast-forward pull, or use a clean deployment worktree. Then `bin/deploy --dry-run` → `bin/deploy`,
   then `bin/deploy_buzz_team.sh`. `bash bin/check_deploy_drift.sh` should read clean.
3. `model.conf`:
   - marcus and trajan: `BUZZ_ACP_MODEL=claude-opus-5-5`.
   - claudius and aurelian: `BUZZ_ACP_MODEL=claude-sonnet-5-5`. Rewrite aurelian's comment to cite
     decision 2.
4. augustus:
   - `mv harness.conf harness.conf.codex-2026-10-06`. systemd loads only `*.conf`, so the file
     stays on disk for rollback.
   - Add `model.conf` with `BUZZ_ACP_MODEL=claude-sonnet-5-5`.
   - Keep `context.conf` at 15 and reword its comment: the reason is now load on the shared Claude
     login, not per-token billing. Keep `logging.conf` and `auth.conf`.
5. `systemctl --user daemon-reload`. Restart one unit at a time, each only when idle (no turn line
   in 20 min, CPUUsageNSec flat). Order:
   1. augustus, as the canary: confirm `ps -o comm= --ppid <MainPID>` shows `node`, not `bwrap`;
      then `check-loaded.sh augustus`.
   2. claudius, aurelian, marcus.
   3. trajan last, detached:
      `systemd-run --user --on-active=120 --collect systemctl --user restart buzz-agent@trajan`.
      Tell Dave first.
6. `~/CLAUDE.md`: correct the lines naming augustus's harness (`:101`, `:167`, `:196-202`).
7. Verify: `verify-fleet.sh`, `check-loaded.sh`, then the per-agent model read (Notes) after each
   agent's first new turn. The hourly heartbeat supplies that turn for every agent except
   aurelian. For him, send one short probe request (any agent may address him).
   Post the evidence to Dave.

**Rollback**
- Models: restore the `.bak-2026-10-06` drop-ins, daemon-reload, restart.
- augustus: also `mv harness.conf.codex-2026-10-06 harness.conf`, `rm model.conf`, and revert the
  PR (its gates key off the manifest).
- `~/.config/codex-agents/augustus/`, his Codex login and `/usr/local/bin/codex-acp` are never
  touched.

## Out of scope / do not touch
- The scheduled runners' `--model` pins (decision 3).
- `~/.config/buzz-agents/augustus.prompt` and every `.env`: deny-listed. If the charter names
  Codex, Dave edits it (`grep -n -i codex ~/.config/buzz-agents/augustus.prompt`). So is the
  heartbeat interval, which lives in the `.env`.
- Deleting augustus's Codex home, the bwrap wrapper, `bin/codex_turn_error.py` or
  `bin/rollout_reader.py`: needed for rollback.
- Effort level (`BUZZ_ACP_EFFORT_LEVEL`) for any agent. Not requested; every agent stays on the
  model default.
- verify-fleet gate 16 (Dave's interactive Codex profile).

## Risks
- **Shared-login rate limits.** augustus's hourly heartbeats and content turns move onto the one
  Claude login all five agents and the scheduled runners use.
  - Tell: `fleet-turn-check` gate 2 failing; 429 / rate-limit retry lines in any `buzz-agent@`
    journal; an agent going silent while its unit is active.
  - Response: roll augustus back; Dave decides whether to lengthen his heartbeat in his `.env`.
- **A pinned ID resolves to a different row than intended.** The adapter maps the ID onto a picker
  row.
  - Tell: the per-agent transcript read shows a model other than the target.
  - Response: stop, restore that agent's `.bak`, report the adapter row it chose.
- **augustus's charter carries Codex-specific instructions** that no longer hold, such as
  `$CODEX_HOME` paths or a bwrap claim.
  - Tell: his first turns cite them or try those paths.
  - Response: Dave edits the charter; nothing else changes.
- **augustus now loads `~/CLAUDE.md` and the shared auto-memory pool** at `-home-dave/`, and can
  write to it.
  - Tell: new memory files written from his sessions.
  - Response: report to Dave; a dedicated `WorkingDirectory=` (aurelian's pattern) isolates him if
    wanted.
- **Containment is weaker (decision 1).** A prompt-injected Bash command that never names a denied
  path is not stopped by the matcher.
  - Tell: none reliable, which is the point of the decision.
  - Response: Dave picks the bwrap alternative.
- **aurelian's verdict quality drops on Sonnet.**
  - Tell: INCONCLUSIVE or shallow verdicts on reviews that previously passed or failed cleanly.
  - Response: report the regression to Dave before restoring his `model.conf` line.
- **The canary restart fails** (the wrapper refuses: settings or plugin unreadable, token helper
  missing).
  - Tell: `buzz-agent@augustus` restart-loops, or `check-loaded.sh` fails.
  - Response: roll augustus back immediately. The other four have not been touched yet.

## Notes / preconditions (measured 2026-10-06)
- Claude Code `2.1.291` (`/home/linuxbrew/.linuxbrew/bin/claude`); claude-agent-acp `0.64.0`.
  `claude -p --model <id>` accepted `claude-opus-5-5`, `claude-sonnet-5-5` and their `[1m]` forms.
  All report `contextWindow: 1000000`.
- `buzz-acp models --json` rows: `default`, `opus` (Opus 5.5), `fable`, `sonnet` (Sonnet 5.5),
  `haiku`, then pinned `claude-sonnet-5`, `claude-opus-5`, `claude-fable-5`, 4.x. There are no
  `[1m]` rows. `resolveModelPreference` (`dist/acp-agent.js:4981`) maps `claude-sonnet-5-5` to
  the `sonnet` row and `claude-opus-5-5` to `opus` (substring tier, version-checked against the
  display name).
- Live model per agent: no `--model` in argv and nothing at INFO in the journal. Instead, take
  `$XDG_RUNTIME_DIR/buzz-team/mcp-<agent>-<session-id>.json` (written per session by the wrapper),
  open `~/.claude/projects/*/<session-id>.jsonl`, and count `"model":"claude-…"`. That is how the
  "today" column was measured.
- augustus's Codex model comes from `~/.config/codex-agents/augustus/config.toml`: `gpt-5.5`, effort
  high. His `AGENTS.md` there is a pointer file with nothing load-bearing for Claude. Codex
  refused him over the usage limit on 09-18, 09-24/25 and 09-28. `codex_turn_error.py blocking`
  reads no block today.
- `skills/augustus/.claude-plugin/plugin.json` is already deployed. The wrapper refuses to start
  without it and without `agent-settings-augustus.json`, so land step 2 must precede step 4.
- Per-agent drop-ins are box-only. `check_deploy_drift.sh` compares user units, not user
  drop-ins, so nothing in the repo records the model values. This brief and the land report are
  the record.

## Build status (Codex, 2026-10-06)
Implementation is prepared in `/home/dave/dev/aw-augustus-claude` on
`feat/augustus-claude-harness`, based on `e30df0a1d01bc46b1ee3dd41533d9ef7e6e20074`.
It is not committed or deployed: the repository gate remains red.

- PASS: capabilities render/check, content dispatcher, fleet turn checks, Codex classifier,
  workflow coverage, and syntax/error-severity shellcheck.
- PASS: removing both Codex-read conditions from a temporary runner makes the new tests
  fail; the drop-in guard accepts an inactive backup and rejects active overrides.
- Expected before rollout: changed-path deployment drift, missing deployed Augustus settings,
  and Augustus's live Codex harness.
- Additional blockers: the App helper cannot see its credential config in this sandbox;
  the shared memory index has one entry exceeding 200 characters. Both checks fail in the
  untouched primary checkout too. Neither is waived, and no credential boundary is widened.
- Raw gate result: `bash bin/verify.sh` exited 1; log `/tmp/augustus-verify.log`.
- SPA toolchain check skipped because this worktree has no `ui/control-room/node_modules`;
  paid live OpenCode checks remain opt-in. CI installs the SPA dependencies.

The local patch, PR text and verification report are in `/home/dave/OUTBOX/` under
`augustus-claude-harness-2026-10-06.*`. Before publishing, rerun the gate from a host session
where the approved App helper can work and resolve the shared index budget violation.
Then commit only this change, push the topic branch and open the PR through `bin/gh_app.sh`.
Approval, merge, deployment and live model/receipt acceptance follow the land-time steps.

## Continuation (2026-10-06)
Dave ran `python3 bin/main_protection.py --live` from a regular host terminal and supplied
`ok: main protection and App access verified live`. The sandbox's App access failure is
therefore an execution-surface limitation rather than missing host credentials.

The one overlong shared memory index entry has been shortened while preserving its link
and lookup meaning. `bash tests/test_memory_index_budget.sh` now exits 0 with no oversized
entries. The source implementation is unchanged. A full host gate run remains required
before commit/PR, with only the documented deployment drift and Augustus live-switch
failures permitted before land.

## Host verification (2026-10-06)
Dave ran the complete gate from a regular host terminal against the staged build.
`bash bin/verify.sh` exited 1; `/tmp/augustus-host-verify.log` contains only the approved
pre-deployment exceptions: eight changed-path drift findings, missing deployed Augustus
settings, and his live Codex override. App access and the shared memory budget now pass.
The host gate ran every source suite successfully; SPA tooling and paid OpenCode live
checks have the previously documented skips. Commit and App-authored PR can proceed;
merge, deployment and live model/receipt acceptance still follow the repository process.
