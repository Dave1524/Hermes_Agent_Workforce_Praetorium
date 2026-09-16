# Brief: T5.3e — Production Control Room frontend (the Figma prototype, wired)

**Date:** 2026-09-15, refreshed 2026-09-16 (T6.1 landed; every anchor re-verified — see § Refresh)   **Verify:** `bash bin/verify.sh` from the repo root (includes
`bin/check_deploy_drift.sh`; extra gates and smoke: none — see § Land-time steps for why the gate is
red on the branch and green only after `bin/deploy` + a service restart).

**Size:** L. **Standing constraint (Dave, 2026-09-14):** the scheduled fleet is OFF except what Dave
has resumed from the screen (MEASURED 2026-09-16: `workflow-incidents.timer` only — `knowledge-digest`
was paused from the screen 2026-09-15 10:34Z, receipt `20260915T103402Z-pause-eb964f`; enumerate
with `systemctl list-timers --all`, never trust this line). No step in this brief enables,
starts, stops, pauses or resumes any workflow timer. Every control-path acceptance step below is a
**preview** or a **refusal** — neither touches live state. The one restart is `control-room.service`.

**Order:** T6.1 landed 2026-09-16 (PR #43, `c85ae37`) — nothing blocks this card. Source of
acceptance: `docs/dev-plan-2026-09.md` T5.3e (card at :539).

## Acceptance criteria

1. `GET /` → 302 `/app/`; `/app/` and every client route (`/app/workflows`, `/app/workflows/<id>`,
   `/app/runs/<id>`, `/app/incidents`, `/app/usage`, `/app/activity`) answer 200 `text/html` with the
   full `HTML_HEADERS` set (CSP, `X-Frame-Options: DENY`, `Cache-Control: no-store`); HEAD carries no
   body. The T5.3 SSR pages (`/exceptions`, `/portfolio`, `/benefit`, `/workflows/<id>`,
   `/runs/<id>`) and `/static/<name>` still answer exactly as today.
2. **CSP is unchanged** — `default-src 'self'; img-src 'self' data:; frame-ancestors 'none';
   base-uri 'none'` (`bin/control_room_api.py:770`) — and the SPA runs under it: the committed
   `index.html` references only `/app/assets/…`, contains no inline `<script>` or `<style>`, no
   `http://`/`https://`; fonts are self-hosted woff2 under `/app/assets/`. At land, zero CSP
   violations in the browser console on all seven routes.
3. **The build is committed, stamped, and gate-checked without Node.** `bin/control_room_ui/app/`
   holds `index.html`, `assets/app.js`, `assets/app.css`, the woff2 files and `BUILD.json`
   `{"schema":1,"source_sha256":"…"}`. `tests/test_control_room_spa.sh` recomputes the hash over
   `git ls-files --cached --others --exclude-standard -z ui/control-room` (path + bytes, sorted) and
   fails when it differs. File names are fixed (no content hashes), so a rebuild never changes
   membership of the `bin/` tree and never forces `bin/deploy --prune`.
4. **Where Node and `ui/control-room/node_modules` exist** the same test also runs `npm run
   typecheck`, `npm test`, and a rebuild into a temp `outDir` that must be byte-identical
   (`diff -r`) to the committed output. Otherwise it prints one `SKIP:` line for that half and the
   stamp check still runs. CI installs Node 22 + `npm ci` before `verify.sh`, so CI runs the full
   path and **no** line is added to `tests/ci-expected-skips.txt`.
5. **One row per logical workflow** on `/app/workflows` (`augustus-content` once with both
   triggers in its expander); the count equals `len(items)` of `/api/v1/workflows` (31 MEASURED
   2026-09-16, after T6.1 retired memory-consolidation; 32 the day before — read the API, not
   this number). No client-side grouping: the API already
   reconciles.
6. **Exception-first landing survives:** `/app/` (Overview) leads with "Needs attention" rendered
   from `/api/v1/exceptions` `items` in the API's `kind` order (`failed, stale-input,
   missing-artifact, missed-cadence, overdue-next-action, unconsumed-output`) plus `dataQuality`
   rows; each row links to its workflow page. Open incidents are on `/app/incidents`, not here.
7. **Missing data renders `Unknown`/`unavailable`, never a fake value.** A `{status:
   "unavailable"}` measurement renders the `Unavailable` component (tooltip: "Runtime did not
   provide trustworthy usage data"); `null` renders `Unknown`; a measured `0` renders `0`. Sums
   (usage totals, chart series) include measured rows only and say how many were excluded.
8. **Vocabularies are the API's**, mapped once in `src/model/` and nowhere else: health
   `healthy|running|incomplete|failed|paused|unknown` (the prototype's `attention` is gone);
   terminal outcome `artifact|decline|failed|skipped` (+ `running` from a live trigger state);
   control state `paused|active|running|unknown`; benefit decision `Keep|Improve|Retire|Unknown`
   with **four separate** consumption counters, never summed.
9. **Controls speak T5.3a exactly** (`bin/control_room_control.py:255-285`): `POST
   /api/v1/control/actions` with `X-Control-Room: 1`; button enablement and disabled-reason come
   from `control.actions[]`; resume is two-stage (preview → implication shown → apply with
   `preview_token`); stop requires a reason and sends `confirm: true`; retry sends `retry_of`;
   a `trigger_required` refusal offers `choices` and resends with `trigger`. Every response renders
   the receipt (`result`, `before`/`after`, `next_scheduled_run`, `run_id`, `links`) or the refusal
   `{code, message}`; the page re-fetches the workflow and redraws `control`. 400/403/404/500/502/
   503/504 are visible states.
10. **Proposals speak T5.3b exactly** (`bin/control_room_proposals.py:65-158`): one endpoint,
    `stage ∈ preview|submit|list`; schedule sends `proposed{on_calendar[], randomized_delay_sec,
    persistent, trigger}`, retire sends `reason` + `proposed{artifact_retention{receipts, notion,
    inbox, note}, acknowledge_pinned_tests}`; preview renders `summary`, `diff`, `checks[]`,
    `residue`, `submit_blockers[]`; "Open pull request" is enabled only when `submit_allowed`
    (or pinned-only blockers are acknowledged, as `proposals.js:191-249` does); submit renders
    `pr.url`; `stage:"list"` renders the workflow's existing proposals.
11. **Nothing is faked.** Dropped from the prototype: recent-output Approve/Reject/Edit/Send/
    Assign/Archive (T5.4), incident Acknowledge and the "acknowledged" tab (no endpoint; T5.3c is
    CLI `declare|resolve`), the DEMO pill, the fake refresh, every hardcoded count/date/run id.
    The handoff timeline renders only when a run carries `parentRunId`/`handoff`; otherwise the
    block reads `Unknown — no handoff telemetry (T5.3d)`.
12. Verify green after land; the Python suites and the SPA suite green on the branch; drift red on
    the branch is explained by exactly the files this brief adds or changes under `bin/`.

## Existing state (read 2026-09-15; anchors re-verified 2026-09-16 — no `bin/control_room_*` file
changed in between)

**Backend** (`bin/control_room_api.py`, 1014 lines):
- Dispatch `_route` :862-923; `_route_page` :799-810 does `/` → 302 `/exceptions` with
  `Content-Length: 0` and no other headers; `/favicon.ico` → 204 (:806-808); SSR pages :809-840;
  `_static` :842-847 → `control_room_static.serve`; `_route_api_extra` :849-859 (contract text,
  `/api/v1/control/**` GET → 405); API ladder :876-920; unknown → JSON 404. No SPA fallback exists.
- Headers: `CSP` :770; `COMMON_HEADERS` :771 (`Cache-Control: no-store`, `X-Content-Type-Options:
  nosniff`, `Referrer-Policy: no-referrer`) on **every** `_send`; `HTML_HEADERS` :772 adds CSP +
  `X-Frame-Options: DENY`; `_html` :793-794. The 302/204 carry none of these.
- Static: `bin/control_room_static.py` `CONTENT_TYPES = {css, js, svg}` (:12), `serve()` :12-24
  refuses `/` or `\` in the name (:18), resolves and requires `path.parent == root` (:20-23) — flat
  directory only, no html/woff2. Static dir = `model.static_dir` (:230), default
  `<script dir>/control_room_ui`, CLI `--static-dir` (:989-990); `bin/control_room_serve.sh` passes
  none, so the live static dir is the **deployed** `~/agent-workforce/bin/control_room_ui`.
- Envelope `_envelope` :532-538 is camelCase: `{apiVersion, generatedAt, dataStatus, items}`.
  `dataStatus` :478-499: `manifests|contracts|receipts|systemd|benefitLedger` ∈
  `available|degraded|unavailable` + `errors{…, malformedReceipts[{path,errors}]}`.
- `/api/v1/workflows` item (:445-476): `id, name, owners[], owner, purpose, lifecycle
  (standing|spent|live|read-only from manifest status), health, manifestPaths[], contract{…}|null,
  contractStatus, contractError, triggers[{unit, scope, kind, surface, trigger, runner, route,
  systemd{service{…}, timer{name, activeState, enabledState, lastTriggerAt, nextRunAt,
  persistent}|null, status, errors[]}, state ∈ running|active|paused|unknown, cadence{status,
  seconds, source, spec, persistent, randomizedDelaySec}}], lastRun (run summary|null),
  latestOutput, usage{status, input_tokens, output_tokens, cache_tokens, total_tokens}`
  **(snake_case)**, `cost{status, amount, currency, source, confidence}` **(snake_case)**,
  `receiptCount, cadence, lastValidArtifact{runId, endedAt, ageSeconds, uri, title, kind}|null,
  artifactFreshness ∈ current|stale|unknown, control{state, source, nextRunAt, nextRunEstimated,
  lastTriggerAt, persistent, lastAction, actions[{id ∈ pause|resume|run_now|retry|stop, enabled,
  reason}]}, links{contractLocal, contractGithub, devPlanTracker, devPlanDoc, taskIds[]},
  benefit{workflowId, decision, baseline, eligibleRuns, validArtifactRate, latencySeconds,
  consumption{status, opened, approved, sent, marked_useful, artifactRuns}, manualMinutesAvoided,
  decidedAt, decidedBy, evidence}, eligibleRuns, validArtifactRate, incompleteRuns[], lineage[{stage
  ∈ source|selection|trigger|agent|output|human_action, value, source}]`. Query params
  `health|agent|lifecycle|q` (:541-554); `lifecycle=all` includes non-standing.
- Run summary `_run_summary` :508-530: `{id, workflowId, unit, agent, model, startedAt, endedAt,
  outcome ∈ artifact|decline|failed|skipped, reason, artifact, stateChange, assertions[{id, status ∈
  passed|failed|not_applicable, …}], usage, cost (raw receipt objects, snake_case), nextAction,
  parentRunId, handoff, receiptPath}`. `/api/v1/workflows/<id>` and `/runs/<id>` put the single
  dict in `items`. There is **no** `/api/v1/runs` list.
- `/api/v1/overview` :702-728: `{apiVersion, generatedAt, dataStatus, summary{workflows, healthy,
  running, failed, incomplete, needAttention, paused, unknown, incompleteRuns}, needsAttention[],
  recentOutputs[≤10 run summaries with artifact], agentUsage[]}`. No per-day series exists.
- `/api/v1/exceptions` :641-663: rows `{kind, workflowId, owner, issue, failedAssertions[],
  requiredAction, evidence{runId, artifactUri}, paused, since, alsoFailed}` in `KINDS` order
  (`control_room_exceptions.py:20`), plus top-level `dataQuality[]`.
- `/api/v1/incidents` :613-637: `{id, status ∈ open|resolved, class, key, severity, workflowId,
  agent, issue, failedAssertion, requiredAction, runId, evidence, firstSeen, lastSeen, resolvedAt,
  notifiedAt, observations}` + `dataStatus.incidentState`. Classes/severity:
  `workflow_incidents.SEVERITY` (:36-44). **No ack endpoint.**
- `/api/v1/usage` :665-696: `{agent, runCount, usage{status, inputTokens, outputTokens,
  cacheTokens, totalTokens}, cost{status, amount, currency}}` **(camelCase here)**.
- `/api/v1/benefit` :698-700 (items = benefit rows); `/api/v1/activity` :730-744 (`{id, time, type
  "run", actor, event, runId, status}`); `/api/v1/health` :746-760 (`{status ok|degraded, …}`,
  503 when manifests fail); `/api/v1/workflows/<id>/contract` → `text/plain` markdown.
- Controls `bin/control_room_control.py`: `handle_post` :255-285; header check :256; `validate_shape`
  :209-214; `FORWARDED_KEYS` :35 `(workflow_id, action, reason, stage, preview_token, trigger,
  confirm, retry_of)`; response `{receipt, control, [preview{implication, preview_token}],
  [error]}` :278-285; `_status` :241-247 (`applied|previewed` 200, `refused` → `HTTP_STATUS_BY_CODE`
  :34, `failed` 500); broker down 502 / timeout 504 :272-277; `peer_allowed` :54-63 (loopback bind
  allows all; non-loopback bind refuses loopback and same-host peers — a Mac over Tailscale passes).
  Broker contract `bin/control_broker.py`: receipt keys :61-66, refusal codes :38-43, `stop` needs
  `confirm` + reason :554-572, resume preview token TTL 600 s :575-588, `trigger_required` with
  `choices` :528.
- Proposals `bin/control_room_proposals.py`: `handle_post` :123-158; shape :65-80 (`kind ∈
  schedule|retire`, `stage ∈ preview|submit|list`, `workflow_id ~ ^[a-z0-9][a-z0-9-]{0,63}$`);
  `FORWARDED_KEYS` :27; refusal shape `{error{code, message, choices, diff}, record}` :119-120;
  `_status` :110-116. Worker responses `bin/workflow_pr.py`: preview :267-270 `{stage, proposal_id,
  preview_token, expires_at, base, branch, summary, description, files[], diff, diff_sha256,
  checks[], residue{source, live}, retention, submit_allowed, submit_blockers[]}`; submit :304
  `{stage:"submitted", proposal_id, pr{url, number, branch, draft}, diff_sha256}`; `list` :117-118.
  Every response also carries `record` and a fresh `control`. Preview TTL 1800 s
  (`bin/workflow_pr_record.py:19`).
- Reference JS: `bin/control_room_ui/actions.js` (`post()` :38-54, `redraw()` :56-74, resume
  :91-101, stop :103-108, trigger picker :110-123, retry :131-147) and `proposals.js` (forms
  :124-151, `runPreview` :191-219, `submit` :249-269, `renderList` :93-111, `proposed` shapes
  :153-163). The SPA reproduces these flows; it does not import them.

**Prototype** (`ui/control-room-prototype/`, 20 files, 2391 lines, one commit `fe80764`):
- Navigation is `useState` only (`src/App.tsx:30-41`); no router, no URL, no `fetch`, no
  `useEffect` anywhere. Pages: Overview, Workflows, WorkflowDetail (`workflowId` prop), Incidents,
  Usage, Activity; no run-detail page.
- All data from `src/data.ts` (types :1-65: `Health` includes `attention`; `Workflow` has
  preformatted `tokens`/`cost` strings, `notionUrl: "#"`) and per-page constants (`MOCK_RUNS`
  `WorkflowDetail.tsx:293-307`, `LINEAGE_STAGES` :309-338, `ACTIVITY_LOG` `Activity.tsx:3-16`) plus
  literal numbers in JSX (`Overview.tsx:29-33`, `Usage.tsx:43`, `WorkflowDetail.tsx:150-153,
  212-214`, `Dialogs.tsx:185`).
- `src/components/Dialogs.tsx` (252 lines): seven dialogs, one shared `reason` state, `handle()`
  :17-24 simulates with `setTimeout(800)`; Schedule dialog discards its `proposed` input (:49, :222).
  `HealthBadge.tsx:3-11` maps seven health values; crashes on an unknown one (:17).
- `src/index.css:1-2` imports Inter and JetBrains Mono from Google Fonts — blocked by CSP.
  `@theme inline` tokens :5-29 are the palette; chart hex literals also sit in
  `Overview.tsx:100-115` and `Usage.tsx:105-123`.
- Inline `style=` in three places (`Workflows.tsx:153`, `WorkflowDetail.tsx:158`, `Usage.tsx:115`)
  and recharts `wrapperStyle` — all React style props, set through CSSOM, which CSP's `style-src`
  does not govern. No `dangerouslySetInnerHTML`, no `@/` imports (alias declared, unused).
- `vite.config.ts` has no `base`, no `outDir`, no proxy; `tsconfig.json` has `strict`, `noEmit`,
  no `noUnusedLocals`; `package.json` has no lockfile, no `test`/`typecheck` script; `.gitignore`
  = `node_modules/`, `dist/`.
- Spec the prototype was generated from: `src/imports/pasted_text/praetorium-control-room.md`
  (287 lines; the data-semantics rules at :75-76, :82, :106, :117-124, :164-170, :219-237).

**Deploy, drift, gate, CI, Node:**
- `bin/deploy:20` `PATHS=(bin profiles docs CLAUDE.md AGENTS.md README.md config systemd skills)`;
  rsync `-a` :57-60 recurses, so `bin/control_room_ui/` and anything under it ships; no extension
  filter, no size filter; `--prune` = `--delete` :63; post-check `check_deploy_drift.sh --scope
  bin` :101-107. `ui/` is not shipped and stays that way.
- `bin/check_deploy_drift.sh:358-375` compares `bin/` **recursively** by relative path and bytes;
  the bin half consults no exclusion list, so a runtime-only file under `bin/` is red until
  `--prune`. `tests/test_deploy_drift.sh:841-866` pins `PATHS` and `CONTENT_TREES` at exactly 9
  entries — unchanged by this brief.
- `bin/verify.sh`: shellcheck over top-level `bin/*` (`.sh` or shell shebang) + `tests/*.sh`; drift
  (hard fail, :53); every `tests/*.sh` (rc 0 or 77; `SKIP:` lines collected). Nothing touches `ui/`.
  Skip convention: `tests/box_precondition.sh:36-45`; CI diffs `SKIP:` lines against
  `tests/ci-expected-skips.txt` (`.github/workflows/verify.yml`, `ubuntu-latest`, no Node step).
- Node on the box: `/home/linuxbrew/.linuxbrew/bin/node` v26.8.2, npm 11.19.1 (also `/usr/bin/node`
  from apt). No `node_modules`, no `dist` anywhere under `ui/`.
- Tests: `tests/control_room_fixture.py` (`build_model()` :71-80 over the real checkout +
  `FakeSystemd`, `serving(model)` :83-93 on loopback); `tests/test_control_room_views.py`:
  `ExceptionsDefault` :102-114 asserts the 302 target is `/exceptions`; `StaticFailsClosed` :232-256;
  `test_pages_reference_only_self_hosted_assets` :251-256; headers :262-266; HEAD :270-274;
  `STANDING_ENTRIES = 32`, `LOGICAL_WORKFLOWS = 31` :29-30 (set by T6.1, MEASURED 2026-09-16). Suite
  registry `design/fleet-suites.toml` :307-343 (asserts `control-room-static-fails-closed` :335,
  `control-room-html-headers` :336), with `(::id)` anchors as comments on the test classes. The
  `control-room-30-of-31` comment at :326 still reads "31 standing entries render as exactly 30
  Portfolio rows" — the 2026-09-10 baseline, two retirements stale.
- Runbook: `docs/runbook.md` § Control Room :228-270 (restart after deploy :242; drift note
  :265-269), § controls :271, § proposals :363. No section on the frontend build.

## Architecture decisions (complete option; reasons once)

1. **Committed build, fixed names, stamped.** No Node at deploy or run time (rsync ships bytes; the
   service reads the deployed tree). Fixed names because every static response is already
   `no-store` and hashed names would turn every rebuild into a `--prune`. The stamp makes "source
   edited, build not" a red gate on any machine.
2. **`/app/` prefix, path routing, `/` → `/app/`.** Prefix avoids colliding with the SSR
   `/workflows/<id>`; path routing (not hash) gives Dave bookmarkable URLs; the server fallback is
   one rule. SSR stays as the no-JS fallback; retiring it is a later card.
3. **CSP untouched; fonts self-hosted** via `@fontsource-variable/inter` + `@fontsource/jetbrains-mono`
   (latin subsets) so the design's typography survives without a `font-src` change.
4. **Schema-first API layer, mappers as the tested core.** Zod schemas per endpoint, `z.infer`
   types; one client that parses the envelope and never lets a raw response reach a page; pure
   mappers own every vocabulary translation. Pages are dumb over view models.
5. **No new runtime dependencies beyond `zod` and the two font packages.** Router is a small hook;
   dialogs are plain `<dialog>`/React; no react-router, no query library, no UI kit — the prototype
   already carries its own primitives and the palette.
6. **Exceptions lead the Overview**; incidents get their page. The T5.3 test anchor
   `control-room-exceptions-default` is retargeted, not deleted.
7. **One backend read-model addition** (`overview.reliability7d`) because the chart needs a per-day
   series and only the model has the runs; everything else the screen needs already exists.
8. **Drop, don't fake** (acceptance 11). A button with no backend is a lie in an operator surface.

## Views (fields are the contract; every value from `/api/v1/*` via a mapper)

**Shell** (`src/App.tsx`): sidebar Overview / Workflows / Incidents / Usage / Activity (active state
from the route); header shows the route title, a Refresh button (re-fetches the current page's
resources), an auto-refresh toggle (60 s, `localStorage["control-room.auto-refresh"]`, parity with
`app.js:5-30`), and `generatedAt` of the last successful fetch. Footer: `/api/v1/health` →
`ok` / `degraded` / `unreachable` (fetch failed or 503) with the source errors on hover; never
"Connected · healthy" as static text. A `DataStatusStrip` under the header renders any
`dataStatus` source that is not `available`, naming its errors.

**Overview** (`/app/`): status cards from `overview.summary` (`workflows, healthy, running,
incomplete, failed, paused, unknown, incompleteRuns`); **Needs attention** = `/api/v1/exceptions`
rows in API order (severity colour by `kind`; `paused` rows carry the paused chip; `alsoFailed`
listed; `evidence.runId` → `/app/runs/<id>`, row → `/app/workflows/<id>`) followed by `dataQuality`
rows; empty state "No exceptions"; **7-day reliability** bar chart from `overview.reliability7d`
(`unavailable` → the Unavailable block, not an empty chart); **Agent usage** from
`overview.agentUsage` (measured rows numeric, else Unavailable; total row says "n of m measured");
**Recent outputs** from `overview.recentOutputs` (workflow, artifact title/kind, `endedAt`, outcome
badge, `Open` → `artifact.uri` in a new tab, `Run` → `/app/runs/<id>`).

**Workflows** (`/app/workflows`): one fetch of `/api/v1/workflows`; client-side filters health /
owner / lifecycle / text over the loaded list (options derived from the data, not hardcoded);
columns Workflow, Owner, Purpose, Health, Last run (`lastRun.endedAt` relative + absolute title),
Next run (`control.nextRunAt`, "estimated" suffix when `nextRunEstimated`), Latest output
(`lastValidArtifact.title` + `artifactFreshness` chip), Reliability (`validArtifactRate` bar; `null` →
Unknown), Tokens (`usage`); trigger expander lists `triggers[]`: unit, kind, `cadence.spec`
(or Unavailable + error), timer `enabledState`/`activeState`, `persistent`, `nextRunAt`.

**Workflow detail** (`/app/workflows/<id>`): `/api/v1/workflows/<id>` + `/workflows/<id>/runs` +
`/workflows/<id>/contract` (text, collapsed). Header: owner avatar, name, health badge, purpose, the
contract sentence from `contract.trigger / artifact / beneficiary / next_action` (each `Unknown` when
absent — never the prototype's fixed "for Dave, so he can act on it promptly"); control buttons
Pause / Resume / Run now / Retry / Stop with `enabled` and `title=reason` from `control.actions[]`;
overflow: Change schedule, Retire. Cards: Last run, Next run, Valid-artifact rate, Eligible runs,
Tokens, Cost. Sections: Triggers (as the expander); Latest output (`lastValidArtifact`, freshness,
`Open`); Recent runs (`id`, outcome badge, `startedAt`→`endedAt` duration, assertions
`passed/failed/n.a.` counts with failed ids named, tokens, cost, artifact link, row →
`/app/runs/<id>`); Benefit (`benefit.decision`, baseline, latency, `consumption` as four labelled
counters or Unavailable, `evidence`); Lineage (`lineage[]` six stages, `value` + `source`, Unknown
when null); Links (contract local/GitHub, dev-plan tracker/doc, task ids); Proposals (`stage:"list"`
for both kinds). Control result panel renders the last receipt/refusal verbatim-structured (not raw
JSON), with the HTTP status.

**Run detail** (`/app/runs/<id>`, new): `/api/v1/runs/<id>` — workflow link, unit, agent, model,
started/ended, outcome, reason, artifact (uri/title/kind), `stateChange`, assertions table (id,
status, output), usage, cost, `nextAction`, and the handoff block: `parentRunId` link + `handoff`
timeline when present, else `Unknown — no handoff telemetry (T5.3d)`.

**Incidents** (`/app/incidents`): tabs Open / Resolved with counts from `status`; card per incident
(severity from `SEVERITY[class]` via the item's `severity`, class, workflow → `/app/workflows/<id>`,
agent, issue, `failedAssertion`, `requiredAction`, first/last seen, `observations`, `runId` →
`/app/runs/<id>`, `notifiedAt`, `resolvedAt`); `dataStatus.incidentState` unavailable → the
Unavailable block; the Buzz-rules notice stays static text.

**Usage** (`/app/usage`): `/api/v1/usage` table (agent, runs, input, output, cache, total, cost;
unavailable → one Unavailable cell spanning the numeric columns); chart over measured agents only
with "n of m agents measured"; per-workflow table from `/api/v1/workflows` (`usage.total_tokens`,
`cost.amount`, `validArtifactRate`).

**Activity** (`/app/activity`): `/api/v1/activity` items in delivered order (time, actor, event,
`runId` → `/app/runs/<id>`, status chip). No handoff block unless an item carries one.

**Dialogs** (one file each under `src/components/dialogs/`): Pause (info: current run finishes;
apply), Resume (preview → show `implication` and `catch_up_fired` risk → Apply with `preview_token`;
token expiry surfaces as the broker's refusal), Run now (shows `run_id` and `next_scheduled_run`
from the receipt), Retry (disabled with `reason` when `control.actions.retry.enabled` is false;
sends `retry_of: lastRun.id`), Stop (reason required, destructive, `confirm: true`),
TriggerPicker (rendered on `trigger_required`, resends with `trigger`), Schedule (fields:
`on_calendar[]` lines, `randomized_delay_sec`, `persistent` tri-state, `trigger` select from
`triggers[]`; Preview → diff/checks/residue/blockers → Open pull request), Retire (reason,
`artifact_retention` four fields, `acknowledge_pinned_tests` checkbox shown only when the blockers
are pinned-test-only; Preview → Create retirement PR).

## HTTP surface (additions; nothing removed)

- `_route_page`: `/` → 302 `/app/`. `GET|HEAD /app` and `/app/<anything>` **except**
  `/app/assets/<name>` → 200 `index.html` bytes from `<static_dir>/app/index.html` with
  `HTML_HEADERS`; 404 JSON when the file is missing (the runtime tree was deployed without a build).
- `/app/assets/<name>` → `control_room_static.serve_app_asset(static_dir, name)`: root
  `<static_dir>/app/assets`, MIME `{css, js, svg, woff2 → font/woff2}`, same `/`/`\` refusal, same
  `parent == root` guard, `COMMON_HEADERS`.
- `overview()` gains `reliability7d`: `{status: "measured", days: [{day: "YYYY-MM-DD", eligible: n,
  valid: n}] × 7 ending today (UTC)}` counting runs by `endedAt` day with `outcome ∈ {artifact,
  decline, failed}` as eligible (`skipped` excluded) and `artifact` as valid; `{status:
  "unavailable", days: []}` when `dataStatus.receipts == "unavailable"`. Zero runs on a day is a
  measured `0`.

## Files to modify

- `bin/control_room_api.py` — `_route_page` (302 target, `/app` fallback), `_route` (asset branch
  before the API ladder), `overview()` (`reliability7d`), `--static-dir` help text.
- `bin/control_room_static.py` — `CONTENT_TYPES` gains `woff2`; `serve_app_asset()` and
  `serve_app_shell()` beside `serve()`, sharing one `_resolve_inside(root, name)` guard.
- `tests/test_control_room_views.py` — `ExceptionsDefault` → `/app/`; `StaticFailsClosed` gains the
  `/app/assets` matrix; new `SpaShell` class; keep every existing SSR assertion.
- `tests/test_control_room_api.py` — `reliability7d` measured/unavailable cases.
- `design/fleet-suites.toml` — reword `control-room-exceptions-default`; extend
  `control-room-static-fails-closed`; add `control-room-spa-shell`, `control-room-overview-reliability`;
  new `[[suite]]` for `tests/test_control_room_spa.sh`; while there, the `control-room-30-of-31`
  comment (:326) states the counts as "the two constants in `tests/test_control_room_views.py`"
  instead of numbers, so the next retirement cannot stale it again (id unchanged).
- `.github/workflows/verify.yml` — `actions/setup-node@v4` (node 22, cache npm with
  `ui/control-room/package-lock.json`) + `npm ci --prefix ui/control-room` before the gate.
- `docs/runbook.md` § Control Room — `/` lands on `/app/`; SSR paths listed as fallback; new
  "Frontend build" subsection (rebuild command, what `BUILD.json` is, deploy + restart, `--prune`
  only if a file is removed from the build); fix the stale :260-263 "501 until T5.3a/b" sentence.
- `CLAUDE.md` — the `control-room.service` bullet (:142) names `ui/control-room/` as source and
  `bin/control_room_ui/app/` as its committed build; `README.md` — add `ui/` to "What this repo
  holds".
- `docs/dev-plan-2026-09.md` — already carries the card; at land, the DONE line.
- `ui/control-room/` (renamed from `ui/control-room-prototype/` with `git mv`):
  `vite.config.ts` (`base`, `build.outDir/emptyOutDir/rollupOptions.output` fixed names,
  `sourcemap: false`, `server.proxy` from `VITE_API_PROXY`), `tsconfig.json` (`noUnusedLocals`,
  `noUnusedParameters`, vitest types), `package.json` (deps + scripts; `format` may stay),
  `index.html` (title "Praetorium Control Room"), `src/index.css` (fontsource imports replace :1-2;
  tokens unchanged), `src/main.tsx`, `src/App.tsx` (shell + route switch), every `src/pages/*.tsx`
  (data via hooks; hardcoded literals removed), `src/components/HealthBadge.tsx` (API vocab; unknown
  value → the `unknown` config, never a crash), `README.md` (rewritten: what it is, dev loop with the
  loopback API, rebuild, what ships, what is dropped and why), `.gitignore` unchanged.

## Files to create

- `bin/control_room_build_ui.sh` — the only rebuild path: refuses Node < 22; `npm ci` when
  `node_modules` is absent (or `--ci` always); `npm run typecheck && npm test && npm run build`;
  writes `bin/control_room_ui/app/BUILD.json` from `bin/control_room_ui_stamp.sh` (below); prints
  the changed files under `bin/control_room_ui/app/`. No timestamps, no Node version in the stamp.
- `bin/control_room_ui_stamp.sh` — prints the source hash: `git -C <repo> ls-files -z --cached
  --others --exclude-standard ui/control-room | sort -z | while read -d '' f; do printf '%s\0' "$f";
  cat "$f"; done | sha256sum`. One owner for writer (build) and reader (test).
- `bin/control_room_ui/app/` — `index.html`, `assets/app.js`, `assets/app.css`, `assets/*.woff2`,
  `BUILD.json` (build output; committed).
- `tests/test_control_room_spa.sh` — `(::control-room-spa-build)`: stamp check + `index.html`
  hygiene (only `/app/assets/` refs, no inline `<script>`/`<style>`, no `http`); Node half
  (typecheck, vitest, rebuild-diff) or the `SKIP:` line. Uses `assert()` scoping as the sibling
  suites do (the `pipefail`/early-reader rule in `CLAUDE.md` § Verification).
- `ui/control-room/package-lock.json`.
- `ui/control-room/docs/spec.md` — `git mv` of `src/imports/pasted_text/praetorium-control-room.md`.
- `ui/control-room/vitest.config.ts` (jsdom, `setupFiles` with jest-dom).
- `ui/control-room/src/router/useRoute.ts` + `useRoute.test.ts`; `routes.ts` (parse/build the seven
  routes; unknown → Overview with a notice).
- `ui/control-room/src/api/schemas/` — one file per endpoint: `envelope.ts`, `dataStatus.ts`,
  `measurement.ts` (`{status: measured|unavailable, …nullable}`), `workflow.ts`, `run.ts`,
  `overview.ts`, `exceptions.ts`, `incidents.ts`, `usage.ts`, `benefit.ts`, `activity.ts`,
  `health.ts`, `control.ts` (request + response + receipt + refusal), `proposals.ts` (request,
  preview, submitted, list, refusal). Schemas are lenient on unknown keys (`.passthrough()` or
  default object mode) so a backend addition never breaks the screen.
- `ui/control-room/src/api/client.ts` + `client.test.ts` — `getJson(path, schema)`,
  `getText(path)`, `postControl(body)`, `postProposal(body)`; the header, envelope parse, and an
  `ApiError {status, body}`; `fetch` mocked at the boundary.
- `ui/control-room/src/api/useResource.ts` — `{status: loading|ready|error, data, error, refresh}`
  with the auto-refresh tick; `fixtures.test-helpers.ts` — typed sample responses mirroring
  `tests/fixtures/control-room/` receipts (one workflow with measured usage, one unavailable, one
  paused, one failed assertion).
- `ui/control-room/src/model/` — `measurement.ts` (`measured|unavailable` → view value),
  `health.ts`, `outcome.ts`, `controlState.ts`, `workflowRow.ts`, `workflowDetail.ts`, `run.ts`,
  `exception.ts`, `incident.ts`, `usage.ts`, `benefit.ts`, `time.ts` (relative + absolute, UTC in
  the title), `tokens.ts` (`12.4K`/`1.2M` formatting, `null` passthrough) — each with a co-located
  test; `it.each` over vocabularies.
- `ui/control-room/src/components/` — `Unavailable.tsx`, `Unknown.tsx`, `OutcomeBadge.tsx`,
  `ControlStateChip.tsx`, `DataStatusStrip.tsx`, `AgentAvatar.tsx` (colour by owner name hash, not
  a fixed five-name map), `ReliabilityBar.tsx`, `FreshnessChip.tsx`, `ReceiptPanel.tsx`,
  `dialogs/{useControlAction.ts, useProposal.ts, PauseDialog, ResumeDialog, RunNowDialog,
  RetryDialog, StopDialog, TriggerPicker, ScheduleDialog, RetireDialog, DialogFrame}.tsx` with
  tests for the two hooks (fetch mocked) and for `ResumeDialog` (two-stage) and `ScheduleDialog`
  (submit gated on `submit_allowed`).
- `ui/control-room/src/pages/RunDetail.tsx`.

## Test plan (TDD; red first; anchors are the `(::id)` comments registered in fleet-suites)

Python (`tests/test_control_room_views.py`, `tests/test_control_room_api.py`):
- `control-room-exceptions-default` — `/` → 302 `/app/`; `/app/` body is the SPA shell **and** the
  shell's first route is Overview whose data source is `/api/v1/exceptions` (asserted grep-level on
  `assets/app.js` for the literal `/api/v1/exceptions`, the way `proposals.js` is asserted today).
- `control-room-spa-shell` — `/app`, `/app/`, `/app/workflows/x`, `/app/runs/y` → 200 `text/html`
  with the exact `HTML_HEADERS`; HEAD empty; `/app/../x` → 400; `index.html` `src`/`href` all start
  with `/app/assets/`; no `<script>` without `src`, no `<style>`, no `http`; missing shell file →
  404 JSON.
- `control-room-static-fails-closed` (extended) — `/app/assets/app.js` 200 `text/javascript`;
  `/app/assets/app.css` 200 `text/css`; `/app/assets/<font>.woff2` 200 `font/woff2`;
  `/app/assets/index.html` 404; `/app/assets/x/y.js` 404; `/app/assets/../index.html` 400/404;
  `/static/` matrix unchanged.
- `control-room-overview-reliability` — seven days, `eligible ≥ valid`, `skipped` not counted,
  a day with no runs is `0`, receipts unavailable → `{status: unavailable, days: []}`.
- Existing SSR/API assertions unchanged and green.

Bash (`tests/test_control_room_spa.sh`, `(::control-room-spa-build)`):
- stamp equals `bin/control_room_ui_stamp.sh` output; a temp edit of a source file (in a copied
  tree, not the checkout) flips it red; `index.html` hygiene as above; canary `yes | grep -q y`.
- Node half when `node` ≥ 22 and `ui/control-room/node_modules` exist: `npm run typecheck`,
  `npm test`, build into `$TMP/out` via `VITE_OUT_DIR` and `diff -r $TMP/out bin/control_room_ui/app`
  ignoring nothing; else `SKIP: test_control_room_spa.sh — the SPA toolchain (absent:
  ui/control-room/node_modules)` and exit 77 **only if** the stamp half passed.

Vitest (`ui/control-room/src/**/*.test.ts(x)`):
- mappers: every vocabulary value round-trips (`it.each`); `unavailable` → `Unavailable`, `null` →
  `Unknown`, `0` → `"0"`; usage totals exclude unavailable rows and report the excluded count;
  exceptions keep API order; lineage renders six stages with `Unknown` fill.
- client: header `X-Control-Room: 1` on POST; envelope parse failure → `ApiError`; 4xx/5xx →
  `ApiError` with body; schema `.passthrough()` tolerates unknown keys.
- router: parse/build for the seven routes; unknown path → Overview; `popstate` updates.
- hooks: `useControlAction` resume two-stage carries `preview_token`; stop refuses without a
  reason; `trigger_required` yields the picker state; `useProposal` gates submit on
  `submit_allowed` and forwards `preview_token`.
- components: `HealthBadge` on an unknown value renders `Unknown`; `Unavailable` tooltip text;
  `ResumeDialog` shows `implication` before Apply.

## Implementation steps (ordered; commit after each numbered group — the auto-sync sweep is 15 min)

1. `git mv ui/control-room-prototype ui/control-room`; move the spec; delete `src/data.ts` **last**
   (step 5) so each page swap is one commit. `package.json` deps/scripts, `vite.config.ts`,
   `tsconfig.json`, `vitest.config.ts`, `package-lock.json`, fontsource in `index.css`. `npm ci`.
2. Backend: `control_room_static.py` (+ tests), `_route_page`/`_route` (+ tests), `reliability7d`
   (+ tests), fleet-suites entries. Deploy is **not** run yet; drift red is expected on the branch.
3. `src/api/` schemas + client + `useResource` + fixtures (tests first), `src/model/` mappers
   (tests first), `src/router/`.
4. Shell + pages, read-only, one commit per page: Overview, Workflows, WorkflowDetail (without
   controls), RunDetail, Incidents, Usage, Activity. Each commit deletes that page's mock constants.
5. Delete `src/data.ts`; `HealthBadge` on the API vocab; `README.md` rewrite.
6. Dialogs + hooks (tests first); WorkflowDetail controls, proposals list, receipt panel.
7. `bin/control_room_ui_stamp.sh`, `bin/control_room_build_ui.sh`, first build committed under
   `bin/control_room_ui/app/`, `tests/test_control_room_spa.sh`, CI step. `bash bin/verify.sh`:
   everything green except drift under `bin/` naming exactly the new/changed files.
8. Docs: runbook, `CLAUDE.md`, `README.md`. Dev-plan DONE line waits for land.

## Land-time steps (sudo not needed; the branch cannot be drift-green before these)

1. Merge to `main` (fast-forward after the independent verify + review, per `/ship-dev-plan`).
2. `bin/control_room_build_ui.sh` on `main` → confirm `git status` clean (the committed build is
   already byte-identical; if it is not, the determinism assumption failed — stop and report, do not
   commit a second build).
3. `bin/deploy` (additive; no `--prune` unless the build removed a file) →
   `sudo systemctl restart control-room.service` → `journalctl -u control-room.service -n 20`.
4. From the Mac: `http://praetorium:8787/` lands on `/app/`. Acceptance, in this order, changing
   nothing: row count equals `/api/v1/workflows` `len(items)`; a workflow with no receipts shows
   `Unknown`/`unavailable` and no `0`; open the browser console — zero CSP reports across all seven
   routes; `knowledge-digest` (paused since 2026-09-15, `resume.enabled: true` on 09-16 — any paused
   row if that changed) → Resume → the preview renders `implication` → **Cancel**; a workflow
   whose contract does not declare retry idempotent → Retry is disabled with its `reason`; a
   `run_now` on a two-trigger workflow (`augustus-content`) → `trigger_required` picker → **Cancel**;
   Change schedule → Preview renders diff/checks/residue → **close without submitting**; Proposals
   list renders; `/exceptions`, `/portfolio`, `/benefit` still answer.
5. `bash bin/verify.sh` green (drift clean). Dev-plan DONE line + archive this brief; commit and
   **push by hand** (the sweep does not push a commit made on a clean tree).

## Out of scope / do not touch

- Retiring the SSR views (`bin/control_room_view_*.py`, `control_room_views.py`, `app.js`,
  `actions.js`, `proposals.js`, `app.css`, `proposals.css`) — follow-up card after a week of SPA use.
- The broker, allowlist, root-owned files, `peer_allowed`, the bind rule, auth, TLS.
- Any timer enable/start/stop/pause/resume; any `stage:"submit"`; any `stage:"apply"`.
- Incident acknowledge; output consumption actions (T5.4); handoff capture (T5.3d).
- `bin/deploy` `PATHS`, `CONTENT_TREES`, the drift check's tree list (`ui/` is not shipped).
- The `@theme` palette and layout — this is a wiring brief, not a redesign.

## Notes / preconditions

- Live logical row count MEASURED 2026-09-16: **31** (`/api/v1/workflows` on the Tailscale bind),
  32 standing entries (`tests/test_control_room_views.py:29-30`, set by T6.1). It was 32/33 on
  2026-09-15 and 30/31 at the plan's 2026-09-10 baseline — three values in six days, which is why
  the gate reads the API and the brief's numbers are dated. `overview.summary` on 09-16:
  `paused 22, unknown 8, running 1, healthy 0` — the Overview will open on a mostly-paused fleet,
  so the empty "No exceptions" state and the paused chip are the first things Dave sees.
- `ProtectHome=read-only` on the service is fine: it reads the deployed static dir; nothing writes.
- The dev loop is `python3 bin/control_room_api.py --host 127.0.0.1 --port 8788` (loopback bind →
  `peer_allowed` lets POSTs through; control/proposals answer 501 unless bound) and `npm run dev`
  with `VITE_API_PROXY=http://127.0.0.1:8788`. Against the live `:8787` from the box, POSTs are
  refused as same-host by design.
- Vite's production HTML carries `crossorigin` on same-origin tags — harmless under this CSP.
  If any inline script or style appears in the built `index.html`, that is a build-config defect to
  fix (`build.modulePreload.polyfill`, plugin injection), never a CSP loosening.
- Determinism risk: if the CI rebuild diff fails on a platform difference while the box build is
  stable, keep the stamp check as the gate everywhere and make the rebuild diff box-only — as a
  recorded finding in the PR, not a silent softening.
- Recharts is kept for the two charts; it is the largest dependency (~150 KB gz). Acceptable for a
  private single-operator screen; note the bundle size in the README after the first build.

## Refresh 2026-09-16 (what changed since 2026-09-15; the body above is already corrected)

- T6.1 landed (PR #43, `c85ae37`); the four persona profiles are deleted, D4 closed. Nothing blocks
  this card and nothing it touches was touched — `bin/control_room_*.py`, `bin/control_room_ui/`,
  `ui/control-room-prototype/` (still `fe80764`, 20 files, no `node_modules`/`dist`),
  `bin/deploy`, `bin/check_deploy_drift.sh`, `bin/verify.sh`, `.github/workflows/verify.yml` and
  `tests/ci-expected-skips.txt` (13 lines) are byte-identical to what the brief read.
- T6.1 retired `memory-consolidation`: 31 logical / 32 standing (was 32/33). Acceptance 5, the
  tests paragraph and § Notes carry the new figures, dated. The T5.3-era fleet-suites comment
  still says 30/31 — folded into the fleet-suites edit above.
- `knowledge-digest.timer` is no longer resumed (Dave paused it from the screen 2026-09-15
  10:34Z). Live resumed set on 09-16: `workflow-incidents.timer`. The land-time resume-preview
  step still targets `knowledge-digest`; it is paused with `resume.enabled: true`.
- Runbook shrank by 27 lines above the Control Room section (T6.1 step 9), so its anchors moved:
  § Control Room :228-270, § controls :271, § proposals :363, the stale 501 sentence :260-263.
  `design/fleet-suites.toml` control-room entries moved +1 (:307-343). Dev-plan card :539.
- `control-room.service` running since 2026-09-16 06:52 CEST; `/` still 302 `/exceptions`.
