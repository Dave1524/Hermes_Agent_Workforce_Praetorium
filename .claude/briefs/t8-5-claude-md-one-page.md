# Brief: T8.5 — CLAUDE.md toward one page: each trap becomes a test

**Date:** 2026-09-22   **Verify:** `bash bin/verify.sh` (repo gate, `tests/*.sh` sweep + drift) and
`~/.config/buzz-team/verify-fleet.sh` (machine-level gate; source `buzz-team/verify-fleet.sh`, shipped by
`bin/deploy_buzz_team.sh`, drift-checked by `bin/check_deploy_drift.sh:24`).
**Sizes MEASURED 2026-09-22T09:41Z:** `~/dev/agent-workforce/CLAUDE.md` **23,906 B / 312 L**;
`~/CLAUDE.md` **51,270 B / 650 L** (card's 09-15 figures were 22 KB / 46 KB — both grew a KB a day).
Section weights (bytes): repo — Where things live 9,577, Roster 2,895, Hard constraints 2,850, Verification 2,731;
machine — Addressing an agent 12,202 (143 L, 24% of the file), Agent CLIs 8,332, Buzz 5,922, bridge 4,989, qmd 4,895.

## Acceptance criteria
- Card: no paragraph deleted without its assertion landing in the same commit; both files smaller than at start, sizes in the PR.
- Every row below marked **write** has its test in the PR of its cluster, red on a fixture that reproduces the trap, green live.
- `tests/test_instruction_size.sh` (cluster A) holds a **ratchet ceiling per file**, lowered in every later PR to the new
  measured size + 256 B; it is the bounding rule the card says is missing. Machine file: `box_only_with ~/CLAUDE.md`, skip line added to `tests/ci-expected-skips.txt`.
- `bin/verify.sh` green after each PR on the box (drift red on a branch only if a PR touches `buzz-team/`; deploy at land).

## Inventory — every trap paragraph, its claim, its check
Kinds: **T** trap (past mistake + the check), **P** policy (stays, Out of scope), **R** reference (not a trap; relocation is a separate card).
Coverage was checked by grep over `tests/*.sh`, `buzz-team/verify-fleet.sh` (gates 1–15, labels at `:134-614`), `bin/check_deploy_drift.sh`; graft indexes only the Python tests, so bash suites were grepped directly.

| # | Location | Mechanical claim | Existing assertion | Write | Cluster |
|---|---|---|---|---|---|
| 1 | repo § Roster :15-18; `~` § Buzz :239-246, § memory :575-580 | fleet size is never taken from prose; enumerate `buzz-agent@*` | `tests/test_fleet_turn_check.sh:90-94` (tool enumerates; prose unchecked) | meta-assert in `test_instruction_size.sh`: neither file matches `\b(four\|five\|[0-9]+) (agents\|units)\b` off a `MEASURED` line | A |
| 2 | repo § Roster :36-43; `~` § layout :48-53 | no `~/.hermes`, `~/.local/bin/hermes`, `ollama` on the box | `tests/test_hermes_residue.sh` scans the tree only (`tests/test_hermes_residue.py:32`; 0 live-path checks) | `box_only_without` probe of the three paths in the residue suite (measured absent 09-22) | B |
| 3 | repo § Roster :44-45 | none (Vespasianus lore) | — | none; delete (`ls design/agents/` is the roster) | A |
| 4 | repo § Roster :46-50 | `discord-bot.service` staged only, never installed | none | residue suite: no `discord-bot.service` under `/etc/systemd/system` or `~/.config/systemd/user` | B |
| 5 | repo § Hard :61-72; `~` § What :17-27 and § layout :55-62 | canonical clone helper is `github_app_credential.py`; `ssh -T git@github-canonical` refused; pre-push guard installed | none. Verified 09-22: `.git/config credential.https://github.com.helper !python3 ~/.local/bin/github_app_credential.py`; ssh → `Permission denied (publickey)`; `.git/hooks/pre-push` present. **`~`:17-19 ("server does not refuse a main push", 08-12) contradicts `~`:55-60 and repo :61-72** | `tests/test_vault_credential.sh` (`box_only_with ~/dev/Obsidian_AI_Operating_System`): helper line present; hook byte-equal to `00_system/tools/hooks/pre-push`; ssh probe with `timeout 10`, SKIP without network. Prose → one bullet in each file | D |
| 6 | repo § Where :98-107 | clean tree → `Nothing to do`, no push | `tests/test_auto_sync.sh:110-120` | none; keep 1 line | C |
| 7 | repo § Where :112-118 | root-level skill dir undiscovered; missing `--plugin-dir` silent | `tests/test_pointer_skills.sh:16-19,135-143` + runner manifest-readable checks | none; keep 1 line | C |
| 8 | repo § Where :120-123 | nothing deploys itself (NUC-44) | `bin/check_deploy_drift.sh` in the gate | none; keep 1 line | C |
| 9 | repo § Where :140-146 ("Until then the sweep skipped…") | sweep amends `not_applicable: vantage` once | `tests/test_receipt_sweep.sh`, `tests/test_receipt_coverage.sh` | none; drop the history sentence | C |
| 10 | repo § Where :158-159, :194-198 | SPA source edit without rebuild is red; retire fail-closed | `tests/test_control_room_spa.sh`, `tests/test_workflow_retirements.sh` | none; drop the two history clauses | C |
| 11 | repo § Daily :207-209 | daily/eod never write `07_daily/logs/` | none (`profiles/daily_plan_task.md:52` names it read-only; no smoke asserts) | daily/eod smokes: task text names `07_daily/` only under a read section, never `Write`/`Edit`/`>>` | D |
| 12 | repo § Daily :210-217 | Notion via `notion_daily.py`; stale mirror refuses loudly | `tests/test_daily_plan_smoke.sh:25-26`, `tests/test_eod_summary_smoke.sh:31-32`, `tests/test_vault_sync_guard.sh:46-57` | none; keep 2 lines | C |
| 13 | repo § Research :219-221 | full model name, never `opus` alias | 9 smokes, e.g. `tests/test_standing_research_smoke.sh:151`, `test_bd_followup_drafts_smoke.sh:69-70` | none; drop the clause | C |
| 14 | repo § Research :224-226, :239-241 | proposal or `DECLINE:` — the 402 ten days | `tests/test_proposal_or_decline.sh:3,61-68` | none; drop the history | C |
| 15 | repo § Research :233-238 | jobs write `_inbox/agents/**` only | 8 smokes grep `_inbox/agents`; `tests/test_s2_containment_claim.sh` | none; drop the "until 2026-09-05 this line cited" sentence | C |
| 16 | repo § Research :242-245 | Contradictions section is a standing instruction | `test_{standing_research,raw_ingest,knowledge_digest}_smoke.sh` grep `Contradictions` | none; keep 1 line | C |
| 17 | repo § BD :255-258 | none (origin story) | — | none; delete | A |
| 18 | repo § BD :259-274 | no elapsed-time claims; Prospect only; `target: none` | `test_bd_followup_drafts_smoke.sh:90-94,131`; `tests/test_bd_stall_radar_kernel.py:48-54,110-112` | none; 3 lines, drop both histories | C |
| 19 | repo § Verification :281-295 | drift loop inverts; off-box skips diffed | `check_deploy_drift.sh`; `tests/ci-expected-skips.txt` + `verify.yml` | none; keep 3 lines | C |
| 20 | repo § Verification :296-306 | `assert()` scopes pipefail off; **every suite carries `yes \| grep -q y`** | **false as written**: 9 bash suites define `assert()` without `set +o pipefail` and carry no canary (`test_agent_alert, test_brave_status, test_content_change_dispatch, test_fetch_status, test_ops_view, test_qmd_status, test_opencode_agents, test_opencode_agents_live, test_opencode_observability`); 36 thin `.py` wrappers carry none (no `assert()`, exempt) | `tests/test_suite_conventions.sh`: every `tests/test_*.sh` defining `assert()` scopes pipefail inside it and carries the canary; fixture with a bare `assert()` is red. Fix the 9 in the same PR. Paragraph → 2 lines + issue link | E |
| 21 | repo § Verification :307-313 | principle (degrade direction) | — | P-like; keep 2 lines (drops when upstream #12 lands) | — |
| 22 | `~` § What :30-31 | no reference to `~/dev/vault-boxsafe` | none. Measured: only `docs/nuc23_approval_outcomes_macside.md` (historical) | residue suite pattern `vault-boxsafe` over `bin/ systemd/ buzz-team/ config/` + live `~/.config/systemd/user` | B |
| 23 | `~` § layout :43-47 | `~/vault` symlink never recorded in units/configs/gitdirs | none. **Live state breaks the rule**: `systemd/qmd-mcp.service:5`, `qmd-refresh.service:16` (`ConditionPathExists=/home/dave/vault/.git`), `~/.config/qmd/index.yml:8`; inbox gitdir is resolved | Dave decides: assert (and fix three files) or delete the rule. Not shipped until decided | D (gated) |
| 24 | `~` § layout :62-65 | `Host github.com` → `~/.ssh/id_agent_workforce` | none | `ssh -G github.com \| grep -q id_agent_workforce` in `test_vault_credential.sh` (reads ssh's output, not the denied file) | D |
| 25 | `~` § CLIs :80-86 | `~/AGENTS.md` → `.codex/AGENTS.md` symlink | none (`test_instruction_scaffolding.sh:55-56` is a comment). Verified 09-22: symlink present | scaffolding suite, `box_only_with ~/.codex`: `readlink ~/AGENTS.md` = `.codex/AGENTS.md` | A |
| 26 | `~` § CLIs :87-100 | thin-pointer invariant ("now asserted rather than remembered") | `tests/test_instruction_scaffolding.sh:197-217` | none; 14 lines → 2 | A |
| 27 | `~` § CLIs :101-112 | managed settings present, drift-checked | `bin/check_deploy_drift.sh:692-704`; `tests/test_fleet_capabilities.sh:299` | none; policy sentence + pointer stay (P) | A |
| 28 | `~` § CLIs :113-131 | `default_permissions = "praetorium"`; `[permissions.praetorium.network] enabled = true`; no `/etc/codex/requirements.toml` deny_read; `codex sandbox -- ls ~/.ssh` denied | **none** (0 hits in `bin/ buzz-team/ tests/`). Verified 09-22: `config.toml:21,75`; requirements.toml absent | verify-fleet gate 16 `codex-profile`: the four checks above (`codex sandbox` costs one bwrap, no model turn) | F |
| 29 | `~` § CLIs :134-166 | HA scope, linear auth, Drive id, google-docs re-auth | — | R; not traps. Relocate `:140-166` (27 L) to `docs/mcp-connectors.md` — separate card | — |
| 30 | `~` § qmd :175-189 | no doc count without `MEASURED` | none | row 1 meta-assert, pattern `[0-9]+ documents` | A |
| 31 | `~` § qmd :190-197 | `get` fuzzy-matches; CLI WAL fails in sandbox | none | none — asserting a defect exists guards nothing; 2 lines stay | — |
| 32 | `~` § qmd :198-207; § Debugging :587-591 | config inert until reload: `ExecMainStartTimestamp` ≥ mtime | verify-fleet gate 7 `:286-318` + `check-loaded.sh:126` — **`buzz-agent@*` only**; nothing covers `qmd-mcp` vs `~/.config/qmd/index.yml` | `tests/test_qmd_status.sh` live half: `systemctl show qmd-mcp -p ExecMainStartTimestamp` ≥ `stat -c %Y index.yml`, `box_only_with` | F |
| 33 | `~` § qmd :208-213 | `vendor/` dropped by `store.js:947` | `bin/fleet_eval_probes.json:86` index-gap probe | none; 1 line + OUTBOX pointer | C |
| 34 | `~` § qmd :214-228 | agent tool namespace; two Brave sites | gates 15 `:567-614`, 13 `:437-459` | none; 3 lines | C |
| 35 | `~` § Buzz :256-274 | check-loaded `INFO` not `DEAD`; moved 09-06; drift-checked | `tests/test_check_loaded.sh:78`; drift | none; 2 lines | C |
| 36 | `~` § Buzz :272-283 | harness is claude-agent-acp not goose; BADAUTH is a live probe | gate 2 `:142`; `tests/test_check_loaded.sh:120-123`, `check-loaded.sh:86` | none; 2 lines | C |
| 37 | `~` § Buzz :284-302 | a Desktop `@mention` re-wakes the Mac head → two dispatches per mention (measured 09-19) | **none** (`bin/audit_buzz_dual_run.sh` is delivery, not heads) | `fleet-turn-check.sh` gate 6 `no-doubled-turn`: per mention event id ≤ 1 interaction receipt per agent in the window (receipts carry `origin` since #60). Keep the two upstream cites, drop the narrative | F |
| 38 | `~` § bridge :309-335 | shim per agent; harness split read live; `comm=` never argv | `bin/fleet_capabilities.py check`; gates 2, 14 `:551-565` | none; keep the `ps -o comm=` loop, 3 lines | C |
| 39 | `~` § bridge :336-345, :354-374 | augustus namespace outage; S1 leak "measured before it landed" | gate 9 `:327-349`; gates 14/15; `tests/test_fleet_capabilities.sh` | none; 3 lines | C |
| 40 | `~` § bridge :346-353 | never widen the namespace; policy in the broker | gate 5 `:236-262` | P; stays | — |
| 41 | `~` § Grounding :375-397 | cite upstream; never validate against a dead relay | none for the dead-relay claim; not cheaply testable (a non-test by definition) | P; keep 4 lines | — |
| 42 | `~` § Addressing :398-540 | `@` menu gate, tag recovery, Keychain layout; three recorded false claims (:419, :441, :452) | none — Desktop/relay-side, untestable from the box | R; relocate to `docs/buzz-provisioning.md` in this repo (`~/.config/buzz-agents/PROVISIONING.md` is deny-listed, so cannot be the home). Separate card; **the one page is unreachable without it** | — |
| 43 | `~` § memory :547-574 | engram fetch/patch semantics | — | R + P (`patch` never `set`); keep 6 lines | — |
| 44 | `~` § Debugging :592-597 | `buzz-acp` logs UTC, journalctl local | none; `buzz-team/check-loaded.sh:52,104`, `trace-turn.sh:28` call `journalctl` without `--utc` | `test_suite_conventions.sh`: every `journalctl` in `buzz-team/*.sh` passes `--utc`; fix the three calls | E |
| 45 | `~` § Debugging :598-604 | no per-message log line; prove work by CPU | superseded: one interaction receipt per turn (`bin/interaction_receipt.py`; 62 under `var/workflow-receipts/buzz-agent@marcus/` MEASURED 09-22) | none; 1 line → receipts | C |
| 46 | `~` § Debugging :605-620 | measure per layer (`context-cost.py`); relay presence ≠ alive | `check-loaded.sh:112` RELAY, gate 1. `context-cost.py` is stale vs current prompt shape (memory `praetorium-ship-dev-plan-state`) | none; 3 lines, mark the tool stale | C |

Count: 46 rows; **37 traps** (T): **21 already asserted** (prose-only survivors; rows 6-10, 12-16, 18-19, 26, 33-36, 38-39, 45-46),
**14 need an assertion** (rows 1, 2, 4, 5, 11, 20, 22, 24, 25, 28, 30, 32, 37, 44), 2 undecided (23, 31). 9 non-trap rows (history, P, R) stay, delete or relocate.

## Files to modify
- `CLAUDE.md` (repo) — rows 1-21; `~/CLAUDE.md` — rows 22-46 (not in this repo; edited in place, size recorded by `test_instruction_size.sh` and the PR body).
- `tests/test_hermes_residue.py` + `.sh` — rows 2, 4, 22 (live probes + `vault-boxsafe`, `discord-bot.service` patterns).
- `tests/test_instruction_scaffolding.sh` — row 25. `tests/test_qmd_status.sh` — row 32. `tests/test_daily_plan_smoke.sh`, `tests/test_eod_summary_smoke.sh` — row 11.
- `buzz-team/verify-fleet.sh` — gate 16 (row 28); `buzz-team/fleet-turn-check.sh` — gate 6 (row 37); `buzz-team/check-loaded.sh`, `trace-turn.sh` — `--utc` (row 44).
- The 9 suites of row 20 — scoped `assert()` + canary. `tests/ci-expected-skips.txt` — new SKIP lines (rows 1, 5, 25, 32).

## Files to create
- `tests/test_instruction_size.sh` — ratchet ceilings (`REPO_MAX`, `MACHINE_MAX`), count-literal and doc-count meta-asserts, fixture red cases; shape of `tests/test_memory_index_budget.sh:38-125`.
- `tests/test_suite_conventions.sh` — rows 20, 44; fixture: a suite with an unscoped `assert()`, a script with bare `journalctl`.
- `tests/test_vault_credential.sh` — rows 5, 24; `box_only_with` the canonical clone.

## Test plan
- Each new assertion: red on a fixture that reproduces the recorded mistake, green live, `yes | grep -q y` canary present, off-box SKIP line matches `ci-expected-skips.txt`.
- Size: `wc -c` before/after per file in every PR body; the ratchet lowered in the same commit; `bash bin/verify.sh` green on the box after deploy.
- Fleet gates (rows 28, 37): `bin/deploy_buzz_team.sh` then `verify-fleet.sh` and `fleet-turn-check.sh` once each, detached (~10 min).

## Order of work — one PR per cluster, smallest and safest first
1. **A — prose and meta-asserts** (rows 1, 3, 17, 25, 26, 27, 30): `test_instruction_size.sh` + scaffolding symlink check; deletes ~40 L. Establishes the ratchet every later PR lowers.
2. **C — already asserted, delete the prose** (rows 6-10, 12-16, 18-19, 33-36, 38-39, 45-46): no new test; each deletion cites its row's test in the commit. Largest byte win (~200 L across both files).
3. **B — residue patterns** (rows 2, 4, 22): three patterns + live probes in the residue suite.
4. **E — suite conventions** (rows 20, 44): meta-suite + the 9 fixes + three `--utc`.
5. **D — vault credential + write boundary** (rows 5, 11, 24; row 23 only after Dave decides): reconciles the `~`:17-19 / repo :61-72 contradiction into one bullet.
6. **F — fleet gates** (rows 28, 32, 37): touches `buzz-team/`, so drift is red on the branch until deployed at land; last for that reason.

## Out of scope / do not touch
- Policy paragraphs stay: secret deny-list (`~`:101-112, :636-650), outward-action gate (repo :51-60), vault writes via `agents` (repo :73-76), publishing Mac-side (:77), secrets tree (:82-84), namespace/broker rules (`~`:346-353), engram `patch` never `set` (`~`:563-574), grounding rules (`~`:375-390), `## Verification` blocks in both files.
- Relocation of R sections (rows 29, 42, 43; ~180 L) — separate card; this brief does not move reference prose.
- `bin/verify.sh`, `bin/check_deploy_drift.sh`, existing tests' assertions (RAILS); `~/.codex/AGENTS.md`, every `AGENTS.md` pointer (scaffolding suite guards them).
- No timer, unit or fleet restart beyond the two gate runs in cluster F.

## Risks
- Trap→test alone lands both files well short of one page: rows 29+42+43 are 12–15 KB of the machine file, and cluster C is deletion of *history*, not of the rule lines. Expect ~24 KB → ~14 KB and ~51 KB → ~30 KB; one page needs the relocation card.
- Row 23: an assertion written before Dave's decision either fails live (three files record the symlink) or codifies the opposite of the paragraph.
- Row 5 contradiction: whichever bullet survives must match live state (`main` refused server-side via the App; the local hook stays as belt-and-braces).
- `~/CLAUDE.md` edits have no PR of their own (file is outside git): each cluster's PR body carries `wc -c` before/after and the ratchet commit is the record. Every `buzz-agent@*` session and every interactive `~` session loads it — a cut that removes a rule agents still rely on shows up only in their behaviour; keep rule lines, cut narrative.
- Auto-sync fires every 15 min: commit each cluster immediately or stop the timer for the batch (repo CLAUDE.md :92-107).

## Notes / preconditions
- Card acceptance and the T8.6 template (Order of work, Risks) are both honoured; status lives in Notion.
- Measured live 09-22: hermes/ollama paths absent; managed settings 622 B root-owned; codex profile selected with network enabled; canonical helper + hook present; ssh alias refused.
