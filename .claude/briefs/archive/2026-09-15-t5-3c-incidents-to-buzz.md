# Brief: T5.3c — route actionable workflow incidents to Buzz
**Date:** 2026-09-14   **Verify:** `bash bin/verify.sh` from the repo root (includes `bin/check_deploy_drift.sh`)

Source of scope: `docs/dev-plan-2026-09.md:510-520` (T5.3c, size S, dep T5.3), decisions `:16-54`,
plan-level definition of done `:67-105` — item 3 (`:88-89`) names this task, item 5 (`:91-92`)
names the incident unit, and `:75` says **no task enables a timer**. Notion card gate: *action-
required incidents reach one dedicated Buzz stream once, with recovery/digest semantics; healthy
runs stay silent; a delivery failure cannot fail the originating workflow* (confirmed operator
requirements 2026-09-10). Standing constraint (Dave, 2026-09-14): the scheduled fleet is OFF —
all twelve system workflow timers disabled since 2026-09-11 and they stay disabled. Every test
here runs from fixtures (precedent `tests/test_contract_exec.sh`); the one live run is Dave's
hand-started `systemctl start workflow-incidents.service`, at a moment of his choosing, and it
is evidence-time, not development-time.

What already exists and is reused, not re-derived:
- **Receipts** — `~/agent-workforce/var/workflow-receipts/<workflow_id>/<run_id>.json`, shape
  owned by `bin/workflow_receipt.py` (`TERMINAL_OUTCOMES` `:23`, `validate` `:112-163`, atomic
  `write` `:176-200`). Exactly one terminal outcome; usage/cost `measured` or `unavailable`,
  never zero-for-unknown. The runtime directory **does not exist on the box today** (MEASURED
  2026-09-14) — T5.2 has not landed — so the read model reports `receipt directory unavailable`
  and nothing can fire at land.
- **Read model** — `bin/control_room_api.py`: `ControlRoomReadModel.workflows()` `:335-418`
  joins manifests + contracts + systemd + receipts into one item per logical workflow (`health`
  from `_health` `:312-327`: running/paused/unknown/failed/incomplete/healthy; `lastRun` from
  `_run_summary` `:421-442`); `receipts()` `:250-272` returns `(valid, malformed, source_errors)`;
  `incidents()` `:488-534` is the **existing incident derivation** (contract-unavailable, failed/
  incomplete latest run, malformed receipt) and is the one this task extends. `SourcePaths`
  `:100-124` (env `CONTROL_ROOM_REPO_ROOT`, `CONTROL_ROOM_RUNTIME_ROOT`,
  `CONTROL_ROOM_RECEIPT_ROOT`); `SystemdReader.show` `:143-167` runs PATH `systemctl show` with
  many `--property=` flags and parses `Key=Value` lines.
- **Transport** — `bin/deliver.sh` (usage `:3-11`) is the single owner of Buzz/Discord delivery;
  **fail-soft by contract** (`:26-31`, `finish` `:167-170` always exits 0), writes exactly one
  JSONL receipt per invocation to `$DELIVERY_RECEIPTS` (default `~/logs/delivery-receipts.jsonl`,
  `:79`; fields at `:137-165` include `job`, `subject`, `outcome`, `buzz_result`,
  `buzz_event_id`, `channel`, `error`, `detail`), prints nothing to stdout. Route table
  `$BUZZ_ROUTES_FILE` (default `bin/buzz_routes.env`, `:38`); an **empty** route value is
  `config_error` — Buzz skipped, Discord still attempted (`:336-339`, `buzz_routes.env:14-16`).
  `DELIVER_DISCORD=0` disables the Discord leg (`:80`).
- **Routing** — `bin/buzz_routes.env`: three lines per key (`ROUTE_<key>`, `_kind`, `_notify`),
  no identities. `bin/buzz_producers.tsv` is the producer matrix `tests/test_buzz_unit_wiring.sh`
  enforces: a `wired` row's unit must carry `Environment=DELIVERY_ROUTE=<route>`,
  `Environment=DELIVERY_JOB=%n`, `DELIVERY_RUNTIME=none` (or a task) and a hook matching
  `/bin/(deliver[a-z_]*|notify|inbox_backlog_alert|agent_alert)\.sh` (`:172-181`, `:246-247`);
  `notify=none` is legal (`:125`); polling timers count as on-demand for the dual-run audit
  (`bin/audit_buzz_dual_run.sh:222`; `systemd/content-change-dispatch.timer:14` is the
  `OnCalendar=*:0/15` precedent).
- **Registries a new timer must satisfy** — `tests/test_workflow_coverage.py:673-685`
  (`timer-family-declared`: every `systemd/*.timer` family needs a `[[workflows]]` entry),
  `:296` (`standing-has-suite`), `:326` (`contract-declared`); `tests/test_fleet_ownership.sh:180-182`
  (manifest ⇔ `config/fleet-units.tsv`); `tests/test_contract_schema.sh` (eight sections, five
  actionability bullets, executable `check` blocks). Precedents: `design/agents/trajan.toml:153-163`
  (`inbox-backlog-alert`), `config/fleet-units.tsv:73`, `design/contracts/inbox-backlog-alert.md`,
  `systemd/inbox-backlog-alert.{service,timer}`.
- **S1 kind check** in `bin/verify.sh` joins the source route table to the live
  `~/.config/buzz-team/TEAM.md`; `buzz-team/check-team-kinds.py:23` matches `ROUTE_<key>=(\S+)`,
  so an **empty placeholder is invisible to it** (stays green) and the moment the UUID is filled
  TEAM.md needs the matching row under kind 9 or the gate goes red.

## Acceptance criteria

1. **One incident model, two consumers.** `bin/workflow_incidents.py` owns the incident
   vocabulary, dedup key and the derivation `derive(workflows, malformed, source_errors,
   declared, now)`; `bin/control_room_api.py:incidents()` and the notifier both call it. No
   second derivation anywhere.
2. **Classes and their signals** (an incident's `class`; `severity` fixed per class):
   | class | signal | path |
   |---|---|---|
   | `failed-assertion` (high) | latest receipt `terminal.outcome == "failed"` with ≥1 assertion `status == "failed"` | immediate |
   | `missing-artifact` (high) | latest receipt outcome `failed` with **no** failed assertion (executor reason `neither artifact nor decline`, `bin/contract_exec.py:14-16`) | immediate |
   | `incomplete-run` (high) | latest receipt outcome `skipped` (`contract_exec.py:72`: "the run never happened"); **or** a trigger whose timer is `active`, whose `lastTriggerAt` is older than `INCIDENT_RECEIPT_GRACE_SECS` (default 7200) and newer than the newest receipt's `started_at` (or there is no receipt), while the service is not `running` — fired and wrote no receipt | immediate |
   | `malformed-receipt` (high) | one per entry of `receipts()`'s `malformed` list | immediate |
   | `control-failure` (high) | the sweep's own sources: receipts root **exists but is unreadable** (`receipt directory unreadable`/`not a directory`; a *missing* root is pre-T5.2 normal and is **not** an incident), manifests `degraded`; plus declared incidents (criterion 4) | immediate |
   | `blocked-next-action` (medium) | **declared only** (criterion 4) — no receipt field says "blocked" and a `due_at` heuristic would alert on actions Dave completed off-box | immediate |
   | `contract-unavailable` (medium) | `contractStatus == "unavailable"` (the API's existing class) | digest only |
   Silent by construction: outcome `artifact` and outcome `decline` (the valid no-output state),
   a healthy receipt following a failed one (that is a recovery), a workflow whose timers are all
   inactive (paused — an owned state; **no staleness incident for a paused workflow**), systemd
   read errors (visible in the API's `data_status`, not an incident — a `--user` bus is
   routinely unreachable from a system unit).
   **The paused label does not suppress a run-derived incident**: `_health` returns `paused`
   for every workflow while the fleet is off, and the existing `incidents()` keyed off
   `health in {failed, incomplete}` would then never see a failed receipt. The new derivation
   reads `lastRun.outcome`/`assertions` directly. A failed last run is an exception until a
   healthy run lands, whatever the timer state; that is also what makes the evidence run below
   possible with the fleet off.
3. **Dedup key** `id == key`: `"<class>:<workflow_id>"` for run-derived classes (a workflow
   failing every night is *one* incident: `observations` increments when `run_id` changes,
   `last_seen` moves, no new alert), `"malformed-receipt:<receipt relative path>"`,
   `"contract-unavailable:<workflow_id>"`, `"control-failure:incident-sweep:<source>"`, and
   `"<class>:<workflow_id>:<declared id>"` for declared ones. The API's old
   `malformed-receipt-<index>` and `run-<run_id>` ids are replaced by these (they were never
   stable; `tests/test_control_room_api.py:193-199` finds the malformed one by
   `failedAssertion`, not by id, and keeps passing).
4. **Declared incidents.** `python3 bin/workflow_incidents.py declare --class <c> --workflow <id>
   --agent <a> --issue <text> --action <text> [--evidence <str>]... --id <stable-id>` writes
   `<INCIDENT_STATE_DIR>/declared/<key-sanitised>.json` atomically; `... resolve --key <key>`
   stamps `resolved_at`. A declared file with `resolved_at == null` is an observation; absent or
   resolved is not (→ recovery). This is the interface T5.3a's broker uses for a failed control
   action; wiring it there is T5.3a's, not this brief's.
5. **State** at `~/agent-workforce/var/incidents/state.json` (`bin/incident_state.py`, schema
   `{"schema": 1, "last_digest_at": iso|null, "incidents": {key: {...}}}`), one entry per key:
   `key, class, severity, workflow_id, agent, unit, issue, failed_assertion, required_action,
   run_id, run_ids[], observations, evidence[], first_seen, last_seen, resolved_at, notified_at,
   notify_event_id, notify_channel, send_attempts, last_send_error, recovery_notified_at,
   digested_at`. `reconcile(state, observed, now)` is pure and returns the transitions
   (`opened`, `updated`, `closed`): observed & absent-or-resolved → open (`first_seen` = the
   receipt's `ended_at` when there is one, else `now`); observed & open → update; open & not
   observed → close (`resolved_at = now`). **A sweep that cannot see a source closes nothing**:
   when receipts or manifests are degraded, no run-derived incident is closed that sweep
   (absence of evidence is not recovery — same rule as `crates/buzz-acp/src/engram_fetch.rs`
   in `~/CLAUDE.md`). Resolved entries are pruned after `INCIDENT_RESOLVED_RETENTION_DAYS`
   (14). Writes are temp-file + `os.replace` in the same directory, never partial. A state
   file that does not parse is moved aside to `state.json.corrupt-<utc ts>` with a logged
   line and the sweep starts fresh (open incidents re-alert once; that is honest).
6. **Immediate path** (`bin/incident_notify.py`, mode `sweep`): after reconcile+save, send one
   message per opened immediate-class incident with `notified_at == null` and
   `send_attempts < INCIDENT_MAX_SEND_ATTEMPTS` (6), at most `INCIDENT_MAX_SENDS_PER_SWEEP`
   (10) per sweep, oldest `first_seen` first (the rest wait for the next sweep; the digest
   lists them all). A second observation of an open key sends nothing. Subject
   `[incident] <key>`; body lines, in this order: `workflow: <workflow_id> (unit <unit>)`,
   `agent: <agent>`, `failure: <class> — <issue>` (+ `failed check: <failed_assertion>` when
   set), `time: first seen <first_seen> · run <run_id> · seen <observations>×` , `required
   action: <required_action>` (the receipt's `next_action.action`, else the class default in
   `workflow_incidents.REQUIRED_ACTION`), `incident: <INCIDENT_LINK_TEMPLATE with {key}>`,
   `evidence: <receipt path>; <artifact uri>; <journalctl -u <unit> --since <ts>>` (whichever
   exist). Every message names workflow, agent, failure, time, required action, incident link
   and evidence — asserted line by line in the tests.
7. **Recovery.** A closed incident whose `notified_at` is set and `recovery_notified_at` is
   null gets one `[recovered] <key>` message: workflow, agent, class, `open since <first_seen>,
   resolved <resolved_at>`, `evidence: <the healthy run's receipt path>` (or "observation
   ceased: <what>" for declared/malformed), and `alert: <POINTER>` where POINTER is
   `buzz://message?channel={notify_channel}&id={notify_event_id}` (Desktop's copy-link form,
   `deliver.sh:67-70`). An incident that was never notified (route unset, digest-only class)
   closes silently.
8. **Digest**, once a day: due when local time ≥ `INCIDENT_DIGEST_AT` (default `07:00`, box
   zone Europe/Amsterdam — `systemd/agent-drift-check.timer:2`) and `last_digest_at` predates
   today's `INCIDENT_DIGEST_AT`. Subject `[incident digest] <N> unresolved`; one line per
   **open** incident sorted by `first_seen`: `<class> <workflow_id> — since <first_seen> (seen
   <n>×, last <last_seen>) — <required_action> — <link>`; an open incident with `notified_at ==
   null` is marked `unsent (<last_send_error>)`. Resolved incidents never appear. **Zero
   unresolved → no digest at all** (an empty digest is a heartbeat; the stream is an exception
   channel). `last_digest_at` is stamped either way so the gate evaluates once per day.
   `--digest` forces one now (hand use); `--dry-run` prints what would be sent and touches
   neither state nor transport.
9. **Route pre-check.** Before any send the notifier reads `$BUZZ_ROUTES_FILE` itself: if
   `ROUTE_<route>` (`DELIVERY_ROUTE`, default `incidents`) is empty or absent it logs
   `route 'incidents' has no channel UUID in <file> — sending nothing, state kept` and skips
   every send (no deliver.sh call, so no Discord fallback and no `config_error` receipt every
   five minutes). State still reconciles, so `first_seen` is honest and the opens fire once the
   UUID lands. `ROUTE_incidents` ships **empty**: the channel id is Dave-supplied.
10. **Delivery isolation.** The notifier runs only as its own unit (`workflow-incidents.service`)
    or by hand; **no workflow unit, runner or `bin/agent_propose.sh` references it** (asserted
    by grep in the tests). Each send is `subprocess.run([$INCIDENT_DELIVER_BIN (default
    bin/deliver.sh), --job $DELIVERY_JOB, --route <route>, --runtime none, --subject …,
    --message …], env + {DELIVER_DISCORD: "0"}, timeout=90)`; a non-zero exit, an
    `OSError`, a `TimeoutExpired`, or a receipt whose `outcome` is not `delivered`/
    `partial_success` with `buzz_result == "ok"` counts as *not sent*: `send_attempts += 1`,
    `last_send_error` recorded, one log line, and the sweep continues with the next message
    and **exits 0**. Success is read from the receipt line(s) appended to `$DELIVERY_RECEIPTS`
    during the call (byte offset taken before, only the delta read; match `job` and `subject`),
    which yields `buzz_event_id` and `channel` for the recovery pointer. Receipts under the
    workflow-receipt root are never written by the notifier. The unit exits non-zero only when
    the sweep itself cannot run (state dir unwritable); that fires `OnFailure=agent-alert@%n`
    to `ops`, which is the existing convention and does not loop back into this stream.
11. **API extension** (`bin/control_room_api.py`, confined edits): `incidents()` calls
    `workflow_incidents.derive` and merges the state file read-only, adding `class`, `key`,
    `firstSeen`, `lastSeen`, `resolvedAt`, `notifiedAt`, `observations` to each item and
    appending resolved-within-retention entries with `status: "resolved"`; `data_status` gains
    `incidentState: available|unavailable`. `SourcePaths` gains `incidents: Path` (default
    `runtime/var/incidents`, env `CONTROL_ROOM_INCIDENT_ROOT`) with a default so the positional
    `SourcePaths(repo, runtime, receipts)` in `tests/test_control_room_api.py:115` still works.
    `SystemdReader.show` adds `--timestamp=utc` (already present if T5.3 landed first — skip) so
    `LastTriggerUSec`/`ExecMainExitTimestamp` render as `Mon 2026-09-14 07:10:10 UTC` (MEASURED
    2026-09-14, systemd 259); `workflow_incidents.parse_systemd_utc` parses that **and** the ISO-8601
    `Z` form T5.3's `_systemd_for` emits for `lastTriggerAt` (raw systemd text stays under `raw`);
    nothing else in the API changes.
12. **Unit pair ships, stays disabled.** `systemd/workflow-incidents.service` +
    `systemd/workflow-incidents.timer` (`OnCalendar=*:0/5`, `RandomizedDelaySec=30`,
    `Persistent=true`). Installing needs sudo and enabling is Dave's decision — land-time steps
    below, never run by `/implement`. The digest is the daily gate inside the five-minute sweep
    (state-keyed, so a missed 07:00 fire is caught by the next one), which is why one pair
    suffices and systemd remains the only scheduler.
13. **Registries updated together**: `bin/buzz_routes.env` (route `incidents`, kind 9,
    notify `none`), `bin/buzz_producers.tsv` (`workflow-incidents.service	incidents	summary	wired	allowed	none`),
    `design/agents/trajan.toml` (`unit = "workflow-incidents"`, platform, standing, the three
    suites, `route = "incidents"`, `alerted = true`), `config/fleet-units.tsv`
    (`workflow-incidents	system	standing	trajan	timer`), `design/contracts/workflow-incidents.md`
    (light contract), `docs/runbook.md:179-192` platform-unit table row.
14. **Gate.** `bash bin/verify.sh` green **except** drift lines that this task's own
    `bin/deploy` + unit install clear (see Land-time steps). All new suites pass from fixtures
    with no box precondition. `tests/test_buzz_unit_wiring.sh`, `test_workflow_coverage.sh`,
    `test_fleet_ownership.sh`, `test_contract_schema.sh`, `test_control_room_api.sh` pass
    unchanged in intent.

## Files to modify

- `bin/control_room_api.py` — import `workflow_incidents` and `incident_state` (sibling
  `sys.path` import like `:29-40`); `SourcePaths` +`incidents` field with default and env
  (`:100-124`); `SystemdReader.show` +`--timestamp=utc` (`:143-148`); replace the body of
  `incidents()` (`:488-534`) with derive + state merge as in criterion 11. **Nothing else** —
  T5.3 may be editing routes/handlers in the same file; keep the diff to these three spots.
  If T5.3 has landed, also bump `STANDING_ENTRIES`/`LOGICAL_WORKFLOWS` in
  `tests/test_control_room_views.py` by one each for the new `workflow-incidents` manifest row.
- `bin/buzz_routes.env` — append the `incidents` route block with a comment: kind 9 (a
  chronological feed, read by Dave), `notify=none` (post, wake nobody — the required action
  is Dave's and waking an agent per alert spends tokens), `ROUTE_incidents=` **empty** until
  Dave creates the channel in Buzz Desktop, adds the `praetorium` service identity as a member
  (as the six channels were on 2026-08-07), pastes the UUID here, deploys, and adds the row to
  `~/.config/buzz-team/TEAM.md` (S1 check).
- `bin/buzz_producers.tsv` — one row (criterion 13). `summary`: composed at send time;
  `allowed`: silence is the product; `none`: no canvas.
- `design/agents/trajan.toml` — `[[workflows]]` entry after `inbox-backlog-alert` (`:153-163`
  shape): `unit = "workflow-incidents"`, `contract = "design/contracts/workflow-incidents.md"`,
  `surface = "platform"`, `status = "standing"`, `suite = ["tests/test_incident_notify.sh",
  "tests/test_workflow_incidents.sh", "tests/test_incident_state.sh"]`, `skills = []`,
  `trigger = "every 5 min (+30s jitter); daily digest gate 07:00"`, `what = "actionable
  workflow incidents → Buzz incidents stream; recovery; daily digest"`, `route = "incidents"`,
  `alerted = true`, `in_repo = true`, `notes` naming that it ships disabled and why.
- `config/fleet-units.tsv` — `workflow-incidents	system	standing	trajan	timer`.
- `docs/runbook.md` — one row in the `| Unit | Role |` platform table (`:179-192`), next to
  `inbox-backlog-alert.timer`: cadence, "ships disabled", route `incidents`, state path.
- `tests/test_control_room_api.py` — extend, do not rewrite: (a) a `failed` receipt for a
  workflow whose fake timer is `inactive` **is** an incident with `class ==
  "failed-assertion"` and `id == "failed-assertion:daily-plan"`; (b) `decline` and `artifact`
  receipts yield no run incident; (c) two malformed receipts get path-keyed ids that do not
  change when a third is added; (d) a state file with a resolved entry surfaces it with
  `status == "resolved"` and `resolvedAt`; (e) `data_status.incidentState == "unavailable"`
  when the state dir is absent.

## Files to create

- `bin/workflow_incidents.py` — incident schema v1, `CLASSES`, `SEVERITY`, `IMMEDIATE_CLASSES`,
  `REQUIRED_ACTION` defaults, `key(...)`, `parse_systemd_utc(text) -> datetime|None`,
  `derive(workflows, malformed, source_errors, declared, now, grace_secs) -> list[dict]`
  (pure; input is exactly what `ControlRoomReadModel.workflows()` and `.receipts()` return),
  `load_declared(dir) -> (list, errors)`, `declare(dir, incident)`, `resolve_declared(dir,
  key)`, and a `main()` with `declare`/`resolve` subcommands. One concept: what an incident is.
  ≤ 220 lines.
- `bin/incident_state.py` — `load(path)`, `save(state, path)` (atomic), `reconcile(state,
  observed, now, sources_ok: bool)`, `prune(state, now, retention_days)`, `digest_due(state,
  now_local, at_hhmm)`, `sanitise_key(key) -> filename`. Pure functions plus two I/O
  functions. ≤ 160 lines.
- `bin/incident_notify.py` — the CLI: `--mode sweep` (default) | `--digest` | `--dry-run`;
  `--now <iso>`, `--state-dir`, `--routes-file`, `--deliver-bin`, `--receipts-log`,
  `--repo-root`, `--runtime-root`, `--receipt-root`, `--route`, `--job`, `--link-template`,
  `--grace-secs`, `--digest-at`, `--max-sends`, `--max-attempts`, `--retention-days` — every
  flag defaulting from the env names in criteria 6-10 and `CONTROL_ROOM_*`. Builds
  `ControlRoomReadModel(SourcePaths(...), systemd=SystemdReader())`, derives, reconciles,
  saves, sends, saves again. Message rendering in two small functions
  (`render_immediate`, `render_recovery`, `render_digest`) so the tests assert on text
  without a transport. Logs one line per decision to `$HOME/logs/workflow-incidents.log`
  (`<utc> incident_notify: ...`), same shape as `bin/delivery_common.sh:33-36`. ≤ 260 lines.
- `bin/deliver_incidents.sh` — the unit-facing adapter (units exec `.sh` adapters; the wiring
  test's hook regex names `deliver[a-z_]*\.sh`): `set -u`, resolves `BIN_DIR`, `exec python3
  "$BIN_DIR/incident_notify.py" "$@"`. Executable. ≤ 20 lines with a header saying why it
  exists.
- `systemd/workflow-incidents.service` — copy the `inbox-backlog-alert.service` shape:
  `Type=oneshot`, `User=dave`, `Environment=DELIVERY_ROUTE=incidents`,
  `Environment=DELIVERY_JOB=%n`, `Environment=DELIVERY_RUNTIME=none`,
  `Environment=CONTROL_ROOM_REPO_ROOT=/home/dave/dev/agent-workforce` (the read model needs
  `design/`, which `bin/deploy` does not ship — the same fallback `SourcePaths.defaults`
  already takes, declared here instead of implied), `Environment=INCIDENT_LINK_TEMPLATE=http://praetorium:8787/api/v1/incidents#{key}` (T5.3 binds the
  Tailscale address only, never loopback)
  (T5.3 repoints this at the incident page once it exists),
  `ExecStart=/home/dave/agent-workforce/bin/deliver_incidents.sh`, `TimeoutStartSec=4min`,
  `NoNewPrivileges=true`, `OnFailure=agent-alert@%n.service`. Header: model-free, ships
  disabled, never invoked from a run path, what the one hand-started run proves.
- `systemd/workflow-incidents.timer` — `OnCalendar=*:0/5`, `RandomizedDelaySec=30`,
  `Persistent=true`, `[Install] WantedBy=timers.target`. Header: **not enabled by any task**;
  `sudo systemctl enable --now workflow-incidents.timer` is Dave's call.
- `design/contracts/workflow-incidents.md` — light contract on the `inbox-backlog-alert.md`
  model: Identity (unit, owner trajan, surface platform, runner `bin/deliver_incidents.sh`,
  route `incidents`, cadence, alerted yes, remediation owner Dave, contract version 1
  2026-09-14), Trigger, Inputs (receipt root, manifests via `CONTROL_ROOM_REPO_ROOT`, systemd,
  declared dir, route table), Outputs (**Artifact:** state file + at most one message per
  transition; **Beneficiary:** Dave; **Next actor:** Dave; **Next action:** act on the named
  required action; **Benefit hypothesis:** a failed run is seen within five minutes and never
  twice; **Benefit signal:** `Unknown`), Decline conditions (`none` — silence is the product),
  Side effects, two `when=sweep` checks: (1) `timer-fired-within-window` — exit 77 when
  `UnitFileState` is `disabled` (the fleet-off posture), else fail if `LastTriggerUSec` is
  older than 30 min; (2) `state-fresh-when-active` — exit 77 when disabled, else fail if
  `~/agent-workforce/var/incidents/state.json` is older than 30 min. Known failure modes:
  route unset (state accrues, nothing sends), corrupt state re-alerts once, manifests read
  from the source checkout (a feature branch there changes what the sweep sees — manifests
  only, never receipts or state).
- `tests/test_workflow_incidents.py` + `tests/test_workflow_incidents.sh` (wrapper `cd
  repo && python3 tests/test_workflow_incidents.py`, T5.1 shape).
- `tests/test_incident_state.py` + `tests/test_incident_state.sh`.
- `tests/test_incident_notify.py` + `tests/test_incident_notify.sh`.
- `tests/fixtures/incidents/bin/deliver.sh` — fake transport: appends argv to
  `$FAKE_DIR/argv.log`, then per `$FAKE_DELIVER_MODE` (`ok` → appends a `delivered` receipt
  line with `buzz_result=ok`, `buzz_event_id=$FAKE_EVENT_ID`, `channel=$FAKE_CHANNEL`, `job`,
  `subject` to `$DELIVERY_RECEIPTS` and exits 0; `failed` → appends an `outcome=failed`,
  `buzz_result=failed` line, exits 0 — deliver.sh's real behaviour; `crash` → exits 1 with no
  receipt; `hang` → sleeps 300). Receipt lines are JSON objects on one line, the
  `delivery_receipt.py` shape.
- `tests/fixtures/incidents/bin/systemctl` — fake for the read model's multi-property `show`:
  prints `Key=Value` for every `--property=` from `$FAKE_SYSTEMD_STATE/<unit>/<Key>` (empty
  when absent), records calls, exits 0; `--user` scope exits 1 with `user bus unavailable`
  (matches `tests/test_control_room_api.py:73-87`). The T5.1 fake
  (`tests/fixtures/contract-exec/bin/systemctl`) answers one property per call and prints bare
  values, so it cannot be reused here — say so in its header.
- `tests/fixtures/incidents/routes.env` — `ROUTE_incidents=<fixture uuid>`,
  `_kind=9`, `_notify=none`; and `routes-unset.env` with `ROUTE_incidents=` empty.
- `tests/fixtures/incidents/receipts/knowledge-digest/synthetic-failed.json` — a schema-valid
  receipt: `workflow_id "knowledge-digest"`, `run_id "synthetic-failed-2026-09-14"`, `unit
  "knowledge-digest"`, `agent "claudius"`, outcome `failed`, reason `failed checks:
  artifact-exists`, assertions `[{"id":"artifact-exists","status":"failed","message":"no
  proposal under _inbox/agents"}]`, usage/cost `unavailable` with nulls, `next_action
  {"actor":"Dave","action":"Check the knowledge-digest attempt log and re-run by hand"}`,
  `started_at 2026-09-14T03:00:00Z`, `ended_at 2026-09-14T03:04:00Z`. **This file is also
  what Dave drops into the live receipt root for the evidence run**, so it is named
  `synthetic-*` and its dates are fixed.
- `tests/fixtures/incidents/receipts/knowledge-digest/synthetic-recovered.json` — same
  workflow, `run_id "synthetic-recovered-2026-09-14"`, outcome `artifact`, `artifact {"uri":
  "file:///home/dave/agent-worktrees/inbox/_inbox/agents/2026-09-14_knowledge-digest.md"}`,
  all assertions passed, `ended_at 2026-09-14T09:04:00Z` (later, so it sorts newest).
- `tests/fixtures/incidents/receipts/daily-plan/decline.json` — outcome `decline` (silence
  case); and `.../daily-plan/skipped.json` — outcome `skipped`, reason `lock held`.

## Test plan

TDD: write each suite red first, then the module. Python `unittest`, fixture roots in
`tempfile`, manifests generated in `setUp` exactly as `tests/test_control_room_api.py:90-121`
does (copy its `FakeSystemd` for the pure tests; the fake `systemctl` on `PATH` for the CLI
tests). `TZ=UTC` in every CLI subprocess env so the digest gate is deterministic. No box
precondition; every suite runs on a bare checkout.

`tests/test_workflow_incidents.py` (derivation, pure):
- healthy `artifact` receipt → `[]`; `decline` receipt → `[]` (silence is asserted, not assumed).
- `failed` + failed assertion → one `failed-assertion:<wf>` with `failed_assertion`, `run_id`,
  `evidence` containing the receipt path and the artifact uri when present.
- `failed` with zero failed assertions → `missing-artifact`.
- `skipped` → `incomplete-run` with the reason.
- fake timer `active`, `lastTriggerAt` 3 h ago, no receipt, service `inactive` → `incomplete-run`
  with the journalctl evidence line; same with `lastTriggerAt` 10 min ago → nothing (grace);
  timer `inactive` → nothing (paused stays silent); service `running` → nothing.
- the same failed receipt under a paused (all timers inactive) workflow → still an incident.
- `contract-unavailable` present and **not** in `IMMEDIATE_CLASSES`.
- two malformed receipts → keys carry their relative paths; adding a third leaves them unchanged.
- `source_errors` `receipt directory unreadable` → `control-failure:incident-sweep:receipts`;
  `receipt directory unavailable` (missing) → nothing.
- declared file with unknown class → error, not an incident; valid → passed through with its key;
  resolved → absent.
- `parse_systemd_utc("Mon 2026-09-14 07:10:10 UTC")` → aware datetime; `"2026-09-14T07:10:10Z"` → the
  same instant; `""`/`"n/a"` → `None`.
- `declare` then `resolve` round-trip through `main()`.

`tests/test_incident_state.py` (state, pure + I/O):
- open → update (observations 1 → 2 only when `run_id` changes; `last_seen` moves) → close
  (`resolved_at`) → re-open (new `first_seen`, `notified_at` reset).
- `sources_ok=False` closes nothing and still opens/updates what was observed.
- `prune` drops resolved entries older than retention and never an open one.
- `save` is atomic (no `.tmp` left; a raised error mid-write leaves the old file intact);
  corrupt file → moved aside, fresh state, the sidecar name recorded.
- `digest_due`: 06:59 → false; 07:00 with `last_digest_at` yesterday → true; 07:04 same day
  after stamping → false; `last_digest_at == null` → true after 07:00.

`tests/test_incident_notify.py` (end to end through the CLI, fake transport):
1. **silence** — healthy + decline receipts → zero `deliver.sh` invocations, state has no open
   incidents, exit 0, log line `0 open, 0 sent`.
2. **immediate** — `synthetic-failed.json` → exactly one invocation; argv carries `--job
   workflow-incidents.service --route incidents --runtime none` and subject `[incident]
   failed-assertion:knowledge-digest`; body lines assert `workflow: knowledge-digest`,
   `agent: claudius`, `failure: failed-assertion — failed checks: artifact-exists`, `failed
   check: artifact-exists`, `time: first seen 2026-09-14T03:04:00Z`, `required action: Check the
   knowledge-digest attempt log…`, `incident: http://…#failed-assertion:knowledge-digest`,
   `evidence: knowledge-digest/synthetic-failed-2026-09-14.json`; `DELIVER_DISCORD=0` in the
   fake's captured env; state `notified_at`, `notify_event_id`, `notify_channel` set.
3. **dedup** — sweep again → zero new invocations; add a second failed receipt with a later
   `ended_at` and a different `run_id` → zero invocations, `observations == 2`, `run_id`
   updated.
4. **recovery** — add `synthetic-recovered.json` → exactly one invocation, subject `[recovered]
   failed-assertion:knowledge-digest`, body carries `open since`, `resolved`, the healthy
   receipt path as evidence and `alert: buzz://message?channel=<fake channel>&id=<fake event>`;
   `resolved_at` set; a further sweep → nothing.
5. **digest** — two open incidents + one resolved, `--now 2026-09-15T05:03:00Z` (= 07:03
   Amsterdam; run with `TZ=Europe/Amsterdam` for this case) and `last_digest_at` yesterday →
   one `[incident digest] 2 unresolved` invocation listing both, sorted by `first_seen`, and
   **not** the resolved one; `--now` four minutes later → no second digest; zero open with the
   gate due → no invocation at all and `last_digest_at` stamped; an open incident with
   `notified_at == null` renders `unsent (<error>)`.
6. **route unset** — `routes-unset.env` → zero invocations, log line `has no channel UUID`,
   state holds the open incident with `notified_at == null`; switch to `routes.env` → the
   pending open sends exactly once.
7. **delivery-failure isolation** — with `FAKE_DELIVER_MODE=failed` → exit 0, `notified_at`
   null, `send_attempts == 1`, `last_send_error` names the receipt outcome; `crash` → exit 0,
   attempts 2; `hang` with `--deliver-timeout 2` → exit 0 within 5 s, attempts 3; a
   non-executable `--deliver-bin` → exit 0; after `--max-attempts` failures no further
   invocation on the next sweep and the digest marks it `unsent`; the receipt root's file list
   and sha256 sums are identical before and after every case; and a repo grep — every
   `systemd/*.service` except `workflow-incidents.service`, every `bin/run_*_cc.sh`,
   `bin/agent_propose.sh`, `bin/contract_exec.py` — finds no `incident_notify` /
   `deliver_incidents`, which is the structural proof it is never inside a run path.
8. **flood cap** — 12 failed workflows with `--max-sends 10` → 10 invocations, then 2 on the
   next sweep.
9. **degraded source closes nothing** — open incident, then point `--receipt-root` at a file
   (not a directory) → sweep opens `control-failure:incident-sweep:receipts`, closes nothing,
   sends the control-failure once.
10. **dry run** — `--dry-run` prints the rendered messages, zero invocations, state file
    byte-identical.

Existing suites that must stay green with the new rows/files: `tests/test_buzz_unit_wiring.sh`
(route declared with kind and notify; unit carries route/job/runtime and a matching hook; no
transport call outside `deliver.sh`), `tests/test_workflow_coverage.sh` (timer family declared,
suites exist), `tests/test_fleet_ownership.sh` (manifest ⇔ fleet-units), `tests/test_contract_schema.sh`
(contract shape), `tests/test_control_room_api.sh` (extended), `tests/test_deploy_drift.sh`.

## Out of scope / do not touch

- **T5.3 — Control Room views**: the frontend, any new API route, `_route`/`ControlRoomHandler`
  in `bin/control_room_api.py`, hosting unit for the API. This brief's edits to that file are
  the three spots named above and nothing else.
- **T5.3a — broker**: the root-owned control broker, its unit, its audit receipts. Wiring
  `workflow_incidents.py declare --class control-failure` into it is T5.3a's step; this brief
  only provides the command.
- **T5.3b — PR generator**: schedule-change / retirement PR tooling.
- **T5.2 — `bin/agent_propose.sh`, every `bin/run_*_cc.sh` runner, `bin/contract_exec.py`,
  `bin/contract_checks.py`**: no receipt is written by this task and no run path is edited;
  the isolation test greps them read-only.
- **T6.1 — hermes scripts** (`bin/*hermes*`, `~/.hermes/**`, `systemd/user/hermes-gateway.service`).
- `bin/deliver.sh`, `bin/delivery_receipt.py`, `bin/delivery_common.sh`, `bin/buzz_publish.sh`
  — transport stays as is; the notifier is a caller.
- `bin/workflow_receipt.py` — the receipt schema is not extended (no `blocked` field; that is
  why `blocked-next-action` is declared-only).
- The twelve workflow timers and their units; `~/.config/**`; `~/.config/buzz-team/TEAM.md`
  (Dave/Marcus adds the row by hand when the UUID exists); `.claude/briefs/current.md`.
- Enabling any timer, creating the Buzz channel, minting any identity.

## Implementation order

1. `bin/workflow_incidents.py` + `tests/test_workflow_incidents.{py,sh}` (red → green).
2. `bin/incident_state.py` + `tests/test_incident_state.{py,sh}`.
3. Fixtures under `tests/fixtures/incidents/` (fake `deliver.sh`, fake `systemctl`, routes,
   the four receipts) — validate the receipts with `workflow_receipt.validate` in a test.
4. `bin/incident_notify.py`, `bin/deliver_incidents.sh` + `tests/test_incident_notify.{py,sh}`.
5. `bin/control_room_api.py` edits + `tests/test_control_room_api.py` additions.
6. `bin/buzz_routes.env`, `bin/buzz_producers.tsv`, `systemd/workflow-incidents.{service,timer}`,
   `design/agents/trajan.toml`, `config/fleet-units.tsv`, `design/contracts/workflow-incidents.md`,
   `docs/runbook.md` — then run `tests/test_buzz_unit_wiring.sh`, `test_workflow_coverage.sh`,
   `test_fleet_ownership.sh`, `test_contract_schema.sh` individually before the full gate.
7. `bash bin/verify.sh`. On the feature branch expect **exactly** these red drift lines and no
   others: new `bin/` files not in `~/agent-workforce/bin/`, changed `bin/buzz_routes.env`,
   `bin/buzz_producers.tsv`, `bin/control_room_api.py`, `config/fleet-units.tsv`; and
   `source-only: systemd/workflow-incidents.service` / `.timer` not installed in
   `/etc/systemd/system`. Anything else red is a defect. Report the drift; do not soften the check.
8. Commit by hand immediately (`bin/auto-sync` sweeps a dirty tree every 15 min under a generic
   message — `CLAUDE.md` § Where things live).

## Land-time steps (Dave / sudo — not `/implement`)

1. `bin/deploy` (ships `bin/`, `config/`, `systemd/` staging) — clears the bin/config drift.
2. `sudo cp systemd/workflow-incidents.service systemd/workflow-incidents.timer /etc/systemd/system/
   && sudo systemctl daemon-reload` — clears the unit drift. **Do not enable the timer.**
   Enabling (`sudo systemctl enable --now workflow-incidents.timer`) is Dave's decision; the
   plan's DoD item 5 (`docs/dev-plan-2026-09.md:91-92`) lists the incident digest among units
   "installed and enabled", `:75` says no task enables a timer, and this brief follows the
   orchestrating instruction: ships disabled, enable is his call.
3. Buzz: create the `incidents` channel in Desktop, add the `praetorium` service identity as a
   member, paste the UUID into `bin/buzz_routes.env`, add the TEAM.md row (kind 9), `bin/deploy`,
   `bash bin/verify.sh` (the S1 check now joins it).
4. `bash bin/verify.sh` green on `main`.

## Evidence run (one unit, hand-started by Dave, three starts)

Precondition: steps 1-3 above. Then, in order, each at a moment of his choosing:
1. `mkdir -p ~/agent-workforce/var/workflow-receipts/knowledge-digest && cp
   ~/dev/agent-workforce/tests/fixtures/incidents/receipts/knowledge-digest/synthetic-failed.json
   ~/agent-workforce/var/workflow-receipts/knowledge-digest/` then
   `sudo systemctl start workflow-incidents.service` → one `[incident]
   failed-assertion:knowledge-digest` message in the stream; `tail -1
   ~/logs/delivery-receipts.jsonl` shows `job=workflow-incidents.service outcome=delivered`;
   `~/agent-workforce/var/incidents/state.json` has the entry with `notified_at`.
2. `sudo systemctl start workflow-incidents.service` again → **no** new message, no new receipt
   line (dedup).
3. `cp .../synthetic-recovered.json` beside it, start again → one `[recovered] …` message
   pointing at the alert; the healthy receipt itself produced no `[incident]` (healthy stays
   silent). Cleanup: `rm ~/agent-workforce/var/workflow-receipts/knowledge-digest/synthetic-*.json`;
   the resolved state entry prunes itself after 14 days. A further start → silence.
Optional: `~/agent-workforce/bin/deliver_incidents.sh --digest` (as dave, no sudo) between
steps 1 and 3 shows one digest listing the open incident; with nothing open it sends nothing.
That is DoD item 3 in full: one synthetic incident reaches the stream, repeats are
deduplicated, recovery is visible, healthy runs stay silent.

## Notes / preconditions

- Confirmed 2026-09-14: `~/agent-workforce/var/workflow-receipts/` absent; all twelve workflow
  timers `UnitFileState=disabled`; systemd 259 accepts `systemctl show --timestamp=utc` and
  renders `Mon 2026-09-14 07:10:10 UTC`; `bin/buzz_agents.env` lists marcus, claudius,
  augustus, trajan (no aurelian, no praetorium — the service identity is credential-only).
- **Decision — one unit pair; the digest is a daily gate inside the five-minute sweep.** A
  timer cannot pass a mode, a template family would need a manifest/contract shape the
  registries do not model, and two plain pairs double every registry row; the state-keyed gate
  also survives a missed 07:00 fire. systemd still schedules every run.
- **Decision — `notify=none`, Buzz-only (`DELIVER_DISCORD=0`).** The reader is Dave; a
  mention wakes an agent and spends tokens per alert, which he asked not to; Discord dual-run is
  the migration baseline being retired and a second surface would double every alert.
- **Decision — dedup key `<class>:<workflow_id>`, not per run.** A nightly failure is one
  persistent incident; a per-run key re-alerts every night, which the gate forbids. A class
  change on the same workflow is a different failure and is news (one close, one open).
- **Decision — run-derived incidents ignore the paused label; staleness of a paused workflow
  is silent.** Needed for the evidence run with the fleet off, and a failed last run is an
  exception until a healthy one lands. The screen's "stale while paused" (DoD item 1) is T5.3's.
- **Decision — `blocked-next-action` is declared-only; `control-failure` is sweep-source-derived
  plus declared.** No receipt field carries "blocked"; a `due_at` heuristic would raise false
  persistent alerts. The command exists so T5.3a can declare without knowing the state layout.
- **Decision — a sweep that cannot see a source closes nothing.** Missing receipts root is
  pre-T5.2 normal (no incident); unreadable root or degraded manifests is a control failure
  and suspends closes.
- **Decision — corrupt state is moved aside and re-alerts once**, rather than silently
  disabling alerts; the sidecar name is logged.
- **Decision — the read model reads `design/` from `CONTROL_ROOM_REPO_ROOT` (source checkout)**,
  exactly as `bin/control_room_api.py` already does via its fallback; declared in the unit so
  the dependency is visible. Reusing the API's join outweighs a second, design/-free
  derivation. Receipts and state are runtime paths and unaffected by the checkout's branch.
- **Decision — incident link = API collection URL + `#<key>`** until T5.3 names the incident
  page; a unit `Environment=` knob, no code change to repoint.
- **Decision — knobs**: cadence 5 min, grace 2 h, flood cap 10/sweep, attempts cap 6,
  retention 14 days, digest 07:00 local, deliver timeout 90 s. All env-overridable.
- **Decision — `SystemdReader.show` gains `--timestamp=utc`.** The read model's timestamp
  strings switch from CEST to UTC (the receipt schema is UTC already); the frontend renders
  strings, so nothing else depends on the old form.
- Coding standards: Python for everything new under `bin/` except the unit-facing adapter,
  which is shell by the repo's adapter convention; one concept per file; tests co-located and
  named above; TDD.
- Size: S per the plan; the file count is what the registries demand of any new unit, not
  extra scope. Land cycle is `edit → deploy → verify → commit`; on the branch the gate is red
  only on the drift named in step 7.
