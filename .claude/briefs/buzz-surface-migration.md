# Brief: Migrate scheduled job output from Discord to Buzz

**Date:** 2026-08-04

**Scope:** output-surface migration; systemd remains the scheduler/invoker

**Verify:** `bash bin/verify.sh` from `~/dev/agent-workforce`

## Decision record

**systemd stays the scheduler and invoker. Buzz becomes the delivery and triage
surface.** This is deliberately not a Buzz-native scheduler migration.

A Buzz workflow cannot currently wake an `--respond-to owner-only` agent:

- Workflow `send_message` events are signed by the relay keypair; the workflow owner is
  only a `p` attribution tag (`crates/buzz-workflow/src/action_sink.rs`).
- The ACP author gate accepts the owner or a cryptographically verified NIP-OA sibling
  and fails closed without an owner (`crates/buzz-acp/src/lib.rs`).
- The relay author is neither, and the attribution `p` tag does not mention the target
  agent. Author gating and mention gating therefore reject the event independently.
- `call_webhook` requires public HTTPS ingress and elevated owner/admin authority. No
  public ingress is being added.

Pin these claims to the deployed Buzz CLI/relay build during Phase 0. Upstream `main`
and the hosted relay may differ; source reading alone is not a deployment-version check.

## Scope inventory

There are **15 scheduled output producers**, not 13:

- **13 work-producing units:** `overnight-pre-snapshot`,
  `overnight-morning-report`, `praetorium-daily-plan`,
  `praetorium-eod-summary`, `agent-proposal`, `raw-ingest`,
  `knowledge-digest`, `weekly-pre-assembly`, `augustus-content`,
  `content-change-dispatch`, `bd-stall-radar`, `bd-followup-drafts`, and
  `m1-signal-scan`.
- **2 deterministic approval units:** `agent-inbox-sync` and
  `inbox-backlog-alert`.
- **1 on-demand failure producer:** `agent-alert@.service`.

All 13 work-producing units execute scripts from `/home/dave/agent-workforce`.
`agent-inbox-sync` is the one in-scope unit that executes from the source checkout.
`agent-workforce-auto-sync` also executes from source but is out of scope and silent.

Deterministic infrastructure timers remain on systemd and remain silent:
`qmd-refresh`, `ttm-pool-drain`, `local-tier-eval`,
`agent-workforce-auto-sync`, `memory-consolidation`, `sysstat-*`, `apt-*`,
`logrotate`, `man-db`, and `fwupd-refresh`.

## Authorship and credential boundary

Scheduled output is authored by a dedicated **Praetorium service identity**, not by a
role persona whose interactive Buzz runtime did not perform the work.

- Dave mints the identity through Buzz Desktop and captures its matching private key and
  NIP-OA auth tag. Never generate or register it on the box.
- Dave adds it as a member of all six destination channels and verifies it can publish a
  channel message, attachment, and NIP-01 note.
- Message content carries `job: <unit>` and `runtime: <actual runtime/profile>` so the
  logical producer remains auditable. A role such as Claudius or Augustus may be named as
  the role owner, but not as the cryptographic author.
- The service identity credential is loaded only by a delivery-only credential helper.
  Do **not** add its `EnvironmentFile` to any work-producing unit: service-level
  environment is inherited by `ExecStart`, which would expose the signing key to the
  LLM/runner process.
- The helper lives in the deny-listed `~/.config/buzz-agents/` tree, accepts only the
  `praetorium` identity and the two required Buzz write commands, loads the matching
  `.env`, and `exec`s the absolute `/home/dave/.local/bin/buzz`. Creating and testing the
  real helper is a Dave action. Repo tests use an offline mock helper and fake key.
- `bin/deliver.sh` never reads, receives, logs, or passes a private key. Its contract with
  the helper is identity slug plus Buzz CLI arguments.

This service identity is a publishing principal, not a fifth interactive agent profile;
the Roman-emperor persona roster convention is unaffected.

## Channel taxonomy

Create these six channels and record their UUIDs in `bin/buzz_routes.env`:

| Channel | Type | Route | Producers |
|---|---|---|---|
| `#ops-praetorium` | stream | `ops` | pre-snapshot, morning report, daily plan, EOD summary, `agent-alert@` |
| `#research` | forum | `research` | standing research, raw ingest, knowledge digest, weekly pre-assembly |
| `#content` | forum | `content` | Augustus content, triggered content dispatch |
| `#bd` | forum | `bd` | BD stall radar, BD follow-up drafts |
| `#market-signals` | stream | `signals` | M1 signal scan |
| `#approvals` | forum | `approvals` | inbox sync changes, aging-backlog alerts |

Streams are chronological operational feeds. Forums are for artifacts that benefit from
a root post and discussion thread. Channel creation and membership are owner-authority
actions performed by Dave from Desktop/the Mac; the box holds no owner key.

`bin/buzz_routes.env` contains only `ROUTE_<key>=<channel-uuid>`. It does not carry agent
names or credentials. Channel UUIDs are stable across renames; update the map only if the
destination UUID changes.

## Per-producer output contract

Every unit must have an explicit output adapter. Adding `DELIVERY_ROUTE` alone does not
create a delivery hook.

| Producer | Route | Delivery condition | Payload |
|---|---|---|---|
| `overnight-pre-snapshot` | ops | fresh snapshot created | `pre-snapshot-*.log` from this invocation |
| `overnight-morning-report` | ops | fresh report created | `morning-report-*.md` from this invocation |
| `praetorium-daily-plan` | ops | fresh receipt/report created | `daily-plan-*.md` from this invocation |
| `praetorium-eod-summary` | ops | fresh receipt/report created | `eod-summary-*.md` from this invocation |
| `agent-proposal` | research | proposal or verified decline | dated `standing-research` proposal; otherwise concise decline status |
| `raw-ingest` | research | proposal or verified decline | dated `raw-ingest` proposal; otherwise concise decline status |
| `knowledge-digest` | research | proposal or verified decline | dated `knowledge-digest` proposal; otherwise concise decline status |
| `weekly-pre-assembly` | research | proposal or clean decline | dated pre-assembly proposal; otherwise concise decline status |
| `augustus-content` | content | run changed content state | completion summary with affected Notion rows; no fake file artifact |
| `content-change-dispatch` | content | a new Picked row triggered work | completion summary only; a quiet poll stays silent |
| `bd-stall-radar` | bd | proposal or clean decline | dated radar proposal; otherwise concise decline status |
| `bd-followup-drafts` | bd | fresh pack or verified decline | dated follow-up pack; otherwise concise decline status |
| `m1-signal-scan` | signals | proposal or clean decline | dated signal proposal; otherwise concise decline status |
| `agent-inbox-sync` | approvals | reconciliation changed state or failed | count/IDs summary; unchanged polls stay silent |
| `inbox-backlog-alert` | approvals | existing age threshold exceeded | existing aging message |
| `agent-alert@` | ops | referenced unit failed | existing local alert text plus unit name |

Artifact selection is anchored to the current invocation, not merely “newer than 26
hours.” A unit must pass an exact artifact path or a run-start marker plus a constrained
glob. Proposal jobs may use their dated, task-specific filename and verified
proposal/decline outcome. A stale artifact must never certify or represent a new run.

No Pulse note or channel message is emitted for a quiet deterministic poll, dedup, or
no-change result unless the table explicitly requires a decline/status receipt.

## Transport seam

`bin/deliver.sh` is the single owner of Discord and Buzz transport. Callers invoke it
once:

```text
deliver.sh --job <unit> --route <key> --subject <text> \
  [--message <text>] [--file <exact-path>] [--note <short-digest>]
```

Responsibilities:

1. Validate arguments and resolve the non-secret route table.
2. Validate an exact file, when present, against the current-run marker and freshness
   budget supplied by the caller.
3. If `DELIVER_DISCORD=1`, attempt Discord delivery through the existing absolute Hermes
   entrypoint even when Buzz routing/configuration is invalid. Discord and Buzz success
   are independent during dual-run.
4. Send the Buzz channel message through the credential helper. For a file payload,
   include a short subject/body with `--content` and attach the exact file with `--file`.
5. Parse and retain the returned channel event ID.
6. Publish one bounded NIP-01 note only after the channel send succeeds. The note contains
   headline, 2–4 digest lines, job/runtime attribution, and a tested pointer to the exact
   channel/thread event.
7. Write one structured delivery receipt and exit 0 for transport failures.

The note budget is defined in **UTF-8 bytes** as `BUZZ_NOTE_MAX_BYTES=800` by default.
Truncation must preserve valid UTF-8 and reserve enough space for attribution and the
channel pointer; the pointer is never truncated. Phase 0 must confirm the actual Desktop
deep-link/pointer form before this constant and rendering contract are frozen.

Configuration errors and transport errors are both fail-soft to the calling unit, but
they are not silent: receipts distinguish `config_error`, `auth_error`,
`membership_error`, `network_error`, `discord_error`, and `partial_success`.

`bin/notify.sh`, `bin/deliver_report.sh`, and `bin/inbox_backlog_alert.sh` remain
compatibility/input adapters only. They parse their existing caller interfaces and invoke
`deliver.sh`; none owns a transport. `notify.sh` accepts/passes a route. Only
`agent-alert@` defaults to `ops`; research/content callers must not be hardcoded there.

## Structured receipts and cutover evidence

Append one JSON object per invocation to `$HOME/logs/delivery-receipts.jsonl` with:

- schema version, UTC timestamp, systemd unit/job, invocation/run marker;
- route key and resolved channel UUID;
- service-author pubkey (never its private key);
- payload type, artifact basename, size, and SHA-256 when a file exists;
- Discord attempted/result;
- Buzz channel attempted/result/event ID;
- Pulse attempted/result/event ID;
- normalized outcome and categorized error, with secrets redacted.

Create `bin/audit_buzz_dual_run.sh` to read receipts and report, per expected timer fire,
whether Discord, Buzz channel, and Pulse all succeeded or the job correctly stayed silent.
It is read-only and exits non-zero on gaps. The seven-day cutover criterion is satisfied
only by this audit, not by green systemd units or absence of error logs.

## Acceptance criteria

1. `bash bin/verify.sh` is green.
2. `tests/test_buzz_deliver.sh` is offline-by-contract and covers:
   - route resolution and absolute binary/helper resolution, never `PATH`;
   - exact-current-run artifact acceptance and missing/stale artifact rejection;
   - Discord still attempted when the Buzz route/config is invalid;
   - unknown route, missing helper, auth/membership/network failure, and non-zero Buzz
     exits remain fail-soft but produce categorized receipts;
   - channel success followed by Pulse failure records `partial_success`;
   - UTF-8-safe byte truncation always preserves attribution and the exact pointer;
   - returned channel/Pulse event IDs are captured;
   - no relay connection and no real credential are possible in the suite.
3. Tests cover every row of the producer matrix: correct route, hook, payload selector,
   and silence/decline behavior.
4. `bin/deliver.sh` is the only transport owner. Repo checks find direct
   `hermes send`, `buzz messages send`, and `buzz social publish` invocations only there
   (or in the offline test mocks/secret-side credential helper contract as explicitly
   allowlisted).
5. The work-producing `ExecStart` process never receives `BUZZ_PRIVATE_KEY` or
   `BUZZ_AUTH_TAG`; an offline environment-capture test proves it.
6. A live canary receipt proves the publishing pubkey is the Praetorium service identity
   and that it is a channel member.
7. For seven consecutive days, `audit_buzz_dual_run.sh` reports every expected in-scope
   fire as delivered to Discord and Buzz with Pulse, or correctly silent. Only then may
   Discord be disabled.
8. No unit fails solely because a delivery transport is unavailable; delivery exits 0 and
   cannot recursively fire `OnFailure=agent-alert@`.

## Files to create

- `bin/deliver.sh` — unified transport and receipt writer.
- `bin/buzz_routes.env` — route UUIDs only.
- `bin/audit_buzz_dual_run.sh` — seven-day receipt auditor.
- `tests/test_buzz_deliver.sh` — offline transport/credential-boundary suite.
- `tests/test_buzz_unit_wiring.sh` — complete producer-matrix wiring suite.
- `docs/buzz-channel-map.md` — channel taxonomy, producer matrix, authorship, and
  operational handover.

The real credential helper and service identity configuration live under
`~/.config/buzz-agents/` and are Dave-created, deny-listed, and outside git.

## Files to modify

- `bin/deliver_report.sh` — artifact lookup/validation adapter; invokes `deliver.sh` once.
- `bin/notify.sh` — text/file adapter with an explicit route; invokes `deliver.sh` once.
- `bin/inbox_backlog_alert.sh` — preserves threshold silence and invokes `deliver.sh` on
  alert.
- Any job-specific adapter required by the producer matrix, without changing
  `agent_propose.sh`, `AGENT_RUNTIME_CMD`, model/profile selection, or vault semantics.
- Canonical `systemd/*.service` sources for all 15 scheduled producers plus
  `agent-alert@.service`: add route/job metadata and the required post-delivery hook.
- `docs/runbook.md`, `docs/inbox_workflow.md`, relevant profile comments, and tests whose
  Discord-only descriptions become stale.

Never edit `/etc/systemd/system` as the only copy. Update the repo unit sources first,
commit, run `bin/deploy`, then install the changed units into `/etc/systemd/system` and run
`systemctl daemon-reload`. `bin/deploy` copies repo files into the runtime tree; it does
not install system units into `/etc`.

## Phasing

### Phase 0 — hosted capability and identity spike (blocking)

Dave mints the Praetorium identity and creates one throwaway channel. Prove:

1. identity auth and channel membership from a systemd-like, non-interactive context;
2. channel text, attachment upload/rendering, returned event ID, and exact Desktop
   pointer/deep link;
3. NIP-01 note rendering, Following behavior, and actual 300-second grouping behavior;
4. relay-signed workflow messages do not wake an owner-only agent;
5. hosted workflows are enabled and identify the deployed relay/CLI revision where
   possible;
6. a complete `request_approval → approve → resume → send_message` workflow.

Item 6 is expected to fail on the currently documented upstream implementation. Record
the result and keep approval workflows out of the migration until it passes end to end.
No real channel or identity is created from this box by an agent.

### Phase 1 — transport seam and offline contracts

Implement `deliver.sh`, routes, structured receipts, the audit command, adapters, and
offline tests. Populate placeholder/test routes only. Do not port live callers yet.

### Phase 2a — atomic canary rollout

Create the six real channels, add the Praetorium identity, fill the UUID table, and update
repo unit sources plus live unit files in one maintenance pass. Start with the four
existing artifact deliveries: morning report, daily plan, EOD summary, and BD follow-up
drafts. Enable Discord and Buzz together. There must be no interval in which ported
callers run with missing routes.

### Phase 2b — complete producer matrix

Add and test the remaining output hooks in small route-based batches. Preserve quiet
polls. After each batch: commit source, deploy runtime scripts, install changed units,
daemon-reload, start a manual safe run where possible, and inspect structured receipts.

### Phase 3 — seven-day dual-run audit

Keep `DELIVER_DISCORD=1`. Run the receipt auditor daily and resolve every missing,
partial, misattributed, or incorrectly noisy delivery. Restart the seven-day clock after
any material delivery fix.

### Phase 4 — Discord cutover

After seven consecutive clean audited days, set `DELIVER_DISCORD=0`. Keep the Discord
code path behind the flag for one-line rollback and retain receipts through the rollback
window.

### Future phase — relay workflows

- Scheduled nudges and simple reaction acknowledgments that need no agent turn are
  allowed after a hosted-relay spike.
- A white-check reaction is itself the human triage/approval signal; do not immediately
  ask for a second approval.
- Any workflow requiring durable approval state remains blocked until the hosted relay
  proves persistence and resume end to end.
- Workflows never invoke jobs in this architecture.

## Out of scope / do not touch

- No public HTTPS ingress, Tailscale Funnel, or `call_webhook` job invocation.
- No job scheduling in Buzz.
- No changes to `agent_propose.sh` semantics, `AGENT_RUNTIME_CMD`, or model/profile
  selection.
- No Hermes kanban-dispatch changes. `overnight-pre-snapshot` is already a systemd timer;
  its retired Hermes prompt explicitly says not to recreate it.
- No reads or edits under `~/.config/buzz-agents/**` by an implementation session. Every
  real identity, membership, and credential-helper step is a Dave action.
- No reads or edits to `~/vault` or `~/agent-worktrees/inbox` outside their governed
  interfaces.

## Operational preconditions

- Commit immediately after editing because `agent-workforce-auto-sync.timer` stages,
  commits, and pushes the entire dirty tree every 15 minutes.
- Fetch and compare with `origin/main` before committing. If SSH configuration prevents a
  fetch, record the blocker; do not claim remote parity.
- Source is `~/dev/agent-workforce`; runtime is `~/agent-workforce`; live system units are
  under `/etc/systemd/system`. These are three distinct deployment layers.
- Unit environment and route changes are inert until daemon-reload/restart. Compare config
  mtime with `ExecMainStartTimestamp` before testing.
- Normalize Buzz/ACP UTC logs against local Europe/Amsterdam journal timestamps.
- Workflow cron is UTC, its scheduler ticks every 60 seconds, and interval triggers have a
  60-second floor. Re-check scheduled nudges at DST transitions.
- `hermes send` and the Buzz CLI path must remain model-free and independent of a running
  LLM gateway.

-> /clear then /implement
