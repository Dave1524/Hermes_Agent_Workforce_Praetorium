# Brief: T7.2 — Diagnose Augustus content dispatch reliability
**Date:** 2026-09-11
**Notion:** [T7.2 — Diagnose Augustus content dispatch reliability](https://app.notion.com/p/3d78d7681ede817bb4cfc2543339f9f8)
**Isolation:** `branch` — use `debug/t7-2-augustus-content-dispatch-reliability`; this is a normal diagnostic/fix, not a live-main or worktree exception.
**Verify:** `bash bin/verify.sh` from the repo root. If `bin/` or `buzz-team/` changes, run `bin/deploy` before the final gate because deploy drift is part of `verify.sh`.

Source of acceptance: `docs/dev-plan-2026-09.md` T7.2. The Notion page is not publicly readable from this box; the reviewed task text in the repo is authoritative for implementation.

## Acceptance criteria

1. Reproduce and correlate the three failed UTC runs — 2026-09-06, 2026-09-07 and
   2026-09-09 — without treating an INFO-silent `buzz-agent@augustus` journal as evidence
   that no turn ran. For each run, one evidence row must join:
   - the trigger delivery receipt and raw trigger event;
   - trigger author, kind, channel and actual `p` tag;
   - channel membership and Augustus's admission rule, with historical unknowns labelled
     rather than replaced by current state;
   - Augustus cgroup/CPU or rollout evidence, with an idle sibling measured over the same
     interval;
   - pre/post board digest and the exact row transition, if any;
   - every Augustus-authored reply event after dispatch; and
   - the terminal log line and timeout.
2. Diagnose in this order and stop at the first failed seam that fully explains the run:
   trigger addressing/routing → channel membership and author admission → cgroup/turn
   activity → board/reply observation → timeout. The cause is evidenced, not inferred.
3. Preserve one logical `augustus-content` workflow with two entry points:
   - nightly `augustus-content.timer`; and
   - `content-change-dispatch.timer` only when a new `Picked` row actually dispatches.
   A quiet change poll, fail-soft Notion read, or flock overlap is not an eligible content
   run and must not count in reliability.
4. Give every published dispatch one run identity. Use the trigger event's
   `buzz_event_id` — already present in `~/logs/delivery-receipts.jsonl` — as the canonical
   content run ID. The same ID must appear in the attempt/journal terminal line, board
   snapshot metadata and change-dispatch log. Do not add a parallel database or a second
   receipt store.
5. Exactly one valid terminal outcome is accepted:
   - a named content row moved from `Picked` to `Draft`, with the row/page ID serving as
     the draft location; or
   - Augustus authored a post-dispatch reply beginning `DECLINE:`, with its event ID
     recorded.
   A generic board mutation, an Idea-only pitch, a failure sentinel, an unrecognised reply,
   or silence is not a valid terminal outcome.
6. Add two explicit contract checks and matching regression assertions:
   - `content-board-transition-produced-draft` fails by name when no baseline `Picked`
     row reaches `Draft` (and is n/a only for a valid owned decline);
   - `owned-reply-evidences-decline` fails by name when no valid draft transition exists
     and no post-dispatch Augustus-authored `DECLINE:` exists (and is n/a only for a valid
     draft transition).
   Remove timeout/silence from any check's accepted-success branch. Failure paths may still
   be named for diagnosis; naming a failure must never make it pass.
7. Prove the existing three-state process contract remains intact:
   - exit `4` / `CRASHED`: nobody was asked;
   - exit `1` / `FAIL`: asked but no valid terminal outcome, including timeout;
   - exit `0`: `Picked -> Draft` or owned `DECLINE:` only.
   `content-change-dispatch.sh` advances `content_picked.state` only for the last case and
   only when a run record exists; lock skips and missing records keep the row eligible.
8. The production cause is either fixed at the failed seam, or recorded as `DECIDED` in
   `design/contracts/augustus-content.md` with the evidence, next actor and concrete next
   action. Do not tune the timeout as a substitute for a missing trigger or missing turn.
9. Complete three consecutive **eligible live dispatches** across the combined logical
   workflow with a valid terminal outcome. The streak must include at least one nightly
   dispatch and one new-`Picked` change dispatch. Record run ID, entry point, page/reply
   evidence and elapsed seconds for all three. Do not manufacture a production `Picked`
   row without Dave's explicit direction.
10. Keep the 1200-second wait or re-base it from measured successful end-to-end durations.
    Record the samples and rule used. A longer timeout requires evidence of a still-active
    turn; successful runs observed at 164s (2026-09-08 UTC) and 196s (2026-09-10 UTC)
    already disprove “normally needs more than 20 minutes.”
11. Carry T4.3's actionability into the evidence:
    - artifact: Notion page ID, `Picked -> Draft`, and draft location in that page;
    - next actor: Dave;
    - next action: review/edit the draft, then schedule/publish or reject it;
    - benefit signal: `Picked`-observed to `Draft`-observed latency and valid-terminal-
      artifact rate. Record raw timestamps and call an observation-window bound an estimate;
      do not invent exact Picked time, human-edit, publication or ROI data.
12. All local harnesses pass, the named contract checks validate, and
    `bash bin/verify.sh` exits 0.

## Confirmed starting evidence

All times below are UTC, normalised once. The receipt's `notify=augustus` is routing intent,
not proof of the raw event's `p` tag; implementation must fetch the event before concluding
that addressing worked.

| Run date | Trigger receipt event ID | Existing terminal evidence | Result |
|---|---|---|---|
| 2026-09-06 | `1a661dc309a1ba10f099eb09fbc7ca978bea154bda5f9a1653daefc976cee02f` | published 23:31:37; `no board movement and no reply` 23:51:53 | failed |
| 2026-09-07 | `5293f3b3542fa3444139d70aec327e1e5baf645d972c27d497b786181ea45e85` | corpus armed 23:33:51; published 23:33:53; timeout 23:53:53 | failed |
| 2026-09-09 | `4fd8670d33de1ec46afea080f8d6d977911726a8d0a02e11c25a0f4e379e01a9` | corpus armed 23:33:51; published 23:33:54; timeout 23:53:52 | failed |
| 2026-09-08 | `5baec07c7fd90b497d9522b509abff6e413ef979fc071b97b63ec096e5c05e5c` | board moved at 23:36:47, 164s after publish | valid comparison |
| 2026-09-10 | `74eb056f9593315deaa557f7bbbf49ac0b2c9bcf8eab2b16b4db4c4d49a442da` | board moved at 23:38:56, 196s after publish | valid comparison |

The current runner only logs “board moved,” accepts any status-digest difference, discards
the trigger event ID after validating the receipt, and has no shared run ID. The current
contract's `run-ended-in-a-named-outcome` check counts the timeout line as a named ending;
that is diagnostic completeness, not successful completion, and is the outstanding T4.3
defect.

## Diagnostic and implementation sequence

### 1. Establish the five-run evidence table

For each trigger event ID above:

1. Resolve the matching schema-1 line in `~/logs/delivery-receipts.jsonl`. Record its UTC
   timestamp, `buzz_result`, kind, channel, author identity and notify target.
2. Fetch the raw event with the existing Buzz event reader and inspect its actual tags.
   Assert author = the repo's `praetorium` pubkey, kind = `45001`, channel = the content
   route and one `p` tag equals the Augustus pubkey from `bin/buzz_agents.env`.
3. Check content-channel membership for both the publishing identity and Augustus. Current
   membership proves only current state. If no historical membership event is available,
   write `unknown for 2026-09-0x`; do not backfill history from today's list.
4. Confirm `buzz-team/augustus.toml` admits the `praetorium` author with
   `require_mention = true`, and prove the running unit had loaded that version using the
   source/deployed drift check plus config mtime versus `ExecMainStartTimestamp`.
5. Look for a Codex rollout covering the dispatch (`buzz-team/trace-turn.sh` is the existing
   reader). For a fresh reproduction, sample `CPUUsageNSec` immediately before publish and
   each poll for Augustus and an idle sibling selected by the lowest pre-run 60-second
   delta. Resolve the unit's `ControlGroup`, read `cgroup.procs`, and print command names
   only (`ps -o comm=`); never use `ps -f` or a status view that exposes argv credentials.
6. Read the channel with `messages get`, not `messages thread`, using author + dispatch
   epoch and no kind filter. Record every Augustus reply event ID and first line.
7. Join the pre-run digest, post-run digest, attempt log, cost record and timeout under the
   trigger event ID. State the earliest seam whose evidence diverges.

The decision table is:

| Evidence | Classification / owner |
|---|---|
| raw event lacks Augustus `p` tag or wrong kind/channel/author | route/publisher defect; fix repo wiring and its harness |
| identity absent from channel | membership state; Dave repairs membership, then re-run; do not automate identity mutation |
| `praetorium` rule absent, stale or rejected | admission/config defect; fix `buzz-team/augustus.toml`, deploy/restart, verify loaded |
| gates good, Augustus CPU/cgroup and rollout stay idle while sibling control stays idle | dispatch-to-harness defect; inspect buzz-acp decision evidence, do not infer from INFO silence |
| rollout/CPU active, no board write and no publish call | agent/profile execution defect; fix the named instruction/tool failure |
| reply exists but waiter reports silence | reply-reader/filter defect in `run_content_via_buzz.sh` |
| `Picked -> Draft` exists but waiter reports no board movement | digest/comparison defect |
| active turn continues near deadline | only this branch justifies a timeout change |

### 2. Add run-scoped evidence without a new telemetry system

In `bin/run_content_via_buzz.sh`, make the receipt-validation snippet return the successful
trigger `buzz_event_id`; validate it as 64 lowercase hex and use it as `run_id`. Append
`run_id=<id>` to the existing `content_board.snapshot`, and include `run_id=<id>` in all
post-publish log lines: trigger, board transition, matched reply, unknown reply and timeout.
Log exact status transitions (`page=<id> from=Picked to=Draft`) rather than the phrase
“board moved.”

In `bin/content_change_dispatch.sh`, label the entry point as `picked-change`, record the
new page IDs before invoking `agent_propose.sh`, and after return read the same snapshot's
`run_id`. Include it on the dispatch-complete/hold line before changing state. The nightly
runner defaults the entry point to `nightly`. Both still invoke the same override and
runtime.

No new Redis key, SQLite table, REST endpoint, JSONL receipt schema or Buzz event kind is
introduced. New textual contracts are limited to:

- snapshot metadata `run_id=<64-hex trigger event id>`;
- attempt/journal tokens `run_id=<same id>` and `entry_point=nightly|picked-change`;
- transition evidence `page=<id> from=Picked to=Draft`.

### 3. Tighten terminal detection and the T4.3 contract

Compare the baseline and current digest by page ID and status. Exit 0 on board evidence
only when at least one page that was `Picked` before dispatch is `Draft` afterward. An
unrelated row edit, removal, new Idea, or other status transition remains useful diagnostic
evidence but does not complete the run.

Keep the existing author+epoch `DECLINE:` branch and its `decline_event=<id>` snapshot
metadata. Failure sentinels and unknown replies stay exit 1. Update
`design/contracts/augustus-content.md` so the two named checks above decide the alternatives
and the general “named outcome” check no longer treats a timeout as contract success.

Update the Outputs fields to name the page ID/draft location, Dave's next action, raw
Picked-observed/Drafted-observed timestamps, latency, and valid-terminal-artifact rate.
Do not claim human use, edits, scheduling, publication or ROI until another system measures it.

### 4. Apply only the evidenced fix

Patch the earliest failed seam and add its regression to the owning suite. Do not edit all
layers prophylactically. If the defect is live membership, record the external repair and
the Dave-owned next action; there is no repo automation for adding relay members. If the
cause cannot be reproduced after the evidence work, record `DECIDED` with exactly what is
known/unknown, retain the run-scoped instrumentation, and validate with the three-run streak.

### 5. Validate and decide the timeout

Measure trigger receipt timestamp to the first valid terminal evidence, not total systemd
wall time. Include one poll interval in the observation error. Keep 1200 seconds unless an
active-turn trace shows it is truncating legitimate work; if re-based, document the sample
set and formula beside `AGENT_BUZZ_WAIT_MINUTES` and pin the chosen boundary in
`tests/test_run_content_via_buzz.sh`.

## Files to modify

- `bin/run_content_via_buzz.sh` — retain the trigger receipt event ID as the run ID; emit
  run-scoped evidence; require an exact `Picked -> Draft` transition or owned decline.
- `bin/content_change_dispatch.sh` — identify the `picked-change` entry point, preserve new
  Picked IDs in the log, join the dispatched run ID, and never advance state without a
  valid recorded terminal result.
- `design/contracts/augustus-content.md` — record the diagnosis/decision; add the two named
  terminal checks; correct the timeout-as-success gap; retain the two-trigger/one-workflow
  model and T4.3 actionability/benefit fields.
- `tests/test_run_content_via_buzz.sh` — add run-ID propagation, exact transition, unrelated
  mutation, missing-movement and missing-reply cases. Keep raw kind/mention assertions and
  author+epoch reply fixtures.
- `tests/test_content_change_dispatch.sh` — assert the change entry point and new Picked IDs
  join to the same content run and that quiet ticks do not create eligible runs.
- `tests/test_content_dispatch_state_hold.sh` — assert timeout, lock skip, missing run record
  and invalid transition all hold state; valid `Picked -> Draft` and owned decline may
  advance it.
- `tests/test_buzz_adapters.sh` — if the completion summary changes, pin the run ID, page ID,
  draft location and next actor in its existing content receipt fixtures.
- `profiles/augustus_content_task.md` — modify only if the evidence names an execution/profile
  defect or a terminal wording ambiguity.
- `buzz-team/augustus.toml` — modify only if the evidence names author admission; then run
  the fleet gate and deploy through the repo's Buzz-team path.
- `bin/buzz_routes.env`, `bin/buzz_agents.env` or `bin/deliver.sh` — modify only if the raw
  event proves routing/addressing wrong. Existing receipt intent is not sufficient evidence.

## Files to create

- None planned. The repository already owns the runner, board digest, snapshot, receipt,
  trace reader, contract and regression harnesses. If implementation discovers that a new
  interface is unavoidable, stop and amend this brief with its path, format, owner and
  tests before adding it.

## Test plan

- `bash tests/test_run_content_via_buzz.sh`
  - trigger remains kind `45001` and carries Augustus's `p` tag;
  - receipt event ID becomes the run ID in snapshot and every terminal log;
  - `Picked -> Draft` for the same page exits 0 and names the page;
  - Idea creation, row deletion and unrelated status change do not count;
  - owned post-dispatch `DECLINE:` exits 0 and records both run and reply event IDs;
  - missing board movement fails under
    `content-board-transition-produced-draft`;
  - missing/foreign/stale reply fails under `owned-reply-evidences-decline`;
  - unknown/failure sentinels remain failures; publish failure remains exit 4.
- `bash tests/test_content_change_dispatch.sh`
  - quiet/fail-soft ticks are ineligible and dispatch nothing;
  - a new Picked row invokes the same Augustus override once with
    `entry_point=picked-change`;
  - the log joins new page IDs to the content run ID.
- `bash tests/test_content_dispatch_state_hold.sh`
  - state advances only on exact draft transition or owned decline;
  - timeout, crash, lock skip, no cost/run record and malformed/missing run ID hold state.
- `bash tests/test_buzz_interactive_harness.sh` for the static author-admission join.
- `bash tests/test_buzz_deliver.sh` for route kind, mention and receipt behavior.
- `bash tests/test_buzz_adapters.sh` if delivery-summary fields change.
- `python3 tests/test_contract_schema.py` and `bash tests/test_contract_schema.sh` for the
  two named checks and contract shape.
- Live evidence: three consecutive eligible runs, combined streak, at least one per entry
  point. For each, preserve the trigger receipt/event, same-ID attempt or journal lines,
  transition or decline event, and measured duration. A failed eligible run resets the streak.
- Final: `bash bin/verify.sh`.

Fixtures stay local: stub Buzz, Notion helper, digests, receipts and cost/run records. Unit
tests never call the live relay, Notion, qmd or a model. Live probes happen only in the
explicit evidence/streak phase.

## Out of scope / do not touch

- Control Room UI/API work (T5.3 and sub-cards).
- Vault files, vault branches, qmd content or any path under `~/vault/`.
- New workflow orchestration, a second content runner, a new scheduler, Redis, SQLite,
  a raw REST integration or a new receipt database.
- Changing the nightly cadence or retiring the 15-minute Picked-row trigger.
- Widening Augustus's bwrap namespace or exposing a credential to his shell.
- Changing the corpus gate, Notion broker transport or publishing outward unless the
  ordered evidence specifically identifies that existing seam.
- Treating Idea creation alone, journal silence, unit presence or a fail-soft exit as proof
  that content was drafted.
- Manufacturing production board rows or contacting Augustus conversationally to ask what
  happened. Diagnose from events, membership, cgroup/rollout, board state and receipts.

## Notes / preconditions

- Work from `~/dev/agent-workforce`, not the deployed `~/agent-workforce` copy. Deploy only
  after the repo change is committed on the branch; use `bin/deploy`, never manual copies.
- The repo's auto-sync timer may commit every dirty path on `main`. Create the isolation
  branch before implementation and commit explicit paths promptly.
- Before the first live reproduction, confirm the content channel and Augustus pubkey from
  `bin/buzz_routes.env` / `bin/buzz_agents.env`; do not copy IDs out of a secret env file.
- `buzz-agent@*` INFO logs are lifecycle-only. Compare `CPUUsageNSec` and cgroup command
  names; never print full argv because the agent private key is present there.
- `buzz messages get --channel ... --since ...` is the reply reader. Do not substitute
  `messages thread` or a kind filter: Augustus replies as kind `45003`, while the trigger is
  kind `45001`.
- Current membership and a currently active unit cannot prove the state on 2026-09-06,
  09-07 or 09-09. Preserve unknowns.
- The fetched branch check could not be completed in this planning session because system
  SSH rejected `/etc/ssh/ssh_config.d/20-systemd-ssh-proxy.conf` for bad owner/permissions.
  Re-run `git fetch origin` after that machine-level issue is repaired; do not bypass SSH
  configuration or read credential files.
