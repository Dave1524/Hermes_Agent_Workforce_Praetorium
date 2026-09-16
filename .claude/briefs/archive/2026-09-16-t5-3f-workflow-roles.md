# Brief: T5.3f — Workflow roles, the Agents view, `requires` and `guards`

**Date:** 2026-09-16   **Verify:** `bash bin/verify.sh` from the repo root (includes
`bin/check_deploy_drift.sh`; extra gates and smoke: none — the gate is red on the branch for deploy
drift on exactly the `bin/` files this brief changes, and green only after `bin/deploy` + the one
service restart).

**Size:** L. **Standing constraint (Dave, 2026-09-14):** the scheduled fleet is OFF except what Dave
has resumed from the screen (MEASURED 2026-09-16 14:00 CEST: `workflow-incidents.timer` enabled and
active; every other workflow timer disabled; all five `buzz-agent@*` inactive; `buzz-notion-broker`
and `ollama.service` active — enumerate with `systemctl list-timers --all` and
`systemctl --user is-active buzz-agent@<name>`, never trust this line). No step in this brief
enables, starts, stops, pauses or resumes any workflow timer or any `buzz-agent@*` unit. The one
restart is `control-room.service`. Nothing under `/etc/control-room/`, `/usr/local/lib/control-room/`
or the allowlist is touched — this brief makes no broker change.

**Order:** after T5.3e (landed 2026-09-16, PR #44). Nothing blocks this card. Source of acceptance:
`docs/dev-plan-2026-09.md` T5.3f. Plan of record: the approved plan this brief was written from
(2026-09-16), summarised in § Design.

## Why (Dave, 2026-09-16)

The Workflows page lists every standing manifest entry in one table with product columns. Three
kinds of thing share it because they share a storage shape (a systemd unit): agent workflows (an
agent does the work, the output is for Dave), system workflows (a script keeps the box honest), and
the five `buzz-agent@<name>` runtimes — which are not workflows at all (no trigger, no end, no
output; their *turns* are the workflow and `bin/interaction_receipt.py` already receipts each one).
Two questions the screen cannot answer today: **which of these are mandatory**, and what
"Agent Workforce Auto Sync — `git add -A + commit + push of this repo`" is for. "Mandatory" is a
relationship, not an attribute: Augustus's runtime is required *while `augustus-content` is
enabled*. Nothing records that — the manifests have no dependency field, systemd declares only
soft `Wants=` lines, and `bin/run_content_via_buzz.sh` hands the task to Augustus and polls twenty
minutes without checking his unit is up.

## Acceptance criteria

1. **Every `/api/v1/workflows` row carries `surface` and `role`**, `role ∈ agent-workflow |
   system-workflow | agent-runtime`, derived from `surface` by one function
   (`bin/control_room_state.py` `role_of`: `scheduled`/`buzz_dispatch` → agent-workflow,
   `platform` → system-workflow, `interactive` → agent-runtime; any other value raises — never
   `unknown`). The SSR portfolio `<tr>` carries `data-role`. `surface` keeps its name and its place
   on every trigger (`tests/test_manifest_surfaces.sh` joins on it).
2. **`GET /api/v1/workflows` omits `agent-runtime` rows by default; `?role=all` restores them**
   (the `?lifecycle=all` convention, `bin/control_room_api.py:541`). The read model's `workflows()`
   is unchanged — `bin/incident_notify.py`, the sweep, `exceptions()`, `benefit()`, `usage()` and
   the SSR pages all read it, and `tests/test_control_room_api.py:185` still finds
   `contract-unavailable:buzz-agent@aurelian`. The SSR call at `control_room_api.py:839` passes
   `{"role": ["all"]}` so `/portfolio` still lists every logical unit (31 today; the pins in
   `tests/test_control_room_views.py:31-32` stay 32/31). `GET /api/v1/workflows/<id>` and
   `/workflows/<id>/runs` still answer for `buzz-agent@<name>`.
3. **`GET /api/v1/agents` and `/api/v1/agents/<name>`** — one item per persona manifest
   (`design/agents/*.toml`): `{name, runtime: {unit, scope, state, since}, health, lastTurn,
   turns7d, usage7d, cost7d, ownedWorkflows: [{id, role}], requiredBy: [{workflow, enabled}]}`.
   Runtime state from `SystemdReader.show` on the `interactive` entry; turns from receipts with
   `vantage == "interaction"` and `workflow_id == "buzz-agent@<name>"`; `usage7d`/`cost7d` sum
   measured receipts only and read `unavailable` otherwise (never 0); `lastTurn` is `null` with no
   receipts. Unknown name → JSON 404. `overview.summary.workflows` and the health counts cover
   non-runtime rows; `summary.agents = {total, up, down, unknown}` — an unavailable bus is
   `unknown`, not `down`.
4. **`requires` is one manifest field, resolved statically, rendered both ways.**
   `requires = ["<unit>", …]` on a `[[workflows]]` entry: a bare name is a manifest unit (scope from
   its entry); a unit outside the manifests is written `user/<unit>` or `system/<unit>` and must be
   a repo unit file under `systemd/` or `systemd/user/` **or** a key of `EXTERNAL_UNITS` in
   `bin/workflow_requires.py` (`system/ollama.service` → "Ollama package unit"), which the suite
   prints by name on every run. Both entries of one logical workflow declare the same list. Declared
   in this brief and nothing else: `augustus-content` and `content-change-dispatch` →
   `["buzz-agent@augustus", "user/buzz-notion-broker"]`; `local-tier-eval` →
   `["system/ollama.service"]`. `fleet-turn-check` declares **none** — detecting the runtimes down
   is its job. The dependent row gets `requires: [{unit, scope, workflow|null, state,
   satisfied}]` with `satisfied ∈ true | false | null` (`null` when the bus is unavailable — never
   `false` by default); the dependency — a workflow row or an agent — gets
   `requiredBy: [{workflow, enabled}]`, `enabled` = the dependent's control state is not paused.
5. **`dependency-down` is a new exceptions kind**: present for a workflow whose control state is
   not paused and whose any `requires` entry has `satisfied === false`; absent when the workflow
   is paused or the state is `null`. It is added to `KINDS` in `bin/control_room_exceptions.py:20`
   (index-sorted — position is the queue order), to `EXCEPTION_KINDS` in
   `ui/control-room/src/model/exception.ts`, and to the `by_kind` fixture in
   `tests/test_control_room_exceptions.py`. `bin/incident_notify.py` is touched only if it
   enumerates kinds by name (verify; do not widen what it alerts on without saying so).
6. **The executor refuses a run whose requirement is down.** `bin/workflow_requires.py check
   <unit>` exits 1 printing the first unsatisfied requirement (`requires buzz-agent@augustus:
   inactive`). `bin/agent_propose.sh` calls it after the MCP probes and before the run loop
   (~`:292`) through the existing `block_exit` (NUC-37: BLOCKED receipt, exit 0, the timer retries
   next tick) — a down runtime is a one-second BLOCKED, not a twenty-minute poll into FAIL.
   `bin/local_tier_eval.sh` writes no receipt; its pre-flight sits after `flock -n 9` succeeds
   (~`:182`) and does log + `exit 0`, parity with its collision path — the `dependency-down` row is
   what makes it visible. The existing ollama `is-active` at `:80-84` is input capture, not a gate;
   leave it.
7. **`guards` is a declared sentence on `platform` entries only** — `guards = "<what stops
   working when this is off>"`, one sentence, with the evidence in that entry's `notes`. It cannot
   be computed (the dependent is Dave, not a unit), so it is declared and rendered: a chip on the
   row and the detail header, and an amber notice in the Pause and Stop dialogs. Set it on the
   entries the audit found load-bearing: `workflow-incidents`, `fleet-turn-check`,
   `agent-drift-check`, `qmd-refresh`, `workflow-receipt-sweep`; **not** on
   `agent-workforce-auto-sync` (its contract calls it "purpose and hazard in one line").
   `tests/test_workflow_coverage.py` refuses `guards` on a non-platform entry and a `guards` or
   platform `what` that is not one sentence (non-empty, ends with a period, no newline).
8. **The Workflows page is two sections, "Agent workflows" and "System workflows"**, each with
   its own header and count; no `agent-runtime` row renders there. The system section drops the
   Tokens and Cost columns (always unavailable for scripts). Every row with `requires` shows a
   chip — green when all satisfied, red naming the first unsatisfied unit, grey "unknown" on
   `null`; every row with `guards` shows its chip. Filters and search still apply across both.
9. **The workflow page shows a "Requires / Required by" panel** (each requirement with unit,
   state and a link when it is a workflow or an agent; each dependent with its enabled state and a
   link), and the Pause and Stop dialogs render an amber notice (precedent
   `RetryDialog.tsx:35`) when `requiredBy` has an enabled entry or `guards` is set. Notice only —
   no client-side refusal: nothing broker-controllable is required by anything today, and the
   broker is out of scope.
10. **`/app/agents` and `/app/agents/<name>`** — a card per agent: avatar, name, runtime state chip
    with `since`, last turn (when, outcome), turns 7d, usage/cost 7d (`unavailable` rendered as
    text), owned workflows by role, "Required by …" links. The detail page adds the recent turns
    table from `/api/v1/workflows/buzz-agent@<name>/runs`. Sidebar gains **Agents**; Overview
    tiles read "Workflows N" (non-runtime) and "Agents 5 · n up"; the Agent usage rows on Overview
    and Usage link to the agent page. The Usage page's "last run per workflow" table stays
    workflows-only (its per-agent rows come from `/api/v1/usage`, unaffected). Read-only: no
    start/stop of a runtime from the screen — that is a separate decision.
11. **The 15 standing platform `what` strings read as one plain sentence each** (what it does, for
    whom), e.g. `agent-workforce-auto-sync`: "Publishes edits made on the box to GitHub every 15
    minutes so nothing on `main` stays local." The two `spent` entries stay as they are.
12. **Nothing faked, nothing broker-side.** No literal counts in the SPA; every missing value is
    `Unknown`/`unavailable`. `bin/control_broker.py`, the allowlist and `/etc/control-room/**` are
    byte-identical before and after. Verify green after land; on the branch, drift red names
    exactly the `bin/` files this brief changes; `tests/test_control_room_spa.sh` recomputes the
    stamp and, with Node, rebuilds byte-identical. No `tests/ci-expected-skips.txt` line — the new
    suite never skips (no live `systemctl`).

## Existing state (read 2026-09-16; re-verify anchors before editing)

- Manifest loader `ControlRoomReadModel._manifests()` `bin/control_room_api.py:232-254` carries every
  TOML key through (`row = dict(workflow)`); no test pins the key set or the surface vocabulary.
  `workflows()` `:384-493` groups by `logical_workflow`; per-trigger `surface` at `:419`; `purpose`
  `:435-440` = first `what` in the group, else "Produces {artifact} for {beneficiary}"; `lifecycle`
  `:451`; `control` via `control_room_state.control_for` `:97-127`; `health` `:49-62`.
  `list_workflows` `:541-554` (`?lifecycle=all`, `?q=`); `render_portfolio(model.list_workflows({}))`
  `:839`; `overview()` `:702-729` counts every standing row (31 today, five of them runtimes);
  `usage()` `:665-696` keyed by receipt `agent`; routes `_route` `:910-971` — no agents endpoint.
- Live surfaces MEASURED 2026-09-16 from `/api/v1/workflows` triggers: platform 15, scheduled 10,
  buzz_dispatch 2, interactive 5 → 31 logical rows; `summary` `{workflows: 31, paused: 22,
  unknown: 9}`.
- Hard dependencies on the box (audited 2026-09-16 from the runners): `run_content_via_buzz.sh`
  `:117-119, :155-159, :242-282` mentions augustus and polls the channel for his reply (20 min →
  exit 1); Augustus reaches Notion only through `buzz-notion-broker` (`bin/notion_rest.py:32-42`);
  `local_tier_eval.sh:129-132` runs every task on `ollama_local`. Delivery (`bin/deliver.sh:46`,
  `:357` → `buzz_publish.sh`) posts as `praetorium` and waits for nobody; `deliver_incidents.sh` →
  `incident_notify.py` imports the read model in-process (`:30, :197-200`). Only `Wants=` lines
  exist in `systemd/` (brave-mcp ×4, qmd-mcp ×1, tailscaled ×1, ollama ×1); no `Requires=`/`BindsTo=`.
- Broker: `UNIT_RE` `bin/control_broker.py:33` rejects `@`; `control_broker_allowlist.py:65-75`
  excludes `kind = service`; `tests/test_control_broker.py:167-168` pins `pause buzz-agent@marcus`
  → `bad_request`. Stdlib-only, root-installed by hand (`docs/runbook.md:370`).
- Pre-flight precedent: `agent_propose.sh` `block_exit` `:162-170`, MCP probes `:256-292`;
  `local_tier_eval.sh` `flock -n 9` `:178-182`, ollama capture `:80-84`.
- Exceptions: `KINDS` `bin/control_room_exceptions.py:20`; `classify(workflow, receipts, now)`.
- SPA: `api/schemas/workflow.ts` (`triggerSchema:27` has `surface:31`; `workflowSchema:101-129`,
  non-strict); `model/workflowRow.ts:7-47`; `model/workflowDetail.ts`; fixtures
  `api/fixtures.test-helpers.ts` (`activeWorkflow:56`, `pausedWorkflow:121`,
  `unavailableWorkflow:149`, `overview:226`); `mockFetch` `api/mockFetch.test-helpers.ts:12`;
  `renderInShell` `shell/render.test-helpers.tsx:5`; routes `router/routes.ts` (union `:3-10`,
  `NAV_ROUTES:14-20`, `matchSegments:35-49`, `routeHref:58-69`); `shell/App.tsx` (`TITLES:16-24`,
  `isNavActive:33`, `page():36-53`); `pages/Workflows.tsx`; `pages/Overview.tsx` (tiles `:34-40`,
  agent usage `:66-85`); `pages/Usage.tsx:55-76`; `components/WorkflowControls.tsx` (dialogs
  `:80-86`); `PauseDialog.tsx:32`, `StopDialog.tsx:27`; `RetryDialog.tsx:35` amber precedent;
  `useControlAction.ts:39-44` client-side refusal precedent. Build committed at
  `bin/control_room_ui/app/` + `BUILD.json`, rebuilt by `bin/control_room_build_ui.sh`.
- Tests that move: `tests/test_control_room_api.py:172-176` (ids pin includes aurelian),
  `:178-185` (finds aurelian via `list_workflows({})`), `:384` (`summary.workflows == 3`);
  `tests/test_control_room_views.py:31-32, :89-93, :152-154, :194` (no empty `<td>`).
- Docs that own the vocabulary: `design/agent-model.md` §4 Manifest schema (`:239+`, subsections
  at `:341`, `:370`); `design/workflow-registry.md` §1 (`:62-90`, the runtimes and
  `kind = "service"`); `design/contract-schema.md` ~`:288` (the fold); `docs/runbook.md` § Control
  Room; `CLAUDE.md` control-room bullet.

## Design (decided; reasons once)

- **Role, one owner, three lines** — in `control_room_state.py` beside `health`; not a module.
- **Runtimes leave the list at the HTTP layer only.** The read model is the registry every
  consumer reads; filtering there would silently change incidents and the SSR fallback.
- **`requires` resolves statically.** A live `systemctl cat` in the suite would fail on a hosted
  runner and force a skip line; `EXTERNAL_UNITS` is a two-entry map printed by name instead.
- **`satisfied` is tri-state.** The fixture bus is unavailable; `false` by default would make every
  requirement read as down in tests and `dependency-down` fire on a lie.
- **`guards` is declared.** It is the `alerted = true` class of field: prose, evidenced in `notes`,
  and the only way to answer "is this one mandatory" for a job whose dependent is Dave.
- **No broker change.** Zero timer→timer dependencies exist; the runtimes are not broker units.
  A refusal with no live case is code nobody exercises. Say so in the runbook.
- **Executor teeth over screen teeth.** The field has consequences where the run happens.

## HTTP surface (additions; nothing removed)

- `GET /api/v1/workflows[?role=all]`, rows gain `surface`, `role`, `requires[]`, `requiredBy[]`,
  `guards|null`.
- `GET /api/v1/agents`, `GET /api/v1/agents/<name>` (envelope as every other list/detail).
- `GET /api/v1/overview` — `summary.agents {total, up, down, unknown}`.
- `GET /api/v1/exceptions` — kind `dependency-down`.

## Files to modify

- `design/agents/augustus.toml`, `design/agents/trajan.toml` — `requires` (3 entries), `guards`
  (5 entries + `notes` evidence), the 15 `what` rewrites.
- `bin/control_room_state.py` — `role_of`.
- `bin/control_room_api.py` — `workflows()` row fields; `list_workflows` `role`; `:839` `role=all`;
  `overview()` split + `agents`; `agents()` / `agent_detail()`; `_route`.
- `bin/control_room_exceptions.py` — `KINDS`, `classify` reads `workflow["requires"]`.
- `bin/control_room_view_portfolio.py` — `data-role` on `<tr>`; nothing else in SSR.
- `bin/agent_propose.sh`, `bin/local_tier_eval.sh` — the pre-flight.
- `tests/test_control_room_api.py`, `tests/test_control_room_views.py`,
  `tests/test_control_room_exceptions.py`, `tests/test_workflow_coverage.py`, the suite that
  anchors the NUC-37 gate in `agent_propose.sh` (find it by `(::` anchor; add the stubbed
  `workflow_requires.py` case).
- `ui/control-room/src/api/schemas/workflow.ts`, `overview.ts`; `model/workflowRow.ts`,
  `workflowDetail.ts`, `model/exception.ts`; `api/fixtures.test-helpers.ts`; `router/routes.ts`;
  `shell/App.tsx`; `pages/Workflows.tsx`, `WorkflowDetail.tsx`, `Overview.tsx`, `Usage.tsx`;
  `components/WorkflowControls.tsx`, `dialogs/PauseDialog.tsx`, `dialogs/StopDialog.tsx`.
- `bin/control_room_ui/app/**` + `BUILD.json` — rebuilt.
- `design/fleet-suites.toml` — `[[suite]]` for the new suite, anchors named.
- `design/agent-model.md` §4, `design/workflow-registry.md` §1, `design/contract-schema.md`,
  `docs/runbook.md` § Control Room, `CLAUDE.md`, `docs/dev-plan-2026-09.md` (DONE line at land).

## Files to create

- `bin/workflow_requires.py` — parse + resolve (`EXTERNAL_UNITS`), `check <unit>` over
  `SystemdReader`; imported by the API. Stdlib only.
- `tests/test_workflow_requires.sh` + `tests/test_workflow_requires.py` (the wrapper pattern) —
  `(::workflow-requires-resolves)` every entry resolves statically and a bare non-manifest name
  refuses; `(::workflow-requires-fold-agrees)` both entries of a logical workflow agree;
  `(::workflow-requires-unit-file)` every same-scope entry appears in that unit file's
  `Wants=`/`Requires=`/`BindsTo=` (cross-manager entries exempt) and every hard
  `Requires=`/`BindsTo=` in a repo unit is mirrored back (vacuous today, the guard);
  `(::workflow-requires-buzz-handoff)` an entry whose `runner` mentions `run_content_via_buzz.sh`
  requires `buzz-agent@<owner>`; `(::workflow-requires-check)` `check` against a fake `systemctl`
  on PATH: active → 0, inactive → 1 with the line, no entry → 0. Canary `yes | grep -q y`.
- `ui/control-room/src/api/schemas/agent.ts`, `model/agent.ts`, `pages/Agents.tsx`,
  `pages/AgentDetail.tsx`, `components/RequiresPanel.tsx`, `components/RequiresChip.tsx`,
  `components/GuardsChip.tsx` — each with its co-located test.

## Test plan (TDD; red first; anchors are the `(::id)` comments registered in fleet-suites)

- API: three roles from the fixture manifests; unknown surface raises; default list omits the
  `interactive` row and `?role=all` restores it; `requires` `satisfied` `null` on the fixture bus
  and `false` with a fake inactive show; `requiredBy` `enabled` false when the dependent is paused;
  `dependency-down` only when enabled and `false`; `/api/v1/agents` shape, `lastTurn` null, 404;
  `summary.agents` buckets; the three moved pins rewritten.
- Views: `data-role` on every portfolio row; 32/31/12/11 unchanged; no empty `<td>`.
- Executor: stubbed `workflow_requires.py` → BLOCKED receipt, exit 0.
- SPA vitest: `Workflows.test.tsx` (two headings, runtime row absent, per-section counts, chips);
  `Agents.test.tsx`, `AgentDetail.test.tsx`; `WorkflowDetail.test.tsx` (panel red/green/unknown);
  `PauseDialog.test.tsx` (notice only with an enabled dependent or `guards`); `useRoute.test.tsx`
  rows for `agents`/`agent`; `exception.test.ts`.
- `tests/test_control_room_spa.sh` — stamp + byte-identical rebuild.

## Implementation steps (ordered; commit after each numbered group — the auto-sync sweep is 15 min)

1. Role + surface on the row; `data-role`; API + views tests.
2. `role` filter (+ SSR `role=all`), `/api/v1/agents`, `summary.agents`; the three pins rewritten.
3. `bin/workflow_requires.py`; `requires` + `guards` in the manifests; row fields; the suite
   registered in fleet-suites; coverage checks.
4. Pre-flight in `agent_propose.sh` and `local_tier_eval.sh` (+ suite case).
5. `dependency-down` (backend + `model/exception.ts`).
6. `what` rewrites (+ the one-sentence check).
7. SPA: schemas/models/fixtures/routes (typecheck green) → Workflows sections + chips →
   WorkflowDetail panel + dialog notices → Agents view + detail → Overview/Usage tiles and links →
   `bin/control_room_build_ui.sh`, restamp. `bash bin/verify.sh`: green except drift under `bin/`
   naming exactly the new/changed files.
8. Docs. Dev-plan DONE line waits for land.

Steps 1–2 and 3 are independent; 4 and 5 depend on 3; 7 on 2+3+5; 6 anytime.

## Land-time steps

1. Merge to `main` after the independent verify + review; pull on the box.
2. `bin/deploy` (changed `bin/*.py`, `agent_propose.sh`, `local_tier_eval.sh`, the SPA build) →
   `sudo -n systemctl restart control-room.service` → `journalctl -u control-room.service -n 20`.
   No root install, no allowlist re-render, no timer or runtime touched.
3. From the Mac, changing nothing: `/app/workflows` shows two sections and no runtime row;
   `/app/agents` shows five cards, every runtime `inactive` (fleet off), `augustus` carrying
   "Required by augustus-content (paused)"; `/app/workflows/augustus-content` shows
   `buzz-agent@augustus — inactive` red and `user/buzz-notion-broker — active` green, and
   `/api/v1/exceptions` carries no `dependency-down` (the workflow is paused);
   `/app/workflows/workflow-incidents` shows its `guards` chip and Pause its notice → **Cancel**;
   `/portfolio` still lists 31. Overview tiles change (runtimes leave the counts) — expected.
4. `bash bin/verify.sh` green, run detached (the harness memory watchdog kills a ten-minute
   background task). Dev-plan DONE line + archive this brief; commit and **push by hand**.

## Out of scope / do not touch

- Any timer enable/start/stop/pause/resume; any `buzz-agent@*` start/stop.
- `bin/control_broker.py`, `bin/control_broker_allowlist.py`, `/etc/control-room/**`,
  `/usr/local/lib/control-room/**`.
- The SSR pages beyond `data-role`; renaming `surface`; restructuring the manifests.
- Live `systemctl` in any suite; a `tests/ci-expected-skips.txt` line.
- Start/stop of a runtime from the screen; incident acknowledge; T5.4 consumption actions.

## Notes / preconditions

- Dev loop for the SPA: `cd ui/control-room && npm run typecheck && npm test`; rebuild with
  `bin/control_room_build_ui.sh` from the repo root (refuses Node < 22; Node 26 on the box).
- `requiredBy.enabled` is derived from control state, so it is meaningful for timer dependents
  only; the inversion is O(rows × requires) per request — trivial at three entries.
- `SystemdReader.show` on `system/ollama.service` from the user-scope service works unprivileged;
  `--user` for `buzz-notion-broker` needs the same bus the runtimes already need — no new failure
  mode.
