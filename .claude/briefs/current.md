# Brief: Migrate agent job output from Discord to Buzz (Pulse + per-activity channels)

**Date:** 2026-08-04   **Verify:** `bash bin/verify.sh` (from `~/dev/agent-workforce`)

## Decision record (settled before this brief — do not re-litigate)

**systemd stays the scheduler and invoker. Buzz becomes the surface.** A Buzz workflow
*cannot* wake an agent, verified in `block/buzz`:

- Workflow `send_message` events are **signed by the relay keypair**; the owner pubkey is
  carried only as a `p` attribution tag — `crates/buzz-workflow/src/action_sink.rs:59`.
- The agent dispatch gate is `is_owner_or_sibling(author, …)`, which returns `false` for any
  author that is neither the owner nor a NIP-OA sibling, and **fails closed** when no owner is
  configured — `crates/buzz-acp/src/lib.rs:192-216`.
- Therefore a relay-signed workflow message is rejected by every `--respond-to owner-only`
  agent, and its `p` tag names Dave rather than the target agent, so `event_mentions_agent`
  (`lib.rs:2831`) also fails. Two independent blockers.

The only workflow→agent path is `call_webhook`, which the schema requires to be a public
HTTPS endpoint and which needs elevated owner/admin authority (SEC-006,
`crates/buzz-workflow/src/schema.rs`). Out of scope — no public ingress is being added.

Scope is **agent-bearing jobs only** (13 units). Deterministic infra timers stay on systemd
and stay silent.

## Acceptance criteria

1. `bash bin/verify.sh` is green (bash syntax + `shellcheck -S error` clean over every
   script in `bin/`, plus every `tests/*.sh`).
2. `tests/test_buzz_deliver.sh` exists, is offline-by-contract (mock `buzz` binary, no relay
   connection, no real key), and passes as part of the gate. It asserts:
   - a routing key resolves to the correct channel UUID from the routing table;
   - an unknown/empty routing key fails soft (exit 0, logged, no send attempted);
   - a missing or stale artefact is skipped without sending (existing 26h freshness rule);
   - the `buzz` binary is resolved by absolute path, never via `PATH`;
   - a non-zero exit from `buzz` still yields exit 0 from the caller (fail-soft contract);
   - Pulse note content is truncated to the note budget and always carries the channel
     pointer.
3. `bin/deliver.sh` is the **single** owner of outbound transport. After the change,
   `grep -rn "hermes.*send\|hsend" bin/` returns hits in `bin/deliver.sh` only — the three
   existing copies in `notify.sh`, `deliver_report.sh` and `inbox_backlog_alert.sh` are gone.
4. Dual-run: for 7 consecutive days every in-scope job's artefact appears in **both** the
   Discord channel and its mapped Buzz channel, with a Pulse note authored by the agent that
   produced it. Only then does Phase 4 remove Discord.
5. No unit fails because Buzz is unreachable — delivery remains fail-soft (`exit 0`), so
   `OnFailure=agent-alert@` never fires for a delivery hiccup.

## Files to create

- `bin/deliver.sh` — the one transport seam. Resolves the `buzz` binary absolutely
  (`$HOME/.local/bin/buzz`), reads the routing table, and exposes two modes:
  `note` (→ `buzz social publish --content`) and `channel`
  (→ `buzz messages send --channel <uuid> --content - [--file <path>]`). Always exits 0.
  Logs to `$HOME/logs/deliver.log`. Keeps the existing `MAX_REPORT_AGE_SECS` staleness guard
  and the `DELIVER_DISCORD=1` dual-run flag (default on until Phase 4).
- `bin/buzz_routes.env` — the routing table: `ROUTE_<key>=<channel-uuid>` plus
  `ROUTE_<key>_AGENT=<name>`. **Single source of truth** for activity→channel mapping; a
  channel rename is one edit here and nowhere else. Non-secret (channel UUIDs only, no keys).
- `tests/test_buzz_deliver.sh` — offline suite per criterion 2, following the
  `tests/rhythm_test_lib.sh` mock-binary pattern.
- `docs/buzz-channel-map.md` — the taxonomy table below, so the mapping is reviewable outside
  Notion and travels with the repo.

## Files to modify

- `bin/deliver_report.sh` — strip the local `hsend()` (lines 31-44) and the direct
  `hsend --to discord` call (line 70); call `deliver.sh` with the routing key from a new
  `REPORT_ROUTE` env var. Keep the freshness guard and fail-soft `exit 0` semantics exactly
  as they are. Do not change `REPORT_DIR`/`REPORT_GLOB`/`REPORT_SUBJECT` — the units set them.
- `bin/notify.sh` — strip its duplicate `hsend()`; delegate to `deliver.sh` with route `ops`.
- `bin/inbox_backlog_alert.sh` — strip its third copy of the entrypoint resolver; delegate to
  `deliver.sh` with route `approvals`. Preserve the "stay silent when under threshold" rule.
- `/etc/systemd/system/<unit>.service` (13 units) — add `Environment=REPORT_ROUTE=<key>` per
  the taxonomy. **Requires sudo; not a repo change.** List the exact lines in the handover so
  Dave can apply them in one pass.

## Channel taxonomy (create these; record UUIDs in `bin/buzz_routes.env`)

| Channel | Type | Route key | Jobs |
|---|---|---|---|
| `#ops-praetorium` | stream | `ops` | overnight-pre-snapshot 04:25, overnight-morning-report 06:15, praetorium-daily-plan 06:00, praetorium-eod-summary 22:15, `agent-alert@` failures |
| `#research` | forum | `research` | agent-proposal 04:30, raw-ingest 03:00, knowledge-digest Sun 09:00, weekly-pre-assembly Fri 22:00 |
| `#content` | forum | `content` | augustus-content 01:30, content-change-dispatch `*/15` |
| `#bd` | forum | `bd` | bd-stall-radar 23:00, bd-followup-drafts 23:30 |
| `#market-signals` | stream | `signals` | m1-signal-scan Mon+Wed 05:30 |
| `#approvals` | forum | `approvals` | agent-inbox-sync `*/30`, inbox-backlog-alert 06:20 |

`stream` for chronological low-interaction feeds; `forum` for anything where each item earns
its own thread (a proposal, a draft, a follow-up, an approval).

## Pulse layer

Every in-scope job publishes a NIP-01 note **authored by the agent that did the work**, in
addition to the channel message. This is what makes Pulse useful rather than a second firehose:

- `AgentNoteGroup` groups one agent's notes within a 300s window into a single activity card
  (`mobile/lib/features/pulse/pulse_models.dart`), so the 04:25→06:15 overnight sequence reads
  as one card.
- The "Following" tab filters by follow graph, so Dave tunes volume per agent rather than
  per job.
- Reactions on notes become the lightweight triage signal that Phase 3 workflows trigger on.

**Hard constraint:** `buzz social publish` accepts `--content` only — no `--file`, no subject
(verified against the installed CLI). So the note is a short digest (headline + 2-4 lines +
pointer to the channel thread) and the full artefact goes to the channel message via
`buzz messages send --file`. `deliver.sh` owns this split; no caller reimplements it.

## Phasing

- **Phase 0 — spike (blocking).** Create one throwaway channel. Prove: (a) `buzz social publish`
  works from a systemd-like context with an agent identity; (b) the note renders in Pulse and
  groups as expected; (c) **empirically confirm** the relay-signed workflow message does *not*
  wake an `owner-only` agent, so the decision record above is evidence-backed rather than
  code-reading alone; (d) workflows are actually enabled on the hosted relay
  `wss://vpc.communities.buzz.xyz` — untested, no owner key on this box.
- **Phase 1 — transport seam.** `bin/deliver.sh` + routing table + tests + port the 3 callers.
  Dual-deliver to Discord and Buzz. Gate green. This phase is pure repo work.
- **Phase 2 — channels + routing.** Create the 6 channels, fill in UUIDs, add the per-agent
  Pulse note to each job's tail, add `REPORT_ROUTE` to the 13 units.
- **Phase 3 — workflows (relay-side only).** `#approvals`: `on: reaction_added,
  emoji: white_check_mark` → `request_approval` → `send_message`. Plus scheduled nudges that
  need no agent turn. Never job invocation.
- **Phase 4 — cutover.** After 7 clean dual-run days, default `DELIVER_DISCORD=0`. Keep the
  Discord path behind the flag for one-line rollback.

## Out of scope / do not touch

- **No public HTTPS ingress**, no Tailscale Funnel, no `call_webhook` job invocation.
- **Deterministic infra timers stay on systemd and stay silent:** `qmd-refresh`,
  `ttm-pool-drain`, `local-tier-eval`, `agent-workforce-auto-sync`, `memory-consolidation`,
  `sysstat-*`, `apt-*`, `logrotate`, `man-db`, `fwupd-refresh`.
- `~/.config/buzz-agents/**` — deny-listed and **enforced against Bash too**. No session can
  read or edit an agent `.env`. Every credential wiring step is a Dave action.
- `~/vault`, `~/agent-worktrees/inbox` — governed by their own CLAUDE.md.
- Do not change `agent_propose.sh` job semantics, `AGENT_RUNTIME_CMD`, or any model/profile
  selection. This is a delivery-surface change only.
- Do not touch the Hermes kanban dispatcher or `hermes cron`. The single remaining Hermes cron
  job (`overnight-pre-snapshot`) keeps its schedule; only its *delivery* moves.

## Notes / preconditions (confirmed 2026-08-04)

- Gate is `bash bin/verify.sh`; `tests/` already holds 26 suites and a shared
  `rhythm_test_lib.sh` with a mock-binary, offline-by-contract pattern to follow.
- Repo `~/dev/agent-workforce` is on `main`, working tree clean.
- **Deploy trap:** source is `~/dev/agent-workforce`, but 11 of the 13 units execute the
  **deployed** copy at `~/agent-workforce/bin/…`. Only `agent-workforce-auto-sync` and
  `agent-inbox-sync` run from `~/dev/…`. Nothing deploys automatically — run `bin/deploy`
  or the fix is invisible to systemd.
- **Auto-sync race:** a 15-min timer runs `git add -A` + commit + push to `origin/main`.
  Commit immediately after editing or the work is swept into a generic "Auto-sync" commit
  with unrelated WIP.
- **UTC trap:** Buzz workflow cron is **UTC**; systemd here is Europe/Amsterdam (CEST, +2).
  Any Phase 3 nudge must be authored in UTC and re-checked at DST. `buzz-acp` also logs UTC
  while `journalctl` renders local — normalise before building any timeline.
- **Interval floor:** workflow `interval` must be ≥60s; the cron loop ticks every 60 seconds.
- **One workflow per channel:** a `send_message` channel override must equal the workflow's own
  channel (`executor.rs:486`). No fan-out — this is *why* separate channels are required, not
  merely nice.
- **Credential wiring is a Dave action.** Publishing as an agent needs that agent's
  `BUZZ_PRIVATE_KEY` in the unit's `EnvironmentFile`. This widens the known exposure of the
  agent nsec in `ps` / `systemctl status` — call it out in the handover rather than silently
  adding units that leak it.
- **Config reload:** units load `EnvironmentFile` only at start. Before concluding a routing
  fix didn't work, compare the file mtime against
  `systemctl show <unit> -p ExecMainStartTimestamp`.
- `hermes send` currently reaches Discord with no LLM spend and no running gateway. The Buzz
  path must match that property — model-free, no gateway dependency.

-> /clear then /implement
