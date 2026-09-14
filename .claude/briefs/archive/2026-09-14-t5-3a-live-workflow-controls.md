# Brief: T5.3a — Live workflow controls through a root-owned allowlisted broker

**Date:** 2026-09-14   **Verify:** `bash bin/verify.sh` from the repo root (includes
`bin/check_deploy_drift.sh`; extra gates and smoke: none for this task — the gate is red on the
branch for exactly the files § Land-time steps names, and green only after `bin/deploy` plus the
sudo installs there).

**Size:** M. **Depends on:** T5.3 (its seam files, `control_reader=` hook, `actions.js`, fixture
helper and the two 501 stubs must exist on `main`). T5.1 landed 2026-09-11 (receipt shape). T5.2 is
an **evidence** dependency only.

**Standing constraint (Dave, 2026-09-14):** the scheduled fleet is OFF — all twelve system workflow
timers disabled since 2026-09-11 and they stay disabled. **No step in this brief enables, starts,
stops or disables a workflow timer.** Every test runs from fixtures against a fake `systemctl` on
`PATH` (precedent: `tests/fixtures/contract-exec/bin/systemctl`, T5.1). The units this brief
installs are the broker's socket and its per-connection template — a control surface, not a
workflow. The one hand-started workflow run is T5.2/T5.3's `knowledge-digest.service`; T5.3a adds
no second run, it routes that same run through **Run now** so one run yields T5.2's receipt, T5.3's
rendering and T5.3a's run-id linkage (§ Evidence-time). Resume is designed here and proven on
fixtures; the first live resume is DoD item 7, Dave's moment, not this brief's.

## Acceptance criteria

Task gate (`docs/dev-plan-2026-09.md:487-499`), the Notion card ("Dave can safely
pause/resume/run/retry/stop allowlisted workflows; current runs are never killed by pause; UI state
reconciled from systemd; every action emits an audit receipt; unknown ids/actions refused") and plan
DoD item 1 (`:79-85`, the controls half) and item 5 (`:98-99`, broker unit installed and enabled,
twelve timers untouched) — all satisfied:

1. **Allowlisted, never arbitrary.** The browser submits `{workflow_id, action, reason}` (+ the
   additive fields in § Request) and nothing else reaches `systemctl`. The broker accepts a
   `workflow_id` present in a **root-owned rendered allowlist** (`/etc/control-room/allowlist.json`,
   derived from `design/agents/*.toml` + `systemd/` + `design/contracts/`) and an `action` in
   `pause | resume | run_now | retry | stop`. Unknown ids, unknown actions, unknown `trigger`
   values, extra keys, non-JSON and oversize bodies are refused **and receipted**; zero `systemctl`
   calls are made for a refused request that fails validation. argv is built from constants plus a
   unit name that matched `^[a-z0-9][a-z0-9-]{0,63}$` **and** the allowlist; the request's strings
   are never interpolated into a command.
2. **Root-owned means root-owned.** The broker runs as root from a root-owned installed copy
   (`/usr/local/lib/control-room/control_broker.py`), reads a root-owned allowlist, and writes
   receipts into a root-owned state directory. Nothing root executes or trusts is dave-writable.
   `bin/check_deploy_drift.sh` compares both installed files against source, so the copies cannot
   rot silently.
3. **Pause never kills the current run.** `pause` = `disable --now <unit>.timer` per timer trigger
   and **no** `stop` of any service; proven on the fixture where the service is `active/running`
   during the pause: the receipt's `after` shows the timer `inactive/disabled` and the service still
   `running`.
4. **Resume shows the `Persistent=true` catch-up implication before applying.** Resume is always
   two-stage: `stage: "preview"` returns the implication (persistent flag, last trigger, missed
   elapse, whether `enable --now` fires the service immediately, the next scheduled elapse) and a
   `preview_token`; `stage: "apply"` requires a fresh token for the same workflow whose recorded
   state fingerprint still matches — otherwise refused `preview_stale` / `preview_required`.
5. **Run now returns a run id** — the service's `InvocationID` after `start --no-block`, which is
   the same id `bin/contract_exec.py` `run_identity` writes into the run's receipt, so
   `/runs/<run_id>` resolves once the executor writes it.
6. **Retry only where the contract declares idempotent** (`| Retry | idempotent: <reason> |` in the
   `## Identity` table, § Retry declaration) **and** the last run failed; otherwise refused
   `not_idempotent` / `state_conflict`, and the button is disabled with the reason as `title`.
7. **Stop current run needs `confirm: true` and a non-empty reason**; refused
   `confirmation_required` / `reason_required` otherwise; refused `state_conflict` when nothing is
   running.
8. **UI state is reconciled from systemd after each action, never assumed from the click.** The
   broker re-reads `systemctl show` for every unit before and after; the HTTP response carries a
   `control` object re-read from the read model; `actions.js` re-fetches `GET /api/v1/workflows/{id}`
   after every response (T5.3's rule, kept).
9. **Every action — applied, refused, failed, previewed — emits one audit receipt** under
   `/var/lib/control-room/receipts/<workflow_id>/<receipt_id>.json` with actor, action, reason,
   before/after state (reconciled from `systemctl`), request/completion timestamps, result, refusal
   code, the exact argv run and their exit codes, run id, next scheduled run and links. The one
   un-receipted outcome is the broker being unreachable (502): nothing can write the receipt, and
   the screen logs it to the journal.
10. **System-scope and user-scope units are addressed correctly**: system units as bare
    `systemctl …`, user units as `systemctl --user --machine=dave@.host …` from the root broker;
    the user timer's stamp file is read from dave's stamp directory — proven on fixtures with
    `buzz-pr-watch` (user) against `knowledge-digest` (system).
11. **Agents cannot reach the broker.** The socket is `root:control-room 0660`; only
    `control-room.service` carries the `control-room` supplementary group (via a drop-in). Every
    other uid-1000 process — every agent on this box — is refused at `connect()`. Control POSTs
    that reach the screen from this host's own address are refused `peer_denied` and receipted.
12. `paused` stays an owned state: after `pause` the workflow renders `paused` (T5.3's rule from
    `UnitFileState=disabled` / inactive), never `failed`; a stale artifact stays `stale`.
13. Verify green after land; fixture suites green on the branch; drift red on the branch is
    explained by exactly the files this brief adds (§ Land-time steps).

## Existing state (read, confirmed 2026-09-14)

- `systemd 259 (259.5-0ubuntu3.4)` on the box — `systemctl --user --machine=dave@.host` is
  supported (≥ 248). `systemctl show` accepts `--timestamp=utc` (T5.3 measured). `/var/lib/systemd/
  timers/stamp-<unit>.timer` are root-owned 0644 (`stamp-knowledge-digest.timer` mtime 2026-09-06
  09:04 — the catch-up evidence); dave's are `~/.local/share/systemd/timers/`.
- No `control-room` group exists (`getent group control-room` → empty). No `*.socket` unit in
  `/etc/systemd/system/` or `~/.config/systemd/user/` today.
- `bin/check_deploy_drift.sh:451-452` compares `systemd/` ↔ `/etc` for `*.service` and `*.timer`
  **only** — a `.socket` would deploy (rsync of the content tree) and be compared by nothing.
  Drop-ins `*.d/*.conf` at depth 2 are compared (`:490-525`). The precedent for a root unit is
  `systemd/ttm-pool-drain.service`, whose binary is untracked; this brief does better (criterion 2).
- Manifests: 31 standing entries; **26 are `kind = "timer"`** (24 system + `buzz-pr-watch` user)
  → **25 logical timer workflows** (`augustus-content` owns `augustus-content` +
  `content-change-dispatch`); the 5 `buzz-agent@*` are `kind = "service"`, the 2 `nekovri-*` are
  `status = "spent"`. Every timer entry has `systemd/<unit>.timer` + `.service` (user: `systemd/user/`).
  Count from the manifests at render time; never write 25 into a test as a live claim.
- `bin/control_room_api.py`: `contract_identity()` keeps only `Unit/Units/Owner/Owners/Surface`
  rows; the Identity table already carries free-form rows (`Executor`, `Cadence`, `Task slug`) and
  `tests/test_contract_schema.py` matches only `Owner`/`Unit` rows → a `Retry` row breaks nothing.
  `_contract()` returns `path` (repo-relative) — the retry policy re-reads the file from it.
  `_run_summary()` exposes `id` and `outcome` — the retry policy reads `item["lastRun"]`.
  `make_server()` binds `model` as a class attribute of a per-server handler subclass; the
  controller is bound the same way (`server.RequestHandlerClass.control = …`).
- `bin/contract_exec.py:272-287` `run_identity`: at `sweep` vantage the run id is the service's
  `InvocationID`; in-run it is `$INVOCATION_ID` — the same value, so the broker's `run_id` is the
  receipt's `run_id`.
- T5.3 seam (its brief § Seams): buttons `data-action="pause|resume|run_now|retry|stop"`, POST
  `/api/v1/control/actions` with header `X-Control-Room: 1`, result region `<pre id="control-result">`,
  `control.lastAction` filled through `ControlRoomReadModel(control_reader=…)`, real responses
  `200 {"receipt", "control"}` / refusal `403|400 {"error", "receipt"}`. Reserved for this brief:
  `bin/control_room_control.py`, `bin/control_broker.py`, `systemd/control-room-broker.*`,
  `tests/test_control_room_control.*`, `tests/test_control_broker.*`, `tests/fixtures/control-broker/`.
- `tests/ci-expected-skips.txt` — this brief adds **no** SKIP line: both new suites run everywhere
  (fixtures + shims), and the drift check's new section runs inside its existing on-box predicate.

## Architecture (complete option; reasons in § Notes)

### Trust boundary — three layers, each with one job

```
Mac browser ──tailnet──▶ control-room.service (dave + group control-room)
                           │  bin/control_room_control.py: shape check, actor, HTTP mapping
                           ▼  unix socket /run/control-room-broker.sock  root:control-room 0660
                         control-room-broker.socket (Accept=yes) ─▶ control-room-broker@N.service (root)
                           │  /usr/local/lib/control-room/control_broker.py  (root-owned copy of bin/control_broker.py)
                           │  reads /etc/control-room/allowlist.json         (root-owned, rendered from the repo)
                           │  writes /var/lib/control-room/receipts/…        (StateDirectory, root-owned, world-readable)
                           ▼
                         systemctl [--user --machine=dave@.host] {show,disable --now,enable --now,start --no-block,stop --no-block}
```

- **Transport: root-owned unix socket + system units, `Accept=yes`** (inetd-style: one broker
  process per connection, the connection is stdin/stdout). Not a sudoers helper: a sudoers line
  would let *every* uid-1000 process — every agent — invoke root, and the helper under `$HOME` would
  be dave-writable root code; sudoers is also outside every tree the drift check reads. The socket
  gives the kernel the access decision (group + mode), systemd owns the socket lifecycle
  declaratively in a unit the drift check compares, and `Accept=yes` makes the broker a
  stdin→stdout filter with no daemon state — trivially driven by tests and by a `sudo` CLI.
- **Who may connect:** `SocketUser=root SocketGroup=control-room SocketMode=0660`.
  `control-room.service` gains `SupplementaryGroups=control-room` through a **drop-in**
  (`systemd/control-room.service.d/broker.conf`) — systemd grants the group to that process only;
  dave is **not** added to the group, so a dave shell, a runner or a `buzz-agent@*` cannot connect.
  Belt and braces: the broker checks `SO_PEERCRED` uid ∈ `CONTROL_BROKER_PEER_UIDS` (`1000`).
- **Root executes only root-owned files.** `ExecStart` names the installed copy, never
  `/home/dave/…`; `bin/check_deploy_drift.sh` gains a section comparing
  `bin/control_broker.py` ↔ `/usr/local/lib/control-room/control_broker.py` and the rendered
  allowlist ↔ `/etc/control-room/allowlist.json` (both directions, `cmp`). The broker is
  **self-contained** (stdlib, no sibling import) — it must not import from the dave-writable `bin/`.
- **Policy is in the broker, not the screen** (the same rule `~/CLAUDE.md` records for the Notion
  broker): allowlist, action vocabulary, state preconditions, confirmation/reason requirements,
  preview token, idempotency gate, receipts. The screen validates shape, adds the actor, maps
  refusal codes to HTTP status, and re-reads state. A client talking to the socket directly gains
  nothing the screen does not enforce.

### Allowlist — `bin/control_broker_allowlist.py`

`render(repo) -> dict` (pure; deterministic bytes: `json.dumps(sort_keys=True, indent=2) + "\n"`,
no timestamp, no commit hash — the drift check compares bytes):

```
{"schema": 1,
 "workflows": {"<logical id>": {"owner": "<agent>", "contract": "design/contracts/<x>.md"|null,
                                "retry": bool, "retry_reason": str|null,
                                "triggers": [{"unit": "<unit>", "scope": "system"|"user"}, …]}, …},
 "excluded": [{"unit": "buzz-agent@marcus", "owner": "marcus", "reason": "kind = service (always-on, not a timer workflow)"},
              {"unit": "nekovri-subsidy-kickoff", "owner": "trajan", "reason": "status = spent"}, …]}
```

Rules: include `[[workflows]]` entries with `status == "standing"` and `kind` (default `timer`)
`== "timer"`; logical id = `logical_workflow or unit` (the read model's own fold); scope = `scope or
"system"`; **require** `systemd/<unit>.timer` and `systemd/<unit>.service` (user: `systemd/user/`)
to exist in the repo, else exclude with reason `no timer/service file in systemd/`; unit and id
must match `^[a-z0-9][a-z0-9-]{0,63}$` else exclude with reason `unit name outside the broker's
grammar`. `retry` from the contract's Identity `Retry` row (§ Retry declaration); a logical
workflow with two contracts or none → `retry: false`, reason named. CLI: `render [--repo R]`
prints the JSON; `check [--repo R] [--installed /etc/control-room/allowlist.json]` exits 1 and
prints a unified diff when the installed file differs or is missing; exit 0 when equal.

### Request (additive to the T5.3 seam)

```
POST /api/v1/control/actions        Content-Type: application/json   X-Control-Room: 1
{"workflow_id": "<logical id>", "action": "pause|resume|run_now|retry|stop", "reason": "<string>",
 "stage": "preview"|"apply"|null,     # resume only; null → refused preview_required
 "preview_token": str|null,           # resume apply
 "trigger": "<unit>"|null,            # run_now/retry/stop on a multi-trigger workflow
 "confirm": bool,                     # stop
 "retry_of": "<run_id>"|null}         # retry: the failed run being retried (audit link only)
```

Broker wire protocol (unix socket or `--serve` stdin): one JSON object + `\n`, ≤ 8 KiB, then the
client half-closes; the broker answers one JSON object + `\n` and exits.
Request to the broker = the HTTP body plus `"v": 1` and
`"actor": {"kind": "screen", "remote": "<peer ip>", "local": "<server ip>", "label": "dave via control-room from <peer ip>"}`.
Response: `{"v": 1, "result": "applied|refused|failed|previewed", "http_status": int,
"refusal": {"code", "message", "choices": [...]|null}|null, "receipt": {…}, "preview": {…}|null}`.

### Actions → systemctl (system scope shown; user scope prefixes `--user --machine=dave@.host`)

| action | precondition (refusal code) | commands (per trigger unless noted) | after / extras |
|---|---|---|---|
| `pause` | state ∈ {active, running} else `state_conflict` ("already paused") | `disable --now <unit>.timer` | service untouched; `next_scheduled_run: null` |
| `resume` `stage=preview` | state == paused else `state_conflict` | read-only: `show` timer+service, stamp mtime, `systemd-analyze calendar --iterations=2 "<spec>"` (env `TZ=UTC`) | `result: previewed`; `preview.implication`, `preview.preview_token` (= the preview receipt id) |
| `resume` `stage=apply` | paused; token names a `previewed` receipt for this workflow+action, `completed_at ≤ 10 min` old, whose `before.fingerprint` equals the current one, else `preview_required` / `preview_stale` | `enable --now <unit>.timer` | `next_scheduled_run` = min `NextElapseUSecRealtime`; `catch_up_fired: bool` (service went active during apply) |
| `run_now` | no service running (`state_conflict`); multi-trigger without `trigger` → `trigger_required` with `choices`; `trigger` not one of the workflow's units → `bad_request` | `start --no-block <unit>.service`, then `show <unit>.service --property=InvocationID,ActiveState,ExecMainStartTimestamp` | `run_id` = InvocationID; `links.run = "/runs/<run_id>"`; allowed while paused (that is the one-hand-started-run path) |
| `retry` | allowlist `retry: true` else `not_idempotent`; then as `run_now` | as `run_now` | `links.retry_of` from the request |
| `stop` | `confirm: true` else `confirmation_required`; non-empty `reason` else `reason_required`; a service running (`state_conflict` otherwise); multi-trigger with two running and no `trigger` → `trigger_required` | `stop --no-block <unit>.service`, then poll `show … ActiveState` every 1 s ≤ 15 s | `after` re-read; if still `deactivating` after 15 s the receipt notes it (`TimeoutStopSec` applies) |

Common refusals (before any mutating call): `bad_request` (shape: non-JSON, unknown keys, wrong
types, oversize, `workflow_id`/`trigger` outside the grammar), `unknown_action`,
`unknown_workflow` (not in the allowlist and not matching any excluded unit), `not_allowlisted`
(matches an `excluded` entry — the message carries its reason), `unit_not_found` (allowlisted but
`systemctl show` says `LoadState=not-found` — a stale install), `masked` (`UnitFileState` ∈ {masked,
masked-runtime}), `peer_denied` (§ Peer gate), `allowlist_invalid` (file missing, unparsable, or an
entry outside the grammar → every request refused until re-rendered), `locked` (another broker
instance holds the lock > 30 s). Every `systemctl` call runs with `--no-pager`, a 20 s timeout,
`env={"PATH": …, "LC_ALL": "C", "TZ": "UTC"}`; a non-zero exit **after** validation → `result:
failed`, stderr captured, state re-read. Mutating actions serialise on `flock` of
`$CONTROL_BROKER_LOCK`.

### Reconciliation and the state rule (broker-side, root truth)

`reconcile(workflow) -> {"state", "fingerprint", "units": [...]}` reads, per trigger,
`show <unit>.timer --property=ActiveState,SubState,UnitFileState,LoadState,LastTriggerUSec,NextElapseUSecRealtime,Persistent,TimersCalendar --timestamp=utc`
and `show <unit>.service --property=ActiveState,SubState,LoadState,Result,InvocationID,ExecMainStartTimestamp,ExecMainExitTimestamp --timestamp=utc`.
`state`: any service `active|activating` with `SubState ∈ {running,start}` → `running`; else all
timers `inactive` **or** `UnitFileState ∈ {disabled, …}` → `paused`; else any timer `active` →
`active`; else `unknown`. (T5.3's `control.state` rule, restated so the receipt and the screen agree;
the screen's `control` object is still T5.3's derivation.) `fingerprint` = sha256 over the sorted
`(unit, ActiveState, SubState, UnitFileState)` tuples. Timestamps parsed with
`"%a %Y-%m-%d %H:%M:%S %Z"` → ISO `Z`; unparsable → `null` with the raw string kept.

### Resume preview — the `Persistent=true` implication

For each timer trigger: `persistent` from `Persistent=yes|no`; `stamp` = mtime of
`<stamp dir>/stamp-<unit>.timer` (system: `/var/lib/systemd/timers`; user:
`$CONTROL_BROKER_USER_STAMP_DIR`) or `null`; every `OnCalendar=<spec>` parsed out of
`TimersCalendar`; `next1, next2` = the two `Next elapse:` / `Iteration #2:` lines of
`systemd-analyze calendar --iterations=2 <spec>` under `TZ=UTC`; `previous = next1 − (next2 − next1)`
(exact for regular specs, **approximate** for irregular ones such as `Mon *-*-08..14 09:37` — the
message says `approximate`). `catch_up = persistent and stamp is not None and stamp < previous`;
`null` when the spec cannot be evaluated (message names the error). Message forms:

- `Persistent=true — <unit>.timer last fired <stamp> and missed <previous>: "enable --now" starts <unit>.service immediately (catch-up). Next scheduled elapse after that: <next1>.`
- `Persistent=true, no missed elapse (last <stamp>, previous <previous>): next fire <next1>.`
- `Persistent=false — no catch-up; next fire <next1>.`
- `Catch-up unknown: <error>. Assume it may fire immediately.`

`preview.implication = {"persistent", "catchUp": bool|null, "lastTriggerAt", "missedElapseAt",
"nextElapseAt", "approximate": bool, "message", "units": [...]}` (one per timer, plus a combined
`message` joined with ` · `). `actions.js` shows the combined message in `confirm()` before apply.

### Audit receipt — `/var/lib/control-room/receipts/<workflow_id>/<receipt_id>.json`

`receipt_id = "<%Y%m%dT%H%M%SZ>-<action>-<6 hex>"`. Unknown/invalid ids write under
`_refused/` with the offending value stored as a ≤ 200-char string field, never as a path segment.
Written atomically (tmp + fsync + rename, mode 0644, the parent dir 0755). Shape (schema 1; the
broker's `validate_receipt()` enforces required keys and vocabularies; the screen-side reader
skips files that fail it):

```
{"schema": 1, "receipt_id", "workflow_id": str|null, "requested_workflow_id": str,
 "action", "stage": "preview"|"apply"|null, "trigger": str|null,
 "actor": {"kind": "screen"|"cli", "label", "remote": str|null, "local": str|null,
           "user": str|null, "peer": {"uid", "gid", "pid"}|null},
 "reason": str|null, "confirm": bool,
 "requested_at": iso, "completed_at": iso,
 "before": {"state", "fingerprint", "units": [...]}|null,       # null only for shape refusals that name no workflow
 "after":  {…same…}|null,                                        # null when nothing was attempted
 "result": "applied"|"refused"|"failed"|"previewed",
 "refusal": {"code", "message", "choices": [...]|null}|null,
 "commands": [{"argv": [...], "exit": int|null, "stderr": str, "seconds": float}],   # every call, reads included
 "run_id": str|null, "next_scheduled_run": iso|null, "catch_up_fired": bool|null,
 "implication": {…}|null,
 "links": {"workflow": "/workflows/<id>", "run": "/runs/<run_id>"|null,
           "preview_receipt": "<receipt_id>"|null, "retry_of": "<run_id>"|null}}
```

### Screen side — `bin/control_room_control.py`

- `peer_allowed(remote, local) -> (bool, reason)`: `local` loopback → allowed (a loopback-bound
  screen is a development instance by construction — T5.3's wrapper never binds one); otherwise
  require `remote` present, not loopback, and `remote != local`. The broker applies the same
  function to `actor.remote/local` (it is 8 lines; duplicated deliberately so the root side does
  not import the dave side).
- `handle_post(handler, control, model)`: header + JSON + shape checks (T5.3's stub rules, kept:
  missing `X-Control-Room` → 400, non-JSON → 400, unknown `action` → 400, `workflow_id` not a
  string → 400); `control is None` → the unchanged **501 stub** (`{"status":"not_implemented", …}`,
  unknown id → 404) so T5.3's `::control-room-control-stub-501` keeps passing; otherwise forward
  to the broker with the actor, then respond `{"receipt", "control": <fresh model.workflow_detail(id)[0]["control"]>, "preview"?: …, "error"?: …}`.
- HTTP map: `applied|previewed` → 200; `refused` → 404 `unknown_workflow`; 403 `peer_denied`,
  `not_allowlisted`; 400 every other refusal code (the seam's `403|400`; the stub's 404 for unknown
  ids is kept); `failed` → 500 `{"error", "receipt", "control"}`; socket absent / refused / broken
  → 502 `{"error": "control broker unreachable: …", "receipt": null}`; broker timeout (60 s) → 504.
- `ControlReceipts(root).last_action(logical_id) -> dict|None`: newest receipt by `completed_at`
  with `result != "previewed"`, mapped to the seam shape `{"action", "actor": <label>, "reason",
  "at": completed_at, "result": "applied|refused|failed", "before": before.state|null, "after":
  after.state|null, "receiptId", "links": {"receipt": <path>, "run", "previewReceipt", "workflow"}}`;
  root missing/unreadable or no receipts → `None`; malformed → skipped with one stderr line.
- `retry_policy(repo) -> Callable[[item], tuple[bool, str|None]]`: contract unavailable → `(False,
  "contract unavailable")`; no `Retry` row → `(False, "contract declares no idempotent operation")`;
  declared idempotent and `item["lastRun"]["outcome"] == "failed"` and `control.state != "running"`
  → `(True, None)`; declared but last run not failed → `(False, "retry needs a failed last run (last
  run: <outcome>|none)")`.
- `ControlRoomControl.from_env()`: `CONTROL_ROOM_BROKER_SOCKET` (default
  `/run/control-room-broker.sock`), `CONTROL_ROOM_CONTROL_RECEIPTS` (default
  `/var/lib/control-room/receipts`); `BrokerClient(socket_path, timeout=60).call(request)`.

### `actions.js` extension (keep T5.3's poster, prompt rules and the re-fetch)

- `resume`: POST `stage:"preview"` → write the implication message + JSON into `#control-result`
  → `confirm(message + "\n\nApply resume?")` → POST `stage:"apply"` with `preview_token` and the
  reason → render → re-fetch. Cancel = nothing applied (the preview receipt stays, as designed).
- `stop`: reason `prompt` (required, T5.3) then `confirm("Stop the current run of <id>
  (<unit>)? This sends SIGTERM; the run's receipt, if the executor writes one, records the
  interruption.")` → POST `confirm:true`.
- `run_now` / `retry`: POST; on 400 `trigger_required` → `prompt` listing `refusal.choices` →
  re-POST with `trigger`. `retry` sends `retry_of` = the page's `lastRun.id` (from the last
  `GET /api/v1/workflows/{id}` the script already holds). A `run_id` in the response renders as
  the first line: `run <id> started — its receipt appears under Runs when the executor writes it`.
- First line of `#control-result` is always a one-line summary (`applied · resume · paused → active
  · next 2026-09-20T09:00:00Z` / `refused · state_conflict · already paused`); the JSON follows.

### Retry declaration (contract Identity row)

`design/contract-schema.md` § `## Identity` gains: an optional row whose first cell is `Retry`;
value `idempotent: <reason>` declares that a second start on the same day either skips or produces
the same artifact, so **Retry** may re-run a failed run; any other value or no row = not idempotent.
Parser (`contract_retry_declaration(text) -> (bool, str|None)` in `control_room_control.py`, and
the same 6 lines in `control_broker_allowlist.py`): first cell `Retry` (case-insensitive, markdown
stripped); value's first word, lowercased and stripped of `*`/backticks, is exactly `idempotent`.
Declared in this brief on the five contracts whose own text already asserts it (verify the quoted
line exists before adding the row; skip any contract where it does not):

| contract | row |
|---|---|
| `knowledge-digest.md` | `\| Retry \| idempotent: STEP 0 skips when today's file exists (":30"), so a second start writes nothing or the same artifact \|` |
| `standing-research.md` | `\| Retry \| idempotent: STEP 0 skips when today's file exists (":44") \|` |
| `weekly-pre-assembly.md` | `\| Retry \| idempotent: STEP 0 stops when today's file exists (":52") \|` |
| `m1-signal-scan.md` | `\| Retry \| idempotent: same-day skip when today's scan exists (":37") \|` |
| `scorecard.md` | `\| Retry \| idempotent: deterministic over cost.log, unchanged week is not rewritten (":9") \|` |

## Files to modify

- `bin/control_room_api.py` — **three edit sites, nothing else** (the third is a seam deviation,
  § Seam deviations): (1) the `POST /api/v1/control/actions` branch → `control_room_control.handle_post(self, getattr(type(self), "control", None), self.model)`;
  (2) `main()`: `control = control_room_control.ControlRoomControl.from_env()`, pass
  `control_reader=control.receipts.last_action` and `retry_policy=control.retry_policy` into
  `ControlRoomReadModel(...)`, then `server.RequestHandlerClass.control = control`; (3) a new
  `retry_policy: Callable[[dict], tuple[bool, str | None]] | None = None` constructor kwarg,
  consulted in `workflows()` right after `item["control"]` is assembled: replace the `retry`
  action's `enabled`/`reason` with its return value (4 lines). `import control_room_control` next
  to the other sibling imports.
- `bin/control_room_ui/actions.js` — § actions.js extension (extend; keep the re-fetch and the
  T5.3 prompt rules).
- `bin/check_deploy_drift.sh` — (a) `:451-452`: the unit globs gain `-o -name '*.socket'` (both
  sides; header comment gains one dated line: a socket unit deployed but never compared is the same
  gap W17 closed for staging); (b) new section **"root-installed control broker"** after the
  buzz-team section and before the summary, inside `SCOPE=all` only: `BROKER_LIB="${DRIFT_BROKER_LIB:-/usr/local/lib/control-room}"`,
  `BROKER_ETC="${DRIFT_BROKER_ETC:-/etc/control-room}"`; when `$SRC_BIN/control_broker.py` is
  absent → one `info` line and nothing else (a fixture with no broker source has nothing to
  compare — the predicate is on the source, which this repo answers for); else: missing
  `$BROKER_LIB/control_broker.py` → `report broker "source-only: control_broker.py is not installed at $BROKER_LIB (sudo install …)"`;
  present and `cmp` differs → `report broker "content differs: control_broker.py (root copy is stale — re-run the install line)"`;
  any other file under `$BROKER_LIB` → `report broker "installed-only: $f has no source"`; when
  `$SRC_BIN/control_broker_allowlist.py` exists: `rendered=$(python3 "$SRC_BIN/control_broker_allowlist.py" render --repo "$SRC_ROOT")`
  vs `$BROKER_ETC/allowlist.json` → `source-only` / `content differs: allowlist.json (re-render and install)`;
  render failure → `report broker "allowlist render failed: <stderr>"`. Different regions from T5.3's
  `:351-352` edit.
- `tests/test_deploy_drift.sh` — `fixture()` exports `DRIFT_BROKER_LIB="$root/broker_lib"` and
  `DRIFT_BROKER_ETC="$root/broker_etc"` (dirs created, empty; existing scenarios have no
  `src_bin/control_broker.py`, so the section stays inert and every `clean()` still holds); new
  group **17. root-installed control broker + socket units** (§ Test plan).
- `design/fleet-suites.toml` — two `[[suite]]` entries (owner `fleet`, one-sentence
  `why_no_workflow`) naming the anchored ids in § Test plan.
- `design/contract-schema.md` — the `Retry` row under `### ## Identity` (§ Retry declaration).
- `design/contracts/{knowledge-digest,standing-research,weekly-pre-assembly,m1-signal-scan,scorecard}.md`
  — one `Retry` row each (§ Retry declaration); no other change. T6.1 edits the side-effect bullets of
  `knowledge-digest`, `standing-research` and `m1-signal-scan` (:88/:108/:99) — other lines; whichever
  lands second rebases, keeping both.
- `docs/runbook.md` — new `## Control Room controls (T5.3a)` directly after T5.3's `## Control Room
  (T5.3)`: the trust boundary diagram, the action table, receipt path, the land sequence, the
  re-render rule ("a manifest, timer or contract change → `python3 bin/control_broker_allowlist.py
  check` red until re-installed"), the CLI form, and "the fleet stays off: resume is Dave's
  moment, DoD item 7".
- `CLAUDE.md` (repo) § Where things live — one bullet: the broker (socket, root copy, allowlist,
  receipts path, "never `--no-verify` equivalent: never widen the socket group or exec the source copy").

## Files to create

Source (stdlib only, `from __future__ import annotations`, Python 3.11+):

- `bin/control_broker.py` — **self-contained** (no sibling import). Public: `main(argv)`, `serve(stdin, stdout, cfg)`,
  `handle(request, cfg, clock) -> response`, `validate_request`, `Allowlist.load(path)`,
  `reconcile`, `plan(action, workflow, request) -> list[argv]`, `preview_implication`,
  `write_receipt`, `validate_receipt`, `peer_allowed`, `parse_systemd_timestamp`,
  `UNIT_RE`, `ACTIONS`, `REFUSAL_CODES`, `PREVIEW_TTL_SECONDS = 600`, `STOP_POLL_SECONDS = 15`.
  Modes: `--serve` (one request on stdin → one response on stdout; stdin a socket → actor kind
  `screen` + `SO_PEERCRED`; a pipe → kind `cli`, `user` = `SUDO_USER` or the login name) and
  `act <action> <workflow_id> [--reason R] [--stage S] [--preview-token T] [--trigger U] [--confirm] [--retry-of ID]`
  (builds the request, prints the response JSON, exit 0 applied/previewed, 1 refused/failed).
  Options with env defaults: `--allowlist` (`CONTROL_BROKER_ALLOWLIST`), `--receipts`
  (`CONTROL_BROKER_RECEIPTS`), `--peer-uids` (`CONTROL_BROKER_PEER_UIDS`, comma list),
  `--user-manager` (`CONTROL_BROKER_USER_MANAGER`, default `dave@.host`), `--system-stamp-dir`
  (default `/var/lib/systemd/timers`), `--user-stamp-dir` (`CONTROL_BROKER_USER_STAMP_DIR`),
  `--lock` (`CONTROL_BROKER_LOCK`), `--now <iso>` (tests only; also seeds the receipt id).
- `bin/control_broker_allowlist.py` — § Allowlist. Public: `render(repo) -> dict`, `dumps(data) -> str`,
  `contract_retry_declaration(text)`, `main(argv)` (`render` / `check`).
- `bin/control_room_control.py` — § Screen side. Public: `handle_post`, `stub_response`,
  `validate_shape`, `peer_allowed`, `BrokerClient`, `BrokerUnavailable`, `ControlReceipts`,
  `retry_policy`, `contract_retry_declaration`, `ControlRoomControl`, `HTTP_STATUS_BY_CODE`.
- `systemd/control-room-broker.socket` — exact content:

```
# Praetorium Control Room broker socket — T5.3a (2026-09-14). Root-owned and group-restricted:
# only a process carrying the control-room supplementary group can connect — that is
# control-room.service, granted through systemd/control-room.service.d/broker.conf — and every
# other uid-1000 process on this box (every agent) is refused at connect() by the kernel.
# Accept=yes: one request per connection, one broker process per request, no daemon state.
# Land: sudo groupadd --system control-room
#       sudo cp systemd/control-room-broker.socket systemd/control-room-broker@.service /etc/systemd/system/
#       sudo systemctl daemon-reload && sudo systemctl enable --now control-room-broker.socket
#       (a socket, not a workflow timer — the twelve stay untouched)
[Unit]
Description=Praetorium Control Room broker socket (allowlisted workflow controls) — T5.3a

[Socket]
ListenStream=/run/control-room-broker.sock
SocketUser=root
SocketGroup=control-room
SocketMode=0660
Accept=yes
MaxConnections=4
RemoveOnStop=yes

[Install]
WantedBy=sockets.target
```

- `systemd/control-room-broker@.service` — exact content:

```
# Praetorium Control Room broker — T5.3a (2026-09-14). One instance per connection, as root,
# executing the ROOT-OWNED installed copy — never the dave-writable source under /home: a root
# unit that execs a file its clients can edit is a privilege escalation, not a broker.
# bin/check_deploy_drift.sh compares the copy against bin/control_broker.py and the rendered
# allowlist against /etc/control-room/allowlist.json, so neither can rot silently.
# Land: sudo install -D -o root -g root -m 0755 bin/control_broker.py /usr/local/lib/control-room/control_broker.py
#       python3 bin/control_broker_allowlist.py render > /tmp/allowlist.json
#       sudo install -D -o root -g root -m 0644 /tmp/allowlist.json /etc/control-room/allowlist.json
# Re-render after any manifest, timer or contract change (the drift check goes red until you do).
[Unit]
Description=Praetorium Control Room broker (per-connection, root, allowlisted) — T5.3a
CollectMode=inactive-or-failed

[Service]
Type=oneshot
ExecStart=/usr/bin/python3 /usr/local/lib/control-room/control_broker.py --serve
StandardInput=socket
StandardOutput=socket
StandardError=journal
Environment=CONTROL_BROKER_ALLOWLIST=/etc/control-room/allowlist.json
Environment=CONTROL_BROKER_RECEIPTS=/var/lib/control-room/receipts
Environment=CONTROL_BROKER_PEER_UIDS=1000
Environment=CONTROL_BROKER_USER_MANAGER=dave@.host
Environment=CONTROL_BROKER_USER_STAMP_DIR=/home/dave/.local/share/systemd/timers
Environment=CONTROL_BROKER_LOCK=/run/control-room/lock
Environment=PYTHONDONTWRITEBYTECODE=1
StateDirectory=control-room
RuntimeDirectory=control-room
RuntimeDirectoryPreserve=yes
TimeoutStartSec=90
ProtectSystem=strict
ProtectHome=read-only
PrivateTmp=yes
NoNewPrivileges=yes
```

- `systemd/control-room.service.d/broker.conf` — exact content (a drop-in; T5.3's unit file is
  not edited):

```
# T5.3a (2026-09-14): the screen joins the control-room group so it — and no other dave
# process — can connect to the broker socket, and learns where the socket and the audit
# receipts are. Land: sudo mkdir -p /etc/systemd/system/control-room.service.d
#   && sudo cp systemd/control-room.service.d/broker.conf /etc/systemd/system/control-room.service.d/
#   && sudo systemctl daemon-reload && sudo systemctl restart control-room.service
[Service]
SupplementaryGroups=control-room
Environment=CONTROL_ROOM_BROKER_SOCKET=/run/control-room-broker.sock
Environment=CONTROL_ROOM_CONTROL_RECEIPTS=/var/lib/control-room/receipts
```

- `tests/acceptance/control_room_controls.sh` — the hand-run acceptance (§ Hand-run acceptance);
  bash, `set -uo pipefail`, shellcheck-clean, **not** under `tests/*.sh` so the gate never runs it;
  `tests/test_control_room_control.sh` lints it (`bash -n` + `shellcheck -S error` when present).

Fixtures (`tests/fixtures/control-broker/`, all committed; the suite copies `bin/` into a temp dir
and writes state beside it, exactly as `test_contract_exec.py` does):

- `bin/systemctl` — executable **Python** shim (`#!/usr/bin/env python3`; `bin/verify.sh` lints
  `bin/` and `tests/*.sh` only, so a python fixture is outside shellcheck). Env: `FAKE_SYSTEMCTL_STATE`
  (JSON: unit → properties), `FAKE_SYSTEMCTL_LOG` (one line per call, the **full** argv
  space-joined, including any `--user --machine=…` prefix), `FAKE_SYSTEMCTL_FAIL` (unit name: any
  mutating verb on it exits 1, stderr `Failed to <verb> <unit>: fake failure`). Accepts and strips
  `--user`, `--machine=X`, `--no-pager`, `--timestamp=utc`, `--no-block`. Verbs: `show <unit>
  --property=A,B` (repeatable / `-p`; prints `K=V` for each requested key, empty when unset; an
  unknown unit prints `LoadState=not-found` + `ActiveState=inactive`, exit 0, like real systemctl);
  `enable --now <t>.timer` → `active/waiting/enabled`, `NextElapseUSecRealtime` = the unit's
  `_next_on_enable` or `Sun 2026-09-20 09:00:00 UTC`; if the unit carries `_catch_up: true` its
  service also becomes `active/running` with a fresh `InvocationID` (simulated Persistent catch-up);
  `disable --now <t>.timer` → `inactive/dead/disabled`, empty `NextElapseUSecRealtime`; `start
  <s>.service` → `active/running`, `InvocationID` = 32 hex from a counter, `ExecMainStartTimestamp`
  = now UTC; `stop <s>.service` → `inactive/dead`, `Result=success`; anything else → stderr
  `fake systemctl: unsupported call`, exit 2.
- `bin/systemd-analyze` — Python shim: `calendar --iterations=2 <spec>` prints the real layout
  (`Original form`, `Normalized form`, `    Next elapse: <%a %Y-%m-%d %H:%M:%S UTC>`, `       From now`,
  `   Iteration #2: …`) from `FAKE_CALENDAR` (JSON path: spec → two ISO strings); unknown spec → exit 1,
  stderr `Failed to parse calendar specification`.
- `state.json` — the initial fake state: `knowledge-digest.timer` paused (`inactive/dead/disabled`,
  `Persistent=yes`, `TimersCalendar={ OnCalendar=Sun 09:00 ; next_elapse=n/a }`, `_catch_up: true`),
  `knowledge-digest.service` inactive; `scorecard.timer` paused, `Persistent=yes`,
  `TimersCalendar={ OnCalendar=Mon 07:00 ; … }`; `augustus-content.timer` + `content-change-dispatch.timer`
  active/enabled with `NextElapseUSecRealtime`, both services inactive; `buzz-pr-watch.timer`
  active/enabled, `Persistent=no`; `local-tier-eval.timer` active + `local-tier-eval.service`
  `active/running` `InvocationID=…` (the pause-during-run case); `masked-job.timer`
  `UnitFileState=masked`.
- `calendar.json` — `"Sun 09:00": ["2026-09-20T09:00:00Z", "2026-09-27T09:00:00Z"]`,
  `"Mon 07:00": [...]`, `"daily 09:23"` for buzz-pr-watch, etc.
- `allowlist.json` — synthetic, six entries: `knowledge-digest` (system, retry false),
  `scorecard` (system, retry true), `augustus-content` (two system triggers), `buzz-pr-watch`
  (user), `local-tier-eval` (system), `masked-job` (system); `excluded`: `buzz-agent@marcus` (kind =
  service), `nekovri-subsidy-kickoff` (status = spent). Deliberately **not** the rendered real one,
  so the broker suite does not churn with the manifests; the render is tested separately.
- `allowlist-bad.json` — one entry with `"unit": "x; rm -rf /"` (grammar violation → `allowlist_invalid`).
- `receipts/` — three hand-written receipts for `knowledge-digest` (previewed, applied, refused) and
  one malformed file, for the screen-side reader test.
- `fake_broker_socket.py` — helper (not a suite): `serve(socket_path, env, argv) ` runs a
  `socketserver.ThreadingUnixStreamServer` whose handler spawns
  `python3 bin/control_broker.py --serve …` with the connection as stdin/stdout — the real broker
  code on a real unix socket, unprivileged, against the shim. Used by
  `tests/test_control_room_control.py` and by the loopback smoke.

Tests (one `.sh` wrapper per `.py`, the wrapper is `python3 tests/<name>.py` with the fixture header
comment, exactly `tests/test_contract_exec.sh`'s shape; anchors live in the `.py`):

- `tests/test_control_broker.{sh,py}`
- `tests/test_control_room_control.{sh,py}` (the `.sh` also lints `tests/acceptance/control_room_controls.sh`)

## Test plan (TDD: each red first; ids are the `(::id)` anchors and the fleet-suites `asserts`)

`tests/test_control_broker.py` — every case runs `bin/control_broker.py --serve` (or `act`) in a
subprocess with `PATH=<tmp fake bin>:$PATH`, `FAKE_SYSTEMCTL_STATE`, `FAKE_SYSTEMCTL_LOG`,
`FAKE_CALENDAR`, `--allowlist`, `--receipts <tmp>`, `--system-stamp-dir <tmp>/stamps`,
`--user-stamp-dir <tmp>/ustamps`, `--lock <tmp>/lock`, `--now 2026-09-14T08:00:00Z`;
`os.utime` sets stamp mtimes.

- (::broker-allowlist-refuses) unknown id → `refused` `unknown_workflow`, HTTP 404 in the response,
  receipt under `_refused/`, **empty call log**; `action: "rm -rf"` → `unknown_action`;
  `workflow_id: "../etc"` → `bad_request`, no path outside `<tmp>/receipts` is created; an extra key
  → `bad_request`; a 9 KiB body → `bad_request`; `buzz-agent@marcus` → `not_allowlisted` with the
  excluded reason in the message; `raw-ingest` (real workflow, not in the synthetic allowlist) →
  `unknown_workflow`; `allowlist-bad.json` → every request `allowlist_invalid`, receipted;
  `masked-job` → `masked`; a unit the shim reports `LoadState=not-found` → `unit_not_found`.
- (::broker-pause-keeps-current-run) `pause local-tier-eval` (timer active, service running):
  log is exactly the `show` reads plus `disable --now local-tier-eval.timer`; no `stop`;
  `after.units` shows the timer `inactive/disabled` and the service `active/running`;
  `after.state == "running"`; `result applied`; `next_scheduled_run is None`. `pause
  knowledge-digest` (already paused) → `state_conflict`, no mutating call.
- (::broker-resume-preview-before-apply) `resume knowledge-digest` with no stage / `stage: "apply"`
  without token → `preview_required`, no mutating call; `stage: "preview"` with the stamp at
  2026-09-06 and calendar next `2026-09-20`/`09-27` → `previewed`, `implication.catchUp is True`,
  `missedElapseAt == "2026-09-13T09:00:00Z"`, message names `knowledge-digest.service` and
  `immediately`, `preview.preview_token` equals the written receipt's id; `stage: "apply"` with that
  token → `enable --now knowledge-digest.timer`, `applied`, `after.state == "running"` (the shim's
  simulated catch-up), `catch_up_fired is True`, `next_scheduled_run == "2026-09-20T09:00:00Z"`,
  `links.preview_receipt` set; the same token again (state changed) → `preview_stale`; a token
  issued at `--now` 11 min earlier → `preview_stale`; `scorecard` with stamp **after** the previous
  elapse → `catchUp False`; `buzz-pr-watch` (`Persistent=no`) → `catchUp False`, message says
  `no catch-up`; an unmapped calendar spec → `catchUp None`, message `unknown`, still `previewed`.
- (::broker-run-now-returns-run-id) `run_now knowledge-digest` (paused) → `start --no-block
  knowledge-digest.service` then `show … InvocationID`; `run_id` == the shim's InvocationID;
  `links.run == "/runs/<id>"`; `local-tier-eval` (running) → `state_conflict`; `augustus-content`
  without `trigger` → `trigger_required` with `choices == ["augustus-content", "content-change-dispatch"]`
  and no mutating call; with `trigger: "content-change-dispatch"` → that service only; `trigger:
  "sshd"` → `bad_request`.
- (::broker-retry-idempotent-only) `retry knowledge-digest` → `not_idempotent`; `retry scorecard`
  with `retry_of: "run-0908"` → `applied`, `links.retry_of == "run-0908"`, same argv as run_now.
- (::broker-stop-needs-confirm-and-reason) `stop local-tier-eval` without `confirm` →
  `confirmation_required`; `confirm: true` + `reason: "  "` → `reason_required`; both →
  `stop --no-block local-tier-eval.service`, polled `show`, `after.units` service `inactive`,
  `after.state == "active"` (its timer is still active), `applied`; `stop knowledge-digest` (idle)
  → `state_conflict`.
- (::broker-scope-addressing) every log line for `buzz-pr-watch` starts with
  `systemctl --user --machine=dave@.host`; every line for `knowledge-digest` starts with
  `systemctl show|disable|enable|start|stop` (no `--user`, no `--machine`); the user preview reads
  `<tmp>/ustamps/stamp-buzz-pr-watch.timer` and the system one `<tmp>/stamps/stamp-knowledge-digest.timer`
  (assert via `implication.units[].stampPath`).
- (::broker-every-outcome-receipted) one receipt per request across applied / refused / failed /
  previewed, each with every key of § Audit receipt, `validate_receipt(data) == []`, `commands[]`
  listing every call (reads included) with `exit`; `FAKE_SYSTEMCTL_FAIL=augustus-content.timer` +
  `pause augustus-content` → `result failed`, stderr captured in `commands[]`, `after` re-read,
  HTTP 500; no `*.tmp` left in the receipts tree; receipt files are mode 0644.
- (::broker-peer-gate) stdin = one end of `socket.socketpair()` (screen mode): `actor.remote ==
  actor.local` → `peer_denied`; `remote: "127.0.0.1"` with `local: "100.86.82.16"` → `peer_denied`;
  `remote: "100.64.0.9"` → allowed (proceeds to the normal outcome); `remote` missing →
  `peer_denied`; `CONTROL_BROKER_PEER_UIDS=99999` → `peer_denied` before any read; `local:
  "127.0.0.1"` (dev instance) → allowed; stdin = a pipe → `actor.kind == "cli"`, `actor.user ==
  $SUDO_USER` when set; receipts record `actor.peer.uid == os.getuid()` in screen mode.
- (::broker-concurrency-lock) two `pause` requests started concurrently against the same lock:
  exactly one `applied`, the other `state_conflict` (serialised, re-reconciled), never two
  `disable` calls.
- (::broker-allowlist-render) `control_broker_allowlist.render(ROOT)` over the real checkout:
  every standing `kind = "timer"` manifest entry appears exactly once under its logical id;
  `augustus-content` has two triggers; `buzz-pr-watch` scope `user`; every `buzz-agent@*` under
  `excluded` with reason `kind = service`, both `nekovri-*` with `status = spent`; `retry` true for
  exactly the five contracts in § Retry declaration and false with a reason elsewhere; `dumps()`
  is byte-identical across two calls; a synthetic manifest dir with a timer entry lacking
  `systemd/<unit>.timer` → excluded `no timer/service file`; `check` exits 1 with a diff against a
  differing file and 0 against `dumps(render(ROOT))`; the numbers (entries, exclusions) are
  computed from the manifests in the test, not literals.

`tests/test_control_room_control.py` — builds `ControlRoomReadModel(SourcePaths(repo=ROOT,
runtime=<tmp>, receipts=<tmp>/receipts), systemd=StateFileSystemd(<tmp>/state.json),
clock=lambda: NOW, calendar_runner=<T5.3's FakeCalendar>, control_reader=…, retry_policy=…)` where
`StateFileSystemd.show()` reads the **same** `state.json` the broker shim mutates (one source of
truth for "reconciled from systemd"); the HTTP server binds `127.0.0.1:0`; the broker end is
`fake_broker_socket.serve()` in a thread, `CONTROL_BROKER_PEER_UIDS=<os.getuid()>`.

- (::control-post-forwards-and-reconciles) `POST resume stage:preview` on `knowledge-digest` →
  200 with `receipt.result == "previewed"` and `preview.preview_token`; then `stage:apply` with the
  token → 200, `receipt.result == "applied"`, and the response's `control.state` is `running`
  (shim catch-up) while the page's previous `control.state` was `paused` — state came from the
  re-read, not the click; the broker saw `actor.kind == "screen"`, `actor.local == "127.0.0.1"`.
- (::control-refusal-status-map) with a `FakeBroker` callable substituted for `BrokerClient`,
  each refusal code maps as § Screen side (`unknown_workflow` 404, `peer_denied`/`not_allowlisted`
  403, `state_conflict` 400, `failed` 500) and every response carries `receipt`; a socket path that
  does not exist → 502 `{"error": "control broker unreachable: …", "receipt": null}`; a broker that
  never answers → 504 (timeout injected at 1 s); T5.3's checks kept: missing header → 400,
  non-JSON → 400, `POST /api/v1/workflows/x` → 405, `HEAD /api/v1/control/actions` → 405; with
  **no** `control` bound the 501 stub still answers `{"status": "not_implemented", …}` and unknown
  id → 404.
- (::control-last-action-from-receipts) the three fixture receipts → `control.lastAction` is the
  newest with `result != "previewed"`, keys exactly `{action, actor, reason, at, result, before,
  after, receiptId, links}`, `actor` a string; missing root → `None` (the page renders `Unknown`);
  the malformed file is skipped and one stderr line names it.
- (::control-retry-policy) a contract text with `| Retry | idempotent: … |` + `lastRun.outcome ==
  "failed"` → `retry` action `enabled True`; same with outcome `artifact` → `False`, reason names
  `artifact`; no `Retry` row → `False`, reason `contract declares no idempotent operation`;
  `contract None` → `False`; `control.state == "running"` → `False`; the four other actions'
  `enabled` values are untouched (T5.3's derivation).
- (::control-peer-rule) `peer_allowed`: `("100.64.0.9", "100.86.82.16")` allowed; `("100.86.82.16",
  "100.86.82.16")` refused; `("127.0.0.1", "100.86.82.16")` refused; `(None, "100.86.82.16")`
  refused; `("127.0.0.1", "127.0.0.1")` allowed with reason `loopback-bound development instance`;
  the broker's copy gives identical answers for the same table (import both, compare).
- (::control-actions-js-flow) `bin/control_room_ui/actions.js` contains `"stage":"preview"`,
  `preview_token`, `confirm(` on the resume and stop paths, `trigger_required`, `retry_of`, and
  still re-fetches `` `/api/v1/workflows/${` `` after the response (grep-level; no JS runtime).
- (::control-acceptance-script-lints) `bash -n tests/acceptance/control_room_controls.sh`; when
  `shellcheck` is on PATH, `shellcheck -S error` is clean; the script contains no `enable --now`
  and no `stage":"apply"` / `--stage apply` (it must never resume) — asserted by grep.

`tests/test_deploy_drift.sh` group **17. root-installed control broker + socket units** (claimed via
trajan.toml's existing `suite` list, as T5.3's group 2b is): a `src_sys/x.socket` with no `etc/`
counterpart → `DRIFT [system] source-only: x.socket`; present on both sides, equal → clean;
`src_bin/control_broker.py` with no `$DRIFT_BROKER_LIB/control_broker.py` → `DRIFT [broker]
source-only: control_broker.py …`; copy present and equal → clean; copy differs → `content differs:
control_broker.py`; an extra `$DRIFT_BROKER_LIB/other.py` → `installed-only: other.py`;
`src_bin/control_broker_allowlist.py` as a 3-line stub printing `{"schema": 1}` and
`$DRIFT_BROKER_ETC/allowlist.json` absent → `source-only: allowlist.json`, equal → clean, different
→ `content differs: allowlist.json`; no `src_bin/control_broker.py` at all → no `[broker]` finding
(the inert case every earlier group relies on).

Fleet registry: two `[[suite]]` entries in `design/fleet-suites.toml` naming exactly the ids above;
`tests/test_workflow_coverage.py`'s asserts join fails on any id missing from either side.

## Implementation steps (ordered; commit after each numbered group — the auto-sync sweep runs every 15 min)

1. Fixtures first: `tests/fixtures/control-broker/{bin/systemctl,bin/systemd-analyze,state.json,calendar.json,allowlist.json,allowlist-bad.json,receipts/*,fake_broker_socket.py}`.
   Prove the shims by hand: `FAKE_SYSTEMCTL_STATE=… bin/systemctl show knowledge-digest.timer --property=ActiveState,Persistent`.
2. `bin/control_broker.py` + `tests/test_control_broker.{sh,py}` — in this order inside the
   suite: `::broker-allowlist-refuses` → `::broker-every-outcome-receipted` (write_receipt +
   validate_receipt) → `::broker-pause-keeps-current-run` → `::broker-scope-addressing` →
   `::broker-run-now-returns-run-id` → `::broker-retry-idempotent-only` →
   `::broker-stop-needs-confirm-and-reason` → `::broker-resume-preview-before-apply` →
   `::broker-peer-gate` → `::broker-concurrency-lock`. Keep the file under ~600 lines: one
   function per action plan, one `reconcile`, one `preview_implication`, one `write_receipt`.
3. `design/contract-schema.md` Retry row; the five contract rows; `bin/control_broker_allowlist.py`
   + `::broker-allowlist-render`. Run `bash tests/test_contract_schema.sh` and
   `bash tests/test_workflow_coverage.sh` — both must stay green after the contract edits.
4. `bin/control_room_control.py` + `tests/test_control_room_control.{sh,py}`: `::control-peer-rule`,
   `::control-last-action-from-receipts`, `::control-retry-policy`, then the three edit sites in
   `bin/control_room_api.py`, then `::control-refusal-status-map` and
   `::control-post-forwards-and-reconciles`. Run `bash tests/test_control_room_api.sh` and
   `bash tests/test_control_room_views.sh` — T5.3's stub test must still pass unchanged.
5. `bin/control_room_ui/actions.js` extension + `::control-actions-js-flow`.
6. `systemd/control-room-broker.socket`, `systemd/control-room-broker@.service`,
   `systemd/control-room.service.d/broker.conf` (verbatim from § Files to create);
   `systemd-analyze verify systemd/control-room-broker@.service` and `… .socket` (read-only, works
   as dave — expect only "unit not found" style warnings for the group, which does not exist yet).
7. `bin/check_deploy_drift.sh` (`.socket` glob + broker section) and `tests/test_deploy_drift.sh`
   (fixture env + group 17). `bash tests/test_deploy_drift.sh` green.
8. `tests/acceptance/control_room_controls.sh` + `::control-acceptance-script-lints`.
9. `design/fleet-suites.toml` entries; `docs/runbook.md` section; `CLAUDE.md` bullet.
10. Run every touched suite directly (`bash tests/test_control_broker.sh`, `bash
    tests/test_control_room_control.sh`, `bash tests/test_control_room_api.sh`, `bash
    tests/test_control_room_views.sh`, `bash tests/test_deploy_drift.sh`, `bash
    tests/test_contract_schema.sh`, `bash tests/test_workflow_coverage.sh`, `bash
    tests/test_fleet_ownership.sh`) — all green on the branch. Then `bash bin/verify.sh`: the
    **only** red is drift naming `control_broker.py`, `control_broker_allowlist.py`,
    `control_room_control.py`, the modified `control_room_api.py` / `actions.js` /
    `check_deploy_drift.sh` (source ≠ runtime until `bin/deploy`), `control-room-broker.socket`,
    `control-room-broker@.service`, `control-room.service.d/broker.conf` (source-only in `/etc`),
    and the broker section's `source-only: control_broker.py` / `allowlist.json`.
11. Loopback smoke, no unit, no root: in one shell
    `python3 tests/fixtures/control-broker/fake_broker_socket.py --socket /tmp/crb.sock --fixture-env`
    (serves the real broker against the shim); in another
    `CONTROL_ROOM_BROKER_SOCKET=/tmp/crb.sock CONTROL_ROOM_CONTROL_RECEIPTS=/tmp/crb-receipts CONTROL_ROOM_RECEIPT_ROOT=tests/fixtures/control-room/receipts python3 bin/control_room_api.py --host 127.0.0.1 --port 8788`;
    then `curl -s -X POST http://127.0.0.1:8788/api/v1/control/actions -H 'X-Control-Room: 1' -H 'Content-Type: application/json' -d '{"workflow_id":"knowledge-digest","action":"resume","reason":"smoke","stage":"preview"}'`
    → 200 with `preview.implication.message`; `-d '{"workflow_id":"nope","action":"pause"}'` → 404
    with a receipt under `/tmp/crb-receipts/_refused/`. Stop both. Nothing on the box changed.

## Land-time steps (sudo; the branch cannot be green before these — say so in the PR, do not soften the gate)

1. Merge to `main` on the box; `bin/deploy` (ships `bin/`, `systemd/` including the `.socket`, the
   template and the drop-in). `bin/deploy` exits non-zero while the `/etc` units and the root copies
   are missing — expected.
2. `sudo groupadd --system control-room`
3. `sudo install -D -o root -g root -m 0755 bin/control_broker.py /usr/local/lib/control-room/control_broker.py`
4. `python3 bin/control_broker_allowlist.py render > /tmp/allowlist.json && sudo install -D -o root -g root -m 0644 /tmp/allowlist.json /etc/control-room/allowlist.json && python3 bin/control_broker_allowlist.py check`
5. `sudo cp systemd/control-room-broker.socket systemd/control-room-broker@.service /etc/systemd/system/ && sudo mkdir -p /etc/systemd/system/control-room.service.d && sudo cp systemd/control-room.service.d/broker.conf /etc/systemd/system/control-room.service.d/ && sudo systemctl daemon-reload`
6. `sudo systemctl enable --now control-room-broker.socket && sudo systemctl restart control-room.service`
   — the socket is the one unit this brief enables (a control surface, not a workflow); the
   restart is T5.3's screen picking up its drop-in. **No workflow timer is touched.**
7. `ls -l /run/control-room-broker.sock` → `srw-rw---- root control-room`;
   `systemctl show control-room.service -p SupplementaryGroups` → `control-room`;
   `sudo systemctl --user --machine=dave@.host show buzz-pr-watch.timer -p ActiveState` answers (the
   user-manager path works from root on this systemd; if it does not, the fallback is
   `runuser -u dave -- env XDG_RUNTIME_DIR=/run/user/1000 DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus systemctl --user …`,
   documented in the runbook, not implemented here).
8. `bash tests/acceptance/control_room_controls.sh` (§ Hand-run acceptance) — all PASS.
9. `bash bin/verify.sh` green (drift clean: units, drop-in, root copy, allowlist all compared);
   commit and push by hand (auto-sync never pushes a clean tree).

## Hand-run acceptance (Dave, once, at land) and evidence-time

`tests/acceptance/control_room_controls.sh [--screen http://100.86.82.16:8787]` runs on the box and
**changes no workflow state** — every positive case is a preview or a refusal, and the script greps
itself for `--stage apply` / `enable --now` as a self-check before it starts. Steps, each `PASS`/`FAIL`:

1. Installed: socket unit `enabled` + `active`; `getent group control-room`; root copy and
   allowlist exist, root-owned, and `control_broker_allowlist.py check` is clean;
   `control-room.service` carries `SupplementaryGroups=control-room`.
2. Agents cannot connect: as dave, a 5-line python `socket.connect("/run/control-room-broker.sock")`
   raises `PermissionError`.
3. Peer gate from this host: `curl` POST `pause knowledge-digest` at the screen from the box → 403
   `peer_denied`, and a new receipt under `/var/lib/control-room/receipts/knowledge-digest/`.
4. CLI through the root copy (`sudo /usr/bin/python3 /usr/local/lib/control-room/control_broker.py act …`):
   `pause knowledge-digest --reason acceptance` → refused `state_conflict` (already paused);
   `resume knowledge-digest --stage preview` → `previewed`, prints the Persistent catch-up
   implication (expected `catchUp: true` — the stamp is 2026-09-06, the last Sunday elapse missed);
   `pause buzz-pr-watch` → refused `state_conflict`, and its receipt's `commands[].argv` carry
   `--user --machine=dave@.host`; `pause no-such-workflow` → `unknown_workflow`, receipt under
   `_refused/`; `stop knowledge-digest --reason x` (no `--confirm`) → `confirmation_required`;
   `retry raw-ingest` → `not_idempotent` (`raw-ingest` declares no `Retry` row; the CLI bypasses
   the screen's failed-last-run rule, so a *declared* workflow such as `knowledge-digest` would be
   started by the CLI — never use one here).
5. Screen (from the Mac, printed instructions, no assertion): open
   `http://praetorium:8787/workflows/knowledge-digest` → Controls shows `paused`, Resume enabled,
   Retry disabled with its reason as tooltip, last action = the newest non-preview receipt for
   this workflow (step 4's refused `stop`, `confirmation_required`). Click **Resume** → the preview
   dialog states the catch-up implication → **Cancel**. Nothing resumed; the fleet is still off.

**Evidence-time (Dave's moment, not development-time):** the one hand-started run that T5.2 and
T5.3 already name — `knowledge-digest.service` — is started through **Run now** on the screen
instead of a raw `systemctl start`: the response carries `run_id`; when the run ends,
`/runs/<run_id>` resolves to T5.2's receipt whose `run_id` is the same InvocationID, and the
control receipt's `links.run` points at it. Record that in the tracker row. If the raw start has
already happened before this lands, the run-id linkage cannot be shown retroactively; whether to
spend a second run on it is Dave's call, not a step here. The first live **resume** is DoD item 7
and starts that workflow's evidence clock; it is deliberately not part of this brief's acceptance.

## Seam deviations from T5.3 § Seams (each minimal, each stated)

1. **Third edit site in `bin/control_room_api.py`**: a `retry_policy=` constructor kwarg and a
   4-line hook in `workflows()`. The seam says "T5.3a may override `retry`" but provides only the
   `control_reader` hook, whose return value replaces `lastAction` verbatim — there is no way to
   override an action through it without changing its contract. A kwarg is smaller than widening
   `control_reader`'s return shape.
2. **Additive request fields** `stage`, `preview_token`, `trigger`, `confirm`, `retry_of`: the seam's
   `{workflow_id, action, reason}` stays valid (it yields `preview_required` for resume and
   `confirmation_required` for stop — refusals, receipted); the broker rejects any key outside this
   list.
3. **Additive response fields**: `preview` on a `previewed` 200; `control` on refusal/failed
   responses too (the UI re-fetches anyway; the extra field costs nothing); `lastAction.result`
   may be `failed` (a validated action whose `systemctl` exited non-zero is neither applied nor
   refused, and calling it either would lie).
4. **Extra HTTP statuses** 404 (unknown id — the stub already did this), 500 (`failed`), 502/504
   (broker unreachable) beyond the seam's `403|400`.
5. **Receipts root** is `/var/lib/control-room/receipts/`, not the reserved
   `~/agent-workforce/var/control-receipts/`: root-owned makes the audit trail tamper-evident
   against the agent uid, `StateDirectory=` makes systemd own its creation, and the screen still
   reads it under `ProtectHome=read-only`. The reserved path is left unused; nothing else claims it.
6. **`actions[].enabled` for the four other actions is not overridden** (seam kept); a stale
   installed allowlist surfaces as a broker refusal (`not_allowlisted`/`unknown_workflow`, receipted)
   and as a drift finding, not as a disabled button.

## Out of scope / do not touch

- **T5.3 (sibling, owns):** `bin/control_room_{cadence,exceptions,benefit,lineage,static,views,view_exceptions,view_portfolio,view_benefit,view_workflow}.py`,
  `bin/control_room_serve.sh`, `bin/control_room_ui/{app.css,app.js}`, `systemd/control-room.service`
  (this brief adds a drop-in **beside** it, never edits it), `design/benefit-ledger.toml`,
  `tests/test_control_room_{views,exceptions,benefit,cadence,lineage}.*`, `tests/control_room_fixture.py`,
  `tests/fixtures/control-room/**`, `bin/check_deploy_drift.sh:351-352` and `tests/test_deploy_drift.sh`
  group 2b (T5.3's regions; this brief edits other regions of both files). In
  `bin/control_room_api.py` only the three sites named above.
- **T5.3b:** `bin/control_room_proposals.py`, `bin/workflow_pr_*.py`, `bin/control_room_ui/proposals.js`,
  the `POST /api/v1/control/proposals` branch, `tests/test_control_room_proposals.*`,
  `tests/fixtures/control-proposals/`; any manifest, timer or contract edit that changes a
  schedule or retires a workflow (`design/agents/*.toml`, `systemd/*.timer` contents). The `Retry`
  rows are the only contract edit here and change no schedule.
- **T5.3c:** `bin/deliver.sh`, `bin/buzz_routes.env`, `bin/deliver_*.sh`, any Buzz route or
  incident-digest unit; `incidents()`/`usage()`/`activity()` semantics. Control receipts are not
  incidents; if T5.3c wants refusals in the stream it reads `/var/lib/control-room/receipts/`.
- **T5.3d:** `bin/control_room_handoffs.py`, `bin/control_room_ui/timeline.js`.
- **T5.2:** `bin/agent_propose.sh`, `bin/run_*_cc.sh` and every runner, `bin/contract_exec.py`,
  `bin/workflow_receipt.py`, `profiles/`. The broker never sets an env var for a runner; retry is a
  plain `start`.
- **T5.4:** entries in `design/benefit-ledger.toml`.
- Every workflow timer: no enable/disable/start/stop; no `systemctl` in tests (shims only); the
  acceptance script previews and refuses, never applies.
- `~/.config/**`, `~/.ssh`, `~/vault`, `~/agent-worktrees` — never read. `~/.local/share/systemd/timers`
  is read by the root broker only (stamp mtimes; no content).
- `sudoers`, polkit rules, `tailscale serve`, TLS, any public bind, any widening of the socket
  group, any `ExecStart` under `/home`.
- `.claude/briefs/current.md` — not written, not archived (orchestrator instruction).
- No manifest entry for the broker (an operator surface, T5.3's reasoning); no
  `config/fleet-units.tsv` change; no `tests/ci-expected-skips.txt` change (no new skip).

## Notes / preconditions

- **Complete option taken** (no MVP): all five actions, two-stage resume with a computed catch-up
  implication, retry gated by a contract declaration, root-owned code + allowlist + receipts,
  group-restricted socket, peer gate, CLI mode, drift coverage for the root copies, acceptance
  script — one land.
- **Socket + system units over a sudoers helper** (§ Trust boundary): kernel-enforced access, unit
  files the drift check compares, no root-executable under `$HOME`, no sudoers edit outside the repo.
- **`Accept=yes` (per-connection) over a resident daemon**: the broker is a stdin→stdout filter —
  no socket code, no idle timeout, no in-memory state to lose, and the same code path serves the
  `sudo` CLI and the tests; `MaxConnections=4` bounds it and `flock` serialises the mutating half.
- **Root-owned installed copy** rather than `ExecStart` of `~/agent-workforce/bin/…`: a root unit
  executing a dave-writable file would be the first dave→root escalation on this box (every
  existing root unit — `ttm-pool-drain` — execs from `/usr/local/bin`). The drift check makes the
  copy a compared tree so it cannot rot the way `ttm-pool-drain`'s untracked binary can.
- **Rendered allowlist in `/etc` rather than reading the manifests live**: the manifests are
  dave-writable; an agent could add `unit = "tailscaled"` and the broker would obey. A root-owned
  render, re-installed by Dave's hand and drift-checked, is what makes "the browser never submits
  arbitrary unit input" true of the whole path, not just of the browser.
- **Group `control-room` on the socket, dave not a member**: the screen runs as dave and so do
  all agents; uid alone cannot separate them. `SupplementaryGroups=` in a drop-in gives exactly one
  process the group, and the acceptance script proves a dave shell is refused at `connect()`.
- **Peer gate in the broker, loopback exempt only when the screen itself is loopback-bound**:
  a local process can reach the Tailscale address too, so "bound to Tailscale" is not "reachable
  only from the Mac"; refusing `remote == local` closes that for the control path. The loopback
  exemption exists because T5.3's wrapper never binds loopback — a loopback-bound screen is by
  construction a development instance, and it is what the fixture suite and the smoke run.
- **Resume is always two-stage**, even for `Persistent=false`: one flow, one dialog, the message
  says "no catch-up" when there is none. Dave's next weeks are resumes; a mode that sometimes
  skips the dialog is a mode he will misread once.
- **Preview token = the preview receipt id + state fingerprint + 10-min TTL**: stateless across
  per-connection processes, auditable (apply links the preview), and a state change between
  preview and apply is refused rather than applied to a workflow that is no longer what was shown.
- **Catch-up is computed from the stamp file and `systemd-analyze calendar`** because a disabled
  timer prints empty `LastTriggerUSec` (T5.3 measured) and `Persistent=` catch-up is decided by
  systemd against that stamp; `previous = next1 − (next2 − next1)` is exact for regular specs and
  labelled approximate otherwise.
- **`retry` = `start`, gated twice**: the broker gates on the contract declaration (root truth), the
  screen on the failed-last-run rule (receipt truth it already holds); the CLI therefore can retry
  without a failed run, which is why the acceptance script uses an undeclared workflow for its
  `not_idempotent` case. Nothing is passed to the runner: a retry that needed a flag would not be
  idempotent.
- **`stop` uses `--no-block` + a 15 s poll**: a blocking `stop` can outlive the broker's timeout on
  a `TimeoutStopSec=90` unit and report `failed` for a stop that succeeded. The receipt says
  `deactivating` honestly when the poll runs out.
- **`kind = "service"` (the five `buzz-agent@*`) is excluded from the allowlist**: pause/resume are
  timer semantics and stop of a chat agent is `systemctl --user stop`, a fleet operation, not a
  workflow control. Their buttons stay disabled (T5.3's derivation) and the broker refuses
  `not_allowlisted` with that reason.
- **Receipts are world-readable, root-written**: the screen (dave) reads them; nothing as dave can
  alter or delete them. Refused requests with an unknown id go under `_refused/` because the id
  cannot be trusted as a path segment — the same rule the broker enforces on `systemctl`, applied
  to its own writes.
- **`--machine=dave@.host`** is the documented way for root to address a user manager on systemd ≥
  248 (box: 259); land step 7 proves it before the acceptance script relies on it.
- **No `ci-expected-skips.txt` change**: both suites are fixture-only; the drift section is inside
  the existing on-box predicate and reports `source-only` (red) on the box until land, which is the
  drift trap working as designed, not a skip.
- Python 3.11+ stdlib only (`tomllib` in the allowlist renderer); no new dependency; the broker
  copy runs under `/usr/bin/python3` (system python, root-owned), not linuxbrew's.
- **Depends on T5.3 landing first** (seam files); T5.3b may land before or after (different files;
  the only shared file is `control_room_api.py` at disjoint sites). This brief's `tests/test_deploy_drift.sh`
  group 17 and `bin/check_deploy_drift.sh` section are in regions T5.3 does not touch; a merge
  conflict there is textual, not semantic.
