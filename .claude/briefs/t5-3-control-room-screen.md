# Brief: T5.3 — Read-only Praetorium Control Room (views + private hosting)

**Date:** 2026-09-14   **Verify:** `bash bin/verify.sh` from the repo root (includes
`bin/check_deploy_drift.sh`; extra gates and smoke: none for this task — see § Land-time steps for
why the gate is red on the branch and green only after `bin/deploy` + the sudo unit install).

**Size:** M. **Standing constraint (Dave, 2026-09-14):** the scheduled fleet is OFF. Every test here
runs from fixtures. No step in this brief enables, starts, stops or disables any workflow timer. The
one hand-started unit is the screen itself (`control-room.service`, at land); the one hand-started
*workflow* run is T5.2's `knowledge-digest.service`, which this screen reads as shared evidence — it
is not a second run.

## Acceptance criteria

Task gate (docs/dev-plan-2026-09.md:484-486) and plan DoD item 1 (:79-85), both satisfied:

1. A private browser interface on this box, Dave only, reached from his Mac over Tailscale, served by
   one always-on unit `control-room.service` (system scope, `User=dave`) — installed and enabled at
   land, restarts on failure, binds the Tailscale address only.
2. The local browser reconciles **30 logical workflows from the 31 standing manifest entries**
   (`augustus-content` once, with both triggers) with no unexplained duplicate and no missing
   artifact field: every Portfolio cell is either a value or `Unknown`/`unavailable`.
3. Three required views plus one page per logical workflow, with every field in the task row
   (§ Views). **Exceptions is the default landing view** (`/` → 302 `/exceptions`).
4. Each paused timer renders as **paused** — an owned state, distinct from `failed`, and **not an
   exception row**. A paused workflow with a stale artifact still shows the artifact as **stale**.
5. Missing data renders `Unknown`/`unavailable`, never a fake zero: no receipt → last run Unknown,
   tokens/cost `unavailable`, benefit `Unknown`. A measured `0` from a receipt renders as `0`.
6. Agent usage is truthful: per-agent tokens/cost sum only `measured` receipts and say
   `unavailable` otherwise (existing `/api/v1/usage` semantics, now rendered).
7. **A deliberately failing check appears by name**: a receipt whose assertion `artifact-is-this-run`
   is `failed` produces an Exceptions row naming that assertion and its workflow, and the workflow
   page lists it. (Proven on fixtures; live it appears the moment T5.2's first receipt lands — the
   morning delivery stays `overnight-morning-report`'s job and is untouched here.)
8. Research lineage on every workflow page: source → selection rule and reason → trigger → agent →
   Notion output → human action, each stage `Unknown` when its source is absent.
9. One-click Notion output links: the latest valid artifact's URI is an `<a target=_blank
   rel=noopener>`; contract and Dev Plan links on every Portfolio row and workflow page.
10. The frontend is vanilla server-rendered HTML + static CSS/JS from the same Python process. No
    bundler, no CDN, no network at deploy or run time. CSP `default-src 'self'`.
11. The HTTP surface stays read-only: every write method is 405 **except** two validated stubs that
    return `501` (§ Seams) so the browser→control contract is exercised end to end before T5.3a/b.
12. Verify green after land; fixture suites green on the branch; drift red on the branch is
    explained by exactly the files this brief adds.

## Existing state (read, confirmed 2026-09-14)

- `bin/control_room_api.py` (746 lines): `ControlRoomReadModel` joins `design/agents/*.toml`,
  `design/contracts/*.md`, `SystemdReader.show` and `~/agent-workforce/var/workflow-receipts/`;
  endpoints health/overview/workflows/{id}/runs/incidents/usage/activity; `_health` already returns
  `paused` when all a workflow's timers are `inactive`; non-GET → 405. `SourcePaths.defaults()` falls
  back to `~/dev/agent-workforce` for `design/` because `bin/deploy` never ships `design/`.
- `bin/workflow_receipt.py` owns the receipt shape (schema 1; exactly one terminal outcome;
  usage/cost `measured`|`unavailable` with nulls). **Not modified by this brief.** `validate()`
  ignores unknown keys, so an optional `consumption` object can be read leniently.
- Live: `~/agent-workforce/var/workflow-receipts/` does not exist yet (T5.2 not landed) → at land the
  screen shows 30 rows with receipts `unavailable`, health from systemd only. That is the honest state.
- Live timers: every system workflow timer in the manifests is `UnitFileState=disabled` except
  `qmd-refresh.timer`; `buzz-pr-watch.timer` (user) disabled. Count from `systemctl`, never prose.
- `systemctl show` accepts `--timestamp=utc` (prints `Mon 2026-09-14 07:10:10 UTC`); a disabled
  timer prints empty `LastTriggerUSec`/`NextElapseUSecRealtime`; a monotonic timer (qmd-refresh,
  `OnUnitActiveSec`) prints empty `NextElapseUSecRealtime` even while active.
- `systemd-analyze calendar "<spec>" --iterations=2` works as `dave` (prints `Next elapse` and
  `Iteration #2`, plus `(in UTC)` lines when the box tz is not UTC).
- `tailscale ip -4` → `100.86.82.16` as `dave`, MagicDNS name `praetorium`; uid 1000;
  `systemctl --user show` works from a clean env with `XDG_RUNTIME_DIR=/run/user/1000` and
  `DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus`.
- `bin/check_deploy_drift.sh:351-362` compares `bin/` **flat** (`names`, `-maxdepth 1`), so a
  subdirectory under `bin/` deploys (rsync) but is drift-checked by nothing. Fixed here (§ Files).
- `bin/verify.sh` lints only top-level `bin/*` shell files and runs every `tests/*.sh`.
- Every `tests/test_*.sh` must be claimed: by a manifest `suite` list or a `[[suite]]` in
  `design/fleet-suites.toml` whose `asserts` ids are anchored `(::id)` in the `.sh` or its
  same-name `.py` (`tests/test_workflow_coverage.py:359-` and the asserts join). Both directions.
- Figma prototype `https://sand-boil-02043797.figma.site` is a JS shell (unreadable by fetch);
  open it in a browser from the Mac for look-and-feel only. **This brief fixes structure and fields;
  the prototype never overrides them.** Visual register: dense operator table, muted greys, one
  accent per state chip (paused=slate, healthy=green, failed=red, incomplete=amber, running=blue,
  unknown=dashed outline), exceptions first, healthy rows recede.

## Architecture decisions (complete option taken; reasons in § Notes)

- **Server-side rendered HTML in Python**, one module per view, pure functions
  `render_*(model_dict) -> str` over the same dicts the JSON API returns. Static `app.css`/`app.js`/
  `actions.js` add filters, auto-refresh and the control stub round-trip. The page is truthful with
  JavaScript disabled.
- **Hosting:** `systemd/control-room.service` (system scope, `User=dave`), `ExecStart` a wrapper
  that binds `tailscale ip -4`:8787 and refuses to start when Tailscale is down. Dave-only =
  reachable only from the tailnet (one user: `Dave1524@`), not LAN, not loopback, not public.
- **Read-model extensions** live in small sibling modules imported by `control_room_api.py`
  (cadence/freshness, exceptions, benefit, lineage, static, control read-model). `incidents()`,
  `usage()`, `activity()` semantics are unchanged (T5.3c reads them).

## Views (fields are the contract; all rendered from `/api/v1/*` dicts)

Layout shell: top nav `Exceptions · Portfolio · Benefit`, right side `generated_at`, data-status
strip (each source `available|degraded|unavailable`, clickable to expand `dataStatus.errors`),
auto-refresh toggle (60 s, off by default, remembered in `localStorage`).

**Exceptions `/exceptions` (default) — the opening screen.** Tiles: workflows by health
(`healthy/running/failed/incomplete/paused/unknown`), incomplete + failed runs (count, linking to
their rows), exceptions by kind. **Agent usage strip**: one card per agent from `/api/v1/usage` —
runs, tokens, cost — each `measured` value as a number, otherwise `unavailable`; never a summed
zero. Queue table, one row per (workflow, kind), ordered `failed, stale-input, missing-artifact,
missed-cadence, overdue-next-action, unconsumed-output`, then by `since` ascending: kind chip ·
workflow (link) · owner · issue (names the failed assertion id / reason / age) · required action ·
evidence links (run page, artifact URI) · `paused` chip when the workflow is paused · since. Empty
state depends on `dataStatus.receipts`: `available` → "No exceptions. N paused, M unknown.";
`unavailable` → "Receipts unavailable — health is Unknown for every workflow; no exceptions can be
derived." Below it, **Data quality** (not exceptions): contract unavailable, malformed receipts,
systemd unavailable, manifest errors — from `/api/v1/incidents` items whose `failedAssertion` ∈
{`contract-available`, `receipt-schema-valid`} plus `dataStatus.errors.systemd/manifests`.

**Portfolio `/portfolio`.** One row per logical workflow (30): workflow (link) · owner · purpose ·
trigger(s) (each trigger: unit, trigger text, state chip `paused|active|running|unknown`) ·
artifact/state change (`contract.artifact`) · beneficiary · next actor → next action · benefit
status (ledger decision or `Unknown`) · health chip · last run (time, outcome) · last valid
artifact (time, freshness chip `current|stale|Unknown`, link) · links (contract local, contract
GitHub, Dev Plan). Default order: exceptions first, then `unknown`, `paused`, `healthy`. Client-side
filters (JS): text, owner, health. No hiding — Portfolio is the full 30.

**Benefit `/benefit`.** Definitions block (six lines) then one row per workflow: decision
`Keep|Improve|Retire|Unknown` · baseline · eligible runs · valid-artifact rate · consumption as four
separate counts `opened / approved / sent / marked useful` (or `Unknown`) · latency (median run
duration) · manual minutes avoided · evidence + owner (ledger) . `Unknown` is preferred when
unmeasured; no estimate is ever computed.

**Workflow `/workflows/{id}`.** Sections in order: header (name, owner, health chip, purpose,
lifecycle) · **Controls** (§ Seams: state chip, next run, last action `Unknown`, buttons) ·
Triggers & schedules (per trigger: unit, scope, kind, trigger text, cadence, timer active/enabled,
last trigger, next run — `estimated` when derived) · Runs (last run; incomplete runs = `skipped` +
`failed` + currently running; reliability = valid-artifact rate over eligible runs; last 10
outcomes strip; each run links `/runs/{run_id}`) · Latest valid artifact (title, opens in Notion,
freshness, age, cadence) · Tokens & cost (latest run; totals over measured receipts; `unavailable`
otherwise) · Benefit & consumption (the Benefit row) · **Lineage** (six stages) · Links (contract
local + GitHub, Dev Plan tracker + task ids, manifest paths) · Handoffs (`Unknown` until T5.3d).

**Run `/runs/{run_id}`.** Receipt rendered: outcome, reason, assertions table (id/status/message),
artifact/state change, usage, cost, next action (+ due), parent run, handoff (raw or `Unknown`),
receipt path.

### Rendering rule (one helper, tested)

`cell(value)` in `bin/control_room_views.py`: `None`/missing → `<span class="unknown">Unknown</span>`;
measurement dict with `status != "measured"` → `<span class="unknown">unavailable</span>`;
measured numbers render as numbers (a measured `0` is `0`). No view may print `0`, `—`, `n/a` or
an empty cell for missing data. Every rendered string passes through `html.escape`.

## Read-model extensions (what the views consume)

Each item from `ControlRoomReadModel.workflows()` gains:

```
"cadence":      {"status": "measured"|"unavailable", "seconds": int|null, "source": "OnCalendar"|"OnUnitActiveSec"|null,
                 "spec": str|null, "persistent": bool|null, "randomizedDelaySec": int|null, "error": str|null}
"lastValidArtifact": null | {"runId", "endedAt", "uri", "title", "kind": "artifact"|"state_change", "ageSeconds"}
"artifactFreshness": "current"|"stale"|"unknown"      # stale = age > 2 × cadence + 3600; unknown when no artifact or cadence unavailable
"control":      {"state": "paused"|"active"|"running"|"unknown", "source": "systemd"|"unavailable",
                 "nextRunAt": iso|null, "nextRunEstimated": bool, "lastTriggerAt": iso|null, "persistent": bool|null,
                 "lastAction": null,                              # T5.3a fills; shape fixed in § Seams
                 "actions": [{"id": "pause"|"resume"|"run_now"|"retry"|"stop", "enabled": bool, "reason": str|null}]}
"links":        {"contractLocal": "/api/v1/workflows/{id}/contract"|null, "contractGithub": url|null,
                 "devPlanTracker": "https://app.notion.com/p/071af559943649fb86494b88a67106a6",
                 "devPlanDoc": "https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium/blob/main/docs/dev-plan-2026-09.md",
                 "taskIds": ["T4.2", ...]}                        # regex \bT\d+\.\d+[a-d]?\b over the contract's first 10 lines
"benefit":      the Benefit row for this workflow (see bin/control_room_benefit.py)
"lineage":      the six-stage list (see bin/control_room_lineage.py)
"eligibleRuns": int, "validArtifactRate": float|null, "incompleteRuns": [run summaries]
```

Trigger dicts gain ISO-UTC `lastTriggerAt`/`nextRunAt`/`startedAt`/`endedAt` (parsed from
`--timestamp=utc` output; unparsable → `null` and the raw string kept under `raw`).
`contract` gains `inputs` (parsed `## Inputs` table rows: `source`, `freshness`, `if_stale`),
`decline_conditions` (section text) and `task_ids`.

`_health` change: only a **timer-kind** trigger's running service yields `running`; for
`kind = "service"` (the five `buzz-agent@*`) health comes from receipts (`unknown` when none) and
`control.state` is `active|paused|unknown` from `ActiveState`.

`control.state`: any timer-kind service running → `running`; all timers `inactive` or
`UnitFileState=disabled` → `paused`; any timer `active` → `active`; systemd unavailable → `unknown`.
`nextRunAt`: `NextElapseUSecRealtime` when present; else, if timer active and `lastTriggerAt` and
cadence measured → `lastTriggerAt + cadence` with `nextRunEstimated: true`; else `null` (paused →
always `null`). `actions[].enabled`: pause ↔ `active|running`; resume ↔ `paused`; run_now ↔ not
`running` and systemd available; retry → `false`, reason `"contract declares no idempotent
operation (T5.3a defines the declaration)"`; stop ↔ `running`.

### Exception classifier (`bin/control_room_exceptions.py`, pure; L = latest receipt)

| kind | rule | emitted while paused? |
|---|---|---|
| `failed` | `L.terminal.outcome == "failed"` or any `L.assertions[].status == "failed"`; `issue` names the failed ids | yes (owed decision before resume), row carries `paused: true` |
| `stale-input` | `L.outcome ∈ {decline, failed}` and (`L.terminal.reason` matches `STALE_INPUT_PATTERN = r"\b(stale|dirty|behind|not current|out of date)\b"` i, or a failed assertion id matches `INPUT_CHECK_PATTERN = r"(stale|fresh|mirror|sync|current)"`). **Precedence over `failed`** for the same run (one row, `alsoFailed: true`). Heuristic over free text — say so in the row's tooltip; a typed cause field is T5.2/T5.4's to add | yes |
| `missing-artifact` | (a) `L.outcome == "skipped"` — the incomplete run, issue = reason; (b) `eligibleRuns ≥ 1` and `validArtifactRate == 0` and the contract declares an Artifact | (a) yes; (b) **no** |
| `missed-cadence` | not paused, timer `active`, `lastTriggerAt` parsed, service not running, and no receipt with `started_at ≥ lastTriggerAt − 900 s`; or `nextRunAt` parsed and `< now − 3600 s` | **no** |
| `overdue-next-action` | `L.next_action.due_at` parsed `< now` | yes |
| `unconsumed-output` | the last valid artifact's receipt carries `consumption` with all four of `opened/approved/sent/marked_useful` explicitly `false` and the artifact is older than 7 days. Absent/null consumption → **no row** (Unknown is not an exception) | yes |

Paused itself is never a row. Constants (`UNCONSUMED_GRACE_SECONDS`, `MISSED_GRACE_SECONDS`,
`NEXT_RUN_SLACK_SECONDS`, the two patterns) are module-level and imported by the tests.

### Benefit (`bin/control_room_benefit.py`, pure)

`eligible` = receipts with outcome ∈ {artifact, decline, failed} (skipped excluded);
`validArtifactRate = artifact / eligible` (`null` when `eligible == 0`); `latencySeconds` = median
(`ended_at − started_at`) over eligible (`null` when none); `consumption` = per-signal count of
`true` over artifact receipts carrying a dict `consumption`, `status: "unavailable"` when none
carries it; `decision`, `baseline`, `manualMinutesAvoided`, `decidedAt`, `decidedBy`, `evidence`
from `design/benefit-ledger.toml` (`[[workflow]] id = "<logical id>"`; missing entry → every
field `null` → renders `Unknown`; missing file → `dataStatus.benefitLedger = "unavailable"`).
`decision` must be one of `Keep|Improve|Retire|Unknown`; anything else → ledger error named in
`dataStatus.errors.benefitLedger`, row renders `Unknown`.

### Lineage (`bin/control_room_lineage.py`, pure)

Six stages, each `{"stage", "value": str|list|null, "source": "contract"|"manifest"|"receipt"|"systemd"|null}`:
`source` ← contract `inputs[].source`; `selection` ← contract `decline_conditions` + `inputs[].freshness`
(rule) and `L.terminal.reason` (decline) or `L.artifact.title` (artifact) as the *reason*;
`trigger` ← manifest trigger text + `control.state`; `agent` ← owner + `L.agent`/`L.model`;
`output` ← `lastValidArtifact.uri` (labelled `Notion` when host ends `notion.so`/`notion.site`, else
by scheme); `human_action` ← contract `next_actor`/`next_action` + `L.next_action` (+ `due_at`).
Missing source → `value: null` → `Unknown`.

### Cadence (`bin/control_room_cadence.py`)

`timer_file(repo, unit, scope)` → `systemd/<unit>.timer` or `systemd/user/<unit>.timer`; parse
`OnCalendar=` (may repeat: take the minimum interval), `OnUnitActiveSec=`/`OnBootSec=` (span parser
for bare seconds and `s|m|min|h|d` — `buzz-pr-watch.timer` writes `20m`, `fleet-turn-check.timer`
a bare `120`), `Persistent=`, `RandomizedDelaySec=`. Interval for a calendar spec =
difference of the two iterations from the injectable `calendar_runner(spec) -> list[datetime]`
(default: `systemd-analyze calendar --iterations=2 <spec>`, parsing the `(in UTC)` lines when present
else `Next elapse`/`Iteration #2`, timeout 3 s). Per-process cache keyed by spec (10 min TTL).
Missing file / parse failure / runner error → `status: "unavailable"` with `error` named.
Also exports `parse_systemd_timestamp("Mon 2026-09-14 07:10:10 UTC") -> datetime|None`.

## HTTP surface (additions to `ControlRoomHandler._route`)

| route | method | response |
|---|---|---|
| `/` | GET | 302 → `/exceptions` |
| `/exceptions`, `/portfolio`, `/benefit` | GET | `text/html` |
| `/workflows/{id}`, `/runs/{run_id}` | GET | `text/html`, 404 page when unknown |
| `/static/{name}` | GET | file from `bin/control_room_ui/`, allowlist `css js svg`, path resolved under the dir, else 404; `Cache-Control: no-store` |
| `/favicon.ico` | GET | 204 |
| `/api/v1/exceptions` | GET | envelope of classifier rows + `dataQuality` list |
| `/api/v1/benefit` | GET | envelope of Benefit rows |
| `/api/v1/workflows/{id}/contract` | GET | `text/plain; charset=utf-8` raw contract (via `_contract` path guard), 404 when undeclared/missing |
| `/api/v1/control/actions` | POST | **501 stub** (§ Seams) |
| `/api/v1/control/proposals` | POST | **501 stub** (§ Seams) |
| anything else | POST/PUT/PATCH/DELETE | 405 (unchanged) |

HTML responses carry: `Content-Security-Policy: default-src 'self'; img-src 'self' data:;
frame-ancestors 'none'; base-uri 'none'`, `X-Frame-Options: DENY`, `X-Content-Type-Options:
nosniff`, `Referrer-Policy: no-referrer`, `Cache-Control: no-store`. HEAD mirrors GET.
`parse_args` gains `--static-dir` (default `bin/control_room_ui` next to the script). The bind
address stays a plain `--host`; choosing the Tailscale address is the wrapper's job, not the app's.

## Hosting

`systemd/control-room.service` (exact content):

```
# Praetorium Control Room — T5.3 (2026-09-14). Read-only operator screen over manifests,
# contracts, systemd state and workflow receipts. Private: binds the Tailscale address only
# (bin/control_room_serve.sh resolves it and refuses to start without one). Dave-only =
# the tailnet has one user. design/ is source-only, hence CONTROL_ROOM_REPO_ROOT.
# Land: sudo cp systemd/control-room.service /etc/systemd/system/ && sudo systemctl daemon-reload
#       && sudo systemctl enable --now control-room.service   (touches no workflow timer)
[Unit]
Description=Praetorium Control Room (read-only operator screen) — T5.3
After=network-online.target tailscaled.service
Wants=network-online.target tailscaled.service

[Service]
Type=simple
User=dave
Environment=CONTROL_ROOM_REPO_ROOT=/home/dave/dev/agent-workforce
Environment=CONTROL_ROOM_RUNTIME_ROOT=/home/dave/agent-workforce
Environment=CONTROL_ROOM_PORT=8787
Environment=XDG_RUNTIME_DIR=/run/user/1000
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/1000/bus
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/home/dave/agent-workforce/bin/control_room_serve.sh
Restart=on-failure
RestartSec=10
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

`bin/control_room_serve.sh` (bash, shellcheck-clean): `set -euo pipefail`; `addr=$(tailscale ip -4
| head -n1)`; refuse (exit 1, message names `tailscale ip -4`) when empty or not `100.` /`fd7a:`-
prefixed; `exec python3 "$(dirname "$0")/control_room_api.py" --host "$addr" --port
"${CONTROL_ROOM_PORT:-8787}"`. Never `0.0.0.0`, never a LAN address. Tests run the script with a
fake `tailscale` on `PATH` (fixture under `tests/fixtures/control-room/bin/tailscale`) and a
`CONTROL_ROOM_DRY_RUN=1` env that makes it print the resolved command instead of exec'ing.

URL for Dave: `http://100.86.82.16:8787/` or `http://praetorium:8787/` (MagicDNS). `tailscale
serve` (TLS, identity headers) is the deliberate non-choice: its state lives in tailscaled, outside
this repo, invisible to the drift check — recorded in § Notes.

## Files to modify

- `bin/control_room_api.py` — import the six sibling modules; `SystemdReader.show` adds
  `--timestamp=utc`, `NextElapseUSecMonotonic` to `PROPERTIES`; `_systemd_for` emits ISO fields;
  `_contract` adds `inputs`, `decline_conditions`, `task_ids`; `workflows()` adds the fields in
  § Read-model extensions (cadence via `control_room_cadence`, control via a new
  `_control_for(triggers, cadence)`, `lastValidArtifact`/`artifactFreshness`, `benefit`, `lineage`,
  `links`, `eligibleRuns`, `validArtifactRate`, `incompleteRuns`); `_health` service-kind rule;
  `dataStatus` gains `benefitLedger`; new methods `exceptions()`, `benefit()`,
  `contract_text(workflow_id)`; `__init__` gains `calendar_runner=None`, `control_reader=None`,
  `static_dir=None`; `_route` gains the routes in § HTTP surface; `_html()` writer; `_read_only`
  stays the default for write methods and `do_POST` routes only the two `/api/v1/control/*` paths
  to the stubs. Keep the file under ~900 lines by delegating rendering entirely to the view modules.
- `bin/check_deploy_drift.sh:351-352` — bin half compares **recursively**: `relnames` instead of
  `names`, with `! -path '*/__pycache__/*' ! -name '*.pyc'` added to both sides. Header comment
  gains one dated line saying why (a nested `bin/control_room_ui/` deploys but was compared by
  nothing).
- `tests/test_deploy_drift.sh` — new group `2b. bin/ is compared recursively` after group 2: a
  nested source-only file under `src_bin/ui/app.css` is `DRIFT [bin] source-only: ui/app.css`; a
  `src_bin/__pycache__/x.pyc` is silent; a nested file present on both sides with different bytes
  is `content differs: ui/app.css`.
- `tests/test_control_room_api.py` — `FakeSystemd` returns UTC-suffixed strings (the reader now
  asks for `--timestamp=utc`); add `test_control_state_and_next_run` (::control-room-control-state):
  paused timer → `control.state == "paused"`, `nextRunAt is None`, `actions` resume enabled / pause
  disabled; active timer → `active`, run_now enabled. Existing assertions unchanged.
- `design/fleet-suites.toml` — five new `[[suite]]` entries (owner `fleet`, `why_no_workflow` one
  sentence each) with the anchored ids listed in § Test plan; add `control-room-control-state` to
  the existing `test_control_room_api.sh` entry; rewrite the paragraph above that entry ("When
  durable hosting lands, the service gets its own workflow entry and contract") to record the
  decision: the screen is an operator surface, **not** a manifest workflow — it renders the
  portfolio and must not be a row of it.
- `docs/runbook.md` — new `## Control Room (T5.3)` section after `## Deploy ordering`: URL, unit,
  bind rule, what it reads, what it never writes, restart command, the `design/` source-only
  dependency, "receipts unavailable until T5.2's first run".
- `CLAUDE.md` (repo) § Where things live — one bullet: `control-room.service` serves
  `http://praetorium:8787/` from `bin/control_room_api.py` + `bin/control_room_ui/`, reads only,
  binds Tailscale only, reads `design/` from the source checkout.

## Files to create

Source (all Python stdlib-only, `from __future__ import annotations`, sibling imports via
`sys.path.insert(0, dirname(__file__))` exactly as `control_room_api.py` does):

- `bin/control_room_cadence.py` — § Cadence. Public: `cadence_for(repo, unit, scope, runner=None)`,
  `parse_span`, `parse_systemd_timestamp`, `freshness(age_seconds, cadence)`, `DEFAULT_RUNNER`.
- `bin/control_room_exceptions.py` — § Exception classifier. Public: `classify(workflow_item,
  receipts_for_workflow, now) -> list[row]`, `KINDS` (ordered tuple), the constants.
- `bin/control_room_benefit.py` — § Benefit. Public: `load_ledger(repo) -> (dict, errors)`,
  `benefit_row(workflow_item, receipts, ledger_entry) -> dict`, `DECISIONS`.
- `bin/control_room_lineage.py` — § Lineage. Public: `lineage(workflow_item, latest_receipt) ->
  list[stage]`, `STAGES`.
- `bin/control_room_static.py` — `serve(static_dir, name) -> (status, content_type, bytes)`;
  allowlist `{"css": "text/css", "js": "text/javascript", "svg": "image/svg+xml"}`; resolves and
  requires `path.relative_to(static_dir)`; no symlink escape; missing → 404.
- `bin/control_room_views.py` — layout shell, nav, data-status strip, `cell()`, `chip(state)`,
  `fmt_time`, `fmt_duration`, `fmt_tokens`, `link()`, `table()` helpers, 404 page. No view content.
- `bin/control_room_view_exceptions.py` — `render_exceptions(exceptions_env, overview, incidents)`.
- `bin/control_room_view_portfolio.py` — `render_portfolio(workflows_env)`.
- `bin/control_room_view_benefit.py` — `render_benefit(benefit_env)`.
- `bin/control_room_view_workflow.py` — `render_workflow(item, runs)`, `render_run(run)`; includes
  the Controls panel markup (§ Seams) and the Lineage block.
- `bin/control_room_serve.sh` — § Hosting.
- `bin/control_room_ui/app.css` — the stylesheet; `.unknown` dashed muted; state chips; tables
  dense; `@media (prefers-color-scheme: dark)` variant; works at 400 px.
- `bin/control_room_ui/app.js` — Portfolio filters, data-status expand, auto-refresh toggle
  (`location.reload()` on a 60 s interval, state in `localStorage`, try/catch), relative-time hover.
- `bin/control_room_ui/actions.js` — § Seams stub round-trip (T5.3a extends this file).
- `design/benefit-ledger.toml` — header comment (owner: T5.4 decisions, one `[[workflow]]` per
  logical id, fields and vocabulary as § Benefit) and **zero entries** at creation.
- `systemd/control-room.service` — § Hosting, verbatim.

Fixtures (`tests/fixtures/control-room/`, all committed files, no generator at test time):

- `receipts/<workflow>/<run>.json` — schema-1 receipts, written once with `workflow_receipt.write`
  semantics but stored as files: `praetorium-daily-plan/run-0912.json`, `run-0913.json` (artifact,
  Notion URI `https://www.notion.so/...`, usage+cost `measured`, agent marcus);
  `m1-signal-scan/run-0910.json` (artifact, usage `unavailable`); `raw-ingest/run-0913.json`
  (failed; assertion `artifact-is-this-run` failed, message "artifact is dated 2026-09-12"; **the
  deliberately failing check**); `agent-proposal/run-0912.json` (decline, reason
  `DECLINE: no open queue item`); `bd-stall-radar/run-0908.json` (decline, reason `DECLINE: mirror
  stale — vault_sync_guard refused`); `knowledge-digest/run-0823.json` (artifact, ended 2026-08-23,
  the stale-while-paused case); `overnight-morning-report/run-0911.json` (artifact,
  `next_action.due_at = 2026-09-12T08:00:00Z`, overdue); `bd-followup-drafts/run-0901.json`
  (artifact, `consumption` all four `false`, unconsumed); `memory-consolidation/run-0914.json`
  (skipped, reason `SKIP: previous run still active`); `agent-inbox-sync/run-0914.json` (artifact,
  started 07:31Z, after its last trigger); `scorecard/bad.json` (`{"not":"a receipt"}`, malformed).
  `weekly-pre-assembly` and every other workflow: **no receipt** (the Unknown case).
- `systemd.json` — `{"default": {"timer": {...active waiting enabled...}, "service": {...inactive dead
  success...}}, "system": {overrides by unit}, "user": {overrides by unit; a `null` value means
  "user bus unavailable"}}`. Overrides — the **twelve paused timer units**, exact list:
  `augustus-content, content-change-dispatch, knowledge-digest, agent-proposal, m1-signal-scan,
  bd-stall-radar, bd-followup-drafts, praetorium-daily-plan, overnight-morning-report,
  praetorium-eod-summary, weekly-pre-assembly, inbox-backlog-alert` (`ActiveState=inactive,
  SubState=dead, UnitFileState=disabled`, empty trigger/next fields) → 12 units, **11 logical
  workflows** paused (augustus-content owns two). Of these, bd-stall-radar (stale-input),
  overnight-morning-report (overdue-next-action) and bd-followup-drafts (unconsumed-output) still
  produce their non-cadence rows with `paused: true`; none produces `missed-cadence` or
  `missing-artifact`. Active timers with a role: `raw-ingest.timer` active, `LastTriggerUSec = Sun
  2026-09-13 03:02:11 UTC` (the failed row); `memory-consolidation.timer` active, last trigger
  `Mon 2026-09-14 03:31:00 UTC` (the skipped → missing-artifact row); `fleet-turn-check.timer`
  active with `LastTriggerUSec = Mon 2026-09-14 07:00:00 UTC` and no receipt (missed-cadence);
  `agent-inbox-sync.timer` active, last trigger `07:30:00 UTC` (receipt after it → no row);
  `local-tier-eval.service` `active/running` (running); `buzz-agent@marcus.service` (user)
  active/running; `buzz-agent@aurelian.service` (user) → `null`; `buzz-pr-watch.timer` (user)
  disabled. Everything else takes `default`. Timestamps all `... UTC`.
- `cadence.json` — map `OnCalendar` spec → seconds for every spec in `systemd/*.timer` and
  `systemd/user/buzz-pr-watch.timer` (`"Sun 09:00": 604800`, `"*-*-* 01:30": 86400`, `"*:0/15": 900`,
  `"hourly": 3600`, `"Mon *-*-08..14 09:37": 2419200`, …). The fake runner returns
  `[T0, T0 + seconds]`; an unmapped spec raises → cadence `unavailable` (tested).
- `benefit-ledger.toml` — `knowledge-digest → Improve` (baseline "weekly digest read Monday",
  `manual_minutes_avoided = 30`), `agent-proposal → Keep`, one invalid entry `decision = "Maybe"`
  for the vocabulary test.
- `bin/tailscale` — executable fake printing `100.86.82.16` (and `bin/tailscale-down` printing
  nothing, exit 1) for the wrapper test.
- `tests/control_room_fixture.py` — helper (not a suite: no `test_` prefix): builds
  `ControlRoomReadModel(SourcePaths(repo=ROOT, runtime=FIXTURE, receipts=FIXTURE/"receipts"),
  systemd=FakeSystemd(FIXTURE/"systemd.json"), clock=lambda: NOW, calendar_runner=FakeCalendar(...))`
  with `NOW = 2026-09-14T08:00:00Z`; `FakeSystemd.show(name, scope)` = override or default or
  `({}, "Unit ... could not be found")`; `repo=ROOT` is the real checkout — manifests, contracts and
  `systemd/*.timer` are what the screen must reconcile, and every checkout carries them (no box
  precondition, no SKIP line).

Tests (one `.sh` wrapper per `.py`, the wrapper is `python3 tests/<name>.py` with the fixture
header comment, exactly `tests/test_control_room_api.sh`'s shape):

- `tests/test_control_room_views.{sh,py}`
- `tests/test_control_room_exceptions.{sh,py}`
- `tests/test_control_room_benefit.{sh,py}`
- `tests/test_control_room_cadence.{sh,py}`
- `tests/test_control_room_lineage.{sh,py}`

## Test plan (TDD: write each red first; ids are the `(::id)` anchors and the fleet-suites `asserts`)

`tests/test_control_room_views.py` (::control-room-30-of-31) 31 standing entries → exactly 30
`<tr data-workflow=…>` on `/portfolio`, `augustus-content` once with two trigger chips, no `id`
repeated, and every row has a non-empty artifact/state-change cell (`Unknown` allowed, empty not);
the numbers 30/31 are the gate's claim, held as module-level `STANDING_ENTRIES = 31` /
`LOGICAL_WORKFLOWS = 30` — a retirement (T5.3b) decrements them, and T5.2 (`workflow-receipt-sweep`),
T5.3c (`workflow-incidents`) and T6.1 (−`memory-consolidation`) each adjust them with the manifest.
(::control-room-exceptions-default) `GET /` is 302 to `/exceptions`; the queue lists `raw-ingest`
first with kind `failed`. (::control-room-failed-check-named) that row's issue text contains
`artifact-is-this-run`; `/workflows/raw-ingest` lists it under Runs. (::control-room-paused-owned)
12 trigger chips read `paused`; 11 workflow rows carry `data-health="paused"`; none of those 11
appears in the queue for `missed-cadence` or `missing-artifact`; the overview tile counts 11
paused; `paused` ≠ `failed` (raw-ingest is `failed`, not paused).
(::control-room-stale-while-paused) `knowledge-digest` renders `paused` **and** its artifact cell
carries `data-freshness="stale"` with the Notion link; it is not in the queue.
(::control-room-unknown-never-zero) `weekly-pre-assembly` row: last run, last artifact and benefit
cells contain `Unknown`; tokens/cost contain `unavailable`; the row's HTML contains none of `>0<`,
`0 tokens`, `$0`, `—`; `m1-signal-scan` tokens read `unavailable` while `praetorium-daily-plan`
reads the measured integers. (::control-room-notion-link) daily-plan's artifact renders
`<a href="https://www.notion.so/…" target="_blank" rel="noopener`. (::control-room-lineage)
`/workflows/agent-proposal` renders six `<li data-stage=…>` with `source` naming
`04_operations/box_brief/queue.md` and `selection` reason `DECLINE: no open queue item`; a stage
with no source renders `Unknown`. (::control-room-usage-truthful) `/exceptions` agent-usage tile
shows marcus measured totals and `unavailable` for claudius. (::control-room-static-fails-closed)
`/static/app.css` 200 `text/css`; `/static/../control_room_api.py` 400/404; `/static/x.py` 404.
(::control-room-html-headers) every HTML response carries the CSP, `X-Frame-Options: DENY` and
`Cache-Control: no-store`; `HEAD /portfolio` has no body. (::control-room-control-stub-501)
`POST /api/v1/control/actions` `{"workflow_id":"knowledge-digest","action":"resume","reason":"test"}`
with `X-Control-Room: 1` → 501 JSON `{"status":"not_implemented","workflow_id":…,"action":…}`;
unknown workflow → 404; `action: "rm -rf"` → 400; missing header → 400; `POST
/api/v1/workflows/x` still 405; the proposals stub behaves the same for `kind: "schedule"|"retire"`
(it validates `kind`, never `stage` — T5.3b adds `stage: "list"`); `GET`/`HEAD /api/v1/control/*` → 405.
(::control-room-serve-tailscale-only) the wrapper under the fake `tailscale` prints `--host
100.86.82.16 --port 8787`; with `tailscale-down` it exits 1 naming `tailscale ip -4`.

`tests/test_control_room_exceptions.py` (::exceptions-kind-table) one synthetic workflow item +
receipts per kind, each yields exactly its kind, in `KINDS` order.
(::exceptions-stale-input-precedence) a failed run whose reason says "mirror stale" yields one
`stale-input` row with `alsoFailed: true`, not two rows. (::exceptions-paused-suppression) paused
+ active-timer-only rules (`missed-cadence`, `missing-artifact`(b)) yield nothing; paused + failed
yields `failed` with `paused: true`. (::exceptions-unknown-is-not-exception) no receipt → no
row; `consumption` absent → no `unconsumed-output`; `due_at` null → no `overdue-next-action`.
(::exceptions-missed-cadence) active timer, last trigger 07:00Z, no receipt since → row; a receipt
at 07:31Z after a 07:30Z trigger → none.

`tests/test_control_room_benefit.py` (::benefit-unknown-preferred) no receipts → rate/latency
`null`, consumption `unavailable`, decision `Unknown`; no ledger file → `dataStatus.benefitLedger
== "unavailable"`. (::benefit-four-signals-separate) two artifact receipts with consumption →
four independent counts, never a combined score key. (::benefit-ledger-join) knowledge-digest →
`Improve`, minutes 30; `decision = "Maybe"` → error named, row `Unknown`.
(::benefit-rate-and-latency) 3 artifact + 1 decline + 1 skipped → eligible 4, rate 0.75, median
latency from the four.

`tests/test_control_room_cadence.py` (::cadence-from-timer-file) `knowledge-digest` → 604800,
`source OnCalendar`, persistent true, `RandomizedDelaySec` 300; `qmd-refresh` → `OnUnitActiveSec`
span parsed without the runner. (::cadence-unavailable-named) a unit with no timer file, and a spec
the fake runner cannot map, both → `status unavailable` with `error` set, never 0.
(::freshness-two-cadences) age 13 d / cadence 7 d → `current`; 15 d → `stale`; cadence
unavailable → `unknown`. (::systemd-timestamp-utc) `"Mon 2026-09-14 07:10:10 UTC"` parses to the
aware datetime; `""`, `"n/a"` and a CEST string → `None`.

`tests/test_control_room_lineage.py` (::lineage-six-stages) standing-research contract + decline
receipt → six stages with the expected sources. (::lineage-unknown-stage) a workflow with no
contract and no receipt → six stages, every `value` `None`.

`tests/test_control_room_api.py` gains (::control-room-control-state) as listed under Files to
modify. `tests/test_deploy_drift.sh` gains group 2b (claimed via trajan.toml's existing `suite`
list; no anchor needed).

Fleet registry: five `[[suite]]` entries in `design/fleet-suites.toml` naming exactly the ids
above; `tests/test_workflow_coverage.py`'s asserts join fails on any id missing from either side.

## Implementation steps (ordered; commit after each numbered group so the auto-sync sweep cannot outrun the message)

1. Fixtures first: `tests/fixtures/control-room/` (receipts, `systemd.json`, `cadence.json`,
   `benefit-ledger.toml`, fake `tailscale`), `tests/control_room_fixture.py`. Validate every
   receipt fixture with `workflow_receipt.validate` in the helper's import (a fixture that does not
   validate is a test bug, caught at import).
2. `bin/control_room_cadence.py` + `tests/test_control_room_cadence.{sh,py}` (red → green).
3. `bin/control_room_api.py`: `--timestamp=utc`, ISO trigger fields, `_health` service rule,
   `_control_for`, `lastValidArtifact`/`artifactFreshness`, `links`, contract `inputs`/
   `decline_conditions`/`task_ids`; update `tests/test_control_room_api.py` (UTC fake, control
   test).
4. `bin/control_room_exceptions.py` + suite; wire `exceptions()` and `/api/v1/exceptions`.
5. `bin/control_room_benefit.py` + suite; `design/benefit-ledger.toml`; wire `benefit()` and
   `/api/v1/benefit`; `dataStatus.benefitLedger`.
6. `bin/control_room_lineage.py` + suite; wire `lineage` onto items.
7. `bin/control_room_static.py`, `bin/control_room_views.py`, the four view modules, the three
   `bin/control_room_ui/` files; HTML routes, `/` redirect, contract text route, headers; the two
   501 stubs; `tests/test_control_room_views.{sh,py}` (largest suite — write its assertions before
   the views, one view at a time).
8. `bin/control_room_serve.sh` + the wrapper assertions; `systemd/control-room.service`.
9. `bin/check_deploy_drift.sh` recursive bin half + `tests/test_deploy_drift.sh` group 2b.
10. `design/fleet-suites.toml` entries and paragraph; `docs/runbook.md` section; `CLAUDE.md` bullet.
11. Run every new suite directly (`bash tests/test_control_room_*.sh`, `bash
    tests/test_deploy_drift.sh`, `bash tests/test_workflow_coverage.sh`, `bash
    tests/test_fleet_ownership.sh`) — all green on the branch. Run `bash bin/verify.sh`: the only
    red is drift naming this brief's `bin/` files and `control-room.service` (source-only).
12. Local smoke on loopback (no unit): `CONTROL_ROOM_RECEIPT_ROOT=tests/fixtures/control-room/receipts
    python3 bin/control_room_api.py --host 127.0.0.1 --port 8788` then `curl -sI
    http://127.0.0.1:8788/` → 302; `curl -s http://127.0.0.1:8788/portfolio | grep -c
    'data-workflow='` → 30. Stop it. (Live receipts dir absent → also smoke once without the env
    var and confirm the data-status strip says receipts `unavailable`.)

## Land-time steps (sudo; the branch cannot be green before these — say so in the PR, do not soften the gate)

1. Merge to `main` on the box; `bin/deploy` (ships `bin/`, `bin/control_room_ui/`, `systemd/`).
   `bin/deploy` exits non-zero while `/etc/systemd/system/control-room.service` is missing — expected.
2. `sudo cp systemd/control-room.service /etc/systemd/system/ && sudo systemctl daemon-reload &&
   sudo systemctl enable --now control-room.service` — **the one hand-started unit of this brief;
   it is the screen, not a workflow timer.** No other `systemctl` call.
3. `systemctl status control-room.service` (no `-f`, no argv dump needed — the unit carries no
   secret); `journalctl -u control-room.service -n 20`: one `listening on http://100.86.82.16:8787`
   line. From the Mac: open `http://praetorium:8787/` → Exceptions view, data-status strip shows
   receipts `unavailable`, Portfolio shows 30 rows, every disabled timer `paused`.
4. `bash bin/verify.sh` green; commit and push by hand (auto-sync never pushes a clean tree).
5. Evidence-time (not development-time, Dave's moment): T5.2's hand-started
   `knowledge-digest.service` writes the first live receipt; refresh the screen — the run appears
   under `/workflows/knowledge-digest` and, if any check failed, in `/exceptions` by name. Record
   the observation in the tracker row; no extra run is started for T5.3.

## Seams for T5.3a and T5.3b

### (a) Action buttons and the request the browser sends

Buttons live **only** in the workflow page's **Controls** panel (`<section id="controls"
data-workflow-id="{id}">`), never in list views. Row 1 (T5.3a): `Pause`, `Resume`, `Run now`,
`Retry`, `Stop current run` — each `<button data-action="pause|resume|run_now|retry|stop"
data-requires-reason="false|true">`, disabled per `control.actions[].enabled` with the `reason`
as `title`. Row 2 (T5.3b): `Change schedule…` and `Retire…` — `<button
data-proposal-kind="schedule|retire">`. Result region `<pre id="control-result">`.

`bin/control_room_ui/actions.js` (T5.3 ships; T5.3a/b extend) on click: `stop` and both proposals
prompt for a reason (required); others prompt optional; then

```
POST /api/v1/control/actions          Content-Type: application/json   X-Control-Room: 1
{"workflow_id": "<logical id>", "action": "pause|resume|run_now|retry|stop", "reason": "<string>"}

POST /api/v1/control/proposals        same headers
{"workflow_id": "<logical id>", "kind": "schedule|retire", "reason": "<string>",
 "stage": "preview|submit", "proposed": {…kind-specific, T5.3b defines…}, "preview_token": null|str}
```

T5.3's stub validates and answers: unknown `workflow_id` → 404; `action`/`kind` outside the
vocabulary, non-JSON body, or missing `X-Control-Room` header → 400 `{"error": …}`; otherwise
**501** `{"status": "not_implemented", "error": "control broker not wired (T5.3a)" | "PR generator
not wired (T5.3b)", "workflow_id": …, "action"|"kind": …}`. After **any** response (2xx, 4xx, 501)
`actions.js` renders the JSON in `#control-result` and **re-fetches `GET
/api/v1/workflows/{id}`** to redraw the state chip and buttons from `control` — the UI never
assumes state from the click. T5.3a's real responses: `200 {"receipt": <audit receipt>, "control":
<reconciled control object>}`; refusal `403|400 {"error", "receipt"}` (refusals are receipted
too). T5.3b's: `200 {"stage": "preview", "preview_token", "diff", "checks": [{id, status,
output}], "residue": [...]}` then `200 {"stage": "submitted", "pr": {"url", "branch"}}`.

### (b) Control read-model fields the UI expects

`control` on every workflow item (§ Read-model extensions) is the contract:
`state ∈ paused|active|running|unknown`, `source`, `nextRunAt`, `nextRunEstimated`,
`lastTriggerAt`, `persistent` (the `Persistent=true` catch-up implication resume must show
*before* applying), `lastAction`, `actions[]`. T5.3 always emits `lastAction: null`. T5.3a fills it
as `{"action", "actor", "reason", "at", "result": "applied|refused", "before": state, "after":
state, "receiptId", "links": {…}}` by passing `control_reader=<callable(logical_id) -> dict|None>`
into `ControlRoomReadModel(...)` — the hook exists in T5.3 and is `None` by default; when set, its
return value replaces `lastAction` verbatim. `actions[].enabled` is T5.3's systemd-derived
default; T5.3a may override `retry` (idempotency declaration) and must keep the shape.

### (c) File and module boundary

**T5.3 owns (this brief):** `bin/control_room_api.py`, `bin/control_room_{cadence,exceptions,
benefit,lineage,static,views,view_exceptions,view_portfolio,view_benefit,view_workflow}.py`,
`bin/control_room_serve.sh`, `bin/control_room_ui/{app.css,app.js,actions.js}`,
`systemd/control-room.service`, `design/benefit-ledger.toml` (file; T5.4 owns its entries),
`tests/test_control_room_{views,exceptions,benefit,cadence,lineage}.*`,
`tests/control_room_fixture.py`, `tests/fixtures/control-room/**`.

**T5.3a edits exactly three places in T5.3 files and nothing else:** the `POST
/api/v1/control/actions` branch in `ControlRoomHandler` (replace the 501 with a call into their
module), the `control_reader=` argument in `main()` (plus a `retry_policy=` kwarg on
`ControlRoomReadModel`, consulted where `item["control"]` is assembled), and
`bin/control_room_ui/actions.js` (extend, keep the re-fetch); in `bin/check_deploy_drift.sh` T5.3a
owns the unit globs at `:451-452` (`*.socket`) and a new broker section (`tests/test_deploy_drift.sh`
group 17) — this brief's region is the bin half `:351-352` and group 2b only. **Reserved for T5.3a
(do not create here):** `bin/control_room_control.py` (HTTP-side client + audit-receipt reader),
`bin/control_broker.py`, `bin/control_broker_allowlist.py`, `systemd/control-room-broker.socket`,
`systemd/control-room-broker@.service` (templated, `Accept=yes`), the drop-in
`systemd/control-room.service.d/broker.conf`, `/var/lib/control-room/receipts/` (root-owned
`StateDirectory`; path reserved, shape theirs), `/etc/control-room/allowlist.json`,
`tests/acceptance/control_room_controls.sh`, `tests/test_control_room_control.*`,
`tests/test_control_broker.*`, `tests/fixtures/control-broker/`.

**T5.3b edits exactly three places in T5.3 files:** the `POST /api/v1/control/proposals` branch, a
`proposals` binding in `main()` (same pattern as T5.3a's `control`), and one `<script
src="/static/proposals.js" defer>` line in `bin/control_room_view_workflow.py`; plus new
`bin/control_room_ui/proposals.{js,css}` (T5.3 leaves the proposal buttons wired to `actions.js`'s
generic poster; T5.3b moves them). **Reserved for T5.3b:** `bin/control_room_proposals.py`,
`bin/workflow_pr_*.py`, `bin/workflow_retire_residue.py`, `design/retired-workflows.toml`,
`systemd/control-room.service.d/proposals.conf`, `tests/test_control_room_proposals.*`,
`tests/test_workflow_pr_*`, `tests/test_workflow_retire*`, `tests/acceptance/control_room_proposals.sh`,
`tests/fixtures/control-proposals/`.
When T5.3b retires a workflow it also updates the 30/31 literals in
`tests/test_control_room_views.py` (::control-room-30-of-31) alongside the manifest — that
coupling is the gate's claim, not an accident.

**T5.3c** consumes `/api/v1/exceptions` read-only and **owns `incidents()`**: it edits three spots in
`bin/control_room_api.py` — sibling imports (`workflow_incidents`, `incident_state`), a defaulted
`SourcePaths.incidents` field, and the body of `incidents()` (ids become `<class>:<workflow_id>`, extra
fields added; the consumers below key on `failedAssertion`, not `id`) — nothing else; this brief's
`--timestamp=utc` on `SystemdReader.show` is shared with T5.3c (idempotent). Item shapes are
frozen by this brief (`id, severity, status, workflowId, agent, issue, failedAssertion,
requiredAction, runId, evidence` and the classifier row `kind, workflowId, owner, issue,
failedAssertions[], requiredAction, evidence{runId, artifactUri}, paused, since, alsoFailed`).
**T5.3d** owns `bin/control_room_handoffs.py`, `bin/control_room_ui/timeline.js` and the Handoffs
section's content; T5.3 renders `handoff` raw or `Unknown` in a `<section id="handoffs">`.

Control execution — any `systemctl start|stop|enable|disable`, any socket, any root path — is
entirely outside this brief; the stubs never shell out.

## Out of scope / do not touch

- **T5.3a:** `bin/control_room_control.py`, `bin/control_broker.py`, `bin/control_broker_allowlist.py`,
  `systemd/control-room-broker.*`, `systemd/control-room.service.d/*`, anything under
  `/var/lib/control-room/` or `/etc/control-room/`.
- **T5.3b:** `bin/control_room_proposals.py`, `bin/workflow_pr_*.py`, `bin/workflow_retire_residue.py`,
  `bin/control_room_ui/proposals.{js,css}`, `design/retired-workflows.toml`, any manifest/unit/contract edit that changes a schedule or
  retires a workflow (`design/agents/*.toml`, `systemd/*.timer` contents, `design/contracts/*.md`).
- **T5.3c:** `bin/deliver.sh`, `bin/buzz_routes.env`, `bin/deliver_*.sh`, any Buzz route or
  incident-digest unit; `incidents()`/`usage()`/`activity()` semantics.
- **T5.3d:** `bin/control_room_handoffs.py`, `bin/control_room_ui/timeline.js`.
- **T5.2:** `bin/agent_propose.sh`, `bin/run_*_cc.sh` and every runner, `bin/contract_exec.py`,
  `bin/workflow_receipt.py` (no schema change; `consumption` is read leniently, formalising it is
  T5.4/T5.2's), `profiles/`.
- **T5.4:** entries in `design/benefit-ledger.toml` (the file is created empty here).
- Every workflow timer: no enable/disable/start/stop, no `systemctl` call in tests (fixtures only).
- `~/.config/**`, `~/.ssh`, `~/vault`, `~/agent-worktrees` — never read; the fixture repo root is
  this checkout and the fixture receipts root is under `tests/fixtures/`.
- `.claude/briefs/current.md` — not written, not archived (orchestrator instruction).
- No manifest entry for `control-room` (§ Notes); no `config/fleet-units.tsv` change.
- `tailscale serve`, TLS, auth headers, any public bind.

## Notes / preconditions

- **Depends on** T5.1 (landed 2026-09-11: receipt shape). T5.2 is an **evidence** dependency (first
  live receipt), not a land dependency — the screen lands rendering `unavailable` honestly.
- **Complete option taken** (no MVP): all three views + workflow + run pages, all listed fields,
  lineage, benefit, cadence-derived freshness, both control stubs, hosting unit — one land.
- **SSR in Python, not an SPA:** the rendered-view tests then live in the same `unittest` suites as
  the read model, need no node/jsdom, and the page tells the truth with JS off; the JS files are
  enhancement only. A bundler would add a network step at deploy, which the constraint forbids.
- **System scope, `User=dave`:** matches `qmd-mcp`/`brave-mcp`, needs no linger, can order after
  `tailscaled.service`, and sits next to T5.3a's root broker in the same manager. Cost: the install
  is sudo, land-time only.
- **Bind the Tailscale address, not loopback + `tailscale serve`:** serve's config lives in
  tailscaled, outside the repo and the drift check; a loopback bind would let every agent process
  on the box reach the screen (and later the control endpoints). The wrapper resolving the address
  at start keeps the unit free of a hardcoded IP.
- **`ProtectHome=read-only`** makes "read-only" a kernel fact for the hosting process, not a code
  review claim; `PYTHONDONTWRITEBYTECODE=1` because `bin/` is under `$HOME`.
- **No manifest entry for the screen:** it is an operator surface, not a standing workflow; an
  entry would make it 32 entries / 31 logical and a row in its own portfolio, breaking T5.2's and
  this brief's 31→30 gates. `design/fleet-suites.toml`'s old sentence saying otherwise is rewritten.
- **Twelve paused units → eleven paused rows** in the fixture, because `augustus-content` owns two
  of the twelve timers; the test asserts both numbers so the two-trigger fold is visible in the
  paused count too. Live, the disabled count is whatever `systemctl list-unit-files '*.timer'` says
  (24 of the manifests' 25 system timers on 2026-09-14) — never written into a test.
- **Stale-input is a heuristic over free text** (receipt `reason`, failed assertion ids) because no
  receipt field types the cause yet; the row says so. Typing it is T5.2/T5.4's schema decision.
- **`failed` rows still show for paused workflows** (with a `paused` chip): DoD item 7 makes "no
  valid artifact / last run failed" the input to a resume-or-retire decision, so hiding it while
  paused would hide the decision. Paused itself is never a row; cadence-derived kinds are suppressed.
- **Benefit ledger in `design/`** because the Control Room reads and the repo writes; the ledger is
  T5.4's decision record, not a second contract schema (one file, one `[[workflow]]` per id).
- **Freshness threshold `2 × cadence + 1 h`:** one missed fire is a miss, two is stale; the hour
  absorbs `RandomizedDelaySec`. Monthly `bd-followup-drafts` therefore reads stale after ~2 months.
- **Recursive bin drift check** is the smallest change that makes `bin/control_room_ui/` owned by
  the gate; `__pycache__`/`*.pyc` excluded on both sides to match `bin/deploy`'s rsync excludes.
- **`--timestamp=utc`** removes the CEST/UTC normalisation trap recorded in `~/CLAUDE.md` §
  Debugging — the reader receives UTC and every rendered time is UTC with a `Z`.
- **`git remote`** is `https://github.com/Dave1524/Hermes_Agent_Workforce_Praetorium.git`; the
  contract GitHub link uses that path on `main`.
- Python 3.11+ (`tomllib`) on the box (3.14) and CI; stdlib only; no new dependency.
- No timer is touched; the only `systemctl` in this brief is the land-time `enable --now` of the
  screen, run by Dave with sudo.
