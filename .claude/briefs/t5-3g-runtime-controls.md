# Brief: T5.3g — Runtime controls: Start / Stop / Restart an agent from the Agents view

**Date:** 2026-09-16   **Verify:** `bash bin/verify.sh` from the repo root (includes
`bin/check_deploy_drift.sh`; extra gates and smoke: none — the gate is red on the branch for deploy
drift on exactly the `bin/` files this brief changes plus the two stale root copies, and green only
after `bin/deploy`, the two `sudo install` lines and the one service restart).

**Size:** M. **Standing constraint (Dave, 2026-09-14):** the scheduled fleet is OFF except what Dave
has resumed from the screen. MEASURED 2026-09-16 15:30 CEST: all five `buzz-agent@*` are
`inactive/dead/disabled` and `buzz-agent@.service` is `disabled` at the unit-file level — enumerate
with `systemctl --user show buzz-agent@<name> -p ActiveState,UnitFileState`, never trust this line.
**No step in this brief starts, stops, restarts, enables or disables any `buzz-agent@*` unit or any
workflow timer.** The one restart is `control-room.service`. The two root-owned files
(`/usr/local/lib/control-room/control_broker.py`, `/etc/control-room/allowlist.json`) are
re-installed by hand at land, exactly as T5.3a installed them. The first live Start is Dave's
moment, from the screen.

**Order:** after T5.3f (landed 2026-09-16, PR #45) and T5.3a (2026-09-14). Nothing blocks this
card. Source of acceptance: `docs/dev-plan-2026-09.md` T5.3g. Plan of record: the approved plan
this brief was written from (2026-09-16), summarised in § Design.

## Why (Dave, 2026-09-16)

T5.3f shipped the Agents view read-only and said so in its brief: "no start/stop of a runtime from
the screen — that is a separate decision." Dave made it the same day. Today the only way to bring
an agent up, or to restart one after a `.env`/`.prompt` edit (`check-loaded.sh` reports STALE
until the process re-reads its files), is a shell on the box. The broker already reaches the user
manager (`systemctl --user --machine=dave@.host`, proven on `buzz-pr-watch` in T5.3a) and refuses
the runtimes by construction: `UNIT_RE` rejects `@` (`bin/control_broker.py:33`) and the allowlist
excludes `kind = service` (`bin/control_broker_allowlist.py:65-68`).

Decisions (Dave, this session): the actions are the **session-scoped systemd verbs** `start`,
`stop`, `restart` — labelled "Start agent now" / "Stop agent now" / "Restart agent now" — and boot
policy (`UnitFileState`) is shown as a fact, never changed from the screen; `restart` is in; build
it in this session.

## Acceptance criteria

1. **One id space.** A runtime is addressed by its read-model id `buzz-agent@<name>` on the
   existing `workflow_id` key — the same receipts tree
   (`/var/lib/control-room/receipts/buzz-agent@<name>/`), the same `ControlReceipts.last_action(id)`
   reader, the same `POST /api/v1/control/actions`. The broker gains `RUNTIME_RE`
   (`^[a-z0-9][a-z0-9-]{0,63}@[a-z0-9][a-z0-9-]{0,63}$`) beside `UNIT_RE`; `UNIT_RE` does not
   widen — timer ids and trigger units keep their grammar. argv is still built from allowlist
   constants only; the request's strings are never interpolated into a command.
2. **The allowlist gains a `runtimes` table** (schema stays 1): `{"<unit>": {"owner", "unit",
   "scope", "template"}}`, rendered from every manifest entry with `status = "standing"` and
   `kind = "service"` (the five today — counted from the manifests in the test, never a literal),
   requiring the template unit file `systemd/<user|>/<template>.service` to exist in the repo
   (resolved the way `bin/workflow_requires.py:78-85` does: `buzz-agent@marcus` →
   `buzz-agent@.service`), else excluded `no service file in systemd/`; an id outside `RUNTIME_RE`
   is excluded `unit name outside the broker's grammar`. The five leave `excluded`; the two
   `status = spent` rows stay. `dumps()` stays byte-deterministic. The broker treats a file
   **without** the table as valid and knowing no runtime (strict on a malformed entry —
   `allowlist_invalid` — lenient on absence, so a stale render refuses runtime requests as
   `unknown_workflow` instead of refusing every workflow action too).
3. **Action vocabulary per kind.** `ACTIONS` (workflow) is unchanged; `RUNTIME_ACTIONS =
   ("start", "stop", "restart")`. `validate_request` accepts the union; after the allowlist lookup
   an action outside the entry's kind is refused `unknown_action` with a message naming the right
   vocabulary (`pause buzz-agent@marcus` → "pause is not a runtime action; runtimes take start,
   stop, restart"; `start knowledge-digest` → "start is not a workflow action; use run_now"),
   with zero mutating calls. The `tests/test_control_broker.py:167` pin (`pause buzz-agent@marcus`
   → `bad_request`) becomes `unknown_action`. `argparse` `choices` on `act` (`:835`),
   `validate_receipt`'s action check (`:408`), `ACTION_IDS` consumers (`validate_shape`
   `control_room_control.py:209`, `STUBS` `control_room_api.py:948`) and the SPA
   `controlActionIdSchema` all learn the union.
4. **Preconditions, broker-side:** `start` needs `confirm: true` (`confirmation_required`) and a
   service that is not active/activating (`state_conflict`); `stop` and `restart` need
   `confirm: true`, a non-empty reason (`reason_required`) and a service that is
   active/activating/reloading (`state_conflict`; `deactivating` says "still stopping"). Common
   refusals apply unchanged — `unit_not_found` on `LoadState=not-found`, `masked` on the
   service's `UnitFileState`/`LoadState`, `peer_denied`, `allowlist_invalid`, `locked`,
   `bad_request`. Every runtime action is mutating and serialises on the lock.
5. **Commands** (user scope prefixes `--user --machine=dave@.host`): `start --no-block
   <unit>.service` then a settle-poll of `show` every 1 s for `START_SETTLE_SECONDS` (default 6
   = the template's `RestartSec=5` + 1; a `Config` field, `--start-settle`, env
   `CONTROL_BROKER_START_SETTLE_SECONDS`, so the suite runs at 0/1 s); `stop --no-block
   <unit>.service` + the existing ≤ 15 s poll; `restart --no-block <unit>.service` + the start
   settle-poll. A unit read as `failed` or `activating/auto-restart` inside the window keeps
   `result: applied` (systemd accepted the verb) and carries a `note` naming `NRestarts`,
   `journalctl --user -u <unit>` and `~/.config/buzz-team/check-loaded.sh`. A non-zero
   `systemctl` exit after validation → `result: failed`, stderr captured, `after` re-read, HTTP 500.
6. **Runtime reconcile reads a fixed property list and nothing else.** `RUNTIME_PROPERTIES =
   ActiveState,SubState,UnitFileState,LoadState,Result,InvocationID,ExecMainStartTimestamp,
   ExecMainExitTimestamp,NRestarts`. Never `ExecStart`, never `Environment`, never `status` — the
   launched process carries the agent's private key in argv (`~/CLAUDE.md` § fleet MCP bridge).
   `before`/`after` = `{"state", "fingerprint", "units": [{"unit", "scope", "timer": null,
   "service": view}]}` where `state` uses the screen's four-value vocabulary (`active` for
   active/activating/reloading, `paused` for inactive/failed/deactivating, else `unknown`) so the
   receipt and the chip agree, and the raw `ActiveState` travels in `units[0].service.activeState`.
   `fingerprint()`, `next_scheduled()` and `check_loaded()` skip a `null` timer.
7. **Every outcome is one receipt**, `validate_receipt(data) == []`, under
   `receipts/buzz-agent@<name>/`; `links` gains `"agent": "/agents/<owner>"` (extra link keys are
   already allowed; **no required receipt key changes**, so every T5.3a receipt on disk stays
   readable). `ControlReceipts._seam` passes `links.agent` through.
8. **The read model owns the runtime's `control` once.** `control_actions(state, source, role)`
   (`bin/control_room_state.py:93`) returns the three runtime actions for an `agent-runtime` row —
   `start` enabled when `paused`, `stop`/`restart` when `active`, all disabled "systemd state
   unavailable" when `source` is not `systemd`. `trigger_state`'s service branch (`:56-57`) maps
   `failed` into the paused bucket (an always-on service that failed is startable; the raw state
   still shows on the chip). `/api/v1/agents[/<name>]` items gain `control` (the runtime row's
   own object) and `runtime.unitFileState`. `GET /api/v1/workflows/buzz-agent@<name>` carries the
   runtime actions, so `handle_post`'s post-action re-read is unchanged in shape.
9. **`/app/agents/<name>` gets three buttons** — "Start agent now", "Stop agent now", "Restart
   agent now" — enabled from `agent.control.actions` (disabled with the reason as `title`), each
   opening one dialog: Start (reason optional) carries the double-hosting line ("If Buzz Desktop
   on the Mac is also hosting this agent, both reply to every mention") and "verify with
   `~/.config/buzz-team/check-loaded.sh` after"; Stop and Restart (reason required, danger tone)
   render the `DependencyNotice` for enabled `requiredBy` entries, "a turn in progress is lost",
   and the boot-policy fact from `runtime.unitFileState` ("unit file disabled — it will not come
   back after a reboot" / "enabled — it comes back after a reboot"). Every action sends
   `confirm: true`; applied → re-fetch the agent; the outcome line and every refusal code render
   as today's `ControlOutcome` does. Cancel touches nothing (no POST). The card shows
   `boot: <unitFileState>` beside the runtime chip. The read-only copy on `pages/Agents.tsx:19`
   and `pages/AgentDetail.tsx:42` goes; `Agents.test.tsx:35` (no start/stop button) flips.
10. **`/app/workflows/buzz-agent@<name>` offers no workflow verbs.** `WorkflowDetail.tsx:76`
    renders `WorkflowControls` for every row; for an `agent-runtime` row it renders a link to the
    agent page instead.
11. **Required-by is a notice, not a refusal.** Stopping `buzz-agent@augustus` while
    `augustus-content` is enabled is allowed: T5.3f's executor pre-flight turns the dependent's
    next run into a one-second BLOCKED and a `dependency-down` exception. The broker stays
    ignorant of `requires`.
12. **The hand-run acceptance adds three refusal-only runtime cases** — `act start|stop|restart
    buzz-agent@marcus` **without** `--confirm` → `confirmation_required`, refused before any
    mutating call whatever the live state — and its self-check forbidden list gains the split
    literal for `--confirm` so the script can never carry a confirmed runtime action.
13. **Nothing else moves.** No unit file, socket, drop-in, group or `bin/check_deploy_drift.sh`
    change (it already compares the one broker file and the rendered allowlist). Verify green
    after land; on the branch, drift red names exactly the changed `bin/` files and the two stale
    root copies; `tests/test_control_room_spa.sh` recomputes the stamp and, with Node, rebuilds
    byte-identical. No `tests/ci-expected-skips.txt` line. **No runtime started, stopped or
    restarted by any step.**

## Existing state (read 2026-09-16; re-verify anchors before editing)

- Broker `bin/control_broker.py`: `UNIT_RE:33`, `ACTIONS:35`, `REFUSAL_CODES:38-43`,
  `REQUEST_KEYS:45-46`, `SERVICE_PROPERTIES:56-57`, `RECEIPT_KEYS:61-66`; `Config:83-98`;
  `Allowlist.load_data:164-173` reads only `workflows`/`excluded`, `_check_entry:176-187`,
  `lookup:189-197`; `Runner._prefix:218-219` (`--user --machine=<user_manager>`), `mutate:233-237`
  (`--now` for enable/disable, else `--no-block`); `_service_view:267-279`; `state_of:290-298`,
  `fingerprint:301-304` and `reconcile:307-315` assume a `.timer` per trigger; `check_loaded:318-324`;
  `next_scheduled:327-331`; `validate_receipt:398-433` (`action` must be in `ACTIONS` `:408`;
  `links` needs the four keys `:428-430`); `write_receipt:436-459` (dir = `workflow_id or _refused`);
  `validate_request:479-513` (`unknown_action:503`, grammar `:505`); `plan:536-551`;
  `_check_preconditions:554-572` (stop's confirm/reason `:566-570`); `_execute:624-650` (stop poll
  `:642-649`); `handle:653-692`; `_build_receipt:703-735` (`links:731-734`); `parse_args:821-843`
  (`act` `choices=ACTIONS` `:835`).
- Renderer `bin/control_broker_allowlist.py`: `_manifest_entries:49-57`, `_units_present:60-62`
  (timer + service by exact name — never matches a template instance), `_exclusion_reason:65-75`
  (`kind = service` excluded `:67-68`), `render:91-110`.
- Read model: `control_room_state.py` `trigger_state:51-62`, `control_actions:93-103`,
  `control_for:113-143`; `control_room_api.py` `SystemdReader.show:189-213`, `_systemd_for:361-403`
  (`timer: None` for `kind != timer`), `workflows()` control at `:529`, `_runtime_of:800-809`,
  `_agent_items:811-833`, `STUBS:948-951`; `control_room_control.py` `ControlReceipts._seam:182-195`,
  `validate_shape:209-214`, `_fresh_control:250-252`, `handle_post:255-285`.
- Fixtures `tests/fixtures/control-broker/`: `allowlist.json` (`buzz-agent@marcus` under
  `excluded`), `state.json` (no `buzz-agent@*` unit), `bin/systemctl` (verbs `show`, `enable`,
  `disable`, `start`, `stop`; anything else exits 2), `fake_broker_socket.py`.
- Suites: `tests/test_control_broker.py` (`Sandbox:36-125`, `req:122`, `assertRefused:135`, the
  `:167` pin, `ScopeAddressing:376-397`, `AllowlistRender:525-607` with `:541-548` pinning the
  exclusion); `tests/test_control_room_control.py` (`PostForwardsAndReconciles:324`,
  `AcceptanceScriptLints:384`); `tests/test_control_room_api.py` (synthetic
  `buzz-agent@aurelian` entry `:126-128`, agents `:268-320`); anchors registered in
  `design/fleet-suites.toml` (`:374-389` broker, `:390+` control, `:309-322` API).
- Acceptance `tests/acceptance/control_room_controls.sh`: forbidden-literal self-check `:34-44`,
  `broker()` `:46-48`, step 3 refusals.
- SPA: `api/schemas/control.ts` (`controlActionIdSchema:5`, `controlRequestSchema:8-17`);
  `schemas/agent.ts` (`agentRuntimeSchema:7-12`, `agentSchema:19-32`); `model/agent.ts`
  (`RuntimeView:10-16`, `UP_STATES:39`, `toAgent:46-65`); `dialogs/useControlAction.ts`
  (`guard:39-44`, `withConfirm:46`); `components/WorkflowControls.tsx` (`Open`/`LABELS:16-19`,
  buttons `:44-55`, dialogs `:81-87`); `dialogs/StopDialog.tsx` (the confirm+reason template);
  `components/DependencyNotice.tsx` (`action: "pause" | "stop"` `:4`); `pages/AgentDetail.tsx`
  (`runtimeId:14`, Runtime panel `:36-43`); `pages/Agents.tsx:19`; `Agents.test.tsx:35`;
  `pages/WorkflowDetail.tsx:76`; fixtures `api/fixtures.test-helpers.ts:304-330` (`agentUp`,
  `agentDown`). Build committed at `bin/control_room_ui/app/` + `BUILD.json`.
- Template unit `systemd/user/buzz-agent@.service`: `Type=simple`, `Restart=on-failure`,
  `RestartSec=5`, `EnvironmentFile=%h/.config/buzz-agents/%i.env`; the key reaches the launched
  process's argv through the launch script, not `ExecStart=`.
- Docs that say "read-only": `docs/runbook.md:294`, `:311-314`; `CLAUDE.md:155`, `:162`;
  `design/agent-model.md:426-502` ("nothing broker-controllable is required by anything today");
  `design/workflow-registry.md` §1; `~/CLAUDE.md` Buzz section (`systemctl --user {start,status}`).

## Design (decided; reasons once)

- **One id space.** A second `runtime_id` key would fork the request shape, the receipt reader
  and the HTTP handler for no gain; the runtime already has a read-model id.
- **`RUNTIME_RE` beside `UNIT_RE`, not a wider `UNIT_RE`.** Timer ids and trigger units keep the
  grammar T5.3a proved; the `@` is admitted only where a template instance is the thing named.
- **Session-scoped verbs.** `start`/`stop`/`restart` are what Dave asked for by name; enable/
  disable is a boot-policy decision and stays a shell command. The screen shows the policy so a
  reboot never surprises anyone.
- **Settle-poll, not a health check.** The broker cannot know an agent is healthy; it can know
  systemd restarted it within `RestartSec`. That fact goes on the receipt as a `note`;
  `check-loaded.sh` stays the deeper diagnostic.
- **Fixed property list, never `status`.** The one credential leak path from a `systemctl` read is
  argv; the constant excludes it and the rule is written down.
- **Lenient on a missing `runtimes` table.** A stale render must degrade to "knows no runtime",
  not to "refuses every workflow action".
- **Required-by is a notice.** The executor already has teeth (T5.3f); a broker refusal here would
  be a second, weaker copy of the same rule.

## HTTP surface (additions; nothing removed)

- `POST /api/v1/control/actions` — `action` accepts `start | restart` (and `stop`) with
  `workflow_id = buzz-agent@<name>`; `confirm: true` required for the three.
- `GET /api/v1/agents`, `/api/v1/agents/<name>` — items gain `control` and `runtime.unitFileState`.
- `GET /api/v1/workflows/buzz-agent@<name>` — `control.actions` are the runtime three.

## Files to modify

- `bin/control_broker.py`, `bin/control_broker_allowlist.py`, `bin/control_room_state.py`,
  `bin/control_room_api.py`, `bin/control_room_control.py`.
- `tests/fixtures/control-broker/{allowlist.json,state.json,bin/systemctl}`;
  `tests/test_control_broker.py`, `tests/test_control_room_control.py`,
  `tests/test_control_room_api.py`; `tests/acceptance/control_room_controls.sh`;
  `design/fleet-suites.toml`.
- `ui/control-room/src/api/schemas/{control,agent}.ts`, `model/agent.ts`,
  `api/fixtures.test-helpers.ts`, `dialogs/useControlAction.ts` (+ test),
  `components/DependencyNotice.tsx`, `components/AgentCard.tsx`, `pages/Agents.tsx` (+ test),
  `pages/AgentDetail.tsx` (+ test), `pages/WorkflowDetail.tsx` (+ test);
  `bin/control_room_ui/app/**` + `BUILD.json` rebuilt.
- `docs/runbook.md` § Control Room controls (+ the T5.3f subsection's read-only lines),
  `CLAUDE.md`, `design/agent-model.md`, `design/workflow-registry.md`, `~/CLAUDE.md` (one line),
  `docs/dev-plan-2026-09.md` (DONE line at land).

## Files to create

- `ui/control-room/src/components/AgentControls.tsx` + `.test.tsx`;
  `ui/control-room/src/components/dialogs/RuntimeDialog.tsx` + `.test.tsx`.

## Test plan (TDD; red first; anchors are the `(::id)` comments registered in fleet-suites)

- `tests/test_control_broker.py` — new `RuntimeStartStopRestart` `(::broker-runtime-actions)`,
  fixture `runtimes` = `buzz-agent@marcus` (inactive/dead/disabled) + `buzz-agent@augustus`
  (active/running); shim gains `restart`, `NRestarts`, and `_dies_after_start` →
  `activating/auto-restart` with `NRestarts=1`: `start marcus` without confirm →
  `confirmation_required`, empty call log; with confirm → the log is the `show` reads plus
  `systemctl --user --machine=dave@.host start --no-block buzz-agent@marcus.service --no-pager`,
  `applied`, `after.state == "active"`, `after.units[0].timer is None`, `links.agent ==
  "/agents/marcus"`, receipt under `receipts/buzz-agent@marcus/`; `start augustus` →
  `state_conflict`; `stop augustus` without reason → `reason_required`, with both → `stop
  --no-block …`, `after.state == "paused"`; `stop marcus` → `state_conflict`; `restart augustus`
  → `restart --no-block …`, `applied`, `after.state == "active"`; `restart marcus` →
  `state_conflict`; `pause|resume|run_now|retry marcus` → `unknown_action`, `start|restart
  knowledge-digest` → `unknown_action`, all with empty mutating log; `start buzz-agent@nobody` →
  `unknown_workflow`; `workflow_id: "buzz-agent@marcus;x"` → `bad_request`; a masked runtime →
  `masked`; `FAKE_SYSTEMCTL_FAIL=buzz-agent@marcus.service` → `failed`, HTTP 500; the
  `_dies_after_start` unit with `--start-settle 1` → `applied` with a `note` naming `NRestarts`;
  every receipt `validate_receipt == []`; an allowlist without `runtimes` → `start marcus` is
  `unknown_workflow` and `pause knowledge-digest` still works; a malformed runtime entry →
  `allowlist_invalid`.
- `AllowlistRender` — every standing `kind = service` entry appears under `runtimes` keyed by unit
  with its owner, `scope == "user"`, `template == "buzz-agent@.service"`; `excluded` carries only
  the spent rows; a synthetic manifest with a service entry whose template is missing → excluded
  `no service file in systemd/`; ids match `RUNTIME_RE`; bytes stable.
- `tests/test_control_room_control.py` — `(::control-runtime-post)`: `validate_shape` accepts
  `start`/`restart`; `POST start buzz-agent@marcus confirm:true` through the fake socket → 200,
  `receipt.result == "applied"`, `control.actions` ids `[start, stop, restart]` with `start`
  disabled and `stop` enabled after the re-read; `_seam` carries `links.agent`.
- `tests/test_control_room_api.py` — the synthetic runtime row's `control.actions` are the three;
  a `failed` service reads `paused`; agent items carry `control` and `runtime.unitFileState`.
- SPA vitest: `AgentControls.test.tsx` (three buttons, disabled + `title`), `RuntimeDialog.test.tsx`
  (start posts `confirm: true` without a reason; stop/restart refuse an empty reason client-side
  and post with one; `DependencyNotice` only with an enabled dependent; boot-policy line; Cancel
  posts nothing; refusal code renders), `useControlAction.test.tsx` rows for start/restart,
  `AgentDetail.test.tsx` (buttons present, re-fetch after applied), `Agents.test.tsx:35` flipped,
  `WorkflowDetail.test.tsx` (runtime row → agent link, no workflow buttons).
- `tests/test_control_room_spa.sh` — stamp + byte-identical rebuild.

## Implementation steps (ordered; commit after each numbered group — the auto-sync sweep is 15 min)

1. Dev-plan card + this brief.
2. Broker: fixture `runtimes` + shim verbs → `AllowlistRender` red/green → request/lookup
   vocabulary → runtime reconcile, preconditions, plan → settle-poll + `note` → links. Renderer.
3. Read model + control handler: role-aware actions, `failed → paused`, agent `control` +
   `unitFileState`, `validate_shape`, the round trip.
4. Acceptance cases + fleet-suites anchors.
5. SPA: schemas/model/fixtures → `useControlAction` → `AgentControls` + `RuntimeDialog` →
   `AgentDetail`, `AgentCard`, `WorkflowDetail`, copy → `npm run typecheck && npm test` →
   `bin/control_room_build_ui.sh`, restamp. `bash bin/verify.sh`: green except drift naming
   exactly the changed `bin/` files and the two root copies.
6. Docs. Dev-plan DONE line waits for land.

## Land-time steps

1. Merge to `main` after the independent verify + review; pull on the box.
2. `bin/deploy` (the changed `bin/*.py` and the SPA build) →
   `sudo install -D -o root -g root -m 0755 bin/control_broker.py /usr/local/lib/control-room/control_broker.py`
   → `python3 bin/control_broker_allowlist.py render > /tmp/allowlist.json && sudo install -D -o root -g root -m 0644 /tmp/allowlist.json /etc/control-room/allowlist.json && python3 bin/control_broker_allowlist.py check`
   → `sudo -n systemctl restart control-room.service` (the broker is per-connection; nothing else
   restarts) → `bash tests/acceptance/control_room_controls.sh` ALL PASS → `bin/check_deploy_drift.sh`
   clean. No timer, no runtime, no unit file touched.
3. From the Mac, changing nothing: `/app/agents/marcus` shows Start enabled, Stop and Restart
   disabled with their reason, `boot: disabled`; Start → dialog → **Cancel**. From the box:
   `sudo /usr/bin/python3 /usr/local/lib/control-room/control_broker.py act start buzz-agent@marcus`
   (no `--confirm`) → `confirmation_required`, receipt under `receipts/buzz-agent@marcus/`, and the
   agent page's last action shows it refused. **No agent started.**
4. `bash bin/verify.sh` green, run detached. Dev-plan DONE line + archive this brief; commit and
   **push by hand**. Notion tracker row for T5.3g from a session with the connector (T5.3f's is
   still Todo).

## Out of scope / do not touch

- Any `buzz-agent@*` start/stop/restart/enable/disable; any timer enable/start/stop/pause/resume.
- `enable`/`disable` of a runtime from the screen (boot policy is shown, not changed).
- A broker-side refusal on `requires`; a health check beyond the settle-poll; reading the journal.
- The socket, the group, the drop-in, `bin/check_deploy_drift.sh`, the SSR pages, `actions.js`.
- Live `systemctl` in any suite; a `tests/ci-expected-skips.txt` line.

## Notes / preconditions

- Dev loop for the SPA: `cd ui/control-room && npm run typecheck && npm test`; rebuild with
  `bin/control_room_build_ui.sh` from the repo root (Node 26 on the box).
- The broker file is self-contained by design (root execs it); the runtime path lives inside it
  and imports nothing from `bin/`.
- `systemctl --user --machine=dave@.host restart` from root needs the same bus the existing
  user-scope verbs already need — no new failure mode.
